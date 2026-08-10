# Onderzoeksomgeving en persona — implementatieplan (W0 + W2, backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De backend antwoordt kloppend voor Robin Vogel als bloemenkweker, en de
tijdelijke serversleutel voor 25/27 augustus is als besluit vastgelegd in plaats
van als stille configwijziging.

**Architecture:** Twee kleine wijzigingen in de KvK-mockdata, één nieuwe
invariant-test die voorkomt dat een persona half bestaat, en drie
documentatiewijzigingen. Geen productiecode in de host zelf.

**Tech Stack:** Python 3.12, pytest (`asyncio_mode=auto`), ruff, uv.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-10-gebruikersonderzoek-augustus-design.md`
- Onderzoekspersona: `?persona=bloemenkweker` → Kwekerij De Bloesem, KvK **62345681**
- Sleutel wordt ingetrokken op **27 augustus 2026**
- Commits zonder `Co-Authored-By`-trailer (voorkeur van de repo-eigenaar gaat vóór
  de regel in `CLAUDE.md` regel 73)
- `NEXT_STEPS.md` bijwerken vóór elke commit (staat in `.gitignore`, dus niet mee te committen)
- Mock-persona's volgen de échte KvK Basisprofiel-vorm (PDR-007)

## Bestanden

| Bestand | Verantwoordelijkheid | Actie |
|---|---|---|
| `services/mcp/kvk/server.py` | `MOCK_PROFIELEN` en `MOCK_EIGENAREN` | Wijzigen |
| `services/host/tests/test_demo_personas.py` | Invarianten over de drie MCP-mocks | Uitbreiden |
| `docs/decisions/PDR-010-sleutel-van-de-gebruiker.md` | Addendum onderzoeksvenster | Wijzigen |
| `docs/deploy-zad.md` | Beschreven deploymentstand | Wijzigen |
| `services/host/.env.example` | Voorbeeldconfiguratie | Wijzigen |

## Ontwerpkeuze die tijdens het plannen naar boven kwam

De spec zei "`MOCK_EIGENAREN["62345681"]` krijgt Robin Vogel als natuurlijk
persoon". Bij het lezen bleek De Bloesem bewust een **VOF** te zijn, mét comment:
"geen rechtspersoonlijkheid, de vennootschap zelf is de eigenaar". Dat is voor een
VOF de correcte vorm van het KvK Basisprofiel, dus dat comment klopt.

Een natuurlijk persoon toevoegen aan een VOF zou de API-vorm breken (PDR-007).
Daarom verandert dit plan de **rechtsvorm** naar Eenmanszaak, in profiel én
eigenaar tegelijk. Een kweker met zeven medewerkers als eenmanszaak is realistisch —
de rechtsvorm zegt niets over het personeelsaantal — en het past bij de
frontend-framing "Robin Vogel van …", waarin de respondent de eigenaar speelt.

**Let op voor de frontend (jouw kant):** `_data/personas.json[13]` moet dezelfde
rechtsvorm noemen, anders spreekt de pagina Bedrijfsgegevens de assistent tegen.

---

### Task 1: De Bloesem krijgt Robin Vogel als eigenaar

**Files:**
- Modify: `services/mcp/kvk/server.py` (`MOCK_PROFIELEN["62345681"]`, `MOCK_EIGENAREN["62345681"]`)
- Test: `services/host/tests/test_demo_personas.py`

**Interfaces:**
- Consumes: het bestaande `_load(naam)`-helpertje boven in `test_demo_personas.py`,
  dat een MCP-server per bestandspad laadt (`services/mcp/<naam>/server.py`).
- Produces: `MOCK_EIGENAREN["62345681"]["natuurlijkPersoon"]["volledigeNaam"] == "Robin Vogel"`

- [ ] **Step 1: Schrijf de falende tests**

Voeg onderaan `services/host/tests/test_demo_personas.py` toe:

```python
def test_bloesem_eigenaar_is_robin_vogel():
    """De respondent speelt Robin Vogel; `kvk__eigenaar` hoort dat te bevestigen."""
    kvk = _load("kvk")
    eigenaar = kvk.MOCK_EIGENAREN["62345681"]
    assert eigenaar["natuurlijkPersoon"]["volledigeNaam"] == "Robin Vogel"


def test_bloesem_rechtsvorm_is_gelijk_in_profiel_en_eigenaar():
    """Twee plekken, één waarheid: anders spreekt het profiel de eigenaar tegen."""
    kvk = _load("kvk")
    assert (
        kvk.MOCK_PROFIELEN["62345681"]["rechtsvorm"]
        == kvk.MOCK_EIGENAREN["62345681"]["rechtsvorm"]
    )


def test_eenmanszaak_heeft_geen_rechtspersoon():
    """Vormcheck op het KvK Basisprofiel (PDR-007): een eenmanszaak heeft er geen."""
    kvk = _load("kvk")
    for nummer, eigenaar in kvk.MOCK_EIGENAREN.items():
        if eigenaar["rechtsvorm"] == "Eenmanszaak":
            assert "rechtspersoon" not in eigenaar, nummer
            assert "natuurlijkPersoon" in eigenaar, nummer
```

- [ ] **Step 2: Draai de tests en zie ze falen**

Run: `uv run pytest services/host/tests/test_demo_personas.py -q`
Expected: FAIL — `KeyError: 'natuurlijkPersoon'` en een ongelijke rechtsvorm
("Vennootschap onder firma" versus wat de eigenaar noemt).

- [ ] **Step 3: Pas de mockdata aan**

In `services/mcp/kvk/server.py`, in `MOCK_PROFIELEN["62345681"]`:

```python
    "rechtsvorm": "Eenmanszaak",
```

En vervang het hele blok `MOCK_EIGENAREN["62345681"]` door:

```python
    # Eenmanszaak: de KvK levert dan een natuurlijk persoon, geen rechtspersoon.
    # Robin Vogel is de persona die de respondent speelt tijdens het
    # gebruikersonderzoek van 25/27 augustus 2026.
    "62345681": {
        "kvkNummer": "62345681",
        "rechtsvorm": "Eenmanszaak",
        "natuurlijkPersoon": {
            "geslachtsnaam": "Vogel",
            "voornamen": "Robin",
            "volledigeNaam": "Robin Vogel",
        },
    },
```

- [ ] **Step 4: Draai de tests en zie ze slagen**

Run: `uv run pytest services/host/tests/test_demo_personas.py -q`
Expected: PASS

- [ ] **Step 5: Draai de volledige suite en de linter**

Run: `uv run pytest -q && uv run ruff check .`
Expected: alles groen. Als een bestaande test op "Vennootschap onder firma" toetste,
hoort die mee te veranderen — die test legde de oude keuze vast, niet een regel.

- [ ] **Step 6: Commit**

```bash
git add services/mcp/kvk/server.py services/host/tests/test_demo_personas.py
git commit -m "fix(kvk): Robin Vogel is de eigenaar van Kwekerij De Bloesem

De respondent speelt tijdens het gebruikersonderzoek van 25/27 augustus Robin
Vogel als bloemenkweker. De Bloesem stond als VOF in de mock, en dan levert het
KvK Basisprofiel terecht de vennootschap als eigenaar in plaats van een persoon.
Rechtsvorm nu Eenmanszaak in profiel en eigenaar tegelijk; een kweker met zeven
medewerkers als eenmanszaak is realistisch, want de rechtsvorm zegt niets over
het personeelsaantal.

De frontend (personas.json) moet dezelfde rechtsvorm noemen, anders spreekt de
pagina Bedrijfsgegevens de assistent tegen."
```

---

### Task 2: Een persona kan niet half bestaan

**Files:**
- Test: `services/host/tests/test_demo_personas.py`

**Interfaces:**
- Consumes: `_load("kvk")`, `_load("netbeheerder")`
- Produces: geen code, alleen bewaking

Dit vangt de klasse fout die dit hele onderzoek bijna liet vastlopen: een persona
die in de ene laag bestaat en in de andere niet.

- [ ] **Step 1: Schrijf de falende test**

```python
def test_elke_mockpersona_is_compleet():
    """Een persona bestaat in alle drie de lagen, of nergens.

    De blokkade die het gebruikersonderzoek van augustus 2026 bijna sloopte was
    precies dit: de frontend bood persona's aan die de backend niet kende.
    """
    kvk = _load("kvk")
    netbeheerder = _load("netbeheerder")

    for nummer in kvk.MOCK_PROFIELEN:
        assert nummer in kvk.MOCK_EIGENAREN, (
            f"{nummer} heeft een profiel maar geen eigenaar; `kvk__eigenaar` valt "
            f"dan terug op de echte KvK-API en faalt voor een mock-persona"
        )
        assert nummer in netbeheerder.MOCK_VERBRUIK, (
            f"{nummer} heeft een profiel maar geen verbruik; de assistent kan de "
            f"informatieplicht dan niet beoordelen en gaat het uitvragen"
        )
```

- [ ] **Step 2: Draai de test**

Run: `uv run pytest services/host/tests/test_demo_personas.py::test_elke_mockpersona_is_compleet -q`
Expected: PASS — de drie huidige persona's zijn compleet. Deze test bewaakt de
toekomst; hij hoort nu al groen te zijn.

- [ ] **Step 3: Bewijs dat de test tanden heeft**

Verwijder tijdelijk `"56789012"` uit `MOCK_EIGENAREN`, draai de test opnieuw, zie
hem falen met de bedoelde melding, en zet het daarna terug.

Run: `uv run pytest services/host/tests/test_demo_personas.py::test_elke_mockpersona_is_compleet -q`
Expected: FAIL, daarna na terugzetten weer PASS.

- [ ] **Step 4: Commit**

```bash
git add services/host/tests/test_demo_personas.py
git commit -m "test(kvk): een mock-persona bestaat in alle lagen of nergens

De blokkade die het gebruikersonderzoek van augustus bijna sloopte was dat de
frontend persona's aanbood die de backend niet kende. Deze test dekt de
backendkant daarvan af: een profiel zonder eigenaar of zonder verbruiksdata valt
door de mand in plaats van pas tijdens een sessie."
```

---

### Task 3: Het onderzoeksvenster vastleggen als besluit

**Files:**
- Modify: `docs/decisions/PDR-010-sleutel-van-de-gebruiker.md` (nieuw addendum onderaan)
- Modify: `docs/deploy-zad.md` (de sleutel-alinea, nu regel 36-37)
- Modify: `services/host/.env.example` (`ALLOW_API_KEY_OVERRIDE`-blok)

**Interfaces:**
- Consumes: de besluiten uit de spec
- Produces: documentatie waarop een beheerder kan handelen

- [ ] **Step 1: Schrijf het addendum onderaan PDR-010**

```markdown
## Addendum (2026-08-10): tijdelijke serversleutel voor het gebruikersonderzoek

Voor het gebruikersonderzoek van **25 en 27 augustus 2026** wijkt de deployment
tijdelijk af van beslissing 1. De ondernemers die meedoen werken in hun eigen
browser op hun eigen machine; hun een sleutel laten invoeren zou betekenen dat
we die aan onderzoeksdeelnemers geven. Ze zouden hem zien, en de frontend bewaart
hem in `localStorage` — dus hij blijft na de sessie in hun browser achter, ook
nadat de schermopname is gewist. Dat is precies het risico dat dit PDR wilde
vermijden.

Daarom in dat venster: een **aparte Anthropic-sleutel met spend limit** op de
ZAD-component, en `ALLOW_API_KEY_OVERRIDE=false`, zodat de sleutel-headers
genegeerd worden en niemand iets hoeft in te voeren.

**Geaccepteerd restrisico:** `/chat` heeft geen authenticatie, dus wie de host
bereikt verbruikt deze sleutel. Draagbaar omdat de backend internal-only is en het
venster twee dagen beslaat. Het is nadrukkelijk niet de stand voor daarbuiten.

**Intrekken:** de sleutel wordt na 27 augustus 2026 ingetrokken en
`ALLOW_API_KEY_OVERRIDE` gaat terug naar `true`. Zolang dat niet gebeurd is, staat
er een gedeelde sleutel op een onauthenticeerde host.
```

- [ ] **Step 2: Werk `docs/deploy-zad.md` bij**

Vervang de regels die zeggen dat er geen `ANTHROPIC_API_KEY` / `VLAM_API_KEY` staat
door een tekst die beide standen beschrijft: de normale stand (geen sleutels,
`ALLOW_API_KEY_OVERRIDE=true`) en het onderzoeksvenster (aparte sleutel,
`ALLOW_API_KEY_OVERRIDE=false`, ingetrokken na 27 augustus 2026), met een verwijzing
naar het addendum in PDR-010.

- [ ] **Step 3: Werk `.env.example` bij**

Voeg onder het bestaande `ALLOW_API_KEY_OVERRIDE`-blok toe:

```
# Uitzondering: tijdens een begeleid gebruikersonderzoek staat deze op false én
# staat er wél een serversleutel, zodat deelnemers niets hoeven in te voeren.
# Zie het addendum van 2026-08-10 in docs/decisions/PDR-010-sleutel-van-de-gebruiker.md.
```

- [ ] **Step 4: Controleer dat de documentatie zichzelf niet tegenspreekt**

Run: `grep -rn "ALLOW_API_KEY_OVERRIDE" docs/ services/host/.env.example .github/workflows/`
Expected: elke vindplaats noemt dezelfde twee standen, of verwijst naar het addendum.
Deze repo had eerder vier documenten die elkaar tegenspraken over `ALLOWED_ORIGINS`;
dat mag hier niet opnieuw gebeuren.

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/PDR-010-sleutel-van-de-gebruiker.md docs/deploy-zad.md services/host/.env.example
git commit -m "docs: leg de tijdelijke serversleutel voor het onderzoek vast (PDR-010)

Voor 25 en 27 augustus staat er een aparte sleutel met spend limit op de
ZAD-component en gaat ALLOW_API_KEY_OVERRIDE op false, zodat deelnemers niets
hoeven in te voeren. Deelnemers een sleutel laten invoeren zou betekenen dat we
die aan hen geven, en de frontend bewaart hem in localStorage — dus hij blijft
na de sessie achter.

Het restrisico (geen authenticatie op /chat) en de intrekdatum staan er expliciet
bij. Zonder die datum is dit geen tijdelijke afwijking maar een stille
verslechtering."
```

---

## Zelfreview van dit plan

**Spec-dekking.** W2-backend is Task 1; de invariant die blokkade 2 en 3
veroorzaakte is Task 2; W0-documentatie is Task 3. Wat hier bewust *niet* in zit en
elders belegd is: de ZAD-configuratie zelf en de frontend (`header-overheid.njk`,
`personas.json`, de rolbeschrijving in het testscript) — die doet de repo-eigenaar.
W1, W3, W4 en W5 krijgen eigen plannen.

**Openstaand na dit plan.** De verificatie uit W0 — "toont de frontend nog *Vul uw
API-sleutel in* terwijl er een serversleutel staat?" — kan pas ná het mergen van
PR #45, omdat die PR precies deze foutmeldingen herschrijft. Dat hoort in het
W1-plan, niet hier.

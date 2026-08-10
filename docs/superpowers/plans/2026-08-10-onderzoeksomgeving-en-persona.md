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

## Ontwerpkeuze: de VOF blijft, en dat corrigeert de spec

De spec zei "`MOCK_EIGENAREN["62345681"]` krijgt Robin Vogel als natuurlijk
persoon". Dat is bij nader inzien fout, en de correctie is belangrijker dan de
wijziging zelf.

De Bloesem is bewust een **VOF**, mét comment: "geen rechtspersoonlijkheid, de
vennootschap zelf is de eigenaar". Dat is voor een VOF de correcte vorm van het KvK
Basisprofiel. Belangrijker: de **frontend modelleert Robin Vogel al als vennoot** —
`_data/personas.json[13]` zegt `rechtsvorm: "Vennootschap onder firma"` en
`functies: "Vennoot, Kweker"`. Beide lagen zijn het dus al eens.

Een natuurlijk persoon in het eigenaar-antwoord duwen zou de API-vorm breken
(PDR-007) én de frontend tegenspreken. **De mockdata blijft ongewijzigd.** Wat
overblijft is een verificatie in W4: het antwoord van de assistent mag niet
suggereren dat Robin géén band met het bedrijf heeft. "De onderneming is een VOF"
is correct; "de eigenaar is onbekend" zou verwarrend zijn voor iemand die net als
Robin Vogel is ingelogd.

**Leidend principe (vastgesteld 2026-08-10): de frontend is leidend.** De
respondent leest de bedrijfsgegevens op het scherm; wat de assistent zegt moet
daarop aansluiten, niet andersom. Waar de twee verschillen én het KvK Basisprofiel
een passend veld heeft, volgt de backend. Waar de frontend gegevens toont die niet
uit het Handelsregister komen (btw-nummer, IBAN, loonheffingennummer), blijft de
backend erbuiten — dat is Belastingdienst-data, geen KvK-data.

Twee velden vallen daaronder:

- **Voltijd personeel.** De frontend toont `werkzamePersonenFulltime: 5`; de
  backend kent alleen `totaalWerkzamePersonen: 7`. Die twee spreken elkaar niet
  tegen — het echte Basisprofiel heeft beide velden — maar zonder het voltijdveld
  antwoordt de assistent "7" op een scherm dat "5" toont. Het veld komt erbij; het
  totaal blijft 7.
- **Website.** De frontend toont `https://www.kwekerijdebloesem.nl`; het
  Basisprofiel heeft daar een `websites`-lijst voor.

---

### Task 1: Laat de backend de frontend volgen voor de onderzoekspersona

**Files:**
- Modify: `services/mcp/kvk/server.py` (`MOCK_PROFIELEN["62345681"]`)
- Test: `services/host/tests/test_demo_personas.py`

**Interfaces:**
- Consumes: het bestaande `_load(naam)`-helpertje boven in `test_demo_personas.py`,
  dat een MCP-server per bestandspad laadt (`services/mcp/<naam>/server.py`).
- Produces: geen code, alleen bewaking

De VOF blijft; die kwam al overeen. Twee velden die de frontend toont en de backend
niet kent komen erbij, en een test legt de hele koppeling vast zodat een latere
"verbetering" de twee lagen niet stilletjes uit elkaar trekt. De frontend staat in
een andere repo, dus de test noteert de waarden die daar gelden mét de bron erbij.

- [ ] **Step 1: Schrijf de falende test**

Voeg onderaan `services/host/tests/test_demo_personas.py` toe:

```python
# Waarden zoals MinBZK/poc-moza ze toont voor `?persona=bloemenkweker`
# (_data/personas.json, index 13), gecontroleerd op 2026-08-10. De frontend is
# leidend: de respondent leest deze op de pagina Bedrijfsgegevens, en de assistent
# hoort er niets anders over te zeggen.
BLOEMENKWEKER_FRONTEND = {
    "kvkNummer": "62345681",
    "handelsnaam": "Kwekerij De Bloesem",
    "rechtsvorm": "Vennootschap onder firma",
    "vestigingsnummer": "000062345681",
    "voltijdWerkzamePersonen": 5,
    "website": "https://www.kwekerijdebloesem.nl",
}


def test_bloemenkweker_komt_overeen_met_de_frontend():
    """De persona van het gebruikersonderzoek, over twee repo's heen.

    Robin Vogel is in de frontend vennoot van een VOF. Voor een VOF levert het KvK
    Basisprofiel terecht de vennootschap als eigenaar en géén natuurlijk persoon —
    dat is dus geen bug om te "repareren".
    """
    kvk = _load("kvk")
    profiel = kvk.MOCK_PROFIELEN[BLOEMENKWEKER_FRONTEND["kvkNummer"]]
    eigenaar = kvk.MOCK_EIGENAREN[BLOEMENKWEKER_FRONTEND["kvkNummer"]]

    assert profiel["naam"] == BLOEMENKWEKER_FRONTEND["handelsnaam"]
    assert profiel["rechtsvorm"] == BLOEMENKWEKER_FRONTEND["rechtsvorm"]
    assert eigenaar["rechtsvorm"] == BLOEMENKWEKER_FRONTEND["rechtsvorm"]
    assert (
        profiel["_embedded"]["hoofdvestiging"]["vestigingsnummer"]
        == BLOEMENKWEKER_FRONTEND["vestigingsnummer"]
    )
    # Een VOF heeft geen natuurlijk persoon als eigenaar; die vorm hoort te blijven.
    assert "rechtspersoon" in eigenaar
    assert "natuurlijkPersoon" not in eigenaar


def test_bloemenkweker_personeel_en_website_volgen_de_frontend():
    """Zonder het voltijdveld antwoordt de assistent "7" op een scherm dat "5" toont.

    Beide getallen zijn waar — het echte Basisprofiel kent totaal én voltijd — maar
    de respondent ziet alleen het voltijdgetal en zou het verschil als een fout
    lezen.
    """
    profiel = _load("kvk").MOCK_PROFIELEN["62345681"]
    assert profiel["totaalWerkzamePersonen"] == 7
    assert (
        profiel["voltijdWerkzamePersonen"]
        == BLOEMENKWEKER_FRONTEND["voltijdWerkzamePersonen"]
    )
    assert BLOEMENKWEKER_FRONTEND["website"] in profiel["websites"]


def test_bloemenkweker_is_indieningsplichtig():
    """De hele onderzoeksflow hangt hieraan: zakt dit onder de drempel, dan is er
    niets te rapporteren en valt het script uit elkaar."""
    netbeheerder = _load("netbeheerder")
    totaal = netbeheerder.MOCK_VERBRUIK["62345681"]["totaal"]
    assert totaal["jaarlijks_elektriciteitsverbruik_kwh"] > 50000
    assert totaal["jaarlijks_gasverbruik_m3"] > 25000
```

- [ ] **Step 2: Draai de tests en zie de tweede falen**

Run: `uv run pytest services/host/tests/test_demo_personas.py -q`
Expected: `test_bloemenkweker_komt_overeen_met_de_frontend` PASS (die legt de
bestaande, correcte stand vast); `test_bloemenkweker_personeel_en_website_volgen_de_frontend`
FAIL met `KeyError: 'voltijdWerkzamePersonen'`.

- [ ] **Step 3: Voeg de twee velden toe**

In `services/mcp/kvk/server.py`, in `MOCK_PROFIELEN["62345681"]`, direct onder
`"totaalWerkzamePersonen": 7,`:

```python
    # De frontend toont het voltijdaantal op de pagina Bedrijfsgegevens; zonder
    # dit veld antwoordt de assistent met het totaal en leest de ondernemer een
    # verschil dat er niet is. Beide velden staan zo ook in het echte Basisprofiel.
    "voltijdWerkzamePersonen": 5,
    "websites": ["https://www.kwekerijdebloesem.nl"],
```

- [ ] **Step 4: Draai de tests en zie ze slagen**

Run: `uv run pytest services/host/tests/test_demo_personas.py -q`
Expected: PASS

- [ ] **Step 5: Bewijs dat de eerste test tanden heeft**

Verander in `services/mcp/kvk/server.py` tijdelijk `MOCK_PROFIELEN["62345681"]["rechtsvorm"]`
naar `"Eenmanszaak"`, draai de test, zie hem falen, en zet het terug.

Run: `uv run pytest services/host/tests/test_demo_personas.py::test_bloemenkweker_komt_overeen_met_de_frontend -q`
Expected: FAIL, daarna na terugzetten weer PASS.

- [ ] **Step 6: Draai de volledige suite en de linter**

Run: `uv run pytest -q && uv run ruff check .`
Expected: alles groen.

- [ ] **Step 7: Commit**

```bash
git add services/mcp/kvk/server.py services/host/tests/test_demo_personas.py
git commit -m "fix(kvk): laat het profiel van De Bloesem de frontend volgen

Voor het gebruikersonderzoek van 25/27 augustus is de frontend leidend: de
respondent leest de bedrijfsgegevens op het scherm, en de assistent hoort daarop
aan te sluiten. Twee velden ontbraken. De pagina toont vijf voltijdmedewerkers
terwijl de mock alleen een totaal van zeven kende, dus de assistent noemde een
ander getal dan het scherm; beide velden bestaan in het echte Basisprofiel en
staan er nu allebei in. De website stond alleen in de frontend.

De rechtsvorm blijft VOF: de frontend modelleert Robin Vogel als vennoot, en voor
een VOF levert het Basisprofiel terecht de vennootschap als eigenaar in plaats van
een natuurlijk persoon. Een test houdt die koppeling nu vast, inclusief de
drempels — zakt het verbruik daaronder, dan is er niets te rapporteren en valt het
testscript uit elkaar."
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

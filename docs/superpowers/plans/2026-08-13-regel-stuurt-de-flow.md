# De regel stuurt de flow — implementatieplan

> **Voor agentische uitvoerders:** VERPLICHTE SUB-SKILL: gebruik
> `superpowers:subagent-driven-development` of `superpowers:executing-plans` om
> dit plan taak voor taak uit te voeren. Stappen gebruiken checkbox-syntax.

**Doel:** De regel declareert wat hij nodig heeft, de host routeert elk veld naar
zijn bron, en het model converseert zonder te orkestreren. Elke waarde op het
scherm is daarmee herleidbaar tot wie hem zei.

**Architectuur:** Een orkestratielus in de host roept de wet aan met wat bekend
is, leest `missing_parameters`, en haalt per veld op wat de routeringstabel
voorschrijft — tot hij toestemming nodig heeft of iets dat alleen de ondernemer
weet. Een feit is `{waarde, bron, soort}`; herkomst wordt afgeleid uit wie
geraadpleegd is, niet als metadata meegedragen.

**Tech stack:** Python 3.11+, FastAPI, MCP (stdio), pytest, ruff, uv, httpx.
Frontend: Eleventy, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-08-13-regel-stuurt-de-flow-design.md`

## Globale randvoorwaarden

- **Branch:** `feat/herkomst-zichtbaar` in `moza-poc-digitale-assistent`.
  Frontend: eigen branch in `/home/claude/projects/poc-moza`.
- **Nooit pushen.** Commits blijven lokaal in beide repo's.
- **Taal:** technische termen Engels, domeintermen Nederlands. Commentaar,
  docstrings en testnamen Nederlands.
- **Commits:** géén `Co-Authored-By`-trailer (`CLAUDE.md` loopt daarin achter op
  de praktijk — nul trailers op `main`).
- **Foutmeldingen** komen uit `services/host/errors.py`.
- **Suite:** `MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q`
- **Lint:** `uv run ruff check .` schoon.
- **Nieuwe host-modules** moeten in `pyproject.toml` bij `known-first-party`,
  anders sorteert ruff de import verkeerd.
- **De engine is live** op `https://ui.lac.projects.digilab.network/mcp/rpc`.
  Gedrag nagemeten 2026-08-13: lege parameters → mist `KVK_NUMMER` en
  `IS_WOONFUNCTIE`; die aangeleverd → mist het verbruik; dat aangeleverd →
  uitkomst.
- **Volgorde is bewust.** Taak 1-3 wijzigen geen gedrag; taak 4 zet de lus aan.
  Loopt de tijd op, dan is stoppen ná taak 3 een coherente tussenstand.

---

### Taak 1: De routeringstabel

Eén plek waar staat welk veld uit welke bron komt. Dit is ook de eenheid waar de
latere uitbreiding naar een tweede wet in landt.

**Files:**
- Create: `services/host/regelrouting.py`
- Test: `services/host/tests/test_regelrouting.py`
- Modify: `pyproject.toml` (`known-first-party`)

**Interfaces:**
- Produces: `HERKOMST: dict[str, Veld]`, `Veld(bron, soort, tool, toestemming)`,
  `route(veldnaam) -> Veld | None`

- [ ] **Stap 1: Schrijf de falende test**

`services/host/tests/test_regelrouting.py`:

```python
"""Welk veld uit welke bron komt, op één plek.

Vraagt de wet een veld dat hier niet staat, dan stopt de orkestratielus. Dat is
opzet: raden waar een gegeven vandaan komt is precies wat deze hele branch
onmogelijk moet maken.
"""

import pytest
from regelrouting import HERKOMST, route


def test_elk_veld_van_de_informatieplicht_is_gerouteerd():
    """De wet vraagt deze vier; ontbreekt er één, dan loopt de flow vast."""
    for veld in (
        "KVK_NUMMER",
        "IS_WOONFUNCTIE",
        "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH",
        "JAARLIJKS_GASVERBRUIK_M3",
    ):
        assert route(veld) is not None, f"{veld} heeft geen bron"


def test_verbruik_vraagt_toestemming_bedrijfsgegevens_niet():
    """PDR-008: geen bron vóór akkoord. Alleen het verbruik valt daaronder."""
    assert route("JAARLIJKS_GASVERBRUIK_M3").toestemming is True
    assert route("JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH").toestemming is True
    assert route("IS_WOONFUNCTIE").toestemming is False
    assert route("KVK_NUMMER").toestemming is False


def test_opgaven_van_de_ondernemer_hebben_geen_tool():
    """Die komen uit het formulier, niet uit een bron die we kunnen aanroepen."""
    veld = route("HEEFT_KOELINSTALLATIE")
    assert veld.tool is None
    assert veld.soort == "opgave"


def test_onbekend_veld_geeft_none():
    assert route("OMZET_2025") is None


@pytest.mark.parametrize("naam,veld", sorted(HERKOMST.items()))
def test_elk_veld_heeft_een_bron_en_een_soort(naam, veld):
    """Een feit zonder bron is in dit ontwerp geen feit."""
    assert veld.bron, naam
    assert veld.soort in {"identiteit", "registratie", "attestatie", "opgave"}, naam
```

- [ ] **Stap 2: Draai en zie hem falen**

```bash
uv run pytest services/host/tests/test_regelrouting.py -v
```

Verwacht: `ModuleNotFoundError: No module named 'regelrouting'`.

- [ ] **Stap 3: Schrijf `services/host/regelrouting.py`**

```python
"""Welk veld van de regel uit welke bron komt.

De engine declareert wat hij mist; deze tabel zegt wie dat levert. Herkomst
wordt daardoor niet als metadata meegedragen maar afgeleid uit wie geraadpleegd
is - dat kan niet uit de pas lopen met de waarde.

Staat een veld hier niet, dan stopt de orkestratielus en meldt dat. Raden waar
een gegeven vandaan komt is precies wat dit ontwerp onmogelijk maakt.

Nu één wet. De tabel staat als aparte eenheid zodat een tweede wet hier landt en
niet door de host heen verspreid raakt.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Veld:
    """Waar één parameter van de regel vandaan komt.

    `tool` is None als geen enkele bron het kan leveren: dan weet alleen de
    ondernemer het en hoort het uit het formulier te komen.
    """

    bron: str
    soort: str  # identiteit | registratie | attestatie | opgave
    tool: str | None
    toestemming: bool


HERKOMST: dict[str, Veld] = {
    "KVK_NUMMER": Veld("sessie", "identiteit", None, False),
    "IS_WOONFUNCTIE": Veld(
        "KvK Handelsregister", "registratie", "kvk__mijn_bedrijf", False
    ),
    "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": Veld(
        "Business Wallet", "attestatie", "netbeheerder__verbruik", True
    ),
    "JAARLIJKS_GASVERBRUIK_M3": Veld(
        "Business Wallet", "attestatie", "netbeheerder__verbruik", True
    ),
    "HEEFT_KOELINSTALLATIE": Veld("de ondernemer", "opgave", None, False),
    "HEEFT_AFZUIGINSTALLATIE": Veld("de ondernemer", "opgave", None, False),
}


def route(veldnaam: str) -> Veld | None:
    """De bron van één veld, of None als we hem niet kennen."""
    return HERKOMST.get(veldnaam)
```

- [ ] **Stap 4: Draai en zie hem slagen**

```bash
uv run pytest services/host/tests/test_regelrouting.py -v
```

- [ ] **Stap 5: `known-first-party`**

Voeg `"regelrouting"` toe aan de lijst in `pyproject.toml`, naast `feiten` en
`slots`.

- [ ] **Stap 6: Suite, lint, commit**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
git add services/host/regelrouting.py services/host/tests/test_regelrouting.py pyproject.toml
git commit -m "feat(host): routeringstabel van regelveld naar bron

De engine declareert wat hij mist; deze tabel zegt wie dat levert. Daarmee wordt
herkomst afgeleid uit wie geraadpleegd is in plaats van als metadata
meegedragen - dat laatste kan uit de pas lopen met de waarde, en zo verdween de
provenance de vorige keer.

Staat een veld er niet in, dan stopt de lus. Raden waar een gegeven vandaan komt
is wat dit ontwerp onmogelijk moet maken."
```

---

### Taak 2: Een feit krijgt een bron en een soort

`feiten.py` levert nu naam→waarde. Dat wordt naam→`{waarde, bron, soort}`.

**Files:**
- Modify: `services/host/feiten.py`, `services/host/slots.py`
- Test: `services/host/tests/test_feitenkaart.py`, `test_slots.py`

**Interfaces:**
- Consumes: `regelrouting.Veld`
- Produces: `feiten_uit_tool()` geeft `dict[str, dict]` met sleutels
  `waarde`, `bron`, `soort`; `vul_slots()` leest `waarde`

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_feitenkaart.py`:

```python
def test_een_feit_draagt_zijn_bron_en_soort(kvk_resultaat):
    """Herkomst hoort bij de waarde, niet ernaast.

    Een tweede dict die je erbij moet houden is precies de constructie waarlangs
    de provenance de vorige keer verdween.
    """
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", kvk_resultaat)
    naam = feiten["BEDRIJFSNAAM"]
    assert naam["waarde"] == "Kwekerij De Bloesem"
    assert naam["bron"] == "KvK Handelsregister"
    assert naam["soort"] == "registratie"


def test_verbruik_draagt_de_business_wallet_als_bron(netbeheerder_resultaat):
    feiten = feiten_uit_tool("netbeheerder__verbruik", netbeheerder_resultaat)
    assert feiten["ELEKTRICITEIT_KWH"]["bron"] == "Business Wallet"
    assert feiten["ELEKTRICITEIT_KWH"]["soort"] == "attestatie"
```

Gebruik de bestaande fixtures die de payload uit de échte MCP-servers bouwen;
schrijf geen envelope met de hand. Dat is de fout die eerder een regressie
opleverde die de suite niet zag.

In `services/host/tests/test_slots.py`:

```python
def test_vul_slots_leest_de_waarde_uit_een_feit():
    tekst, ontbrekend = vul_slots(
        "Uw bedrijf {{BEDRIJFSNAAM}}.",
        {"BEDRIJFSNAAM": {"waarde": "Kwekerij De Bloesem",
                          "bron": "KvK Handelsregister",
                          "soort": "registratie"}},
    )
    assert tekst == "Uw bedrijf Kwekerij De Bloesem."
    assert ontbrekend == []
```

- [ ] **Stap 2: Draai en zie ze falen**

```bash
uv run pytest services/host/tests/test_feitenkaart.py services/host/tests/test_slots.py -v
```

- [ ] **Stap 3: Pas `feiten.py` aan**

Geef elke oogster de bron en soort mee die bij zijn tool horen. Bijvoorbeeld:

```python
def _met_herkomst(waarden: dict, bron: str, soort: str) -> dict:
    """Verpak platte waarden tot feiten met hun herkomst.

    None-waarden vallen weg: een feit zonder waarde is geen feit, en een lege
    plek is eerlijker dan een verzonnen invulling.
    """
    return {
        naam: {"waarde": waarde, "bron": bron, "soort": soort}
        for naam, waarde in waarden.items()
        if waarde is not None
    }
```

Let op de bestaande bug die in `NEXT_STEPS.md` staat: `_OORDELEN` filtert `None`
niet weg terwijl `_UITKOMST_VELDEN` dat twee regels lager wél doet. Deze
verpakking lost dat meteen op — controleer dat en noem het in je verslag.

Bronnen per oogster: `kvk__mijn_bedrijf` → "KvK Handelsregister"/"registratie";
`netbeheerder__verbruik` → "Business Wallet"/"attestatie";
`regelrecht__execute_law` → "RegelRecht"/"wetsconstante" voor `drempelwaarden`,
en voor `gebruikte_waarden` de herkomst uit `regelrouting.route()` als die het
veld kent, anders "RegelRecht"; `rvo__indienen` → "RVO"/"registratie".

Dat onderscheid bij `gebruikte_waarden` is de kern: de engine echoot terug wat
wij hem gaven, en een verbruikscijfer dat via de engine terugkomt hoort de
Business Wallet als bron te houden, niet RegelRecht.

- [ ] **Stap 4: Pas `slots.py` aan**

`vul_slots` leest `feiten[naam]["waarde"]`. Houd `_weergave` ongewijzigd — die
krijgt de waarde, niet het feit.

- [ ] **Stap 5: Werk de bestaande consumenten bij**

`grep -rn "feiten\[" services/host/` en `grep -rn "self.feiten" services/host/`
wijzen de plekken aan. `test_feitenkaart_dispatch.py` assert op
`host.feiten[conv_key]["VESTIGINGSADRES"]` — dat wordt `[...]["waarde"]`.

- [ ] **Stap 6: Suite, lint, commit**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
git add -A
git commit -m "feat(host): een feit draagt zijn bron en soort

Herkomst hoort bij de waarde, niet in een tweede dict ernaast - die kan uit de
pas lopen, en zo verdween de provenance uit de MCP-envelope de vorige keer.

Soort onderscheidt een wetsconstante van een registratie, een attestatie en een
opgave van de ondernemer. Zonder dat verschil lijkt 'koelinstallatie: ja' straks
een uitspraak van RegelRecht.

Een verbruikscijfer dat via de engine terugkomt houdt de Business Wallet als
bron: gebruikte_waarden echoot wat wij meegaven, dat maakt de engine nog niet de
bron ervan."
```

---

### Taak 3: De orkestratielus, nog niet aangesloten

Bouw de lus als losse, testbare eenheid. Aansluiten gebeurt in taak 4.

**Files:**
- Create: `services/host/regelloop.py`
- Test: `services/host/tests/test_regelloop.py`

**Interfaces:**
- Consumes: `regelrouting.route()`, een `call_tool(naam, args) -> str`-callable
- Produces: `async volg_regel(law, service, feiten, call_tool, toestemming) -> Uitkomst`
  met `Uitkomst(klaar, resultaat, wacht_op, reden)`

- [ ] **Stap 1: Schrijf de falende test**

`services/host/tests/test_regelloop.py`:

```python
"""De regel stuurt, de host haalt op.

De engine declareert laag voor laag wat hij mist. De lus draait door zolang hij
zelf verder kan en stopt waar toestemming nodig is of waar alleen de ondernemer
het antwoord heeft.
"""

import json

import pytest
from regelloop import volg_regel


def _engine(stappen):
    """Een nep-engine die per aanroep de volgende stap teruggeeft."""
    beurten = iter(stappen)

    async def call_tool(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": next(beurten)})
        if naam == "kvk__mijn_bedrijf":
            return json.dumps({"data": {"is_woonfunctie": False}})
        raise AssertionError(f"onverwachte tool: {naam}")

    return call_tool


@pytest.mark.asyncio
async def test_lus_haalt_op_wat_hij_zelf_kan():
    """Woonfunctie komt uit de KvK; daar is geen toestemming voor nodig."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"voldoet_aan_voorwaarden": True, "uitkomsten": {"heeft_informatieplicht": True}},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
    )
    assert uit.klaar is True
    assert uit.resultaat["uitkomsten"]["heeft_informatieplicht"] is True


@pytest.mark.asyncio
async def test_lus_stopt_bij_een_bron_die_toestemming_vraagt():
    """PDR-008: geen bron vóór akkoord. De lus raadpleegt de wallet niet."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "JAARLIJKS_GASVERBRUIK_M3"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "toestemming"


@pytest.mark.asyncio
async def test_lus_stopt_bij_iets_dat_alleen_de_ondernemer_weet():
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "HEEFT_KOELINSTALLATIE"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/maatregelen",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "opgave"


@pytest.mark.asyncio
async def test_onbekend_veld_stopt_de_lus_in_plaats_van_te_raden():
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "OMZET_2025"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "onbekend"
    assert "OMZET_2025" in uit.reden


@pytest.mark.asyncio
async def test_lus_loopt_niet_eindeloos_als_een_bron_niets_oplevert():
    """Een bron die het gevraagde veld niet levert mag geen oneindige lus geven."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=lambda n, a: _leeg_kvk(call_tool, n, a),
        toestemming=True,
    )
    assert uit.klaar is False
```

Kijk hoe de bestaande async-tests in deze suite zijn opgezet (`pytest-asyncio`
staat in `pyproject.toml`, mode is `auto`) en volg dat patroon; pas de laatste
test aan tot hij een KvK-tool gebruikt die de woonfunctie niet teruggeeft.

- [ ] **Stap 2: Draai en zie ze falen**

- [ ] **Stap 3: Schrijf `services/host/regelloop.py`**

Ontwerp:

```python
@dataclass(frozen=True)
class Uitkomst:
    """Waar de lus is gestopt en waarom.

    `wacht_op` is None als de regel klaar is; anders "toestemming", "opgave" of
    "onbekend". De aanroeper vertaalt dat naar wat het model moet doen.
    """

    klaar: bool
    resultaat: dict | None
    wacht_op: str | None
    reden: str
```

De lus:

1. roep `regelrecht__execute_law` aan met de parameters die uit `feiten` af te
   leiden zijn (zie hieronder)
2. `voldoet_aan_voorwaarden` waar → `Uitkomst(klaar=True, resultaat=…)`
3. lees `ontbrekende_gegevens`; leeg maar niet voldaan → stop met `"onbekend"`
4. eerste ontbrekende veld → `route()`:
   - `None` → stop met `"onbekend"`
   - `toestemming` en niet gegeven → stop met `"toestemming"`
   - `tool is None` → stop met `"opgave"`
   - anders: roep de tool aan, oogst met `feiten_uit_tool`, voeg toe aan
     `feiten`, terug naar 1
5. maximaal vijf rondes; daarna stoppen met een reden

Die bovengrens is geen sierlijkheid: levert een bron het gevraagde veld niet,
dan blijft de wet erom vragen en draait de lus rond. Vijf is ruim boven de drie
lagen die deze wet kent.

Voor het afleiden van de parameters uit `feiten`: de regel vraagt namen als
`JAARLIJKS_GASVERBRUIK_M3`, de feitenkaart kent `GAS_M3`. Leg die vertaling in
`regelrouting.py` vast als een tweede veld op `Veld` (bijvoorbeeld
`feitnaam`), zodat beide kanten op één plek staan.

- [ ] **Stap 4: Draai en zie ze slagen**

- [ ] **Stap 5: Suite, lint, commit**

```bash
git commit -m "feat(host): orkestratielus die de regel volgt

De engine declareert laag voor laag wat hij mist; de lus haalt op wat hij zelf
kan en stopt waar toestemming nodig is of waar alleen de ondernemer het weet.

Nog niet aangesloten: dit is de eenheid, taak 4 zet hem aan. Een bovengrens van
vijf rondes vangt de bron die het gevraagde veld niet levert - zonder die grens
blijft de wet erom vragen en draait de lus rond."
```

---

### Taak 4: De lus aansluiten

Hier verandert het gedrag.

**Files:**
- Modify: `services/host/vlam_host.py`, `services/host/prompts/composer.py`
- Create: `services/host/prompts/blocks/shared/regel_status.md`
- Test: `services/host/tests/test_regelloop_integratie.py`

- [ ] **Stap 1: Schrijf de falende test**

Een test via de publieke ingang (`chat_stream`) die bewijst dat bij de eerste
vraag van de respondent de wet is aangeroepen vóór enige andere bron, en dat de
KvK-tool wél en de netbeheerder níét is geraadpleegd zolang er geen toestemming
is. Volg het mock-patroon van `test_feitenkaart_dispatch.py`.

- [ ] **Stap 2: Draai en zie hem falen**

- [ ] **Stap 3: Roep de lus aan vóór het model**

In `chat()` en `chat_stream()`, na `feiten = self.feiten.setdefault(conv_key, {})`
en vóór de LLM-aanroep: draai `volg_regel` met
`call_tool=self.registry.call_tool` en de toestemmingsstand van deze sessie.

Toestemming afleiden: er is geen expliciete vlag. Neem als stand dat toestemming
gegeven is zodra de feitenkaart een attestatie-feit bevat, of zodra het gesprek
al een `netbeheerder__verbruik`-resultaat heeft gezien. Leg in een comment vast
dat dit een afleiding is en geen registratie van instemming, en zet het als open
punt in `NEXT_STEPS.md`: een PoC mag dat zo doen, een echt systeem niet.

- [ ] **Stap 4: Zet de openstaande behoefte in de prompt**

`regel_status.md` als samengesteld blok, naar het model van
`_compose_bronnen_status`. Inhoud hangt af van `wacht_op`:

- `toestemming` → welke bron, waarvoor, en dat er om akkoord gevraagd moet worden
- `opgave` → welke vragen, met de vraagteksten die de engine meegaf
- `onbekend` → dat de assistent het niet kan bepalen en dat eerlijk moet melden
- klaar → de uitkomst, met de mededeling dat die uit RegelRecht komt

- [ ] **Stap 5: Haal de orkestratie uit `tool_usage.md`**

De regels die het model vertellen welke tool wanneer met welke parameters, en in
welke volgorde. Laat staan wat over presentatie en toon gaat. Wees precies: haal
weg wat de host nu doet, niet meer.

- [ ] **Stap 6: Suite, lint, commit**

---

### Taak 5: De EML-fallback maakt zich kenbaar

**Files:**
- Modify: `services/mcp/regelrecht/server.py`,
  `services/host/prompts/blocks/shared/tool_usage.md`
- Test: bestaande regelrecht-tests

- [ ] **Stap 1: Schrijf de falende test**

Een test die bewijst dat `_eml_fallback` een veld draagt waaruit blijkt dat dit
een lokale kopie is, en dat het engine-pad dat veld niet heeft.

- [ ] **Stap 2: Draai, zie falen, implementeer**

Voeg aan de fallback-respons een veld toe zoals
`"herkomst": "lokale kopie van de regel; RegelRecht was niet bereikbaar"`.
De prompt draagt het model op dat te melden zodra het aanwezig is.

Waarom labelen en niet verwijderen: een kapotte demo tijdens een sessie is
erger dan een gelabelde kopie. Maar een respondent hoort te weten wanneer hij
naar onze weergave van de regel kijkt in plaats van naar de regel — dat is
"de juridische geldigheid blijft bij de oorspronkelijke wetgeving".

- [ ] **Stap 3: Suite, lint, commit**

---

### Taak 6: `opgaven` op het contract

**Files:**
- Modify: `services/host/api.py`, `services/host/vlam_host.py`
- Test: `services/host/tests/test_opgaven.py`

- [ ] **Stap 1: Schrijf de falende test**

Een test die `POST /chat/stream` met `opgaven` stuurt en bewijst dat die als
feiten met bron "de ondernemer" en soort "opgave" in de kaart landen, vóórdat de
lus draait.

Plus: een test dat een opgave die níét in de routeringstabel staat wordt
geweigerd. Een frontend mag geen willekeurige feiten de kaart in schrijven.

- [ ] **Stap 2: Draai, zie falen, implementeer**

`opgaven: dict[str, object] | None = None` op `ChatRequest`. In de host: filter
op wat `regelrouting.route()` kent met `soort == "opgave"`, verpak met bron
"de ondernemer", en zet ze in de feitenkaart vóór de lus.

- [ ] **Stap 3: Suite, lint, commit**

---

### Taak 7: De frontend stuurt opgaven en haalt de drempels op

**Repo:** `/home/claude/projects/poc-moza` — eigen branch, **niet pushen**.

**Files:**
- Modify: `assets/javascript/digitale-assistent.js`

- [ ] **Stap 1: Maak een branch**

```bash
cd /home/claude/projects/poc-moza
git checkout -b feat/opgaven-en-drempels-uit-de-bron
```

- [ ] **Stap 2: Stuur de formulierantwoorden als data**

Rond regel 703 staat de submit-handler die de antwoorden platslaat:

```js
var bericht = "Mijn antwoorden: " + delen.join("; ") + ".";
```

De radioknoppen dragen hun veldnaam al (`naam` in de veld-spec). Bouw daarnaast
een `opgaven`-object en stuur dat mee in de fetch naar `/chat/stream`. Houd het
chatbericht: de respondent hoort in het gesprek terug te zien wat hij antwoordde.

Alleen velden waarvan de naam eruitziet als een regelparameter
(`/^[A-Z][A-Z0-9_]*$/`) gaan mee. De backend filtert nog eens op zijn eigen
tabel; dit voorkomt alleen dat we onzin sturen.

Waarden: "Uitgevoerd"/"Ja" → `true`, "Niet uitgevoerd"/"Nee" → `false`. Kijk in
`vraagSpec` welke optie-labels er precies gebruikt worden en leid de vertaling
daaruit af in plaats van hem te raden.

- [ ] **Stap 3: Haal de drempels op in plaats van ze te hardcoderen**

```js
var KWH_GRENS = 50000;
var GAS_GRENS = 25000;
```

Vervang door een ophaal uit `GET /regelrecht/drempels` — het endpoint dat daar
al voor bestaat en nog nooit is aangeroepen. Het geeft
`{"drempelwaarden": {"DREMPEL_ELEKTRICITEIT_KWH": 50000, "DREMPEL_GAS_M3": 25000, ...}}`.

**Faalt de ophaal, toon dan geen grensvergelijking.** `walletCijfer` krijgt de
grens nu als argument; laat dat deel weg als de waarde onbekend is. Liever geen
oordeel dan een oordeel op eigen gezag — de frontend hoort geen wettelijke grens
uit eigen code te tonen.

- [ ] **Stap 4: Controleer met de draaiende host**

De host draait op poort 8000. Controleer met `curl` dat het endpoint antwoordt,
en dat de opgaven aankomen (kijk in de hostlog naar de feitenkaart).

- [ ] **Stap 5: Commit in de frontend-repo, niet pushen**

```bash
git commit -m "feat(assistent): stuur formulierantwoorden als data en haal drempels op

De radioknoppen droegen hun veldnaam al, maar werden platgeslagen tot een zin
die het model weer moest interpreteren. Nu gaan ze als opgaven mee, zodat een
antwoord toerekenbaar is aan wie hem gaf.

De drempelwaarden kwamen uit twee constanten in dit bestand. GET
/regelrecht/drempels bestaat daar al voor en werd nooit aangeroepen; het scherm
vertelde de ondernemer dus 'boven de grens van 50.000' op eigen gezag. Faalt de
ophaal, dan tonen we de waarden zonder grensvergelijking."
```

---

### Taak 8: Meten

- [ ] **Stap 1: Breid `onderzoeksflow.py` uit**

Nieuwe controles:
- elk feit in de kaart heeft een bron en een soort
- de wet is aangeroepen vóór enige andere bron
- geen veld aan de wet meegegeven dat niet uit de routeringstabel komt

De eerste twee zijn alleen te zien in de hostlog of via een debug-endpoint; kies
zelf en verantwoord het. Kan een controle niet, zeg dat dan in het meetdocument
in plaats van hem weg te laten.

- [ ] **Stap 2: Herstart de host en draai vijf runs**

```bash
uv run python services/host/scripts/onderzoeksflow.py --mode vlam --kvk 62345681 --runs 5 --json /tmp/meting-regelloop.json
```

- [ ] **Stap 3: Vergelijk met de eindmeting**

`docs/superpowers/plans/eindmeting-2026-08-13.md` is het ijkpunt. Elke bestaande
controle houdt zijn score; zakken is een regressie.

Schrijf `docs/superpowers/plans/meting-regelloop-2026-08-13.md` met beide tabellen
naast elkaar en de commit-hash.

- [ ] **Stap 4: Commit**

---

## Zelfcontrole bij oplevering

- [ ] Elk veld dat de engine kan vragen staat in `HERKOMST`, en omgekeerd routeert
      `HERKOMST` geen velden die de wet niet kent.
- [ ] `/chat` en `/chat/stream` gedragen zich gelijk.
- [ ] Geen bron vóór toestemming — de controle stond op 5/5.
- [ ] Suite groen inclusief de pariteitstest; ruff schoon.
- [ ] Beide repo's gecommit, **geen van beide gepusht**.
- [ ] `NEXT_STEPS.md` bijgewerkt (gitignored, dus lokaal).

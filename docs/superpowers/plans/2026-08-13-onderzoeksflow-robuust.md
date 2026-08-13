# Feiten uit de bron in de onderzoeksflow — implementatieplan

> **Voor agentische uitvoerders:** VERPLICHTE SUB-SKILL: gebruik
> `superpowers:subagent-driven-development` (aanbevolen) of
> `superpowers:executing-plans` om dit plan taak voor taak uit te voeren. Stappen
> gebruiken checkbox-syntax (`- [ ]`) voor het bijhouden.

**Doel:** Het model schrijft geen feiten meer op maar plaatshouders; de host vult
die in uit de bron, zodat een respondent tijdens het gebruikersonderzoek van 25
en 27 augustus 2026 nooit een verzonnen gegeven over zijn eigen bedrijf leest.

**Architectuur:** De RegelRecht-MCP-server geeft voortaan door wat de engine
werkelijk teruggaf (`gebruikte_waarden`, `drempelwaarden`). De host oogst uit elk
tool-resultaat een feitenkaart per sessie. Het model schrijft `{{SLOT}}` in
plaats van waarden; de host substitueert vlak vóór het `answer`-event en weigert
elk onopgelost slot. De maatregelenlijst gaat als gestructureerd veld mee op dat
event, waar de frontend hem al kan lezen.

**Tech stack:** Python 3.11+, FastAPI, MCP (stdio), pytest, ruff, uv, httpx.

**Spec:** `docs/superpowers/specs/2026-08-13-onderzoeksflow-robuust-design.md`

## Globale randvoorwaarden

- **Branch:** `feat/onderzoeksflow-verificatie`. Nooit direct naar `main`.
- **Taal:** technische termen Engels, domeintermen Nederlands. Commentaar,
  docstrings en testnamen in het Nederlands. Zie `CLAUDE.md`.
- **Commits:** géén `Co-Authored-By`-trailer in dit project.
- **Commentaar legt het *waarom* vast**, niet het *wat*. Geen verwijzingen naar
  PR-nummers of `NEXT_STEPS.md` in comments.
- **Foutmeldingen komen uit `errors.py`**, niet uit een f-string ter plekke.
- **Slot-syntax:** `{{SLOT_NAAM}}`, hoofdletters met liggend streepje-loze
  underscores. Nooit `[SLOT]` (markdown-links) en nooit `___` (dat betekent in
  `format.md` al "hier vult de gebruiker iets in").
- **Persona onder test:** Kwekerij De Bloesem, KvK `62345681`.
- **Modus onder test:** `vlam`. De `claude`-backend is onbruikbaar tot de
  Anthropic-sleutel krediet heeft; laat `claude`-runs weg in plaats van ze rood
  te laten staan.
- **Na elke taak:** `uv run pytest` groen en `uv run ruff check .` schoon.
- **Pariteitstest:** draaien met
  `MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json`, anders
  slaat hij over.
- **`onderzoeksflow.py` kost echte LLM-calls.** Het is geen pytest-test en hoort
  niet in de suite.

---

### Taak 1: Persona zonder onderzoeksplicht

De Bloesem verbruikt 198.000 m³ gas en gaat daarmee over de onderzoeksdrempel van
170.000. Dat geeft een zwaardere verplichting waarvoor de assistent geen
handelingsperspectief biedt, en dat maakt "dit helpt me niet" onmogelijk te
duiden. Dit moet vóór de nulmeting, anders meten we straks een ander scenario dan
we repareren.

**Files:**
- Modify: `services/mcp/netbeheerder/server.py` (mockverbruik `62345681`)
- Modify: `services/host/.env.example` (persona-tabel)
- Test: `services/host/tests/test_demo_personas.py`

**Interfaces:**
- Consumes: niets
- Produces: `62345681` heeft gas < 170.000 en > 25.000

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_demo_personas.py`:

```python
def test_de_bloesem_heeft_geen_onderzoeksplicht(netbeheerder):
    """De onderzoeksplicht heeft een ander handelingsperspectief dan rapporteren.

    De assistent biedt dat niet. Raakt de persona die drempel toch, dan is een
    'dit helpt me niet' van de respondent niet meer te scheiden van een gat in
    de implementatie - en dat is precies de uitkomst die het onderzoek moet
    kunnen meten.
    """
    DREMPEL_ONDERZOEK_GAS_M3 = 170_000
    DREMPEL_ONDERZOEK_ELEKTRICITEIT_KWH = 10_000_000
    DREMPEL_GAS_M3 = 25_000

    totaal = netbeheerder._verbruik_voor("62345681")["totaal"]
    gas = totaal["jaarlijks_gasverbruik_m3"]
    elektriciteit = totaal["jaarlijks_elektriciteitsverbruik_kwh"]

    assert gas < DREMPEL_ONDERZOEK_GAS_M3, f"{gas} m3 geeft een onderzoeksplicht"
    assert elektriciteit < DREMPEL_ONDERZOEK_ELEKTRICITEIT_KWH
    # ... maar de informatieplicht moet blijven gelden, anders valt het
    # testscript uit elkaar: er is dan niets te rapporteren.
    assert gas > DREMPEL_GAS_M3
```

Kijk hoe de bestaande tests in dit bestand aan de netbeheerder-module komen en
volg dat patroon (fixture of `importlib`-laadhulp). Verzin geen nieuwe manier.

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_demo_personas.py::test_de_bloesem_heeft_geen_onderzoeksplicht -v
```

Verwacht: FAIL met `198000 m3 geeft een onderzoeksplicht`.

- [ ] **Stap 3: Verlaag het gasverbruik**

In `services/mcp/netbeheerder/server.py`, bij het mockverbruik van `62345681`:
zet `jaarlijks_gasverbruik_m3` op `140000`, zowel in de aansluiting als in
`totaal`. Laat het elektriciteitsverbruik op `420000` staan.

Voeg er een comment bij dat vastlegt waaróm dit getal zo is:

```python
# 140.000 m3 is gekozen, niet gegroeid: boven de gasdrempel van 25.000 (dus de
# informatieplicht geldt) en onder de onderzoeksdrempel van 170.000. Die tweede
# grens geeft een verplichting waarvoor de assistent geen handelingsperspectief
# heeft; een respondent kan dat niet onderscheiden van een gat in het product.
```

- [ ] **Stap 4: Draai de test en zie hem slagen**

```bash
uv run pytest services/host/tests/test_demo_personas.py -v
```

- [ ] **Stap 5: Werk de persona-tabel bij**

In `services/host/.env.example` staat `62345681 = Kwekerij De Bloesem (persona
bloemenkweker) — plicht via gas`. Dat klopt niet: met 420.000 kWh zit De Bloesem
ook boven de elektriciteitsdrempel van 50.000. Maak ervan: `plicht via gas en
elektriciteit`.

- [ ] **Stap 6: Draai de volledige suite**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
```

Verwacht: alles groen. Let op de bestaande drempeltest in dit bestand — die
bestaat omdat het testscript uit elkaar valt als het verbruik onder de drempel
zakt. 140.000 blijft boven 25.000, dus hij hoort te slagen. Faalt hij, stop en
meld het; verlaag de drempel in die test niet.

- [ ] **Stap 7: Commit**

```bash
git add services/mcp/netbeheerder/server.py services/host/.env.example services/host/tests/test_demo_personas.py
git commit -m "fix(persona): De Bloesem onder de onderzoeksdrempel

Met 198.000 m3 gas raakte de persona de onderzoeksdrempel van 170.000 en kreeg
hij naast de informatieplicht ook een onderzoeksplicht. Daar biedt de assistent
geen handelingsperspectief voor, en dan is een 'dit helpt me niet' van de
respondent niet meer te scheiden van een gat in de implementatie.

140.000 m3 houdt de informatieplicht in stand (boven 25.000) en blijft onder de
onderzoeksdrempel. Raakt geen frontend-pariteit: personas.json bevat geen
verbruiksgegevens."
```

---

### Taak 2: Herhaald draaien en de nulmeting

Alle vier de besmettende bevindingen zijn intermitterend (1 tot 2 op 3). Eén
doorloop zegt daarover niets. Zonder nulmeting is elke verbetering straks een
bewering in plaats van een meting.

**Files:**
- Modify: `services/host/scripts/onderzoeksflow.py`
- Create: `docs/superpowers/plans/nulmeting-2026-08-13.md`

**Interfaces:**
- Consumes: `Loop`, `Uitkomst`, `draai()` uit `onderzoeksflow.py`
- Produces: `--runs N`, `--json PAD`; JSON-vorm
  `{"runs": [{"run": 1, "geslaagd": 22, "totaal": 25, "mislukt": ["stap4: …"]}], "samenvatting": {"controle": "4/5"}}`

- [ ] **Stap 1: Schrijf de falende test**

De aggregatie is pure functie-logica en hoort wél in de suite, ook al draait het
script zelf er niet in. In `services/host/tests/test_onderzoeksflow_aggregatie.py`:

```python
"""De aggregatie over meerdere runs, los van de LLM-calls.

Het script zelf kost echte LLM-beurten en hoort niet in de suite. De optelsom
eroverheen is gewone code en moet wel gedekt zijn: die bepaalt of we straks
"vijf van de vijf" of "vier van de vijf" concluderen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from onderzoeksflow import Uitkomst, aggregeer


def test_aggregeer_telt_per_controle_over_runs():
    runs = [
        [Uitkomst("stap4", True, "formulier"), Uitkomst("stap6", True, "indienen")],
        [Uitkomst("stap4", False, "formulier"), Uitkomst("stap6", True, "indienen")],
    ]
    resultaat = aggregeer(runs)
    assert resultaat["formulier"] == "1/2"
    assert resultaat["indienen"] == "2/2"


def test_aggregeer_bij_nul_runs_geeft_lege_samenvatting():
    assert aggregeer([]) == {}


def test_aggregeer_kent_een_controle_die_maar_in_een_run_voorkwam():
    """Een run die halverwege afbreekt levert minder controles op.

    Dan mag de noemer niet stilzwijgend het aantal runs worden: dat maakt een
    afgebroken run tot een gefaalde controle en dat is iets anders.
    """
    runs = [
        [Uitkomst("stap4", True, "formulier")],
        [],
    ]
    assert aggregeer(runs) == {"formulier": "1/1"}
```

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_onderzoeksflow_aggregatie.py -v
```

Verwacht: FAIL met `ImportError: cannot import name 'aggregeer'`.

- [ ] **Stap 3: Implementeer `aggregeer`**

In `services/host/scripts/onderzoeksflow.py`, naast de bestaande dataclasses:

```python
def aggregeer(runs: list[list[Uitkomst]]) -> dict[str, str]:
    """Per controle: hoe vaak geslaagd van hoe vaak uitgevoerd.

    De noemer is het aantal keren dat de controle daadwerkelijk draaide, niet
    het aantal runs. Een run die halverwege afbreekt heeft die controle niet
    uitgevoerd, en dat is iets anders dan hem niet halen.
    """
    tellers: dict[str, list[int]] = {}
    for run in runs:
        for uitkomst in run:
            geslaagd, totaal = tellers.setdefault(uitkomst.reden, [0, 0])
            tellers[uitkomst.reden] = [geslaagd + int(uitkomst.ok), totaal + 1]
    return {reden: f"{g}/{t}" for reden, (g, t) in tellers.items()}
```

- [ ] **Stap 4: Draai de test en zie hem slagen**

```bash
uv run pytest services/host/tests/test_onderzoeksflow_aggregatie.py -v
```

- [ ] **Stap 5: Voeg `--runs` en `--json` toe**

In `main()` van `onderzoeksflow.py`:

```python
    p.add_argument("--runs", type=int, default=1, help="aantal doorlopen")
    p.add_argument("--json", help="schrijf een machineleesbare samenvatting hierheen")
```

En vervang de enkele `draai()`-aanroep door een lus die per run een verse `Loop`
maakt (dus een vers `session_id`, anders lopen de gesprekken door elkaar):

```python
    alle_runs: list[list[Uitkomst]] = []
    for nummer in range(1, a.runs + 1):
        print(f"\n{'#' * 70}\n# RUN {nummer} van {a.runs}\n{'#' * 70}")
        loop = Loop(host=a.host, kvk=a.kvk, mode=a.mode)
        try:
            draai(loop, persona)
        except httpx.HTTPError as e:
            print(f"RUN {nummer} AFGEBROKEN: {type(e).__name__}: {e}")
        alle_runs.append(loop.uitkomsten)

    samenvatting = aggregeer(alle_runs)
    print(f"\n{'=' * 70}\nSAMENVATTING OVER {a.runs} RUN(S)")
    for reden, score in sorted(samenvatting.items()):
        geslaagd, totaal = (int(x) for x in score.split("/"))
        vlag = "OK  " if geslaagd == totaal else "FOUT"
        print(f"  [{vlag}] {score}  {reden}")

    if a.json:
        Path(a.json).write_text(
            json.dumps(
                {
                    "modus": a.mode,
                    "kvk": a.kvk,
                    "runs": a.runs,
                    "samenvatting": samenvatting,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    alles_groen = all(
        score.split("/")[0] == score.split("/")[1] for score in samenvatting.values()
    )
    return 0 if alles_groen else 1
```

- [ ] **Stap 6: Draai de nulmeting**

De host moet draaien. Start hem in een aparte shell (deze omgeving exporteert
`ANTHROPIC_API_KEY` als lege string, wat `load_dotenv` overschaduwt — vandaar
`env -u`):

```bash
env -u ANTHROPIC_API_KEY uv run uvicorn api:app --app-dir services/host --port 8000
```

Dan, vijf runs:

```bash
uv run python services/host/scripts/onderzoeksflow.py \
  --mode vlam --kvk 62345681 --runs 5 --json /tmp/nulmeting-vlam.json
```

Dit kost ongeveer dertig LLM-beurten en duurt tien tot twintig minuten.

- [ ] **Stap 7: Leg de nulmeting vast**

Schrijf `docs/superpowers/plans/nulmeting-2026-08-13.md` met de tabel uit de
samenvatting, de datum, de modus en de commit-hash waarop gemeten is. Zonder die
hash is de meting later niet te reproduceren.

- [ ] **Stap 8: Commit**

```bash
git add services/host/scripts/onderzoeksflow.py services/host/tests/test_onderzoeksflow_aggregatie.py docs/superpowers/plans/nulmeting-2026-08-13.md
git commit -m "feat(scripts): draai de onderzoeksflow herhaald en aggregeer

Alle besmettende bevindingen zijn intermitterend: een tot twee op drie runs.
Een enkele doorloop zegt daar niets over, dus --runs met een samenvatting per
controle, en de nulmeting op de huidige code vastgelegd.

De noemer in de samenvatting is het aantal keren dat een controle draaide en
niet het aantal runs: een afgebroken run heeft die controle niet uitgevoerd, en
dat is iets anders dan hem niet halen."
```

---

### Taak 3: Doorgeefluik in de RegelRecht-server

De engine geeft de drempelwaarden alleen mee op de aanroep met lege parameters;
het model roept altijd met gevulde parameters aan en krijgt ze dus nooit. Tegelijk
zeggen de tool-beschrijving en `tool_usage.md` dat het die waarden moet gebruiken
en geen eigen getallen mag noemen. Die instructie is niet op te volgen.

**Files:**
- Modify: `services/mcp/regelrecht/server.py` (`_simplify_result`, nieuwe
  `_definities_voor`, de tool-handler die `_simplify_result` aanroept)
- Modify: `services/host/prompts/blocks/shared/tool_usage.md`
- Test: `services/mcp/regelrecht/` heeft geen eigen testmap; test in
  `services/host/tests/test_regelrecht_doorgeefluik.py`

**Interfaces:**
- Consumes: `_rpc_call(method, params)` uit dezelfde module
- Produces: `_simplify_result(structured: dict, definities: dict | None = None) -> dict`
  met de sleutels `gebruikte_waarden: dict[str, Any]` en `drempelwaarden: dict[str, Any]`;
  `async _definities_voor(law: str, service: str) -> dict`

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_regelrecht_doorgeefluik.py`:

```python
"""De waarden waarop RegelRecht rekende, bereiken het model.

De engine levert de gebruikte waarden onder `input` en de constanten onder
`rule_spec.properties.definitions`. Dat laatste is alleen gevuld bij een aanroep
met lege parameters - precies de aanroep die het model nooit doet. Zonder dit
doorgeefluik moet het model getallen noemen die het niet heeft, terwijl de
prompt verbiedt ze uit eigen kennis te halen.
"""

import importlib.util
from pathlib import Path

import pytest

SERVER = (
    Path(__file__).resolve().parents[2] / "mcp" / "regelrecht" / "server.py"
)


@pytest.fixture(scope="module")
def regelrecht():
    spec = importlib.util.spec_from_file_location("mcp_regelrecht", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gebruikte_waarden_komen_mee_zonder_dollarprefix(regelrecht):
    structured = {
        "requirements_met": True,
        "output": {"heeft_informatieplicht": True},
        "input": {
            "$JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 420000,
            "$DREMPEL_ELEKTRICITEIT_KWH": 50000,
        },
    }
    resultaat = regelrecht._simplify_result(structured)
    assert resultaat["gebruikte_waarden"] == {
        "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 420000,
        "DREMPEL_ELEKTRICITEIT_KWH": 50000,
    }


def test_drempelwaarden_komen_uit_de_meegegeven_definities(regelrecht):
    """De echte engine geeft `definitions` leeg terug bij gevulde parameters.

    Dat is het geval dat telt: dit is de aanroep die het model doet.
    """
    structured = {
        "requirements_met": True,
        "output": {},
        "input": {},
        "rule_spec": {"properties": {"definitions": {}}},
    }
    resultaat = regelrecht._simplify_result(
        structured, definities={"DREMPEL_GAS_M3": 25000}
    )
    assert resultaat["drempelwaarden"] == {"DREMPEL_GAS_M3": 25000}


def test_zonder_input_geen_leeg_veld(regelrecht):
    """Een leeg veld suggereert dat er niets gebruikt is, en dat is iets anders
    dan dat we het niet weten."""
    resultaat = regelrecht._simplify_result(
        {"requirements_met": False, "output": {}, "input": {}}
    )
    assert "gebruikte_waarden" not in resultaat
```

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_regelrecht_doorgeefluik.py -v
```

Verwacht: FAIL met `KeyError: 'gebruikte_waarden'`.

- [ ] **Stap 3: Breid `_simplify_result` uit**

In `services/mcp/regelrecht/server.py`, in `_simplify_result` (regel 192), vóór
de bestaande `rule_spec`-blokken:

```python
def _simplify_result(structured: dict, definities: dict | None = None) -> dict:
    """Extraheer de relevante velden uit de uitgebreide RegelRecht response.

    `definities` komt van `_definities_voor`, omdat de engine
    `rule_spec.properties.definitions` alleen vult bij een aanroep met lege
    parameters. Het model roept altijd met gevulde parameters aan; zonder dit
    argument heeft het dus nooit de drempels waar de prompt om vraagt.
    """
```

En binnen de functie, na `result["uitkomsten"]`:

```python
    # De waarden waarop de regel feitelijk rekende. Zonder deze moet het model
    # de getallen uit het gesprek reconstrueren of verzinnen.
    gebruikt = {
        naam.lstrip("$"): waarde
        for naam, waarde in (structured.get("input") or {}).items()
    }
    if gebruikt:
        result["gebruikte_waarden"] = gebruikt
```

En vervang het bestaande `definitions`-blok:

```python
    # Constanten van de regel. Meegegeven wint van wat er in deze respons zit:
    # bij gevulde parameters geeft de engine hier niets terug.
    uit_respons = (
        structured.get("rule_spec", {}).get("properties", {}).get("definitions", {})
    )
    drempels = definities or uit_respons
    if drempels:
        result["drempelwaarden"] = drempels
```

- [ ] **Stap 4: Draai de test en zie hem slagen**

```bash
uv run pytest services/host/tests/test_regelrecht_doorgeefluik.py -v
```

- [ ] **Stap 5: Voeg `_definities_voor` toe met cache**

Naast `_rpc_call` in dezelfde module:

```python
# Constanten per wet. De engine geeft ze alleen bij een aanroep met lege
# parameters, dus die aanroep is een extra RPC per toets. Binnen een sessie
# veranderen wetsconstanten niet, dus cachen we ze procesbreed.
_definities_cache: dict[str, dict] = {}


async def _definities_voor(law: str, service: str) -> dict:
    """Constanten (drempelwaarden) van een wet, uit de engine.

    Faalt de aanroep, dan geven we een leeg dict terug in plaats van de toets te
    laten klappen: zonder drempels is het antwoord onvolledig, met een exception
    is er geen antwoord.
    """
    sleutel = f"{service}/{law}"
    if sleutel in _definities_cache:
        return _definities_cache[sleutel]
    try:
        rpc = await _rpc_call(
            "tools/call",
            {
                "name": "execute_law",
                "arguments": {"service": service, "law": law, "parameters": {}},
            },
        )
        structured = rpc.get("structuredContent", {})
        definities = (
            structured.get("rule_spec", {}).get("properties", {}).get("definitions", {})
            or {}
        )
    except Exception as e:
        logger.warning("Definities ophalen mislukt (%s): %s", law, e)
        definities = {}
    _definities_cache[sleutel] = definities
    return definities
```

- [ ] **Stap 6: Geef de definities door in de tool-handler**

Zoek in `server.py` de plek waar `_simplify_result(...)` wordt aangeroepen na
`_rpc_call` (rond regel 434 in de `execute_law`-handler). Haal daar eerst de
definities op en geef ze mee:

```python
        definities = await _definities_voor(law, service)
        data = _simplify_result(result.get("structuredContent", {}), definities)
```

Gebruik de variabelenamen die er staan; verander de omliggende structuur niet.

- [ ] **Stap 7: Werk `tool_usage.md` bij**

Regel 41 verwijst naar `DREMPEL_ELEKTRICITEIT_KWH` en `DREMPEL_GAS_M3` in een
veld `drempelwaarden` dat er tot nu toe nooit was. Dat veld bestaat nu wél, en er
is een tweede veld bij. Maak ervan:

```
-> De drempelwaarden staan in het execute_law-resultaat in het veld
   drempelwaarden (o.a. DREMPEL_ELEKTRICITEIT_KWH, DREMPEL_GAS_M3). De waarden
   waarop de toets feitelijk rekende staan in gebruikte_waarden. Gebruik die
   velden; noem geen drempelgetallen uit je eigen kennis. Staat een waarde er
   niet bij, zeg dan dat je hem niet hebt.
```

- [ ] **Stap 8: Controleer end-to-end tegen de echte engine**

```bash
uv run python -c "
import asyncio, importlib.util, json
spec = importlib.util.spec_from_file_location('rr', 'services/mcp/regelrecht/server.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
async def probe():
    d = await m._definities_voor('omgevingswet/energiebesparing/informatieplicht', 'RVO')
    print('definities:', json.dumps(d, ensure_ascii=False))
asyncio.run(probe())
"
```

Verwacht: een dict met minstens `DREMPEL_ELEKTRICITEIT_KWH: 50000` en
`DREMPEL_GAS_M3: 25000`. Komt er `{}` uit, dan is de engine onbereikbaar of
veranderd — stop en meld het, want de rest van dit plan steunt hierop.

- [ ] **Stap 9: Volledige suite en commit**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
git add services/mcp/regelrecht/server.py services/host/prompts/blocks/shared/tool_usage.md services/host/tests/test_regelrecht_doorgeefluik.py
git commit -m "fix(regelrecht): geef door waarop de regel gerekend heeft

De engine levert de drempelwaarden alleen op de aanroep met lege parameters.
Het model roept altijd met gevulde parameters aan en kreeg ze dus nooit, terwijl
de prompt zegt dat ze in het resultaat staan en dat het geen eigen getallen mag
noemen. Die instructie was niet op te volgen.

_simplify_result geeft nu gebruikte_waarden door (uit input, zonder dollarprefix)
en drempelwaarden uit een aparte lege-parameter-aanroep, procesbreed gecachet
omdat wetsconstanten binnen een sessie niet veranderen."
```

---

### Taak 4: Feitenkaart per sessie

De substitutie in taak 5 heeft een bron nodig. De host ziet elk tool-resultaat al
langs komen in `_execute_tools`; `_extract_lopende_zaak` leest daar nu al uit mee
en stuurt een `case`-event dat het model niet aanraakt. Dat patroon breiden we uit.

**Files:**
- Create: `services/host/feiten.py`
- Modify: `services/host/vlam_host.py` (opslag naast `self.conversations`, oogsten
  in beide streaming-lussen)
- Test: `services/host/tests/test_feitenkaart.py`

**Interfaces:**
- Consumes: tool-resultaten als JSON-string, envelope `{"data": {...}, "provenance": {...}}`
- Produces: `feiten_uit_tool(tool_naam: str, resultaat: str) -> dict[str, object]`
  met slotnamen als sleutel; `VlamHost.feiten: dict[str, dict]` op dezelfde
  sleutel als `self.conversations`

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_feitenkaart.py`:

```python
"""Canonieke feiten uit tool-resultaten, als bron voor slot-substitutie.

Elk feit dat hier niet uit komt, moet het model uit het gesprek reconstrueren -
en dat is precies waar 'Bloemenlaan 12' vandaan kwam terwijl de KvK-tool
'Hoefweg 210' had geleverd.
"""

import json

from feiten import feiten_uit_tool


def _envelope(data: dict) -> str:
    return json.dumps({"data": data, "provenance": {"source": "test"}})


def test_kvk_levert_naam_nummer_en_bezoekadres():
    resultaat = _envelope(
        {
            "naam": "Kwekerij De Bloesem",
            "kvkNummer": "62345681",
            "rechtsvorm": "Vennootschap onder firma",
            "_embedded": {
                "hoofdvestiging": {
                    "vestigingsnummer": "000062345681",
                    "adressen": [
                        {"type": "correspondentieadres", "volledigAdres": "Postbus 1, 2665AA Bleiswijk"},
                        {"type": "bezoekadres", "volledigAdres": "Hoefweg 210, 2665KG Bleiswijk"},
                    ],
                }
            },
        }
    )
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["BEDRIJFSNAAM"] == "Kwekerij De Bloesem"
    assert feiten["KVK_NUMMER"] == "62345681"
    assert feiten["VESTIGINGSNUMMER"] == "000062345681"
    assert feiten["VESTIGINGSADRES"] == "Hoefweg 210, 2665KG Bleiswijk"


def test_adres_wordt_op_type_gekozen_niet_op_positie():
    """Een postbus als eerste adres is het geval dat positie-kiezen sloopt."""
    resultaat = _envelope(
        {
            "naam": "Vogel Bouwregie B.V.",
            "kvkNummer": "61234570",
            "_embedded": {
                "hoofdvestiging": {
                    "adressen": [
                        {"type": "correspondentieadres", "volledigAdres": "Postbus 44, 3000AA Rotterdam"},
                        {"type": "bezoekadres", "volledigAdres": "Coolsingel 1, 3011AD Rotterdam"},
                    ]
                }
            },
        }
    )
    assert feiten_uit_tool("kvk__mijn_bedrijf", resultaat)["VESTIGINGSADRES"] == (
        "Coolsingel 1, 3011AD Rotterdam"
    )


def test_netbeheerder_levert_verbruik_en_peiljaar():
    resultaat = _envelope(
        {
            "peiljaar": 2025,
            "netbeheerder": "Stedin (mock)",
            "totaal": {
                "jaarlijks_elektriciteitsverbruik_kwh": 420000,
                "jaarlijks_gasverbruik_m3": 140000,
            },
        }
    )
    feiten = feiten_uit_tool("netbeheerder__verbruik", resultaat)
    assert feiten["ELEKTRICITEIT_KWH"] == 420000
    assert feiten["GAS_M3"] == 140000
    assert feiten["PEILJAAR"] == 2025
    assert feiten["NETBEHEERDER"] == "Stedin (mock)"


def test_regelrecht_levert_drempels_en_oordelen():
    resultaat = _envelope(
        {
            "drempelwaarden": {"DREMPEL_ELEKTRICITEIT_KWH": 50000},
            "gebruikte_waarden": {"JAARLIJKS_GASVERBRUIK_M3": 140000},
            "uitkomsten": {
                "heeft_informatieplicht": True,
                "heeft_onderzoeksplicht": False,
                "volgende_rapportage_deadline": "2027-12-01",
            },
        }
    )
    feiten = feiten_uit_tool("regelrecht__execute_law", resultaat)
    assert feiten["DREMPEL_ELEKTRICITEIT_KWH"] == 50000
    assert feiten["OORDEEL_INFORMATIEPLICHT"] is True
    assert feiten["OORDEEL_ONDERZOEKSPLICHT"] is False
    assert feiten["VOLGENDE_DEADLINE"] == "2027-12-01"


def test_onbekende_tool_levert_niets():
    assert feiten_uit_tool("koop__zoek_regelgeving", _envelope({"titel": "x"})) == {}


def test_kapot_resultaat_levert_niets_en_gooit_niet():
    """Een bron die rommel teruggeeft mag het gesprek niet laten klappen."""
    assert feiten_uit_tool("kvk__mijn_bedrijf", "geen json") == {}
```

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_feitenkaart.py -v
```

Verwacht: FAIL met `ModuleNotFoundError: No module named 'feiten'`.

- [ ] **Stap 3: Schrijf `services/host/feiten.py`**

```python
"""Canonieke feiten uit tool-resultaten, als bron voor slot-substitutie.

Het model schrijft `{{VESTIGINGSADRES}}`; de host vult in wat hier uit komt. Een
feit dat deze module niet oplevert, kan het model dus niet noemen - en dat is de
bedoeling: liever "die gegevens heb ik niet" dan een verzonnen adres in een
rapport dat namens de ondernemer naar RVO gaat.

Waarom hier en niet in de MCP-servers: die leveren de vorm van hun eigen bron.
De vertaling naar slotnamen is een keuze van de host, en één plek waar die keuze
staat is beter dan vijf servers die hem elk half maken.
"""

import json
import logging

logger = logging.getLogger("vlam.feiten")


def _bezoekadres(vestiging: dict) -> str | None:
    """Het bezoekadres, gekozen op type en niet op positie.

    De KvK-API zet het correspondentieadres eerst. Bij een postbus als postadres
    zou positie-kiezen het verkeerde adres opleveren - en dat is precies het
    adres dat de respondent op zijn scherm niet ziet staan.
    """
    for adres in vestiging.get("adressen") or []:
        if adres.get("type") == "bezoekadres":
            return adres.get("volledigAdres")
    return None


def _uit_kvk(data: dict) -> dict:
    vestiging = (data.get("_embedded") or {}).get("hoofdvestiging") or {}
    feiten = {
        "BEDRIJFSNAAM": data.get("naam"),
        "KVK_NUMMER": data.get("kvkNummer"),
        "RECHTSVORM": data.get("rechtsvorm"),
        "VESTIGINGSNUMMER": vestiging.get("vestigingsnummer"),
        "VESTIGINGSADRES": _bezoekadres(vestiging),
        "WOONFUNCTIE": (data.get("bag") or {}).get("is_woonfunctie"),
        "GEBRUIKSDOEL": (data.get("bag") or {}).get("gebruiksdoel"),
    }
    return {k: v for k, v in feiten.items() if v is not None}


def _uit_netbeheerder(data: dict) -> dict:
    totaal = data.get("totaal") or {}
    feiten = {
        "ELEKTRICITEIT_KWH": totaal.get("jaarlijks_elektriciteitsverbruik_kwh"),
        "GAS_M3": totaal.get("jaarlijks_gasverbruik_m3"),
        "PEILJAAR": data.get("peiljaar"),
        "NETBEHEERDER": data.get("netbeheerder"),
    }
    return {k: v for k, v in feiten.items() if v is not None}


# De uitkomsten van RegelRecht die als slot beschikbaar komen.
_OORDELEN = {
    "heeft_energiebesparingsplicht": "OORDEEL_ENERGIEBESPARINGSPLICHT",
    "heeft_informatieplicht": "OORDEEL_INFORMATIEPLICHT",
    "heeft_onderzoeksplicht": "OORDEEL_ONDERZOEKSPLICHT",
}

_UITKOMST_VELDEN = {
    "volgende_rapportage_deadline": "VOLGENDE_DEADLINE",
    "rapportage_frequentie_jaren": "RAPPORTAGE_FREQUENTIE_JAREN",
    "rapportage_methode": "RAPPORTAGE_METHODE",
    "bevoegd_gezag": "BEVOEGD_GEZAG",
}


def _uit_regelrecht(data: dict) -> dict:
    feiten: dict[str, object] = {}
    feiten.update(data.get("drempelwaarden") or {})
    feiten.update(data.get("gebruikte_waarden") or {})
    uitkomsten = data.get("uitkomsten") or {}
    for bron, slot in _OORDELEN.items():
        if bron in uitkomsten:
            feiten[slot] = uitkomsten[bron]
    for bron, slot in _UITKOMST_VELDEN.items():
        if uitkomsten.get(bron) is not None:
            feiten[slot] = uitkomsten[bron]
    return feiten


def _uit_rvo(data: dict) -> dict:
    zaak = data.get("lopende_zaak") or {}
    nummer = zaak.get("referentienummer")
    return {"REFERENTIENUMMER": nummer} if nummer else {}


_OOGSTERS = {
    "kvk__mijn_bedrijf": _uit_kvk,
    "netbeheerder__verbruik": _uit_netbeheerder,
    "regelrecht__execute_law": _uit_regelrecht,
    "rvo__indienen": _uit_rvo,
}


def feiten_uit_tool(tool_naam: str, resultaat: str) -> dict[str, object]:
    """Feiten uit één tool-resultaat, met slotnamen als sleutel.

    Een onbekende tool of onleesbaar resultaat levert een leeg dict op: een bron
    die rommel teruggeeft mag het gesprek niet laten klappen.
    """
    oogster = _OOGSTERS.get(tool_naam)
    if oogster is None:
        return {}
    try:
        data = json.loads(resultaat).get("data") or {}
    except (ValueError, AttributeError):
        logger.warning("Tool-resultaat van %s is geen leesbare JSON", tool_naam)
        return {}
    if not isinstance(data, dict):
        return {}
    return oogster(data)
```

- [ ] **Stap 4: Draai de test en zie hem slagen**

```bash
uv run pytest services/host/tests/test_feitenkaart.py -v
```

- [ ] **Stap 5: Sla de feitenkaart op in de host**

In `services/host/vlam_host.py`, naast `self.conversations` (regel 473):

```python
        # Feiten per gesprek, geoogst uit tool-resultaten. Zelfde sleutel als
        # self.conversations, zodat één opruimmechanisme later allebei dekt -
        # geen van beide heeft nu een TTL.
        self.feiten: dict[str, dict] = {}
```

Voeg `from feiten import feiten_uit_tool` toe bij de imports.

In beide lussen waar `_extract_lopende_zaak` wordt aangeroepen (rond regel 934),
oogst je in dezelfde `zip`:

```python
            for tu, tr in zip(tool_uses, tool_results, strict=True):
                inhoud = tr.get("content", "")
                self.feiten.setdefault(conv_key, {}).update(
                    feiten_uit_tool(tu.name, inhoud)
                )
                zaak = _extract_lopende_zaak(tu.name, inhoud)
                if zaak:
                    yield {"type": "case", "data": zaak}
```

Zoek de tweede, niet-streamende lus en doe daar hetzelfde. Draait er maar één
van de twee, dan werkt `/chat` anders dan `/chat/stream` en dat merk je pas in
een sessie.

- [ ] **Stap 6: Volledige suite en commit**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
git add services/host/feiten.py services/host/vlam_host.py services/host/tests/test_feitenkaart.py
git commit -m "feat(host): feitenkaart per gesprek uit tool-resultaten

De host ziet elk tool-resultaat al langs komen; _extract_lopende_zaak leest daar
al uit mee. Datzelfde patroon levert nu de canonieke feiten voor slot-substitutie.

Het adres wordt op type gekozen en niet op positie: de KvK-API zet het
correspondentieadres eerst, en bij een postbus als postadres levert positie
kiezen het adres op dat de respondent juist niet op zijn scherm ziet."
```

---

### Taak 5: Slot-substitutie in de host

Het hart van dit plan. Een feit dat het model nooit schrijft, kan het niet fout
schrijven.

**Files:**
- Create: `services/host/slots.py`
- Modify: `services/host/vlam_host.py` (`_antwoord_events`, `_antwoord_tekst`)
- Modify: `services/host/errors.py` (nieuwe foutcode)
- Test: `services/host/tests/test_slots.py`

**Interfaces:**
- Consumes: `feiten_uit_tool` uit taak 4 (via `VlamHost.feiten`)
- Produces: `vul_slots(tekst: str, feiten: dict) -> tuple[str, list[str]]` — de
  ingevulde tekst plus de namen van slots die niet opgelost konden worden

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_slots.py`:

```python
"""Het model schrijft slots, de host vult ze in.

Een feit dat het model nooit schrijft kan het niet fout schrijven. Dat is de
hele reden dat deze laag bestaat; alles hier moet dus liever weigeren dan gokken.
"""

from slots import vul_slots


def test_bekend_slot_wordt_ingevuld():
    tekst, ontbrekend = vul_slots(
        "Uw bedrijf {{BEDRIJFSNAAM}} is bekend.", {"BEDRIJFSNAAM": "Kwekerij De Bloesem"}
    )
    assert tekst == "Uw bedrijf Kwekerij De Bloesem is bekend."
    assert ontbrekend == []


def test_getallen_krijgen_nederlandse_duizendtallen():
    """Zonder deze regel schrijft het model de ene keer 420000 en de andere keer
    420.000, en dat verschil ziet de respondent."""
    tekst, _ = vul_slots("{{ELEKTRICITEIT_KWH}} kWh", {"ELEKTRICITEIT_KWH": 420000})
    assert tekst == "420.000 kWh"


def test_booleans_worden_ja_of_nee():
    tekst, _ = vul_slots("Woonfunctie: {{WOONFUNCTIE}}", {"WOONFUNCTIE": False})
    assert tekst == "Woonfunctie: nee"


def test_oordeel_wordt_wel_of_niet():
    """Het oordeel komt uit RegelRecht, niet uit het model."""
    tekst, _ = vul_slots(
        "De informatieplicht geldt {{OORDEEL_INFORMATIEPLICHT}} voor u.",
        {"OORDEEL_INFORMATIEPLICHT": True},
    )
    assert tekst == "De informatieplicht geldt wel voor u."


def test_onbekend_slot_blijft_staan_en_wordt_gemeld():
    """Blijft staan zodat de aanroeper het kan tegenhouden.

    Stil weglaten zou een halve zin opleveren waarvan niemand merkt dat er een
    feit uit is verdwenen.
    """
    tekst, ontbrekend = vul_slots("Adres: {{VESTIGINGSADRES}}", {})
    assert ontbrekend == ["VESTIGINGSADRES"]
    assert "{{VESTIGINGSADRES}}" in tekst


def test_slot_buiten_het_woordenboek_wordt_gemeld():
    """Een verzonnen slotnaam is net zo goed een verzonnen feit."""
    _, ontbrekend = vul_slots("{{OMZET_2025}}", {"BEDRIJFSNAAM": "x"})
    assert ontbrekend == ["OMZET_2025"]


def test_tekst_zonder_slots_blijft_ongewijzigd():
    tekst, ontbrekend = vul_slots("Gewoon een zin.", {"BEDRIJFSNAAM": "x"})
    assert tekst == "Gewoon een zin."
    assert ontbrekend == []


def test_datum_wordt_nederlands_geschreven():
    tekst, _ = vul_slots("{{VOLGENDE_DEADLINE}}", {"VOLGENDE_DEADLINE": "2027-12-01"})
    assert tekst == "1 december 2027"
```

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_slots.py -v
```

Verwacht: FAIL met `ModuleNotFoundError: No module named 'slots'`.

- [ ] **Stap 3: Schrijf `services/host/slots.py`**

```python
"""Slots invullen uit de feitenkaart.

Het model schrijft `{{VESTIGINGSADRES}}`; deze module vult in wat de bron zei.
Wat hier niet ingevuld kan worden, blijft staan en wordt gemeld - de aanroeper
houdt het antwoord dan tegen. Een `{{…}}` op het scherm van een respondent is
even besmettend voor het onderzoek als een verkeerd feit.
"""

import re

_SLOT = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

_MAANDEN = (
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
)

# Slots waarvan de waarde een oordeel is: die lezen als "geldt wel" / "geldt
# niet" en niet als ja/nee, omdat ze middenin een zin staan.
_OORDEELSLOTS = frozenset(
    {
        "OORDEEL_ENERGIEBESPARINGSPLICHT",
        "OORDEEL_INFORMATIEPLICHT",
        "OORDEEL_ONDERZOEKSPLICHT",
    }
)


def _als_datum(waarde: str) -> str | None:
    """ISO-datum naar '1 december 2027'. Geen datum? Dan None."""
    delen = waarde.split("-")
    if len(delen) != 3:
        return None
    try:
        jaar, maand, dag = (int(d) for d in delen)
        return f"{dag} {_MAANDEN[maand - 1]} {jaar}"
    except (ValueError, IndexError):
        return None


def _weergave(naam: str, waarde: object) -> str:
    """Eén waarde, zoals de respondent hem hoort te lezen.

    De opmaak hoort hier en niet bij het model: anders schrijft het de ene keer
    420000 en de andere keer 420.000, en dat verschil valt op het scherm op.
    """
    if isinstance(waarde, bool):
        if naam in _OORDEELSLOTS:
            return "wel" if waarde else "niet"
        return "ja" if waarde else "nee"
    if isinstance(waarde, int):
        return f"{waarde:,}".replace(",", ".")
    if isinstance(waarde, float):
        return f"{waarde:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    tekst = str(waarde)
    return _als_datum(tekst) or tekst


def vul_slots(tekst: str, feiten: dict) -> tuple[str, list[str]]:
    """Vul `{{SLOT}}` in uit `feiten`.

    Geeft de ingevulde tekst terug plus de slots die niet opgelost konden worden.
    Die blijven letterlijk staan: stil weglaten levert een halve zin op waarvan
    niemand merkt dat er een feit uit verdwenen is.
    """
    ontbrekend: list[str] = []

    def vervang(match: re.Match) -> str:
        naam = match.group(1)
        if naam not in feiten:
            ontbrekend.append(naam)
            return match.group(0)
        return _weergave(naam, feiten[naam])

    return _SLOT.sub(vervang, tekst or ""), ontbrekend
```

- [ ] **Stap 4: Draai de test en zie hem slagen**

```bash
uv run pytest services/host/tests/test_slots.py -v
```

- [ ] **Stap 5: Voeg de foutcode toe**

In `services/host/errors.py`, in de `FOUTEN`-catalogus, volgens het patroon van
de bestaande entries:

```python
    "ANTWOORD_ONVOLLEDIG": Fout(
        code="ANTWOORD_ONVOLLEDIG",
        bericht="De assistent kon een gegeven niet ophalen bij de bron.",
        actie="Stel uw vraag opnieuw. Blijft het misgaan, meld dit dan bij de "
        "beheerder van deze omgeving.",
        http_status=502,
    ),
```

Kijk hoe de bestaande `Fout`-objecten er precies uitzien en volg dat exact;
`tests/test_foutmeldingen_catalogus.py` scant de broncode en faalt bij afwijking.

- [ ] **Stap 6: Sluit de substitutie aan op het antwoord**

In `vlam_host.py` gaan alle streaming-antwoorden door `_antwoord_events` en alle
blokkerende door `_antwoord_tekst`. Dat zijn de twee plekken.

Beide functies zijn nu module-niveau en kennen de feiten niet. Geef ze een
`feiten`-argument mee met een lege default, zodat bestaande aanroepen blijven
werken tot je ze allemaal langs bent geweest:

```python
def _antwoord_events(tekst: str, afgekapt: bool = False, feiten: dict | None = None):
    """...bestaande docstring...

    De slots worden hier ingevuld, op de laatste plek voordat de tekst de deur
    uit gaat. Blijft er een slot onopgelost, dan gaat het antwoord niet mee: een
    zichtbare `{{…}}` is voor de respondent even verwarrend als een fout feit,
    en een half ingevuld rapport is erger dan een foutmelding.
    """
    tekst, ontbrekend = vul_slots(tekst, feiten or {})
    if ontbrekend:
        logger.error("Onopgeloste slots in het antwoord: %s", sorted(set(ontbrekend)))
        return [naar_event(maak_fout("ANTWOORD_ONVOLLEDIG"))]
```

Zet dit vóór de bestaande `if not (tekst or "").strip():`-controle, zodat een
antwoord dat alleen uit slots bestond niet als leeg antwoord wordt gemeld.

Doe hetzelfde in `_antwoord_tekst`.

Werk daarna elke aanroep van beide functies bij zodat de feitenkaart van dat
gesprek meegaat: `self.feiten.get(conv_key, {})`. Zoek ze met
`grep -n "_antwoord_events\|_antwoord_tekst" services/host/vlam_host.py`.

- [ ] **Stap 7: Schrijf de regressietest op het dichtzetten**

In `services/host/tests/test_slots.py`:

```python
def test_een_onopgelost_slot_haalt_het_antwoord_niet():
    """De hele reden dat deze laag bestaat.

    Liever een foutmelding dan een rapport waarin een feit ontbreekt of verzonnen
    is; dat rapport gaat namens de ondernemer naar RVO.
    """
    import vlam_host

    events = vlam_host._antwoord_events(
        "Uw adres is {{VESTIGINGSADRES}}.", feiten={}
    )
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "{{" not in str(events[0])
```

- [ ] **Stap 8: Draai en commit**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
git add services/host/slots.py services/host/errors.py services/host/vlam_host.py services/host/tests/test_slots.py
git commit -m "feat(host): vul slots in uit de bron en weiger wat niet opgelost is

Het model schrijft {{VESTIGINGSADRES}}; de host vult in wat de KvK zei. Een feit
dat het model nooit schrijft, kan het niet fout schrijven.

Een onopgelost slot haalt het antwoord niet: een zichtbare {{...}} is voor de
respondent even verwarrend als een verkeerd feit, en een half ingevuld rapport
is erger dan een foutmelding.

De opmaak zit in de host en niet in het model - duizendtallen, datums, ja/nee -
zodat dezelfde waarde niet per antwoord anders geschreven wordt."
```

---

### Taak 6: De prompt laat het model slots schrijven

Zonder deze taak schrijft het model gewoon door in feiten en doet taak 5 niets.

**Files:**
- Create: `services/host/prompts/blocks/shared/slots.md`
- Modify: `services/host/prompts/composer.py`
- Modify: `services/host/prompts/blocks/shared/format.md`
- Modify: alle `services/host/prompts/examples/*.md` die feiten tonen
- Test: `services/host/tests/test_slots_prompt.py`

**Interfaces:**
- Consumes: `compose_system_prompt(mode, has_tools, bronnen_offline, cli_transport)`
- Produces: systeemprompt bevat het slotblok wanneer `has_tools` waar is

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_slots_prompt.py`:

```python
"""De prompt leert het model slots te schrijven, en de voorbeelden doen het voor.

Een model imiteert voorbeelden sterker dan het een instructie volgt. Staat er in
een voorbeeld een letterlijk bedrijfsnaam, dan schrijft het model die ook - en
dan blokkeert de host het antwoord.
"""

import re
from pathlib import Path

from prompts.composer import compose_system_prompt

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
VOORBEELDEN = sorted((PROMPTS / "examples").glob("*.md"))

# Waarden uit de mockpersona's die nooit letterlijk in een voorbeeld horen: als
# het model ze imiteert, noemt het het bedrijf van iemand anders.
_VERBODEN_LETTERLIJK = ("Koffiezaak Noon", "Test BV Donald", "Hoefweg 210", "Meent 88")


def test_de_prompt_bevat_het_slotblok():
    prompt = compose_system_prompt("vlam", has_tools=True)
    assert "{{BEDRIJFSNAAM}}" in prompt
    assert "{{ELEKTRICITEIT_KWH}}" in prompt


def test_zonder_tools_geen_slotblok():
    """Zonder bronnen zijn er geen feiten, dus ook niets om in te vullen."""
    assert "{{BEDRIJFSNAAM}}" not in compose_system_prompt("vlam", has_tools=False)


def test_geen_voorbeeld_toont_een_letterlijk_bedrijfsfeit():
    overtredingen = []
    for pad in VOORBEELDEN:
        tekst = pad.read_text(encoding="utf-8")
        for waarde in _VERBODEN_LETTERLIJK:
            if waarde in tekst:
                overtredingen.append(f"{pad.name}: {waarde!r}")
    assert not overtredingen, (
        "voorbeelden tonen letterlijke feiten waar een slot hoort:\n  "
        + "\n  ".join(overtredingen)
    )


def test_elk_slot_in_de_voorbeelden_staat_in_het_woordenboek():
    """Een verzonnen slotnaam in een voorbeeld leert het model een slot dat de
    host niet kent, en dat blokkeert elk antwoord waarin het voorkomt."""
    from slots import _SLOT

    bekend = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", (
        PROMPTS / "blocks" / "shared" / "slots.md"
    ).read_text(encoding="utf-8")))
    for pad in VOORBEELDEN:
        for naam in _SLOT.findall(pad.read_text(encoding="utf-8")):
            assert naam in bekend, f"{pad.name}: onbekend slot {naam}"
```

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_slots_prompt.py -v
```

Verwacht: FAIL — het slotblok bestaat nog niet en de voorbeelden staan vol
letterlijke feiten.

- [ ] **Stap 3: Schrijf `slots.md`**

```markdown
Gegevens over het bedrijf van de gebruiker schrijft u NOOIT zelf uit. U schrijft
een plaatshouder; het systeem vult de waarde in uit de bron.

Dus: "Uw bedrijf {{BEDRIJFSNAAM}} verbruikt {{ELEKTRICITEIT_KWH}} kWh per jaar."
Niet: "Uw bedrijf Kwekerij De Bloesem verbruikt 420.000 kWh per jaar."

Dit geldt in ELK antwoord, niet alleen in het rapport.

Beschikbare plaatshouders:
- Bedrijf: {{BEDRIJFSNAAM}}, {{KVK_NUMMER}}, {{RECHTSVORM}}, {{VESTIGINGSADRES}}, {{VESTIGINGSNUMMER}}, {{WOONFUNCTIE}}, {{GEBRUIKSDOEL}}
- Energie: {{ELEKTRICITEIT_KWH}}, {{GAS_M3}}, {{PEILJAAR}}, {{NETBEHEERDER}}
- Drempels: {{DREMPEL_ELEKTRICITEIT_KWH}}, {{DREMPEL_GAS_M3}}, {{DREMPEL_ONDERZOEK_ELEKTRICITEIT_KWH}}, {{DREMPEL_ONDERZOEK_GAS_M3}}
- Uitkomst: {{OORDEEL_ENERGIEBESPARINGSPLICHT}}, {{OORDEEL_INFORMATIEPLICHT}}, {{OORDEEL_ONDERZOEKSPLICHT}}
- Rapportage: {{VOLGENDE_DEADLINE}}, {{RAPPORTAGE_FREQUENTIE_JAREN}}, {{RAPPORTAGE_METHODE}}, {{BEVOEGD_GEZAG}}, {{REFERENTIENUMMER}}

De oordeel-plaatshouders worden "wel" of "niet". Schrijf de zin zo dat beide
passen: "De informatieplicht geldt {{OORDEEL_INFORMATIEPLICHT}} voor uw bedrijf."

Gebruik ALLEEN plaatshouders uit deze lijst. Verzin er geen. Hebt u een gegeven
nodig dat er niet bij staat, zeg dan dat u het niet hebt.

Gebruik een plaatshouder pas nadat u de bron hebt geraadpleegd. Noemt u
{{ELEKTRICITEIT_KWH}} voordat u het verbruik hebt opgevraagd, dan kan het
systeem hem niet invullen en krijgt de gebruiker een foutmelding in plaats van
een antwoord.

Getallen, datums en ja/nee worden door het systeem opgemaakt. Schrijf geen
eenheid ín de plaatshouder: "{{ELEKTRICITEIT_KWH}} kWh", niet "{{ELEKTRICITEIT_KWH_MET_EENHEID}}".
```

- [ ] **Stap 4: Laad het blok in de composer**

In `services/host/prompts/composer.py`, in `compose_system_prompt`, binnen de
`if has_tools:`-tak en vóór `tool_usage.md`:

```python
        # Vóór tool_usage: de slotregel geldt voor élk antwoord, ook voor
        # antwoorden die geen tool gebruiken maar wel een eerder feit noemen.
        blocks.append(_load("shared/slots.md"))
```

- [ ] **Stap 5: Draai de eerste twee tests**

```bash
uv run pytest services/host/tests/test_slots_prompt.py::test_de_prompt_bevat_het_slotblok services/host/tests/test_slots_prompt.py::test_zonder_tools_geen_slotblok -v
```

Verwacht: PASS.

- [ ] **Stap 6: Herschrijf de voorbeelden naar slots**

Loop elk bestand in `services/host/prompts/examples/` langs en vervang elk
bedrijfsgegeven door zijn slot. Bijvoorbeeld in `informatieplicht_flow.md`:

```
- KvK Handelsregister: {{BEDRIJFSNAAM}}, KvK {{KVK_NUMMER}}, café (SBI 56102), {{VESTIGINGSADRES}} - geen woonfunctie.
- Uw Business Wallet: {{ELEKTRICITEIT_KWH}} kWh elektriciteit en {{GAS_M3}} m³ gas (peiljaar {{PEILJAAR}}).
```

Let op drie dingen:
1. `format.md` regels 17-19 tonen een formulier met `- Jaarlijks
   elektriciteitsverbruik: ___ kWh`. Dat blijft `___`: dat betekent "hier vult de
   gebruiker iets in" en is iets anders dan een slot.
2. De B1-tests uit `test_taalniveau.py` draaien over deze bestanden. Een slot
   telt als één woord, dus de zinslengte verandert; controleer na afloop.
3. `test_taalniveau.py` heeft een `BASISSCORE`-ratel per bestand. Verandert een
   score door het herschrijven, werk die waarde bij — dat is geen omzeiling maar
   precies waar de ratel voor bedoeld is.

- [ ] **Stap 7: Draai alle tests en repareer de ratel**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
```

Faalt `test_voorbeeldantwoorden_gebruiken_ook_alledaagse_woorden`, werk dan de
betreffende waarde in `BASISSCORE` bij naar de gemeten score.

- [ ] **Stap 8: Commit**

```bash
uv run ruff check .
git add services/host/prompts/ services/host/tests/test_slots_prompt.py
git commit -m "feat(prompts): het model schrijft plaatshouders in plaats van feiten

Zonder deze wijziging blijft het model feiten uitschrijven en doet de
substitutie in de host niets.

De voorbeelden gaan mee, want die sturen sterker dan de instructie: een
letterlijke bedrijfsnaam in een voorbeeld leert het model precies het
tegenovergestelde, en dan blokkeert de host het antwoord.

Een test bewaakt dat geen voorbeeld nog een letterlijk bedrijfsfeit toont en dat
elk gebruikt slot in het woordenboek staat."
```

---

### Taak 7: Maatregelen op het `answer`-event

De frontend leest `payload.maatregelen` al vóór hij terugvalt op tekst parsen.
Het formulier hangt nu af van hoe het model formatteert, en dat verschilt per
beurt.

**Files:**
- Modify: `services/host/vlam_host.py`
- Test: `services/host/tests/test_maatregelen_event.py`

**Interfaces:**
- Consumes: tool-resultaat van `regelrecht__execute_law` met veld `maatregelen`
- Produces: `maatregelen_voor_event(tool_naam: str, resultaat: str) -> list[dict] | None`,
  items `{"code": str, "omschrijving": str}`

- [ ] **Stap 1: Schrijf de falende test**

In `services/host/tests/test_maatregelen_event.py`:

```python
"""De maatregelen gaan als data mee, niet als tekst.

vraagSpec() in digitale-assistent.js leest payload.maatregelen vóór het
terugvalt op het parsen van de platte tekst. Zolang de backend dat veld niet
vult, hangt het formulier af van hoe het model die beurt formatteert - en dat
verschilt per beurt.
"""

import json

from vlam_host import maatregelen_voor_event


def _envelope(data: dict) -> str:
    return json.dumps({"data": data, "provenance": {"source": "test"}})


def test_alleen_geldende_maatregelen_gaan_mee():
    resultaat = _envelope(
        {
            "maatregelen": [
                {"code": "GC1", "naam": "Pas een klokregeling toe", "van_toepassing": True},
                {"code": "FE4", "naam": "Iets anders", "van_toepassing": False},
            ]
        }
    )
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) == [
        {"code": "GC1", "omschrijving": "Pas een klokregeling toe"}
    ]


def test_naam_wordt_omschrijving():
    """De frontend leest m.omschrijving; _eml_lijst produceert m.naam.

    Zonder deze hermapping toont het formulier kale codes zonder tekst.
    """
    resultaat = _envelope(
        {"maatregelen": [{"code": "GF4", "naam": "Vervang lampen door LED", "van_toepassing": True}]}
    )
    velden = maatregelen_voor_event("regelrecht__execute_law", resultaat)
    assert velden[0]["omschrijving"] == "Vervang lampen door LED"


def test_zonder_maatregelen_geen_veld():
    """Anders draagt elk volgend antwoord een verouderd formulier mee."""
    assert maatregelen_voor_event("regelrecht__execute_law", _envelope({})) is None


def test_andere_tool_levert_niets():
    assert maatregelen_voor_event("kvk__mijn_bedrijf", _envelope({"naam": "x"})) is None


def test_kapot_resultaat_gooit_niet():
    assert maatregelen_voor_event("regelrecht__execute_law", "geen json") is None
```

- [ ] **Stap 2: Draai de test en zie hem falen**

```bash
uv run pytest services/host/tests/test_maatregelen_event.py -v
```

Verwacht: FAIL met `ImportError: cannot import name 'maatregelen_voor_event'`.

- [ ] **Stap 3: Implementeer de extractie**

In `services/host/vlam_host.py`, naast `_extract_lopende_zaak`:

```python
def maatregelen_voor_event(tool_naam: str, resultaat: str) -> list[dict] | None:
    """De geldende EML-maatregelen als veld voor het answer-event.

    De frontend (vraagSpec in digitale-assistent.js) leest `maatregelen` vóór het
    terugvalt op het parsen van de platte tekst, en verwacht `omschrijving` waar
    de MCP-server `naam` levert. Zonder die hermapping toont het formulier kale
    codes.
    """
    if tool_naam != "regelrecht__execute_law":
        return None
    try:
        data = json.loads(resultaat).get("data") or {}
    except (ValueError, AttributeError):
        return None
    geldend = [
        {"code": m.get("code", ""), "omschrijving": m.get("naam", "")}
        for m in (data.get("maatregelen") or [])
        if m.get("van_toepassing")
    ]
    return geldend or None
```

- [ ] **Stap 4: Draai de test en zie hem slagen**

```bash
uv run pytest services/host/tests/test_maatregelen_event.py -v
```

- [ ] **Stap 5: Hang het veld aan het answer-event**

In de streaming-lus waar je in taak 4 al oogst, verzamel je de maatregelen van
déze beurt:

```python
            maatregelen_deze_beurt = None
            for tu, tr in zip(tool_uses, tool_results, strict=True):
                inhoud = tr.get("content", "")
                self.feiten.setdefault(conv_key, {}).update(
                    feiten_uit_tool(tu.name, inhoud)
                )
                maatregelen_deze_beurt = (
                    maatregelen_voor_event(tu.name, inhoud) or maatregelen_deze_beurt
                )
                zaak = _extract_lopende_zaak(tu.name, inhoud)
                if zaak:
                    yield {"type": "case", "data": zaak}
```

Geef `maatregelen_deze_beurt` mee aan `_antwoord_events` en laat die het veld
alleen toevoegen als het gevuld is:

```python
def _antwoord_events(tekst, afgekapt=False, feiten=None, maatregelen=None):
    ...
    antwoord = {"type": "answer", "message": tekst}
    if maatregelen:
        antwoord["maatregelen"] = maatregelen
    return [antwoord]
```

Vergeet de afgekapt-tak niet: die bouwt hetzelfde `answer`-event.

- [ ] **Stap 6: Volledige suite en commit**

```bash
MOZA_POC_PERSONAS=/home/claude/projects/poc-moza/_data/personas.json uv run pytest -q
uv run ruff check .
git add services/host/vlam_host.py services/host/tests/test_maatregelen_event.py
git commit -m "feat(host): maatregelen als data op het answer-event

vraagSpec leest payload.maatregelen vóór het terugvalt op tekst parsen. Zolang
de backend dat veld niet vulde, hing het formulier af van hoe het model die
beurt formatteerde - en dat verschilde per beurt.

naam wordt omschrijving omdat de frontend dat veld leest; zonder die hermapping
toont het formulier kale codes zonder tekst. Alleen geldende maatregelen gaan
mee, en alleen op de beurt waarin de tool ze opleverde."
```

---

### Taak 8: Verificatie en eindmeting

**Files:**
- Modify: `services/host/scripts/onderzoeksflow.py`
- Create: `docs/superpowers/plans/eindmeting-2026-08-13.md`

**Interfaces:**
- Consumes: `vul_slots` uit taak 5, `Loop`/`Uitkomst`/`aggregeer` uit taak 2
- Produces: controles op ruwe én ingevulde tekst

- [ ] **Stap 1: Voeg de slotcontroles toe**

In `onderzoeksflow.py`, naast `_controleer_adres`:

```python
def _controleer_slots(loop: Loop, stap: str, antwoord: str, persona: Persona) -> None:
    """Geen onopgelost slot, en de bron-waarden staan er na substitutie wél.

    Let op wat dit niet is. De spec noemt ook "geen letterlijk feit waar een slot
    hoort", en die controle hoort op de RUWE modeltekst vóór substitutie. Die
    krijgt dit script niet: over HTTP komt alleen het ingevulde antwoord binnen.
    Wil je dat toetsen, dan moet de host de ruwe tekst meesturen achter een
    debug-vlag - bewust niet in dit plan, want dat is een nieuw veld op het
    contract vlak voor een onderzoek.

    Wat hier overblijft is nog steeds het meeste waard: een onopgelost slot
    betekent dat het model een feit noemde dat de bron niet had, en ontbrekende
    bron-waarden betekenen dat de substitutie niet gedraaid heeft.
    """
    loop.controleer(
        stap,
        "{{" not in antwoord,
        "geen onopgelost slot in het antwoord",
        antwoord[:400],
    )
    letterlijk = [
        waarde
        for waarde in (persona.naam, persona.straat, persona.elektriciteit, persona.gas)
        if waarde in antwoord
    ]
    loop.controleer(
        stap,
        bool(letterlijk),
        f"de bron-waarden staan in het antwoord ({', '.join(letterlijk) or 'geen'})",
        "de host heeft de slots niet ingevuld, of het model noemde de feiten niet",
    )
```

Roep hem aan op elke stap waar nu `_controleer_adres` staat, en op stap 2 en 6
allebei.

- [ ] **Stap 2: Voeg de vereiste-slots-controle op het rapport toe**

In stap 5 van `draai()`, op de ruwe tekst vóór substitutie. De host stuurt die
niet mee, dus dit toetst het eindresultaat: het rapport moet de feiten bevatten
die `tool_usage.md` voorschrijft.

```python
    for waarde, wat in (
        (persona.naam, "bedrijfsnaam"),
        (persona.straat, "vestigingsadres"),
        (persona.elektriciteit, "elektriciteitsverbruik"),
    ):
        loop.controleer(
            "stap5", waarde in antwoord, f"het rapport bevat {wat}", antwoord[:400]
        )
```

- [ ] **Stap 3: Draai de eindmeting**

Start de host opnieuw (de prompt is gewijzigd) en draai vijf runs:

```bash
uv run python services/host/scripts/onderzoeksflow.py \
  --mode vlam --kvk 62345681 --runs 5 --json /tmp/eindmeting-vlam.json
```

- [ ] **Stap 4: Vergelijk met de nulmeting**

Schrijf `docs/superpowers/plans/eindmeting-2026-08-13.md` met de twee tabellen
naast elkaar en de commit-hashes waarop gemeten is.

Blijft één controle wisselvallig, draai díe situatie dan nog vijf keer extra
voordat je hem groen noemt — dat is de escalatieregel uit de spec. Vijf schone
runs missen een fout met kans ⅓ nog in ongeveer 13 procent van de gevallen; dat
hoort in het verslag te staan en niet weggelaten te worden.

- [ ] **Stap 5: Commit**

```bash
git add services/host/scripts/onderzoeksflow.py docs/superpowers/plans/eindmeting-2026-08-13.md
git commit -m "test(onderzoeksflow): controleer slots en leg de eindmeting vast

Twee controles erbij: geen onopgelost slot in enig antwoord, en de bron-waarden
moeten na substitutie in de tekst staan. Die tweede vangt wat waardevergelijking
mist - een verzonnen waarde staat in geen enkele feitenkaart en matcht nergens
mee.

Nulmeting en eindmeting naast elkaar, met de commit-hashes erbij zodat de meting
reproduceerbaar is."
```

---

## Zelfcontrole bij oplevering

Loop na afloop deze punten na en meld wat niet klopt:

- [ ] Elke `{{SLOT}}` in `slots.md` komt voor in `_OOGSTERS` van `feiten.py`, en
      omgekeerd levert geen oogster een slot dat niet in `slots.md` staat.
- [ ] `/chat` en `/chat/stream` gedragen zich gelijk: beide oogsten feiten, beide
      vullen slots in, beide weigeren een onopgelost slot.
- [ ] `uv run pytest` groen inclusief de pariteitstest met `MOZA_POC_PERSONAS`.
- [ ] `uv run ruff check .` schoon.
- [ ] De nulmeting en de eindmeting staan allebei vastgelegd, met commit-hash.
- [ ] `NEXT_STEPS.md` bijgewerkt (staat in `.gitignore`, dus lokaal).

## Bekende schuld die dit plan maakt

`VlamHost.feiten` groeit per gesprek en wordt nooit opgeruimd, net als
`self.conversations`. Beide staan op dezelfde sleutel zodat één opruimmechanisme
later allebei dekt. Voor een begeleide sessie met een handvol gesprekken is dat
geen probleem, maar het hoort niet stilzwijgend te groeien — zet het als open
punt in `NEXT_STEPS.md` onder MVP-02.

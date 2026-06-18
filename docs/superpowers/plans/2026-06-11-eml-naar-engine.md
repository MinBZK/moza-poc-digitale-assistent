# EML-maatregelbepaling naar poc-machine-law engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** De EML-maatregelbepaling (nu lokale mock in de RegelRecht-MCP-server) wordt een machine-uitvoerbare wet in de poc-machine-law engine (EML 2023-structuur), met een twee-staps-tool-flow waarin de feitelijke vragen uit de engine worden afgelezen.

**Architecture:** Wet-YAML `omgevingswet/energiebesparing/maatregelen` in `~/projects/poc-machine-law` met per EML 2023-maatregel één boolean output; de MCP-server (`services/mcp/regelrecht/server.py`) wordt engine-proxy met lokale fallback. Spec: `docs/superpowers/specs/2026-06-11-eml-naar-engine-design.md`.

**Tech Stack:** poc-machine-law schema v0.1.7 (YAML), Python 3.12, MCP Python SDK, httpx, pytest (+pytest-asyncio).

**Repo's en branches:**
- `~/projects/poc-machine-law` — nieuwe branch `feat/eml-maatregelen` vanaf `main`.
- Deze repo — branch `feat/eml-naar-engine` (bestaat al, gebaseerd op `feat/improve-demo`).

**Demo-subset (echte EML 2023 v1.3 codes — bron: RVO-PDF `erkende-maatregelenlijst-eml-2023-v-1-3.pdf`):**

| Code | Officiële naam | Categorie | Voorwaarde |
|---|---|---|---|
| GC1 | Pas een klokregeling toe en regel deze in | Gebouwen, Ruimteverwarming | — |
| GC3 | Pas een weersafhankelijke regeling toe | Gebouwen, Ruimteverwarming | — |
| GF4 | Vervang gloei-, halogeen- en spaarlampen door LED-lampen | Gebouwen, Binnenverlichting | — |
| FD3 | Pas nachtafdekking toe bij semi-verticale koelmeubels | Faciliteiten, Productkoeling | `HEEFT_KOELINSTALLATIE` |
| FD7 | Isoleer de wanden van koelcellen om warmte buiten te houden | Faciliteiten, Productkoeling | `HEEFT_KOELINSTALLATIE` |
| FE4 | Pas een laagdebiet afzuigkap toe bij grootkeukens | Faciliteiten, Grootkeukenapparatuur | `HEEFT_AFZUIGINSTALLATIE` |
| GD1 | Pas een klokregeling toe op het ventilatiesysteem | Gebouwen, Ruimteventilatie | `HEEFT_AFZUIGINSTALLATIE` |

NB: de oude mock-namen "waterzijdig inregelen" en "deurdranger" bestaan niet
in EML 2023; GC1/GC3 zijn de werkelijke equivalenten.

**Engine-responsevorm (geverifieerd in `web/routers/mcp.py` van poc-machine-law):**
`execute_law` → `structuredContent` met `success`, `output` (`{naam: waarde}`),
`requirements_met`, `missing_required` (bool), `rule_spec` (dict met
`properties.parameters[].{name,description}` en `properties.output[].{name,description}`).
Bij ontbrekende verplichte parameters komt `missing_required: true` terug
(evaluate gooit niet).

---

### Task 1: Wet-YAML in poc-machine-law

**Files:**
- Create: `~/projects/poc-machine-law/laws/omgevingswet/energiebesparing/maatregelen/RVO-2024-01-01.yaml`

- [ ] **Step 1: Branch maken**

```bash
cd ~/projects/poc-machine-law
git checkout main && git pull && git checkout -b feat/eml-maatregelen
```

- [ ] **Step 2: Wet-YAML schrijven**

Volledige inhoud van `laws/omgevingswet/energiebesparing/maatregelen/RVO-2024-01-01.yaml`:

```yaml
$id: https://raw.githubusercontent.com/MinBZK/poc-machine-law/refs/heads/main/schema/v0.1.7/schema.json
uuid: 7c2e8f4a-91d3-4e5b-8a6f-2b0c9d1e3f57
name: Erkende Maatregelenlijst energiebesparing (EML 2023, demo-subset)
law: omgevingswet/energiebesparing/maatregelen
law_type: "FORMELE_WET"
legal_character: "BESCHIKKING"
decision_type: "ANDERE_HANDELING"
discoverable: "BUSINESS"
requires_manual_approval: false
valid_from: 2024-01-01
service: "RVO"
description: >
  Bepaling welke maatregelen uit de Erkende Maatregelenlijst energiebesparing
  (EML 2023, versie 1.3) van toepassing zijn, op basis van feitelijke
  bedrijfskenmerken die de ondernemer aanlevert. Demo-subset van 7 maatregelen
  uit de onderdelen Gebouwen en Faciliteiten; de volledige EML kent er ~150.
  De parameter-descriptions zijn letterlijk de vragen die aan de ondernemer
  gesteld worden.

legal_basis:
  law: "Besluit activiteiten leefomgeving"
  bwb_id: "BWBR0041330"
  article: "5.15"
  url: "https://wetten.overheid.nl/BWBR0041330/2024-01-01#Hoofdstuk5_Afdeling5.4_Paragraaf5.4.1_Artikel5.15"
  juriconnect: "jci1.3:c:BWBR0041330&artikel=5.15&z=2024-01-01&g=2024-01-01"
  explanation: "Artikel 5.15 Bal verplicht tot het treffen van alle energiebesparende maatregelen met een terugverdientijd van 5 jaar of minder; de EML geldt als erkende invulling daarvan"

references:
  - law: "Erkende maatregelenlijst energiebesparing (EML) 2023, versie 1.3"
    article: "Onderdelen Gebouwen en Faciliteiten"
    url: "https://www.rvo.nl/sites/default/files/2023-11/erkende-maatregelenlijst-eml-2023-v-1-3.pdf"

properties:
  parameters:
    - name: "HEEFT_KOELINSTALLATIE"
      description: "Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?"
      type: "boolean"
      required: true
      legal_basis:
        law: "Besluit activiteiten leefomgeving"
        bwb_id: "BWBR0041330"
        article: "5.15"
        url: "https://wetten.overheid.nl/BWBR0041330/2024-01-01#Hoofdstuk5_Afdeling5.4_Paragraaf5.4.1_Artikel5.15"
        juriconnect: "jci1.3:c:BWBR0041330&artikel=5.15&z=2024-01-01&g=2024-01-01"
        explanation: "Feitelijk bedrijfskenmerk, aangeleverd door de ondernemer; bepaalt of de productkoeling-maatregelen (FD) van toepassing zijn"
    - name: "HEEFT_AFZUIGINSTALLATIE"
      description: "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?"
      type: "boolean"
      required: true
      legal_basis:
        law: "Besluit activiteiten leefomgeving"
        bwb_id: "BWBR0041330"
        article: "5.15"
        url: "https://wetten.overheid.nl/BWBR0041330/2024-01-01#Hoofdstuk5_Afdeling5.4_Paragraaf5.4.1_Artikel5.15"
        juriconnect: "jci1.3:c:BWBR0041330&artikel=5.15&z=2024-01-01&g=2024-01-01"
        explanation: "Feitelijk bedrijfskenmerk, aangeleverd door de ondernemer; bepaalt of de afzuig-/ventilatiemaatregelen (FE4, GD1) van toepassing zijn"

  output:
    - name: "eml_gc1_van_toepassing"
      description: "Gebouwen, Ruimteverwarming — Pas een klokregeling toe en regel deze in"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: &eml_basis
        law: "Besluit activiteiten leefomgeving"
        bwb_id: "BWBR0041330"
        article: "5.15"
        url: "https://wetten.overheid.nl/BWBR0041330/2024-01-01#Hoofdstuk5_Afdeling5.4_Paragraaf5.4.1_Artikel5.15"
        juriconnect: "jci1.3:c:BWBR0041330&artikel=5.15&z=2024-01-01&g=2024-01-01"
        explanation: "EML 2023-maatregel als erkende invulling van de energiebesparingsplicht (art. 5.15 Bal)"
    - name: "eml_gc3_van_toepassing"
      description: "Gebouwen, Ruimteverwarming — Pas een weersafhankelijke regeling toe"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: *eml_basis
    - name: "eml_gf4_van_toepassing"
      description: "Gebouwen, Binnenverlichting — Vervang gloei-, halogeen- en spaarlampen door LED-lampen"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: *eml_basis
    - name: "eml_fd3_van_toepassing"
      description: "Faciliteiten, Productkoeling — Pas nachtafdekking toe bij semi-verticale koelmeubels"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: *eml_basis
    - name: "eml_fd7_van_toepassing"
      description: "Faciliteiten, Productkoeling — Isoleer de wanden van koelcellen om warmte buiten te houden"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: *eml_basis
    - name: "eml_fe4_van_toepassing"
      description: "Faciliteiten, Grootkeukenapparatuur — Pas een laagdebiet afzuigkap toe bij grootkeukens"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: *eml_basis
    - name: "eml_gd1_van_toepassing"
      description: "Gebouwen, Ruimteventilatie — Pas een klokregeling toe op het ventilatiesysteem"
      type: "boolean"
      temporal:
        type: "point_in_time"
        reference: "$calculation_date"
      citizen_relevance: primary
      legal_basis: *eml_basis

  definitions: {}

variables: []

requirements: []

actions:
  - output: "eml_gc1_van_toepassing"
    value: true
    legal_basis: *eml_basis
  - output: "eml_gc3_van_toepassing"
    value: true
    legal_basis: *eml_basis
  - output: "eml_gf4_van_toepassing"
    value: true
    legal_basis: *eml_basis
  - output: "eml_fd3_van_toepassing"
    value: "$HEEFT_KOELINSTALLATIE"
    legal_basis: *eml_basis
  - output: "eml_fd7_van_toepassing"
    value: "$HEEFT_KOELINSTALLATIE"
    legal_basis: *eml_basis
  - output: "eml_fe4_van_toepassing"
    value: "$HEEFT_AFZUIGINSTALLATIE"
    legal_basis: *eml_basis
  - output: "eml_gd1_van_toepassing"
    value: "$HEEFT_AFZUIGINSTALLATIE"
    legal_basis: *eml_basis
```

NB: YAML-anchors (`&eml_basis`/`*eml_basis`) zijn standaard-YAML; mocht
`validate.py` erover klagen, vervang elke `*eml_basis` door het volledige
blok. Mocht `requirements: []` of `definitions: {}` een validatiefout geven,
laat die sleutels dan weg.

- [ ] **Step 3: Valideren**

```bash
cd ~/projects/poc-machine-law && ./script/validate.py
```

Expected: exit 0, geen fouten over het nieuwe bestand. Bij fouten: melding
lezen, YAML aanpassen (zie NB hierboven), opnieuw valideren.

- [ ] **Step 4: Smoke-check dat de engine de wet kan laden en uitvoeren**

```bash
cd ~/projects/poc-machine-law && uv run python - <<'EOF'
from machine.service import Services
services = Services("2026-06-11")
result = services.evaluate(
    "RVO", "omgevingswet/energiebesparing/maatregelen",
    parameters={"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": False},
)
print(result.output)
assert result.output["eml_gc1_van_toepassing"] is True
assert result.output["eml_fd3_van_toepassing"] is True
assert result.output["eml_fe4_van_toepassing"] is False
print("OK")
EOF
```

Expected: `OK`. (Als het Services-import-pad afwijkt: kijk hoe
`web/dependencies.py` de machine-service construeert en volg dat patroon.)
Test ook de vragen-stap: zelfde script met `parameters={}` —
verwacht `result.missing_required == True`.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/poc-machine-law
git add laws/omgevingswet/energiebesparing/maatregelen/RVO-2024-01-01.yaml
git commit -m "feat(laws): EML 2023 maatregelbepaling (demo-subset, RVO)"
```

---

### Task 2: PR naar poc-machine-law

- [ ] **Step 1: Push en draft-PR**

```bash
cd ~/projects/poc-machine-law
git push -u origin feat/eml-maatregelen
gh pr create --draft --title "feat(laws): EML 2023 maatregelbepaling (demo-subset, RVO)" --body "$(cat <<'EOF'
Voegt de wet `omgevingswet/energiebesparing/maatregelen` toe: bepaling welke
EML 2023-maatregelen van toepassing zijn op basis van feitelijke
bedrijfskenmerken (parameters; de descriptions zijn letterlijk de vragen aan
de ondernemer). Demo-subset van 7 maatregelen (GC1, GC3, GF4, FD3, FD7, FE4,
GD1) met echte EML 2023 v1.3-codes en -namen.

Gebruikt door de MOZa Digitale Assistent (MinBZK/moza-poc-digitale-assistent)
voor de informatieplicht-demo op de Dag van de Toekomst (18 juni 2026); de
assistent leest de te stellen vragen af uit de parameter-descriptions.

Bekende beperking: per-maatregel boolean outputs schalen niet naar de
volledige EML (~150 maatregelen); daarvoor is een list/map-uitbreiding van de
engine nodig.
EOF
)"
```

Expected: PR-URL. Meld de URL aan de gebruiker (digilab-deploy vóór 18/6 is
spoor a; zie spec).

---

### Task 3: Failing tests voor de nieuwe tool-flow (deze repo)

**Files:**
- Create: `services/host/tests/test_eml_maatregelen.py`
- Modify: `services/host/tests/test_demo_personas.py:69-89` (de twee EML-tests)

- [ ] **Step 1: Nieuwe testfile schrijven**

Volledige inhoud `services/host/tests/test_eml_maatregelen.py`:

```python
"""EML-maatregelbepaling: twee-staps-flow, engine-mapping en fallback.

De regelrecht-server bepaalt EML-maatregelen via de poc-machine-law engine
(wet omgevingswet/energiebesparing/maatregelen) en valt terug op een lokale
evaluatie als de engine onbereikbaar is. Deze tests draaien zonder netwerk.
"""

import asyncio
import importlib.util
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"


def _load_regelrecht():
    pad = MCP_DIR / "regelrecht" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_regelrecht_server", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RULE_SPEC = {
    "properties": {
        "parameters": [
            {
                "name": "HEEFT_KOELINSTALLATIE",
                "description": "Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?",
            },
            {
                "name": "HEEFT_AFZUIGINSTALLATIE",
                "description": "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?",
            },
        ],
        "output": [
            {
                "name": "eml_gf4_van_toepassing",
                "description": "Gebouwen, Binnenverlichting — Vervang gloei-, halogeen- en spaarlampen door LED-lampen",
            },
            {
                "name": "eml_fd3_van_toepassing",
                "description": "Faciliteiten, Productkoeling — Pas nachtafdekking toe bij semi-verticale koelmeubels",
            },
        ],
    }
}

ENGINE_RESULT_COMPLEET = {
    "structuredContent": {
        "success": True,
        "requirements_met": True,
        "missing_required": False,
        "output": {
            "eml_gf4_van_toepassing": True,
            "eml_fd3_van_toepassing": False,
        },
        "rule_spec": RULE_SPEC,
    }
}

ENGINE_RESULT_FEITEN_ONTBREKEN = {
    "structuredContent": {
        "success": True,
        "requirements_met": False,
        "missing_required": True,
        "output": {},
        "rule_spec": RULE_SPEC,
    }
}


def test_eml_lijst_mapt_engine_outputs_naar_maatregelen():
    regelrecht = _load_regelrecht()
    lijst = regelrecht._eml_lijst(ENGINE_RESULT_COMPLEET["structuredContent"])
    per_code = {m["code"]: m for m in lijst}
    assert per_code["GF4"]["van_toepassing"] is True
    assert per_code["GF4"]["naam"] == (
        "Vervang gloei-, halogeen- en spaarlampen door LED-lampen"
    )
    assert per_code["GF4"]["categorie"] == "Gebouwen, Binnenverlichting"
    assert per_code["FD3"]["van_toepassing"] is False


def test_eml_vragen_uit_rule_spec_minus_geleverde_feiten():
    regelrecht = _load_regelrecht()
    vragen = regelrecht._eml_vragen(RULE_SPEC, {"HEEFT_KOELINSTALLATIE": True})
    assert vragen == [
        {
            "naam": "HEEFT_AFZUIGINSTALLATIE",
            "vraag": "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?",
        }
    ]


def test_maatregelen_zonder_feiten_geeft_vragen_uit_engine(monkeypatch):
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        assert params["arguments"]["law"] == regelrecht.EML_LAW
        return ENGINE_RESULT_FEITEN_ONTBREKEN

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(regelrecht._maatregelen({}))
    assert fallback is False
    namen = [v["naam"] for v in data["benodigde_feiten"]]
    assert namen == ["HEEFT_KOELINSTALLATIE", "HEEFT_AFZUIGINSTALLATIE"]


def test_maatregelen_met_feiten_geeft_lijst_uit_engine(monkeypatch):
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        assert params["arguments"]["parameters"] == {
            "HEEFT_KOELINSTALLATIE": True,
            "HEEFT_AFZUIGINSTALLATIE": False,
        }
        return ENGINE_RESULT_COMPLEET

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(
        regelrecht._maatregelen(
            {"feiten": {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": False}}
        )
    )
    assert fallback is False
    assert {m["code"] for m in data["maatregelen"]} == {"GF4", "FD3"}


def test_maatregelen_fallback_bij_onbereikbare_engine(monkeypatch):
    regelrecht = _load_regelrecht()

    async def kapot(method, params):
        raise regelrecht.httpx.ConnectError("engine offline")

    monkeypatch.setattr(regelrecht, "_rpc_call", kapot)

    # Stap 1: vragen komen dan uit de lokale fallback
    data, fallback = asyncio.run(regelrecht._maatregelen({}))
    assert fallback is True
    assert [v["naam"] for v in data["benodigde_feiten"]] == [
        "HEEFT_KOELINSTALLATIE",
        "HEEFT_AFZUIGINSTALLATIE",
    ]

    # Stap 2: lijst komt dan uit de lokale fallback (alle 7 subset-maatregelen)
    data, fallback = asyncio.run(
        regelrecht._maatregelen(
            {"feiten": {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": True}}
        )
    )
    assert fallback is True
    codes = {m["code"] for m in data["maatregelen"]}
    assert codes == {"GC1", "GC3", "GF4", "FD3", "FD7", "FE4", "GD1"}
    assert all(m["van_toepassing"] for m in data["maatregelen"])
```

- [ ] **Step 2: EML-tests in test_demo_personas.py vervangen**

Vervang de twee bestaande EML-tests (regels 69–89, functies
`test_eml_maatregelen_volgen_bedrijfskenmerken` en
`test_eml_alle_kenmerken_true_geeft_alle_maatregelen`) door:

```python
def test_eml_fallback_volgt_bedrijfskenmerken():
    regelrecht = _load("regelrecht")
    data = regelrecht._eml_fallback(
        {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": False}
    )
    per_code = {m["code"]: m["van_toepassing"] for m in data["maatregelen"]}
    # onvoorwaardelijke maatregelen gelden altijd
    assert per_code["GF4"] is True
    # koelinstallatie=True activeert de productkoeling-maatregelen
    assert per_code["FD3"] is True
    # afzuiginstallatie=False deactiveert de afzuig-/ventilatiemaatregelen
    assert per_code["FE4"] is False


def test_eml_fallback_zonder_feiten_geeft_de_twee_vragen():
    regelrecht = _load("regelrecht")
    data = regelrecht._eml_fallback({})
    assert [v["naam"] for v in data["benodigde_feiten"]] == [
        "HEEFT_KOELINSTALLATIE",
        "HEEFT_AFZUIGINSTALLATIE",
    ]
```

- [ ] **Step 3: Tests draaien — moeten falen**

```bash
uv run pytest services/host/tests/test_eml_maatregelen.py services/host/tests/test_demo_personas.py -v
```

Expected: FAIL met `AttributeError` (o.a. `_eml_lijst`, `_eml_vragen`,
`_eml_fallback`, `EML_LAW` bestaan nog niet).

---

### Task 4: Server-implementatie

**Files:**
- Modify: `services/mcp/regelrecht/server.py` (EML-mockblok regels 49–107, tooldefinitie `maatregelen` regels 311–357, dispatcher regel 374–375, handler `_maatregelen` regels 380–438)

- [ ] **Step 1: EML-datablok vervangen**

Vervang het blok `EML_SOURCE_LABEL` + `EML_HORECA` + `_geldende_maatregelen`
(regels 59–107) door:

```python
EML_SOURCE_LABEL = "RegelRecht — EML-maatregelbepaling (lokale fallback)"
EML_LAW = "omgevingswet/energiebesparing/maatregelen"

# Lokale fallback voor als de engine onbereikbaar is: zelfde demo-subset als
# de wet-YAML in poc-machine-law (EML 2023 v1.3). Vorm en inhoud moeten
# synchroon blijven met laws/omgevingswet/energiebesparing/maatregelen/.
EML_FALLBACK_VRAGEN = [
    {
        "naam": "HEEFT_KOELINSTALLATIE",
        "vraag": "Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?",
    },
    {
        "naam": "HEEFT_AFZUIGINSTALLATIE",
        "vraag": "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?",
    },
]

EML_FALLBACK_MAATREGELEN = [
    {"code": "GC1", "naam": "Pas een klokregeling toe en regel deze in", "categorie": "Gebouwen, Ruimteverwarming", "voorwaarde": None},
    {"code": "GC3", "naam": "Pas een weersafhankelijke regeling toe", "categorie": "Gebouwen, Ruimteverwarming", "voorwaarde": None},
    {"code": "GF4", "naam": "Vervang gloei-, halogeen- en spaarlampen door LED-lampen", "categorie": "Gebouwen, Binnenverlichting", "voorwaarde": None},
    {"code": "FD3", "naam": "Pas nachtafdekking toe bij semi-verticale koelmeubels", "categorie": "Faciliteiten, Productkoeling", "voorwaarde": "HEEFT_KOELINSTALLATIE"},
    {"code": "FD7", "naam": "Isoleer de wanden van koelcellen om warmte buiten te houden", "categorie": "Faciliteiten, Productkoeling", "voorwaarde": "HEEFT_KOELINSTALLATIE"},
    {"code": "FE4", "naam": "Pas een laagdebiet afzuigkap toe bij grootkeukens", "categorie": "Faciliteiten, Grootkeukenapparatuur", "voorwaarde": "HEEFT_AFZUIGINSTALLATIE"},
    {"code": "GD1", "naam": "Pas een klokregeling toe op het ventilatiesysteem", "categorie": "Gebouwen, Ruimteventilatie", "voorwaarde": "HEEFT_AFZUIGINSTALLATIE"},
]


def _eml_fallback(feiten: dict) -> dict:
    """Lokale evaluatie van de demo-subset (zelfde flow als de engine)."""
    onbeantwoord = [v for v in EML_FALLBACK_VRAGEN if v["naam"] not in feiten]
    if onbeantwoord:
        return {"benodigde_feiten": onbeantwoord}
    return {
        "maatregelen": [
            {
                "code": m["code"],
                "naam": m["naam"],
                "categorie": m["categorie"],
                "van_toepassing": (
                    m["voorwaarde"] is None or bool(feiten.get(m["voorwaarde"]))
                ),
            }
            for m in EML_FALLBACK_MAATREGELEN
        ],
        "feiten": feiten,
    }


def _eml_vragen(rule_spec: dict, feiten: dict) -> list[dict]:
    """Lees de nog te stellen feitelijke vragen af uit de wet-spec."""
    params = rule_spec.get("properties", {}).get("parameters", [])
    return [
        {"naam": p["name"], "vraag": p.get("description", p["name"])}
        for p in params
        if p.get("name") and p["name"] not in feiten
    ]


def _eml_lijst(structured: dict) -> list[dict]:
    """Map engine-outputs (eml_<code>_van_toepassing) naar de maatregelenlijst.

    Naam en categorie komen uit de output-descriptions in de wet-spec
    ("<categorie> — <naam>"); alle regelkennis zit dus in de engine.
    """
    beschrijvingen = {
        o["name"]: o.get("description", "")
        for o in structured.get("rule_spec", {})
        .get("properties", {})
        .get("output", [])
        if o.get("name")
    }
    lijst = []
    for naam, waarde in structured.get("output", {}).items():
        if not (naam.startswith("eml_") and naam.endswith("_van_toepassing")):
            continue
        code = naam[len("eml_") : -len("_van_toepassing")].upper()
        beschrijving = beschrijvingen.get(naam, "")
        categorie, scheider, titel = beschrijving.partition(" — ")
        lijst.append(
            {
                "code": code,
                "naam": titel if scheider else beschrijving,
                "categorie": categorie if scheider else "",
                "van_toepassing": bool(waarde),
            }
        )
    return lijst
```

- [ ] **Step 2: Tooldefinitie `maatregelen` vervangen**

Vervang de `Tool(name="maatregelen", ...)`-definitie (regels 311–357) door:

```python
        Tool(
            name="maatregelen",
            description=(
                "Bepaal welke maatregelen uit de Erkende Maatregelenlijst "
                "(EML 2023) voor het bedrijf gelden. Roep EERST aan zónder "
                "feiten: de tool meldt dan welke feitelijke vragen aan de "
                "ondernemer gesteld moeten worden (benodigde_feiten). Stel "
                "die vragen letterlijk — de feiten staan nergens "
                "geregistreerd en blijven bewust bij de ondernemer — en roep "
                "daarna opnieuw aan met de antwoorden in 'feiten'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "feiten": {
                        "type": "object",
                        "description": (
                            "Antwoorden op de gemelde feitelijke vragen "
                            "(naam → true/false). Weglaten bij de eerste "
                            "aanroep."
                        ),
                        "additionalProperties": {"type": "boolean"},
                    },
                },
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=True,
            ),
        ),
```

(NB: `openWorldHint` gaat van `False` naar `True` — de tool praat nu met de
externe engine.)

- [ ] **Step 3: Handler vervangen**

Vervang `_maatregelen` (regels 380–438, de hele functie) door, en pas de
dispatcher aan:

```python
async def _maatregelen(arguments: dict) -> tuple[dict, bool]:
    """Bepaal EML-maatregelen via de engine; lokale fallback bij storing.

    Geeft (data, fallback_gebruikt) terug zodat de caller het juiste
    provenance-label kan kiezen.
    """
    feiten = {
        str(k): bool(v) for k, v in (arguments.get("feiten") or {}).items()
    }
    try:
        result = await _rpc_call(
            "tools/call",
            {
                "name": "execute_law",
                "arguments": {
                    "service": "RVO",
                    "law": EML_LAW,
                    "parameters": feiten,
                },
            },
        )
        structured = (result or {}).get("structuredContent") or {}
        if not structured.get("success"):
            raise RuntimeError("engine-response zonder structuredContent")
    except (httpx.HTTPError, RuntimeError) as e:
        logger.warning("EML via engine mislukt, lokale fallback: %s", e)
        return _eml_fallback(feiten), True

    if structured.get("missing_required"):
        vragen = _eml_vragen(structured.get("rule_spec", {}), feiten)
        if not vragen:
            # Spec onbruikbaar om vragen uit af te leiden — fallback weet ze.
            return _eml_fallback(feiten), True
        return {"benodigde_feiten": vragen}, False

    lijst = _eml_lijst(structured)
    if not lijst:
        logger.warning("EML-engine-response zonder eml_-outputs, fallback")
        return _eml_fallback(feiten), True
    return {"maatregelen": lijst, "feiten": feiten}, False
```

In de dispatcher (`call_tool`) het bestaande blok

```python
    if name == "maatregelen":
        return _maatregelen(arguments)
```

vervangen door:

```python
    if name == "maatregelen":
        data, fallback = await _maatregelen(arguments)
        _audit_log("maatregelen", arguments, data)
        tekst = _wrap_eml_provenance(data) if fallback else _wrap_provenance(data)
        return [TextContent(type="text", text=tekst)]
```

`httpx.ConnectError` is een subklasse van `httpx.HTTPError` — de testcase
uit Task 3 valt onder de bestaande except. De docstring-kop van het bestand
(regels 49–57, het commentaarblok "Lokale regelevaluatie") bijwerken:
EML-bepaling loopt nu via de engine; het lokale blok is alleen fallback.

- [ ] **Step 4: Tests draaien — moeten slagen**

```bash
uv run pytest services/host/tests/ -v
```

Expected: alle tests PASS (ook de niet-EML-tests: Donald/Noon-invarianten
raken dit niet).

- [ ] **Step 5: Lint en commit**

```bash
uv run ruff check . && git add -A services/mcp/regelrecht services/host/tests && git commit -m "feat(regelrecht): EML-maatregelen via poc-machine-law engine

Twee-staps-flow: eerste aanroep meldt de te stellen feitelijke vragen
(afgelezen uit de wet-spec), tweede aanroep evalueert. Lokale mock blijft
als fallback met eigen provenance-label."
```

---

### Task 5: Prompts bijwerken (vragen niet meer hardcoded)

**Files:**
- Modify: `services/host/prompts/blocks/shared/tool_usage.md:38`
- Modify: `services/host/prompts/examples/informatieplicht_flow.md:19-36`

- [ ] **Step 1: tool_usage.md**

Vervang regel 38 (de `-> Bepaal vóór het indienen ...`-regel) door:

```markdown
-> Bepaal vóór het indienen welke maatregelen gelden via regelrecht__maatregelen. Roep de tool EERST aan zonder feiten: de respons (benodigde_feiten) meldt welke feitelijke vragen u aan de gebruiker moet stellen. Stel die vragen LETTERLIJK en leg uit waarom: dit zijn feiten die nergens geregistreerd staan en bewust bij de ondernemer blijven — alleen feiten, geen regelinterpretatie. Vermeld dat de antwoorden worden bewaard voor de volgende rapportageronde. Roep daarna de tool opnieuw aan met de antwoorden in 'feiten'.
```

Werk regel 41 en 63 bij: vervang `(koelinstallatie, afzuiginstallatie)` door
`(de feiten uit de maatregelen-flow)` op regel 41, en op regel 63
`Bedrijfskenmerken zoals koelinstallatie/afzuiginstallatie` door
`Bedrijfskenmerken (de feitelijke antwoorden uit de maatregelen-flow)`.

- [ ] **Step 2: informatieplicht_flow.md**

Vervang regels 19–36 door:

```markdown
U hoeft dus niets op te zoeken. Om te bepalen wélke maatregelen voor uw zaak gelden, heb ik nog twee feitelijke vragen. Deze staan nergens geregistreerd — alleen u weet dit; het blijft een feit dat u aanlevert, geen juridische beoordeling. Uw antwoorden worden bewaard voor de volgende rapportageronde.

1. Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?
2. Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?"

(De assistent heeft deze vragen afgelezen uit regelrecht__maatregelen, dat
zonder feiten aangeroepen de benodigde_feiten meldt — de vraagteksten komen
uit de machine-uitvoerbare regel zelf.)

Gebruiker: "Ja allebei."

Assistent (na regelrecht__maatregelen met feiten={"HEEFT_KOELINSTALLATIE": true, "HEEFT_AFZUIGINSTALLATIE": true}):

"Dank u. Op basis van de Erkende Maatregelenlijst (EML 2023) gelden voor Koffiezaak Noon 7 maatregelen. Kunt u per maatregel aangeven of deze is uitgevoerd?

1. GC1 — Pas een klokregeling toe en regel deze in (ruimteverwarming) — uitgevoerd / niet uitgevoerd?
2. GC3 — Pas een weersafhankelijke regeling toe — uitgevoerd / niet uitgevoerd?
3. GF4 — Vervang gloei-, halogeen- en spaarlampen door LED-lampen — uitgevoerd / niet uitgevoerd?
4. FD3 — Pas nachtafdekking toe bij semi-verticale koelmeubels — uitgevoerd / niet uitgevoerd?
5. FD7 — Isoleer de wanden van koelcellen — uitgevoerd / niet uitgevoerd?
6. FE4 — Pas een laagdebiet afzuigkap toe bij grootkeukens — uitgevoerd / niet uitgevoerd?
7. GD1 — Pas een klokregeling toe op het ventilatiesysteem — uitgevoerd / niet uitgevoerd?"
```

- [ ] **Step 3: Smoke-test en commit**

```bash
uv run pytest && git add services/host/prompts && git commit -m "feat(prompts): EML-vragen aflezen uit regelrecht__maatregelen

De feitelijke vragen staan niet meer hardcoded in de prompt; de tool meldt
ze (benodigde_feiten) vanuit de wet-spec in de engine."
```

Expected: alle tests PASS.

---

### Task 6: PDR-007 addendum

**Files:**
- Modify: `docs/decisions/PDR-007-demo-persona-en-netbeheerder-bron.md` (§3)

- [ ] **Step 1: Addendum toevoegen**

Voeg direct onder de bestaande §3-tekst toe:

```markdown
**Addendum (2026-06-11):** de vervolgstap is uitgevoerd — de EML-bepaling
draait nu als wet `omgevingswet/energiebesparing/maatregelen` in de
poc-machine-law engine (zie
`docs/superpowers/specs/2026-06-11-eml-naar-engine-design.md`). Daarbij is
de structuur gemoderniseerd naar de EML 2023 (één lijst, onderdelen
Gebouwen/Faciliteiten/Processen, echte maatregelcodes; het
bedrijfstak-model en de `sbi_code`-parameter zijn vervallen) en worden de
feitelijke vragen niet meer hardcoded gesteld maar door de assistent
afgelezen uit de wet-spec (parameter-descriptions). De lokale mock blijft
als fallback met eigen provenance-label. Bekende beperking voor de echte
bouw: per-maatregel boolean outputs schalen niet naar de volledige EML
(~150 maatregelen) — daarvoor is een list/map-uitbreiding van de engine
nodig.
```

- [ ] **Step 2: Commit**

```bash
git add docs/decisions/PDR-007-demo-persona-en-netbeheerder-bron.md
git commit -m "docs: PDR-007-addendum — EML-bepaling naar de engine"
```

---

### Task 7: Integratiescript (handmatig, tegen echte engine)

**Files:**
- Create: `services/host/scripts/check_eml_engine.py`

- [ ] **Step 1: Script schrijven**

Volledige inhoud:

```python
"""Handmatige integratiecheck: EML-maatregelen via de echte engine.

Draait de twee-staps-flow tegen REGELRECHT_RPC_URL (default: digilab).
Vereist netwerktoegang; geen API-keys nodig.

    uv run python services/host/scripts/check_eml_engine.py
"""

import asyncio
import json
import os

import httpx

RPC_URL = os.getenv(
    "REGELRECHT_RPC_URL",
    "https://ui.lac.apps.digilab.network/mcp/rpc",
)
LAW = "omgevingswet/energiebesparing/maatregelen"


async def _execute_law(client: httpx.AsyncClient, parameters: dict) -> dict:
    response = await client.post(
        RPC_URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "execute_law",
                "arguments": {
                    "service": "RVO",
                    "law": LAW,
                    "parameters": parameters,
                },
            },
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise SystemExit(f"RPC-fout: {data['error']}")
    return data["result"].get("structuredContent", {})


async def main() -> None:
    async with httpx.AsyncClient() as client:
        # Stap 1: zonder feiten — engine moet melden wat er ontbreekt
        stap1 = await _execute_law(client, {})
        print("— Stap 1 (zonder feiten) —")
        print("missing_required:", stap1.get("missing_required"))
        params = (
            stap1.get("rule_spec", {}).get("properties", {}).get("parameters", [])
        )
        for p in params:
            print(f"  vraag: {p.get('name')}: {p.get('description')}")
        assert stap1.get("missing_required") is True, "verwacht: feiten ontbreken"

        # Stap 2: met feiten (Noon: koeling én afzuiging)
        stap2 = await _execute_law(
            client,
            {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": True},
        )
        print("— Stap 2 (met feiten) —")
        outputs = stap2.get("output", {})
        print(json.dumps(outputs, indent=2, ensure_ascii=False))
        eml = {k: v for k, v in outputs.items() if k.startswith("eml_")}
        assert len(eml) == 7, f"verwacht 7 maatregelen, kreeg {len(eml)}"
        assert all(eml.values()), "Noon (koeling+afzuiging): alles van toepassing"
        print("OK — engine bepaalt de EML-maatregelen")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Draaien (verwacht falen zolang de wet niet gedeployd is)**

```bash
uv run python services/host/scripts/check_eml_engine.py
```

Expected nu: RPC-fout (wet onbekend op digilab) — dat is informatief, niet
blokkerend. Tegen een lokaal draaiende engine
(`REGELRECHT_RPC_URL=http://localhost:8000/mcp/rpc`, engine gestart vanuit
`~/projects/poc-machine-law` met de nieuwe wet): expected `OK`.

- [ ] **Step 3: Commit**

```bash
git add services/host/scripts/check_eml_engine.py
git commit -m "test: integratiecheck EML-maatregelen tegen de echte engine"
```

---

### Task 8: Eindcontrole en PR

- [ ] **Step 1: Volledige suite + lint**

```bash
uv run pytest && uv run ruff check .
```

Expected: alles groen.

- [ ] **Step 2: Push en draft-PR**

```bash
git push -u origin feat/eml-naar-engine
gh pr create --draft --base feat/improve-demo --title "feat(regelrecht): EML-maatregelbepaling via poc-machine-law engine" --body "$(cat <<'EOF'
## Samenvatting / Summary

De EML-maatregelbepaling draait niet langer als lokale mock maar als
machine-uitvoerbare wet in de poc-machine-law engine
(`omgevingswet/energiebesparing/maatregelen`, zie PR <LINK NAAR
POC-MACHINE-LAW-PR UIT TASK 2>). Design:
`docs/superpowers/specs/2026-06-11-eml-naar-engine-design.md`.

## Wijzigingen / Changes

- `regelrecht__maatregelen` is een twee-staps-engine-proxy: eerste aanroep
  meldt de te stellen feitelijke vragen (afgelezen uit de wet-spec), tweede
  aanroep evalueert. `sbi_code` vervalt; EML 2023-structuur (één lijst,
  echte maatregelcodes GC1/GC3/GF4/FD3/FD7/FE4/GD1).
- Lokale mock blijft als fallback bij een onbereikbare engine, met eigen
  provenance-label — de demo kan hier niet door stuk.
- Prompts: feitelijke vragen niet meer hardcoded; patroon-instructie.
- PDR-007-addendum + integratiescript `check_eml_engine.py`.

## Deploy

Wet moet op `ui.lac.apps.digilab.network` landen vóór 18/6 (spoor a) of de
engine draait lokaal via `REGELRECHT_RPC_URL` (spoor b); de fallback dekt
het gat.
EOF
)"
```

Vervang `<LINK NAAR POC-MACHINE-LAW-PR UIT TASK 2>` door de echte PR-URL.
Base is `feat/improve-demo` zolang PR #26 open staat; na merge van #26 de
base naar `main` omzetten (`gh pr edit --base main`).

- [ ] **Step 3: Restpunten melden aan de gebruiker**

- Digilab-deploy van poc-machine-law vóór 18/6 (spoor a) of lokaal draaien
  (spoor b) — fallback dekt het gat.
- `uv.lock`-wijziging is er niet (geen nieuwe dependencies).

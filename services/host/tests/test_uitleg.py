"""Uitleg in gewone taal uit een beslisgraaf (PDR-016).

Drie lagen: de graaf naar regels, de toets van een modeltekst tegen de graaf,
en het endpoint `/uitleg` met dezelfde sessie- en sleutelregels als `/chat`.
Draait netwerkloos: het model wordt vervangen door een recorder.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402
import uitleg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from config import MAX_VRAAG_TEKENS  # noqa: E402

client = TestClient(api.app)
KVK = "85234567"
HEADERS = {"X-Test-User": KVK}

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "uitleg_graaf_lks.json").read_text()
)
RECHT = FIXTURE["heeft_recht_op_lks"]
BEDRAG = FIXTURE["hoogte_lks_eurocent_per_maand"]


# --- graaf -> regels -----------------------------------------------------------


def test_graaf_regels_begint_met_de_uitkomst_en_noemt_de_grond():
    regels = uitleg.graaf_regels(RECHT["graaf"])
    assert regels[0] == "- uitkomst: heeft_recht_op_lks = ja [grond: participatiewet art. 10d]"
    # Diepte-eerst: de kinderen springen in.
    assert regels[1].startswith("  - voorwaarde: AND = ja")


def test_graaf_regels_toont_eurocent_als_bedrag():
    regels = "\n".join(uitleg.graaf_regels(BEDRAG["graaf"]))
    assert "€ 897,41" in regels
    assert "89741" not in regels
    # Een gegeven zonder eenheid maar met "eurocent" in de naam is ook een bedrag.
    assert "hoogte_lks_voltijd_eurocent_per_maand = € 1.009,58" in regels
    assert "100958.4" not in regels


def test_graaf_regels_laat_tussenresultaten_van_operatoren_weg():
    """DIVIDE = 89740.8 zegt een lezer niets en nodigt het model uit tot een verzonnen getal."""
    regels = uitleg.graaf_regels(BEDRAG["graaf"])
    assert regels[1] == "  - berekening: DIVIDE"
    assert not any("89740.8" in r or "3230668.8" in r for r in regels)
    # De ja/nee van een keuze blijft: die zegt welke tak gold.
    assert any(r.strip() == "- keuze: CASE_0 = nee" for r in regels)


def test_graaf_regels_blijft_binnen_de_grenzen():
    diep = {"soort": "gegeven", "waarde": 1, "doorslaggevend": []}
    for _ in range(12):
        diep = {"soort": "voorwaarde", "waarde": True, "doorslaggevend": [diep]}
    assert len(uitleg.graaf_regels(diep)) == uitleg.MAX_DIEPTE + 1
    breed = {
        "soort": "uitkomst",
        "waarde": True,
        "doorslaggevend": [{"soort": "gegeven", "waarde": n} for n in range(200)],
    }
    assert len(uitleg.graaf_regels(breed)) == uitleg.MAX_REGELS


@pytest.mark.parametrize(
    "graaf",
    [None, "tekst", {}, {"soort": "uitkomst"}, {"soort": "x", "waarde": 1, "doorslaggevend": "nee"},
     {"soort": "x", "waarde": 1, "doorslaggevend": [{"waarde": 1}]}],
)
def test_graaf_geldig_weigert_wat_geen_graaf_is(graaf):
    assert uitleg.graaf_geldig(graaf) is False


def test_prompt_van_de_lks_graaf_past_binnen_de_vraaggrens():
    for geval in (RECHT, BEDRAG):
        prompt = uitleg.bouw_prompt(
            uitleg.graaf_regels(geval["graaf"]), "Loonkostensubsidie", geval["samenvatting"]
        )
        assert len(prompt) <= MAX_VRAAG_TEKENS
        assert "Beslisgraaf" in prompt


# --- toets ---------------------------------------------------------------------


def _regels_bedrag():
    return uitleg.graaf_regels(BEDRAG["graaf"])


def test_toets_slaagt_als_bedragen_en_artikel_uit_de_graaf_komen():
    tekst = (
        "U krijgt € 897,41 per maand. Dat is het minimumloon min de loonwaarde, "
        "naar 32 uur per week (artikel 10d Participatiewet)."
    )
    t = uitleg.toets(tekst, _regels_bedrag(), BEDRAG["samenvatting"])
    assert t.geslaagd is True
    assert t.onbekende_bedragen == []
    assert t.artikel_genoemd is True


def test_toets_betrapt_een_bedrag_dat_niet_in_de_graaf_staat():
    tekst = "U krijgt € 1.000,00 per maand (artikel 10d)."
    t = uitleg.toets(tekst, _regels_bedrag(), BEDRAG["samenvatting"])
    assert t.geslaagd is False
    assert t.onbekende_bedragen == ["€ 1.000,00"]
    assert any("bedrag" in o for o in t.opmerkingen)


def test_toets_betrapt_een_percentage_dat_niet_in_de_graaf_staat():
    tekst = "De loonwaarde is 70% (artikel 10d)."
    t = uitleg.toets(tekst, _regels_bedrag(), BEDRAG["samenvatting"])
    assert t.onbekende_percentages == ["70%"]
    assert t.geslaagd is False


def test_toets_betrapt_een_omgedraaide_rekenstap():
    """Gemeten op 20 oktober 2026: de graaf koos met MAX € 1.680,64 uit drie
    tegemoetkomingen, het model schreef "het laagste bedrag". Bedragen klopten."""
    graaf = {
        "soort": "uitkomst", "naam": "hoogte", "waarde": 168064, "eenheid": "eurocent",
        "grond": {"wet": "wtl", "artikel": "2.1"},
        "doorslaggevend": [{"soort": "berekening", "operator": "MAX", "waarde": 168064,
                            "doorslaggevend": [{"soort": "gegeven", "naam": "a_eurocent", "waarde": 168064},
                                               {"soort": "gegeven", "naam": "b_eurocent", "waarde": 0}]}],
    }
    regels = uitleg.graaf_regels(graaf)
    fout = uitleg.toets("Het laagste bedrag is € 1.680,64 (artikel 2.1).", regels)
    assert fout.geslaagd is False
    assert fout.omgedraaide_stappen == ["laagste"]
    goed = uitleg.toets("Het hoogste bedrag is € 1.680,64 (artikel 2.1).", regels)
    assert goed.geslaagd is True


def test_toets_kijkt_naar_de_buitenste_keuze_als_de_graaf_min_en_max_heeft():
    """De echte LKV-graaf: MAX bovenaan, een MIN dieper. "Laagste" gaat over de MAX."""
    regels = [
        "- uitkomst: hoogte = € 1.680,64 [grond: wtl art. 2.1]",
        "  - berekening: MAX",
        "    - gegeven: a_eurocent = € 1.680,64",
        "      - berekening: MIN",
    ]
    assert uitleg.toets("Het laagste bedrag is € 1.680,64 (artikel 2.1).", regels).geslaagd is False
    assert uitleg.toets("Het hoogste bedrag is € 1.680,64 (artikel 2.1).", regels).geslaagd is True


def test_toets_eist_het_wetsartikel_alleen_als_de_graaf_er_een_heeft():
    zonder_grond = [{"soort": "gegeven", "waarde": True}]
    regels = uitleg.graaf_regels(zonder_grond[0])
    assert uitleg.toets("Het geldt.", regels).geslaagd is True
    t = uitleg.toets("U krijgt € 897,41 per maand.", _regels_bedrag())
    assert t.artikel_genoemd is False
    assert t.geslaagd is False


@pytest.mark.parametrize(
    "bedrag, verwacht",
    [("€ 897,41", "897,41"), ("€897,4", "897,40"), ("€ 2.523,96", "2523,96"), ("€ 32", "32,00")],
)
def test_normaliseer_bedrag(bedrag, verwacht):
    assert uitleg._normaliseer_bedrag(bedrag) == verwacht


# --- verwoord met een nep-model ------------------------------------------------


class _NepClaude:
    """Een Anthropic-client die de prompt onthoudt en een vaste tekst teruggeeft."""

    api_key = "nep"

    def __init__(self, tekst: str):
        self.tekst = tekst
        self.ontvangen: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs):
        self.ontvangen.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=self.tekst)], usage=None)


def _met_nep_claude(monkeypatch, tekst: str) -> _NepClaude:
    from contextlib import asynccontextmanager

    nep = _NepClaude(tekst)

    @asynccontextmanager
    async def _clients(self, vlam_api_key_override="", claude_api_key_override="", mode=""):
        yield nep, None

    monkeypatch.setattr(type(api.host), "_request_clients", _clients)
    monkeypatch.setattr(api, "kvk_uit_header", lambda w: KVK if (w or "").strip() == KVK else None)
    return nep


@pytest.mark.asyncio
async def test_verwoord_stuurt_alleen_de_graaf_zonder_tools(monkeypatch):
    nep = _met_nep_claude(monkeypatch, "U krijgt € 897,41 per maand (artikel 10d).")
    resultaat = await uitleg.verwoord(
        api.host, graaf=BEDRAG["graaf"], regeling="Loonkostensubsidie",
        samenvatting=BEDRAG["samenvatting"], mode="claude",
    )
    assert isinstance(resultaat, uitleg.Uitleg)
    assert resultaat.toets.geslaagd is True
    (aanroep,) = nep.ontvangen
    assert "tools" not in aanroep
    assert aanroep["system"] == uitleg.SYSTEEMPROMPT
    assert aanroep["messages"][0]["content"].startswith('Regeling: "Loonkostensubsidie"')
    assert "€ 897,41" in aanroep["messages"][0]["content"]


@pytest.mark.asyncio
async def test_verwoord_te_grote_graaf_gaat_niet_naar_het_model(monkeypatch):
    nep = _met_nep_claude(monkeypatch, "x")
    # Lange namen maken de regels lang zonder de grens op het aantal te raken.
    graaf = {
        "soort": "uitkomst", "waarde": True,
        "doorslaggevend": [{"soort": "gegeven", "naam": "n" * 300, "waarde": n} for n in range(20)],
    }
    resultaat = await uitleg.verwoord(api.host, graaf=graaf, regeling="X", samenvatting=[])
    assert resultaat.code == "UITLEG_GRAAF_TE_GROOT"
    assert nep.ontvangen == []


# --- endpoint ------------------------------------------------------------------


def _body(**extra):
    return {
        "regeling": "Loonkostensubsidie",
        "graaf": BEDRAG["graaf"],
        "samenvatting": BEDRAG["samenvatting"],
        **extra,
    }


def test_uitleg_zonder_sessie_roept_het_model_niet_aan(monkeypatch):
    nep = _met_nep_claude(monkeypatch, "x")
    r = client.post("/uitleg", json=_body())
    assert r.status_code == 401
    assert nep.ontvangen == []


def test_uitleg_geeft_tekst_en_toets_terug(monkeypatch):
    _met_nep_claude(monkeypatch, "U krijgt € 897,41 per maand (artikel 10d).")
    r = client.post("/uitleg", json=_body(), headers=HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["tekst"].startswith("U krijgt")
    assert data["toets"]["geslaagd"] is True
    assert data["toets"]["bedragen_in_tekst"] == ["€ 897,41"]
    assert data["mode"] == "claude"
    assert data["regels"] > 5


def test_uitleg_markeert_een_verzonnen_bedrag_maar_geeft_de_tekst_wel(monkeypatch):
    _met_nep_claude(monkeypatch, "U krijgt € 950,00 per maand (artikel 10d).")
    r = client.post("/uitleg", json=_body(), headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["toets"]["geslaagd"] is False
    assert r.json()["toets"]["onbekende_bedragen"] == ["€ 950,00"]


@pytest.mark.parametrize("graaf", [{}, {"soort": "uitkomst"}, "tekst", [1]])
def test_uitleg_weigert_een_ongeldige_graaf(monkeypatch, graaf):
    nep = _met_nep_claude(monkeypatch, "x")
    r = client.post("/uitleg", json=_body(graaf=graaf), headers=HEADERS)
    assert r.status_code in (400, 422), r.text
    assert nep.ontvangen == []


def test_uitleg_zonder_regeling_wordt_geweigerd(monkeypatch):
    _met_nep_claude(monkeypatch, "x")
    r = client.post("/uitleg", json=_body(regeling="  "), headers=HEADERS)
    assert r.status_code == 400
    assert r.json()["code"] == "UITLEG_GRAAF_ONGELDIG"


def test_uitleg_leeg_antwoord_is_een_catalogusfout(monkeypatch):
    _met_nep_claude(monkeypatch, "   ")
    r = client.post("/uitleg", json=_body(), headers=HEADERS)
    assert r.status_code != 200
    assert r.json()["code"] == "LLM_LEEG_ANTWOORD"


def test_uitleg_zonder_sleutel_meldt_welke_sleutel(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _clients(self, vlam_api_key_override="", claude_api_key_override="", mode=""):
        yield SimpleNamespace(api_key=""), None

    monkeypatch.setattr(type(api.host), "_request_clients", _clients)
    monkeypatch.setattr(api, "kvk_uit_header", lambda w: KVK if (w or "").strip() == KVK else None)
    r = client.post("/uitleg", json=_body(), headers=HEADERS)
    assert r.status_code != 200
    assert r.json()["code"] in ("LLM_GEEN_SLEUTEL", "LLM_NIET_INGESTELD")

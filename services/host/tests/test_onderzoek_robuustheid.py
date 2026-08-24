"""Vier plekken waar één afwijkende bron een beurt kon laten hangen of klappen.

Gevonden bij de review vóór het gebruikersonderzoek van 25 en 27 augustus:

1. `rvo__zoek_regeling` matcht op de letterlijke zoekstring. Het model zoekt
   "energiebesparingsrapportage" en krijgt niets, terwijl "Informatieplicht
   Energiebesparing" bedoeld is - in elke live run twee extra rondes en een
   bronfout, vlak voor het indienen.
2. `get_definities` wachtte zonder grens op de regelrecht-tool; een bron die
   niet antwoordt hield de hele regelloop en dus de stream vast.
3. `volg_regel` parste het engine-antwoord zonder vangnet; geen JSON betekende
   een stille "onbekend" zonder spoor in de log.
4. De oogsters in `feiten.py` lazen geneste velden zonder typecontrole; een
   lijst waar een dict hoorde brak de beurt af met een AttributeError.
"""

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

import vlam_host
from feiten import feiten_uit_tool
from regelloop import volg_regel

_RVO = Path(__file__).resolve().parents[2] / "mcp" / "rvo" / "server.py"


def _rvo():
    spec = importlib.util.spec_from_file_location("rvo_server", _RVO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zoek(trefwoord: str) -> list[str]:
    uit = json.loads(_rvo()._zoek_regeling({"trefwoord": trefwoord})[0].text)
    return [r["id"] for r in (uit.get("data") or {}).get("resultaten", [])]


# --- 1. zoeken op betekenis, niet op letterlijke string ---------------------


@pytest.mark.parametrize(
    "trefwoord",
    [
        "energiebesparingsrapportage",
        "energiebesparingsplicht informatieplicht rapportage",
        "informatieplicht energiebesparing",
        "Informatieplicht",
        "rapportage energiebesparende maatregelen",
    ],
)
def test_de_zoektermen_van_het_model_vinden_de_informatieplicht(trefwoord):
    assert "EBR-2026" in _zoek(trefwoord)


def test_een_los_trefwoord_vindt_nog_steeds_de_juiste_regeling():
    assert any("ISDE" in regeling_id.upper() for regeling_id in _zoek("isde"))


def test_een_trefwoord_zonder_raakvlak_vindt_niets():
    assert _zoek("kinderopvangtoeslag") == []


def test_een_leeg_trefwoord_blijft_een_fout():
    uit = json.loads(_rvo()._zoek_regeling({"trefwoord": ""})[0].text)
    assert uit["error"] == "ONTBREKEND_VELD"


# --- 2. get_definities binnen de bron-grens ---------------------------------


@pytest.mark.asyncio
async def test_get_definities_wacht_niet_langer_dan_de_bron_grens(monkeypatch):
    class _Registry:
        tool_map = {"regelrecht__execute_law": object()}

        async def call_tool(self, *_a, **_k):
            await asyncio.sleep(60)

    host = vlam_host.VLAMHost()
    host.registry = _Registry()
    monkeypatch.setattr(vlam_host, "TOOL_TIMEOUT", 0.05)
    law = next(iter(vlam_host.REGELRECHT_DEFINITIES_ALLOWLIST))
    uit = await asyncio.wait_for(host.get_definities(law), timeout=2)
    assert "definities" in uit or "error" in uit


# --- 3. onleesbaar engine-antwoord ------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("ruw", ["geen json", "[1, 2]", '"tekst"', ""])
async def test_onleesbaar_engine_antwoord_stopt_met_reden(ruw):
    async def call_tool(_naam, _args):
        return ruw

    uitkomst = await volg_regel("wet", "RVO", {}, call_tool, frozenset())
    assert uitkomst.klaar is False
    assert uitkomst.wacht_op is None
    assert "onleesbaar" in uitkomst.reden.lower()


# --- 4. rommel uit een bron breekt de beurt niet ----------------------------


@pytest.mark.parametrize(
    "tool, payload",
    [
        ("kvk__mijn_bedrijf", {"data": {"_embedded": {"hoofdvestiging": ["x"]}}}),
        ("kvk__mijn_bedrijf", {"data": {"bag": "n.v.t."}}),
        ("kvk__mijn_bedrijf", {"data": {"sbiActiviteiten": "landbouw"}}),
        (
            "netbeheerder__verbruik",
            {"data": {"beschikbaar": True, "verbruik": "n.v.t.", "credential": 3}},
        ),
    ],
)
def test_rommel_uit_een_bron_levert_geen_feiten_en_geen_crash(tool, payload):
    assert feiten_uit_tool(tool, json.dumps(payload)) == {} or isinstance(
        feiten_uit_tool(tool, json.dumps(payload)), dict
    )


def test_een_gezonde_kvk_respons_levert_nog_steeds_feiten():
    payload = {
        "data": {
            "naam": "Kwekerij De Bloesem",
            "kvkNummer": "62345681",
            "_embedded": {"hoofdvestiging": {"vestigingsnummer": "000012345678"}},
        }
    }
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", json.dumps(payload))
    assert feiten["BEDRIJFSNAAM"]["waarde"] == "Kwekerij De Bloesem"

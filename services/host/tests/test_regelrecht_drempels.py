"""Drempelwaarden uit RegelRecht: engine-mapping + /regelrecht/definities-logica.

De drempel is autoritatief in de engine (rule_spec.definitions). _simplify_result
mapt die naar `drempelwaarden` in het tool-resultaat, en de host ontsluit ze via
get_definities (achter GET /regelrecht/definities, met allowlist + fallback).
Deze tests draaien zonder netwerk.
"""

import asyncio
import importlib.util
import types
from pathlib import Path

import vlam_host

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"
INFORMATIEPLICHT = "omgevingswet/energiebesparing/informatieplicht"


def _load_regelrecht():
    pad = MCP_DIR / "regelrecht" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_regelrecht_drempels", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_simplify_result_mapt_definitions_naar_drempelwaarden():
    """De engine-definitions belanden als drempelwaarden in het tool-resultaat."""
    rr = _load_regelrecht()
    structured = {
        "requirements_met": True,
        "output": {"heeft_informatieplicht": True},
        "rule_spec": {
            "properties": {
                "definitions": {
                    "DREMPEL_ELEKTRICITEIT_KWH": 50000,
                    "DREMPEL_GAS_M3": 25000,
                }
            }
        },
    }
    res = rr._simplify_result(structured)
    assert res["drempelwaarden"] == {
        "DREMPEL_ELEKTRICITEIT_KWH": 50000,
        "DREMPEL_GAS_M3": 25000,
    }


# --- host.get_definities zonder volledige host-constructie (fake self) ---


class _FakeRegistry:
    def __init__(self, tool_map, result=None):
        self.tool_map = tool_map
        self._result = result

    async def call_tool(self, tool_key, arguments):
        return self._result


def _get_definities(registry, law):
    fake_self = types.SimpleNamespace(registry=registry)
    return asyncio.run(vlam_host.VLAMHost.get_definities(fake_self, law))


def test_get_definities_uit_engine():
    raw = (
        '{"data": {"drempelwaarden": {"DREMPEL_ELEKTRICITEIT_KWH": 50000, '
        '"DREMPEL_GAS_M3": 25000}}, "provenance": {}}'
    )
    res = _get_definities(_FakeRegistry({"regelrecht__execute_law": True}, raw), INFORMATIEPLICHT)
    assert res["definities"]["DREMPEL_ELEKTRICITEIT_KWH"] == 50000
    assert "RegelRecht" in res["bron"]
    assert res["law"] == INFORMATIEPLICHT


def test_get_definities_fallback_zonder_tool():
    # regelrecht-tool niet verbonden -> lokale fallback voor de informatieplicht
    res = _get_definities(_FakeRegistry({}), INFORMATIEPLICHT)
    assert res["definities"]["DREMPEL_ELEKTRICITEIT_KWH"] == 50000
    assert "fallback" in res["bron"]


def test_get_definities_allowlist_weigert_onbekende_wet():
    res = _get_definities(
        _FakeRegistry({"regelrecht__execute_law": True}, "{}"), "zorgtoeslagwet"
    )
    assert res["error"] == "WET_NIET_TOEGESTAAN"


# --- Het filter op de constanten mag geen sluiproute hebben ------------------


def test_terugvalpad_filtert_de_bijlagen_ook_weg():
    """`_bruikbare_definities` bestaat om 255 maatregelen uit de respons te houden.

    Dat filter zat alleen op het pad via `_definities_voor`. In
    `_simplify_result` gold `drempels = definities or uit_respons`, en
    `uit_respons` komt ongefilterd uit de respons zelf. Valt de tweede RPC om,
    dan wint dat ongefilterde blok: beide bijlagen gaan als drempelwaarden naar
    het model en belanden als losse wetsconstante-feiten op de feitenkaart -
    precies wat het filter moest tegenhouden.
    """
    structured = {
        "rule_spec": {
            "properties": {
                "definitions": {
                    "CATEGORIEEN": [{"categorie": "Perslucht", "onderdeel": "Faciliteiten"}],
                    "MAATREGELEN_ALGEMEEN": [{"code": f"X{n}"} for n in range(255)],
                    "MAATREGELEN_GLASTUINBOUW": [{"code": f"G{n}"} for n in range(120)],
                }
            }
        },
        "requirements_met": True,
        "output": {},
    }
    rr = _load_regelrecht()
    resultaat = rr._simplify_result(structured, definities=None, law=rr.EML_LAW)
    drempels = resultaat.get("drempelwaarden", {})
    assert "CATEGORIEEN" in drempels
    assert "MAATREGELEN_ALGEMEEN" not in drempels
    assert "MAATREGELEN_GLASTUINBOUW" not in drempels


def test_een_wet_zonder_filter_houdt_al_zijn_constanten():
    """De tegenproef: alleen de maatregelenwet wordt beperkt.

    De informatieplicht levert drempelwaarden die de assistent juist nodig
    heeft; die mogen niet meesneuvelen.
    """
    structured = {
        "rule_spec": {
            "properties": {"definitions": {"DREMPEL_ELEKTRICITEIT_KWH": 50000}}
        },
        "requirements_met": True,
        "output": {},
    }
    rr = _load_regelrecht()
    resultaat = rr._simplify_result(structured, definities=None, law=INFORMATIEPLICHT)
    assert resultaat["drempelwaarden"] == {"DREMPEL_ELEKTRICITEIT_KWH": 50000}


def test_een_lege_ophaal_wordt_niet_gecachet():
    """Anders legt één hik de drempelwaarden voor de rest van het proces plat.

    De cache is procesbreed en kent geen invalidatie. Een RPC die technisch
    slaagt maar niets bruikbaars draagt - geen `structuredContent` - zette een
    leeg resultaat vast. Vanaf dat moment kreeg elke toets in dit proces geen
    drempelwaarden meer, en meldde de host "RegelRecht niet beschikbaar" terwijl
    de engine draaide.
    """
    rr = _load_regelrecht()
    rr._definities_cache.clear()
    beurten = iter([{}, {"structuredContent": {"rule_spec": {"properties": {"definitions": {"DREMPEL_GAS_M3": 25000}}}}}])

    async def _nep_rpc(methode, params):
        return next(beurten)

    rr._rpc_call = _nep_rpc
    leeg = asyncio.run(rr._definities_voor(INFORMATIEPLICHT, "RVO"))
    assert leeg == {}
    assert not rr._definities_cache, "een leeg resultaat is vastgelegd"

    # Tweede poging: de engine antwoordt nu wel, en dat hoort door te komen.
    tweede = asyncio.run(rr._definities_voor(INFORMATIEPLICHT, "RVO"))
    assert tweede == {"DREMPEL_GAS_M3": 25000}
    assert rr._definities_cache, "een geslaagde ophaal hoort juist wel gecachet te worden"

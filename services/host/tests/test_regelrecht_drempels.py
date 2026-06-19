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


def _get_definities(registry, law, service=None):
    fake_self = types.SimpleNamespace(registry=registry)
    return asyncio.run(vlam_host.VLAMHost.get_definities(fake_self, law, service))


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
        _FakeRegistry({"regelrecht__execute_law": True}, "{}"), "zorgtoeslagwet", "TOESLAGEN"
    )
    assert res["error"] == "WET_NIET_TOEGESTAAN"

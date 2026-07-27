"""Sessie-identiteit: host injecteert het KvK-nummer server-side (MVP-01, PDR-009).

Het KvK-nummer van de sessie wordt bij elke bron-aanroep geinjecteerd en
overschrijft wat het LLM invulde. Aanvullend is `kvk_nummer` uit de
LLM-zichtbare tool-schema's gehaald zodat het model het niet eens kan meegeven.
"""

import vlam_host
from mcp_client import _strip_kvk_param

SESSIE_KVK = "85234567"
ANDER_KVK = "68750110"

_INFORMATIEPLICHT = "omgevingswet/energiebesparing/informatieplicht"
_MAATREGELEN = "omgevingswet/energiebesparing/maatregelen"


def test_kvk_tools_krijgen_sessie_kvk_geinjecteerd():
    for tool in ("kvk__mijn_bedrijf", "kvk__vestigingen", "kvk__eigenaar"):
        out = vlam_host._inject_session_kvk(tool, {}, SESSIE_KVK)
        assert out["kvk_nummer"] == SESSIE_KVK


def test_regelrecht_check_kvk_wordt_overschreven():
    out = vlam_host._inject_session_kvk(
        "regelrecht__check", {"kvk_nummer": ANDER_KVK}, SESSIE_KVK
    )
    assert out["kvk_nummer"] == SESSIE_KVK


def test_rvo_indienen_kvk_wordt_overschreven():
    out = vlam_host._inject_session_kvk(
        "rvo__indienen",
        {"kvk_nummer": ANDER_KVK, "regeling_id": "EBR-2026", "maatregelen": ["x"]},
        SESSIE_KVK,
    )
    assert out["kvk_nummer"] == SESSIE_KVK
    # Overige argumenten blijven ongemoeid.
    assert out["regeling_id"] == "EBR-2026"
    assert out["maatregelen"] == ["x"]


def test_execute_law_informatieplicht_overschrijft_kvk_in_parameters():
    out = vlam_host._inject_session_kvk(
        "regelrecht__execute_law",
        {"law": _INFORMATIEPLICHT, "parameters": {"KVK_NUMMER": ANDER_KVK}},
        SESSIE_KVK,
    )
    assert out["parameters"]["KVK_NUMMER"] == SESSIE_KVK


def test_execute_law_maatregelen_krijgt_geen_kvk_injectie():
    # De maatregelen-regel gebruikt parameters als feiten; geen KvK erin prakken.
    feiten = {"HEEFT_KOELINSTALLATIE": True}
    out = vlam_host._inject_session_kvk(
        "regelrecht__execute_law",
        {"law": _MAATREGELEN, "parameters": dict(feiten)},
        SESSIE_KVK,
    )
    assert "KVK_NUMMER" not in out["parameters"]
    assert out["parameters"] == feiten


def test_injectie_muteert_de_input_niet():
    original = {"kvk_nummer": ANDER_KVK}
    vlam_host._inject_session_kvk("regelrecht__check", original, SESSIE_KVK)
    assert original == {"kvk_nummer": ANDER_KVK}


def test_niet_kvk_tools_blijven_ongemoeid():
    args = {"trefwoord": "energie"}
    out = vlam_host._inject_session_kvk("koop__zoek_regelgeving", args, SESSIE_KVK)
    assert out == args
    assert "kvk_nummer" not in out


def test_cli_defs_tonen_geen_kvk_nummer_aan_llm():
    # Het LLM mag de parameter niet eens kunnen meegeven (PDR-009 besluit 3).
    for tool in vlam_host.CLI_TOOL_DEFINITIONS_ANTHROPIC:
        props = tool["input_schema"].get("properties", {})
        assert "kvk_nummer" not in props, tool["name"]
        assert "kvk_nummer" not in tool["input_schema"].get("required", []), tool["name"]


class _RecordingRegistry:
    """Registry-stub die de argumenten van de laatste tool-call onthoudt."""

    def __init__(self):
        self.calls = []

    async def call_tool(self, tool_key, arguments):
        self.calls.append((tool_key, arguments))
        return "{}"


class _FakeToolUse:
    def __init__(self, name, input, id="t1"):
        self.name = name
        self.input = input
        self.id = id


async def test_execute_tools_injecteert_sessie_kvk():
    host = vlam_host.VLAMHost()
    host.registry = _RecordingRegistry()
    await host._execute_tools(
        [_FakeToolUse("regelrecht__check", {"kvk_nummer": ANDER_KVK})], SESSIE_KVK
    )
    tool_key, arguments = host.registry.calls[0]
    assert tool_key == "regelrecht__check"
    assert arguments["kvk_nummer"] == SESSIE_KVK


def test_strip_kvk_param_verwijdert_property_en_required():
    schema = {
        "type": "object",
        "properties": {
            "kvk_nummer": {"type": "string"},
            "regeling_id": {"type": "string"},
        },
        "required": ["kvk_nummer", "regeling_id"],
    }
    stripped = _strip_kvk_param(schema)
    assert "kvk_nummer" not in stripped["properties"]
    assert stripped["required"] == ["regeling_id"]
    # Origineel blijft ongemoeid (gedeelde tool.inputSchema niet muteren).
    assert "kvk_nummer" in schema["properties"]

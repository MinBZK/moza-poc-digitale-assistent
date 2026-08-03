"""Elke tool die `kvk_nummer` vraagt, moet het ook geïnjecteerd krijgen.

MVP-01/PDR-009 knipt `kvk_nummer` uit *alle* LLM-zichtbare tool-schema's
(`mcp_client._strip_kvk_param`), maar injecteert het alleen terug voor de tools
in `vlam_host._KVK_SESSIE_TOOLS`. Staat een tool wel in de strip maar niet in de
injectie, dan krijgt de bronserver een lege `kvk_nummer` en faalt de aanroep
stilzwijgend — precies wat er met `netbeheerder__verbruik` gebeurde.

Deze test leest de echte tool-definities uit de MCP-servers, zodat een nieuwe
tool met een `kvk_nummer`-parameter niet ongemerkt buiten de injectie valt.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parent.parent.parent
MCP_DIR = SERVICES / "mcp"
SERVERS = ["kvk", "koop", "regelrecht", "rvo", "netbeheerder"]


def _load_mcp_server(naam: str):
    pad = MCP_DIR / naam / "server.py"
    spec = importlib.util.spec_from_file_location(f"mcp_{naam}_server_dekking", pad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _vraagt_kvk_nummer(tool) -> bool:
    schema = getattr(tool, "inputSchema", None) or {}
    props = schema.get("properties") or {}
    return "kvk_nummer" in props


async def _tools_met_kvk_parameter() -> set[str]:
    gevonden: set[str] = set()
    for naam in SERVERS:
        srv = _load_mcp_server(naam)
        for tool in await srv.list_tools():
            if _vraagt_kvk_nummer(tool):
                gevonden.add(f"{naam}__{tool.name}")
    return gevonden


@pytest.fixture(scope="module")
def vlam_host():
    sys.path.insert(0, str(SERVICES / "host"))
    import vlam_host as mod

    return mod


async def test_elke_tool_met_kvk_parameter_krijgt_injectie(vlam_host):
    tools = await _tools_met_kvk_parameter()
    assert tools, "geen enkele tool met kvk_nummer gevonden — test is stuk"
    ontbrekend = tools - set(vlam_host._KVK_SESSIE_TOOLS)
    assert not ontbrekend, (
        f"deze tools vragen kvk_nummer maar krijgen het niet geïnjecteerd: "
        f"{sorted(ontbrekend)}"
    )


async def test_injectie_levert_daadwerkelijk_een_kvk_nummer(vlam_host):
    # Niet alleen lidmaatschap van de set: de injectie moet ook echt vullen.
    for tool_key in sorted(await _tools_met_kvk_parameter()):
        args = vlam_host._inject_session_kvk(tool_key, {}, "85234567")
        assert args.get("kvk_nummer") == "85234567", tool_key


async def test_netbeheerder_verbruik_is_gedekt(vlam_host):
    # Regressie: deze tool viel buiten de injectie, waardoor de
    # informatieplicht-flow (PDR-007) altijd op ontbrekend verbruik strandde.
    assert "netbeheerder__verbruik" in vlam_host._KVK_SESSIE_TOOLS
    args = vlam_host._inject_session_kvk("netbeheerder__verbruik", {}, "62345681")
    assert args["kvk_nummer"] == "62345681"


async def test_sessie_kvk_wint_van_wat_het_llm_meegeeft(vlam_host):
    args = vlam_host._inject_session_kvk(
        "netbeheerder__verbruik", {"kvk_nummer": "99999999"}, "56789012"
    )
    assert args["kvk_nummer"] == "56789012"

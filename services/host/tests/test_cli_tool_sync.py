"""Guard: CLI-tooldefinities moeten synchroon blijven met cli_executor.

`CLI_TOOL_DEFINITIONS_ANTHROPIC` in `vlam_host.py` (wat het LLM ziet) en de
`tool_key`-afhandeling in `cli_executor.py` (wat daadwerkelijk wordt uitgevoerd)
worden *dubbel onderhouden* — MCP doet dit automatisch via `tools/list`, CLI
niet (zie CLAUDE.md, PDR-005/PDR-006). Deze test maakt drift een CI-fout in
plaats van een runtime-verrassing: een tool die het LLM krijgt aangeboden maar
die de executor niet kent (of andersom) faalt hier meteen.
"""

import re
from pathlib import Path

HOST_DIR = Path(__file__).resolve().parent.parent


def _executor_tool_keys() -> set[str]:
    """Haal de afgehandelde tool-keys uit de `tool_key == "..."`-takken."""
    src = (HOST_DIR / "cli_executor.py").read_text(encoding="utf-8")
    return set(re.findall(r'tool_key == "([^"]+)"', src))


def test_cli_tooldefinities_en_executor_zijn_synchroon():
    from vlam_host import CLI_TOOL_DEFINITIONS_ANTHROPIC

    aangeboden = {t["name"] for t in CLI_TOOL_DEFINITIONS_ANTHROPIC}
    afgehandeld = _executor_tool_keys()

    assert aangeboden == afgehandeld, (
        "CLI-tooldefinities en cli_executor lopen uiteen.\n"
        f"  Wel aangeboden, niet afgehandeld: {sorted(aangeboden - afgehandeld)}\n"
        f"  Wel afgehandeld, niet aangeboden: {sorted(afgehandeld - aangeboden)}"
    )


def test_alle_cli_tools_hebben_verplichte_velden():
    """Elke tooldefinitie heeft de velden die het Anthropic-formaat vereist."""
    from vlam_host import CLI_TOOL_DEFINITIONS_ANTHROPIC

    for tool in CLI_TOOL_DEFINITIONS_ANTHROPIC:
        assert "name" in tool, f"tool zonder 'name': {tool}"
        assert tool.get("description"), f"{tool['name']}: ontbrekende/lege description"
        assert "input_schema" in tool, f"{tool['name']}: ontbrekend input_schema"

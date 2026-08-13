"""De feitenkaart (`VLAMHost.feiten`) vult zich voor alle zes agentic-loop-paden.

`feiten_uit_tool` zelf staat onder test in `test_feitenkaart.py`; dat bewijst
niets over de bedrading in `vlam_host.py`. Zonder deze test heeft precies de
fout die taak 4 riskeert geen vangnet: zet iemand later `feiten = {...}` in
plaats van `feiten.update(...)` in een van de zes `_chat_*`-methoden, dan
vervangt dat de by-reference-koppeling naar `self.feiten[conv_key]` door een
lokale dict, blijft de sessiekaart leeg, en blijft CI groen.

Elke test roept de publieke ingang aan (`chat()`/`chat_stream()`), niet de
interne `_chat_*`-methode direct — dat dekt ook de routering in
`chat`/`chat_stream` zelf, net als `test_dispatch_injection.py` doet voor de
KvK-injectie.
"""

import json
import types

import pytest

import vlam_host

SESSIE = "85234567"

# Eén KvK-resultaat volstaat: feiten_uit_tool wordt al los getest, hier gaat
# het om "komt het bij self.feiten aan", niet "wat komt eruit".
KVK_ENVELOPE = json.dumps(
    {
        "data": {
            "naam": "Kwekerij De Bloesem",
            "kvkNummer": "62345681",
            "_embedded": {
                "hoofdvestiging": {
                    "adressen": [
                        {"type": "bezoekadres", "volledigAdres": "Hoefweg 210, 2665KG Bleiswijk"},
                    ]
                }
            },
        }
    }
)
VESTIGINGSADRES = "Hoefweg 210, 2665KG Bleiswijk"


# --- Fakes: OpenAI/VLAM-stijl (gelijk aan test_dispatch_injection.py) --------


def _vlam_toolcall_msg():
    tc = types.SimpleNamespace(
        id="tc1",
        function=types.SimpleNamespace(name="kvk__mijn_bedrijf", arguments="{}"),
    )
    msg = types.SimpleNamespace(tool_calls=[tc], content="")
    msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": ""}
    return msg


def _vlam_final_msg():
    msg = types.SimpleNamespace(tool_calls=None, content="klaar")
    msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": "klaar"}
    return msg


def _fake_vlam_client():
    scripted = [_vlam_toolcall_msg(), _vlam_final_msg()]
    calls = {"i": 0}

    async def _create(**kwargs):
        msg = scripted[calls["i"]]
        calls["i"] += 1
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )


# --- Fakes: Anthropic/Claude-stijl -------------------------------------------


def _claude_toolcall_resp():
    block = types.SimpleNamespace(type="tool_use", name="kvk__mijn_bedrijf", input={}, id="tu1")
    return types.SimpleNamespace(content=[block], usage=None)


def _claude_final_resp():
    block = types.SimpleNamespace(type="text", text="klaar")
    return types.SimpleNamespace(content=[block], usage=None)


def _fake_claude_client():
    scripted = [_claude_toolcall_resp(), _claude_final_resp()]
    calls = {"i": 0}

    async def _create(**kwargs):
        resp = scripted[calls["i"]]
        calls["i"] += 1
        return resp

    return types.SimpleNamespace(api_key="x", messages=types.SimpleNamespace(create=_create))


# --- Tool-transport -----------------------------------------------------------


class _KvkRegistry:
    """MCP-registry die kvk__mijn_bedrijf beantwoordt, ongeacht de argumenten."""

    tool_map = {"kvk__mijn_bedrijf": ("kvk", {})}

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []

    async def call_tool(self, tool_key, arguments):
        return KVK_ENVELOPE


class _LegeRegistry:
    """Voor de CLI-paden: het CLI-transport gaat niet via de MCP-registry."""

    tool_map: dict = {}

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []


async def _drain(gen):
    async for _ in gen:
        pass


# --- De zes paden, als (mode, stream_of_blocking, mcp_of_cli) ---------------
#
# Dit zijn precies de zes _chat_*-methoden uit taak 4: vlam/claude x
# stream/blocking x mcp/cli (CLI-blocking bestaat niet als apart pad).
PADEN = [
    pytest.param("vlam", "stream", "mcp", id="vlam-stream(_chat_vlam_stream)"),
    pytest.param("claude", "stream", "mcp", id="claude-stream(_chat_claude_stream)"),
    pytest.param("vlam", "blocking", "mcp", id="vlam-blocking(_chat_vlam)"),
    pytest.param("claude", "blocking", "mcp", id="claude-blocking(_chat_claude)"),
    pytest.param("cli:claude", "stream", "cli", id="cli-claude-stream(_chat_cli_stream)"),
    pytest.param("cli:vlam", "stream", "cli", id="cli-vlam-stream(_chat_vlam_cli_stream)"),
]


@pytest.mark.parametrize("mode, kind, transport", PADEN)
async def test_feitenkaart_vult_zich_via_publieke_ingang(mode, kind, transport, monkeypatch):
    host = vlam_host.VLAMHost()
    llm = "claude" if "claude" in mode else "vlam"

    if transport == "mcp":
        host.registry = _KvkRegistry()
    else:
        # Het CLI-transport roept execute_cli_tool aan, niet de MCP-registry;
        # zonder deze patch valt dit pad praktisch niet te mocken via de
        # publieke ingang.
        host.registry = _LegeRegistry()

        async def _fake_cli(tool_key, arguments):
            return KVK_ENVELOPE

        monkeypatch.setattr(vlam_host, "execute_cli_tool", _fake_cli)

    if llm == "vlam":
        host.vlam_client = _fake_vlam_client()
    else:
        host.claude_client = _fake_claude_client()

    if kind == "stream":
        await _drain(host.chat_stream("sess", "hoi", mode=mode, session_kvk=SESSIE))
    else:
        await host.chat("sess", "hoi", mode=mode, session_kvk=SESSIE)

    conv_key = host._conv_key(SESSIE, "sess", mode)
    assert host.feiten.get(conv_key, {}).get("VESTIGINGSADRES") == VESTIGINGSADRES, (
        f"self.feiten is niet gevuld voor pad '{mode}/{kind}/{transport}' "
        f"(conv_key={conv_key!r}, feiten={host.feiten!r})"
    )

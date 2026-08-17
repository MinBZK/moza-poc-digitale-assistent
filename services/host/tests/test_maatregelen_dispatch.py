"""De bedrading van `maatregelen` op het SSE `answer`-event, via de publieke ingang.

`maatregelen_voor_event` zelf staat onder test in `test_maatregelen_event.py`;
dat bewijst niets over de bedrading in `vlam_host.py`. Precies dat is het
faalpatroon dat de nulmeting blootlegde: het veld bestond al in de frontend,
maar niemand vulde het — een correcte functie die nergens wordt aangeroepen is
geen werkende functie.

Alleen de twee MCP-streaming-paden kunnen `regelrecht__execute_law` ooit zien;
het CLI-transport sluit die tool uit (`_NIET_IN_CLI` in `cli_executor.py`), dus
`_chat_cli_stream`/`_chat_vlam_cli_stream` blijven hier buiten beschouwing —
net zoals `test_feitenkaart_dispatch.py` per pad toetst wat daar relevant is.

Volgt het patroon van `test_feitenkaart_dispatch.py` (taak 4): publieke ingang
(`chat_stream()`), niet de interne `_chat_*`-methode direct.
"""

import json
import types

import pytest

import vlam_host

SESSIE = "85234567"

MAATREGELEN_ENVELOPE = json.dumps(
    {
        "data": {
            "uitkomsten": {
                "maatregelen": [
                    {
                        "code": "GC1",
                        "naam": "Pas een klokregeling toe",
                        "categorie": "Ruimteverwarming",
                        "bijlage": "XIV",
                    }
                ]
            }
        }
    }
)
VERWACHTE_MAATREGELEN = [
    {
        "code": "GC1",
        "omschrijving": "Pas een klokregeling toe",
        "categorie": "Ruimteverwarming",
        "bijlage": "XIV",
    }
]


# --- Fakes: OpenAI/VLAM-stijl (gelijk aan test_feitenkaart_dispatch.py) ------


def _vlam_toolcall_msg():
    tc = types.SimpleNamespace(
        id="tc1",
        function=types.SimpleNamespace(name="regelrecht__execute_law", arguments="{}"),
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
    block = types.SimpleNamespace(
        type="tool_use", name="regelrecht__execute_law", input={}, id="tu1"
    )
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


class _EmlRegistry:
    """MCP-registry die regelrecht__execute_law beantwoordt, ongeacht de argumenten."""

    tool_map = {"regelrecht__execute_law": ("regelrecht", {})}

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []

    async def call_tool(self, tool_key, arguments):
        return MAATREGELEN_ENVELOPE


# --- De twee MCP-streaming-paden die deze tool ooit zien --------------------

PADEN = [
    pytest.param("vlam", id="vlam-stream(_chat_vlam_stream)"),
    pytest.param("claude", id="claude-stream(_chat_claude_stream)"),
]


@pytest.mark.parametrize("mode", PADEN)
async def test_maatregelen_verschijnt_op_answer_event(mode):
    host = vlam_host.VLAMHost()
    host.registry = _EmlRegistry()
    if mode == "vlam":
        host.vlam_client = _fake_vlam_client()
    else:
        host.claude_client = _fake_claude_client()

    events = [e async for e in host.chat_stream("sess", "hoi", mode=mode, session_kvk=SESSIE)]

    answer_events = [e for e in events if e.get("type") == "answer"]
    assert len(answer_events) == 1, f"verwacht precies één answer-event, kreeg {events!r}"
    assert answer_events[0].get("maatregelen") == VERWACHTE_MAATREGELEN, (
        f"maatregelen-veld ontbreekt of klopt niet voor pad '{mode}': {answer_events[0]!r}"
    )

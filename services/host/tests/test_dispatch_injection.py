"""Elk dispatch-pad injecteert het sessie-KvK (MVP-01/PDR-009).

Regressiebewaking: als iemand de `_inject_session_kvk`-wrapper uit één van de
vier inline-paden (VLAM-stream, VLAM-blocking, CLI-Claude, CLI-VLAM) verwijdert,
moet een test breken. We voeren elk pad end-to-end uit met een gescript LLM-fake
en een recorder op de tool-transport, en controleren dat het door het LLM
meegegeven (foute) KvK is overschreven door het sessie-KvK.
"""

import types

import vlam_host

SESSIE = "85234567"
LLM_KVK = "68750110"  # wat het "LLM" probeert; moet overschreven worden


# --- Fakes: OpenAI/VLAM-stijl ------------------------------------------------


def _vlam_toolcall_msg():
    tc = types.SimpleNamespace(
        id="tc1",
        function=types.SimpleNamespace(
            name="regelrecht__check",
            arguments=f'{{"kvk_nummer": "{LLM_KVK}"}}',
        ),
    )
    msg = types.SimpleNamespace(tool_calls=[tc], content="")
    msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": ""}
    return msg


def _vlam_final_msg():
    msg = types.SimpleNamespace(tool_calls=None, content="klaar")
    msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": "klaar"}
    return msg


def _fake_vlam_client(scripted):
    calls = {"i": 0}

    async def _create(**kwargs):
        msg = scripted[calls["i"]]
        calls["i"] += 1
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=msg)], usage=None
        )

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )


# --- Fakes: Anthropic/Claude-stijl (voor het CLI-Claude-pad) -----------------


def _claude_toolcall_resp():
    block = types.SimpleNamespace(
        type="tool_use", name="regelrecht__check", input={"kvk_nummer": LLM_KVK}, id="tu1"
    )
    return types.SimpleNamespace(content=[block], usage=None)


def _claude_final_resp():
    block = types.SimpleNamespace(type="text", text="klaar")
    return types.SimpleNamespace(content=[block], usage=None)


def _fake_claude_client(scripted):
    calls = {"i": 0}

    async def _create(**kwargs):
        resp = scripted[calls["i"]]
        calls["i"] += 1
        return resp

    return types.SimpleNamespace(
        api_key="x", messages=types.SimpleNamespace(create=_create)
    )


class _RecordingRegistry:
    def __init__(self):
        self.calls = []
        self.tool_map = {"regelrecht__check": ("regelrecht", {})}

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []

    async def call_tool(self, tool_key, arguments):
        self.calls.append((tool_key, arguments))
        return "{}"


def _host_with_recording_registry():
    host = vlam_host.VLAMHost()
    host.registry = _RecordingRegistry()
    return host


async def _drain(gen):
    async for _ in gen:
        pass


# De LLM-client gaat sinds MVP-02 als argument mee (nooit via gedeelde state op
# de host), dus geven de tests de fake expliciet mee aan het dispatch-pad.


async def test_vlam_stream_pad_injecteert_kvk():
    host = _host_with_recording_registry()
    vlam = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    await _drain(
        host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, vlam)
    )
    assert host.registry.calls[0][1]["kvk_nummer"] == SESSIE


async def test_vlam_blocking_pad_injecteert_kvk():
    host = _host_with_recording_registry()
    vlam = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    await host._chat_vlam([{"role": "user", "content": "hoi"}], SESSIE, vlam)
    assert host.registry.calls[0][1]["kvk_nummer"] == SESSIE


async def test_cli_claude_pad_injecteert_kvk(monkeypatch):
    host = _host_with_recording_registry()
    claude = _fake_claude_client([_claude_toolcall_resp(), _claude_final_resp()])
    recorded = []

    async def _fake_cli(tool_key, arguments):
        recorded.append((tool_key, arguments))
        return "{}"

    monkeypatch.setattr(vlam_host, "execute_cli_tool", _fake_cli)
    await _drain(
        host._chat_cli_stream([{"role": "user", "content": "hoi"}], SESSIE, claude)
    )
    assert recorded[0][1]["kvk_nummer"] == SESSIE


async def test_cli_vlam_pad_injecteert_kvk(monkeypatch):
    host = _host_with_recording_registry()
    vlam = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    recorded = []

    async def _fake_cli(tool_key, arguments):
        recorded.append((tool_key, arguments))
        return "{}"

    monkeypatch.setattr(vlam_host, "execute_cli_tool", _fake_cli)
    await _drain(
        host._chat_vlam_cli_stream([{"role": "user", "content": "hoi"}], SESSIE, vlam)
    )
    assert recorded[0][1]["kvk_nummer"] == SESSIE

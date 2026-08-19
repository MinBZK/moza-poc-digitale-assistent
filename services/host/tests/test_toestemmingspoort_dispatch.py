"""De toestemmingspoort geldt op élk dispatch-pad, niet alleen op dat van Claude.

`_bron_aanroep_gated` (PDR-008) heeft drie aanroeplocaties: `_execute_tools` voor
de Claude-paden, `_chat_vlam_stream` en `_chat_vlam`. Alleen de eerste stond
onder test. Een mutatietest liet zien wat dat waard is: haal de poort weg uit
beide VLAM-paden, en de hele suite blijft groen. Dat is niet zomaar een gat -
`vlam` is de default-modus, dus het ongedekte pad is het pad dat een respondent
raakt.

Dezelfde opzet als `test_dispatch_injection.py`: een gescripte LLM-fake die
`netbeheerder__verbruik` probeert aan te roepen, en een recorder op de
tool-transport. Bereikt die aanroep de registry, dan is de wallet geraadpleegd
zonder vastgelegde toestemming.
"""

import types

import pytest

import vlam_host

SESSIE = "62345681"
CONV = "62345681|sessie-a|vlam"


def _vlam_wallet_toolcall():
    """Een modelbeurt die de Business Wallet probeert aan te roepen."""
    tc = types.SimpleNamespace(
        id="tc1",
        function=types.SimpleNamespace(name="netbeheerder__verbruik", arguments="{}"),
    )
    msg = types.SimpleNamespace(tool_calls=[tc], content="")
    msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": ""}
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg, finish_reason="tool_calls")],
        usage=None,
    )


def _vlam_final():
    msg = types.SimpleNamespace(tool_calls=None, content="klaar")
    msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": "klaar"}
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg, finish_reason="stop")], usage=None
    )


def _fake_vlam(scripted):
    calls = {"i": 0}

    async def _create(**kwargs):
        resp = scripted[min(calls["i"], len(scripted) - 1)]
        calls["i"] += 1
        return resp

    return types.SimpleNamespace(
        api_key="x",
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create)),
    )


class _RecordingRegistry:
    def __init__(self):
        self.calls = []
        self.tool_map = {"netbeheerder__verbruik": ("netbeheerder", {})}

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []

    async def call_tool(self, tool_key, arguments):
        self.calls.append((tool_key, arguments))
        return "{}"


def _host():
    host = vlam_host.VLAMHost()
    host.registry = _RecordingRegistry()
    return host


async def _drain(gen):
    events = []
    async for e in gen:
        events.append(e)
    return events


async def test_vlam_stream_weigert_de_wallet_zonder_toestemming():
    host = _host()
    vlam = _fake_vlam([_vlam_wallet_toolcall(), _vlam_final()])
    events = await _drain(
        host._chat_vlam_stream(
            [{"role": "user", "content": "hoi"}], SESSIE, vlam, {}, None, CONV
        )
    )
    assert host.registry.calls == [], (
        f"de Business Wallet is geraadpleegd zonder toestemming: {host.registry.calls}"
    )
    codes = [e.get("code") for e in events if e.get("type") == "bron_fout"]
    assert "TOESTEMMING_VEREIST" in codes, f"geen weigering gemeld; events: {events}"


async def test_vlam_blocking_weigert_de_wallet_zonder_toestemming():
    host = _host()
    vlam = _fake_vlam([_vlam_wallet_toolcall(), _vlam_final()])
    await host._chat_vlam(
        [{"role": "user", "content": "hoi"}], SESSIE, vlam, {}, None, CONV
    )
    assert host.registry.calls == [], (
        f"de Business Wallet is geraadpleegd zonder toestemming: {host.registry.calls}"
    )


@pytest.mark.parametrize("streamend", [True, False])
async def test_vlam_laat_de_wallet_door_met_vastgelegde_toestemming(streamend):
    """De tegenproef: zonder deze kant meet de test alleen dat er niets gebeurt.

    Een poort die álles weigert zou de twee tests hierboven ook laten slagen.
    """
    host = _host()
    host.toestemming[CONV] = {"netbeheerder"}
    vlam = _fake_vlam([_vlam_wallet_toolcall(), _vlam_final()])
    argumenten = ([{"role": "user", "content": "hoi"}], SESSIE, vlam, {}, None, CONV)
    if streamend:
        await _drain(host._chat_vlam_stream(*argumenten))
    else:
        await host._chat_vlam(*argumenten)
    assert [t for t, _ in host.registry.calls] == ["netbeheerder__verbruik"]


async def test_claude_pad_blijft_gedekt():
    """De dekking die er al was, hier expliciet naast de nieuwe.

    Zo staat op één plek dat alle drie de aanroeplocaties van de poort getoetst
    zijn, in plaats van twee hier en één in een ander bestand.
    """
    host = _host()
    tool_use = types.SimpleNamespace(
        type="tool_use", name="netbeheerder__verbruik", input={}, id="tu1"
    )
    uitkomst = await host._execute_tools([tool_use], SESSIE, CONV)
    assert host.registry.calls == []
    # De vorm van de terugkeerwaarde staat hier niet vast; wat vaststaat is dat
    # de bron niet geraadpleegd is en dat de naam nergens als geraadpleegd
    # opduikt.
    assert "netbeheerder__verbruik" not in str(uitkomst[-1])

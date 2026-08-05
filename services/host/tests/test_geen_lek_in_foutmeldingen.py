"""Een mislukte bron-aanroep mag niets technisch doorgeven.

De host bouwde bij een falende tool `f"Fout bij tool '{naam}': {e}"` en gaf dat
als tool-resultaat aan het LLM, dat het kon doorvertellen aan de gebruiker.
Daarin zaten bestandspaden, interne URL's en stack-tekst. Deze test bewijst de
eigenschap in plaats van de huidige tekst: hij laat een tool falen met een
exception vol herkenbare technische rommel en controleert dat geen enkel
fragment daarvan het gesprek of de SSE-stream haalt.

Elk transport heeft zijn eigen dispatch-plek, dus alle vier de paden komen aan
bod; een verwijderde vertaalslag in één pad breekt hier een test.
"""

import types

import vlam_host

SESSIE = "85234567"

# Fragmenten die een echte exception meedraagt en die de gebruiker nooit hoort
# te zien. Elk fragment komt letterlijk terug in het bericht hieronder.
GEHEIM = "/Users/ontwikkelaar/services/host/.env"
INTERN = "https://interne-api.invalid/v1/prive"
SLEUTEL = "sk-ant-api03-ZEERGEHEIMEWAARDE1234567890"
BOODSCHAP = f"Connection refused bij {INTERN} (config: {GEHEIM}, key={SLEUTEL})"

LEKKEN = (GEHEIM, INTERN, SLEUTEL, "Connection refused", "Traceback")


def _bevat_geen_lek(tekst: str, waar: str):
    for fragment in LEKKEN:
        assert fragment not in tekst, f"{waar} lekt '{fragment}'"


# --- Fakes -------------------------------------------------------------------


def _vlam_toolcall_msg(argumenten='{"trefwoord": "energie"}'):
    tc = types.SimpleNamespace(
        id="tc1",
        function=types.SimpleNamespace(
            name="koop__zoek_regelgeving", arguments=argumenten
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
    beurt = {"i": 0}

    async def _create(**kwargs):
        msg = scripted[beurt["i"]]
        beurt["i"] += 1
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=msg)], usage=None
        )

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )


def _claude_toolcall_resp():
    block = types.SimpleNamespace(
        type="tool_use", name="koop__zoek_regelgeving", input={"trefwoord": "energie"}, id="tu1"
    )
    return types.SimpleNamespace(content=[block], usage=None)


def _claude_final_resp():
    block = types.SimpleNamespace(type="text", text="klaar")
    return types.SimpleNamespace(content=[block], usage=None)


def _fake_claude_client(scripted):
    beurt = {"i": 0}

    async def _create(**kwargs):
        resp = scripted[beurt["i"]]
        beurt["i"] += 1
        return resp

    return types.SimpleNamespace(api_key="x", messages=types.SimpleNamespace(create=_create))


class _FalendeRegistry:
    """Een registry waarvan elke tool-aanroep klapt met technische details."""

    tool_map = {"koop__zoek_regelgeving": ("koop", {})}

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []

    async def call_tool(self, tool_key, arguments):
        raise ConnectionError(BOODSCHAP)


def _host():
    host = vlam_host.VLAMHost()
    host.registry = _FalendeRegistry()
    return host


async def _events(gen):
    return [event async for event in gen]


# --- MCP-transport -----------------------------------------------------------


async def test_claude_stream_geeft_nette_melding_bij_falende_bron():
    host = _host()
    host.claude_client = _fake_claude_client([_claude_toolcall_resp(), _claude_final_resp()])
    events = await _events(host._chat_claude_stream([{"role": "user", "content": "hoi"}], SESSIE))

    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")

    bronfouten = [e for e in events if e["type"] == "bron_fout"]
    assert bronfouten, "de UI hoort te horen dat een bron uitviel"
    assert bronfouten[0]["bron"] == "koop"
    assert "wetten.overheid.nl" in bronfouten[0]["message"]


async def test_tool_resultaat_naar_het_llm_bevat_geen_techniek():
    """Wat het LLM ziet kan het doorvertellen; daar mag dus niets in zitten."""
    host = _host()
    berichten = [{"role": "user", "content": "hoi"}]
    host.claude_client = _fake_claude_client([_claude_toolcall_resp(), _claude_final_resp()])
    await _events(host._chat_claude_stream(berichten, SESSIE))

    tool_resultaten = [
        blok
        for bericht in berichten
        if isinstance(bericht.get("content"), list)
        for blok in bericht["content"]
        if isinstance(blok, dict) and blok.get("type") == "tool_result"
    ]
    assert tool_resultaten, "de tool-resultaten horen in de geschiedenis te staan"
    for blok in tool_resultaten:
        _bevat_geen_lek(blok["content"], "tool-resultaat")
        assert "gebruikersmelding" in blok["content"]


async def test_vlam_stream_geeft_nette_melding_bij_falende_bron():
    host = _host()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE))
    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")
    assert any(e["type"] == "bron_fout" for e in events)


async def test_vlam_blocking_pad_lekt_niet():
    host = _host()
    berichten = [{"role": "user", "content": "hoi"}]
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    antwoord = await host._chat_vlam(berichten, SESSIE)
    _bevat_geen_lek(antwoord, "antwoord")


# --- CLI-transport -----------------------------------------------------------


async def test_cli_claude_pad_lekt_niet(monkeypatch):
    async def _falende_cli(tool_key, arguments):
        raise ConnectionError(BOODSCHAP)

    monkeypatch.setattr(vlam_host, "execute_cli_tool", _falende_cli)
    host = _host()
    host.claude_client = _fake_claude_client([_claude_toolcall_resp(), _claude_final_resp()])
    events = await _events(host._chat_cli_stream([{"role": "user", "content": "hoi"}], SESSIE))
    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")
    assert any(e["type"] == "bron_fout" for e in events)


async def test_cli_vlam_pad_lekt_niet(monkeypatch):
    async def _falende_cli(tool_key, arguments):
        raise ConnectionError(BOODSCHAP)

    monkeypatch.setattr(vlam_host, "execute_cli_tool", _falende_cli)
    host = _host()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    events = await _events(host._chat_vlam_cli_stream([{"role": "user", "content": "hoi"}], SESSIE))
    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")
    assert any(e["type"] == "bron_fout" for e in events)


# --- Randgevallen ------------------------------------------------------------


async def test_onleesbare_toolcall_breekt_de_stream_niet():
    """Malformed JSON van het model gaf eerder een afgebroken SSE-stream."""
    host = _host()
    host.vlam_client = _fake_vlam_client(
        [_vlam_toolcall_msg(argumenten="{dit is geen json"), _vlam_final_msg()]
    )
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE))

    codes = [e.get("code") for e in events]
    assert "LLM_TOOLCALL_ONLEESBAAR" in codes
    assert events[-1]["type"] == "answer", "het gesprek hoort gewoon door te lopen"


async def test_onbereikbare_bron_wordt_als_zodanig_gemeld():
    """Een bron die niet opstartte, staat niet in de registry."""
    host = vlam_host.VLAMHost()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE))

    bronfouten = [e for e in events if e["type"] == "bron_fout"]
    assert bronfouten and bronfouten[0]["code"] == "BRON_NIET_GESTART"
    assert "KOOP" in bronfouten[0]["message"]

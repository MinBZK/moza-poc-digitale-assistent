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

import asyncio
import types
from pathlib import Path

from anyio import ClosedResourceError

import vlam_host
from errors import classificeer_tool_fout
from mcp_client import MCPServerConnection, MCPToolRegistry

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


def _terminale(events) -> list[str]:
    """De events waarop de frontend de chat afsluit; er hoort er precies één te zijn."""
    return [e["type"] for e in events if e["type"] in ("answer", "error")]


# --- MCP-transport -----------------------------------------------------------


async def test_claude_stream_geeft_nette_melding_bij_falende_bron():
    host = _host()
    host.claude_client = _fake_claude_client([_claude_toolcall_resp(), _claude_final_resp()])
    events = await _events(host._chat_claude_stream([{"role": "user", "content": "hoi"}], SESSIE, host.claude_client))

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
    await _events(host._chat_claude_stream(berichten, SESSIE, host.claude_client))

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
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client))
    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")
    assert any(e["type"] == "bron_fout" for e in events)


async def test_vlam_blocking_pad_lekt_niet():
    host = _host()
    berichten = [{"role": "user", "content": "hoi"}]
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    antwoord = await host._chat_vlam(berichten, SESSIE, host.vlam_client)
    _bevat_geen_lek(antwoord, "antwoord")


# --- CLI-transport -----------------------------------------------------------


async def test_cli_claude_pad_lekt_niet(monkeypatch):
    async def _falende_cli(tool_key, arguments):
        raise ConnectionError(BOODSCHAP)

    monkeypatch.setattr(vlam_host, "execute_cli_tool", _falende_cli)
    host = _host()
    host.claude_client = _fake_claude_client([_claude_toolcall_resp(), _claude_final_resp()])
    events = await _events(host._chat_cli_stream([{"role": "user", "content": "hoi"}], SESSIE, host.claude_client))
    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")
    assert any(e["type"] == "bron_fout" for e in events)


async def test_cli_vlam_pad_lekt_niet(monkeypatch):
    async def _falende_cli(tool_key, arguments):
        raise ConnectionError(BOODSCHAP)

    monkeypatch.setattr(vlam_host, "execute_cli_tool", _falende_cli)
    host = _host()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    events = await _events(host._chat_vlam_cli_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client))
    for event in events:
        _bevat_geen_lek(str(event), "SSE-event")
    assert any(e["type"] == "bron_fout" for e in events)


# --- Randgevallen ------------------------------------------------------------


async def test_onleesbare_toolcall_breekt_de_stream_niet():
    """Malformed JSON van het model gaf eerder een afgebroken SSE-stream.

    De gebruiker hoort er niets van: het model corrigeert dit zelf in de
    volgende ronde, en een storing aankondigen die er niet is maakt een gesprek
    dat verder gewoon slaagt onnodig verwarrend.
    """
    host = _host()
    scripted = [_vlam_toolcall_msg(argumenten="{dit is geen json"), _vlam_final_msg()]
    gezien = []
    beurt = {"i": 0}

    async def _create(**kwargs):
        # Vang de berichten die het model bij de tweede beurt te zien krijgt:
        # daar hoort de correctie-opdracht in te staan.
        gezien.append(kwargs.get("messages", []))
        msg = scripted[beurt["i"]]
        beurt["i"] += 1
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=msg)], usage=None
        )

    host.vlam_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client))

    assert events[-1]["type"] == "answer", "het gesprek hoort gewoon door te lopen"
    assert _terminale(events) == ["answer"], "precies één eindpunt"
    assert not [e for e in events if e["type"] in ("error", "bron_fout")], (
        "geen storingsmelding voor een fout die het model zelf herstelt"
    )

    # Het model krijgt de correctie-opdracht wél, anders kan het niets herstellen.
    tool_berichten = [m for m in gezien[-1] if m.get("role") == "tool"]
    assert tool_berichten, "het model hoort een tool-resultaat terug te krijgen"
    inhoud = tool_berichten[0]["content"]
    assert "LLM_TOOLCALL_ONLEESBAAR" in inhoud
    assert "gebruikersmelding" not in inhoud, "niets om aan de gebruiker door te vertellen"


async def test_onbereikbare_bron_wordt_als_zodanig_gemeld():
    """Een bron die niet opstartte, staat niet in de registry."""
    host = vlam_host.VLAMHost()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client))

    bronfouten = [e for e in events if e["type"] == "bron_fout"]
    assert bronfouten and bronfouten[0]["code"] == "BRON_NIET_GESTART"
    assert "KOOP" in bronfouten[0]["message"]


async def test_toolnaam_op_een_draaiende_bron_is_geen_startprobleem():
    """Een verzonnen toolnaam mag de gebruiker niet naar de beheerder sturen.

    Het model kan een tool verzinnen die niet bestaat; draait de bron gewoon,
    dan is "de bron is niet opgestart, meld het bij de beheerder" onjuist én
    onbruikbaar advies.
    """
    registry = MCPToolRegistry()
    registry.connections["koop"] = object()  # de bron draait wél
    melding = classificeer_tool_fout(
        "koop__verzonnen_tool", await registry.call_tool("koop__verzonnen_tool", {})
    )
    assert melding.code == "ONBEKENDE_TOOL"
    # Op de volledige melding, niet alleen op het `bericht`: de gebruiker leest
    # bericht + actie als één zin.
    assert "niet beschikbaar gekomen" not in melding.tekst
    assert melding.herstelbaar is True, "opnieuw vragen is hier juist wél het advies"


async def test_uitgevallen_bron_is_wel_een_startprobleem():
    registry = MCPToolRegistry()  # geen enkele verbinding
    melding = classificeer_tool_fout(
        "koop__zoek_regelgeving", await registry.call_tool("koop__zoek_regelgeving", {})
    )
    assert melding.code == "BRON_NIET_GESTART"


async def test_exception_in_een_mcp_server_lekt_niet_via_isError():
    """De MCP-SDK levert een handler-exception af als gewone tekst met isError.

    Dat pad liep buiten de foutafhandeling om: de exception-tekst ging als
    geslaagd resultaat naar het LLM. Precies wat deze branch belooft te sluiten,
    dus het hoort ook getest te worden op de echte vorm en niet alleen op een
    registry die zelf raist.
    """
    class _FakeSessie:
        async def call_tool(self, naam, argumenten):
            return types.SimpleNamespace(
                isError=True,
                content=[types.SimpleNamespace(text=BOODSCHAP)],
            )

    verbinding = MCPServerConnection("koop", Path("/bestaat/niet"))
    verbinding.session = _FakeSessie()
    resultaat = await verbinding.call_tool("zoek_regelgeving", {})

    _bevat_geen_lek(resultaat, "MCP isError-resultaat")
    melding = classificeer_tool_fout("koop__zoek_regelgeving", resultaat)
    assert melding is not None, "een isError-resultaat hoort een melding op te leveren"
    assert melding.bron == "koop"


async def test_respons_zonder_choices_geeft_melding_en_sluit_de_stream():
    """Een OpenAI-compatibele proxy kan `choices: []` teruggeven.

    Dat gooide een IndexError buiten elke except om: de stream stopte zonder
    antwoord, zonder melding en zonder `done`, en de UI bleef hangen.
    """
    host = _host()

    async def _leeg(**kwargs):
        return types.SimpleNamespace(choices=[], usage=None)

    host.vlam_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_leeg))
    )
    events = await _events(
        host.chat_stream("s1", "hoi", mode="vlam", session_kvk=SESSIE)
    )

    assert _terminale(events) == ["error"]
    assert events[-1]["type"] == "done", "de stream hoort altijd netjes te sluiten"


async def test_onverwachte_fout_in_de_loop_sluit_de_stream_alsnog_netjes(caplog):
    """Vangnet: wat de loops zelf niet afvangen, hoort alsnog een melding te geven.

    De fout moet buiten de `try` rond de LLM-call ontstaan, anders vangt de loop
    'm zelf af en raakt de test het vangnet helemaal niet. Hier struikelt het
    uitpakken van de respons: `message` ontbreekt op het choice-object.
    """
    host = _host()

    async def _rare_vorm(**kwargs):
        return types.SimpleNamespace(choices=[types.SimpleNamespace()], usage=None)

    host.vlam_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_rare_vorm))
    )
    events = await _events(host.chat_stream("s1", "hoi", mode="vlam", session_kvk=SESSIE))

    assert _terminale(events) == ["error"]
    assert events[-1]["type"] == "done", "de stream hoort altijd netjes te sluiten"
    # Een fout in de assistent zelf is geen fout van het AI-model: dat zou
    # iedereen die dit onderzoekt in de verkeerde hoek laten zoeken.
    assert events[-2]["code"] == "HOST_FOUT"
    assert "Onverwachte fout in de chat-stream" in caplog.text


async def test_hangende_bron_laat_de_stream_niet_eeuwig_staan(monkeypatch):
    """Zonder time-out op de tool-aanroep bleef de spinner oneindig draaien.

    Geen exception, dus het vangnet hielp daar niet: de generator stond gewoon
    stil op het `await`. De time-out maakt er een SOURCE_UNAVAILABLE van.
    """
    monkeypatch.setattr(vlam_host, "TOOL_TIMEOUT", 0.05)

    class _HangendeRegistry(_FalendeRegistry):
        async def call_tool(self, tool_key, arguments):
            await asyncio.sleep(30)

    host = vlam_host.VLAMHost()
    host.registry = _HangendeRegistry()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])

    events = await asyncio.wait_for(
        _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client)),
        timeout=5,
    )
    bronfouten = [e for e in events if e["type"] == "bron_fout"]
    assert bronfouten and bronfouten[0]["code"] == "SOURCE_UNAVAILABLE"
    assert _terminale(events) == ["answer"]


async def test_weggevallen_verbinding_meldt_de_bron_en_het_alternatief():
    """Een gecrashte MCP-server geeft geen OSError maar een SDK-/anyio-fout.

    Die viel eerder in de vage "onverwachte fout"-melding, precies bij het
    scenario dat de architectuurdocumentatie als voorbeeld gebruikt.
    """

    class _WeggevallenRegistry(_FalendeRegistry):
        async def call_tool(self, tool_key, arguments):
            raise ClosedResourceError

    host = vlam_host.VLAMHost()
    host.registry = _WeggevallenRegistry()
    host.vlam_client = _fake_vlam_client([_vlam_toolcall_msg(), _vlam_final_msg()])

    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client))
    bronfouten = [e for e in events if e["type"] == "bron_fout"]
    assert bronfouten and bronfouten[0]["code"] == "SOURCE_UNAVAILABLE"
    assert "wetten.overheid.nl" in bronfouten[0]["message"]


async def test_client_van_de_gebruiker_blijft_niet_op_de_host_staan():
    """De host is één gedeeld object; een per-verzoek sleutel mag niet blijven staan.

    Valt de client weg terwijl het eerste event wordt weggeschreven, dan wordt de
    generator daar gesloten. Stond dat `yield` buiten de try, dan draaide het
    `finally` nooit en bediende de sleutel van de een het volgende verzoek van
    een ander.

    Dekt bewust alleen het afgebroken-verzoek-pad. Dat twee gelijktijdige
    verzoeken met verschillende sleutels elkaar nog steeds raken (de client staat
    op `self`) is pre-existing en wordt opgelost in PR #44 (MVP-02).
    """
    host = _host()
    origineel_claude = host.claude_client
    origineel_vlam = host.vlam_client

    gen = host.chat_stream(
        "s1", "hoi", mode="claude", session_kvk=SESSIE, claude_api_key_override="sk-ant-VAN-A"
    )
    eerste = await gen.__anext__()
    assert eerste["type"] == "status"
    # Client valt weg midden in de stream (tab dicht, netwerk weg).
    await gen.aclose()

    assert host.claude_client is origineel_claude, "sleutel van de gebruiker blijft achter"
    assert host.vlam_client is origineel_vlam


async def test_afgekapt_antwoord_gaat_niet_verloren():
    """Een antwoord dat op max_tokens afbreekt is meestal grotendeels bruikbaar.

    Weggooien is een grotere achteruitgang dan de afbreking zelf; de gebruiker
    hoort de deeltekst te krijgen mét de melding dat er meer was.
    """
    host = _host()

    async def _afgekapt(**kwargs):
        msg = types.SimpleNamespace(tool_calls=None, content="Het antwoord begint en")
        msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": ""}
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=msg, finish_reason="length")], usage=None
        )

    host.vlam_client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_afgekapt))
    )
    events = await _events(host._chat_vlam_stream([{"role": "user", "content": "hoi"}], SESSIE, host.vlam_client))

    codes = [e.get("code") for e in events]
    assert "LLM_ANTWOORD_AFGEKAPT" in codes
    assert _terminale(events) == ["answer"], "precies één eindpunt"
    antwoord = [e for e in events if e["type"] == "answer"][0]
    assert "Het antwoord begint en" in antwoord["message"], "de deeltekst blijft"


async def test_bronfout_logt_geen_argumentwaarden(caplog):
    """De logregel van een mislukte bron-aanroep draagt geen identiteit.

    Regressie uit het samenvoegen van MVP-02 en PDR-011: `_bron_aanroep` logde de
    volledige exception-tekst, en die kan het sessie-KvK bevatten. Dat ondergraaft
    `_arg_keys`, dat juist alleen veldnamen logt.
    """

    async def _kapot():
        raise ValueError(f"kvk_nummer {SESSIE} niet gevonden in het Handelsregister")

    with caplog.at_level("ERROR", logger="vlam.host"):
        await vlam_host._bron_aanroep(_kapot, "kvk__mijn_bedrijf", {})

    assert SESSIE not in caplog.text, "het sessie-KvK stond in de foutregel"
    assert "kvk__mijn_bedrijf" in caplog.text
    assert "ValueError" in caplog.text

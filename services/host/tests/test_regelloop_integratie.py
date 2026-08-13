"""De regel stuurt de flow, niet het model (taak 4).

Vóór taak 4 orkestreerde het model zelf welke tool wanneer aan te roepen; de
routeringsregels in `tool_usage.md` schreven dat voor. Vanaf deze taak draait
`volg_regel` vóór het model, en bepaalt de host zelf wat hij zonder het model
al kan ophalen. Deze test bewijst dat via de publieke ingang (`chat_stream`):
bij de allereerste vraag van de respondent is de wet (`regelrecht__execute_law`)
de EERSTE bron die wordt aangeroepen — vóór KvK of wat dan ook — en wordt de
Business Wallet (`netbeheerder__verbruik`) niet geraadpleegd zolang er geen
toestemming is (PDR-008), ook al vraagt de respondent iets dat daar niets mee
te maken heeft.

Volgt het mock-patroon van `test_feitenkaart_dispatch.py`: de publieke ingang
aanroepen met een fake LLM-client en een fake registry, niet de interne
`_chat_*`-methode direct — dat dekt ook de bedrading in `chat`/`chat_stream`
zelf.
"""

import json
import types

import pytest

import vlam_host

SESSIE = "85234567"


# --- Fakes: LLM geeft meteen een tekstantwoord, geen tool-aanroep ------------
# De regelloop draait vóór het model; het model hoeft in deze test niets te
# doen behalve een afsluitend antwoord geven.


def _fake_claude_client():
    async def _create(**kwargs):
        block = types.SimpleNamespace(type="text", text="Ik vraag het na.")
        return types.SimpleNamespace(content=[block], usage=None)

    return types.SimpleNamespace(api_key="x", messages=types.SimpleNamespace(create=_create))


def _fake_vlam_client():
    async def _create(**kwargs):
        msg = types.SimpleNamespace(tool_calls=None, content="Ik vraag het na.")
        msg.model_dump = lambda exclude_none=True: {"role": "assistant", "content": "Ik vraag het na."}
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)], usage=None)

    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))
    )


class _RolRegistry:
    """MCP-registry die de aanroepvolgorde vastlegt en de wet-rondes scripts.

    Ronde 1 van de wet mist IS_WOONFUNCTIE (routeert naar de KvK-tool, geen
    toestemming nodig); ronde 2 mist het elektriciteitsverbruik (routeert naar
    de Business Wallet, WEL toestemming nodig). Zonder toestemming stopt de lus
    daar - de netbeheerder__verbruik-tool mag dan nooit aangeroepen worden.
    """

    tool_map = {
        "regelrecht__execute_law": ("regelrecht", {}),
        "kvk__mijn_bedrijf": ("kvk", {}),
        "netbeheerder__verbruik": ("netbeheerder", {}),
    }

    def __init__(self):
        self.aanroepen: list[str] = []
        self._wet_ronde = 0

    def get_openai_tools(self):
        return []

    def get_anthropic_tools(self):
        return []

    async def call_tool(self, tool_key, arguments):
        self.aanroepen.append(tool_key)
        if tool_key == "regelrecht__execute_law":
            self._wet_ronde += 1
            if self._wet_ronde == 1:
                missend = "IS_WOONFUNCTIE"
            else:
                missend = "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": missend}]}})
        if tool_key == "kvk__mijn_bedrijf":
            return json.dumps({"data": {"is_woonfunctie": False}})
        if tool_key == "netbeheerder__verbruik":
            raise AssertionError(
                "netbeheerder__verbruik aangeroepen zonder toestemming (PDR-008)"
            )
        raise AssertionError(f"onverwachte tool: {tool_key}")


async def _drain(gen):
    async for _ in gen:
        pass


PADEN = [
    pytest.param("vlam", id="vlam-stream"),
    pytest.param("claude", id="claude-stream"),
]


@pytest.mark.parametrize("mode", PADEN)
async def test_wet_altijd_eerst_en_geen_netbeheerder_zonder_toestemming(mode):
    host = vlam_host.VLAMHost()
    host.registry = _RolRegistry()
    if mode == "vlam":
        host.vlam_client = _fake_vlam_client()
    else:
        host.claude_client = _fake_claude_client()

    await _drain(
        host.chat_stream("sess", "Geldt de informatieplicht voor mij?", mode=mode, session_kvk=SESSIE)
    )

    aanroepen = host.registry.aanroepen
    assert aanroepen, "de regelloop heeft geen enkele bron aangeroepen"
    assert aanroepen[0] == "regelrecht__execute_law", (
        f"de wet moet vóór elke andere bron aangeroepen zijn, kreeg: {aanroepen}"
    )
    assert "kvk__mijn_bedrijf" in aanroepen, "de KvK-tool levert IS_WOONFUNCTIE zonder toestemming"
    assert "netbeheerder__verbruik" not in aanroepen


async def test_toestemming_afgeleid_uit_attestatie_feit_ontsluit_de_wallet():
    """De zwakste plek van het ontwerp: toestemming is een afleiding, geen vlag.

    Staat er al een attestatie-feit in de feitenkaart (bv. van een eerdere
    beurt), dan mag de lus de Business Wallet zonder opnieuw te vragen
    raadplegen.
    """
    host = vlam_host.VLAMHost()
    registry = _RolRegistry()

    async def _call_tool_met_wallet(tool_key, arguments):
        registry.aanroepen.append(tool_key)
        if tool_key == "regelrecht__execute_law":
            registry._wet_ronde += 1
            if registry._wet_ronde == 1:
                return json.dumps(
                    {"data": {"ontbrekende_gegevens": [{"naam": "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"}]}}
                )
            return json.dumps({"data": {"voldoet_aan_voorwaarden": True, "uitkomsten": {}}})
        if tool_key == "netbeheerder__verbruik":
            return json.dumps(
                {"data": {"beschikbaar": True, "verbruik": {"totaal": {"jaarlijks_elektriciteitsverbruik_kwh": 60000}}}}
            )
        raise AssertionError(f"onverwachte tool: {tool_key}")

    registry.call_tool = _call_tool_met_wallet
    host.registry = registry
    host.claude_client = _fake_claude_client()

    conv_key = host._conv_key(SESSIE, "sess", "claude")
    host.feiten[conv_key] = {
        "ELEKTRICITEIT_KWH": {"waarde": 40000, "bron": "Business Wallet", "soort": "attestatie"}
    }

    await _drain(host.chat_stream("sess", "Geldt de informatieplicht voor mij?", mode="claude", session_kvk=SESSIE))

    assert "netbeheerder__verbruik" in registry.aanroepen


async def test_rondegrens_overschreden_wordt_als_onbekend_afgehandeld():
    """`wacht_op=None` mét `klaar=False` is een derde toestand (zie regelloop.py).

    Zonder expliciete afhandeling valt dit geval stilzwijgend door de
    `wacht_op`-dispatch; hier moet de host het gewoon als "onbekend" behandelen
    in plaats van vast te lopen.
    """
    host = vlam_host.VLAMHost()

    class _EindeloosRegistry:
        tool_map = {"regelrecht__execute_law": ("regelrecht", {})}

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            # Blijft hetzelfde ontbrekende veld melden: nooit klaar, altijd
            # dezelfde vraag - precies de rondegrens-situatie uit test_regelloop.py.
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]}})

    host.registry = _EindeloosRegistry()
    host.claude_client = _fake_claude_client()

    events = []
    async for event in host.chat_stream(
        "sess", "Geldt de informatieplicht voor mij?", mode="claude", session_kvk=SESSIE
    ):
        events.append(event)

    # Geen crash, en het gesprek sluit gewoon af met een antwoord.
    assert any(e.get("type") == "answer" for e in events)

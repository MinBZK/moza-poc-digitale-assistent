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
zelf. Net als daar: alle zes de paden (vlam/claude x stream/blocking x mcp/cli),
niet alleen de twee MCP-streampaden — anders dekt de suite de andere vier niet.
"""

import ast
import json
import types
from pathlib import Path

import pytest

import errors
import vlam_host

SESSIE = "85234567"


# --- Fakes: LLM geeft meteen een tekstantwoord, geen tool-aanroep ------------
# De regelloop draait vóór het model; het model hoeft in de meeste tests hier
# niets te doen behalve een afsluitend antwoord geven. `system_prompts` (een
# lijst) vangt de systeemprompt op zoals die het model bereikte, zodat een
# test kan controleren of "STATUS VAN DE REGELTOETS" er wel/niet in staat.


def _fake_claude_client(system_prompts: list | None = None):
    async def _create(**kwargs):
        if system_prompts is not None:
            system_prompts.append(kwargs.get("system", ""))
        block = types.SimpleNamespace(type="text", text="Ik vraag het na.")
        return types.SimpleNamespace(content=[block], usage=None)

    return types.SimpleNamespace(api_key="x", messages=types.SimpleNamespace(create=_create))


def _fake_vlam_client(system_prompts: list | None = None):
    async def _create(**kwargs):
        if system_prompts is not None:
            eerste = kwargs.get("messages", [{}])[0]
            system_prompts.append(eerste.get("content", ""))
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


# --- De zes paden, als (mode, kind, transport) — zelfde matrix als
# test_feitenkaart_dispatch.py. Voor de CLI-paden draait de lus bewust NIET
# (cli_transport.md): die twee bewijzen dat, niet het wet-eerst-gedrag.
PADEN = [
    pytest.param("vlam", "stream", "mcp", id="vlam-stream(_chat_vlam_stream)"),
    pytest.param("claude", "stream", "mcp", id="claude-stream(_chat_claude_stream)"),
    pytest.param("vlam", "blocking", "mcp", id="vlam-blocking(_chat_vlam)"),
    pytest.param("claude", "blocking", "mcp", id="claude-blocking(_chat_claude)"),
    pytest.param("cli:claude", "stream", "cli", id="cli-claude-stream(_chat_cli_stream)"),
    pytest.param("cli:vlam", "stream", "cli", id="cli-vlam-stream(_chat_vlam_cli_stream)"),
]


@pytest.mark.parametrize("mode, kind, transport", PADEN)
async def test_wet_altijd_eerst_en_geen_netbeheerder_zonder_toestemming(
    mode, kind, transport, monkeypatch
):
    host = vlam_host.VLAMHost()
    llm = "claude" if "claude" in mode else "vlam"
    system_prompts: list = []

    if transport == "mcp":
        host.registry = _RolRegistry()
    else:
        host.registry = _LegeRegistry()

        async def _fake_cli(tool_key, arguments):
            raise AssertionError(
                f"CLI-transport hoort hier niets aan te roepen via de regel-loop: {tool_key}"
            )

        monkeypatch.setattr(vlam_host, "execute_cli_tool", _fake_cli)

    if llm == "vlam":
        host.vlam_client = _fake_vlam_client(system_prompts)
    else:
        host.claude_client = _fake_claude_client(system_prompts)

    if kind == "stream":
        await _drain(host.chat_stream("sess", "hoi", mode=mode, session_kvk=SESSIE))
    else:
        await host.chat("sess", "hoi", mode=mode, session_kvk=SESSIE)

    if transport == "mcp":
        aanroepen = host.registry.aanroepen
        assert aanroepen, f"de regelloop heeft geen enkele bron aangeroepen (pad {mode}/{kind})"
        assert aanroepen[0] == "regelrecht__execute_law", (
            f"de wet moet vóór elke andere bron aangeroepen zijn, kreeg: {aanroepen}"
        )
        assert "kvk__mijn_bedrijf" in aanroepen, "de KvK-tool levert IS_WOONFUNCTIE zonder toestemming"
        assert "netbeheerder__verbruik" not in aanroepen
        assert "STATUS VAN DE REGELTOETS" in system_prompts[0]
        assert "bestaat in deze instelling NIET" not in system_prompts[0]
    else:
        # De lus draait hier niet: geen regel_status-blok, wel de CLI-correctie
        # die zegt dat die sectie hier ontbreekt (I6) - zonder die correctie
        # zou het model op een sectie sturen die voor dit transport nooit komt.
        assert "bestaat in deze instelling NIET" in system_prompts[0]


async def test_toestemming_expliciet_true_ontsluit_de_wallet():
    """C1/C3: toestemming is een vastgelegde vlag, niet een afleiding uit feiten.

    De publieke `toestemming=True` op `chat_stream` (het contract-veld, gevuld
    door de "Delen"-knop van de frontend) moet de lus meteen laten doorlopen
    naar de Business Wallet — zonder dat er al een attestatie-feit in de kaart
    hoeft te staan.
    """
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
    host = vlam_host.VLAMHost()
    host.registry = registry
    host.claude_client = _fake_claude_client()

    await _drain(
        host.chat_stream(
            "sess",
            "Geldt de informatieplicht voor mij?",
            mode="claude",
            session_kvk=SESSIE,
            toestemming=True,
        )
    )

    assert "netbeheerder__verbruik" in registry.aanroepen


async def test_attestatieachtig_feit_in_de_kaart_ontsluit_de_wallet_niet():
    """Regressiebewaking tegen de circulaire afleiding die C1/C2 fixten.

    Een feit met `soort: attestatie` in de kaart mag NIET langer als
    toestemming gelden — anders staat de wallet open voor elke waarde die
    toevallig die soort draagt, inclusief een modelgestuurde override die zich
    voor een attestatie uitgeeft (C2).
    """
    host = vlam_host.VLAMHost()
    host.registry = _RolRegistry()
    host.claude_client = _fake_claude_client()

    conv_key = host._conv_key(SESSIE, "sess", "claude")
    host.feiten[conv_key] = {
        "ELEKTRICITEIT_KWH": {"waarde": 40000, "bron": "Business Wallet", "soort": "attestatie"}
    }

    await _drain(
        host.chat_stream("sess", "Geldt de informatieplicht voor mij?", mode="claude", session_kvk=SESSIE)
    )

    assert "netbeheerder__verbruik" not in host.registry.aanroepen


async def test_netbeheerder_zonder_vastgelegde_toestemming_wordt_geweigerd():
    """De harde poort (PDR-008): `_bron_aanroep_gated` weigert
    `netbeheerder__verbruik` zolang `self.toestemming[conv_key]` niet is
    vastgelegd — ook als het model zelf de aanroep initieert, buiten de
    regelloop om. De registry hieronder raiset zodra hij toch wordt bereikt,
    zodat deze test bewijst dat de poort vóór de bron staat, niet erna.
    """
    host = vlam_host.VLAMHost()

    class _RegistryDieNooitBereiktMagWorden:
        tool_map = {"netbeheerder__verbruik": ("netbeheerder", {})}

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            raise AssertionError(
                "netbeheerder__verbruik bereikte de registry zonder vastgelegde "
                "toestemming — de PDR-008-poort had dit moeten tegenhouden"
            )

    host.registry = _RegistryDieNooitBereiktMagWorden()
    conv_key = "conv-geen-toestemming"
    tool_use = types.SimpleNamespace(
        type="tool_use", name="netbeheerder__verbruik", input={}, id="tu1"
    )

    assert host.toestemming.get(conv_key, False) is False
    tool_results, bronfouten = await host._execute_tools([tool_use], SESSIE, conv_key)

    assert len(bronfouten) == 1
    assert bronfouten[0].code == "TOESTEMMING_VEREIST"
    payload = json.loads(tool_results[0]["content"])
    assert payload["error"] == "TOESTEMMING_VEREIST"
    # De catalogusmelding uit errors.py, niet een verzonnen tekst.
    assert payload["gebruikersmelding"] == errors.maak_fout("TOESTEMMING_VEREIST", bron="netbeheerder").tekst
    assert host.toestemming.get(conv_key, False) is False


async def test_netbeheerder_met_vastgelegde_toestemming_bereikt_de_bron():
    """Dezelfde aanroep als hierboven, nu mét toestemming: de poort laat 'm door."""
    host = vlam_host.VLAMHost()

    class _NetbeheerderRegistry:
        tool_map = {"netbeheerder__verbruik": ("netbeheerder", {})}

        def __init__(self):
            self.aanroepen = 0

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            self.aanroepen += 1
            return json.dumps({"data": {"beschikbaar": True}})

    registry = _NetbeheerderRegistry()
    host.registry = registry
    conv_key = "conv-met-toestemming"
    host.toestemming[conv_key] = True
    tool_use = types.SimpleNamespace(
        type="tool_use", name="netbeheerder__verbruik", input={}, id="tu1"
    )

    tool_results, bronfouten = await host._execute_tools([tool_use], SESSIE, conv_key)

    assert registry.aanroepen == 1
    assert not bronfouten
    assert json.loads(tool_results[0]["content"])["data"]["beschikbaar"] is True


async def test_toestemming_op_het_verzoek_ontsluit_een_modelgestuurde_aanroep():
    """End-to-end via het publieke contract: `toestemming: true` op het
    verzoek (de "Delen"-knop) zet de vlag vóórdat het model aan zet is, en
    laat een aanroep die het model zelf initieert — niet de regelloop —
    daarna gewoon door de poort.
    """
    host = vlam_host.VLAMHost()

    class _NetbeheerderRegistry:
        tool_map = {"netbeheerder__verbruik": ("netbeheerder", {})}

        def __init__(self):
            self.aanroepen: list[str] = []

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            self.aanroepen.append(tool_key)
            return json.dumps({"data": {"beschikbaar": True}})

    registry = _NetbeheerderRegistry()
    host.registry = registry

    # Het model roept eerst zelf `netbeheerder__verbruik` aan, en sluit de
    # beurt daarna af met tekst — de exacte modelgestuurde beweging uit de
    # bug: geen regelloop, geen wet, alleen het model dat de tool kiest.
    beurten = iter(
        [
            types.SimpleNamespace(
                content=[
                    types.SimpleNamespace(
                        type="tool_use", id="tu1", name="netbeheerder__verbruik", input={}
                    )
                ],
                usage=None,
            ),
            types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text="Uw verbruik is opgehaald.")],
                usage=None,
            ),
        ]
    )

    async def _create(**kwargs):
        return next(beurten)

    host.claude_client = types.SimpleNamespace(
        api_key="x", messages=types.SimpleNamespace(create=_create)
    )

    await _drain(
        host.chat_stream(
            "sess",
            "Wat is mijn energieverbruik?",
            mode="claude",
            session_kvk=SESSIE,
            toestemming=True,
        )
    )

    assert "netbeheerder__verbruik" in registry.aanroepen


async def test_geslaagde_netbeheerder_aanroep_zet_de_toestemmingsvlag_niet_meer():
    """Regressietest op de grondoorzaak: een geslaagde
    `netbeheerder__verbruik`-aanroep autoriseerde zichzelf (de aanroep zette de
    vlag die hij zelf nodig had om door de poort te komen). Toestemming komt nu
    uitsluitend uit het `toestemming`-veld op het chat-contract (`chat`/
    `chat_stream`) — nergens anders.

    Functioneel is dit sinds de poort (taak 8) niet meer los te toetsen: een
    aanroep die zonder toestemming zou moeten "slagen om zichzelf te
    autoriseren" komt de poort al niet meer door, dus die situatie bestaat
    domweg niet meer om tegen te toetsen (de twee tests hierboven bewijzen
    dát). Wat wél blijft: de broncode mag `self.toestemming[...] = True` alleen
    nog zetten op het contract-veld, niet als bijeffect van een tool-resultaat.
    Deze test scant daarop, zodat hij faalt zodra iemand de oude regel (`if
    tool_key == "netbeheerder__verbruik" and fout is None: ...`) ergens
    terugzet.
    """
    bron = Path(vlam_host.__file__).read_text(encoding="utf-8")
    plekken = [
        i + 1
        for i, regel in enumerate(bron.splitlines())
        if "self.toestemming[conv_key] = True" in regel
    ]
    functies = ast.parse(bron)
    toegestane_regels = {
        regel
        for node in ast.walk(functies)
        if isinstance(node, ast.AsyncFunctionDef) and node.name in ("chat", "chat_stream")
        for regel in range(node.lineno, (node.end_lineno or node.lineno) + 1)
    }
    buiten_contract = [r for r in plekken if r not in toegestane_regels]
    assert not buiten_contract, (
        f"self.toestemming wordt op regel(s) {buiten_contract} gezet buiten "
        "chat/chat_stream om - dat is precies het pad waarmee een geslaagde "
        "netbeheerder__verbruik-aanroep zichzelf autoriseerde (PDR-008)."
    )


async def test_regelloop_yieldt_tool_events_terwijl_hij_raadpleegt():
    """I1/I2: de lus yieldt voortgang, niet pas een antwoord aan het einde.

    Zonder deze events ziet de respondent niet dat er iets geraadpleegd wordt
    (op een branch die "herkomst zichtbaar" heet), en mist een verificatiescript
    dat op events let de aanroepen van de lus volledig.
    """
    host = vlam_host.VLAMHost()
    host.registry = _RolRegistry()
    host.claude_client = _fake_claude_client()

    events = [
        e
        async for e in host.chat_stream(
            "sess", "Geldt de informatieplicht voor mij?", mode="claude", session_kvk=SESSIE
        )
    ]

    tool_events = [e for e in events if e.get("type") == "tool"]
    genoemde_tools = [e.get("tool") for e in tool_events]
    assert "regelrecht__execute_law" in genoemde_tools
    assert "kvk__mijn_bedrijf" in genoemde_tools
    # De tool-events van de lus gaan vooraf aan het antwoord, niet erna.
    answer_index = next(i for i, e in enumerate(events) if e.get("type") == "answer")
    assert all(events.index(e) < answer_index for e in tool_events)


async def test_regelloop_yieldt_bron_fout_bij_een_falende_aanroep():
    """I1/I2: een falende aanroep valt niet stilzwijgend op {} - de client
    krijgt een `bron_fout`-event, net als bij een modelgestuurde tool-aanroep."""
    host = vlam_host.VLAMHost()

    class _FalendeKvkRegistry:
        tool_map = {
            "regelrecht__execute_law": ("regelrecht", {}),
            "kvk__mijn_bedrijf": ("kvk", {}),
        }

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            if tool_key == "regelrecht__execute_law":
                return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]}})
            if tool_key == "kvk__mijn_bedrijf":
                raise TimeoutError("kvk-server reageert niet")
            raise AssertionError(f"onverwachte tool: {tool_key}")

    host.registry = _FalendeKvkRegistry()
    host.claude_client = _fake_claude_client()

    events = [
        e
        async for e in host.chat_stream(
            "sess", "Geldt de informatieplicht voor mij?", mode="claude", session_kvk=SESSIE
        )
    ]

    assert any(e.get("type") == "bron_fout" for e in events)
    # Geen crash: het gesprek sluit nog steeds af met een antwoord.
    assert any(e.get("type") == "answer" for e in events)


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


def test_regel_status_dict_normaliseert_de_rondegrens_expliciet():
    """Directe, nauwkeurige toets van de normalisatie zelf (I10).

    De integratietest hierboven bewijst alleen dat er geen crash optreedt -
    dat slaagt ook zónder de normalisatie, want elke onbekende `wacht_op` zou
    de prompt gewoon zonder specifieke instructie laten. Deze test faalt wél
    zodra iemand de `or (...)`-normalisatie uit `_regel_status_dict` haalt.
    """
    from regelloop import Uitkomst

    uitkomst = Uitkomst(klaar=False, resultaat=None, wacht_op=None, reden="rondegrens overschreden")
    status = vlam_host._regel_status_dict(uitkomst)
    assert status["wacht_op"] == "onbekend"

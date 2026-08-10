"""Sleutels blijven binnen één verzoek (MVP-02).

De host is één gedeeld object en de endpoints zijn async; vóór MVP-02 stond de
per-verzoek client op `self.*`. Deze tests forceren de interleaving die dat liet
misgaan — A start, B start, pas dán doet A zijn LLM-call — en falen op de oude
implementatie. Verder: een override-client wordt gesloten, server-clients niet.
"""

import asyncio
import io
import logging
import types

import pytest

import log_redaction
import vlam_host

KVK_A = "85234567"
KVK_B = "62345681"
# Bewust vormloos (geen `sk-`-voorvoegsel), zoals een VLAM/UbiOps-token: dat is
# het geval dat patroonherkenning niet ziet. Wel lang genoeg en een mengsel van
# letters en cijfers, want anders wordt de waarde — terecht — niet als sleutel
# geregistreerd bij het log-vangnet.
KEY_A = "vlamtoken-a1b2c3d4e5f6a7b8c9d0"
KEY_B = "vlamtoken-9z8y7x6w5v4u3t2s1r0q"


class _FakeClaude:
    """Anthropic-achtige client die vastlegt wélke sleutel wélke vraag bediende."""

    gemaakt: list["_FakeClaude"] = []

    def __init__(self, api_key="", **_kwargs):
        self.api_key = api_key
        self.gesloten = False
        self.messages = types.SimpleNamespace(create=self._create)
        _FakeClaude.gemaakt.append(self)

    async def _create(self, **kwargs):
        # Leg vast: (vraag van de gebruiker, sleutel waarmee die verstuurd werd)
        vraag = next(
            (m["content"] for m in kwargs["messages"] if m.get("role") == "user"), "?"
        )
        AANROEPEN.append((vraag, self.api_key))
        # Momentopname van de redactie mídden in het verzoek.
        TIJDENS_VERZOEK.append(log_redaction.redact(f"fout met {self.api_key}"))
        block = types.SimpleNamespace(type="text", text="klaar")
        return types.SimpleNamespace(content=[block], usage=None)

    async def close(self):
        self.gesloten = True


class _FakeVlam:
    """OpenAI-achtige client, zelfde registratie als _FakeClaude."""

    gemaakt: list["_FakeVlam"] = []

    def __init__(self, api_key="", **_kwargs):
        self.api_key = api_key
        self.gesloten = False
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )
        _FakeVlam.gemaakt.append(self)

    async def _create(self, **kwargs):
        vraag = next(
            (m["content"] for m in kwargs["messages"] if m.get("role") == "user"), "?"
        )
        AANROEPEN.append((vraag, self.api_key))
        msg = types.SimpleNamespace(tool_calls=None, content="klaar")
        msg.model_dump = lambda exclude_none=True: {
            "role": "assistant",
            "content": "klaar",
        }
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=msg)], usage=None
        )

    async def close(self):
        self.gesloten = True


AANROEPEN: list[tuple[str, str]] = []
TIJDENS_VERZOEK: list[str] = []


@pytest.fixture
def host(monkeypatch):
    """Host met echte server-env-clients, fakes voor override-clients.

    Eerst de host bouwen, daarna de SDK-klassen patchen: zo kunnen we ook zien
    dat de server-clients niet zijn aangeraakt.
    """
    AANROEPEN.clear()
    TIJDENS_VERZOEK.clear()
    _FakeClaude.gemaakt.clear()
    _FakeVlam.gemaakt.clear()
    h = vlam_host.VLAMHost()
    monkeypatch.setattr(vlam_host.anthropic, "AsyncAnthropic", _FakeClaude)
    monkeypatch.setattr(vlam_host.openai, "AsyncOpenAI", _FakeVlam)
    # VLAM_BASE_URL moet gezet zijn, anders slaat _request_clients de
    # vlam-override over (dat is bestaand gedrag, geen onderdeel van deze test).
    monkeypatch.setattr(vlam_host, "VLAM_BASE_URL", "https://vlam.test/v1")
    return h


async def _drain(gen):
    async for _ in gen:
        pass


async def test_gelijktijdige_gesprekken_delen_geen_claude_sleutel(host):
    gen_a = host.chat_stream(
        "sessie-a", "vraag-A", mode="claude", session_kvk=KVK_A,
        claude_api_key_override=KEY_A,
    )
    gen_b = host.chat_stream(
        "sessie-b", "vraag-B", mode="claude", session_kvk=KVK_B,
        claude_api_key_override=KEY_B,
    )

    # Stap 1+2: beide streams starten (tot het eerste status-event) vóórdat er
    # een LLM-call gedaan is. Hier ging het mis: B overschreef de state van A.
    await gen_a.__anext__()
    await gen_b.__anext__()

    # Stap 3: A doet nu pas zijn LLM-call.
    await _drain(gen_a)
    await _drain(gen_b)

    assert ("vraag-A", KEY_A) in AANROEPEN, (
        f"vraag-A is niet met de sleutel van A verstuurd: {AANROEPEN}"
    )
    assert ("vraag-B", KEY_B) in AANROEPEN
    assert ("vraag-A", KEY_B) not in AANROEPEN, "sleutel van B lekte naar het verzoek van A"
    assert ("vraag-B", KEY_A) not in AANROEPEN, "sleutel van A lekte naar het verzoek van B"


async def test_gelijktijdige_gesprekken_delen_geen_vlam_sleutel(host):
    gen_a = host.chat_stream(
        "sessie-a", "vraag-A", mode="vlam", session_kvk=KVK_A,
        vlam_api_key_override=KEY_A,
    )
    gen_b = host.chat_stream(
        "sessie-b", "vraag-B", mode="vlam", session_kvk=KVK_B,
        vlam_api_key_override=KEY_B,
    )

    await gen_a.__anext__()
    await gen_b.__anext__()
    await _drain(gen_a)
    await _drain(gen_b)

    assert ("vraag-A", KEY_A) in AANROEPEN, (
        f"vraag-A is niet met de sleutel van A verstuurd: {AANROEPEN}"
    )
    assert ("vraag-B", KEY_B) in AANROEPEN
    assert ("vraag-A", KEY_B) not in AANROEPEN
    assert ("vraag-B", KEY_A) not in AANROEPEN


async def test_gelijktijdige_blocking_chats_delen_geen_sleutel(host):
    """Zelfde bugklasse als hierboven, maar op het niet-streamende pad.

    `chat()` muteerde dezelfde gedeelde state. Zonder deze test zou een
    regressie daar ongemerkt terug kunnen komen.
    """
    trager = asyncio.Event()

    async def _a():
        return await host.chat(
            "sessie-a", "vraag-A", mode="claude", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
        )

    async def _b():
        await trager.wait()
        return await host.chat(
            "sessie-b", "vraag-B", mode="claude", session_kvk=KVK_B,
            claude_api_key_override=KEY_B,
        )

    taak_a = asyncio.create_task(_a())
    taak_b = asyncio.create_task(_b())
    trager.set()
    await asyncio.gather(taak_a, taak_b)

    assert ("vraag-A", KEY_A) in AANROEPEN
    assert ("vraag-B", KEY_B) in AANROEPEN
    assert ("vraag-A", KEY_B) not in AANROEPEN
    assert ("vraag-B", KEY_A) not in AANROEPEN


async def test_sleutel_is_geredigeerd_tijdens_maar_niet_onthouden_erna(host):
    """Het log-vangnet kent de sleutel zolang die in gebruik is, daarna niet meer.

    KEY_A heeft bewust géén herkenbare vorm (geen `sk-`-voorvoegsel): dat is
    precies het geval — een VLAM/UbiOps-token — dat patroonherkenning mist.
    """
    await _drain(
        host.chat_stream(
            "s1", "hoi", mode="claude", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
        )
    )

    assert TIJDENS_VERZOEK, "de LLM-call is niet gedaan"
    assert KEY_A not in TIJDENS_VERZOEK[0], (
        "tijdens het verzoek hoort de sleutel uit een logregel geredigeerd te worden"
    )
    assert log_redaction.REDACTED in TIJDENS_VERZOEK[0]
    # En daarna: niet langer vasthouden dan de client zelf (PDR-010).
    assert KEY_A in log_redaction.redact(f"fout met {KEY_A}"), (
        "na afloop hoort de sleutel niet meer geregistreerd te staan"
    )


async def test_override_client_wordt_gesloten_na_de_stream(host):
    await _drain(
        host.chat_stream(
            "s1", "hoi", mode="claude", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
        )
    )
    assert _FakeClaude.gemaakt, "er is geen override-client aangemaakt"
    assert all(c.gesloten for c in _FakeClaude.gemaakt), (
        "een override-client is niet gesloten; de sleutel en de httpx-pool "
        "blijven dan na het verzoek in leven"
    )


async def test_override_client_wordt_gesloten_na_blocking_chat(host):
    await host.chat(
        "s1", "hoi", mode="claude", session_kvk=KVK_A, claude_api_key_override=KEY_A
    )
    assert _FakeClaude.gemaakt
    assert all(c.gesloten for c in _FakeClaude.gemaakt)


async def test_vlam_override_client_wordt_gesloten_na_de_stream(host):
    """Spiegel van de claude-variant: ook de vlam-override moet dicht.

    Zonder deze test wordt `_FakeVlam.gesloten` nergens getoetst.
    """
    await _drain(
        host.chat_stream(
            "s1", "hoi", mode="vlam", session_kvk=KVK_A,
            vlam_api_key_override=KEY_A,
        )
    )
    assert _FakeVlam.gemaakt, "er is geen vlam-override-client aangemaakt"
    assert all(c.gesloten for c in _FakeVlam.gemaakt)


async def test_alleen_de_client_van_de_gevraagde_mode_wordt_gebouwd(host):
    """Beide headers, één mode: de ongebruikte client wordt niet gebouwd.

    Een clientconstructie kost een geparste CA-bundel in de event loop, en de
    tweede client doet in dit verzoek geen enkele call.
    """
    await _drain(
        host.chat_stream(
            "s1", "hoi", mode="claude", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
            vlam_api_key_override=KEY_B,
        )
    )
    assert len(_FakeClaude.gemaakt) == 1
    assert _FakeVlam.gemaakt == [], (
        "de vlam-client is gebouwd terwijl mode=claude; die doet geen enkele call"
    )
    # En andersom, zodat dit geen eenzijdige assertie is.
    await _drain(
        host.chat_stream(
            "s2", "hoi", mode="vlam", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
            vlam_api_key_override=KEY_B,
        )
    )
    assert len(_FakeVlam.gemaakt) == 1
    assert len(_FakeClaude.gemaakt) == 1, "er is een tweede claude-client gebouwd"


async def test_afgebroken_stream_sluit_de_client_en_vergeet_de_sleutel(host, monkeypatch):
    """Het meest voorkomende faalpad: de gebruiker sluit het tabblad.

    De stream wordt dan halverwege ge-`aclose()`d. Draait de opruiming niet, dan
    blijft de sleutel procesbreed in het redactie-register staan — precies de
    kernclaim van PDR-010 §2 — en blijft de client met sleutel open.

    De agentic loop yieldt pas ná de LLM-call; om áfgebroken te worden terwijl
    de client-scope openstaat, vervangen we die loop door een generator met een
    yield ervóór.
    """

    async def nep_stream(messages, session_kvk, claude):
        yield {"type": "status", "message": "bezig"}
        yield {"type": "answer", "message": "klaar"}

    monkeypatch.setattr(host, "_chat_claude_stream", nep_stream)

    gen = host.chat_stream(
        "s1", "hoi", mode="claude", session_kvk=KVK_A, claude_api_key_override=KEY_A
    )
    await gen.__anext__()  # "Vraag analyseren…" — nog vóór de client-scope
    await gen.__anext__()  # "bezig" — nu staat de scope open
    await gen.aclose()

    assert _FakeClaude.gemaakt, "er is geen override-client aangemaakt"
    assert all(c.gesloten for c in _FakeClaude.gemaakt), (
        "een afgebroken stream liet de override-client open staan"
    )
    assert KEY_A in log_redaction.redact(f"fout met {KEY_A}"), (
        "na een afgebroken stream staat de sleutel nog in het redactie-register"
    )


async def test_afbreken_midden_in_de_llm_call_ruimt_op(host, monkeypatch):
    """Zelfde opruiming, maar afgebroken terwijl de LLM-call loopt.

    Hier komt de annulering binnen als `CancelledError` — die erft van
    `BaseException` en werd door de opruimlus niet als zodanig behandeld.
    """
    in_de_call = asyncio.Event()

    async def blokkeer(**kwargs):
        in_de_call.set()
        await asyncio.Event().wait()  # nooit klaar

    monkeypatch.setattr(_FakeClaude, "_create", lambda self, **kw: blokkeer(**kw))

    taak = asyncio.create_task(
        _drain(
            host.chat_stream(
                "s1", "hoi", mode="claude", session_kvk=KVK_A,
                claude_api_key_override=KEY_A,
            )
        )
    )
    await in_de_call.wait()
    taak.cancel()
    with pytest.raises(asyncio.CancelledError):
        await taak

    assert all(c.gesloten for c in _FakeClaude.gemaakt), (
        "de override-client bleef open na annulering midden in de LLM-call"
    )
    assert KEY_A in log_redaction.redact(f"fout met {KEY_A}")


async def test_fout_tijdens_sluiten_gaat_geredigeerd_de_logs_in(host, monkeypatch):
    """De redactie moet het sluiten omvatten, niet alleen het opbouwen.

    Stond het `finally` búiten de `redact_temporarily`-scope, dan was de
    registratie al afgelopen op het moment dat een httpx-fout uit `close()` de
    logs bereikte — en stond de sleutel er alsnog in.
    """
    stroom = io.StringIO()
    handler = logging.StreamHandler(stroom)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log = logging.getLogger("vlam.host")
    log.addHandler(handler)
    log_redaction.install_redaction()

    async def kapotte_close(self):
        raise ValueError(f"upstream weigerde sleutel {self.api_key}")

    monkeypatch.setattr(_FakeClaude, "close", kapotte_close)
    try:
        await _drain(
            host.chat_stream(
                "s1", "hoi", mode="claude", session_kvk=KVK_A,
                claude_api_key_override=KEY_A,
            )
        )
    finally:
        log.removeHandler(handler)

    uitvoer = stroom.getvalue()
    assert "Sluiten van request-client" in uitvoer, "de fout is niet gelogd"
    assert KEY_A not in uitvoer, (
        "de sleutel stond ongeredigeerd in de logregel over het mislukte sluiten"
    )
    assert log_redaction.REDACTED in uitvoer


async def test_falende_constructor_laat_de_sleutel_niet_achter(host, monkeypatch):
    """Gaat het opbouwen van de client mis, dan blijft er niets van hangen.

    De registratie gebeurt vóór de constructie — juist zodat een fout tijdens
    het opbouwen geredigeerd de logs in gaat — dus moet ze ook opruimen als die
    constructie gooit.

    Sinds PDR-011 ontsnapt zo'n fout niet meer uit de generator maar wordt hij
    een `HOST_FOUT`-event. Dat is de betere afloop: de client krijgt een nette
    melding plus `done` in plaats van een afgekapte stream. De eis die hier
    getoetst wordt is ongewijzigd — de sleutel mag niet blijven hangen.
    """

    def _kapot(**kwargs):
        raise RuntimeError("kan de client niet opbouwen")

    monkeypatch.setattr(vlam_host.anthropic, "AsyncAnthropic", _kapot)

    events = [
        e
        async for e in host.chat_stream(
            "s1", "hoi", mode="claude", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
        )
    ]
    assert any(e.get("code") == "HOST_FOUT" for e in events), (
        f"geen nette melding bij een falende clientconstructie: "
        f"{[e.get('code') or e.get('type') for e in events]}"
    )

    assert KEY_A in log_redaction.redact(f"fout met {KEY_A}"), (
        "de sleutel bleef geregistreerd nadat de clientconstructie faalde"
    )


def test_server_sleutels_worden_blijvend_geregistreerd(monkeypatch):
    """`VLAMHost.__init__` meldt de server-env-sleutels aan bij het vangnet.

    Die twee regels waren nergens gedekt: schrappen brak niets.

    Bewust een vormloze waarde: met een `sk-ant-`-voorvoegsel zou een patroon
    hem ook zonder registratie pakken, en dan toetst de test niets.
    """
    server_sleutel = "serversleutel1234567890abc"
    monkeypatch.setattr(vlam_host, "ANTHROPIC_API_KEY", server_sleutel)
    monkeypatch.setattr(vlam_host.anthropic, "AsyncAnthropic", _FakeClaude)

    vlam_host.VLAMHost()

    geredigeerd = log_redaction.redact(f"upstream weigerde {server_sleutel}")
    assert server_sleutel not in geredigeerd
    assert log_redaction.REDACTED in geredigeerd


async def test_opruimen_slaat_geen_client_over_bij_annulering():
    """Unit op de opruimlus: een `CancelledError` mag de rest niet overslaan.

    De annulering hoort daarna alsnog door te komen, anders verdwijnt een
    afbreking stilletjes.
    """

    class _Weigert:
        gesloten = False

        async def close(self):
            raise asyncio.CancelledError

    class _Werkt:
        def __init__(self):
            self.gesloten = False

        async def close(self):
            self.gesloten = True

    tweede = _Werkt()
    with pytest.raises(asyncio.CancelledError):
        await vlam_host.VLAMHost._close_request_clients([_Weigert(), tweede])
    assert tweede.gesloten, "de tweede client werd overgeslagen na een CancelledError"


async def test_gelijktijdige_gesprekken_overlappen_echt_binnen_de_llm_call(host):
    """A zit ín zijn LLM-call wanneer B binnenkomt.

    De andere interleaving-tests pauzeren op het eerste status-event, dus vóór
    het `async with _request_clients`; de twee scopes overlappen daar nog niet.
    Hier blokkeert de fake `create` op een event, zodat de scope van A
    aantoonbaar openstaat terwijl B er een opent.
    """
    a_zit_in_de_call = asyncio.Event()
    laat_a_door = asyncio.Event()
    origineel = _FakeClaude._create

    async def _create(self, **kwargs):
        vraag = next(
            (m["content"] for m in kwargs["messages"] if m.get("role") == "user"), "?"
        )
        if vraag == "vraag-A":
            a_zit_in_de_call.set()
            await laat_a_door.wait()
        return await origineel(self, **kwargs)

    _FakeClaude._create = _create
    try:
        taak_a = asyncio.create_task(
            _drain(
                host.chat_stream(
                    "sessie-a", "vraag-A", mode="claude", session_kvk=KVK_A,
                    claude_api_key_override=KEY_A,
                )
            )
        )
        await a_zit_in_de_call.wait()
        # B doet zijn volledige verzoek terwijl A binnen zijn scope hangt.
        await _drain(
            host.chat_stream(
                "sessie-b", "vraag-B", mode="claude", session_kvk=KVK_B,
                claude_api_key_override=KEY_B,
            )
        )
        laat_a_door.set()
        await taak_a
    finally:
        _FakeClaude._create = origineel

    assert ("vraag-A", KEY_A) in AANROEPEN
    assert ("vraag-B", KEY_B) in AANROEPEN
    assert ("vraag-A", KEY_B) not in AANROEPEN
    assert ("vraag-B", KEY_A) not in AANROEPEN


async def test_server_clients_blijven_onaangeraakt(host):
    server_claude, server_vlam = host.claude_client, host.vlam_client

    await _drain(
        host.chat_stream(
            "s1", "hoi", mode="claude", session_kvk=KVK_A,
            claude_api_key_override=KEY_A,
        )
    )

    # Geen spoor van het verzoek in de gedeelde state: exact dezelfde objecten,
    # en de sleutel van de gebruiker zit er niet in.
    assert host.claude_client is server_claude
    assert host.vlam_client is server_vlam
    assert host.claude_client.api_key != KEY_A
    assert host.claude_client not in _FakeClaude.gemaakt

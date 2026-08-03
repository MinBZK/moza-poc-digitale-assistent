"""Sleutels blijven binnen één verzoek (MVP-02).

De host is één gedeeld object en de endpoints zijn async. Vóór MVP-02 zette
`chat`/`chat_stream` de per-verzoek client op `self.claude_client` /
`self.vlam_client` en herstelde die in een `finally`. Bij twee gelijktijdige
gesprekken kon daardoor de sleutel van gebruiker A het verzoek van gebruiker B
bedienen — en procesbreed blijven staan nadat A weg was.

Deze tests forceren precies die interleaving en falen op de oude implementatie:

  1. A start (mutatie van de gedeelde state gebeurde daar)
  2. B start (overschrijft de gedeelde state)
  3. A doet zijn LLM-call → las de client van B

Daarnaast borgen we dat een override-client na afloop gesloten wordt (de sleutel
overleeft het verzoek niet en de httpx-pool lekt niet weg) en dat de
server-env-clients onaangeraakt blijven.
"""

import types

import pytest

import vlam_host

KVK_A = "85234567"
KVK_B = "62345681"
KEY_A = "sleutel-van-A"
KEY_B = "sleutel-van-B"


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


@pytest.fixture
def host(monkeypatch):
    """Host met echte server-env-clients, maar fakes voor override-clients.

    Volgorde is bewust: eerst de host bouwen (die krijgt de echte, lege
    server-env-clients), daarna de SDK-klassen patchen. Zo kunnen we ook
    controleren dat de server-clients níét zijn aangeraakt of gesloten.
    """
    AANROEPEN.clear()
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

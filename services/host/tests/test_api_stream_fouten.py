"""Een SSE-stream eindigt altijd op `done`, ook als er iets misgaat (MVP-02).

Status 200 is bij de eerste byte al verstuurd, dus een fout halverwege kan niet
meer als HTTP-status naar buiten. Zonder afhandeling krijgt de UI een afgekapte
respons zónder `error` en zónder `done`, en blijft ze in "Nadenken…" hangen.

De fouten hieronder zijn de soorten die de nauwe `except (TimeoutError,
APIError)` in de agentic loops niet vangt: een kapot tool-resultaat, een
verbindingsfout, een ontbrekende sleutel in een respons.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import json  # noqa: E402

import api  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(api.app)

KVK = "85234567"
GEHEIM = "sk-ant-ZEER-GEHEIM-1234567890"


@pytest.fixture(autouse=True)
def _sessie(monkeypatch):
    monkeypatch.setattr(api, "kvk_uit_header", lambda w: KVK if w == KVK else None)
    monkeypatch.setattr(api, "ALLOW_API_KEY_OVERRIDE", True)


def _events(tekst: str) -> list[tuple[str, dict]]:
    """Ontleed een SSE-body tot (event-naam, payload)-paren."""
    uit = []
    for blok in tekst.strip().split("\n\n"):
        naam = payload = None
        for regel in blok.splitlines():
            if regel.startswith("event: "):
                naam = regel[len("event: ") :]
            elif regel.startswith("data: "):
                payload = json.loads(regel[len("data: ") :])
        if naam:
            uit.append((naam, payload))
    return uit


def _stream(headers: dict | None = None) -> list[tuple[str, dict]]:
    r = client.post(
        "/chat/stream",
        json={"message": "hoi"},
        headers={"X-Test-User": KVK, **(headers or {})},
    )
    assert r.status_code == 200
    return _events(r.text)


FOUTEN = [
    pytest.param(
        json.JSONDecodeError("Expecting value", "", 0), id="kapot-tool-resultaat"
    ),
    pytest.param(KeyError("lopende_zaak"), id="ontbrekende-sleutel"),
    pytest.param(ConnectionError("upstream weg"), id="verbindingsfout"),
]


@pytest.mark.parametrize("fout", FOUTEN)
def test_fout_halverwege_geeft_error_en_done(fout, monkeypatch):
    """Elke fout buiten de nauwe except-clausules sluit de stream netjes af."""

    async def _stukke_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        yield {"type": "status", "message": "Vraag analyseren…"}
        raise fout

    monkeypatch.setattr(api.host, "chat_stream", _stukke_stream)

    events = _stream()
    namen = [naam for naam, _ in events]
    assert namen == ["status", "error", "done"], (
        f"de stream sloot niet af met error + done: {namen}"
    )


def test_foutmelding_bevat_geen_exception_inhoud(monkeypatch):
    """De respons hangt niet aan de inhoud van een exception.

    Een exception-tekst kan een sleutel, een pad of een KvK-nummer dragen; de
    client krijgt daarom een vaste tekst (CodeQL py/stack-trace-exposure).
    """

    async def _stukke_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        yield {"type": "status", "message": "Vraag analyseren…"}
        raise RuntimeError(f"upstream weigerde {GEHEIM} voor kvk {KVK}")

    monkeypatch.setattr(api.host, "chat_stream", _stukke_stream)

    r = client.post(
        "/chat/stream", json={"message": "hoi"}, headers={"X-Test-User": KVK}
    )
    assert GEHEIM not in r.text
    assert "upstream weigerde" not in r.text
    assert api.STREAM_ERROR_MESSAGE in r.text


def test_fout_vóór_het_eerste_event_geeft_ook_error_en_done(monkeypatch):
    """Ook als de generator al bij het eerste `__anext__` stukloopt."""

    async def _stukke_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        raise RuntimeError("meteen kapot")
        yield  # pragma: no cover — maakt dit een async generator

    monkeypatch.setattr(api.host, "chat_stream", _stukke_stream)

    assert [naam for naam, _ in _stream()] == ["error", "done"]


def test_geslaagde_stream_blijft_ongewijzigd(monkeypatch):
    """Vangnet: de gelukkige route mag hier niet door veranderen."""

    async def _goede_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        yield {"type": "status", "message": "Vraag analyseren…"}
        yield {"type": "answer", "message": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(api.host, "chat_stream", _goede_stream)

    events = _stream()
    assert [naam for naam, _ in events] == ["status", "answer", "done"]
    antwoord = next(payload for naam, payload in events if naam == "answer")
    assert antwoord["session_id"] and antwoord["mode"] == "vlam"


def test_afgebroken_stream_sluit_de_binnenste_generator(monkeypatch):
    """`aclosing`: bij een disconnect wordt de host-generator meteen gesloten.

    Zonder dat blijft die opgeschort staan tot asyncgen-finalisatie, en draait de
    opruiming van `_request_clients` — die de sleutel uit het redactie-register
    haalt — pas ronden later, of niet.
    """
    opgeruimd = []

    async def _lange_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        try:
            yield {"type": "status", "message": "Vraag analyseren…"}
            yield {"type": "status", "message": "nog bezig"}
            yield {"type": "answer", "message": "ok"}
        finally:
            opgeruimd.append(True)

    monkeypatch.setattr(api.host, "chat_stream", _lange_stream)

    with client.stream(
        "POST", "/chat/stream", json={"message": "hoi"}, headers={"X-Test-User": KVK}
    ) as r:
        next(r.iter_lines())  # één regel lezen, dan weglopen

    assert opgeruimd, "de binnenste generator is niet gesloten na het afbreken"

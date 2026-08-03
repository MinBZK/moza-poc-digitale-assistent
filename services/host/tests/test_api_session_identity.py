"""Endpoint-laag: bedrijfsidentiteit via de `X-Test-User`-header (MVP-01/PDR-009).

De header draagt het KvK-nummer van de gekozen persona. Buiten de allowlist =>
de host blokkeert hard (nette melding, geen LLM/bron). Erbinnen => het nummer
gaat door naar de host, die het bij elke bron-aanroep injecteert.

Draait netwerkloos (geen lifespan => geen MCP-servers, geen LLM-calls: host.chat
wordt gemonkeypatcht tot een recorder).
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(api.app)

_ALLOWLIST = {"85234567", "68750110"}


def _fake_allowlist_check(waarde):
    kvk = (waarde or "").strip()
    return kvk if kvk in _ALLOWLIST else None


def _install_recorder(monkeypatch):
    """Vervang host.chat door een recorder die de doorgegeven session_kvk vangt."""
    captured = {}

    async def _fake_chat(session_id, message, mode="vlam", session_kvk="", **kw):
        captured["session_kvk"] = session_kvk
        captured["called"] = True
        return "ok"

    monkeypatch.setattr(api, "kvk_uit_header", _fake_allowlist_check)
    monkeypatch.setattr(api.host, "chat", _fake_chat)
    return captured


def test_chat_zonder_header_blokkeert_hard(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post("/chat", json={"message": "wat zijn mijn bedrijfsgegevens?"})
    assert r.status_code == 401
    assert "log eerst in" in r.text.lower()
    # Geen enkele bron/LLM geraadpleegd.
    assert captured.get("called") is not True


def test_chat_kvk_buiten_allowlist_blokkeert_hard(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post(
        "/chat",
        json={"message": "hoi"},
        headers={"X-Test-User": "99999999"},
    )
    assert r.status_code == 401
    assert captured.get("called") is not True


def test_toegestaan_kvk_gaat_door_naar_de_host(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post(
        "/chat",
        json={"message": "hoi"},
        headers={"X-Test-User": "85234567"},
    )
    assert r.status_code == 200
    assert captured["session_kvk"] == "85234567"


def test_twee_persona_s_geven_elk_eigen_kvk(monkeypatch):
    captured = _install_recorder(monkeypatch)
    client.post("/chat", json={"message": "x"}, headers={"X-Test-User": "85234567"})
    assert captured["session_kvk"] == "85234567"
    client.post("/chat", json={"message": "x"}, headers={"X-Test-User": "68750110"})
    assert captured["session_kvk"] == "68750110"


def test_chat_stream_zonder_header_blokkeert_hard(monkeypatch):
    called = {"stream": False}

    async def _fake_stream(*a, **k):
        called["stream"] = True
        yield {"type": "answer", "message": "mag niet"}

    monkeypatch.setattr(api, "kvk_uit_header", _fake_allowlist_check)
    monkeypatch.setattr(api.host, "chat_stream", _fake_stream)

    r = client.post("/chat/stream", json={"message": "hoi"})
    assert "log eerst in" in r.text.lower()
    assert called["stream"] is False

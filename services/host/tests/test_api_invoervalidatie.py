"""Een lege of buitensporig lange vraag krijgt meteen een concrete melding.

Zonder deze check ging een leeg bericht gewoon naar het LLM en kwam de gebruiker
verderop uit bij een vage fout; een bericht zonder bovengrens belandde ongelezen
in de gespreksgeschiedenis. Beide endpoints controleren dit vóór er een LLM of
een bron in beeld komt: de recorder mag niet aangeroepen worden.

Draait netwerkloos (geen lifespan => geen MCP-servers, geen LLM-calls).
"""

import json
import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from config import MAX_VRAAG_TEKENS  # noqa: E402

client = TestClient(api.app)

KVK = "85234567"
HEADERS = {"X-Test-User": KVK}


def _install_recorder(monkeypatch):
    """Vervang de host door recorders, zodat we zien of er iets is aangeroepen."""
    captured = {"called": False}

    async def _fake_chat(session_id, message, mode="vlam", session_kvk="", **kw):
        captured["called"] = True
        return "ok"

    async def _fake_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        captured["called"] = True
        yield {"type": "answer", "message": "ok"}

    monkeypatch.setattr(api, "kvk_uit_header", lambda w: KVK if (w or "").strip() == KVK else None)
    monkeypatch.setattr(api.host, "chat", _fake_chat)
    monkeypatch.setattr(api.host, "chat_stream", _fake_stream)
    return captured


def _events(response) -> list[dict]:
    """Parse de SSE-body tot een lijst payloads."""
    payloads = []
    for blok in response.text.split("\n\n"):
        for regel in blok.split("\n"):
            if regel.startswith("data: "):
                payloads.append(json.loads(regel[6:]))
    return payloads


def test_lege_vraag_wordt_geweigerd_met_een_voorbeeld(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post("/chat", json={"message": "   "}, headers=HEADERS)
    assert r.status_code == 400
    assert "geen vraag" in r.text.lower()
    # De melding vertelt ook wat de gebruiker dan wel kan doen.
    assert "energiebesparingsplicht" in r.text
    assert captured["called"] is False


def test_te_lange_vraag_noemt_de_grens(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post(
        "/chat", json={"message": "a" * (MAX_VRAAG_TEKENS + 1)}, headers=HEADERS
    )
    assert r.status_code == 413
    assert str(MAX_VRAAG_TEKENS) in r.text
    assert captured["called"] is False


def test_vraag_op_de_grens_gaat_gewoon_door(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post("/chat", json={"message": "a" * MAX_VRAAG_TEKENS}, headers=HEADERS)
    assert r.status_code == 200
    assert captured["called"] is True


def test_stream_geeft_een_error_event_bij_lege_vraag(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post("/chat/stream", json={"message": ""}, headers=HEADERS)
    assert r.status_code == 200  # SSE: de fout zit in het event, niet in de status
    payloads = _events(r)
    assert payloads[0]["code"] == "LEGE_VRAAG"
    assert payloads[0]["actie"].strip()
    assert payloads[-1]["type"] == "done", "de stream hoort netjes af te sluiten"
    assert captured["called"] is False


def test_stream_geeft_een_error_event_bij_te_lange_vraag(monkeypatch):
    captured = _install_recorder(monkeypatch)
    r = client.post(
        "/chat/stream",
        json={"message": "a" * (MAX_VRAAG_TEKENS + 1)},
        headers=HEADERS,
    )
    payloads = _events(r)
    assert payloads[0]["code"] == "VRAAG_TE_LANG"
    assert captured["called"] is False


def test_sessiecontrole_gaat_voor_op_invoercontrole(monkeypatch):
    """Zonder sessie hoort de gebruiker eerst te horen dat hij moet inloggen."""
    _install_recorder(monkeypatch)
    r = client.post("/chat", json={"message": ""})
    assert r.status_code == 401
    assert "log eerst in" in r.text.lower()

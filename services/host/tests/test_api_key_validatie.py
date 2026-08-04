"""Sleutel-headers worden op vorm getoetst vóór gebruik (MVP-02).

Een sleutel met een regeleinde erin komt niet door de HTTP-clientbibliotheek
heen; die gooit een fout waarvan de binnenste melding de *volledige sleutel*
bevat. We weigeren zulke waarden daarom aan de voordeur, en de melding die de
gebruiker terugkrijgt mag niets van de waarde prijsgeven.

Draait netwerkloos: `host.chat`/`host.chat_stream` zijn recorders.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(api.app)

KVK = "85234567"
GEHEIM = "sk-ant-ZEER-GEHEIM-1234567890"


@pytest.fixture(autouse=True)
def _sessie_en_recorder(monkeypatch):
    """Geldige sessie + een host die niets echt aanroept."""
    captured = {}

    async def _fake_chat(session_id, message, mode="vlam", session_kvk="", **kw):
        captured["keys"] = kw
        return "ok"

    async def _fake_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        captured["keys"] = kw
        yield {"type": "answer", "message": "ok"}

    monkeypatch.setattr(api, "kvk_uit_header", lambda w: KVK if w == KVK else None)
    monkeypatch.setattr(api, "ALLOW_API_KEY_OVERRIDE", True)
    monkeypatch.setattr(api.host, "chat", _fake_chat)
    monkeypatch.setattr(api.host, "chat_stream", _fake_stream)
    return captured


def _headers(sleutel: str) -> dict:
    return {"X-Test-User": KVK, "x-claude-api-key": sleutel}


# Wat een browser daadwerkelijk over de lijn kan zetten. Stuurtekens en
# niet-ASCII komen niet door de HTTP-laag heen (de testclient weigert ze al bij
# het opbouwen van het verzoek), dus die toetsen we een niveau lager, direct op
# `_valideer_sleutel`.
ONGELDIG = [
    pytest.param(f"{GEHEIM} met spatie", id="witruimte"),
    pytest.param("kort", id="te-kort"),
    pytest.param("sk-ant-" + "a" * 600, id="te-lang"),
]


@pytest.mark.parametrize("sleutel", ONGELDIG)
def test_chat_weigert_ongeldige_sleutel(sleutel, _sessie_en_recorder):
    r = client.post("/chat", json={"message": "hoi"}, headers=_headers(sleutel))
    assert r.status_code == 400
    assert "ongeldige vorm" in r.text.lower()
    # Niets van de waarde in het antwoord, en de host is niet aangeroepen.
    assert sleutel not in r.text
    assert GEHEIM not in r.text
    assert "keys" not in _sessie_en_recorder


@pytest.mark.parametrize("sleutel", ONGELDIG)
def test_chat_stream_weigert_ongeldige_sleutel(sleutel, _sessie_en_recorder):
    r = client.post("/chat/stream", json={"message": "hoi"}, headers=_headers(sleutel))
    # SSE-route: geen 400 maar een error-event, zodat de UI het contract volgt.
    assert r.status_code == 200
    assert "event: error" in r.text
    assert "ongeldige vorm" in r.text.lower()
    assert sleutel not in r.text
    assert GEHEIM not in r.text
    assert "keys" not in _sessie_en_recorder


def test_geldige_sleutel_gaat_gewoon_door(_sessie_en_recorder):
    r = client.post("/chat", json={"message": "hoi"}, headers=_headers(GEHEIM))
    assert r.status_code == 200
    assert _sessie_en_recorder["keys"]["claude_api_key_override"] == GEHEIM


def test_zonder_sleutel_geen_override(_sessie_en_recorder):
    r = client.post("/chat", json={"message": "hoi"}, headers={"X-Test-User": KVK})
    assert r.status_code == 200
    assert _sessie_en_recorder["keys"]["claude_api_key_override"] == ""


def test_override_uit_negeert_de_header(monkeypatch, _sessie_en_recorder):
    """Met ALLOW_API_KEY_OVERRIDE=false wordt de header genegeerd, niet geweigerd."""
    monkeypatch.setattr(api, "ALLOW_API_KEY_OVERRIDE", False)
    r = client.post("/chat", json={"message": "hoi"}, headers=_headers("kort"))
    assert r.status_code == 200
    assert _sessie_en_recorder["keys"]["claude_api_key_override"] == ""


def test_geweigerde_sleutel_komt_niet_in_de_log(caplog, _sessie_en_recorder):
    with caplog.at_level("WARNING"):
        client.post("/chat", json={"message": "hoi"}, headers=_headers(f"{GEHEIM} x"))
    assert caplog.text, "de weigering hoort wél zichtbaar te zijn in de log"
    assert "x-claude-api-key" in caplog.text  # welke header, niet welke waarde
    assert GEHEIM not in caplog.text


# --- Direct op de validator ---------------------------------------------------
#
# Stuurtekens en niet-ASCII halen de HTTP-laag niet, maar de checks staan er wel
# met een reden. Niet-ASCII laat de uitgaande LLM-call stuklopen op een
# UnicodeEncodeError — die valt buiten `except (TimeoutError, APIError)` en geeft
# dus een onafgevangen 500 of een afgebroken SSE-stream. Een stuurteken levert
# een fout op waarvan de binnenste melding de volledige sleutel bevat.


@pytest.mark.parametrize(
    "sleutel",
    [
        pytest.param("sk-ant-geheim-éé", id="niet-ascii"),
        pytest.param("sk-ant-geheim\nX-Evil: 1", id="regeleinde"),
        pytest.param("sk-ant-geheim\ttab", id="tab"),
        pytest.param("sk-ant-geheim\x00nul", id="nul-byte"),
    ],
)
def test_validator_weigert_onbruikbare_waarden(sleutel):
    with pytest.raises(api.OngeldigeSleutel) as excinfo:
        api._valideer_sleutel(sleutel, "x-claude-api-key")
    # De melding aan de gebruiker verklapt niets van de waarde.
    assert "geheim" not in str(excinfo.value)


def test_validator_laat_een_normale_sleutel_door():
    assert api._valideer_sleutel(GEHEIM, "x-claude-api-key") == GEHEIM


def test_validator_beschouwt_leeg_als_geen_override():
    assert api._valideer_sleutel("", "x-claude-api-key") == ""


def test_rauwe_mode_wordt_niet_in_de_log_geëchood(caplog, _sessie_en_recorder):
    """Regressie: `body.mode` ging ongefilterd en zonder lengtegrens de log in.

    Dat was de route waarlangs een verzoek van 64 KB de logverwerking — en
    daarmee de event loop — tientallen seconden bezet hield (CodeQL
    py/polynomial-redos op de redactiepatronen). De logregel noemt nu alleen de
    gevalideerde mode plus of er iets afwijkends gevraagd werd.
    """
    kwaadaardig = "a-" * 500
    with caplog.at_level("INFO", logger="vlam.api"):
        r = client.post(
            "/chat/stream",
            json={"message": "hoi", "mode": kwaadaardig},
            headers={"X-Test-User": KVK},
        )
    assert r.status_code == 200
    assert kwaadaardig not in caplog.text
    assert "afwijkende mode" in caplog.text  # wél zichtbaar dát het afweek
    assert "'vlam'" in caplog.text  # en waarop is teruggevallen

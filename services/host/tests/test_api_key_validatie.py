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

import log_redaction  # noqa: E402

client = TestClient(api.app)

KVK = "85234567"
GEHEIM = "sk-ant-ZEER-GEHEIM-1234567890"


@pytest.fixture(autouse=True)
def _schone_throttle():
    """De weiger-throttle is procesbrede state; die hoort niet te lekken."""
    api._reset_key_rejection_throttle()
    yield
    api._reset_key_rejection_throttle()


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
# `_validate_api_key`.
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
    with pytest.raises(api.InvalidApiKey) as excinfo:
        api._validate_api_key(sleutel, "x-claude-api-key")
    # De melding aan de gebruiker verklapt niets van de waarde.
    assert "geheim" not in str(excinfo.value)


def test_validator_laat_een_normale_sleutel_door():
    assert api._validate_api_key(GEHEIM, "x-claude-api-key") == GEHEIM


def test_validator_beschouwt_leeg_als_geen_override():
    assert api._validate_api_key("", "x-claude-api-key") == ""


# --- Log-flooding op een onauthenticeerd pad ---------------------------------


def test_herhaalde_weigeringen_vullen_de_log_niet(caplog):
    """`/chat` heeft geen authenticatie: iedereen kan weigeringen produceren.

    Ongethrottled is dat een WARNING per verzoek, op verzoeksnelheid
    (BIO 12.4.1/12.4.2).
    """
    with caplog.at_level("WARNING", logger="vlam.api"):
        for _ in range(50):
            with pytest.raises(api.InvalidApiKey):
                api._validate_api_key("kort", "x-claude-api-key")
    regels = [r for r in caplog.records if "geweigerd" in r.getMessage()]
    assert len(regels) == 1, f"50 weigeringen leverden {len(regels)} logregels op"


def test_onderdrukte_weigeringen_worden_alsnog_gemeld(caplog, monkeypatch):
    """Een aanhoudende stroom moet juist opvallen, niet verdwijnen."""
    monkeypatch.setattr(api, "_KEY_REJECTION_LOG_INTERVAL", 0.0)
    with caplog.at_level("WARNING", logger="vlam.api"):
        with pytest.raises(api.InvalidApiKey):
            api._validate_api_key("kort", "x-claude-api-key")
        # Binnen het venster: onderdrukt maar geteld.
        monkeypatch.setattr(api, "_KEY_REJECTION_LOG_INTERVAL", 60.0)
        for _ in range(4):
            with pytest.raises(api.InvalidApiKey):
                api._validate_api_key("kort", "x-claude-api-key")
        # Venster voorbij: de volgende weigering meldt wat er tussenin zat.
        monkeypatch.setattr(api, "_KEY_REJECTION_LOG_INTERVAL", 0.0)
        with pytest.raises(api.InvalidApiKey):
            api._validate_api_key("kort", "x-claude-api-key")
    assert "4 eerdere weigeringen onderdrukt" in caplog.text


# --- De grens tussen "geaccepteerd" en "door het vangnet gedekt" --------------


def test_ondergrens_is_die_van_het_log_vangnet():
    """De twee drempels mogen niet los van elkaar bestaan.

    Deden ze dat wel, dan liepen ze uit elkaar en ontstond er opnieuw een stil
    gat: een sleutel die de voordeur binnenkomt maar die het log-vangnet niet
    registreert, terwijl `config.py` en PDR-010 §5 redactie beloven.
    """
    assert api._MIN_API_KEY_LENGTH == log_redaction.MIN_UNTRUSTED_SECRET_LENGTH


@pytest.mark.parametrize(
    ("lengte", "geaccepteerd"),
    [
        pytest.param(log_redaction.MIN_UNTRUSTED_SECRET_LENGTH - 1, False, id="19"),
        pytest.param(log_redaction.MIN_UNTRUSTED_SECRET_LENGTH, True, id="20"),
        pytest.param(511, True, id="511"),
        pytest.param(512, True, id="512"),
        pytest.param(513, False, id="513"),
    ],
)
def test_lengterandes(lengte, geaccepteerd):
    """`<=`-vergelijkingen horen op hun randen getoetst te worden."""
    sleutel = ("sk1" + "a" * lengte)[:lengte]
    if geaccepteerd:
        assert api._validate_api_key(sleutel, "x-claude-api-key") == sleutel
        assert log_redaction.looks_like_a_key(sleutel), (
            "een geaccepteerde sleutel hoort registreerbaar te zijn"
        )
    else:
        with pytest.raises(api.InvalidApiKey):
            api._validate_api_key(sleutel, "x-claude-api-key")


def test_elke_geaccepteerde_lengte_is_registreerbaar():
    """Het gat van bevinding 4: geen enkele lengte valt er nog tussenin."""
    for lengte in range(api._MIN_API_KEY_LENGTH, api._MAX_API_KEY_LENGTH + 1):
        sleutel = ("sk1" + "a" * lengte)[:lengte]
        assert log_redaction.looks_like_a_key(api._validate_api_key(sleutel, "h"))


def test_sleutel_zonder_cijfer_wordt_gebruikt_maar_luid_gemeld(caplog):
    """Een vormloze sleutel zónder cijfer werkt wel, maar valt buiten het vangnet.

    Dat restje degradatie blijft bestaan — de registratie-eis houdt "sleutel
    opgeven" tegen als manier om logtekst te laten verdwijnen — maar het mag niet
    stil gebeuren.
    """
    sleutel = "a" * 30
    with caplog.at_level("WARNING", logger="vlam.api"):
        assert api._validate_api_key(sleutel, "x-vlam-api-key") == sleutel
    assert "buiten het log-vangnet" in caplog.text
    assert "x-vlam-api-key" in caplog.text
    assert sleutel not in caplog.text  # nog steeds nooit de waarde zelf


# --- Beide headers, niet alleen de claude-header ------------------------------


def test_vlam_header_gaat_ook_door_het_endpoint(_sessie_en_recorder):
    """`x-vlam-api-key` kwam nergens langs de endpoint-route."""
    r = client.post(
        "/chat",
        json={"message": "hoi"},
        headers={"X-Test-User": KVK, "x-vlam-api-key": GEHEIM},
    )
    assert r.status_code == 200
    assert _sessie_en_recorder["keys"]["vlam_api_key_override"] == GEHEIM
    assert _sessie_en_recorder["keys"]["claude_api_key_override"] == ""


def test_beide_headers_tegelijk(_sessie_en_recorder):
    vlam_sleutel = "vlamtoken-1234567890abcdef"
    r = client.post(
        "/chat",
        json={"message": "hoi"},
        headers={
            "X-Test-User": KVK,
            "x-vlam-api-key": vlam_sleutel,
            "x-claude-api-key": GEHEIM,
        },
    )
    assert r.status_code == 200
    assert _sessie_en_recorder["keys"]["vlam_api_key_override"] == vlam_sleutel
    assert _sessie_en_recorder["keys"]["claude_api_key_override"] == GEHEIM


def test_ongeldige_vlam_header_wordt_ook_geweigerd(_sessie_en_recorder):
    r = client.post(
        "/chat",
        json={"message": "hoi"},
        headers={"X-Test-User": KVK, "x-vlam-api-key": "kort"},
    )
    assert r.status_code == 400
    assert "keys" not in _sessie_en_recorder


@pytest.mark.parametrize("pad", ["/chat", "/chat/stream"])
def test_exception_inhoud_bereikt_de_client_nooit(monkeypatch, pad, _sessie_en_recorder):
    """Regressie op py/stack-trace-exposure: de respons hangt niet aan `str(e)`.

    Bewijst de eigenschap, niet de huidige tekst: wát er ook in de exception
    zit, de client krijgt alleen de vaste melding.
    """

    def _lekkende_validatie(value, header):
        raise api.InvalidApiKey(
            "INTERN: /opt/app/services/host/api.py regel 42, sleutel sk-ant-GEHEIM"
        )

    monkeypatch.setattr(api, "_validate_api_key", _lekkende_validatie)
    r = client.post(pad, json={"message": "hoi"}, headers=_headers(GEHEIM))

    assert "INTERN" not in r.text
    assert "api.py" not in r.text
    assert "sk-ant-GEHEIM" not in r.text
    assert api.INVALID_API_KEY_MESSAGE in r.text


def test_rauwe_mode_wordt_niet_in_de_log_geëchood(caplog, _sessie_en_recorder):
    """Regressie: `body.mode` ging ongefilterd en zonder lengtegrens de log in.

    Dat was de route waarlangs 64 KB de event loop tientallen seconden bezet
    hield. De logregel noemt nu alleen de gevalideerde mode.
    """
    malicious = "a-" * 500
    with caplog.at_level("INFO", logger="vlam.api"):
        r = client.post(
            "/chat/stream",
            json={"message": "hoi", "mode": malicious},
            headers={"X-Test-User": KVK},
        )
    assert r.status_code == 200
    assert malicious not in caplog.text
    assert "afwijkende mode" in caplog.text  # wél zichtbaar dát het afweek
    assert "'vlam'" in caplog.text  # en waarop is teruggevallen

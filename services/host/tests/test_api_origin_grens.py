"""De host waarschuwt als de origin-grens openstaat (MVP-02).

Let op de richting: leeg = strikt (geen cross-origin toegang, de stand voor de
deployment met een same-origin reverse proxy). `*` = open, en dat is wat een
waarschuwing verdient — zeker met de sleutel-override aan.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402


def _draai(monkeypatch, caplog, origins, override):
    monkeypatch.setattr(api, "ALLOWED_ORIGINS", origins)
    monkeypatch.setattr(api, "ALLOW_API_KEY_OVERRIDE", override)
    with caplog.at_level("WARNING", logger="vlam.api"):
        api.controleer_origin_grens()
    return caplog.text


def test_ster_waarschuwt(monkeypatch, caplog):
    tekst = _draai(monkeypatch, caplog, ["*"], False)
    assert "ALLOWED_ORIGINS staat op '*'" in tekst


def test_ster_met_override_benoemt_de_combinatie(monkeypatch, caplog):
    tekst = _draai(monkeypatch, caplog, ["*"], True)
    assert "eigen sleutel" in tekst


def test_ster_zonder_override_benoemt_de_combinatie_niet(monkeypatch, caplog):
    tekst = _draai(monkeypatch, caplog, ["*"], False)
    assert "ALLOWED_ORIGINS staat op '*'" in tekst
    assert "eigen sleutel" not in tekst


def test_leeg_is_de_strikte_stand_en_waarschuwt_niet(monkeypatch, caplog):
    assert _draai(monkeypatch, caplog, [], True) == ""


def test_concrete_whitelist_waarschuwt_niet(monkeypatch, caplog):
    tekst = _draai(monkeypatch, caplog, ["https://moza.overheid.nl"], True)
    assert tekst == ""


def test_whitelist_met_ster_ertussen_waarschuwt_wel(monkeypatch, caplog):
    tekst = _draai(monkeypatch, caplog, ["https://moza.overheid.nl", "*"], True)
    assert "ALLOWED_ORIGINS staat op '*'" in tekst

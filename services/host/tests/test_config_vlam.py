"""Guard: waar de host VLAM zoekt en welk model hij vraagt.

VLAM is alleen bereikbaar via de ZAD-dienst VLAM-API (die zet VLAM_API_URL);
VLAM_BASE_URL gaat daar expliciet voor. Zonder een van beide is er géén adres —
geen stille terugval op een hardcoded VLAM-project.

config.py leest env op import-tijd, dus we herladen de module met
gemonkeypatchte env per scenario.
"""

import importlib

import pytest


def _reload_config(monkeypatch, **env):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, str(value))
    import config

    return importlib.reload(config)


@pytest.fixture(autouse=True)
def herstel_config():
    # Laat de herladen module niet achter voor latere tests.
    yield
    import config

    importlib.reload(config)


@pytest.mark.parametrize(
    ("base_url", "api_url", "verwacht"),
    [
        (None, None, ""),
        ("", "", ""),
        ("   ", None, ""),
        (None, "http://vlam-api.svc:8080", "http://vlam-api.svc:8080/v1"),
        (None, "http://vlam-api.svc:8080/", "http://vlam-api.svc:8080/v1"),
        (None, "http://vlam-api.svc:8080//", "http://vlam-api.svc:8080/v1"),
        ("https://vlam.lokaal/v1", None, "https://vlam.lokaal/v1"),
        ("https://vlam.lokaal/v1", "http://vlam-api.svc:8080", "https://vlam.lokaal/v1"),
        ("", "http://vlam-api.svc:8080", "http://vlam-api.svc:8080/v1"),
    ],
)
def test_vlam_base_url_volgorde(monkeypatch, base_url, api_url, verwacht):
    cfg = _reload_config(monkeypatch, VLAM_BASE_URL=base_url, VLAM_API_URL=api_url)
    assert cfg.VLAM_BASE_URL == verwacht


@pytest.mark.parametrize(
    ("raw", "verwacht"),
    [
        (None, "Kimi-K3-prepaid"),
        ("", "Kimi-K3-prepaid"),
        ("vlam-llm-large-prepaid", "vlam-llm-large-prepaid"),
    ],
)
def test_vlam_model_id(monkeypatch, raw, verwacht):
    cfg = _reload_config(monkeypatch, VLAM_MODEL_ID=raw)
    assert cfg.VLAM_MODEL_ID == verwacht


@pytest.mark.parametrize(
    ("base_url", "override", "verwachte_code"),
    [
        # Geen adres: geen sleutel helpt, dus geen "vul uw sleutel in".
        ("", True, "LLM_NIET_INGESTELD"),
        ("", False, "LLM_NIET_INGESTELD"),
        # Wel een adres: de bestaande sleutelmelding.
        ("http://vlam-api.svc:8080/v1", True, "LLM_GEEN_SLEUTEL"),
        ("http://vlam-api.svc:8080/v1", False, "LLM_NIET_INGESTELD"),
    ],
)
def test_geen_vlam_adres_vraagt_niet_om_een_sleutel(
    monkeypatch, base_url, override, verwachte_code
):
    import vlam_host

    monkeypatch.setattr(vlam_host, "VLAM_BASE_URL", base_url)
    monkeypatch.setattr(vlam_host, "ALLOW_API_KEY_OVERRIDE", override)
    assert vlam_host._geen_sleutel_fout("vlam").code == verwachte_code


def test_claude_melding_hangt_niet_af_van_vlam_adres(monkeypatch):
    import vlam_host

    monkeypatch.setattr(vlam_host, "VLAM_BASE_URL", "")
    monkeypatch.setattr(vlam_host, "ALLOW_API_KEY_OVERRIDE", True)
    assert vlam_host._geen_sleutel_fout("claude").code == "LLM_GEEN_SLEUTEL"

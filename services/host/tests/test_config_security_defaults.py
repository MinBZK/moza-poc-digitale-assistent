"""Guard: de strenge security-defaults uit CLAUDE.md / config.py.

- ALLOWED_ORIGINS: leeg/ontbrekend => géén CORS (geen stille terugval op "*").
- ALLOW_API_KEY_OVERRIDE: default true; expliciet "false" zet hem uit.

config.py leest env op import-tijd, dus we herladen de module met
gemonkeypatchte env per scenario.
"""

import importlib

import pytest


def _reload_config(monkeypatch, **env):
    # Stub load_dotenv: tests mogen niet afhangen van een lokale .env. Alle
    # relevante waarden zetten we expliciet via monkeypatch hieronder.
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, str(value))
    import config

    return importlib.reload(config)


@pytest.mark.parametrize(
    ("raw", "verwacht"),
    [
        ("", []),
        ("   ", []),
        ("https://a.nl", ["https://a.nl"]),
        ("https://a.nl, https://b.nl", ["https://a.nl", "https://b.nl"]),
        ("*", ["*"]),
    ],
)
def test_allowed_origins_parsing(monkeypatch, raw, verwacht):
    cfg = _reload_config(monkeypatch, ALLOWED_ORIGINS=raw)
    assert cfg.ALLOWED_ORIGINS == verwacht


def test_allowed_origins_leeg_betekent_geen_cors(monkeypatch):
    cfg = _reload_config(monkeypatch, ALLOWED_ORIGINS="")
    # Leeg = geen enkele origin toegestaan (bewust geen "*"-terugval).
    assert cfg.ALLOWED_ORIGINS == []


@pytest.mark.parametrize(
    ("raw", "verwacht"),
    [
        ("true", True),
        ("True", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("0", False),
        ("nee", False),
        ("", False),
    ],
)
def test_allow_api_key_override_parsing(monkeypatch, raw, verwacht):
    cfg = _reload_config(monkeypatch, ALLOW_API_KEY_OVERRIDE=raw)
    assert cfg.ALLOW_API_KEY_OVERRIDE is verwacht


def test_allow_api_key_override_default_is_true_when_unset(monkeypatch):
    # Niet gezet => true, en dat is een bewuste keuze (PDR-010): de deployment
    # draait zonder LLM-sleutels, dus zonder deze default werkt de assistent
    # daar niet. Wie hem omzet, moet server-sleutels zetten. Expliciet geborgd
    # omdat het gedrag hier van afhangt. conftest forceert alleen de LLM-keys
    # leeg, daarom verwijderen we deze var hier zelf.
    cfg = _reload_config(monkeypatch, ALLOW_API_KEY_OVERRIDE=None)
    assert cfg.ALLOW_API_KEY_OVERRIDE is True

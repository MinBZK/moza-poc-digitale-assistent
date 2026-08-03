"""Guard: TEST_KVK_NUMMERS-allowlist en kvk_uit_header() (MVP-01, PDR-009).

config.py leest env op import-tijd, dus we herladen de module per scenario.
"""

import importlib


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


def test_allowlist_leeg_is_lege_verzameling(monkeypatch):
    cfg = _reload_config(monkeypatch, TEST_KVK_NUMMERS=None)
    assert cfg.TEST_KVK_NUMMERS == frozenset()


def test_allowlist_parst_meerdere_nummers(monkeypatch):
    cfg = _reload_config(
        monkeypatch, TEST_KVK_NUMMERS="85234567, 62345681,56789012"
    )
    assert cfg.TEST_KVK_NUMMERS == frozenset(
        {"85234567", "62345681", "56789012"}
    )


def test_allowlist_negeert_lege_stukken(monkeypatch):
    cfg = _reload_config(monkeypatch, TEST_KVK_NUMMERS="85234567, ,,  ,62345681")
    assert cfg.TEST_KVK_NUMMERS == frozenset({"85234567", "62345681"})


def test_bekend_nummer_wordt_geaccepteerd(monkeypatch):
    cfg = _reload_config(monkeypatch, TEST_KVK_NUMMERS="85234567")
    assert cfg.kvk_uit_header("85234567") == "85234567"
    # Whitespace rond de headerwaarde wordt genegeerd.
    assert cfg.kvk_uit_header("  85234567  ") == "85234567"


def test_nummer_buiten_de_allowlist_is_none(monkeypatch):
    # De kern: een willekeurig nummer meesturen geeft geen sessie.
    cfg = _reload_config(monkeypatch, TEST_KVK_NUMMERS="85234567")
    assert cfg.kvk_uit_header("62345681") is None
    assert cfg.kvk_uit_header("99999999") is None
    assert cfg.kvk_uit_header("") is None
    assert cfg.kvk_uit_header(None) is None


def test_lege_allowlist_laat_niemand_door(monkeypatch):
    # Vergeten env-var => iedereen krijgt "log eerst in", niemand krijgt data.
    cfg = _reload_config(monkeypatch, TEST_KVK_NUMMERS=None)
    assert cfg.kvk_uit_header("85234567") is None


def test_geen_token_indirectie_meer(monkeypatch):
    # Regressie: de oude token->kvk-map is weg.
    cfg = _reload_config(monkeypatch, TEST_KVK_NUMMERS="85234567")
    assert not hasattr(cfg, "TEST_USERS")
    assert not hasattr(cfg, "kvk_voor_token")
    assert cfg.kvk_uit_header("tok_claudia") is None

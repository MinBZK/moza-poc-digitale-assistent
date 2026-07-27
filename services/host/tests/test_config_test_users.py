"""Guard: TEST_USERS token->kvk mapping en kvk_voor_token() (MVP-01, PDR-009).

De host bepaalt de bedrijfsidentiteit server-side uit een vertrouwd token in de
`X-Test-User`-header. `config.TEST_USERS` mapt token->KvK-nummer; `kvk_voor_token`
resolvet een token naar het KvK-nummer van die testgebruiker (of None).

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


def test_test_users_leeg_is_lege_map(monkeypatch):
    cfg = _reload_config(monkeypatch, TEST_USERS=None)
    assert cfg.TEST_USERS == {}


def test_test_users_parst_meerdere_paren(monkeypatch):
    cfg = _reload_config(
        monkeypatch, TEST_USERS="tok_donald:68750110, tok_claudia:85234567"
    )
    assert cfg.TEST_USERS == {
        "tok_donald": "68750110",
        "tok_claudia": "85234567",
    }


def test_test_users_negeert_kapotte_paren(monkeypatch):
    # Lege stukken en paren zonder dubbele punt worden overgeslagen.
    cfg = _reload_config(monkeypatch, TEST_USERS="geen_dubbelepunt, ,tok:123, :leeg")
    assert cfg.TEST_USERS == {"tok": "123"}


def test_kvk_voor_token_resolvet_bekend_token(monkeypatch):
    cfg = _reload_config(monkeypatch, TEST_USERS="tok_claudia:85234567")
    assert cfg.kvk_voor_token("tok_claudia") == "85234567"
    # Whitespace rond het token wordt genegeerd.
    assert cfg.kvk_voor_token("  tok_claudia  ") == "85234567"


def test_kvk_voor_token_onbekend_of_leeg_is_none(monkeypatch):
    cfg = _reload_config(monkeypatch, TEST_USERS="tok_claudia:85234567")
    assert cfg.kvk_voor_token("onbekend") is None
    assert cfg.kvk_voor_token("") is None
    assert cfg.kvk_voor_token(None) is None

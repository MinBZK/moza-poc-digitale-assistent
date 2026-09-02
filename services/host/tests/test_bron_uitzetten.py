"""Een bron uitzetten hoort een keuze te zijn, geen storing.

`_resolve_server_path` valt bij een ontbrekende omgevingsvariabele terug op een
standaardpad, dus een server weglaten uit de configuratie schakelt hem niet uit -
hij start gewoon. De enige manier om hem weg te krijgen was hem laten falen, en
dan staat er een fout in de log voor iets dat je bewust deed.

Voor het gebruikersonderzoek is dit een echte knop: draait het onderzoek op
gegevens die de ondernemer zelf aanlevert, dan hoort de Business Wallet er niet
te zijn - en hoort de assistent hem ook niet te beloven.
"""

import importlib

import pytest


def _config_met(monkeypatch, **env):
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import config

    return importlib.reload(config)


@pytest.mark.parametrize("waarde", ["uit", "off", "none", "geen", "false", "no", "nee", "0", "disabled", " Uit "])
def test_een_uitzet_woord_schakelt_de_bron_uit(monkeypatch, waarde):
    config = _config_met(monkeypatch, MCP_SERVER_NETBEHEERDER=waarde)
    assert "netbeheerder" not in config.MCP_SERVERS
    assert config.MCP_SERVERS_UIT == {"netbeheerder": "MCP_SERVER_NETBEHEERDER"}
    assert "kvk" in config.MCP_SERVERS


@pytest.mark.parametrize("waarde", ["", "   "])
def test_een_lege_waarde_houdt_de_bron_aan(monkeypatch, waarde):
    """Leegmaken in een beheer-UI is de gewone handeling voor "terug naar
    standaard"; die mag de Business Wallet niet stil uitzetten."""
    config = _config_met(monkeypatch, MCP_SERVER_NETBEHEERDER=waarde)
    assert "netbeheerder" in config.MCP_SERVERS
    assert config.MCP_SERVERS_UIT == {}


def test_zonder_variabele_blijft_de_bron_gewoon_staan(monkeypatch):
    """Weglaten is niet hetzelfde als uitzetten; anders verdwijnt een bron door
    een vergeten regel in plaats van door een besluit."""
    config = _config_met(monkeypatch, MCP_SERVER_NETBEHEERDER=None)
    assert "netbeheerder" in config.MCP_SERVERS


@pytest.mark.parametrize("waarde", ["uit", "UIT", " off "])
def test_uitzetten_kan_op_meer_dan_een_manier(monkeypatch, waarde):
    """Hoofdletters en spaties eromheen maken niet uit - wie een bron wil
    uitzetten moet niet hoeven raden welke schrijfwijze werkt. Leeg hoort er
    bewust niet bij: dat is "terug naar standaard"."""
    config = _config_met(monkeypatch, MCP_SERVER_NETBEHEERDER=waarde)
    assert "netbeheerder" not in config.MCP_SERVERS


def test_de_andere_bronnen_blijven_ongemoeid(monkeypatch):
    config = _config_met(monkeypatch, MCP_SERVER_NETBEHEERDER="uit")
    assert set(config.MCP_SERVERS) == {"kvk", "koop", "regelrecht", "rvo"}

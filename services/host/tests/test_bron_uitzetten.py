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
import re
from pathlib import Path

import pytest

from config import _UIT


def _config_met(monkeypatch, **env):
    import dotenv

    # Anders vult load_dotenv een gewiste sleutel weer aan uit de .env van de
    # ontwikkelaar, en test je zijn omgeving in plaats van de configuratie.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    import config

    return importlib.reload(config)


@pytest.mark.parametrize("waarde", sorted(_UIT) + [" Uit "])
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
    assert "MCP_SERVER_NETBEHEERDER" in config.MCP_SERVERS_LEEG


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


@pytest.mark.parametrize(
    "bestand",
    [
        Path(__file__).parents[1] / ".env.example",
        Path(__file__).parents[3] / "docs" / "deploy-zad.md",
    ],
)
def test_de_uitzet_woorden_in_de_documentatie_zijn_die_van_de_code(bestand):
    """De lijst leeft in `config._UIT`; de docs herhalen hem voor beheerders.
    Loopt een woord uit de pas, dan belooft een doc iets dat de host negeert."""
    tekst = bestand.read_text(encoding="utf-8")
    m = re.search(r"uitzet-woord \(([^;)]*)", tekst)
    assert m, f"{bestand.name}: geen 'uitzet-woord (...)'-lijst gevonden"
    gedocumenteerd = {w.strip(" \n#`") for w in m.group(1).split(",")}
    assert gedocumenteerd == set(_UIT), (
        f"{bestand.name}: docs {sorted(gedocumenteerd)} vs code {sorted(_UIT)}"
    )

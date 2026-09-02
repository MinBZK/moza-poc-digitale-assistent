"""Een bron die niet geconfigureerd is, staat uit; een bron die niet opkwam, heeft
een storing. Het model krijgt ze allebei te horen, maar anders: over een storing
meldt het wat er mist, over een uitgezette bron zwijgt het.

`bronnen_offline` keek alleen naar servers die wél in de configuratie stonden
maar niet startten. Schakel je een bron uit door hem uit de configuratie te
halen - bijvoorbeeld de Business Wallet, om een onderzoek op eigen opgaven te
laten draaien - dan stond hij nergens als "weg", en bleef de assistent hem
beloven: "uw energieverbruik haal ik op uit uw Business Wallet".

Een belofte over een bron die er niet is, is precies het soort vertrouwensfout
dat dit project wil vermijden. En het is erger dan een storing melden, want de
gebruiker heeft geen enkele aanwijzing dat er iets mist.
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import vlam_host
from config import MCP_SERVER_ENV_KEYS
from errors import BRON_LABELS
from vlam_host import VLAMHost

ALLE = sorted(BRON_LABELS)
LOGGER = "vlam.host"


def _host(uit: list[str] | None = None, storing: list[str] | None = None) -> VLAMHost:
    """Een host waarvan `uit` niet is ingericht en `storing` wel, maar niet opkwam.

    Zet de configuratie-globals van `vlam_host` direct; de autouse-fixture
    `configuratie_per_test` in conftest.py draait dat na elke test terug."""
    uit, storing = uit or [], storing or []
    host = VLAMHost()
    vlam_host.MCP_SERVERS = {n: Path(f"{n}/server.py") for n in ALLE if n not in uit}
    vlam_host.MCP_SERVERS_UIT = {n: MCP_SERVER_ENV_KEYS[n] for n in uit}
    host.server_status = {
        n: ("niet beschikbaar" if n in storing else "verbonden") for n in ALLE if n not in uit
    }
    return host


def _waarschuwingen(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelname == "WARNING"]


UIT_GEVALLEN = [[], ["netbeheerder"], ["koop", "netbeheerder"]]


def test_een_niet_geconfigureerde_bron_staat_uit_en_is_geen_storing():
    """De wallet uit de configuratie halen is genoeg om hem uit te schakelen."""
    host = _host(uit=["netbeheerder"])
    assert host.bronnen_uit == ["netbeheerder"]
    assert host.bronnen_offline == []


def test_een_gestarte_bron_telt_niet_als_weg():
    assert _host().bronnen_offline == []


def test_een_bron_die_niet_opkwam_blijft_gemeld():
    """Het bestaande geval mag niet sneuvelen met deze wijziging."""
    assert "koop" in _host(storing=["koop"]).bronnen_offline


def test_de_lijsten_blijven_gesorteerd_en_gescheiden():
    """De lijsten gaan de prompt in; een dubbele bron leest als een fout."""
    host = _host(uit=["netbeheerder"], storing=["koop"])
    assert host.bronnen_offline == ["koop"]
    assert host.bronnen_uit == ["netbeheerder"]


def test_elke_bron_heeft_een_omgevingsvariabele():
    """De waarschuwing noemt de variabele uit de configuratie; een bron zonder
    variabele zou een naam verzinnen die niemand kan zetten."""
    assert set(BRON_LABELS) == set(MCP_SERVER_ENV_KEYS)


@pytest.mark.parametrize("uit", UIT_GEVALLEN)
def test_elke_uitgezette_bron_krijgt_een_eigen_waarschuwing(uit, caplog):
    host = _host(uit=uit)
    with caplog.at_level("WARNING", logger=LOGGER):
        host._meld_uitgezette_bronnen()
    meldingen = _waarschuwingen(caplog)
    assert len(meldingen) == len(uit)
    for naam, melding in zip(sorted(uit), meldingen, strict=True):
        assert f"Bron '{naam}'" in melding
        assert BRON_LABELS[naam] in melding
        assert MCP_SERVER_ENV_KEYS[naam] in melding
        assert "maak hem leeg" in melding


def test_een_storing_is_geen_reden_voor_de_uitzet_waarschuwing(caplog):
    with caplog.at_level("WARNING", logger=LOGGER):
        _host(storing=["koop"])._meld_uitgezette_bronnen()
    assert _waarschuwingen(caplog) == []


@pytest.mark.parametrize("uit", UIT_GEVALLEN)
def test_health_toont_de_uitgezette_bronnen_apart(uit):
    """`servers` meldt storingen; een bewust uitgezette bron hoort daar niet
    tussen, maar wel zichtbaar zijn voor wie /health leest."""
    status = _host(uit=uit).get_status()
    assert status["bronnen_uit"] == sorted(uit)
    assert set(status["servers"]) == set(ALLE) - set(uit)


@pytest.mark.parametrize("uit", UIT_GEVALLEN)
def test_startup_meldt_de_uitgezette_bronnen(uit, caplog):
    """Niet de private methode maar `startup()` zelf: de omgeving staat buiten de
    repo, dus de log bij het opstarten is de plek waar een bron die voor één
    onderzoek is uitgezet, zichtbaar blijft."""
    host = _host(uit=uit)
    host.server_status = {}
    host.registry.register_server = AsyncMock()
    import asyncio

    with caplog.at_level("WARNING", logger=LOGGER):
        asyncio.run(host.startup())
    assert host.registry.register_server.await_count == len(ALLE) - len(uit)
    assert [n for n in ALLE if n not in uit] == sorted(host.server_status)
    meldingen = _waarschuwingen(caplog)
    assert [m.split("'")[1] for m in meldingen] == sorted(uit)


@pytest.mark.parametrize(
    ("uit", "storing", "verwacht"),
    [([], [], "actief"), (["netbeheerder"], [], "gedegradeerd"), ([], ["koop"], "gedegradeerd")],
)
def test_health_status_is_gedegradeerd_bij_een_bron_die_uit_of_weg_is(uit, storing, verwacht):
    """De readiness-probe kijkt naar de HTTP-status; wie de body leest hoort in
    één woord te zien dat er een bron ontbreekt."""
    assert _host(uit=uit, storing=storing).get_status()["status"] == verwacht


def test_regelstatus_geeft_de_bron_van_de_maatregelen_toestemming_door():
    from regelloop import Uitkomst

    plicht = Uitkomst(klaar=True, wacht_op=None, reden="", resultaat={})
    maatregelen = Uitkomst(
        klaar=False, wacht_op="toestemming", reden="", resultaat=None,
        bron="Business Wallet", scope="netbeheerder",
    )
    status = vlam_host._regel_status_dict(plicht, maatregelen)
    assert status["maatregelen"]["toestemming_bron"] == "Business Wallet"

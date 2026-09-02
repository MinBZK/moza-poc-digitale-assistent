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

from errors import BRON_LABELS
from vlam_host import VLAMHost


def _host(status: dict[str, str]) -> VLAMHost:
    host = VLAMHost()
    host.server_status = status
    return host


def test_een_niet_geconfigureerde_bron_staat_uit_en_is_geen_storing():
    """De wallet uit de configuratie halen is genoeg om hem uit te schakelen."""
    zonder_wallet = {n: "verbonden" for n in BRON_LABELS if n != "netbeheerder"}
    host = _host(zonder_wallet)
    assert host.bronnen_uit == ["netbeheerder"]
    assert host.bronnen_offline == []


def test_een_gestarte_bron_telt_niet_als_weg():
    alles = {n: "verbonden" for n in BRON_LABELS}
    assert _host(alles).bronnen_offline == []


def test_een_bron_die_niet_opkwam_blijft_gemeld():
    """Het bestaande geval mag niet sneuvelen met deze wijziging."""
    status = {n: "verbonden" for n in BRON_LABELS}
    status["koop"] = "niet beschikbaar"
    assert "koop" in _host(status).bronnen_offline


def test_de_lijsten_blijven_gesorteerd_en_gescheiden():
    """De lijsten gaan de prompt in; een dubbele bron leest als een fout."""
    status = {n: "verbonden" for n in BRON_LABELS if n not in ("koop", "netbeheerder")}
    status["koop"] = "niet beschikbaar"
    host = _host(status)
    assert host.bronnen_offline == ["koop"]
    assert host.bronnen_uit == ["netbeheerder"]


def test_een_uitgezette_bron_wordt_bij_het_opstarten_gemeld(caplog):
    """De omgeving staat buiten de repo; de log is de plek waar een bron die
    voor één onderzoek is uitgezet, zichtbaar blijft."""
    zonder_wallet = {n: "verbonden" for n in BRON_LABELS if n != "netbeheerder"}
    host = _host(zonder_wallet)
    with caplog.at_level("WARNING", logger="vlam.host"):
        host._meld_uitgezette_bronnen()
    meldingen = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(meldingen) == 1
    assert "netbeheerder" in meldingen[0]
    assert "MCP_SERVER_NETBEHEERDER" in meldingen[0]
    assert "Business Wallet" in meldingen[0]


def test_alle_bronnen_aan_geeft_geen_waarschuwing(caplog):
    alles = {n: "verbonden" for n in BRON_LABELS}
    with caplog.at_level("WARNING", logger="vlam.host"):
        _host(alles)._meld_uitgezette_bronnen()
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_health_toont_de_uitgezette_bronnen_apart():
    """`servers` meldt storingen; een bewust uitgezette bron hoort daar niet
    tussen, maar wel zichtbaar zijn voor wie /health leest."""
    zonder_wallet = {n: "verbonden" for n in BRON_LABELS if n != "netbeheerder"}
    status = _host(zonder_wallet).get_status()
    assert status["bronnen_uit"] == ["netbeheerder"]
    assert "netbeheerder" not in status["servers"]
    alles = {n: "verbonden" for n in BRON_LABELS}
    assert _host(alles).get_status()["bronnen_uit"] == []

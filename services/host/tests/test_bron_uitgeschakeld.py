"""Een bron die niet geconfigureerd is, is voor het model even weg als een bron
die niet opkwam.

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


def test_een_niet_geconfigureerde_bron_telt_als_weg():
    """De wallet uit de configuratie halen is genoeg om hem uit te schakelen."""
    zonder_wallet = {n: "verbonden" for n in BRON_LABELS if n != "netbeheerder"}
    assert "netbeheerder" in _host(zonder_wallet).bronnen_offline


def test_een_gestarte_bron_telt_niet_als_weg():
    alles = {n: "verbonden" for n in BRON_LABELS}
    assert _host(alles).bronnen_offline == []


def test_een_bron_die_niet_opkwam_blijft_gemeld():
    """Het bestaande geval mag niet sneuvelen met deze wijziging."""
    status = {n: "verbonden" for n in BRON_LABELS}
    status["koop"] = "niet beschikbaar"
    assert "koop" in _host(status).bronnen_offline


def test_de_lijst_blijft_gesorteerd_en_zonder_dubbelen():
    """De lijst gaat de prompt in; een dubbele bron leest als een fout."""
    status = {n: "verbonden" for n in BRON_LABELS if n not in ("koop", "netbeheerder")}
    offline = _host(status).bronnen_offline
    assert offline == sorted(set(offline))
    assert set(offline) == {"koop", "netbeheerder"}

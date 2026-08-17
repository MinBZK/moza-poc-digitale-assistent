"""Een logregel mag een gesprek aanwijzen, niet de ondernemer erachter.

`_conv_key` is `f"{session_kvk}|{session_id}|{mode}"`. Die sleutel logeren zet
het KvK-nummer én het client-gekozen session_id in platte tekst in de log, en dat
is precies wat PDR-009 uitsluit. De maskering die daarvoor elders is aangebracht
(`_arg_keys` logt alleen veldnamen, de KvK-server vervangt het pad-segment door
`<kvk>`, de CLI redigeert via `_loggable_cmd`) helpt hier niet: het vangnet in
`log_redaction.py` gebruikt bewust geen entropie-heuristiek, juist omdat die
KvK-nummers zou raken.

Voor het onderzoek zijn de nummers fictief. De maskering hoort er toch te zijn:
zodra er echte gegevens door deze host lopen, telt elke logpipeline mee.
"""

import logging

import pytest

from vlam_host import VLAMHost, log_sleutel

KVK = "62345681"
SESSION = "b2f1c9e4-0000-4444-8888-aaaaaaaaaaaa"


@pytest.fixture
def conv_key():
    return VLAMHost._conv_key(KVK, SESSION, "vlam")


def test_de_logsleutel_draagt_geen_kvk_nummer(conv_key):
    assert KVK not in log_sleutel(conv_key)


def test_de_logsleutel_draagt_geen_session_id(conv_key):
    """Het session_id komt van de client en identificeert de sessie.

    Samen met het KvK-nummer maakt het een logregel herleidbaar tot één
    ondernemer in één gesprek; los is het nog steeds een sessie-identificatie
    die niet in een log hoort.
    """
    sleutel = log_sleutel(conv_key)
    assert SESSION not in sleutel
    assert SESSION.split("-")[0] not in sleutel


def test_de_logsleutel_noemt_de_modus_wel(conv_key):
    """Zonder de modus is een logregel niet meer te plaatsen tussen de zes paden."""
    assert "vlam" in log_sleutel(conv_key)


def test_dezelfde_sessie_geeft_dezelfde_sleutel(conv_key):
    """Anders zijn twee regels van één gesprek niet meer aan elkaar te knopen."""
    assert log_sleutel(conv_key) == log_sleutel(conv_key)


def test_verschillende_sessies_geven_verschillende_sleutels():
    """Twee gesprekken mogen niet op dezelfde logsleutel uitkomen.

    Cardinaliteiten die er hier toe doen: ander KvK met hetzelfde session_id, en
    hetzelfde KvK met een ander session_id. Beide moeten uit elkaar te houden
    zijn, anders leest een storing in het ene gesprek als een storing in het
    andere.
    """
    basis = VLAMHost._conv_key(KVK, SESSION, "vlam")
    ander_bedrijf = VLAMHost._conv_key("85234567", SESSION, "vlam")
    andere_sessie = VLAMHost._conv_key(KVK, "een-ander-id", "vlam")
    andere_modus = VLAMHost._conv_key(KVK, SESSION, "claude")
    sleutels = {
        log_sleutel(k) for k in (basis, ander_bedrijf, andere_sessie, andere_modus)
    }
    assert len(sleutels) == 4


def test_een_lege_sleutel_geeft_geen_crash():
    """Onbereikbaar via de hard-block, maar een logregel mag nooit de oorzaak
    van een tweede fout worden."""
    assert log_sleutel("")


def test_geen_logregel_geeft_conv_key_rechtstreeks_door():
    """Bewaking op de broncode: de sleutel zelf hoort nooit in een logaanroep.

    Dit is de regressie die CodeQL en een onafhankelijke review beide vonden.
    Een nieuwe logregel met `conv_key` erin breekt hier, ook als hij op een
    ander pad staat dan de twee die het toen betrof.
    """
    import ast
    from pathlib import Path

    bron = Path(__file__).resolve().parent.parent / "vlam_host.py"
    boom = ast.parse(bron.read_text())
    fout = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        if not (isinstance(doel, ast.Attribute) and isinstance(doel.value, ast.Name)):
            continue
        if doel.value.id != "logger":
            continue
        for arg in knoop.args:
            tekst = ast.unparse(arg)
            if tekst == "conv_key" or tekst.endswith(".conv_key"):
                fout.append(f"regel {knoop.lineno}: {ast.unparse(knoop)[:70]}")
    assert not fout, f"logregel draagt conv_key rechtstreeks: {fout}"


def test_de_geweigerde_wallet_logt_geen_kvk(caplog):
    """Het pad dat in elke sessie geraakt wordt, end-to-end op de logregel.

    De poort weigert de Business Wallet zolang toestemming niet is vastgelegd
    (PDR-008). Die weigering logt een waarschuwing; juist die regel droeg het
    KvK-nummer.
    """
    host = VLAMHost()
    conv_key = VLAMHost._conv_key(KVK, SESSION, "vlam")

    async def nooit_aangeroepen():
        raise AssertionError("de bron had niet geraadpleegd mogen worden")

    import asyncio

    with caplog.at_level(logging.WARNING):
        resultaat, fout, aangeroepen = asyncio.run(
            host._bron_aanroep_gated(
                nooit_aangeroepen, "netbeheerder__verbruik", {}, conv_key
            )
        )
    assert aangeroepen is False
    assert fout is not None
    logtekst = "\n".join(r.getMessage() for r in caplog.records)
    assert logtekst, "geen logregel geschreven; dan meet deze test niets"
    assert KVK not in logtekst
    assert SESSION not in logtekst

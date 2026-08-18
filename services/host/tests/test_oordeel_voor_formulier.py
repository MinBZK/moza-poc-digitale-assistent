"""Eerst het oordeel en de herkomst, dan pas het formulier.

De host rondt de informatieplicht af en draait daarna meteen de
maatregelenregel. Die heeft gegevens nodig die alleen de ondernemer weet, dus er
komt een formulier uit - en dat reed mee op hetzelfde antwoord als het oordeel.

Voor de ondernemer vielen daarmee drie dingen samen in één scherm: een uitkomst
waar hij toestemming voor gaf, een tweede toets die over hem nog niets had
vastgesteld (`requirements_met: false`, uitkomst leeg), en een vragenlijst van
achtentwintig categorieen. Hij kreeg geen moment om het oordeel te laten landen,
en geen eigen besluit over dat tweede deel.

De wet vraagt die rapportage wel (artikel 5.15d Bal), dus de host blijft de regel
draaien en houdt de uitkomst vast. Alleen het formulier wacht een beurt.
"""

import pytest

from vlam_host import VLAMHost

KVK = "62345681"
CONV = "62345681|sessie-a|vlam"


@pytest.fixture
def host():
    return VLAMHost()


def _status(klaar: bool = True) -> dict:
    """Een regel_status zoals `_regel_status_dict` hem oplevert."""
    return {
        "klaar": klaar,
        "wacht_op": None if klaar else "toestemming",
        "reden": "",
        "resultaat": {"voldoet_aan_voorwaarden": True, "uitkomsten": {}},
    }


def test_het_oordeel_is_pas_een_keer_gemeld_na_de_eerste_keer(host):
    assert host.oordeel_al_gemeld(CONV) is False
    host.markeer_oordeel_gemeld(CONV)
    assert host.oordeel_al_gemeld(CONV) is True


def test_elk_gesprek_heeft_zijn_eigen_stand(host):
    """Anders mist de tweede respondent zijn formulier, of krijgt hij het te vroeg."""
    host.markeer_oordeel_gemeld(CONV)
    assert host.oordeel_al_gemeld("85234567|sessie-b|vlam") is False


def test_een_nieuw_gesprek_begint_opnieuw(host):
    """`clear_session` hoort deze stand mee op te ruimen.

    Blijft hij staan, dan krijgt de ondernemer na 'nieuw gesprek' het formulier
    meteen weer bij het oordeel - precies wat we wilden voorkomen.
    """
    host.markeer_oordeel_gemeld(CONV)
    host.clear_session(KVK, "sessie-a")
    assert host.oordeel_al_gemeld(CONV) is False

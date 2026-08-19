"""De maatregelenlijst hoort één keer op het scherm te komen, niet elke beurt.

De regelloop draait bij iedere beurt opnieuw en levert de uitkomst van de
maatregelenregel dus ook iedere beurt opnieuw. De frontend bouwt van elke
`maatregelen`-lijst op het answer-event een formulier. Samen betekende dat: de
respondent kreeg de drieëntwintig maatregelen opnieuw voorgeschoteld nadat hij
ze had ingevuld, en nog een keer toen hij "ja, dien maar in" zei.

Gemeten in een volledige flow tegen een draaiende host: beurt 4, 5 én 6 droegen
alle drie dezelfde lijst van 23 items. Voor een sessie van twintig minuten is
dat niet alleen verwarrend maar ook duur - de respondent denkt dat zijn antwoord
niet is aangekomen en vult hem opnieuw in.

Het eerder getoonde formulier blijft gewoon in het gesprek staan en blijft
invulbaar; deze poort haalt alleen de herhaling weg.
"""

import ast
from pathlib import Path

import pytest

from vlam_host import VLAMHost

KVK = "62345681"
CONV = "62345681|sessie-a|vlam"


@pytest.fixture
def host():
    return VLAMHost()


def test_de_lijst_geldt_als_gemeld_na_de_eerste_keer(host):
    assert host.maatregelen_al_gemeld(CONV) is False
    host.markeer_maatregelen_gemeld(CONV)
    assert host.maatregelen_al_gemeld(CONV) is True


def test_elk_gesprek_houdt_zijn_eigen_stand(host):
    """Anders mist de tweede respondent zijn maatregelenformulier volledig."""
    host.markeer_maatregelen_gemeld(CONV)
    assert host.maatregelen_al_gemeld("85234567|sessie-b|vlam") is False


def test_een_nieuw_gesprek_begint_opnieuw(host):
    """Blijft de stand staan, dan krijgt hij na 'nieuw gesprek' nooit meer een lijst."""
    host.markeer_maatregelen_gemeld(CONV)
    host.clear_session(KVK, "sessie-a")
    assert host.maatregelen_al_gemeld(CONV) is False


def _paden_met_poort() -> list[str]:
    """Zoek in de broncode welke methoden de poort daadwerkelijk toepassen.

    Een unittest op de twee helpers bewijst niet dat ze ook bedraad zijn. Deze
    controle leest de AST, zodat een pad dat later wordt bijgebouwd niet
    stilzwijgend zonder poort blijft - precies hoe de toestemmingspoort ooit op
    één van twee paden ontbrak.
    """
    bron = Path(__file__).resolve().parent.parent / "vlam_host.py"
    boom = ast.parse(bron.read_text())
    gevonden = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tekst = ast.dump(knoop)
        if "maatregelen_uit_status" in tekst and "maatregelen_al_gemeld" in tekst:
            gevonden.append(knoop.name)
    return gevonden


def test_elk_pad_dat_de_lijst_ophaalt_past_ook_de_poort_toe():
    bron = (Path(__file__).resolve().parent.parent / "vlam_host.py").read_text()
    boom = ast.parse(bron)
    ophalers = [
        k.name
        for k in ast.walk(boom)
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))
        and "maatregelen_uit_status" in ast.dump(k)
        and k.name != "maatregelen_uit_status"
    ]
    assert ophalers, "geen enkel pad haalt de lijst nog op; werk deze test bij"
    zonder_poort = sorted(set(ophalers) - set(_paden_met_poort()))
    assert not zonder_poort, (
        f"deze paden sturen de maatregelenlijst zonder poort en herhalen hem dus "
        f"elke beurt: {zonder_poort}"
    )

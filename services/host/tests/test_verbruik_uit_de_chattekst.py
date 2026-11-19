"""Verbruik dat de ondernemer in de chat typt, telt als opgave.

Gezien tijdens het gebruikersonderzoek (25 augustus): een respondent stuurde
zijn verbruik als tekst in plaats van via het formulier. Alleen `opgaven` uit
het formulier werden een feit, dus de regelloop bleef wachten en de assistent
vroeg het verbruik opnieuw, terwijl het net gegeven was.
"""

import pytest

from vlam_host import _opgaven_als_feiten, _opgaven_uit_tekst

E = "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"
G = "JAARLIJKS_GASVERBRUIK_M3"


@pytest.mark.parametrize(
    "tekst, verwacht",
    [
        ("420.000 kWh en 140.000 m3", {E: 420000, G: 140000}),
        ("Elektriciteit: 420000, gas: 140000", {E: 420000, G: 140000}),
        ("mijn stroomverbruik is 420.000 kwh, aardgas 140.000 m³", {E: 420000, G: 140000}),
        ("We verbruiken ongeveer 60.000 kWh per jaar", {E: 60000}),
        ("gas 25.000 kuub", {G: 25000}),
        ("elektriciteit 61.250 kWh en gas 9.800 m3", {E: 61250, G: 9800}),
        ("Geldt de energiebesparingsplicht voor mijn bedrijf?", {}),
        ("Wij hebben 12 medewerkers", {}),
        ("Ja, ga je gang.", {}),
    ],
)
def test_verbruik_uit_tekst(tekst, verwacht):
    assert _opgaven_uit_tekst(tekst) == verwacht


def test_tekst_opgaven_worden_feiten_via_dezelfde_poort():
    feiten = _opgaven_als_feiten(_opgaven_uit_tekst("420.000 kWh en 140.000 m3"))
    assert feiten["ELEKTRICITEIT_KWH"]["waarde"] == 420000
    assert feiten["GAS_M3"]["waarde"] == 140000
    assert feiten["ELEKTRICITEIT_KWH"]["soort"] == "opgave"


def test_formulier_wint_van_tekst():
    tekst = _opgaven_uit_tekst("ongeveer 400.000 kWh")
    formulier = {E: 420000}
    samen = {**tekst, **formulier}
    assert samen[E] == 420000

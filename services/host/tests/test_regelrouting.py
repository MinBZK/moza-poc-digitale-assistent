"""Welk veld uit welke bron komt, op één plek.

Vraagt de wet een veld dat hier niet staat, dan stopt de orkestratielus. Dat is
opzet: raden waar een gegeven vandaan komt is precies wat deze hele branch
onmogelijk moet maken.
"""

import pytest

from regelrouting import HERKOMST, route


def test_elk_veld_van_de_informatieplicht_is_gerouteerd():
    """De wet vraagt deze vier; ontbreekt er één, dan loopt de flow vast."""
    for veld in (
        "KVK_NUMMER",
        "IS_WOONFUNCTIE",
        "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH",
        "JAARLIJKS_GASVERBRUIK_M3",
    ):
        assert route(veld) is not None, f"{veld} heeft geen bron"


def test_verbruik_vraagt_toestemming_bedrijfsgegevens_niet():
    """PDR-008: geen bron vóór akkoord. Alleen het verbruik valt daaronder."""
    assert route("JAARLIJKS_GASVERBRUIK_M3").toestemming is True
    assert route("JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH").toestemming is True
    assert route("IS_WOONFUNCTIE").toestemming is False
    assert route("KVK_NUMMER").toestemming is False


def test_opgaven_van_de_ondernemer_hebben_geen_tool():
    """Die komen uit het formulier, niet uit een bron die we kunnen aanroepen."""
    veld = route("MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF")
    assert veld.tool is None
    assert veld.soort == "opgave"


def test_onbekend_veld_geeft_none():
    assert route("OMZET_2025") is None


@pytest.mark.parametrize("naam,veld", sorted(HERKOMST.items()))
def test_elk_veld_heeft_een_bron_en_een_soort(naam, veld):
    """Een feit zonder bron is in dit ontwerp geen feit."""
    assert veld.bron, naam
    assert veld.soort in {"identiteit", "registratie", "attestatie", "opgave"}, naam


def test_velden_met_afwijkende_feitnaam_bestaan_in_feitenkaart():
    """Elk veld met een afwijkende feitnaam moet echt in feiten.py voorkomen."""
    from feiten import _uit_kvk, _uit_netbeheerder

    # Maak mock-resultaten van de oogsters om de feitnamen te zien
    kvk_feit = _uit_kvk({
        "naam": "Test",
        "kvkNummer": "12345678",
        "rechtsvorm": "vof",
        "is_woonfunctie": False,
        "_embedded": {"hoofdvestiging": {}},
        "bag": {}
    })

    netbeheerder_feit = _uit_netbeheerder({
        "beschikbaar": True,
        "verbruik": {
            "totaal": {
                "jaarlijks_elektriciteitsverbruik_kwh": 1000,
                "jaarlijks_gasverbruik_m3": 100
            }
        },
        "credential": {
            "peiljaar": 2024,
            "uitgegeven_door": "Liander"
        }
    })

    # Controleer dat afwijkende feitnamen echt bestaan
    elektriciteit_veld = route("JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH")
    assert elektriciteit_veld.feitnaam == "ELEKTRICITEIT_KWH"
    assert "ELEKTRICITEIT_KWH" in netbeheerder_feit

    gas_veld = route("JAARLIJKS_GASVERBRUIK_M3")
    assert gas_veld.feitnaam == "GAS_M3"
    assert "GAS_M3" in netbeheerder_feit

    woonfunctie_veld = route("IS_WOONFUNCTIE")
    assert woonfunctie_veld.feitnaam == "WOONFUNCTIE"
    assert "WOONFUNCTIE" in kvk_feit

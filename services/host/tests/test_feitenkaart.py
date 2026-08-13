"""Canonieke feiten uit tool-resultaten, als bron voor slot-substitutie.

Elk feit dat hier niet uit komt, moet het model uit het gesprek reconstrueren -
en dat is precies waar 'Bloemenlaan 12' vandaan kwam terwijl de KvK-tool
'Hoefweg 210' had geleverd.
"""

import json

from feiten import feiten_uit_tool


def _envelope(data: dict) -> str:
    return json.dumps({"data": data, "provenance": {"source": "test"}})


def test_kvk_levert_naam_nummer_en_bezoekadres():
    resultaat = _envelope(
        {
            "naam": "Kwekerij De Bloesem",
            "kvkNummer": "62345681",
            "rechtsvorm": "Vennootschap onder firma",
            "_embedded": {
                "hoofdvestiging": {
                    "vestigingsnummer": "000062345681",
                    "adressen": [
                        {"type": "correspondentieadres", "volledigAdres": "Postbus 1, 2665AA Bleiswijk"},
                        {"type": "bezoekadres", "volledigAdres": "Hoefweg 210, 2665KG Bleiswijk"},
                    ],
                }
            },
        }
    )
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["BEDRIJFSNAAM"] == "Kwekerij De Bloesem"
    assert feiten["KVK_NUMMER"] == "62345681"
    assert feiten["VESTIGINGSNUMMER"] == "000062345681"
    assert feiten["VESTIGINGSADRES"] == "Hoefweg 210, 2665KG Bleiswijk"


def test_adres_wordt_op_type_gekozen_niet_op_positie():
    """Een postbus als eerste adres is het geval dat positie-kiezen sloopt."""
    resultaat = _envelope(
        {
            "naam": "Vogel Bouwregie B.V.",
            "kvkNummer": "61234570",
            "_embedded": {
                "hoofdvestiging": {
                    "adressen": [
                        {"type": "correspondentieadres", "volledigAdres": "Postbus 44, 3000AA Rotterdam"},
                        {"type": "bezoekadres", "volledigAdres": "Coolsingel 1, 3011AD Rotterdam"},
                    ]
                }
            },
        }
    )
    assert feiten_uit_tool("kvk__mijn_bedrijf", resultaat)["VESTIGINGSADRES"] == (
        "Coolsingel 1, 3011AD Rotterdam"
    )


def test_netbeheerder_levert_verbruik_en_peiljaar():
    resultaat = _envelope(
        {
            "peiljaar": 2025,
            "netbeheerder": "Stedin (mock)",
            "totaal": {
                "jaarlijks_elektriciteitsverbruik_kwh": 420000,
                "jaarlijks_gasverbruik_m3": 140000,
            },
        }
    )
    feiten = feiten_uit_tool("netbeheerder__verbruik", resultaat)
    assert feiten["ELEKTRICITEIT_KWH"] == 420000
    assert feiten["GAS_M3"] == 140000
    assert feiten["PEILJAAR"] == 2025
    assert feiten["NETBEHEERDER"] == "Stedin (mock)"


def test_regelrecht_levert_drempels_en_oordelen():
    resultaat = _envelope(
        {
            "drempelwaarden": {"DREMPEL_ELEKTRICITEIT_KWH": 50000},
            "gebruikte_waarden": {"JAARLIJKS_GASVERBRUIK_M3": 140000},
            "uitkomsten": {
                "heeft_informatieplicht": True,
                "heeft_onderzoeksplicht": False,
                "volgende_rapportage_deadline": "2027-12-01",
            },
        }
    )
    feiten = feiten_uit_tool("regelrecht__execute_law", resultaat)
    assert feiten["DREMPEL_ELEKTRICITEIT_KWH"] == 50000
    assert feiten["OORDEEL_INFORMATIEPLICHT"] is True
    assert feiten["OORDEEL_ONDERZOEKSPLICHT"] is False
    assert feiten["VOLGENDE_DEADLINE"] == "2027-12-01"


def test_onbekende_tool_levert_niets():
    assert feiten_uit_tool("koop__zoek_regelgeving", _envelope({"titel": "x"})) == {}


def test_kapot_resultaat_levert_niets_en_gooit_niet():
    """Een bron die rommel teruggeeft mag het gesprek niet laten klappen."""
    assert feiten_uit_tool("kvk__mijn_bedrijf", "geen json") == {}

"""Het model schrijft slots, de host vult ze in.

Een feit dat het model nooit schrijft kan het niet fout schrijven. Dat is de
hele reden dat deze laag bestaat; alles hier moet dus liever weigeren dan gokken.
"""

from slots import vul_slots


def test_bekend_slot_wordt_ingevuld():
    tekst, ontbrekend = vul_slots(
        "Uw bedrijf {{BEDRIJFSNAAM}} is bekend.", {"BEDRIJFSNAAM": "Kwekerij De Bloesem"}
    )
    assert tekst == "Uw bedrijf Kwekerij De Bloesem is bekend."
    assert ontbrekend == []


def test_getallen_krijgen_nederlandse_duizendtallen():
    """Zonder deze regel schrijft het model de ene keer 420000 en de andere keer
    420.000, en dat verschil ziet de respondent."""
    tekst, _ = vul_slots("{{ELEKTRICITEIT_KWH}} kWh", {"ELEKTRICITEIT_KWH": 420000})
    assert tekst == "420.000 kWh"


def test_booleans_worden_ja_of_nee():
    tekst, _ = vul_slots("Woonfunctie: {{WOONFUNCTIE}}", {"WOONFUNCTIE": False})
    assert tekst == "Woonfunctie: nee"


def test_oordeel_wordt_wel_of_niet():
    """Het oordeel komt uit RegelRecht, niet uit het model."""
    tekst, _ = vul_slots(
        "De informatieplicht geldt {{OORDEEL_INFORMATIEPLICHT}} voor u.",
        {"OORDEEL_INFORMATIEPLICHT": True},
    )
    assert tekst == "De informatieplicht geldt wel voor u."


def test_onbekend_slot_blijft_staan_en_wordt_gemeld():
    """Blijft staan zodat de aanroeper het kan tegenhouden.

    Stil weglaten zou een halve zin opleveren waarvan niemand merkt dat er een
    feit uit is verdwenen.
    """
    tekst, ontbrekend = vul_slots("Adres: {{VESTIGINGSADRES}}", {})
    assert ontbrekend == ["VESTIGINGSADRES"]
    assert "{{VESTIGINGSADRES}}" in tekst


def test_slot_buiten_het_woordenboek_wordt_gemeld():
    """Een verzonnen slotnaam is net zo goed een verzonnen feit."""
    _, ontbrekend = vul_slots("{{OMZET_2025}}", {"BEDRIJFSNAAM": "x"})
    assert ontbrekend == ["OMZET_2025"]


def test_tekst_zonder_slots_blijft_ongewijzigd():
    tekst, ontbrekend = vul_slots("Gewoon een zin.", {"BEDRIJFSNAAM": "x"})
    assert tekst == "Gewoon een zin."
    assert ontbrekend == []


def test_datum_wordt_nederlands_geschreven():
    tekst, _ = vul_slots("{{VOLGENDE_DEADLINE}}", {"VOLGENDE_DEADLINE": "2027-12-01"})
    assert tekst == "1 december 2027"


def test_een_onopgelost_slot_haalt_het_antwoord_niet():
    """De hele reden dat deze laag bestaat.

    Liever een foutmelding dan een rapport waarin een feit ontbreekt of verzonnen
    is; dat rapport gaat namens de ondernemer naar RVO.
    """
    import vlam_host

    events = vlam_host._antwoord_events(
        "Uw adres is {{VESTIGINGSADRES}}.", feiten={}
    )
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "{{" not in str(events[0])

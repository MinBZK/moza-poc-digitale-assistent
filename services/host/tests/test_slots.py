"""Het model schrijft slots, de host vult ze in.

Een feit dat het model nooit schrijft kan het niet fout schrijven. Dat is de
hele reden dat deze laag bestaat; alles hier moet dus liever weigeren dan gokken.
"""

from slots import vul_slots


def _feit(waarde: object) -> dict:
    """Een feit met alleen de waarde: `vul_slots` leest verder niets uit."""
    return {"waarde": waarde, "bron": "test", "soort": "opgave"}


def test_vul_slots_leest_de_waarde_uit_een_feit():
    tekst, ontbrekend = vul_slots(
        "Uw bedrijf {{BEDRIJFSNAAM}}.",
        {"BEDRIJFSNAAM": {"waarde": "Kwekerij De Bloesem",
                          "bron": "KvK Handelsregister",
                          "soort": "registratie"}},
    )
    assert tekst == "Uw bedrijf Kwekerij De Bloesem."
    assert ontbrekend == []


def test_bekend_slot_wordt_ingevuld():
    tekst, ontbrekend = vul_slots(
        "Uw bedrijf {{BEDRIJFSNAAM}} is bekend.", {"BEDRIJFSNAAM": _feit("Kwekerij De Bloesem")}
    )
    assert tekst == "Uw bedrijf Kwekerij De Bloesem is bekend."
    assert ontbrekend == []


def test_getallen_krijgen_nederlandse_duizendtallen():
    """Zonder deze regel schrijft het model de ene keer 420000 en de andere keer
    420.000, en dat verschil ziet de respondent."""
    tekst, _ = vul_slots("{{ELEKTRICITEIT_KWH}} kWh", {"ELEKTRICITEIT_KWH": _feit(420000)})
    assert tekst == "420.000 kWh"


def test_peiljaar_krijgt_geen_duizendtalscheiding():
    """Een jaartal is geen bedrag: 2025 hoort 2025 te blijven, niet '2.025'.

    Stond in het vlaggenschipvoorbeeld (informatieplicht_flow.md) en werd door
    geen enkele controle gezien.
    """
    tekst, _ = vul_slots("Uw verbruik in {{PEILJAAR}}.", {"PEILJAAR": _feit(2025)})
    assert tekst == "Uw verbruik in 2025."


def test_rapportage_frequentie_jaren_krijgt_geen_duizendtalscheiding():
    """Klein getal, dus toevallig ook goed zonder de uitzondering - deze test
    legt vast dat het om de slotnaam gaat, niet om de grootte van de waarde."""
    tekst, _ = vul_slots(
        "Rapporteer elke {{RAPPORTAGE_FREQUENTIE_JAREN}} jaar.",
        {"RAPPORTAGE_FREQUENTIE_JAREN": _feit(4)},
    )
    assert tekst == "Rapporteer elke 4 jaar."


def test_booleans_worden_ja_of_nee():
    tekst, _ = vul_slots("Woonfunctie: {{WOONFUNCTIE}}", {"WOONFUNCTIE": _feit(False)})
    assert tekst == "Woonfunctie: nee"


def test_oordeel_wordt_wel_of_niet():
    """Het oordeel komt uit RegelRecht, niet uit het model."""
    tekst, _ = vul_slots(
        "De informatieplicht geldt {{OORDEEL_INFORMATIEPLICHT}} voor u.",
        {"OORDEEL_INFORMATIEPLICHT": _feit(True)},
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
    _, ontbrekend = vul_slots("{{OMZET_2025}}", {"BEDRIJFSNAAM": _feit("x")})
    assert ontbrekend == ["OMZET_2025"]


def test_tekst_zonder_slots_blijft_ongewijzigd():
    tekst, ontbrekend = vul_slots("Gewoon een zin.", {"BEDRIJFSNAAM": _feit("x")})
    assert tekst == "Gewoon een zin."
    assert ontbrekend == []


def test_datum_wordt_nederlands_geschreven():
    tekst, _ = vul_slots("{{VOLGENDE_DEADLINE}}", {"VOLGENDE_DEADLINE": _feit("2027-12-01")})
    assert tekst == "1 december 2027"


def test_niet_bestaande_datum_blijft_onbewerkt():
    """`2027-2-30` heeft de ISO-vorm, maar 30 februari bestaat niet.

    `date.fromisoformat` valideert dat; zonder die validatie werd dit stil
    "30 februari 2027" - een datum die niet bestaat, verzonnen door de laag die
    juist geen feiten mag verzinnen.
    """
    tekst, _ = vul_slots("{{VOLGENDE_DEADLINE}}", {"VOLGENDE_DEADLINE": _feit("2027-2-30")})
    assert tekst == "2027-2-30"


def test_datum_in_dag_maand_jaar_volgorde_blijft_onbewerkt():
    """Dag-maand-jaar is geen ISO-datum en mag niet als zodanig gelezen worden.

    Zonder validatie werd `31-12-2027` (jaar-maand-dag gelezen) stil
    "2027 december 31" - onzin, zonder enige melding.
    """
    tekst, _ = vul_slots("{{VOLGENDE_DEADLINE}}", {"VOLGENDE_DEADLINE": _feit("31-12-2027")})
    assert tekst == "31-12-2027"


def test_waarde_zonder_streepjes_blijft_ongewijzigd():
    tekst, _ = vul_slots("{{VESTIGINGSPLAATS}}", {"VESTIGINGSPLAATS": _feit("Utrecht")})
    assert tekst == "Utrecht"


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


def test_een_onopgelost_slot_haalt_het_blokkerende_antwoord_niet():
    """Spiegel van de vorige test, voor het blokkerende pad (`/chat`).

    `_antwoord_tekst` is los gewijzigd van `_antwoord_events`; zonder deze test
    was de symmetrie tussen beide alleen met codelezing vast te stellen.
    """
    import vlam_host
    from errors import maak_fout

    tekst = vlam_host._antwoord_tekst("Uw adres is {{VESTIGINGSADRES}}.", feiten={})
    assert "{{" not in tekst
    assert tekst == maak_fout("ANTWOORD_ONVOLLEDIG").tekst


# --- Wat een slot NIET mag doen ---------------------------------------------


def test_een_kvk_nummer_blijft_een_nummer():
    """`date.fromisoformat` accepteert sinds 3.11 ook het ISO-basisformaat.

    Daardoor leest een achtcijferig nummer waarvan de middelste cijfers toevallig
    een geldige maand en dag vormen als datum. Gemeten op de persona's van de
    frontend: 67890123 werd "23 januari 6789" en 24681012 werd "12 oktober 2468".
    Een datum in dit systeem komt altijd met streepjes binnen (2027-12-01), dus
    het basisformaat hoeft niet herkend te worden.
    """
    from slots import vul_slots

    feiten = {"KVK_NUMMER": {"waarde": "67890123", "bron": "KvK", "soort": "registratie"}}
    tekst, ontbrekend = vul_slots("KvK {{KVK_NUMMER}}.", feiten)
    assert tekst == "KvK 67890123."
    assert not ontbrekend


def test_een_echte_datum_wordt_nog_steeds_uitgeschreven():
    """De tegenproef: het formaat dat de bronnen wél leveren blijft werken."""
    from slots import vul_slots

    feiten = {
        "VOLGENDE_DEADLINE": {"waarde": "2027-12-01", "bron": "RegelRecht", "soort": "wetsconstante"}
    }
    tekst, _ = vul_slots("Uiterlijk {{VOLGENDE_DEADLINE}}.", feiten)
    assert tekst == "Uiterlijk 1 december 2027."


def test_een_lijstwaarde_wordt_niet_als_python_uitgeschreven():
    """Anders staat er een rij dicts in het antwoord van de assistent.

    De feitenkaart draagt ook waarden die geen zin in kunnen: de 28 categorieen
    uit de wet, of de maatregelenlijst. Die horen niet ingevuld te worden maar
    gemeld, zodat de aanroeper het antwoord tegenhoudt in plaats van er een
    `[{'categorie': ...}]` op te zetten.
    """
    from slots import vul_slots

    feiten = {
        "CATEGORIEEN": {
            "waarde": [{"categorie": "Perslucht", "onderdeel": "Faciliteiten"}],
            "bron": "RegelRecht",
            "soort": "wetsconstante",
        }
    }
    tekst, ontbrekend = vul_slots("Dit geldt: {{CATEGORIEEN}}.", feiten)
    assert "categorie" not in tekst
    assert ontbrekend == ["CATEGORIEEN"]

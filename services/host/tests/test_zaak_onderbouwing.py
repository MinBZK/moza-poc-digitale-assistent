"""De zaak draagt zijn eigen onderbouwing, niet alleen zijn uitkomst.

Het rapport dat de ondernemer vóór het indienen leest is rijk: elk getal met zijn
bron, de drempel ernaast, het artikel eronder. De zaak die daarna in Lopende
zaken belandt had daar niets van - referentienummer, status en een lijst
maatregelen, verder niets.

Daarmee verdampte de herleidbaarheid precies op het moment dat er een dossier
ontstaat. Wie een week later terugkijkt kan niet zien waaróm de plicht gold, op
welk verbruik dat berustte, of wie dat verbruik verklaarde. Traceability hoort
duurzaam te worden waar een besluit aan vasthangt, niet te verdwijnen.

De onderbouwing komt uit de feitenkaart van de host en niet uit de argumenten van
het model: de host weet wie geraadpleegd is, het model geeft door wat het denkt
te weten.
"""

from vlam_host import verrijk_zaak

ZAAK = {"referentienummer": "RVO-EBR-2026-62345681-001", "status": "In behandeling"}


def _feiten() -> dict:
    def feit(waarde, bron, soort):
        return {"waarde": waarde, "bron": bron, "soort": soort}

    return {
        "ELEKTRICITEIT_KWH": feit(420000, "Business Wallet", "attestatie"),
        "GAS_M3": feit(140000, "Business Wallet", "attestatie"),
        "NETBEHEERDER": feit("Stedin", "Business Wallet", "attestatie"),
        "PEILJAAR": feit(2025, "Business Wallet", "attestatie"),
        "DREMPEL_ELEKTRICITEIT_KWH": feit(50000, "RegelRecht", "wetsconstante"),
        "DREMPEL_GAS_M3": feit(25000, "RegelRecht", "wetsconstante"),
        "BEDRIJFSNAAM": feit("Kwekerij De Bloesem", "KvK Handelsregister", "registratie"),
        "TEELT_IN_KAS": feit(True, "KvK Handelsregister", "registratie"),
    }


def test_het_verbruik_gaat_mee_met_bron_en_soort():
    zaak = verrijk_zaak(dict(ZAAK), _feiten(), grondslag=[])
    verbruik = zaak["onderbouwing"]["verbruik"]
    assert verbruik["ELEKTRICITEIT_KWH"]["waarde"] == 420000
    assert verbruik["ELEKTRICITEIT_KWH"]["bron"] == "Business Wallet"
    assert verbruik["ELEKTRICITEIT_KWH"]["soort"] == "attestatie"


def test_de_drempels_gaan_mee():
    """Zonder de drempel is het verbruik een getal zonder betekenis."""
    zaak = verrijk_zaak(dict(ZAAK), _feiten(), grondslag=[])
    assert zaak["onderbouwing"]["drempelwaarden"]["DREMPEL_ELEKTRICITEIT_KWH"] == 50000


def test_de_wettelijke_grondslag_gaat_mee():
    grondslag = [{"artikel": "5.15", "wet": "Besluit activiteiten leefomgeving"}]
    zaak = verrijk_zaak(dict(ZAAK), _feiten(), grondslag=grondslag)
    assert zaak["onderbouwing"]["wettelijke_grondslag"] == grondslag


def test_een_opgave_van_de_ondernemer_blijft_als_opgave_herkenbaar():
    """Het verschil tussen 'verklaard door uw netbeheerder' en 'u zei het zelf'
    is precies waar herleidbaarheid over gaat."""
    feiten = _feiten()
    feiten["TEELT_IN_KAS"] = {"waarde": False, "bron": "de ondernemer", "soort": "opgave"}
    zaak = verrijk_zaak(dict(ZAAK), feiten, grondslag=[])
    kenmerk = zaak["onderbouwing"]["bedrijfsgegevens"]["TEELT_IN_KAS"]
    assert kenmerk["soort"] == "opgave"
    assert kenmerk["bron"] == "de ondernemer"


def test_de_bestaande_velden_blijven_ongemoeid():
    """De frontend leest referentienummer en status; die vorm mag niet wijzigen."""
    zaak = verrijk_zaak(dict(ZAAK), _feiten(), grondslag=[])
    assert zaak["referentienummer"] == ZAAK["referentienummer"]
    assert zaak["status"] == "In behandeling"


def test_zonder_feiten_geen_lege_onderbouwing():
    """Een leeg blok suggereert dat er niets te onderbouwen viel."""
    zaak = verrijk_zaak(dict(ZAAK), {}, grondslag=[])
    assert "onderbouwing" not in zaak


def test_elk_dispatchpad_verrijkt_de_zaak():
    """Vier paden maken een case-event; alle vier moeten de onderbouwing meegeven.

    Dezelfde valkuil als bij de sessie-KvK en de toestemmingspoort: een waarde
    die op het ene pad wel en op het andere niet wordt meegegeven, valt niet op
    tot een respondent net dat pad raakt.
    """
    import ast
    from pathlib import Path

    bron = Path(__file__).resolve().parent.parent / "vlam_host.py"
    boom = ast.parse(bron.read_text())
    kaal = []
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.Dict):
            continue
        tekst = ast.unparse(knoop)
        if '"case"' not in tekst and "'case'" not in tekst:
            continue
        if "verrijk_zaak" not in tekst:
            kaal.append(f"regel {knoop.lineno}: {tekst[:60]}")
    assert not kaal, f"case-event zonder onderbouwing: {kaal}"

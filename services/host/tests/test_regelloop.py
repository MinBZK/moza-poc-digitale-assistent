"""De regel stuurt, de host haalt op.

De engine declareert laag voor laag wat hij mist. De lus draait door zolang hij
zelf verder kan en stopt waar toestemming nodig is of waar alleen de ondernemer
het antwoord heeft.
"""

import json

from regelloop import _parameters_uit_feiten, volg_regel


def _engine(stappen):
    """Een nep-engine die per aanroep de volgende stap teruggeeft."""
    beurten = iter(stappen)

    async def call_tool(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": next(beurten)})
        if naam == "kvk__mijn_bedrijf":
            return json.dumps({"data": {"is_woonfunctie": False}})
        raise AssertionError(f"onverwachte tool: {naam}")

    return call_tool


async def test_lus_haalt_op_wat_hij_zelf_kan():
    """Woonfunctie komt uit de KvK; daar is geen toestemming voor nodig."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"voldoet_aan_voorwaarden": True, "uitkomsten": {"heeft_informatieplicht": True}},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
    )
    assert uit.klaar is True
    assert uit.resultaat["uitkomsten"]["heeft_informatieplicht"] is True


async def test_lus_stopt_bij_een_bron_die_toestemming_vraagt():
    """PDR-008: geen bron vóór akkoord. De lus raadpleegt de wallet niet."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "JAARLIJKS_GASVERBRUIK_M3"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "toestemming"


async def test_lus_stopt_bij_iets_dat_alleen_de_ondernemer_weet():
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/maatregelen",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "opgave"


async def test_alle_openstaande_opgaven_gaan_in_een_keer_mee():
    """Eén formulier met alle vragen, niet één vraag per beurt.

    De lus stopt op het eerste veld dat hij niet zelf kan halen, maar de andere
    openstaande opgaven staan al in dezelfde respons. Zou hij ze één voor één
    melden, dan kost het de ondernemer drie beurten om drie vinkjes te zetten en
    stuit de lus na elk antwoord op de volgende.
    """
    call_tool = _engine([
        {
            "ontbrekende_gegevens": [
                {"naam": "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS", "beschrijving": "Teelt u in een gebouw?"},
                {"naam": "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF", "beschrijving": "Verlaagd tarief?"},
                {"naam": "AANWEZIGE_CATEGORIEEN", "beschrijving": "Welke categorieen?"},
            ]
        },
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/maatregelen",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.wacht_op == "opgave"
    assert [v["naam"] for v in uit.velden] == [
        "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS",
        "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF",
        "AANWEZIGE_CATEGORIEEN",
    ]
    assert uit.velden[0]["beschrijving"] == "Teelt u in een gebouw?"


async def test_een_veld_met_een_bron_hoort_niet_in_het_formulier():
    """Wat de host zelf kan ophalen, vraagt hij niet aan de ondernemer.

    `IS_WOONFUNCTIE` komt uit de BAG-verrijking. Zou hij in het formulier komen,
    dan vraagt de assistent iets wat hij al weet - en laat hij de ondernemer een
    registratie overschrijven die geen afleiding van ons is.
    """
    call_tool = _engine([
        {
            "ontbrekende_gegevens": [
                {"naam": "AANWEZIGE_CATEGORIEEN", "beschrijving": "Welke categorieen?"},
                {"naam": "IS_WOONFUNCTIE", "beschrijving": "Woonfunctie?"},
            ]
        },
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/maatregelen",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.wacht_op == "opgave"
    assert [v["naam"] for v in uit.velden] == ["AANWEZIGE_CATEGORIEEN"]


async def test_onbekend_veld_stopt_de_lus_in_plaats_van_te_raden():
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "OMZET_2025"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "onbekend"
    assert "OMZET_2025" in uit.reden


async def test_definitieve_negatieve_uitkomst_is_klaar_niet_onbekend():
    """`missing_required: False` zonder ontbrekende velden is een echt "nee".

    De engine heeft dan alles getoetst en niets mist; `voldoet_aan_voorwaarden`
    staat op False omdat de verplichting simpelweg niet geldt - dat is geen
    onbekende toestand.
    """
    call_tool = _engine([
        {"voldoet_aan_voorwaarden": False, "missing_required": False, "uitkomsten": {}},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is True
    assert uit.wacht_op is None
    assert uit.resultaat["voldoet_aan_voorwaarden"] is False


async def test_ontbrekend_missing_required_blijft_voorzichtig_onbekend():
    """Zonder het veld `missing_required` (oudere servervorm) niet aannemen
    dat het een definitief "nee" is."""
    call_tool = _engine([
        {"voldoet_aan_voorwaarden": False, "uitkomsten": {}},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "onbekend"


async def test_lus_loopt_niet_eindeloos_als_een_bron_niets_oplevert():
    """Een bron die het gevraagde veld niet levert mag geen oneindige lus geven.

    De KvK-tool geeft hier geen `is_woonfunctie` terug (in tegenstelling tot
    `_engine`), dus blijft de wet elke ronde opnieuw om IS_WOONFUNCTIE vragen.
    Zonder rondegrens draait dit voor altijd door.
    """
    beurten = iter([
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
    ])

    async def _leeg_kvk(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": next(beurten)})
        if naam == "kvk__mijn_bedrijf":
            return json.dumps({"data": {"naam": "Kwekerij De Bloesem"}})
        raise AssertionError(f"onverwachte tool: {naam}")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=_leeg_kvk,
        toestemming=True,
    )
    assert uit.klaar is False


def test_parameters_uit_feiten_slaat_een_echo_over():
    """Een echo is alleen wat WIJ als invoer instuurden, teruggekaatst door
    RegelRecht - nooit een eigen waarneming. Telt hij mee als wetsinvoer, dan
    wordt een door het model verzonnen override een feit dat de host de
    volgende ronde zelf weer als wetsinvoer aan de wet aanbiedt."""
    feiten = {
        "ELEKTRICITEIT_KWH": {
            "waarde": 999999,
            "bron": "RegelRecht (doorgegeven invoer)",
            "soort": "echo",
        }
    }
    parameters = _parameters_uit_feiten(feiten)
    assert "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH" not in parameters


def test_parameters_uit_feiten_gebruikt_wel_een_attestatie():
    """Tegenhanger van de vorige test: een echte attestatie telt gewoon mee."""
    feiten = {
        "ELEKTRICITEIT_KWH": {"waarde": 420000, "bron": "Business Wallet", "soort": "attestatie"}
    }
    parameters = _parameters_uit_feiten(feiten)
    assert parameters["JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"] == 420000


async def test_lus_stopt_meteen_als_een_ronde_geen_nieuw_feit_oplevert():
    """Voortgangsbewaking: geen tweede, derde... vijfde aanroep van dezelfde
    twee tools als de bron het gevraagde veld niet levert. `_leeg_kvk` in de
    test hierboven bewijst alleen dat de lus ooit stopt; deze test bewijst dat
    ze na de eerste mislukte poging stopt, niet na `MAX_RONDES`."""
    pogingen = {"execute_law": 0, "kvk": 0}

    async def _telt_aanroepen(naam, arguments):
        if naam == "regelrecht__execute_law":
            pogingen["execute_law"] += 1
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]}})
        if naam == "kvk__mijn_bedrijf":
            pogingen["kvk"] += 1
            # Levert nooit is_woonfunctie: precies de storing/lege-BAG-situatie
            # die de voortgangscontrole moet opvangen.
            return json.dumps({"data": {"naam": "Kwekerij De Bloesem"}})
        raise AssertionError(f"onverwachte tool: {naam}")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=_telt_aanroepen,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op is None
    # Eén ronde, en dan stoppen. Eerder waren dit er twee: BEDRIJFSNAAM kwam
    # als nieuwe sleutel binnen en telde toen als vooruitgang, ook al vroeg de
    # regel om IS_WOONFUNCTIE en leverde de KvK dát niet. Sinds de
    # voortgangsmaat naar "levert de bron het gevraagde veld" is gegaan, stopt
    # de lus meteen: een tweede aanroep van dezelfde bron voor hetzelfde veld
    # verloopt identiek en kost de respondent alleen tijd.
    assert pogingen == {"execute_law": 1, "kvk": 1}


async def test_bron_zonder_antwoord_laat_een_corrigeerbaar_veld_aan_de_ondernemer():
    """De KvK levert niet altijd wat wij eruit afleiden.

    `TEELT_GEWASSEN_IN_KAS` komt uit de SBI-omschrijving; een bedrijf zonder
    ingeschreven activiteiten levert die niet op. Zonder uitweg loopt de lus dan
    vast op "onbekend", terwijl de ondernemer zelf prima weet of hij in een kas
    teelt. Het veld is als corrigeerbaar gemarkeerd, dus mag hij het opgeven.
    """

    async def call_tool(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({
                "data": {"ontbrekende_gegevens": [
                    {"naam": "TEELT_GEWASSEN_IN_KAS", "beschrijving": "Teelt u in kassen?"}
                ]}
            })
        if naam == "kvk__mijn_bedrijf":
            # Geen sbiActiviteiten: de afleiding levert niets op.
            return json.dumps({"data": {"naam": "Zonder inschrijving BV"}})
        raise AssertionError(f"onverwachte tool: {naam}")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/maatregelen",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.wacht_op == "opgave"
    assert [v["naam"] for v in uit.velden] == ["TEELT_GEWASSEN_IN_KAS"]
    assert uit.velden[0]["beschrijving"] == "Teelt u in kassen?"


async def test_bron_zonder_antwoord_op_een_niet_corrigeerbaar_veld_blijft_onbekend():
    """`IS_WOONFUNCTIE` is een waarneming van de BAG, geen afleiding van ons.

    Levert die bron niets, dan is de uitkomst onbekend - de ondernemer mag een
    registratie niet overschrijven omdat een ophaling faalde.
    """

    async def call_tool(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]}})
        if naam == "kvk__mijn_bedrijf":
            return json.dumps({"data": {}})
        raise AssertionError(f"onverwachte tool: {naam}")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.wacht_op is None
    assert uit.velden == ()


# --- Voortgang meten aan het gevraagde veld, niet aan de sleutelverzameling ---


async def test_bron_levert_iets_anders_dan_het_gevraagde_veld():
    """Nieuwe sleutels zijn geen voortgang als het gevraagde veld ontbreekt.

    De lus mat voortgang met `set(feiten) == sleutels_voor`. Levert de wallet
    wel elektriciteit maar niet het gevraagde gas, dan komen er nieuwe sleutels
    bij (peiljaar, netbeheerder) en telde dat als vooruitgang: de volgende ronde
    riep dezelfde bron nog een keer aan. Voor de respondent is dat een tweede
    raadpleging van gegevens die hij net gedeeld heeft.
    """
    aanroepen = []

    async def call_tool(naam, arguments):
        aanroepen.append(naam)
        if naam == "regelrecht__execute_law":
            return json.dumps(
                {"data": {"ontbrekende_gegevens": [{"naam": "JAARLIJKS_GASVERBRUIK_M3"}]}}
            )
        if naam == "netbeheerder__verbruik":
            # Wel een geldige credential, maar zonder gas: alleen elektriciteit.
            return json.dumps(
                {
                    "data": {
                        "beschikbaar": True,
                        "verbruik": {
                            "totaal": {"jaarlijks_elektriciteitsverbruik_kwh": 420000}
                        },
                        "credential": {"peiljaar": 2025, "uitgegeven_door": "Stedin"},
                    }
                }
            )
        raise AssertionError(f"onverwachte tool: {naam}")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert aanroepen.count("netbeheerder__verbruik") == 1, (
        f"de wallet is meer dan een keer geraadpleegd: {aanroepen}"
    )


async def test_bron_levert_het_gevraagde_veld_als_overschrijving():
    """Een bestaande sleutel bijwerken is wél voortgang.

    Stond het gevraagde feit er al met een andere herkomst - een echo van de
    engine bijvoorbeeld - dan verandert de sleutelverzameling niet als de
    attestatie binnenkomt. De lus concludeerde dan 'gestopt zonder voortgang'
    en meldde 'onbekend', terwijl de Business Wallet het antwoord net had
    geleverd.
    """
    beurten = iter(
        [
            {"ontbrekende_gegevens": [{"naam": "JAARLIJKS_GASVERBRUIK_M3"}]},
            {"voldoet_aan_voorwaarden": True, "uitkomsten": {"heeft_informatieplicht": True}},
        ]
    )

    async def call_tool(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": next(beurten)})
        if naam == "netbeheerder__verbruik":
            return json.dumps(
                {
                    "data": {
                        "beschikbaar": True,
                        "verbruik": {
                            "totaal": {
                                "jaarlijks_elektriciteitsverbruik_kwh": 420000,
                                "jaarlijks_gasverbruik_m3": 140000,
                            }
                        },
                        "credential": {"peiljaar": 2025, "uitgegeven_door": "Stedin"},
                    }
                }
            )
        raise AssertionError(f"onverwachte tool: {naam}")

    # Alle sleutels die de wallet levert staan er al, met een andere herkomst.
    feiten = {
        naam: {"waarde": waarde, "bron": "RegelRecht (doorgegeven invoer)", "soort": "echo"}
        for naam, waarde in (
            ("ELEKTRICITEIT_KWH", 1),
            ("GAS_M3", 1),
            ("PEILJAAR", 1),
            ("NETBEHEERDER", "x"),
        )
    }
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten=feiten,
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is True, f"lus stopte onterecht: {uit.reden}"

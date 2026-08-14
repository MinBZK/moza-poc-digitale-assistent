"""Canonieke feiten uit tool-resultaten, als bron voor slot-substitutie.

Elk feit dat hier niet uit komt, moet het model uit het gesprek reconstrueren -
en dat is precies waar 'Bloemenlaan 12' vandaan kwam terwijl de KvK-tool
'Hoefweg 210' had geleverd.

De kvk-, netbeheerder- en rvo-testdata komt uit de echte MCP-servers
(importlib, zoals `test_kvk_multitenant.py` en `test_rvo_indienen.py` dat doen)
en niet uit een met de hand geschreven envelope. Een handgeschreven envelope
toetst alleen de aanname van wie hem schreef: `_uit_netbeheerder` en `_uit_kvk`
lazen ooit paden die de servers helemaal niet teruggeven (`data["totaal"]`
i.p.v. `data["verbruik"]["totaal"]`, `data["bag"]["is_woonfunctie"]` i.p.v. het
top-level `data["is_woonfunctie"]`) en de suite bleef groen omdat de
handgeschreven envelope toevallig wél de aangenomen vorm had. Door de servers
zelf de payload te laten leveren, breekt deze test zodra hun vorm wijzigt.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from feiten import feiten_uit_tool, samenvoegen

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"


def _load(pad_relatief: str, modulenaam: str):
    """Laad een MCP-servermodule vanaf schijf, los van sys.path/packaging."""
    pad = MCP_DIR / pad_relatief
    spec = importlib.util.spec_from_file_location(modulenaam, pad)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _kvk_resultaat(kvk_nummer: str) -> str:
    """De envelope die de KvK-server voor `mijn_bedrijf` teruggeeft (BAG incl.).

    Draait netwerkloos: het KvK-nummer zit in `MOCK_PROFIELEN` en het adres in
    `_BAG_DEMO_FALLBACK`, dus geen `BAG_API_KEY` nodig (niet gezet in deze
    omgeving).
    """
    srv = _load("kvk/server.py", "mcp_kvk_server_feitenkaart")
    resultaten = await srv.call_tool("mijn_bedrijf", {"kvk_nummer": kvk_nummer})
    return resultaten[0].text


def _netbeheerder_resultaat(kvk_nummer: str) -> str:
    """De envelope die de netbeheerder-server voor `verbruik` teruggeeft."""
    srv = _load("netbeheerder/server.py", "mcp_netbeheerder_server_feitenkaart")
    resultaten = srv._verbruik({"kvk_nummer": kvk_nummer})
    return resultaten[0].text


def _rvo_resultaat(kvk_nummer: str) -> str:
    """De envelope die de RVO-server voor `indienen` teruggeeft."""
    srv = _load("rvo/server.py", "mcp_rvo_server_feitenkaart")
    resultaten = srv._indienen(
        {
            "kvk_nummer": kvk_nummer,
            "regeling_id": "EBR-2026",
            "maatregelen": ["GF4: uitgevoerd"],
        }
    )
    return resultaten[0].text


def _envelope(data: dict) -> str:
    return json.dumps({"data": data, "provenance": {"source": "test"}})


@pytest.fixture
async def kvk_resultaat():
    """Envelope van de echte KvK-server, voor Kwekerij De Bloesem."""
    return await _kvk_resultaat("62345681")


@pytest.fixture
def netbeheerder_resultaat():
    """Envelope van de echte netbeheerder-server, voor Kwekerij De Bloesem."""
    return _netbeheerder_resultaat("62345681")


def test_een_feit_draagt_zijn_bron_en_soort(kvk_resultaat):
    """Herkomst hoort bij de waarde, niet ernaast.

    Een tweede dict die je erbij moet houden is precies de constructie waarlangs
    de provenance de vorige keer verdween.
    """
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", kvk_resultaat)
    naam = feiten["BEDRIJFSNAAM"]
    assert naam["waarde"] == "Kwekerij De Bloesem"
    assert naam["bron"] == "KvK Handelsregister"
    assert naam["soort"] == "registratie"


def test_verbruik_draagt_de_business_wallet_als_bron(netbeheerder_resultaat):
    feiten = feiten_uit_tool("netbeheerder__verbruik", netbeheerder_resultaat)
    assert feiten["ELEKTRICITEIT_KWH"]["bron"] == "Business Wallet"
    assert feiten["ELEKTRICITEIT_KWH"]["soort"] == "attestatie"


async def test_kvk_levert_naam_nummer_en_bezoekadres():
    """Kwekerij De Bloesem is de persona uit de regressie: 'Hoefweg 210'."""
    resultaat = await _kvk_resultaat("62345681")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["BEDRIJFSNAAM"]["waarde"] == "Kwekerij De Bloesem"
    assert feiten["KVK_NUMMER"]["waarde"] == "62345681"
    assert feiten["RECHTSVORM"]["waarde"] == "Vennootschap onder firma"
    assert feiten["VESTIGINGSNUMMER"]["waarde"] == "000062345681"
    assert feiten["VESTIGINGSADRES"]["waarde"] == "Hoefweg 210, 2665KG Bleiswijk"


async def test_adres_wordt_op_type_gekozen_niet_op_positie():
    """Vogel Bouwregie B.V. heeft een postbus als correspondentieadres.

    Dat is precies het geval waarin adres-op-positie kiezen het postbusadres
    zou opleveren i.p.v. het bezoekadres.
    """
    resultaat = await _kvk_resultaat("61234570")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["VESTIGINGSADRES"]["waarde"] == "Waalhaven 120, 3089JJ Rotterdam"


async def test_gebruiksdoel_met_één_waarde_wordt_leesbare_tekst():
    """`bag.gebruiksdoelen` is een lijst; met één waarde blijft dat leesbaar."""
    resultaat = await _kvk_resultaat("62345681")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["GEBRUIKSDOEL"]["waarde"] == "industriefunctie"
    assert feiten["WOONFUNCTIE"]["waarde"] is False


async def test_gebruiksdoel_met_meerdere_waarden_wordt_leesbare_tekst():
    """Vogel Bouwregie B.V. heeft een pand met twee gebruiksdoelen.

    Een Python-lijstrepresentatie ("['kantoorfunctie', 'industriefunctie']")
    hoort niet in de tekst van een rapport voor de ondernemer.
    """
    resultaat = await _kvk_resultaat("61234570")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["GEBRUIKSDOEL"]["waarde"] == "kantoorfunctie, industriefunctie"
    assert "[" not in feiten["GEBRUIKSDOEL"]["waarde"]
    assert feiten["WOONFUNCTIE"]["waarde"] is False


def test_netbeheerder_levert_verbruik_en_peiljaar():
    """Verbruik zit onder `verbruik.totaal`, peiljaar/uitgever onder `credential`.

    Niet op het hoogste niveau van `data` (PDR-008: de respons modelleert een
    Business Wallet-credential, geen platte verbruiksrespons).
    """
    resultaat = _netbeheerder_resultaat("62345681")
    feiten = feiten_uit_tool("netbeheerder__verbruik", resultaat)
    assert feiten["ELEKTRICITEIT_KWH"]["waarde"] == 420000
    assert feiten["GAS_M3"]["waarde"] == 140000
    assert feiten["PEILJAAR"]["waarde"] == 2025
    assert feiten["NETBEHEERDER"]["waarde"] == "Stedin (mock)"


def test_netbeheerder_zonder_attestatie_levert_niets():
    """Geen Business Wallet-attestatie (`beschikbaar: False`) → geen feiten.

    Niet nul-waarden of een gedeeltelijk gevulde dict: de host mag hier niet op
    gokken, en de assistent moet de gebruiker om het verbruik vragen.
    """
    resultaat = _netbeheerder_resultaat("00000000")
    assert feiten_uit_tool("netbeheerder__verbruik", resultaat) == {}


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
    assert feiten["DREMPEL_ELEKTRICITEIT_KWH"]["waarde"] == 50000
    assert feiten["DREMPEL_ELEKTRICITEIT_KWH"]["bron"] == "RegelRecht"
    assert feiten["DREMPEL_ELEKTRICITEIT_KWH"]["soort"] == "wetsconstante"
    assert feiten["OORDEEL_INFORMATIEPLICHT"]["waarde"] is True
    assert feiten["OORDEEL_ONDERZOEKSPLICHT"]["waarde"] is False
    assert feiten["VOLGENDE_DEADLINE"]["waarde"] == "2027-12-01"


def test_gebruikte_waarde_uit_regelrecht_is_een_echo_geen_attestatie():
    """`gebruikte_waarden` echoot terug wat wíj de engine gaven.

    Dat kan een feit uit de feitenkaart zijn, maar net zo goed een override
    die het model verzon - die twee zijn hier niet te onderscheiden. Krijgt
    zo'n waarde de soort van de oorspronkelijke bron (`attestatie`), dan zou
    een modelgestuurde override kunnen doorgaan voor een bevestigde attestatie
    van de netbeheerder, en de toestemmingsafleiding daarop kunnen leunen.
    """
    resultaat = _envelope(
        {"gebruikte_waarden": {"JAARLIJKS_GASVERBRUIK_M3": 140000}}
    )
    feiten = feiten_uit_tool("regelrecht__execute_law", resultaat)
    assert feiten["GAS_M3"]["waarde"] == 140000
    assert feiten["GAS_M3"]["soort"] == "echo"


def test_gebruikte_waarde_zonder_route_gebruikt_de_veldnaam_als_sleutel():
    """Een veld dat `regelrouting` niet kent, blijft onder zijn eigen naam staan."""
    resultaat = _envelope({"gebruikte_waarden": {"ONBEKEND_VELD": 42}})
    feiten = feiten_uit_tool("regelrecht__execute_law", resultaat)
    assert feiten["ONBEKEND_VELD"]["waarde"] == 42
    assert feiten["ONBEKEND_VELD"]["soort"] == "echo"


def test_oordeel_met_expliciete_null_levert_geen_feit_op():
    """Bug uit `NEXT_STEPS.md`: `_OORDELEN` filterde `None` niet weg.

    Een `null`-oordeel van de engine mocht nooit als slotwaarde eindigen ("De
    onderzoeksplicht geldt None voor u"); een feit zonder waarde is geen feit.
    """
    resultaat = _envelope({"uitkomsten": {"heeft_onderzoeksplicht": None}})
    feiten = feiten_uit_tool("regelrecht__execute_law", resultaat)
    assert "OORDEEL_ONDERZOEKSPLICHT" not in feiten


def test_rvo_levert_referentienummer():
    """`_uit_rvo` was nergens tegen de echte server getoetst.

    Dezelfde klasse fout als de kvk/netbeheerder-regressie hierboven:
    REFERENTIENUMMER ging in een gemeten run al eens mis, en handgeschreven
    testdata bevestigt alleen de aanname van wie hem schreef.
    """
    resultaat = _rvo_resultaat("62345681")
    feiten = feiten_uit_tool("rvo__indienen", resultaat)
    assert feiten["REFERENTIENUMMER"]["waarde"] == "RVO-EBR-2026-62345681-001"


def test_regelrecht_levert_de_uitkomstvelden_die_slots_md_aanbiedt():
    """RAPPORTAGE_METHODE, BEVOEGD_GEZAG en RAPPORTAGE_FREQUENTIE_JAREN staan in
    `slots.md` maar werden nergens tegen de echte engine gelegd.

    Geverifieerd op 2026-08-13 tegen de live RegelRecht-engine
    (https://ui.lac.projects.digilab.network/mcp/rpc, KvK 62345681): het
    `structuredContent.output` van de engine gaf exact deze sleutels terug, en
    `_simplify_result` in `services/mcp/regelrecht/server.py` zet dat ongewijzigd
    door naar `uitkomsten`. Dit is dus de vorm zoals de engine hem echt levert,
    niet een aanname.
    """
    resultaat = _envelope(
        {
            "uitkomsten": {
                "heeft_energiebesparingsplicht": True,
                "heeft_informatieplicht": True,
                "heeft_onderzoeksplicht": False,
                "rapportage_frequentie_jaren": 4,
                "volgende_rapportage_deadline": "2027-12-01",
                "rapportage_methode": "RVO eLoket (mijn.rvo.nl) met eHerkenning niveau 2+",
                "bevoegd_gezag": "gemeente",
            }
        }
    )
    feiten = feiten_uit_tool("regelrecht__execute_law", resultaat)
    assert feiten["OORDEEL_ENERGIEBESPARINGSPLICHT"]["waarde"] is True
    assert feiten["RAPPORTAGE_FREQUENTIE_JAREN"]["waarde"] == 4
    assert (
        feiten["RAPPORTAGE_METHODE"]["waarde"]
        == "RVO eLoket (mijn.rvo.nl) met eHerkenning niveau 2+"
    )
    assert feiten["BEVOEGD_GEZAG"]["waarde"] == "gemeente"


def test_echo_overschrijft_geen_bestaand_feit():
    """De kern van de eindreview-bevinding: de echo mag de attestatie niet verdringen.

    Nagemeten scenario: eerst levert de Business Wallet 420000 kWh als
    attestatie. De daaropvolgende wetsaanroep echoot diezelfde waarde terug
    (soort `echo`) - zonder deze regel overschrijft die echo het feit en is
    de herkomst na één ronde geen Business Wallet meer, precies de belofte
    die deze branch doet.
    """
    feiten: dict = {}
    samenvoegen(
        feiten,
        {"ELEKTRICITEIT_KWH": {"waarde": 420000, "bron": "Business Wallet", "soort": "attestatie"}},
    )
    samenvoegen(
        feiten,
        {
            "ELEKTRICITEIT_KWH": {
                "waarde": 420000,
                "bron": "RegelRecht (doorgegeven invoer)",
                "soort": "echo",
            }
        },
    )
    assert feiten["ELEKTRICITEIT_KWH"]["bron"] == "Business Wallet"
    assert feiten["ELEKTRICITEIT_KWH"]["soort"] == "attestatie"


def test_echo_overschrijft_geen_bestaand_feit_ook_niet_met_afwijkende_waarde():
    """Het ernstigere geval: een door het model verzonnen override komt als
    echo terug met een ANDERE waarde dan de echte attestatie. Zonder deze
    regel wint het verzonnen getal het van de Business Wallet-waarde."""
    feiten: dict = {}
    samenvoegen(
        feiten,
        {"ELEKTRICITEIT_KWH": {"waarde": 420000, "bron": "Business Wallet", "soort": "attestatie"}},
    )
    samenvoegen(
        feiten,
        {
            "ELEKTRICITEIT_KWH": {
                "waarde": 999999,
                "bron": "RegelRecht (doorgegeven invoer)",
                "soort": "echo",
            }
        },
    )
    assert feiten["ELEKTRICITEIT_KWH"]["waarde"] == 420000
    assert feiten["ELEKTRICITEIT_KWH"]["soort"] == "attestatie"


def test_echo_mag_wel_een_nieuw_feit_aanleggen():
    """Bestaat het feit nog niet, dan mag de echo hem wél toevoegen (bv. de
    eerste ronde). `_parameters_uit_feiten` in `regelloop.py` vertrouwt zo'n
    feit daarna sowieso niet als wetsinvoer (aparte test in
    `test_regelloop.py`)."""
    feiten: dict = {}
    samenvoegen(feiten, {"ONBEKEND_VELD": {"waarde": 42, "bron": "x", "soort": "echo"}})
    assert feiten["ONBEKEND_VELD"]["waarde"] == 42


def test_een_niet_echo_feit_overschrijft_gewoon():
    """Geen speciale regel voor registratie/attestatie/wetsconstante: die
    overschrijven zoals `dict.update` altijd deed - alleen de echo is bijzonder."""
    feiten = {"BEDRIJFSNAAM": {"waarde": "Oud", "bron": "KvK", "soort": "registratie"}}
    samenvoegen(feiten, {"BEDRIJFSNAAM": {"waarde": "Nieuw", "bron": "KvK", "soort": "registratie"}})
    assert feiten["BEDRIJFSNAAM"]["waarde"] == "Nieuw"


def test_onbekende_tool_levert_niets():
    assert feiten_uit_tool("koop__zoek_regelgeving", _envelope({"titel": "x"})) == {}


def test_kapot_resultaat_levert_niets_en_gooit_niet():
    """Een bron die rommel teruggeeft mag het gesprek niet laten klappen."""
    assert feiten_uit_tool("kvk__mijn_bedrijf", "geen json") == {}

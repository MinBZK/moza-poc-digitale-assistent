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

from feiten import feiten_uit_tool

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


async def test_kvk_levert_naam_nummer_en_bezoekadres():
    """Kwekerij De Bloesem is de persona uit de regressie: 'Hoefweg 210'."""
    resultaat = await _kvk_resultaat("62345681")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["BEDRIJFSNAAM"] == "Kwekerij De Bloesem"
    assert feiten["KVK_NUMMER"] == "62345681"
    assert feiten["RECHTSVORM"] == "Vennootschap onder firma"
    assert feiten["VESTIGINGSNUMMER"] == "000062345681"
    assert feiten["VESTIGINGSADRES"] == "Hoefweg 210, 2665KG Bleiswijk"


async def test_adres_wordt_op_type_gekozen_niet_op_positie():
    """Vogel Bouwregie B.V. heeft een postbus als correspondentieadres.

    Dat is precies het geval waarin adres-op-positie kiezen het postbusadres
    zou opleveren i.p.v. het bezoekadres.
    """
    resultaat = await _kvk_resultaat("61234570")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["VESTIGINGSADRES"] == "Waalhaven 120, 3089JJ Rotterdam"


async def test_gebruiksdoel_met_één_waarde_wordt_leesbare_tekst():
    """`bag.gebruiksdoelen` is een lijst; met één waarde blijft dat leesbaar."""
    resultaat = await _kvk_resultaat("62345681")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["GEBRUIKSDOEL"] == "industriefunctie"
    assert feiten["WOONFUNCTIE"] is False


async def test_gebruiksdoel_met_meerdere_waarden_wordt_leesbare_tekst():
    """Vogel Bouwregie B.V. heeft een pand met twee gebruiksdoelen.

    Een Python-lijstrepresentatie ("['kantoorfunctie', 'industriefunctie']")
    hoort niet in de tekst van een rapport voor de ondernemer.
    """
    resultaat = await _kvk_resultaat("61234570")
    feiten = feiten_uit_tool("kvk__mijn_bedrijf", resultaat)
    assert feiten["GEBRUIKSDOEL"] == "kantoorfunctie, industriefunctie"
    assert "[" not in feiten["GEBRUIKSDOEL"]
    assert feiten["WOONFUNCTIE"] is False


def test_netbeheerder_levert_verbruik_en_peiljaar():
    """Verbruik zit onder `verbruik.totaal`, peiljaar/uitgever onder `credential`.

    Niet op het hoogste niveau van `data` (PDR-008: de respons modelleert een
    Business Wallet-credential, geen platte verbruiksrespons).
    """
    resultaat = _netbeheerder_resultaat("62345681")
    feiten = feiten_uit_tool("netbeheerder__verbruik", resultaat)
    assert feiten["ELEKTRICITEIT_KWH"] == 420000
    assert feiten["GAS_M3"] == 140000
    assert feiten["PEILJAAR"] == 2025
    assert feiten["NETBEHEERDER"] == "Stedin (mock)"


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
    assert feiten["DREMPEL_ELEKTRICITEIT_KWH"] == 50000
    assert feiten["OORDEEL_INFORMATIEPLICHT"] is True
    assert feiten["OORDEEL_ONDERZOEKSPLICHT"] is False
    assert feiten["VOLGENDE_DEADLINE"] == "2027-12-01"


def test_rvo_levert_referentienummer():
    """`_uit_rvo` was nergens tegen de echte server getoetst.

    Dezelfde klasse fout als de kvk/netbeheerder-regressie hierboven:
    REFERENTIENUMMER ging in een gemeten run al eens mis, en handgeschreven
    testdata bevestigt alleen de aanname van wie hem schreef.
    """
    resultaat = _rvo_resultaat("62345681")
    feiten = feiten_uit_tool("rvo__indienen", resultaat)
    assert feiten["REFERENTIENUMMER"] == "RVO-EBR-2026-62345681-001"


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
    assert feiten["OORDEEL_ENERGIEBESPARINGSPLICHT"] is True
    assert feiten["RAPPORTAGE_FREQUENTIE_JAREN"] == 4
    assert feiten["RAPPORTAGE_METHODE"] == "RVO eLoket (mijn.rvo.nl) met eHerkenning niveau 2+"
    assert feiten["BEVOEGD_GEZAG"] == "gemeente"


def test_onbekende_tool_levert_niets():
    assert feiten_uit_tool("koop__zoek_regelgeving", _envelope({"titel": "x"})) == {}


def test_kapot_resultaat_levert_niets_en_gooit_niet():
    """Een bron die rommel teruggeeft mag het gesprek niet laten klappen."""
    assert feiten_uit_tool("kvk__mijn_bedrijf", "geen json") == {}

"""Guard: demo-persona's en de informatieplicht-flow (Dag van de Toekomst).

De flow voor Claudia van Dam / Koffiezaak Noon steunt op invarianten die
over drie MCP-servers verspreid staan (kvk, netbeheerder, regelrecht).
Deze tests borgen dat de mock-data consistent blijft: één afwijkend
KvK-nummer of een verbruik dat onder de drempel zakt, breekt de demo stil.

De MCP-servers staan buiten de pythonpath (services/host); we laden ze
per bestandspad. De servers starten geen verbindingen bij import.
"""

import importlib.util
import json
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"

NOON_KVK = "85234567"


def _load(naam: str):
    """Laad een MCP-servermodule op bestandspad."""
    pad = MCP_DIR / naam / "server.py"
    spec = importlib.util.spec_from_file_location(f"mcp_{naam}_server", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_noon_bestaat_in_kvk_mock():
    kvk = _load("kvk")
    profiel = kvk.MOCK_PROFIELEN[NOON_KVK]
    assert profiel["naam"] == "Koffiezaak Noon"
    hoofdactiviteit = profiel["sbiActiviteiten"][0]
    assert hoofdactiviteit["sbiCode"] == "56102"
    # Vestigingen en eigenaar horen bij hetzelfde nummer beschikbaar te zijn
    assert NOON_KVK in kvk.MOCK_VESTIGINGEN
    assert NOON_KVK in kvk.MOCK_EIGENAREN
    eigenaar = kvk.MOCK_EIGENAREN[NOON_KVK]["natuurlijkPersoon"]
    assert eigenaar["volledigeNaam"] == "Claudia van Dam"


def test_noon_adres_heeft_bag_fallback_zonder_woonfunctie():
    kvk = _load("kvk")
    adres = kvk.MOCK_PROFIELEN[NOON_KVK]["_embedded"]["hoofdvestiging"]["adressen"][0]
    key = f"{adres['postcode']}-{adres['huisnummer']}"
    bag = kvk._BAG_DEMO_FALLBACK[key]
    # De woonfunctie-uitzondering mag NIET gelden, anders vervalt de plicht
    assert bag["gebruiksdoelen"] != ["woonfunctie"]


def test_noon_verbruik_boven_elektriciteitsdrempel():
    netbeheerder = _load("netbeheerder")
    verbruik = netbeheerder._verbruik_voor(NOON_KVK)
    assert verbruik is not None, "Noon moet bekend zijn bij de netbeheerder-mock"
    totaal = verbruik["totaal"]
    # Kern van de demo: elektriciteit boven 50.000 kWh => informatieplicht geldt
    assert totaal["jaarlijks_elektriciteitsverbruik_kwh"] > 50_000
    assert totaal["jaarlijks_gasverbruik_m3"] < 25_000


def test_netbeheerder_onbekend_kvk_geeft_geen_data():
    netbeheerder = _load("netbeheerder")
    assert netbeheerder._verbruik_voor("68750110") is None, (
        "Test BV Donald hoort GEEN netbeheerder-data te hebben: de bestaande "
        "demo-flow (verbruik uitvragen bij de gebruiker) moet blijven werken."
    )


def test_wallet_presenteert_attestatie_met_toestemming():
    """De energiegegevens komen als door de Business Wallet gepresenteerde credential.

    Demo-model EU Business Wallet: bron = Business Wallet, uitgever = netbeheerder,
    met expliciete toestemming. Het verbruik moet binnen de credential
    leesbaar blijven voor de assistent.
    """
    netbeheerder = _load("netbeheerder")
    resultaat = netbeheerder._verbruik({"kvk_nummer": NOON_KVK})
    payload = json.loads(resultaat[0].text)

    # Bron is de Business Wallet; de netbeheerder is de uitgever van de attestatie
    assert "Business Wallet" in payload["provenance"]["source"]
    assert payload["provenance"]["issuer"] == netbeheerder.ISSUER_LABEL

    data = payload["data"]
    assert data["beschikbaar"] is True
    assert data["credential"]["type"] == "EnergieverbruikAttestatie"
    assert data["toestemming"]["met_toestemming_ondernemer"] is True
    # Het verbruik blijft leesbaar — kern van de demo (boven de drempel)
    assert data["verbruik"]["totaal"]["jaarlijks_elektriciteitsverbruik_kwh"] > 50_000


def test_eml_fallback_volgt_bedrijfskenmerken():
    regelrecht = _load("regelrecht")
    data = regelrecht._eml_fallback(
        {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": False}
    )
    per_code = {m["code"]: m["van_toepassing"] for m in data["maatregelen"]}
    # onvoorwaardelijke maatregelen gelden altijd
    assert per_code["GF4"] is True
    # koelinstallatie=True activeert de productkoeling-maatregelen
    assert per_code["FD3"] is True
    # afzuiginstallatie=False deactiveert de afzuig-/ventilatiemaatregelen
    assert per_code["FE4"] is False


def test_eml_fallback_zonder_feiten_geeft_de_twee_vragen():
    regelrecht = _load("regelrecht")
    data = regelrecht._eml_fallback({})
    assert [v["naam"] for v in data["benodigde_feiten"]] == [
        "HEEFT_KOELINSTALLATIE",
        "HEEFT_AFZUIGINSTALLATIE",
    ]


# --- Onderzoekspersona 25/27 augustus 2026: Robin Vogel als bloemenkweker -----
#
# Waarden zoals MinBZK/poc-moza ze toont voor `?persona=bloemenkweker`
# (_data/personas.json), overgenomen uit commit 205fffc2. De frontend is
# leidend: de respondent leest deze op de pagina's Bedrijfsgegevens en
# Adresgegevens, en de assistent hoort er niets anders over te zeggen.
#
# Alleen velden die het KvK Basisprofiel kent staan hier. De frontend toont
# daarnaast btw-, omzetbelasting- en loonheffingennummer en een IBAN; die komen
# van de Belastingdienst en de bank, en horen dus niet uit een KvK-mock te
# rollen.
BLOEMENKWEKER_FRONTEND = {
    "kvkNummer": "62345681",
    "handelsnaam": "Kwekerij De Bloesem",
    "rechtsvorm": "Vennootschap onder firma",
    "rsin": "62345681",
    "vestigingsnummer": "000062345681",
    "voltijdWerkzamePersonen": 5,
    "deeltijdWerkzamePersonen": 2,
    "website": "https://www.kwekerijdebloesem.nl",
    "postcode": "2665KG",
    "huisnummer": 210,
    "plaats": "Bleiswijk",
}


def test_bloemenkweker_komt_overeen_met_de_frontend():
    """De persona van het gebruikersonderzoek, over twee repo's heen.

    Robin Vogel is in de frontend vennoot van een VOF. Voor een VOF levert het
    KvK Basisprofiel terecht de vennootschap als eigenaar en géén natuurlijk
    persoon — dat is dus geen bug om te "repareren".
    """
    kvk = _load("kvk")
    nummer = BLOEMENKWEKER_FRONTEND["kvkNummer"]
    profiel = kvk.MOCK_PROFIELEN[nummer]
    eigenaar = kvk.MOCK_EIGENAREN[nummer]

    assert profiel["naam"] == BLOEMENKWEKER_FRONTEND["handelsnaam"]
    assert profiel["rechtsvorm"] == BLOEMENKWEKER_FRONTEND["rechtsvorm"]
    assert eigenaar["rechtsvorm"] == BLOEMENKWEKER_FRONTEND["rechtsvorm"]
    # De pagina Bedrijfsgegevens toont het RSIN; zonder dit veld in het profiel
    # kent de assistent alleen de eigenaar-route ernaartoe.
    assert profiel["rsin"] == BLOEMENKWEKER_FRONTEND["rsin"]
    assert eigenaar["rechtspersoon"]["rsin"] == BLOEMENKWEKER_FRONTEND["rsin"]
    assert (
        profiel["_embedded"]["hoofdvestiging"]["vestigingsnummer"]
        == BLOEMENKWEKER_FRONTEND["vestigingsnummer"]
    )
    # Een VOF heeft geen natuurlijk persoon als eigenaar; die vorm hoort te blijven.
    assert "rechtspersoon" in eigenaar
    assert "natuurlijkPersoon" not in eigenaar


def test_bloemenkweker_personeel_en_website_volgen_de_frontend():
    """Zonder het voltijdveld antwoordt de assistent "7" op een scherm dat "5" toont.

    Beide getallen zijn waar — het echte Basisprofiel kent totaal én voltijd —
    maar de respondent ziet alleen het voltijdgetal en zou het verschil als een
    fout lezen.
    """
    profiel = _load("kvk").MOCK_PROFIELEN["62345681"]
    voltijd = BLOEMENKWEKER_FRONTEND["voltijdWerkzamePersonen"]
    deeltijd = BLOEMENKWEKER_FRONTEND["deeltijdWerkzamePersonen"]
    assert profiel["voltijdWerkzamePersonen"] == voltijd
    assert profiel["deeltijdWerkzamePersonen"] == deeltijd
    # Het totaal is geen los feit maar de som; loopt dat uiteen, dan spreekt de
    # assistent zichzelf tegen tussen twee antwoorden.
    assert profiel["totaalWerkzamePersonen"] == voltijd + deeltijd
    assert BLOEMENKWEKER_FRONTEND["website"] in profiel["websites"]

    # De hoofdvestiging draagt dezelfde aantallen; de assistent kan beide routes
    # nemen en hoort er hetzelfde getal uit te halen.
    hoofdvestiging = profiel["_embedded"]["hoofdvestiging"]
    assert hoofdvestiging["voltijdWerkzamePersonen"] == voltijd
    assert hoofdvestiging["deeltijdWerkzamePersonen"] == deeltijd


def test_bloemenkweker_heeft_vestigings_en_postadres():
    """De pagina Adresgegevens toont beide; één adres maakt het andere onbekend."""
    profiel = _load("kvk").MOCK_PROFIELEN["62345681"]
    adressen = profiel["_embedded"]["hoofdvestiging"]["adressen"]
    per_type = {adres["type"]: adres for adres in adressen}
    assert set(per_type) == {"bezoekadres", "correspondentieadres"}
    for adres in per_type.values():
        assert adres["postcode"] == BLOEMENKWEKER_FRONTEND["postcode"]
        assert adres["huisnummer"] == BLOEMENKWEKER_FRONTEND["huisnummer"]
        assert adres["plaats"] == BLOEMENKWEKER_FRONTEND["plaats"]


def test_bloemenkweker_is_indieningsplichtig():
    """De hele onderzoeksflow hangt hieraan.

    Zakt dit onder de drempel, dan is er niets te rapporteren en valt het
    testscript uit elkaar: geen maatregelen, geen indiening, geen lopende zaak.
    """
    totaal = _load("netbeheerder").MOCK_VERBRUIK["62345681"]["totaal"]
    assert totaal["jaarlijks_elektriciteitsverbruik_kwh"] > 50000
    assert totaal["jaarlijks_gasverbruik_m3"] > 25000


def test_elke_mockpersona_is_compleet():
    """Een persona bestaat in alle lagen, of nergens.

    De blokkade die het gebruikersonderzoek van augustus 2026 bijna sloopte was
    precies dit: de frontend bood persona's aan die de backend niet kende.
    """
    kvk = _load("kvk")
    netbeheerder = _load("netbeheerder")

    for nummer in kvk.MOCK_PROFIELEN:
        assert nummer in kvk.MOCK_EIGENAREN, (
            f"{nummer} heeft een profiel maar geen eigenaar; `kvk__eigenaar` valt "
            f"dan terug op de echte KvK-API en faalt voor een mock-persona"
        )
        assert nummer in netbeheerder.MOCK_VERBRUIK, (
            f"{nummer} heeft een profiel maar geen verbruik; de assistent kan de "
            f"informatieplicht dan niet beoordelen en gaat het uitvragen"
        )

"""Guard: demo-persona's en de informatieplicht-flow (Dag van de Toekomst).

De flow voor Claudia van Dam / Koffiezaak Noon steunt op invarianten die
over drie MCP-servers verspreid staan (kvk, netbeheerder, regelrecht).
Deze tests borgen dat de mock-data consistent blijft: één afwijkend
KvK-nummer of een verbruik dat onder de drempel zakt, breekt de demo stil.

De MCP-servers staan buiten de pythonpath (services/host); we laden ze
per bestandspad. De servers starten geen verbindingen bij import.
"""

import asyncio
import importlib.util
import json
from functools import cache
from pathlib import Path

import pytest

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"

NOON_KVK = "85234567"


@cache
def _load(naam: str):
    """Laad een MCP-servermodule op bestandspad.

    Gecachet: de tests lezen alleen module-constanten, en `exec_module` draait
    anders per test de hele server opnieuw.
    """
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
    # Via _extract_address, want dat is het adres dat de verrijking ook pakt.
    adres = kvk._extract_address(kvk.MOCK_PROFIELEN[NOON_KVK])
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


# --- Onderzoekspersona's -----------------------------------------------------
#
# Of de mock-data gelijk is aan wat de frontend op het scherm toont, staat in
# `test_personas_frontend_pariteit.py`: die leest `_data/personas.json` van
# MinBZK/moza-poc echt uit. Hier staan de invarianten die de backend op eigen
# kracht moet halen, zonder die repo.


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

    Ontbreekt er één laag, dan valt die tool terug op de echte KvK-API met een
    nummer dat daar niet bestaat: de bron faalt middenin een sessie. De BAG-laag
    faalt stiller — dan mist de woonfunctie-toets zijn invoer en wordt het
    oordeel over de informatieplicht geveld zonder dat de uitzondering is
    bekeken.
    """
    kvk = _load("kvk")
    netbeheerder = _load("netbeheerder")

    for nummer, profiel in kvk.MOCK_PROFIELEN.items():
        assert nummer in kvk.MOCK_EIGENAREN, (
            f"{nummer} heeft een profiel maar geen eigenaar; `kvk__eigenaar` valt "
            f"dan terug op de echte KvK-API en faalt voor een mock-persona"
        )
        assert nummer in kvk.MOCK_VESTIGINGEN, (
            f"{nummer} heeft een profiel maar geen vestigingen; `kvk__vestigingen` "
            f"valt dan terug op de echte KvK-API en faalt voor een mock-persona"
        )
        assert nummer in netbeheerder.MOCK_VERBRUIK, (
            f"{nummer} heeft een profiel maar geen verbruik; de assistent kan de "
            f"informatieplicht dan niet beoordelen en gaat het uitvragen"
        )

        vestigingsnummer = profiel["_embedded"]["hoofdvestiging"]["vestigingsnummer"]
        assert vestigingsnummer in kvk.MOCK_VESTIGINGSPROFIELEN, (
            f"{nummer} heeft geen vestigingsprofiel; de assistent noemt dan het "
            f"totaal aantal medewerkers waar het scherm voltijd en deeltijd toont"
        )

        adres = kvk._extract_address(profiel)
        assert adres is not None, f"{nummer} heeft geen bruikbaar adres"
        sleutel = f"{adres['postcode'].replace(' ', '')}-{adres['huisnummer']}"
        assert sleutel in kvk._BAG_DEMO_FALLBACK, (
            f"{nummer} heeft geen BAG-fallback op {sleutel}; de woonfunctie-toets "
            f"verliest dan stil zijn invoer"
        )


def test_extract_address_kiest_het_bezoekadres_niet_het_eerste():
    """Het correspondentieadres staat in de API-volgorde vóór het bezoekadres.

    Kiest de extractie op positie in plaats van op type, dan gaat de
    BAG-verrijking naar een postbus: geen pand, geen gebruiksdoel, en de
    woonfunctie-uitzondering wordt beoordeeld op het verkeerde adres.
    """
    kvk = _load("kvk")
    profiel = {
        "_embedded": {
            "hoofdvestiging": {
                "adressen": [
                    {"type": "correspondentieadres", "postcode": "3009AC"},
                    {"type": "bezoekadres", "postcode": "3089JJ"},
                ]
            }
        }
    }
    assert kvk._extract_address(profiel)["postcode"] == "3089JJ"


def test_extract_address_valt_terug_als_er_geen_bezoekadres_is():
    kvk = _load("kvk")
    profiel = {
        "_embedded": {
            "hoofdvestiging": {
                "adressen": [{"type": "correspondentieadres", "postcode": "3009AC"}]
            }
        }
    }
    assert kvk._extract_address(profiel)["postcode"] == "3009AC"
    assert kvk._extract_address({"_embedded": {"hoofdvestiging": {}}}) is None


def test_bouwmanagement_gebruikt_het_bezoekadres_voor_de_bag():
    """De enige persona met een postbus als postadres — het discriminerende geval."""
    kvk = _load("kvk")
    adres = kvk._extract_address(kvk.MOCK_PROFIELEN["61234570"])
    assert adres["type"] == "bezoekadres"
    assert adres["postcode"] == "3089JJ"
    assert "3009AC-8120" not in kvk._BAG_DEMO_FALLBACK


def test_mijn_bedrijf_levert_de_personeelsuitsplitsing_uit():
    """De data in de dict zegt niets als de tool hem niet doorgeeft.

    Het basisprofiel kent alleen het totaal; voltijd en deeltijd komen uit het
    vestigingsprofiel. Blijft die verrijking achterwege, dan antwoordt de
    assistent "7" op een scherm dat "5 voltijd, 2 deeltijd" toont.
    """
    kvk = _load("kvk")
    profiel = asyncio.run(
        kvk._enrich_with_vestigingsprofiel(kvk.MOCK_PROFIELEN["62345681"])
    )
    hoofdvestiging = profiel["_embedded"]["hoofdvestiging"]
    assert hoofdvestiging["voltijdWerkzamePersonen"] == 5
    assert hoofdvestiging["deeltijdWerkzamePersonen"] == 2
    assert hoofdvestiging["totaalWerkzamePersonen"] == 7

    # De verrijking mag de cache niet muteren: die deelt het dict tussen sessies.
    assert "voltijdWerkzamePersonen" not in (
        kvk.MOCK_PROFIELEN["62345681"]["_embedded"]["hoofdvestiging"]
    )


def test_leeg_vestigingsprofielveld_overschrijft_het_basisprofiel_niet(monkeypatch):
    """De KvK-API geeft een geregistreerd-maar-leeg veld terug als null of [].

    Toets je op aanwezigheid van de sleutel in plaats van op de waarde, dan
    vervangt zo'n leeg veld een gevulde waarde uit het basisprofiel en vertelt
    de assistent de ondernemer dat zijn bedrijf geen website heeft.
    """
    kvk = _load("kvk")
    profiel = {
        "kvkNummer": "99999999",
        "_embedded": {
            "hoofdvestiging": {
                "vestigingsnummer": "000099999999",
                "websites": ["https://www.example.nl"],
                "totaalWerkzamePersonen": 3,
            }
        },
    }

    async def _leeg(_nummer):
        return {
            "websites": [],
            "voltijdWerkzamePersonen": None,
            "deeltijdWerkzamePersonen": 0,
        }

    monkeypatch.setattr(kvk, "_get_vestigingsprofiel", _leeg)
    hoofdvestiging = asyncio.run(kvk._enrich_with_vestigingsprofiel(profiel))[
        "_embedded"
    ]["hoofdvestiging"]

    assert hoofdvestiging["websites"] == ["https://www.example.nl"]
    assert "voltijdWerkzamePersonen" not in hoofdvestiging
    # Nul is een geldig antwoord en geen ontbrekende waarde: die hoort wél mee.
    assert hoofdvestiging["deeltijdWerkzamePersonen"] == 0


def test_mijn_bedrijf_overleeft_een_falend_vestigingsprofiel(monkeypatch):
    """Een profiel zonder uitsplitsing is beter dan een foutmelding."""
    kvk = _load("kvk")
    profiel = {
        "kvkNummer": "99999999",
        "_embedded": {"hoofdvestiging": {"vestigingsnummer": "000099999999"}},
    }

    def _weigeren(_pad):
        raise kvk.URLError("geen netwerk")

    monkeypatch.setattr(kvk, "_kvk_fetch", _weigeren)
    resultaat = asyncio.run(kvk._enrich_with_vestigingsprofiel(profiel))
    assert resultaat == profiel


@pytest.mark.parametrize(
    "fout",
    [
        TimeoutError("read timeout"),
        json.JSONDecodeError("geen JSON", "<html>", 0),
        ValueError("onverwacht"),
    ],
)
def test_vestigingsprofiel_laat_geen_enkele_fout_ontsnappen(monkeypatch, fout):
    """`_kvk_fetch` doet `json.loads` binnen het `urlopen`-blok.

    Een read-timeout, een HTML-foutpagina en een afgebroken verbinding zijn
    daardoor geen van drie een `HTTPError` of `URLError`. Ontsnappen ze, dan
    komt hun tekst via `call_tool` bij het LLM terecht — wat PDR-011 verbiedt.
    """
    kvk = _load("kvk")
    profiel = {
        "kvkNummer": "99999999",
        "_embedded": {"hoofdvestiging": {"vestigingsnummer": "000099999999"}},
    }

    def _weigeren(_pad):
        raise fout

    monkeypatch.setattr(kvk, "_kvk_fetch", _weigeren)
    assert asyncio.run(kvk._enrich_with_vestigingsprofiel(profiel)) == profiel

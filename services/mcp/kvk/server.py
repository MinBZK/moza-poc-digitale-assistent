"""KvK MCP-server — Bedrijfsgegevens van de ingelogde gebruiker via MCP.

Haalt bedrijfsgegevens op via de KvK Test API (api.kvk.nl/test/api) voor het
KvK-nummer dat de host per aanroep meegeeft. De host bepaalt dat nummer
server-side uit de sessie (MVP-01/PDR-009); de server bedient dat bedrijf en
is daarmee multi-tenant (cache per KvK-nummer).

Verrijkt het profiel automatisch met BAG-gegevens (gebruiksdoel pand)
via de PDOK LVBAG API. Hiermee kan de woonfunctie-check automatisch
worden ingevuld bij de RegelRecht-toets, zonder dat de gebruiker dit
zelf hoeft op te geven.

Er is geen hardcoded demo-bedrijf meer. Voor standalone gebruik (buiten de
host) kan DEMO_KVK_NUMMER als dev-fallback gezet worden; anders weigert de
server zonder sessie-KvK. Echte authenticatie is BETA-02.

Voldoet aan de MCP-standaard voor Generieke Interactieservices:
- Provenance metadata bij elke resource-response (§4.1, §7)
- ToolAnnotations op elke tool (§4.2, §7)
- Audit logging bij elke tool-aanroep (§2.2)
- Beschrijvingen en inputschema's (§7)
"""

import asyncio
import json
import logging
import os
import re
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    ResourceTemplate,
    TextContent,
    Tool,
    ToolAnnotations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [kvk] %(message)s")
logger = logging.getLogger("kvk")

server = Server(name="kvk")

SOURCE_LABEL = "KvK Handelsregister (testomgeving — sessie-gebonden)"
SERVER_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Configuratie KvK Test API
# ---------------------------------------------------------------------------

KVK_TEST_BASE = "https://api.kvk.nl/test/api"
KVK_TEST_API_KEY = "l7xx1f2691f2520d487b902f4e0b57a0b197"

# Het KvK-nummer wordt per aanroep meegegeven door de host, die het server-side
# uit de sessie bepaalt (MVP-01/PDR-009). Er is bewust GEEN hardcoded default
# meer: zonder sessie-KvK (en zonder DEMO_KVK_NUMMER voor standalone dev) weigert
# de server. Zo ziet niet iedereen hetzelfde demo-bedrijf.
def _resolve_kvk(arguments: dict | None) -> str | None:
    """Bepaal het te bedienen KvK-nummer voor deze aanroep.

    Eerst het door de host meegegeven `kvk_nummer`; anders de optionele
    DEMO_KVK_NUMMER (dev-fallback voor wie de server standalone draait, buiten de
    host). Geen waarde => None, en de aanroeper krijgt een nette fout.
    """
    kvk = str((arguments or {}).get("kvk_nummer") or "").strip()
    if kvk:
        return kvk
    return (os.getenv("DEMO_KVK_NUMMER") or "").strip() or None


# Cache per KvK-nummer (de server bedient meerdere bedrijven binnen zijn lifetime)
_profiel_cache: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Mock-persona's — KvK-nummers die niet in de KvK Test API bestaan en
# volledig lokaal worden geserveerd. Vorm volgt de KvK Basisprofiel API
# zodat downstream-logica (adres-extractie, BAG-verrijking) identiek werkt.
#
# Welk veld op welk niveau hoort, is afgelezen aan de echte Test API en niet
# aan wat handig uitkomt. Het basisprofiel draagt `totaalWerkzamePersonen`;
# de uitsplitsing naar voltijd en deeltijd, het RSIN en de websites zitten in
# het vestigingsprofiel (MOCK_VESTIGINGSPROFIELEN) respectievelijk bij de
# eigenaar. Zet je ze op de profielwortel, dan werkt de mock wél en een echt
# KvK-nummer niet — en dat verschil merk je pas tijdens een sessie.
#
# De adressenlijst staat in API-volgorde: correspondentieadres eerst, dan
# bezoekadres. `_extract_address` kiest daarom op type en niet op positie.
#
# Waarden volgen MinBZK/moza-poc `_data/personas.json`: de respondent leest ze
# op het scherm. `tests/test_personas_frontend_pariteit.py` leest dat bestand
# en faalt zodra de twee repo's uiteenlopen.
# ---------------------------------------------------------------------------

MOCK_PROFIELEN: dict[str, dict] = {
    "85234567": {
        "kvkNummer": "85234567",
        "naam": "Koffiezaak Noon",
        "rechtsvorm": "Eenmanszaak",
        "totaalWerkzamePersonen": 4,
        "handelsnamen": [{"naam": "Koffiezaak Noon", "volgorde": 0}],
        "sbiActiviteiten": [
            {
                "sbiCode": "56102",
                "sbiOmschrijving": "Cafés",
                "indHoofdactiviteit": "Ja",
            }
        ],
        "materieleRegistratie": {"datumAanvang": "20210314"},
        "statusinformatie": "actief",
        "_embedded": {
            "hoofdvestiging": {
                "vestigingsnummer": "000085234567",
                "eersteHandelsnaam": "Koffiezaak Noon",
                "indHoofdvestiging": "Ja",
                "totaalWerkzamePersonen": 4,
                "websites": ["https://www.koffiezaaknoon.nl"],
                "adressen": [
                    {
                        "type": "correspondentieadres",
                        "volledigAdres": "Meent 88, 3011JM Rotterdam",
                        "straatnaam": "Meent",
                        "huisnummer": 88,
                        "postcode": "3011JM",
                        "plaats": "Rotterdam",
                    },
                    {
                        "type": "bezoekadres",
                        "volledigAdres": "Meent 88, 3011JM Rotterdam",
                        "straatnaam": "Meent",
                        "huisnummer": 88,
                        "postcode": "3011JM",
                        "plaats": "Rotterdam",
                    },
                ],
                "sbiActiviteiten": [
                    {
                        "sbiCode": "56102",
                        "sbiOmschrijving": "Cafés",
                        "indHoofdactiviteit": "Ja",
                    }
                ],
            }
        },
    },
    "62345681": {
        "kvkNummer": "62345681",
        "naam": "Kwekerij De Bloesem",
        "rechtsvorm": "Vennootschap onder firma",
        "totaalWerkzamePersonen": 7,
        "handelsnamen": [{"naam": "Kwekerij De Bloesem", "volgorde": 0}],
        "sbiActiviteiten": [
            {
                "sbiCode": "01192",
                "sbiOmschrijving": (
                    "Teelt van bloemen, bloembollen en perkplanten (onder glas)"
                ),
                "indHoofdactiviteit": "Ja",
            },
            {
                "sbiCode": "01300",
                "sbiOmschrijving": "Teelt van sierplanten voor vermeerdering",
                "indHoofdactiviteit": "Nee",
            },
        ],
        "materieleRegistratie": {"datumAanvang": "20110212"},
        "statusinformatie": "actief",
        "_embedded": {
            "hoofdvestiging": {
                "vestigingsnummer": "000062345681",
                "eersteHandelsnaam": "Kwekerij De Bloesem",
                "indHoofdvestiging": "Ja",
                "totaalWerkzamePersonen": 7,
                "websites": ["https://www.kwekerijdebloesem.nl"],
                # De pagina Adresgegevens toont vestigings- én postadres. Voor
                # deze kweker zijn ze gelijk; dat is geen kopieerfout maar wat
                # het scherm toont.
                "adressen": [
                    {
                        "type": "correspondentieadres",
                        "volledigAdres": "Hoefweg 210, 2665KG Bleiswijk",
                        "straatnaam": "Hoefweg",
                        "huisnummer": 210,
                        "postcode": "2665KG",
                        "plaats": "Bleiswijk",
                    },
                    {
                        "type": "bezoekadres",
                        "volledigAdres": "Hoefweg 210, 2665KG Bleiswijk",
                        "straatnaam": "Hoefweg",
                        "huisnummer": 210,
                        "postcode": "2665KG",
                        "plaats": "Bleiswijk",
                    },
                ],
                "sbiActiviteiten": [
                    {
                        "sbiCode": "01192",
                        "sbiOmschrijving": (
                            "Teelt van bloemen, bloembollen en perkplanten (onder glas)"
                        ),
                        "indHoofdactiviteit": "Ja",
                    }
                ],
            }
        },
    },
    "56789012": {
        "kvkNummer": "56789012",
        "naam": "Roots & Locks",
        "rechtsvorm": "Eenmanszaak",
        "totaalWerkzamePersonen": 1,
        "handelsnamen": [{"naam": "Roots & Locks", "volgorde": 0}],
        "sbiActiviteiten": [
            {
                "sbiCode": "96021",
                "sbiOmschrijving": "Haarverzorging",
                "indHoofdactiviteit": "Ja",
            },
            {
                "sbiCode": "47750",
                "sbiOmschrijving": "Winkels in parfums en cosmetica",
                "indHoofdactiviteit": "Nee",
            },
        ],
        "materieleRegistratie": {"datumAanvang": "20210920"},
        "statusinformatie": "actief",
        "_embedded": {
            "hoofdvestiging": {
                "vestigingsnummer": "000056789012",
                "eersteHandelsnaam": "Roots & Locks",
                "indHoofdvestiging": "Ja",
                "totaalWerkzamePersonen": 1,
                "websites": ["https://www.rootsandlocks.nl"],
                "adressen": [
                    {
                        "type": "correspondentieadres",
                        "volledigAdres": "Witte de Withstraat 18, 3012BP Rotterdam",
                        "straatnaam": "Witte de Withstraat",
                        "huisnummer": 18,
                        "postcode": "3012BP",
                        "plaats": "Rotterdam",
                    },
                    {
                        "type": "bezoekadres",
                        "volledigAdres": "Witte de Withstraat 18, 3012BP Rotterdam",
                        "straatnaam": "Witte de Withstraat",
                        "huisnummer": 18,
                        "postcode": "3012BP",
                        "plaats": "Rotterdam",
                    },
                ],
                "sbiActiviteiten": [
                    {
                        "sbiCode": "96021",
                        "sbiOmschrijving": "Haarverzorging",
                        "indHoofdactiviteit": "Ja",
                    }
                ],
            }
        },
    },
    # Vogel Bouwregie B.V. — de persona die de frontend op dit moment als
    # actief serveert. Het postadres is een postbus en wijkt dus af van het
    # bezoekadres; dat is precies het geval waarin adres-op-positie kiezen de
    # BAG-verrijking op het verkeerde pand zou zetten.
    "61234570": {
        "kvkNummer": "61234570",
        "naam": "Vogel Bouwregie B.V.",
        "statutaireNaam": "Vogel Bouwregie B.V.",
        "rechtsvorm": "Besloten vennootschap",
        "totaalWerkzamePersonen": 9,
        "handelsnamen": [{"naam": "Vogel Bouwregie B.V.", "volgorde": 0}],
        "sbiActiviteiten": [
            {
                "sbiCode": "41",
                "sbiOmschrijving": (
                    "Algemene burgerlijke en utiliteitsbouw en projectontwikkeling"
                ),
                "indHoofdactiviteit": "Ja",
            },
            {
                "sbiCode": "71121",
                "sbiOmschrijving": (
                    "Ingenieurs en overig technisch ontwerp en advies"
                ),
                "indHoofdactiviteit": "Nee",
            },
        ],
        "materieleRegistratie": {"datumAanvang": "20140305"},
        "statusinformatie": "actief",
        "_embedded": {
            "hoofdvestiging": {
                "vestigingsnummer": "000061234570",
                "eersteHandelsnaam": "Vogel Bouwregie B.V.",
                "indHoofdvestiging": "Ja",
                "totaalWerkzamePersonen": 9,
                "websites": ["https://www.vogelbouwregie.nl"],
                "adressen": [
                    {
                        "type": "correspondentieadres",
                        "volledigAdres": "Postbus 8120, 3009AC Rotterdam",
                        "straatnaam": "Postbus",
                        "huisnummer": 8120,
                        "postcode": "3009AC",
                        "plaats": "Rotterdam",
                    },
                    {
                        "type": "bezoekadres",
                        "volledigAdres": "Waalhaven 120, 3089JJ Rotterdam",
                        "straatnaam": "Waalhaven",
                        "huisnummer": 120,
                        "postcode": "3089JJ",
                        "plaats": "Rotterdam",
                    },
                ],
                "sbiActiviteiten": [
                    {
                        "sbiCode": "41",
                        "sbiOmschrijving": (
                            "Algemene burgerlijke en utiliteitsbouw en "
                            "projectontwikkeling"
                        ),
                        "indHoofdactiviteit": "Ja",
                    }
                ],
            }
        },
    },
}

# Het vestigingsprofiel is een eigen endpoint (/v1/vestigingsprofielen/<nr>) en
# draagt wat het basisprofiel niet heeft: de uitsplitsing voltijd/deeltijd, het
# RSIN en de volledige adressenlijst. De frontend toont die uitsplitsing op de
# pagina Bedrijfsgegevens, dus zonder deze bron antwoordt de assistent met het
# totaal en leest de ondernemer een verschil dat er niet is.
MOCK_VESTIGINGSPROFIELEN: dict[str, dict] = {
    "000085234567": {
        "vestigingsnummer": "000085234567",
        "kvkNummer": "85234567",
        "eersteHandelsnaam": "Koffiezaak Noon",
        "indHoofdvestiging": "Ja",
        "rsin": "85234567",
        "totaalWerkzamePersonen": 4,
        "voltijdWerkzamePersonen": 1,
        "deeltijdWerkzamePersonen": 3,
        "websites": ["https://www.koffiezaaknoon.nl"],
    },
    "000062345681": {
        "vestigingsnummer": "000062345681",
        "kvkNummer": "62345681",
        "eersteHandelsnaam": "Kwekerij De Bloesem",
        "indHoofdvestiging": "Ja",
        "rsin": "62345681",
        "totaalWerkzamePersonen": 7,
        "voltijdWerkzamePersonen": 5,
        "deeltijdWerkzamePersonen": 2,
        "websites": ["https://www.kwekerijdebloesem.nl"],
    },
    "000056789012": {
        "vestigingsnummer": "000056789012",
        "kvkNummer": "56789012",
        "eersteHandelsnaam": "Roots & Locks",
        "indHoofdvestiging": "Ja",
        "rsin": "56789012",
        "totaalWerkzamePersonen": 1,
        "voltijdWerkzamePersonen": 1,
        "deeltijdWerkzamePersonen": 0,
        "websites": ["https://www.rootsandlocks.nl"],
    },
    "000061234570": {
        "vestigingsnummer": "000061234570",
        "kvkNummer": "61234570",
        "eersteHandelsnaam": "Vogel Bouwregie B.V.",
        "indHoofdvestiging": "Ja",
        "rsin": "61234570",
        "totaalWerkzamePersonen": 9,
        "voltijdWerkzamePersonen": 8,
        "deeltijdWerkzamePersonen": 1,
        "websites": ["https://www.vogelbouwregie.nl"],
    },
}

MOCK_VESTIGINGEN: dict[str, dict] = {
    "85234567": {
        "kvkNummer": "85234567",
        "aantalCommercieleVestigingen": 1,
        "vestigingen": [
            {
                "vestigingsnummer": "000085234567",
                "eersteHandelsnaam": "Koffiezaak Noon",
                "indHoofdvestiging": "Ja",
                "volledigAdres": "Meent 88, 3011JM Rotterdam",
            }
        ],
    },
    "62345681": {
        "kvkNummer": "62345681",
        "aantalCommercieleVestigingen": 1,
        "vestigingen": [
            {
                "vestigingsnummer": "000062345681",
                "eersteHandelsnaam": "Kwekerij De Bloesem",
                "indHoofdvestiging": "Ja",
                "volledigAdres": "Hoefweg 210, 2665KG Bleiswijk",
            }
        ],
    },
    "56789012": {
        "kvkNummer": "56789012",
        "aantalCommercieleVestigingen": 1,
        "vestigingen": [
            {
                "vestigingsnummer": "000056789012",
                "eersteHandelsnaam": "Roots & Locks",
                "indHoofdvestiging": "Ja",
                "volledigAdres": "Witte de Withstraat 18, 3012BP Rotterdam",
            }
        ],
    },
    "61234570": {
        "kvkNummer": "61234570",
        "aantalCommercieleVestigingen": 1,
        "vestigingen": [
            {
                "vestigingsnummer": "000061234570",
                "eersteHandelsnaam": "Vogel Bouwregie B.V.",
                "indHoofdvestiging": "Ja",
                "volledigAdres": "Waalhaven 120, 3089JJ Rotterdam",
            }
        ],
    },
}

# De echte /eigenaar-response draagt `rsin`, `rechtsvorm` en
# `uitgebreideRechtsvorm` op het hoogste niveau. De geneste `natuurlijkPersoon`
# en `rechtspersoon` zijn een toevoeging van deze mock, zodat de assistent een
# naam kan noemen waar de Test API alleen een rechtsvorm teruggeeft.
MOCK_EIGENAREN: dict[str, dict] = {
    "85234567": {
        "kvkNummer": "85234567",
        "rsin": "85234567",
        "rechtsvorm": "Eenmanszaak",
        "uitgebreideRechtsvorm": "Eenmanszaak",
        "natuurlijkPersoon": {
            "geslachtsnaam": "van Dam",
            "voornamen": "Claudia",
            "volledigeNaam": "Claudia van Dam",
        },
    },
    # VOF: geen rechtspersoonlijkheid, de vennootschap zelf is de eigenaar. De
    # vennoten staan in het UBO-register, een apart register met een eigen
    # bron; die kent deze server niet, dus de assistent noemt hier geen namen.
    "62345681": {
        "kvkNummer": "62345681",
        "rsin": "62345681",
        "rechtsvorm": "Vennootschap onder firma",
        "uitgebreideRechtsvorm": "Vennootschap onder firma",
        "rechtspersoon": {
            "rsin": "62345681",
            "statutaireNaam": "Kwekerij De Bloesem",
        },
    },
    "56789012": {
        "kvkNummer": "56789012",
        "rsin": "56789012",
        "rechtsvorm": "Eenmanszaak",
        "uitgebreideRechtsvorm": "Eenmanszaak",
        "natuurlijkPersoon": {
            "geslachtsnaam": "Vogel",
            "voornamen": "Robin",
            "volledigeNaam": "Robin Vogel",
        },
    },
    "61234570": {
        "kvkNummer": "61234570",
        "rsin": "61234570",
        "rechtsvorm": "Besloten vennootschap",
        "uitgebreideRechtsvorm": "Besloten vennootschap",
        "rechtspersoon": {
            "rsin": "61234570",
            "statutaireNaam": "Vogel Bouwregie B.V.",
        },
    },
}


# Het KvK-nummer zit in het API-pad (/v1/basisprofielen/<kvk>/...). Dat nummer
# is de identiteit van de sessie en hoort niet in de logs — consistent met
# _audit_log hieronder en met de host, die alleen argument-namen logt (PDR-009).
_KVK_IN_PAD = re.compile(r"/\d{8}(?=/|$)")


def _pad_zonder_kvk(path: str) -> str:
    """Geef het API-pad terug met het KvK-nummer vervangen, voor logging.

    Welk endpoint is aangeroepen blijft zichtbaar (nuttig bij debuggen); welk
    bedrijf het betrof niet.
    """
    return _KVK_IN_PAD.sub("/<kvk>", path)


def _kvk_fetch(path: str) -> dict:
    """Haal data op van de KvK Test API."""
    url = f"{KVK_TEST_BASE}{path}"
    req = Request(url, headers={"apikey": KVK_TEST_API_KEY})
    logger.info("KVK API call: %s%s", KVK_TEST_BASE, _pad_zonder_kvk(path))
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


async def _get_basisprofiel(kvk: str) -> dict:
    """Haal het basisprofiel op (met cache per KvK). Mock-persona's komen lokaal."""
    if kvk in _profiel_cache:
        return _profiel_cache[kvk]
    if kvk in MOCK_PROFIELEN:
        _profiel_cache[kvk] = MOCK_PROFIELEN[kvk]
        return _profiel_cache[kvk]
    loop = asyncio.get_event_loop()
    profiel = await loop.run_in_executor(
        None, _kvk_fetch, f"/v1/basisprofielen/{kvk}"
    )
    _profiel_cache[kvk] = profiel
    return profiel


async def _get_vestigingsprofiel(vestigingsnummer: str) -> dict:
    """Haal het vestigingsprofiel op (voltijd/deeltijd, RSIN, websites)."""
    if vestigingsnummer in MOCK_VESTIGINGSPROFIELEN:
        return MOCK_VESTIGINGSPROFIELEN[vestigingsnummer]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _kvk_fetch, f"/v1/vestigingsprofielen/{vestigingsnummer}"
    )


# Wat het basisprofiel niet draagt maar het vestigingsprofiel wel. Alleen deze
# velden overnemen: de rest zou het basisprofiel stilzwijgend van vorm laten
# veranderen, en dan weet de assistent niet meer welke bron hij citeert.
_VESTIGINGSPROFIEL_VELDEN = (
    "voltijdWerkzamePersonen",
    "deeltijdWerkzamePersonen",
    "websites",
)


async def _enrich_with_vestigingsprofiel(profiel: dict) -> dict:
    """Vul de hoofdvestiging aan met de personeelsuitsplitsing en de websites.

    De frontend toont voltijd en deeltijd apart; het basisprofiel kent alleen
    het totaal. Zonder deze aanvulling noemt de assistent een ander getal dan
    het scherm. Een falend vestigingsprofiel mag het basisprofiel niet meeslepen
    — de gebruiker heeft meer aan een profiel zonder uitsplitsing dan aan een
    foutmelding — dus dat blijft bij een logregel.
    """
    hoofdvestiging = profiel.get("_embedded", {}).get("hoofdvestiging", {})
    vestigingsnummer = hoofdvestiging.get("vestigingsnummer")
    if not vestigingsnummer:
        return profiel

    try:
        vestigingsprofiel = await _get_vestigingsprofiel(vestigingsnummer)
    except (HTTPError, URLError) as exc:
        logger.warning("vestigingsprofiel niet opgehaald: %s", type(exc).__name__)
        return profiel

    aanvulling = {
        veld: vestigingsprofiel[veld]
        for veld in _VESTIGINGSPROFIEL_VELDEN
        if veld in vestigingsprofiel
    }
    if not aanvulling:
        return profiel

    # Niet de cache muteren: _profiel_cache deelt dit dict tussen aanroepen.
    profiel = dict(profiel)
    profiel["_embedded"] = dict(profiel["_embedded"])
    profiel["_embedded"]["hoofdvestiging"] = {**hoofdvestiging, **aanvulling}
    return profiel


async def _get_vestigingen(kvk: str) -> dict:
    """Haal de vestigingen-lijst op voor het meegegeven bedrijf."""
    if kvk in MOCK_VESTIGINGEN:
        return MOCK_VESTIGINGEN[kvk]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _kvk_fetch, f"/v1/basisprofielen/{kvk}/vestigingen"
    )


async def _get_eigenaar(kvk: str) -> dict:
    """Haal de eigenaar-informatie op voor het meegegeven bedrijf."""
    if kvk in MOCK_EIGENAREN:
        return MOCK_EIGENAREN[kvk]
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _kvk_fetch, f"/v1/basisprofielen/{kvk}/eigenaar"
    )


# ---------------------------------------------------------------------------
# BAG-verrijking via de Kadaster BAG API Individuele Bevragingen.
# Sinds 1-3-2023 vereist deze API een eigen API-key (gratis aan te vragen bij
# Kadaster). Zet die in BAG_API_KEY (.env). Zonder key valt de verrijking terug
# op demo-data (_BAG_DEMO_FALLBACK) voor de bekende demo-adressen.
# ---------------------------------------------------------------------------

BAG_API_BASE = "https://api.bag.kadaster.nl/lvbag/individuelebevragingen/v2"
BAG_API_KEY = os.getenv("BAG_API_KEY", "").strip()

# Fallback BAG-data voor bekende demo-adressen (als PDOK niet bereikbaar is
# of het adres niet bestaat in de BAG, bv. bij KvK test-adressen)
_BAG_DEMO_FALLBACK = {
    "8823SJ-3": {
        "gebruiksdoelen": ["industriefunctie"],
        "oppervlakte": 250,
        "oorspronkelijkBouwjaar": "1985",
        "nummeraanduidingIdentificatie": "0081200000012345",
    },
    # Koffiezaak Noon (mock-persona Claudia van Dam) — horecapand, geen
    # woonfunctie, dus de woonfunctie-uitzondering geldt niet.
    "3011JM-88": {
        "gebruiksdoelen": ["bijeenkomstfunctie"],
        "oppervlakte": 140,
        "oorspronkelijkBouwjaar": "1923",
        "nummeraanduidingIdentificatie": "0599200000312345",
    },
    # Kwekerij De Bloesem (mock-persona bloemenkweker) — kassencomplex,
    # industriefunctie, dus geen woonfunctie-uitzondering.
    "2665KG-210": {
        "gebruiksdoelen": ["industriefunctie"],
        "oppervlakte": 18500,
        "oorspronkelijkBouwjaar": "2004",
        "nummeraanduidingIdentificatie": "1621200000045678",
    },
    # Roots & Locks (mock-persona haarstylist) — kapsalon op de begane grond,
    # winkelfunctie. Verbruik ligt onder de drempels, dus geen informatieplicht.
    "3012BP-18": {
        "gebruiksdoelen": ["winkelfunctie"],
        "oppervlakte": 65,
        "oorspronkelijkBouwjaar": "1931",
        "nummeraanduidingIdentificatie": "0599200000398765",
    },
    # Vogel Bouwregie B.V. (mock-persona bouwmanagement) — bedrijfsloods met
    # kantoor in de haven. Op het postbusadres staat bewust geen entry: komt
    # die sleutel toch langs, dan koos de adres-extractie het verkeerde adres.
    "3089JJ-120": {
        "gebruiksdoelen": ["kantoorfunctie", "industriefunctie"],
        "oppervlakte": 1240,
        "oorspronkelijkBouwjaar": "1998",
        "nummeraanduidingIdentificatie": "0599200000427531",
    },
}


def _extract_address(profiel: dict) -> dict | None:
    """Extraheer het hoofdvestigingsadres uit een KvK-basisprofiel."""
    embedded = profiel.get("_embedded", {})
    hoofdvestiging = embedded.get("hoofdvestiging", {})
    adressen = hoofdvestiging.get("adressen", [])
    if not adressen:
        return None
    for adres in adressen:
        if adres.get("type") == "bezoekadres":
            return adres
    return adressen[0]


def _bag_fetch(postcode: str, huisnummer: int, huisletter: str = "") -> dict | None:
    """Haal BAG-gegevens op via de Kadaster BAG API (vereist BAG_API_KEY).

    Zonder API-key of bij een storing valt de verrijking terug op demo-data
    voor de bekende demo-adressen (_BAG_DEMO_FALLBACK).
    """
    fallback_key = f"{postcode.replace(' ', '')}-{huisnummer}"

    if not BAG_API_KEY:
        logger.info("Geen BAG_API_KEY gezet, BAG-verrijking via demo-data")
        return _BAG_DEMO_FALLBACK.get(fallback_key)

    params = {"postcode": postcode, "huisnummer": huisnummer}
    if huisletter:
        params["huisletter"] = huisletter
    url = f"{BAG_API_BASE}/adressenuitgebreid?{urlencode(params)}"

    logger.info("BAG API call: %s", url)
    try:
        # De API-key gaat als header mee (X-Api-Key), niet in de URL of de logs.
        req = Request(
            url,
            headers={
                "Accept": "application/hal+json",
                "X-Api-Key": BAG_API_KEY,
            },
        )
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        adressen = data.get("_embedded", {}).get("adressen", [])
        if adressen:
            adres = adressen[0]
            return {
                "gebruiksdoelen": adres.get("gebruiksdoelen", []),
                "oppervlakte": adres.get("oppervlakte"),
                "oorspronkelijkBouwjaar": adres.get("oorspronkelijkBouwjaar"),
                "nummeraanduidingIdentificatie": adres.get(
                    "nummeraanduidingIdentificatie"
                ),
            }
    except Exception as e:
        logger.warning("BAG API niet bereikbaar: %s, fallback naar demo-data", e)

    return _BAG_DEMO_FALLBACK.get(fallback_key)


async def _enrich_with_bag(profiel: dict) -> dict:
    """Verrijk een KvK-profiel met BAG-gegevens (gebruiksdoel/woonfunctie)."""
    adres = _extract_address(profiel)
    if not adres:
        return profiel

    postcode = (adres.get("postcode") or "").replace(" ", "")
    huisnummer = adres.get("huisnummer")
    huisletter = adres.get("huisletter") or ""

    if not postcode or not huisnummer:
        return profiel

    loop = asyncio.get_event_loop()
    bag_data = await loop.run_in_executor(
        None, _bag_fetch, postcode, int(huisnummer), huisletter
    )

    if bag_data:
        profiel = dict(profiel)  # niet de cache muteren
        profiel["bag"] = bag_data
        gebruiksdoelen = bag_data.get("gebruiksdoelen", [])
        profiel["is_woonfunctie"] = (
            len(gebruiksdoelen) == 1 and gebruiksdoelen[0] == "woonfunctie"
        )
        logger.info(
            "BAG verrijking: gebruiksdoelen=%s, is_woonfunctie=%s",
            gebruiksdoelen,
            profiel["is_woonfunctie"],
        )

    return profiel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_provenance(data: dict) -> str:
    """Wrap data met verplichte provenance metadata (standaard §4.1, §7)."""
    return json.dumps(
        {
            "data": data,
            "provenance": {
                "source": SOURCE_LABEL,
                "timestamp": datetime.now(UTC).isoformat(),
                "version": SERVER_VERSION,
            },
        },
        ensure_ascii=False,
    )


def _audit_log(tool_name: str, input_data: dict, output_data: dict) -> None:
    """Log een tool-aanroep conform standaard §2.2 (Audit by default)."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": tool_name,
        # Alleen veldnamen, geen waarden: het KvK-nummer (identiteit) hoort
        # niet in de logs — consistent met de CLI-audit (audit.sh) (PDR-009).
        "input_keys": sorted(str(k) for k in input_data),
        "output": {
            "type": type(output_data).__name__,
            "keys": list(output_data.keys()),
        },
    }
    logger.info("AUDIT: %s", json.dumps(entry, ensure_ascii=False, default=str))


# ---------------------------------------------------------------------------
# Resources — read-only bedrijfsgegevens (standaard §4.1)
# ---------------------------------------------------------------------------


@server.list_resources()
async def list_resources() -> list[Resource]:
    return []


@server.list_resource_templates()
async def list_resource_templates() -> list[ResourceTemplate]:
    """Publiceer resource templates voor dynamisch opvragen."""
    return [
        ResourceTemplate(
            uriTemplate="kvk://basisprofiel/{kvk_nummer}",
            name="Basisprofiel",
            description=(
                "Haal het basisprofiel op van het bedrijf van de ingelogde "
                "gebruiker. Bevat naam, rechtsvorm, SBI-activiteiten, "
                "hoofdvestiging en adresgegevens. Alleen het eigen bedrijf "
                "is beschikbaar (sessie-gebonden)."
            ),
            mimeType="application/json",
        ),
    ]


@server.read_resource()
async def read_resource(uri: str) -> list[ReadResourceContents]:
    """Retourneer het bedrijfsprofiel voor het KvK-nummer in de resource-URI.

    De host is de identiteits-autoriteit (PDR-009): hij stelt de URI samen met
    het KvK-nummer van de ingelogde sessie. De server bedient dat nummer.

    LET OP: deze resource-read is NIET sessie-gebonden — hij vertrouwt het
    KvK-nummer uit de URI. De host ontsluit op dit moment geen MCP-resource-reads
    aan het LLM, dus dit is geen live bypass. Wordt dat ooit wel gedaan, dan moet
    het KvK-nummer hier eerst tegen de sessie gevalideerd/geinjecteerd worden,
    anders is `kvk://basisprofiel/<willekeurig>` een cross-tenant read.
    """
    kvk_nummer = str(uri).rstrip("/").split("/")[-1]

    if not kvk_nummer:
        return [
            ReadResourceContents(
                content=json.dumps(
                    {"error": "GEEN_SESSIE", "message": "Geen KvK-nummer in URI."},
                    ensure_ascii=False,
                ),
                mime_type="application/json",
            )
        ]

    try:
        profiel = await _get_basisprofiel(kvk_nummer)
    except (HTTPError, URLError) as exc:
        logger.error("KVK API fout: %s", exc)
        return [
            ReadResourceContents(
                content=json.dumps(
                    {"error": "API_FOUT", "message": str(exc)}, ensure_ascii=False
                ),
                mime_type="application/json",
            )
        ]

    return [
        ReadResourceContents(
            content=_wrap_provenance(profiel),
            mime_type="application/json",
        )
    ]


# ---------------------------------------------------------------------------
# Tools (standaard §4.2)
# ---------------------------------------------------------------------------


# kvk_nummer wordt server-side door de host geïnjecteerd (PDR-009) en is uit de
# LLM-zichtbare schema's gestript (mcp_client._strip_kvk_param). Het staat hier
# als property zodat de geïnjecteerde waarde niet op additionalProperties botst.
_SESSION_BOUND_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "kvk_nummer": {
            "type": "string",
            "description": "Server-side gezet door de host; niet door het LLM.",
        }
    },
    "additionalProperties": False,
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Publiceer beschikbare tools met beschrijving, schema en annotaties."""
    return [
        Tool(
            name="mijn_bedrijf",
            description=(
                "Haal de bedrijfsgegevens op van de ingelogde gebruiker. "
                "Retourneert het KvK-basisprofiel met naam, KvK-nummer, "
                "rechtsvorm, SBI-activiteiten, vestigingsadres en aantal "
                "werkzame personen. Het profiel wordt automatisch verrijkt "
                "met BAG-gegevens (gebruiksdoel pand en is_woonfunctie) "
                "via het Kadaster. Geen parameters nodig — de gegevens "
                "zijn gekoppeld aan de huidige sessie."
            ),
            inputSchema=_SESSION_BOUND_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="vestigingen",
            description=(
                "Haal de lijst met vestigingen op van de ingelogde gebruiker. "
                "Retourneert nevenvestigingen, hoofdvestiging, en per vestiging "
                "het adres en de SBI-activiteiten. Geen parameters nodig — "
                "sessie-gebonden."
            ),
            inputSchema=_SESSION_BOUND_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="eigenaar",
            description=(
                "Haal de eigenaar-informatie op van de ingelogde gebruiker. "
                "Retourneert rechtspersoon-gegevens of natuurlijk-persoon-gegevens "
                "afhankelijk van de rechtsvorm. Geen parameters nodig — "
                "sessie-gebonden."
            ),
            inputSchema=_SESSION_BOUND_INPUT_SCHEMA,
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=False,
            ),
        ),
    ]


def _api_error(exc: Exception) -> list[TextContent]:
    """Format a KvK API-fout als TextContent (gedeeld door alle tools)."""
    logger.error("KVK API fout: %s", exc)
    return [
        TextContent(
            type="text",
            text=json.dumps(
                {"error": "API_FOUT", "message": str(exc)}, ensure_ascii=False
            ),
        )
    ]


def _geen_sessie_fout(name: str) -> list[TextContent]:
    """Nette fout als er geen KvK-nummer (sessie) is meegegeven (PDR-009)."""
    logger.warning("SECURITY: %s aangeroepen zonder sessie-KvK-nummer", name)
    return [
        TextContent(
            type="text",
            text=json.dumps(
                {
                    "error": "GEEN_SESSIE",
                    "message": (
                        "Geen ingelogde gebruiker: er is geen KvK-nummer bekend "
                        "voor deze sessie."
                    ),
                },
                ensure_ascii=False,
            ),
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Voer een tool uit en log de aanroep (standaard §2.2).

    Het KvK-nummer wordt server-side door de host meegegeven (PDR-009); de tool
    bedient dat bedrijf. Zonder KvK-nummer volgt een nette fout.
    """
    kvk = _resolve_kvk(arguments)
    if not kvk:
        return _geen_sessie_fout(name)

    if name == "mijn_bedrijf":
        try:
            profiel = await _get_basisprofiel(kvk)
        except (HTTPError, URLError) as exc:
            return _api_error(exc)
        # Vul aan met de personeelsuitsplitsing uit het vestigingsprofiel en
        # verrijk met BAG-gegevens (gebruiksdoel pand / woonfunctie)
        profiel = await _enrich_with_vestigingsprofiel(profiel)
        profiel = await _enrich_with_bag(profiel)
        _audit_log("mijn_bedrijf", {"kvk_nummer": kvk}, profiel)
        return [TextContent(type="text", text=_wrap_provenance(profiel))]

    if name == "vestigingen":
        try:
            data = await _get_vestigingen(kvk)
        except (HTTPError, URLError) as exc:
            return _api_error(exc)
        _audit_log("vestigingen", {"kvk_nummer": kvk}, data)
        return [TextContent(type="text", text=_wrap_provenance(data))]

    if name == "eigenaar":
        try:
            data = await _get_eigenaar(kvk)
        except (HTTPError, URLError) as exc:
            return _api_error(exc)
        _audit_log("eigenaar", {"kvk_nummer": kvk}, data)
        return [TextContent(type="text", text=_wrap_provenance(data))]

    raise ValueError(f"Onbekende tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())

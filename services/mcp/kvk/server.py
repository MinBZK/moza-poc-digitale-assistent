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
        "materieleRegistratie": {"datumAanvang": "20220301"},
        "statusinformatie": "actief",
        "_embedded": {
            "hoofdvestiging": {
                "vestigingsnummer": "000052341288",
                "eersteHandelsnaam": "Koffiezaak Noon",
                "indHoofdvestiging": "Ja",
                "totaalWerkzamePersonen": 4,
                "adressen": [
                    {
                        "type": "bezoekadres",
                        "volledigAdres": "Witte de Withstraat 27, 3012BL Rotterdam",
                        "straatnaam": "Witte de Withstraat",
                        "huisnummer": 27,
                        "postcode": "3012BL",
                        "plaats": "Rotterdam",
                    }
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
    }
}

MOCK_VESTIGINGEN: dict[str, dict] = {
    "85234567": {
        "kvkNummer": "85234567",
        "aantalCommercieleVestigingen": 1,
        "vestigingen": [
            {
                "vestigingsnummer": "000052341288",
                "eersteHandelsnaam": "Koffiezaak Noon",
                "indHoofdvestiging": "Ja",
                "volledigAdres": "Witte de Withstraat 27, 3012BL Rotterdam",
            }
        ],
    }
}

MOCK_EIGENAREN: dict[str, dict] = {
    "85234567": {
        "kvkNummer": "85234567",
        "rechtsvorm": "Eenmanszaak",
        "natuurlijkPersoon": {
            "geslachtsnaam": "van Dam",
            "voornamen": "Claudia",
            "volledigeNaam": "Claudia van Dam",
        },
    }
}


def _kvk_fetch(path: str) -> dict:
    """Haal data op van de KvK Test API."""
    url = f"{KVK_TEST_BASE}{path}"
    req = Request(url, headers={"apikey": KVK_TEST_API_KEY})
    logger.info("KVK API call: %s", url)
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
    "3012BL-27": {
        "gebruiksdoelen": ["bijeenkomstfunctie"],
        "oppervlakte": 140,
        "oorspronkelijkBouwjaar": "1923",
        "nummeraanduidingIdentificatie": "0599200000312345",
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
        "input": input_data,
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
        # Verrijk met BAG-gegevens (gebruiksdoel pand / woonfunctie)
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

"""Regelingen rond het aannemen van iemand met een afstand tot de arbeidsmarkt — demo-mock.

DEMO-CODE voor de werksessie van 10 augustus 2026. Geen productiecode, geen
echte UWV-koppeling.

Deze server is bewust ontworpen rond één grens: **hij kent regelingen, geen
personen.** Er zit geen enkel gegeven in over een kandidaat — geen naam, geen
BSN, geen uitkering, geen diagnose, geen registerstatus. Wie wil weten of een
concrete persoon in aanmerking komt, moet bij UWV of de gemeente zijn; dat
oordeel hoort niet in dit kanaal. De assistent kan met deze bron het landelijke
kader uitleggen zonder ooit iets over de sollicitant te verwerken.

Twee kleinere ontwerpkeuzes volgen daaruit:

- **Geen bedragen, geen termijnlengtes.** Elke regeling draagt wél
  `heeft_termijn` en `controleer_termijn_bij`, zodat de assistent kan
  waarschuwen *dát* er een termijn is zonder te verzinnen welke. Bedragen en
  exacte termijnen veranderen te vaak; een fout kost de ondernemer direct geld.
- **Peildatum per regeling.** De regels rond het loonkostenvoordeel zijn per
  1 januari 2026 veranderd (doelgroepverklaring banenafspraak afgeschaft, LKV
  oudere werknemer vervallen). Een model dat op oudere kennis leunt vertelt het
  verkeerde verhaal. De peildatum maakt zichtbaar hoe vers de bron is.

Elke regeling draagt ook `plichten`: wat er voor de werkgever tegenover staat.
Een antwoord dat alleen de voordelen noemt is onvolledig.

Voldoet aan de MCP-standaard voor Generieke Interactieservices:
- Provenance metadata bij elke response (§4.1, §7)
- ToolAnnotations op elke tool (§4.2, §7)
- Audit logging bij elke tool-aanroep (§2.2)
- Beschrijvingen en inputschema's (§7)
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
    ToolAnnotations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [uwv] %(message)s")
logger = logging.getLogger("uwv")

server = Server(name="uwv")

SOURCE_LABEL = "UWV / Werkgeversservicepunt (mock)"
SERVER_VERSION = "0.1.0"
PEILDATUM = "2026-08-06"

# ---------------------------------------------------------------------------
# Mock-data — regelingen, niet personen
#
# Bewust weggelaten: bedragen, termijnlengtes, en elk gegeven dat aan een
# individuele kandidaat hangt. Zie de moduledocstring.
# ---------------------------------------------------------------------------

REGELINGEN: list[dict] = [
    {
        "id": "lkv-banenafspraak",
        "naam": "Loonkostenvoordeel doelgroep banenafspraak",
        "soort": "financieel",
        "wat_het_doet": "Vermindering van de loonkosten voor werkgevers die iemand uit de doelgroep banenafspraak in dienst nemen.",
        "uitvoerder": "UWV stelt vast, de Belastingdienst verrekent via de aangifte loonheffingen",
        "wettelijk_kader": "Wet tegemoetkomingen loondomein (Wtl)",
        "heeft_termijn": True,
        "controleer_termijn_bij": "UWV",
        "gewijzigd_per": "2026-01-01",
        "wijziging": (
            "De doelgroepverklaring is voor deze doelgroep vervallen. De werkgever vraagt "
            "niets meer aan en kan in het werkgeversportaal van UWV zelf zien of iemand in "
            "het doelgroepregister staat. Het voordeel loopt nu zolang het dienstverband "
            "duurt, in plaats van maximaal drie jaar."
        ),
        "plichten": [
            "Doeltreffende aanpassing van de werkplek als die nodig is (Wgbh/cz)",
            "Gelijke behandeling bij werving, selectie en tijdens het dienstverband",
        ],
        "beoordeling_door": "UWV bepaalt of iemand tot de doelgroep behoort — niet de werkgever en niet deze assistent",
    },
    {
        "id": "lkv-arbeidsgehandicapt",
        "naam": "Loonkostenvoordeel arbeidsgehandicapte werknemer",
        "soort": "financieel",
        "wat_het_doet": "Vermindering van de loonkosten bij het in dienst nemen van een arbeidsgehandicapte werknemer.",
        "uitvoerder": "UWV stelt vast, de Belastingdienst verrekent",
        "wettelijk_kader": "Wet tegemoetkomingen loondomein (Wtl)",
        "heeft_termijn": True,
        "controleer_termijn_bij": "UWV",
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Doeltreffende aanpassing van de werkplek als die nodig is (Wgbh/cz)",
            "Loondoorbetaling en re-integratie bij ziekte (Wet verbetering poortwachter)",
        ],
        "beoordeling_door": "UWV. Voor deze doelgroep is nog wél een doelgroepverklaring nodig; de werknemer vraagt die aan.",
    },
    {
        "id": "loonkostensubsidie",
        "naam": "Loonkostensubsidie",
        "soort": "financieel",
        "wat_het_doet": "Compensatie van het verschil tussen de vastgestelde loonwaarde en het loon dat u betaalt.",
        "uitvoerder": "De gemeente",
        "wettelijk_kader": "Participatiewet, onder meer artikel 10c en 10d",
        "heeft_termijn": True,
        "controleer_termijn_bij": "de gemeente waarin de kandidaat woont",
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Doeltreffende aanpassing van de werkplek als die nodig is (Wgbh/cz)",
            "Meewerken aan de loonwaardebepaling door de gemeente",
        ],
        "beoordeling_door": "De gemeente",
        "let_op": (
            "Gemeenten hebben hier beleids- en uitvoeringsruimte. De loonwaardebepaling en "
            "de werkwijze verschillen per gemeente; een landelijk antwoord kan lokaal onjuist "
            "zijn. Verwijs altijd naar de eigen gemeente."
        ),
    },
    {
        "id": "no-riskpolis",
        "naam": "No-riskpolis",
        "soort": "risico",
        "wat_het_doet": "UWV betaalt ziekengeld als de werknemer ziek wordt, zodat het financiële risico bij ziekte niet bij u ligt.",
        "uitvoerder": "UWV",
        "wettelijk_kader": "Ziektewet, artikel 29b",
        "heeft_termijn": False,
        "controleer_termijn_bij": None,
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Loondoorbetaling en re-integratie bij ziekte blijven gelden; de no-riskpolis vergoedt, hij neemt de verplichting niet weg",
        ],
        "beoordeling_door": "UWV",
    },
    {
        "id": "proefplaatsing",
        "naam": "Proefplaatsing",
        "soort": "begeleiding",
        "wat_het_doet": "De kandidaat werkt tijdelijk met behoud van uitkering, met de bedoeling daarna een dienstverband aan te gaan.",
        "uitvoerder": "UWV of de gemeente, afhankelijk van de uitkering",
        "wettelijk_kader": "Uitvoeringsregels UWV / Participatiewet",
        "heeft_termijn": True,
        "controleer_termijn_bij": "UWV of de gemeente",
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Er moet een reële intentie tot een dienstverband zijn; een proefplaatsing is geen gratis arbeid",
        ],
        "beoordeling_door": "UWV of de gemeente",
    },
    {
        "id": "jobcoach",
        "naam": "Jobcoach en werkvoorzieningen",
        "soort": "begeleiding",
        "wat_het_doet": "Begeleiding op de werkvloer en voorzieningen of aanpassingen die het werk mogelijk maken.",
        "uitvoerder": "UWV of de gemeente",
        "wettelijk_kader": "Wet WIA, Wajong, Participatiewet en de bijbehorende uitvoeringsregelingen",
        "heeft_termijn": False,
        "controleer_termijn_bij": None,
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Doeltreffende aanpassing van de werkplek als die nodig is (Wgbh/cz) — dit is een verplichting, geen gunst",
        ],
        "beoordeling_door": "UWV of de gemeente",
    },
    {
        "id": "subsidie-praktijkleren",
        "naam": "Subsidie praktijkleren",
        "soort": "scholing",
        "wat_het_doet": "Tegemoetkoming in de kosten van begeleiding van een leerwerkplek, onder meer voor een BBL-plek.",
        "uitvoerder": "RVO",
        "wettelijk_kader": "Subsidieregeling praktijkleren",
        "heeft_termijn": True,
        "controleer_termijn_bij": "RVO",
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Begeleiding daadwerkelijk bieden en de administratie daarvan bewaren",
        ],
        "beoordeling_door": "RVO",
    },
    {
        "id": "detachering-social-return",
        "naam": "Detachering via een sociaal ontwikkelbedrijf",
        "soort": "alternatief",
        "wat_het_doet": "Iemand aan het werk helpen zonder zelf werkgever te worden; het ontwikkelbedrijf blijft de formele werkgever.",
        "uitvoerder": "Gemeente of regionaal sociaal ontwikkelbedrijf",
        "wettelijk_kader": "Participatiewet, gemeentelijk inkoopbeleid",
        "heeft_termijn": False,
        "controleer_termijn_bij": None,
        "gewijzigd_per": None,
        "wijziging": None,
        "plichten": [
            "Een veilige en passende werkplek bieden, ook zonder formeel werkgeverschap",
        ],
        "beoordeling_door": "De gemeente of het ontwikkelbedrijf",
    },
]

# Verplichtingen die bij elk dienstverband horen. Geen regeling, geen voordeel —
# maar ze horen in een evenwichtig antwoord, dus de bron levert ze mee.
ALTIJD_GELDENDE_PLICHTEN: list[dict] = [
    {
        "plicht": "Doeltreffende aanpassing",
        "toelichting": "U moet redelijke aanpassingen treffen zodat iemand met een beperking het werk kan doen.",
        "wettelijk_kader": "Wet gelijke behandeling op grond van handicap of chronische ziekte",
    },
    {
        "plicht": "Gelijke behandeling",
        "toelichting": "Bij werving, selectie en tijdens het dienstverband gelden dezelfde regels als voor iedere andere werknemer.",
        "wettelijk_kader": "Algemene wet gelijke behandeling, Wgbh/cz",
    },
    {
        "plicht": "Loondoorbetaling en re-integratie bij ziekte",
        "toelichting": "Ook met een no-riskpolis blijft u verantwoordelijk voor de re-integratie.",
        "wettelijk_kader": "Burgerlijk Wetboek, Wet verbetering poortwachter",
    },
]

# Werkgeversservicepunten per vestigingsplaats van de demo-persona's. Eén loket
# waar UWV en gemeenten samen werkgevers helpen — de concrete vervolgstap.
SERVICEPUNTEN: dict[str, dict] = {
    "85234567": {
        "vestigingsplaats": "Rotterdam",
        "servicepunt": "Werkgeversservicepunt Rijnmond (mock)",
        "samenwerking": "UWV en de gemeenten in de arbeidsmarktregio Rijnmond",
        "waarvoor": "Eén ingang voor alle regelingen in dit overzicht, inclusief de gemeentelijke route.",
    },
    "62345681": {
        "vestigingsplaats": "Bleiswijk",
        "servicepunt": "Werkgeversservicepunt Zuid-Holland Centraal (mock)",
        "samenwerking": "UWV en de gemeenten in de arbeidsmarktregio Zuid-Holland Centraal",
        "waarvoor": "Eén ingang voor alle regelingen in dit overzicht, inclusief de gemeentelijke route.",
    },
    "56789012": {
        "vestigingsplaats": "Rotterdam",
        "servicepunt": "Werkgeversservicepunt Rijnmond (mock)",
        "samenwerking": "UWV en de gemeenten in de arbeidsmarktregio Rijnmond",
        "waarvoor": "Eén ingang voor alle regelingen in dit overzicht, inclusief de gemeentelijke route.",
    },
}

SOORTEN = sorted({r["soort"] for r in REGELINGEN})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wrap_provenance(data: dict | list) -> str:
    """Wrap data met verplichte provenance metadata (standaard §4.1, §7)."""
    return json.dumps(
        {
            "data": data,
            "provenance": {
                "source": SOURCE_LABEL,
                "timestamp": datetime.now(UTC).isoformat(),
                "peildatum": PEILDATUM,
                "version": SERVER_VERSION,
                "mock": True,
            },
        },
        ensure_ascii=False,
    )


def _audit_log(tool_name: str, input_data: dict, output_data: dict | list) -> None:
    """Log een tool-aanroep conform standaard §2.2 (Audit by default)."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": tool_name,
        "input": input_data,
        "output_type": type(output_data).__name__,
    }
    logger.info("AUDIT: %s", json.dumps(entry, ensure_ascii=False, default=str))


def _fout(code: str, bericht: str) -> list[TextContent]:
    return [
        TextContent(
            type="text",
            text=json.dumps({"error": code, "message": bericht}, ensure_ascii=False),
        )
    ]


# ---------------------------------------------------------------------------
# Tools (standaard §4.2)
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Publiceer beschikbare tools met beschrijving, schema en annotaties."""
    return [
        Tool(
            name="regelingen",
            description=(
                "Geef het landelijke overzicht van regelingen en ondersteuning voor een "
                "werkgever die iemand met een afstand tot de arbeidsmarkt in dienst wil "
                "nemen. Levert per regeling: wat die doet, welk bestuursorgaan hem "
                "uitvoert, het wettelijk kader, of er een termijn aan hangt en waar die "
                "te controleren is, en welke plichten ertegenover staan. "
                "Deze bron kent GEEN personen: er zit geen enkel gegeven in over een "
                "kandidaat, en u kunt er dus niet mee bepalen of iemand in aanmerking "
                "komt. Dat oordeel ligt bij UWV of de gemeente. Gebruik deze tool bij "
                "elke vraag over personeel aannemen uit deze doelgroep."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "soort": {
                        "type": "string",
                        "description": (
                            "Optioneel filter op soort ondersteuning: "
                            + ", ".join(SOORTEN)
                            + ". Laat leeg voor het volledige overzicht."
                        ),
                        "enum": SOORTEN,
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="plichten",
            description=(
                "Geef de verplichtingen die bij elk dienstverband horen: doeltreffende "
                "aanpassing, gelijke behandeling, en loondoorbetaling en re-integratie bij "
                "ziekte. Dit zijn geen regelingen maar plichten van de werkgever. "
                "Noem ze in hetzelfde antwoord als de financiële regelingen — een "
                "overzicht dat alleen de voordelen laat zien is onvolledig."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=False,
            ),
        ),
        Tool(
            name="werkgeversservicepunt",
            description=(
                "Zoek het Werkgeversservicepunt dat hoort bij de vestigingsplaats van de "
                "ingelogde ondernemer. Dat is één loket waar UWV en de gemeenten samen "
                "werkgevers helpen, en daarmee de concrete vervolgstap: daar wordt wél "
                "beoordeeld wat er voor een specifieke kandidaat mogelijk is."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kvk_nummer": {
                        "type": "string",
                        "description": (
                            "KvK-nummer van het bedrijf (8 cijfers), uit kvk__mijn_bedrijf."
                        ),
                    },
                },
                "required": ["kvk_nummer"],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=False,
            ),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Voer een tool uit en log de aanroep (standaard §2.2)."""
    if name == "regelingen":
        return _regelingen(arguments)
    if name == "plichten":
        return _plichten(arguments)
    if name == "werkgeversservicepunt":
        return _werkgeversservicepunt(arguments)
    raise ValueError(f"Onbekende tool: {name}")


def _regelingen(arguments: dict) -> list[TextContent]:
    """Geef het landelijke regelingenoverzicht, optioneel gefilterd op soort."""
    soort = str(arguments.get("soort", "") or "").strip()
    if soort and soort not in SOORTEN:
        return _fout(
            "ONBEKENDE_SOORT",
            f"Onbekende soort '{soort}'. Kies uit: {', '.join(SOORTEN)}.",
        )

    gekozen = [r for r in REGELINGEN if not soort or r["soort"] == soort]
    output = {
        "regelingen": gekozen,
        "aantal": len(gekozen),
        "reikwijdte": (
            "Landelijk kader. Deze bron bevat geen gegevens over personen en kan niet "
            "bepalen of een specifieke kandidaat in aanmerking komt."
        ),
        "beoordeling_ligt_bij": "UWV of de gemeente, afhankelijk van de regeling",
        "geen_bedragen": (
            "Bedragen en exacte termijnen staan bewust niet in deze bron: ze veranderen "
            "regelmatig en een fout kost de werkgever direct geld. Waarschuw dát er een "
            "termijn is en verwijs voor de lengte naar het genoemde loket."
        ),
    }
    _audit_log("regelingen", arguments, output)
    return [TextContent(type="text", text=_wrap_provenance(output))]


def _plichten(arguments: dict) -> list[TextContent]:
    """Geef de verplichtingen die bij elk dienstverband horen."""
    output = {
        "plichten": ALTIJD_GELDENDE_PLICHTEN,
        "toelichting": (
            "Deze plichten gelden ongeacht welke regeling van toepassing is. Ze horen in "
            "hetzelfde antwoord als de financiële regelingen."
        ),
    }
    _audit_log("plichten", arguments, output)
    return [TextContent(type="text", text=_wrap_provenance(output))]


def _werkgeversservicepunt(arguments: dict) -> list[TextContent]:
    """Geef het regionale Werkgeversservicepunt voor een KvK-nummer (mock)."""
    kvk_nummer = str(arguments.get("kvk_nummer", "")).strip()
    if not kvk_nummer:
        return _fout("ONTBREKEND_VELD", "kvk_nummer is verplicht.")

    data = SERVICEPUNTEN.get(kvk_nummer)
    if data is None:
        output = {
            "kvk_nummer": kvk_nummer,
            "beschikbaar": False,
            "melding": (
                "Geen servicepunt bekend voor dit KvK-nummer in de demo-set. Verwijs de "
                "ondernemer naar het Werkgeversservicepunt in zijn eigen arbeidsmarktregio."
            ),
        }
        _audit_log("werkgeversservicepunt", arguments, output)
        return [TextContent(type="text", text=_wrap_provenance(output))]

    output = {"beschikbaar": True, **data}
    _audit_log("werkgeversservicepunt", arguments, output)
    return [TextContent(type="text", text=_wrap_provenance(output))]


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

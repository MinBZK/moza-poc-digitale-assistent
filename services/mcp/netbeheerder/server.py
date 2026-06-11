"""Netbeheerder MCP-server — Energieverbruik bij de bron via MCP (mock).

Mock-implementatie van een netbeheerder-gegevensdienst. Levert het
jaarlijkse energieverbruik (elektriciteit en gas) van de aansluiting(en)
van een bedrijf, zodat de assistent verbruiksgegevens bij de bron kan
raadplegen in plaats van ze aan de ondernemer te vragen (PDR-007).

Alleen bekende demo-aansluitingen worden geserveerd; voor andere
KvK-nummers meldt de server dat er geen gegevens beschikbaar zijn —
de assistent valt dan terug op uitvragen bij de gebruiker.

In productie zou dit een koppeling met de netbeheerder(s) zijn,
uitsluitend met machtiging van de ondernemer.

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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [netbeheerder] %(message)s")
logger = logging.getLogger("netbeheerder")

server = Server(name="netbeheerder")

SOURCE_LABEL = "Netbeheerder (mock)"
SERVER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Mock-data — jaarverbruik per KvK-nummer
# ---------------------------------------------------------------------------

MOCK_VERBRUIK: dict[str, dict] = {
    # Koffiezaak Noon (Claudia van Dam) — elektriciteit boven de drempel van
    # 50.000 kWh, dus de informatieplicht energiebesparing geldt.
    "85234567": {
        "kvk_nummer": "85234567",
        "netbeheerder": "Stedin (mock)",
        "peiljaar": 2025,
        "aansluitingen": [
            {
                "ean": "871685900012345678",
                "adres": "Witte de Withstraat 27, 3012BL Rotterdam",
                "jaarlijks_elektriciteitsverbruik_kwh": 61250,
                "jaarlijks_gasverbruik_m3": 9800,
            }
        ],
        "totaal": {
            "jaarlijks_elektriciteitsverbruik_kwh": 61250,
            "jaarlijks_gasverbruik_m3": 9800,
        },
        "toelichting": (
            "Verbruiksgegevens van de netbeheerder over het laatste volledige "
            "kalenderjaar. Gedeeld met machtiging van de ondernemer."
        ),
    },
}


def _verbruik_voor(kvk_nummer: str) -> dict | None:
    """Geef het mock-jaarverbruik voor een KvK-nummer, of None."""
    return MOCK_VERBRUIK.get(kvk_nummer)


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


# ---------------------------------------------------------------------------
# Tools (standaard §4.2)
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Publiceer beschikbare tools met beschrijving, schema en annotaties."""
    return [
        Tool(
            name="verbruik",
            description=(
                "Haal het jaarlijkse energieverbruik (elektriciteit in kWh en "
                "gas in m³) op bij de netbeheerder voor het bedrijf van de "
                "ingelogde gebruiker. Gebruik dit VOORDAT u de gebruiker om "
                "verbruiksgegevens vraagt — als de bron de gegevens heeft, "
                "hoeft de ondernemer niets op te zoeken. Als er geen gegevens "
                "beschikbaar zijn, vraag het verbruik dan aan de gebruiker."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kvk_nummer": {
                        "type": "string",
                        "description": (
                            "KvK-nummer van het bedrijf (8 cijfers), "
                            "uit kvk__mijn_bedrijf."
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
    if name == "verbruik":
        return _verbruik(arguments)
    raise ValueError(f"Onbekende tool: {name}")


def _verbruik(arguments: dict) -> list[TextContent]:
    """Geef het jaarverbruik voor een KvK-nummer (mock)."""
    kvk_nummer = str(arguments.get("kvk_nummer", "")).strip()
    if not kvk_nummer:
        return [
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "error": "ONTBREKEND_VELD",
                        "message": "kvk_nummer is verplicht.",
                    },
                    ensure_ascii=False,
                ),
            )
        ]

    data = _verbruik_voor(kvk_nummer)
    if data is None:
        output = {
            "kvk_nummer": kvk_nummer,
            "beschikbaar": False,
            "melding": (
                "Geen verbruiksgegevens beschikbaar bij de netbeheerder voor "
                "dit KvK-nummer. Vraag het jaarverbruik aan de gebruiker."
            ),
        }
        _audit_log("verbruik", arguments, output)
        return [TextContent(type="text", text=_wrap_provenance(output))]

    output = {"beschikbaar": True, **data}
    _audit_log("verbruik", arguments, output)
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

"""Business Wallet-presentatie van energiegegevens — demo-mock (PDR-008).

Demo-model van de EU Business Wallet: de ondernemer HOUDT een
energieverbruik-attestatie (afgegeven door de netbeheerder) in zijn Business Wallet
en DEELT die met toestemming met de assistent. Zo komen de verbruiksgegevens
"uit de Business Wallet" in plaats van uit een directe bevraging van een achterliggende
dienst.

LET OP — dit is bewust GEEN echte Business Wallet-/MCP-koppeling: de Business Wallet is voor de
demo een presentatie-/toestemmingslaag. De mock hieronder speelt de
netbeheerder als UITGEVER (issuer) van de attestatie; de respons modelleert
een door de Business Wallet gepresenteerde verifiable credential met expliciete
toestemming. Zie ook PDR-008 en https://digital-strategy.ec.europa.eu/nl/policies/business-wallets

Alleen bekende demo-aansluitingen worden geserveerd; voor andere KvK-nummers
meldt de server dat er geen attestatie in de Business Wallet zit — de assistent valt
dan terug op uitvragen bij de gebruiker.

In productie zou de netbeheerder de attestatie uitgeven aan de Business Wallet van de
ondernemer (EUDI/Business Wallet), die haar met toestemming presenteert.

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

# De Business Wallet PRESENTEERT de gegevens (bron die de gebruiker ziet); de
# netbeheerder is de UITGEVER (issuer) van de attestatie.
SOURCE_LABEL = "EU Business Wallet (mock)"
ISSUER_LABEL = "Netbeheerder (mock, uitgever)"
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
                "adres": "Meent 88, 3011JM Rotterdam",
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
    # Kwekerij De Bloesem (glastuinbouw) — elektriciteit boven drempel van 50.000
    # kWh, gas boven drempel van 25.000 m3 (dus informatieplicht). 140.000 m3 is
    # gekozen, niet gegroeid: boven de gasdrempel van 25.000 (dus de
    # informatieplicht geldt) en onder de onderzoeksdrempel van 170.000. Die tweede
    # grens geeft een verplichting waarvoor de assistent geen handelingsperspectief
    # heeft; een respondent kan dat niet onderscheiden van een gat in het product.
    "62345681": {
        "kvk_nummer": "62345681",
        "netbeheerder": "Stedin (mock)",
        "peiljaar": 2025,
        "aansluitingen": [
            {
                "ean": "871685900023456789",
                "adres": "Hoefweg 210, 2665KG Bleiswijk",
                "jaarlijks_elektriciteitsverbruik_kwh": 420000,
                "jaarlijks_gasverbruik_m3": 140000,
            }
        ],
        "totaal": {
            "jaarlijks_elektriciteitsverbruik_kwh": 420000,
            "jaarlijks_gasverbruik_m3": 140000,
        },
        "toelichting": (
            "Verbruiksgegevens van de netbeheerder over het laatste volledige "
            "kalenderjaar. Gedeeld met machtiging van de ondernemer."
        ),
    },
    # Roots & Locks (kapsalon) — ruim onder beide drempels, dus de
    # informatieplicht energiebesparing geldt niet. De negatieve uitkomst.
    "56789012": {
        "kvk_nummer": "56789012",
        "netbeheerder": "Stedin (mock)",
        "peiljaar": 2025,
        "aansluitingen": [
            {
                "ean": "871685900034567890",
                "adres": "Witte de Withstraat 18, 3012BP Rotterdam",
                "jaarlijks_elektriciteitsverbruik_kwh": 14800,
                "jaarlijks_gasverbruik_m3": 1900,
            }
        ],
        "totaal": {
            "jaarlijks_elektriciteitsverbruik_kwh": 14800,
            "jaarlijks_gasverbruik_m3": 1900,
        },
        "toelichting": (
            "Verbruiksgegevens van de netbeheerder over het laatste volledige "
            "kalenderjaar. Gedeeld met machtiging van de ondernemer."
        ),
    },
    # Vogel Bouwregie B.V. (bouwmanagement) — bedrijfsloods met kantoor. De
    # elektriciteit ligt boven de drempel van 50.000 kWh, het gas eronder: nog
    # een derde pad door dezelfde regel, en dus een bruikbaar onderzoekscenario.
    "61234570": {
        "kvk_nummer": "61234570",
        "netbeheerder": "Stedin (mock)",
        "peiljaar": 2025,
        "aansluitingen": [
            {
                "ean": "871685900045678901",
                "adres": "Waalhaven 120, 3089JJ Rotterdam",
                "jaarlijks_elektriciteitsverbruik_kwh": 88400,
                "jaarlijks_gasverbruik_m3": 12600,
            }
        ],
        "totaal": {
            "jaarlijks_elektriciteitsverbruik_kwh": 88400,
            "jaarlijks_gasverbruik_m3": 12600,
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
                "issuer": ISSUER_LABEL,
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
                "Vraag de energieverbruik-attestatie op uit de "
                "Business Wallet (mock) van de ingelogde ondernemer: het jaarverbruik "
                "(elektriciteit in kWh, gas in m³), afgegeven door de "
                "netbeheerder en met toestemming van de ondernemer gedeeld. "
                "Gebruik dit VOORDAT u de gebruiker om verbruiksgegevens vraagt "
                "— zit de attestatie in de Business Wallet, dan hoeft de ondernemer niets "
                "op te zoeken; vermeld dat de gegevens uit de Business Wallet komen "
                "(afgegeven door de netbeheerder). Zit er geen attestatie in de "
                "Business Wallet, vraag het verbruik dan aan de gebruiker."
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
                        # `velden` apart van `message`: de host bouwt daar een
                        # gebruikersmelding mee (zie services/host/errors.py).
                        "velden": ["kvk_nummer"],
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
                "Geen energieverbruik-attestatie in de Business Wallet voor dit "
                "KvK-nummer. Vraag het jaarverbruik aan de gebruiker."
            ),
        }
        _audit_log("verbruik", arguments, output)
        return [TextContent(type="text", text=_wrap_provenance(output))]

    # Modelleer de respons als een door de Business Wallet gepresenteerde credential:
    # uitgever (netbeheerder), houder (de ondernemer) en expliciete toestemming.
    output = {
        "beschikbaar": True,
        "credential": {
            "type": "EnergieverbruikAttestatie",
            "uitgegeven_door": data.get("netbeheerder", ISSUER_LABEL),
            "houder": {"kvk_nummer": kvk_nummer},
            "peiljaar": data["peiljaar"],
        },
        "toestemming": {
            "gedeeld_via": SOURCE_LABEL,
            "met_toestemming_ondernemer": True,
        },
        "verbruik": {
            "aansluitingen": data["aansluitingen"],
            "totaal": data["totaal"],
        },
        "toelichting": data["toelichting"],
    }
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

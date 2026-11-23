"""Uitleg MCP-server — een beslisgraaf in gewone taal, via MCP (PDR-016).

De regelrecht-engine levert per uitkomst een beslisgraaf: de uitkomst
bovenaan, daaronder de doorslaggevende voorwaarden, gegevens en berekening
met wetsgrond. Deze server zet die graaf om in een korte tekst voor een
ondernemer en toetst die tekst tegen de graaf. Dezelfde module als het
endpoint `/uitleg` van de host (`services/host/uitleg.py`): één prompt, één
toets.

De server heeft zelf geen sleutel voor een taalmodel. `verwoord` vraagt het
model van de aanroepende client via MCP-sampling (`sampling/createMessage`),
zodat de sleutel bij de client blijft (PDR-010). Een client zonder sampling
krijgt het prompt terug (`modus: "prompt"`) en kan zelf het model aanroepen;
`toets` werkt altijd, zonder model.

Voldoet aan de MCP-standaard voor Generieke Interactieservices:
- Provenance metadata bij elke response (§4.1, §7)
- ToolAnnotations op elke tool (§4.2, §7)
- Audit logging bij elke tool-aanroep (§2.2)
- Beschrijvingen en inputschema's (§7)
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    ClientCapabilities,
    SamplingCapability,
    SamplingMessage,
    TextContent,
    Tool,
    ToolAnnotations,
)

# De module van de host, zodat prompt en toets op één plek staan.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "host"))

import uitleg  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [uitleg] %(message)s")
logger = logging.getLogger("uitleg")

server = Server(name="uitleg")

SOURCE_LABEL = "Uitleg in gewone taal (regelrecht-beslisgraaf)"
SERVER_VERSION = "0.1.0"

GRAAF_SCHEMA = {
    "type": "object",
    "description": (
        "De beslisgraaf van de regelrecht-engine (`afleiding.uitkomst` uit de "
        "kern van regelrecht-uitleg): knopen met soort, naam, waarde, eenheid, "
        "grond en doorslaggevend."
    ),
}
SAMENVATTING_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "description": "De korte, niet-technische regels van de kern (tekst.kort).",
}


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
    """Log een tool-aanroep conform standaard §2.2: veldnamen, geen inhoud."""
    entry = {
        "timestamp": datetime.now(UTC).isoformat(),
        "tool": tool_name,
        "input_keys": sorted(str(k) for k in input_data),
        "output": {"type": type(output_data).__name__, "keys": list(output_data.keys())},
    }
    logger.info("AUDIT: %s", json.dumps(entry, ensure_ascii=False, default=str))


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Publiceer de tools met beschrijving, schema en annotaties."""
    return [
        Tool(
            name="verwoord",
            description=(
                "Leg een uitkomst van de regelrecht-engine uit in gewone taal (B1). "
                "Gebruikt alleen de beslisgraaf; het model van de aanroeper schrijft "
                "de tekst (MCP-sampling). Geeft de tekst terug met een toets: elk "
                "bedrag en percentage moet in de graaf staan en het wetsartikel moet "
                "genoemd zijn. Zonder sampling komt het prompt terug (modus 'prompt')."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "regeling": {"type": "string", "description": "Naam van de regeling."},
                    "graaf": GRAAF_SCHEMA,
                    "samenvatting": SAMENVATTING_SCHEMA,
                },
                "required": ["regeling", "graaf"],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, openWorldHint=False
            ),
        ),
        Tool(
            name="toets",
            description=(
                "Toets een uitlegtekst tegen de beslisgraaf: verzonnen bedragen of "
                "percentages, ontbrekend wetsartikel, leesbaarheid. Zonder model."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tekst": {"type": "string", "description": "De te toetsen tekst."},
                    "graaf": GRAAF_SCHEMA,
                    "samenvatting": SAMENVATTING_SCHEMA,
                },
                "required": ["tekst", "graaf"],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, openWorldHint=False
            ),
        ),
        Tool(
            name="regels",
            description=(
                "De beslisgraaf als ingesprongen regels, met het prompt dat "
                "`verwoord` gebruikt. Zonder model; om zelf te lezen of te prompten."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "regeling": {"type": "string", "description": "Naam van de regeling."},
                    "graaf": GRAAF_SCHEMA,
                    "samenvatting": SAMENVATTING_SCHEMA,
                },
                "required": ["graaf"],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True, destructiveHint=False, openWorldHint=False
            ),
        ),
    ]


def _lees(arguments: dict) -> tuple[dict, dict | None]:
    """De graaf en de samenvatting uit de argumenten, of een nette fout."""
    graaf = arguments.get("graaf")
    if not uitleg.graaf_geldig(graaf):
        return {}, {
            "error": "INPUT_INVALID",
            "velden": ["graaf"],
            "message": "Geen geldige beslisgraaf: een knoop heeft 'soort' en 'waarde'.",
        }
    samenvatting = arguments.get("samenvatting") or []
    if not isinstance(samenvatting, list):
        samenvatting = []
    return {
        "graaf": graaf,
        "regeling": str(arguments.get("regeling") or "").strip()[:120],
        "samenvatting": [str(z)[:400] for z in samenvatting[:12]],
    }, None


async def _verwoord(arguments: dict) -> dict:
    invoer, fout = _lees(arguments)
    if fout:
        return fout
    if not invoer["regeling"]:
        return {"error": "ONTBREKEND_VELD", "velden": ["regeling"], "message": "Parameter 'regeling' is verplicht."}
    regels = uitleg.graaf_regels(invoer["graaf"])
    prompt = uitleg.bouw_prompt(regels, invoer["regeling"], invoer["samenvatting"])
    if len(prompt) > uitleg.MAX_VRAAG_TEKENS:
        return {
            "error": "INPUT_INVALID",
            "velden": ["graaf"],
            "message": f"De beslisgraaf is groter dan {uitleg.MAX_VRAAG_TEKENS} tekens.",
        }

    sessie = server.request_context.session
    kan_samplen = sessie.check_client_capability(
        ClientCapabilities(sampling=SamplingCapability())
    )
    if not kan_samplen:
        return {
            "modus": "prompt",
            "systeemprompt": uitleg.SYSTEEMPROMPT,
            "prompt": prompt,
            "regels": len(regels),
        }

    resultaat = await sessie.create_message(
        messages=[SamplingMessage(role="user", content=TextContent(type="text", text=prompt))],
        system_prompt=uitleg.SYSTEEMPROMPT,
        max_tokens=uitleg.MAX_UITLEG_TOKENS,
    )
    inhoud = resultaat.content
    tekst = (
        inhoud.text
        if isinstance(inhoud, TextContent)
        else "\n".join(c.text for c in (inhoud if isinstance(inhoud, list) else []) if isinstance(c, TextContent))
    ).strip()
    if not tekst:
        return {"error": "EXECUTION_ERROR", "message": "Het model gaf geen tekst terug."}
    return {
        "modus": "sampling",
        "tekst": tekst,
        "toets": uitleg.toets(tekst, regels, invoer["samenvatting"]).als_dict(),
        "regels": len(regels),
        "model": getattr(resultaat, "model", None),
    }


def _toets(arguments: dict) -> dict:
    invoer, fout = _lees(arguments)
    if fout:
        return fout
    tekst = str(arguments.get("tekst") or "")
    if not tekst.strip():
        return {"error": "ONTBREKEND_VELD", "velden": ["tekst"], "message": "Parameter 'tekst' is verplicht."}
    regels = uitleg.graaf_regels(invoer["graaf"])
    return uitleg.toets(tekst, regels, invoer["samenvatting"]).als_dict()


def _regels(arguments: dict) -> dict:
    invoer, fout = _lees(arguments)
    if fout:
        return fout
    regels = uitleg.graaf_regels(invoer["graaf"])
    return {
        "regels": regels,
        "prompt": uitleg.bouw_prompt(regels, invoer["regeling"] or "de regeling", invoer["samenvatting"]),
        "systeemprompt": uitleg.SYSTEEMPROMPT,
    }


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Voer een tool uit en log de aanroep (standaard §2.2)."""
    arguments = arguments or {}
    if name == "verwoord":
        data = await _verwoord(arguments)
    elif name == "toets":
        data = _toets(arguments)
    elif name == "regels":
        data = _regels(arguments)
    else:
        raise ValueError(f"Onbekende tool: {name}")
    _audit_log(name, arguments, data)
    return [TextContent(type="text", text=_wrap_provenance(data))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

"""RegelRecht MCP-server — Beslislogica via MCP.

Proxy naar de RegelRecht law execution engine (poc-machine-law) voor het
toetsen van regelgeving. Primaire use case: Informatieplicht Energiebesparing.

De server stuurt requests door naar het POC-endpoint van RegelRecht
via JSON-RPC en vertaalt de resultaten naar MCP-responses.

Voldoet aan de MCP-standaard voor Generieke Interactieservices:
- Provenance metadata bij elke response (§4.1, §7)
- ToolAnnotations op elke tool (§4.2, §7)
- Audit logging bij elke tool-aanroep (§2.2)
- Beschrijvingen en inputschema's (§7)
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
    ToolAnnotations,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [regelrecht] %(message)s")
logger = logging.getLogger("regelrecht")

server = Server(name="regelrecht")

# ---------------------------------------------------------------------------
# API configuratie
# ---------------------------------------------------------------------------

REGELRECHT_RPC_URL = os.getenv(
    "REGELRECHT_RPC_URL",
    "https://ui.lac.apps.digilab.network/mcp/rpc",
)

SOURCE_LABEL = "RegelRecht (poc-machine-law)"
SERVER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# EML-maatregelbepaling: via de poc-machine-law engine, met lokale fallback
#
# Welke maatregelen gelden hangt af van feitelijke bedrijfskenmerken die
# nergens geregistreerd staan; de ondernemer levert ze. De wet
# omgevingswet/energiebesparing/maatregelen in de engine bepaalt de
# geldende maatregelen; de vraagteksten staan als parameter-descriptions
# in die wet en worden door de assistent afgelezen (twee-staps-flow).
# Het blok hieronder is uitsluitend de fallback voor als de engine
# onbereikbaar is en moet synchroon blijven met de wet-YAML (PDR-007).
# ---------------------------------------------------------------------------

EML_SOURCE_LABEL = "RegelRecht — EML-maatregelbepaling (lokale fallback)"
EML_LAW = "omgevingswet/energiebesparing/maatregelen"

EML_FALLBACK_VRAGEN = [
    {
        "naam": "HEEFT_KOELINSTALLATIE",
        "vraag": "Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?",
    },
    {
        "naam": "HEEFT_AFZUIGINSTALLATIE",
        "vraag": "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?",
    },
]

EML_FALLBACK_MAATREGELEN = [
    {"code": "GC1", "naam": "Pas een klokregeling toe en regel deze in", "categorie": "Gebouwen, Ruimteverwarming", "voorwaarde": None},
    {"code": "GC3", "naam": "Pas een weersafhankelijke regeling toe", "categorie": "Gebouwen, Ruimteverwarming", "voorwaarde": None},
    {"code": "GF4", "naam": "Vervang gloei-, halogeen- en spaarlampen door LED-lampen", "categorie": "Gebouwen, Binnenverlichting", "voorwaarde": None},
    {"code": "FD3", "naam": "Pas nachtafdekking toe bij semi-verticale koelmeubels", "categorie": "Faciliteiten, Productkoeling", "voorwaarde": "HEEFT_KOELINSTALLATIE"},
    {"code": "FD7", "naam": "Isoleer de wanden van koelcellen om warmte buiten te houden", "categorie": "Faciliteiten, Productkoeling", "voorwaarde": "HEEFT_KOELINSTALLATIE"},
    {"code": "FE4", "naam": "Pas een laagdebiet afzuigkap toe bij grootkeukens", "categorie": "Faciliteiten, Grootkeukenapparatuur", "voorwaarde": "HEEFT_AFZUIGINSTALLATIE"},
    {"code": "GD1", "naam": "Pas een klokregeling toe op het ventilatiesysteem", "categorie": "Gebouwen, Ruimteventilatie", "voorwaarde": "HEEFT_AFZUIGINSTALLATIE"},
]


def _eml_fallback(feiten: dict) -> dict:
    """Lokale evaluatie van de demo-subset (zelfde flow als de engine)."""
    onbeantwoord = [v for v in EML_FALLBACK_VRAGEN if v["naam"] not in feiten]
    if onbeantwoord:
        return {"benodigde_feiten": onbeantwoord}
    return {
        "maatregelen": [
            {
                "code": m["code"],
                "naam": m["naam"],
                "categorie": m["categorie"],
                "van_toepassing": (
                    m["voorwaarde"] is None or bool(feiten.get(m["voorwaarde"]))
                ),
            }
            for m in EML_FALLBACK_MAATREGELEN
        ],
        "feiten": feiten,
    }


def _eml_vragen(rule_spec: dict, feiten: dict) -> list[dict]:
    """Lees de nog te stellen feitelijke vragen af uit de wet-spec."""
    params = rule_spec.get("properties", {}).get("parameters", [])
    return [
        {"naam": p["name"], "vraag": p.get("description", p["name"])}
        for p in params
        if p.get("name") and p["name"] not in feiten
    ]


def _eml_lijst(structured: dict) -> list[dict]:
    """Map engine-outputs (eml_<code>_van_toepassing) naar de maatregelenlijst.

    Naam en categorie komen uit de output-descriptions in de wet-spec
    ("<categorie> — <naam>"); alle regelkennis zit dus in de engine.
    """
    beschrijvingen = {
        o["name"]: o.get("description", "")
        for o in structured.get("rule_spec", {})
        .get("properties", {})
        .get("output", [])
        if o.get("name")
    }
    lijst = []
    for naam, waarde in structured.get("output", {}).items():
        if not (naam.startswith("eml_") and naam.endswith("_van_toepassing")):
            continue
        if waarde is None:
            continue
        code = naam[len("eml_") : -len("_van_toepassing")].upper()
        beschrijving = beschrijvingen.get(naam, "")
        categorie, scheider, titel = beschrijving.partition(" — ")
        lijst.append(
            {
                "code": code,
                "naam": titel if scheider else (beschrijving or code),
                "categorie": categorie if scheider else "",
                "van_toepassing": bool(waarde),
            }
        )
    return lijst


# ---------------------------------------------------------------------------
# HTTP helper — JSON-RPC naar RegelRecht endpoint
# ---------------------------------------------------------------------------

_rpc_id = 0


async def _rpc_call(method: str, params: dict) -> dict:
    """Stuur een JSON-RPC request naar het RegelRecht MCP endpoint."""
    global _rpc_id
    _rpc_id += 1

    payload = {
        "jsonrpc": "2.0",
        "id": _rpc_id,
        "method": method,
        "params": params,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            REGELRECHT_RPC_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        raise RuntimeError(
            f"RegelRecht RPC fout: {data['error'].get('message', data['error'])}"
        )

    return data.get("result", {})


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _simplify_result(structured: dict) -> dict:
    """Extraheer de relevante velden uit de uitgebreide RegelRecht response."""
    result = {}

    # Metadata van de wet
    metadata = structured.get("law_metadata", {})
    if metadata:
        result["wet"] = metadata.get("name", "")
        result["beschrijving"] = metadata.get("description", "").strip()
        result["service"] = metadata.get("service", "")

    # Hoofdresultaten
    result["voldoet_aan_voorwaarden"] = structured.get("requirements_met", False)
    result["uitkomsten"] = structured.get("output", {})

    # Ontbrekende parameters
    missing = structured.get("missing_parameters", [])
    if missing:
        result["ontbrekende_gegevens"] = [
            {
                "naam": field.get("name", ""),
                "beschrijving": field.get("description", ""),
            }
            for entry in missing
            for field in entry.get("missing_fields", [])
        ]

    # Regelspecificatie: definities (drempelwaarden etc.)
    rule_spec = structured.get("rule_spec", {})
    definitions = rule_spec.get("properties", {}).get("definitions", {})
    if definitions:
        result["drempelwaarden"] = definitions

    # Wettelijke grondslag uit actions
    actions = rule_spec.get("actions", [])
    if actions:
        grondslagen = []
        for action in actions:
            basis = action.get("legal_basis", {})
            if basis:
                grondslagen.append(
                    {
                        "output": action.get("output", ""),
                        "wet": basis.get("law", ""),
                        "artikel": basis.get("article", ""),
                        "url": basis.get("url", ""),
                        "toelichting": basis.get("explanation", ""),
                    }
                )
        if grondslagen:
            result["wettelijke_grondslag"] = grondslagen

    return result


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


def _wrap_eml_provenance(data: dict) -> str:
    """Provenance voor de lokale EML-maatregelbepaling (lokale fallback wanneer de engine onbereikbaar is)."""
    return json.dumps(
        {
            "data": data,
            "provenance": {
                "source": EML_SOURCE_LABEL,
                "timestamp": datetime.now(UTC).isoformat(),
                "version": SERVER_VERSION,
                "fallback": True,
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
# Tools (standaard §4.2)
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Publiceer beschikbare tools met beschrijving, schema en annotaties."""
    return [
        Tool(
            name="check",
            description=(
                "Controleer of de Informatieplicht Energiebesparing van toepassing "
                "is op een bedrijf. Gebruikt de beslislogica van het Besluit "
                "activiteiten leefomgeving (artikelen 5.15 en 5.15d) om te bepalen "
                "of een organisatie verplicht is om energiebesparende maatregelen "
                "te rapporteren. Vereist minimaal een KvK-nummer. Optioneel kunnen "
                "energieverbruikcijfers worden meegegeven voor een volledig oordeel."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kvk_nummer": {
                        "type": "string",
                        "description": (
                            "KvK-nummer van het bedrijf (8 cijfers). "
                            "Wordt gebruikt om bedrijfsgegevens op te halen."
                        ),
                    },
                    "jaarlijks_elektriciteitsverbruik_kwh": {
                        "type": "number",
                        "description": (
                            "Jaarlijks elektriciteitsverbruik in kWh. "
                            "Drempel: 50.000 kWh."
                        ),
                    },
                    "jaarlijks_gasverbruik_m3": {
                        "type": "number",
                        "description": (
                            "Jaarlijks gasverbruik in m3 aardgasequivalenten. "
                            "Drempel: 25.000 m3."
                        ),
                    },
                    "is_woonfunctie": {
                        "type": "boolean",
                        "description": (
                            "Of het pand uitsluitend een woonfunctie heeft. "
                            "Gebouwen met alleen woonfunctie zijn uitgezonderd."
                        ),
                    },
                },
                "required": ["kvk_nummer"],
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=True,
            ),
        ),
        Tool(
            name="maatregelen",
            description=(
                "Bepaal welke maatregelen uit de Erkende Maatregelenlijst "
                "(EML 2023) voor het bedrijf gelden. Roep EERST aan zónder "
                "feiten: de tool meldt dan welke feitelijke vragen aan de "
                "ondernemer gesteld moeten worden (benodigde_feiten). Stel "
                "die vragen letterlijk — de feiten staan nergens "
                "geregistreerd en blijven bewust bij de ondernemer — en roep "
                "daarna opnieuw aan met de antwoorden in 'feiten'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "feiten": {
                        "type": "object",
                        "description": (
                            "Antwoorden op de gemelde feitelijke vragen "
                            "(naam → true/false). Weglaten bij de eerste "
                            "aanroep."
                        ),
                        "additionalProperties": {"type": "boolean"},
                    },
                },
                "additionalProperties": False,
            },
            annotations=ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=True,
            ),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Voer een tool uit en log de aanroep (standaard §2.2)."""
    if name == "check":
        result = await _check_informatieplicht(arguments)
        _audit_log("check", arguments, result)
        return [
            TextContent(
                type="text",
                text=_wrap_provenance(result),
            )
        ]

    if name == "maatregelen":
        data, fallback = await _maatregelen(arguments)
        _audit_log("maatregelen", arguments, data)
        tekst = _wrap_eml_provenance(data) if fallback else _wrap_provenance(data)
        return [TextContent(type="text", text=tekst)]

    raise ValueError(f"Onbekende tool: {name}")


async def _maatregelen(arguments: dict) -> tuple[dict, bool]:
    """Bepaal EML-maatregelen via de engine; lokale fallback bij storing.

    Geeft (data, fallback_gebruikt) terug zodat de caller het juiste
    provenance-label kan kiezen.
    """
    ruwe_feiten = arguments.get("feiten")
    if not isinstance(ruwe_feiten, dict):
        ruwe_feiten = {}
    feiten = {str(k): bool(v) for k, v in ruwe_feiten.items()}
    try:
        result = await _rpc_call(
            "tools/call",
            {
                "name": "execute_law",
                "arguments": {
                    "service": "RVO",
                    "law": EML_LAW,
                    "parameters": feiten,
                },
            },
        )
        structured = (result or {}).get("structuredContent") or {}
        if not structured.get("success"):
            raise RuntimeError(f"engine-response niet bruikbaar (success={structured.get('success')!r})")
    except (httpx.HTTPError, ValueError, RuntimeError) as e:
        logger.warning("EML via engine mislukt, lokale fallback: %s", e)
        return _eml_fallback(feiten), True

    if structured.get("missing_required"):
        vragen = _eml_vragen(structured.get("rule_spec", {}), feiten)
        if not vragen:
            # Spec onbruikbaar om vragen uit af te leiden — fallback weet ze.
            return _eml_fallback(feiten), True
        return {"benodigde_feiten": vragen}, False

    lijst = _eml_lijst(structured)
    if not lijst:
        logger.warning("EML-engine-response zonder eml_-outputs, fallback")
        return _eml_fallback(feiten), True
    return {"maatregelen": lijst, "feiten": feiten}, False


async def _check_informatieplicht(params: dict) -> dict:
    """Check Informatieplicht Energiebesparing via RegelRecht."""
    kvk_nummer = params.get("kvk_nummer", "")

    # Bouw parameters op voor de law engine
    law_params = {"KVK_NUMMER": kvk_nummer}

    # Optionele overrides voor energieverbruik
    overrides = {}
    elektriciteit = params.get("jaarlijks_elektriciteitsverbruik_kwh")
    gas = params.get("jaarlijks_gasverbruik_m3")
    is_woonfunctie = params.get("is_woonfunctie")

    if elektriciteit is not None or gas is not None or is_woonfunctie is not None:
        rvo_overrides = {}
        if elektriciteit is not None:
            rvo_overrides["JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"] = elektriciteit
        if gas is not None:
            rvo_overrides["JAARLIJKS_GASVERBRUIK_M3"] = gas
        if is_woonfunctie is not None:
            rvo_overrides["IS_WOONFUNCTIE"] = is_woonfunctie
        overrides["RVO"] = rvo_overrides

    # Bouw het RPC request
    rpc_arguments = {
        "service": "RVO",
        "law": "omgevingswet/energiebesparing/informatieplicht",
        "parameters": law_params,
    }
    if overrides:
        rpc_arguments["overrides"] = overrides

    try:
        result = await _rpc_call(
            "tools/call",
            {"name": "execute_law", "arguments": rpc_arguments},
        )
    except httpx.HTTPStatusError as e:
        return {
            "error": "SOURCE_UNAVAILABLE",
            "message": (
                f"RegelRecht endpoint niet beschikbaar: {e.response.status_code}"
            ),
        }
    except httpx.RequestError as e:
        return {
            "error": "SOURCE_UNAVAILABLE",
            "message": f"RegelRecht endpoint niet bereikbaar: {e}",
        }
    except RuntimeError as e:
        return {
            "error": "EXECUTION_ERROR",
            "message": str(e),
        }

    # Extraheer structured content uit de MCP response
    structured = result.get("structuredContent", {})
    if not structured:
        # Fallback: geef de ruwe tekst terug
        content = result.get("content", [])
        text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        return {"resultaat": text}

    return _simplify_result(structured)


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

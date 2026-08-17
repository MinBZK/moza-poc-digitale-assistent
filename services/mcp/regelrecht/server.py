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
    # De demo-engine verhuisde van ui.lac.apps.* naar ui.lac.projects.* (de oude
    # host 301-redirect nog tijdelijk). Override desnoods via REGELRECHT_RPC_URL.
    "https://ui.lac.projects.digilab.network/mcp/rpc",
)

SOURCE_LABEL = "RegelRecht (poc-machine-law)"
SERVER_VERSION = "0.1.0"

# De maatregelbepaling liep hier lang langs een eigen pad, met een lokale kopie
# van zeven maatregelen als terugval. Die kopie is weg. Ze gaf de algemene
# bijlage aan iedereen, en sinds de wet ook de glastuinbouwbijlagen draagt zou
# ze een kweker onder glas maatregelen voorschotelen die in zijn eigen bijlage
# niet staan — een lokale kopie die zich voordoet als de regel, en dan ook nog
# de verkeerde. De regel gaat nu langs dezelfde weg als elke andere.
EML_LAW = "omgevingswet/energiebesparing/maatregelen"

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


# Constanten per wet. De engine geeft ze alleen bij een aanroep met lege
# parameters, dus die aanroep is een extra RPC per toets. Binnen een sessie
# veranderen wetsconstanten niet, dus cachen we ze procesbreed.
_definities_cache: dict[str, dict] = {}


# Welke constanten van een wet bruikbaar zijn als "drempelwaarden". De
# maatregelbepaling draagt naast de categorie-indeling ook de twee volledige
# bijlagen — 255 maatregelen met hun randvoorwaarden. Die horen in de uitkomst
# (`uitkomsten.maatregelen`, gefilterd op wat bij dit bedrijf past), niet als
# constantenblok in elke respons: dat vult het venster van het model met
# maatregelen waar de ondernemer niets mee te maken heeft.
_DEFINITIES_TOEGESTAAN: dict[str, frozenset[str]] = {
    EML_LAW: frozenset({"CATEGORIEEN"}),
}


def _bruikbare_definities(law: str, definities: dict) -> dict:
    """Beperk de constanten van een wet tot wat een client ermee kan."""
    toegestaan = _DEFINITIES_TOEGESTAAN.get(law)
    if toegestaan is None:
        return definities
    return {naam: waarde for naam, waarde in definities.items() if naam in toegestaan}


async def _definities_voor(law: str, service: str) -> dict:
    """Constanten (drempelwaarden) van een wet, uit de engine.

    Faalt de aanroep, dan geven we een leeg dict terug in plaats van de toets te
    laten klappen: zonder drempels is het antwoord onvolledig, met een exception
    is er geen antwoord.
    """
    sleutel = f"{service}/{law}"
    if sleutel in _definities_cache:
        return _definities_cache[sleutel]
    try:
        rpc = await _rpc_call(
            "tools/call",
            {
                "name": "execute_law",
                "arguments": {"service": service, "law": law, "parameters": {}},
            },
        )
        structured = rpc.get("structuredContent", {})
        definities = (
            structured.get("rule_spec", {}).get("properties", {}).get("definitions", {})
            or {}
        )
        definities = _bruikbare_definities(law, definities)
    except Exception as e:
        # Niet cachen: een mislukte ophaal is geen weten-dat-het-leeg-is, en
        # anders legt één tijdelijke hik de drempelwaarden blijvend plat.
        logger.warning("Definities ophalen mislukt (%s): %s", law, e)
        return {}
    # Een leeg resultaat is net zomin "weten dat het leeg is" als een mislukte
    # ophaal: de RPC kan technisch slagen zonder bruikbare inhoud (geen
    # `structuredContent`, of een wet die de constante anders noemt). De cache
    # is procesbreed en kent geen invalidatie, dus dat zou blijven staan tot een
    # herstart - en dan meldt de host "RegelRecht niet beschikbaar" terwijl de
    # engine gewoon draait.
    if definities:
        _definities_cache[sleutel] = definities
    return definities


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _simplify_result(
    structured: dict, definities: dict | None = None, law: str = ""
) -> dict:
    """Extraheer de relevante velden uit de uitgebreide RegelRecht response.

    `definities` komt van `_definities_voor`, omdat de engine
    `rule_spec.properties.definitions` alleen vult bij een aanroep met lege
    parameters. Het model roept altijd met gevulde parameters aan; zonder dit
    argument heeft het dus nooit de drempels waar de prompt om vraagt.
    """
    result = {}

    # Metadata van de wet
    metadata = structured.get("law_metadata", {})
    if metadata:
        result["wet"] = metadata.get("name", "")
        result["beschrijving"] = metadata.get("description", "").strip()
        result["service"] = metadata.get("service", "")

    # Hoofdresultaten
    result["voldoet_aan_voorwaarden"] = structured.get("requirements_met", False)
    # Onderscheidt "de verplichting geldt niet" (alles getoetst, niets mist)
    # van "nog niet vast te stellen" (er mist nog een gegeven). Zonder dit
    # veld is een definitieve negatieve uitkomst niet te onderscheiden van een
    # onvolledige: beide geven hier `voldoet_aan_voorwaarden: False` terug.
    # Alleen doorgeven als de engine het meegaf: ontbreekt het (oudere
    # servervorm), dan moet de host-kant de voorzichtige aanname kunnen maken
    # in plaats van hier stilzwijgend "niets mist" in te vullen.
    if "missing_required" in structured:
        result["missing_required"] = structured["missing_required"]
    result["uitkomsten"] = structured.get("output", {})

    # De waarden waarop de regel feitelijk rekende. Zonder deze moet het model
    # de getallen uit het gesprek reconstrueren of verzinnen.
    gebruikt = {
        naam.lstrip("$"): waarde
        for naam, waarde in (structured.get("input") or {}).items()
    }
    if gebruikt:
        result["gebruikte_waarden"] = gebruikt

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

    # Constanten van de regel. Meegegeven wint van wat er in deze respons zit:
    # bij gevulde parameters geeft de engine hier niets terug.
    #
    # Het terugvalpad gaat door hetzelfde filter als `_definities_voor`. Zonder
    # dat sloop de maatregelenwet haar twee volledige bijlagen - 255 maatregelen
    # met randvoorwaarden - alsnog als constantenblok de respons in zodra
    # `definities` leeg is, bijvoorbeeld omdat de tweede RPC omviel. Precies wat
    # `_bruikbare_definities` moet voorkomen.
    rule_spec = structured.get("rule_spec", {})
    uit_respons = _bruikbare_definities(
        law, rule_spec.get("properties", {}).get("definitions", {}) or {}
    )
    drempels = definities or uit_respons
    if drempels:
        result["drempelwaarden"] = drempels

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
# Tools (standaard §4.2)
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Publiceer beschikbare tools met beschrijving, schema en annotaties.

    RegelRecht is één engine (poc-machine-law); daarom is er één generieke
    tool `execute_law`. Welke regel je uitvoert kies je via de parameter
    `law` — niet via aparte tools per wet (PDR-007-addendum / PDR-008).
    """
    return [
        Tool(
            name="execute_law",
            description=(
                "Voer een RegelRecht-regel (wet) uit via de poc-machine-law "
                "engine en krijg een juridisch onderbouwd oordeel terug. Dit is "
                "de ENIGE RegelRecht-tool: kies de regel via de parameter "
                "'law'.\n\n"
                "Beschikbare regels in deze demo:\n"
                "• 'omgevingswet/energiebesparing/informatieplicht' — bepaalt of "
                "de energiebesparings-/informatieplicht geldt. parameters: "
                '{"KVK_NUMMER": "<8 cijfers>"}. Geef verbruik en woonfunctie mee '
                'via overrides: {"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": '
                '<kWh>, "JAARLIJKS_GASVERBRUIK_M3": <m3>, "IS_WOONFUNCTIE": '
                "<true/false>}}. De geldende drempelwaarden komen uit de regel "
                "zelf en staan in het resultaat (veld drempelwaarden).\n"
                "• 'omgevingswet/energiebesparing/maatregelen' — bepaalt welke "
                "erkende maatregelen gelden, en uit welke bijlage van de "
                "Omgevingsregeling die komen. De host draait deze regel zelf "
                "zodra de energiebesparingsplicht geldt; roep hem niet uit "
                "eigen beweging aan. Ontbreekt er nog een gegeven, dan staat dat "
                "in 'ontbrekende_gegevens' en vertelt de STATUS VAN DE REGELTOETS "
                "wat u de ondernemer moet vragen.\n\n"
                "Parameternamen volgen de engine-conventie (HOOFDLETTERS). Geef "
                "regel-parameters in 'parameters'; gegevens die de engine "
                "normaliter zelf ophaalt (zoals verbruik) geef je in 'overrides' "
                "onder de juiste service."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "law": {
                        "type": "string",
                        "description": (
                            "Pad van de uit te voeren regel, bv. "
                            "'omgevingswet/energiebesparing/informatieplicht' of "
                            "'omgevingswet/energiebesparing/maatregelen'."
                        ),
                    },
                    "parameters": {
                        "type": "object",
                        "description": (
                            "Regel-parameters (engine-namen, HOOFDLETTERS). Een "
                            "aanroep met een leeg object laat de regel zelf "
                            "melden wat hij nodig heeft."
                        ),
                        "additionalProperties": True,
                    },
                    "overrides": {
                        "type": "object",
                        "description": (
                            "Optionele overrides per service, bv. "
                            '{"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": '
                            "61250}}."
                        ),
                        "additionalProperties": True,
                    },
                    "service": {
                        "type": "string",
                        "description": "Service waaronder de regel valt. Standaard 'RVO'.",
                    },
                },
                "required": ["law"],
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
    if name == "execute_law":
        data = await _execute_law(arguments)
        _audit_log("execute_law", arguments, data)
        return [TextContent(type="text", text=_wrap_provenance(data))]

    raise ValueError(f"Onbekende tool: {name}")


async def _execute_law(arguments: dict) -> dict:
    """Voer de gevraagde regel uit via de engine.

    Eén tool voor het LLM, terwijl alle regelkennis in de engine zit. Elke regel
    loopt langs dezelfde weg: geen enkele wordt hier lokaal nagebootst.
    """
    law = str(arguments.get("law", "")).strip()
    if not law:
        return {
            "error": "ONTBREKEND_VELD",
            # `velden` apart van `message`: de host bouwt daar een
            # gebruikersmelding mee (zie services/host/errors.py).
            "velden": ["law"],
            "message": "Parameter 'law' is verplicht.",
        }

    parameters = arguments.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    service = str(arguments.get("service") or "RVO")
    overrides = arguments.get("overrides")
    overrides = overrides if isinstance(overrides, dict) else {}
    return await _engine_execute(service, law, parameters, overrides)


async def _engine_execute(
    service: str, law: str, parameters: dict, overrides: dict
) -> dict:
    """Generieke uitvoering van een regel via de engine, met nette foutmeldingen."""
    rpc_arguments = {"service": service, "law": law, "parameters": parameters}
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
    structured = (result or {}).get("structuredContent", {})
    if not structured:
        # Fallback: geef de ruwe tekst terug
        content = (result or {}).get("content", [])
        text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        return {"resultaat": text}

    definities = await _definities_voor(law, service)
    data = _simplify_result(structured, definities, law)
    return data


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

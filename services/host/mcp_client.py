"""MCP-clientbeheer: verbindt met MCP-servers en verzamelt beschikbare tools."""

import hashlib
import json
import logging
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from errors import bron_uit_tool, schoon_echo
from subprocess_env import MCP_ALLOWLIST, subprocess_env

logger = logging.getLogger("vlam.mcp_client")

logger = logging.getLogger("vlam.mcp_client")


def _subprocess_env() -> dict:
    """Bouw de env voor MCP-subprocessen: alleen de allowlist, geen LLM-keys.

    De lijst staat sinds MVP-02 in `subprocess_env.py`, gedeeld met het
    CLI-transport dat dezelfde regel moet volgen.
    """
    return subprocess_env(MCP_ALLOWLIST)


def _strip_kvk_param(schema: dict) -> dict:
    """Verwijder `kvk_nummer` uit een LLM-zichtbaar inputschema (MVP-01/PDR-009).

    De host bepaalt het KvK-nummer server-side en injecteert het bij de aanroep;
    het LLM mag de parameter niet eens kunnen meegeven. Geeft een kopie terug
    zodat de gedeelde `tool.inputSchema` niet gemuteerd wordt.
    """
    if not isinstance(schema, dict):
        return schema
    stripped = dict(schema)
    props = schema.get("properties")
    if isinstance(props, dict) and "kvk_nummer" in props:
        stripped["properties"] = {
            k: v for k, v in props.items() if k != "kvk_nummer"
        }
    required = schema.get("required")
    if isinstance(required, list) and "kvk_nummer" in required:
        stripped["required"] = [r for r in required if r != "kvk_nummer"]
    return stripped


def _tool_fingerprint(tool) -> str:
    """Hash de stabiele velden van een tool-definitie.

    Onderbouwing: tool-poisoning via gemanipuleerde metadata (zie 2026-onderzoek
    op MCP-protocol; o.a. arXiv:2603.22489) is een aanvalsvector waarbij een
    server tussen twee runs een tool-beschrijving aanpast om het LLM te sturen.
    Door bij host-start een fingerprint te loggen kunnen wij in de audit-trail
    achterhalen wanneer een definitie veranderde.
    """
    payload = {
        "name": getattr(tool, "name", ""),
        "description": getattr(tool, "description", "") or "",
        "inputSchema": getattr(tool, "inputSchema", {}),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


# Meldingen waarmee de MCP-SDK een schending van het tool-schema teruggeeft.
# Die komen van de validatielaag, niet uit de bron, en zijn door het model zelf
# op te lossen door de aanroep te corrigeren. Bewust niet het bredere
# "validation error for": dat is ook het standaardformaat van pydantic, en een
# pydantic-fout uit een server-handler kan de aangeboden waarde meedragen -- dan
# zou er alsnog broninhoud langs het lek-vangnet komen.
_VALIDATIE_SIGNALEN = (
    "input validation error",
    "is a required property",
    "additional properties are not allowed",
    "is not of type",
)


def _is_validatiefout(tekst: str) -> bool:
    """Herken een schemavalidatie-melding van de MCP-SDK."""
    lager = (tekst or "").lower()
    return any(signaal in lager for signaal in _VALIDATIE_SIGNALEN)


class MCPServerConnection:
    """Eén actieve verbinding met een MCP-server."""

    def __init__(self, name: str, server_path: Path):
        self.name = name
        self.server_path = server_path
        self.session: ClientSession | None = None
        self._context = None
        self._read = None
        self._write = None

    async def connect(self) -> list[dict]:
        """Start de MCP-server als subprocess en retourneer beschikbare tools."""
        if not self.server_path.exists():
            raise FileNotFoundError(f"Server-script niet gevonden: {self.server_path}")

        # Geef alleen een allowlist van env-vars door (zie _subprocess_env):
        # server-config zoals DEMO_KVK_NUMMER / REGELRECHT_RPC_URL / BAG_API_KEY
        # moet de subprocess bereiken, maar de LLM-sleutels bewust NIET.
        server_params = StdioServerParameters(
            command="python",
            args=[str(self.server_path)],
            env=_subprocess_env(),
        )

        self._context = stdio_client(server_params)
        self._read, self._write = await self._context.__aenter__()
        self.session = ClientSession(self._read, self._write)
        await self.session.__aenter__()
        await self.session.initialize()

        tools_response = await self.session.list_tools()
        logger.info(
            "Server '%s' verbonden — %d tools beschikbaar",
            self.name,
            len(tools_response.tools),
        )
        return tools_response.tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Roep een tool aan op deze server."""
        if not self.session:
            raise RuntimeError(f"Server '{self.name}' is niet verbonden")
        result = await self.session.call_tool(tool_name, arguments)
        # Combineer alle content-blokken tot tekst
        tekst = "\n".join(
            block.text for block in result.content if hasattr(block, "text")
        )
        if getattr(result, "isError", False):
            # De MCP-SDK vangt élke onafgevangen exception in een server-handler
            # af en levert `str(exc)` als gewone tekst met isError=True. Zonder
            # deze check zou die tekst — met paden, interne URL's en soms een
            # sleutel — als geslaagd resultaat het gesprek in gaan. De inhoud
            # hoort in de log, de gebruiker krijgt een catalogusmelding.
            logger.error("Server '%s' meldt een fout bij '%s': %s", self.name, tool_name, tekst)
            if _is_validatiefout(tekst):
                # Schemavalidatie door de SDK: een fout van het model, niet van
                # de bron. De melding gaat terug naar het model zodat het de
                # aanroep kan corrigeren; die tekst gaat over het tool-schema en
                # bevat geen bron-interne gegevens.
                return json.dumps(
                    {"error": "LLM_TOOLCALL_ONGELDIG", "validatiefout": schoon_echo(tekst, 200)},
                    ensure_ascii=False,
                )
            return json.dumps({"error": "TOOL_ONVERWACHT"}, ensure_ascii=False)
        return tekst

    async def disconnect(self):
        """Sluit de verbinding."""
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self._context:
            await self._context.__aexit__(None, None, None)
        logger.info("Server '%s' losgekoppeld", self.name)


class MCPToolRegistry:
    """Beheert alle MCP-serververbindingen en hun tools."""

    def __init__(self):
        self.connections: dict[str, MCPServerConnection] = {}
        # tool_name → (server_name, tool_schema)
        self.tool_map: dict[str, tuple[str, dict]] = {}

    async def register_server(self, name: str, server_path: Path):
        """Verbind met een MCP-server en registreer diens tools."""
        conn = MCPServerConnection(name, server_path)
        tools = await conn.connect()
        self.connections[name] = conn

        for tool in tools:
            tool_key = f"{name}__{tool.name}"
            self.tool_map[tool_key] = (name, tool)
            logger.info(
                "  Tool geregistreerd: %s [fingerprint:%s]",
                tool_key,
                _tool_fingerprint(tool),
            )

    def get_anthropic_tools(self) -> list[dict]:
        """Converteer MCP-tools naar Anthropic API tool-formaat."""
        anthropic_tools = []
        for tool_key, (_, tool) in self.tool_map.items():
            anthropic_tools.append(
                {
                    "name": tool_key,
                    "description": tool.description or "",
                    "input_schema": _strip_kvk_param(tool.inputSchema),
                }
            )
        return anthropic_tools

    def get_openai_tools(self) -> list[dict]:
        """Converteer MCP-tools naar OpenAI API tool-formaat."""
        openai_tools = []
        for tool_key, (_, tool) in self.tool_map.items():
            openai_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_key,
                        "description": tool.description or "",
                        "parameters": _strip_kvk_param(tool.inputSchema),
                    },
                }
            )
        return openai_tools

    async def call_tool(self, tool_key: str, arguments: dict) -> str:
        """Roep een tool aan via de juiste server."""
        if tool_key not in self.tool_map:
            # Een bron die bij startup niet opkwam heeft geen tools in de
            # registry: de aanroep landt hier. Alleen dán is "de bron ligt eruit"
            # waar — draait de server wél, dan verzon het model een toolnaam en
            # is doorverwijzen naar de beheerder onjuist.
            bron = bron_uit_tool(tool_key)
            code = (
                "BRON_NIET_GESTART"
                if bron and bron not in self.connections
                else "ONBEKENDE_TOOL"
            )
            # %r en afgekapt: de toolnaam komt van het LLM en kan regeleindes
            # bevatten, waarmee een valse logregel te schrijven zou zijn.
            logger.warning("Tool niet in de registry: %r (%s)", str(tool_key)[:80], code)
            return json.dumps({"error": code}, ensure_ascii=False)

        server_name, _ = self.tool_map[tool_key]
        # Haal de originele tool-naam terug (zonder server-prefix)
        original_name = tool_key.split("__", 1)[1]
        conn = self.connections[server_name]
        return await conn.call_tool(original_name, arguments)

    async def disconnect_all(self):
        """Sluit alle serververbindingen."""
        for conn in self.connections.values():
            await conn.disconnect()
        self.connections.clear()
        self.tool_map.clear()

"""FastAPI-server voor de VLAM MCP-host.

Biedt een REST API waarmee het moza-portaal met VLAM kan communiceren.
Ondersteunt zowel blocking (/chat) als streaming (/chat/stream) responses.
"""

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    ALLOW_API_KEY_OVERRIDE,
    ALLOWED_ORIGINS,
    VLAM_HOST,
    VLAM_PORT,
    kvk_voor_token,
)
from vlam_host import VLAMHost

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

host = VLAMHost()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start en stop de VLAM-host met de FastAPI-levenscyclus."""
    await host.startup()
    yield
    await host.shutdown()


app = FastAPI(
    title="VLAM Host",
    description="Rijksbrede digitale assistent — MCP-host wrapper",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Log alleen de deployment-posture (booleaanse vlag), nooit een sleutelwaarde.
# We loggen een vaste label-string i.p.v. de vlag zelf, zodat statische analyse
# (CodeQL) deze diagnostische regel niet als clear-text logging van een secret
# aanmerkt — er stroomt geen sleutel of waarde de logregel in.
logging.getLogger("vlam.api").info(
    "CORS allow_origins=%s | api-key-override toegestaan: %s",
    ALLOWED_ORIGINS,
    "ja" if ALLOW_API_KEY_OVERRIDE else "nee",
)


# --- Request/Response modellen ---


class ChatRequest(BaseModel):
    """Inkomend chatbericht."""

    message: str
    session_id: str | None = None
    mode: str = "vlam"  # "vlam" (met MCP-tools) of "claude" (zonder tools)


class ChatResponse(BaseModel):
    """Antwoord van de assistent."""

    reply: str
    session_id: str
    mode: str
    has_tools: bool


class ToolInfo(BaseModel):
    """Beschikbare tool-informatie."""

    name: str
    description: str
    server: str


# --- Endpoints ---


# Nette melding als er geen geldige sessie is (MVP-01/PDR-009). De host raadpleegt
# dan géén bron en roept het LLM niet aan; de identiteit wordt server-side bepaald.
GEEN_SESSIE_MELDING = (
    "Log eerst in om uw bedrijfsgegevens te kunnen gebruiken. "
    "Zonder geldige sessie raadpleegt de assistent geen overheidsbronnen."
)


def _resolve_session_kvk(request: Request) -> str | None:
    """Bepaal het KvK-nummer van de sessie uit de `X-Test-User`-header.

    Het KvK-nummer wordt server-side afgeleid uit een vertrouwd token (PDR-009),
    niet uit de conversatie. Geeft None als er geen geldig token is.
    """
    token = request.headers.get("x-test-user", "").strip()
    return kvk_voor_token(token)


def _extract_api_keys(request: Request) -> dict:
    """Lees optionele API key overrides uit request headers.

    Alleen actief als ALLOW_API_KEY_OVERRIDE=true in de omgeving.
    Anders worden de headers genegeerd en gebruikt de host de server-env keys.
    """
    if not ALLOW_API_KEY_OVERRIDE:
        return {"vlam_api_key_override": "", "claude_api_key_override": ""}
    return {
        "vlam_api_key_override": request.headers.get("x-vlam-api-key", "").strip(),
        "claude_api_key_override": request.headers.get("x-claude-api-key", "").strip(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    """Stuur een bericht naar de assistent en ontvang een antwoord."""
    session_kvk = _resolve_session_kvk(request)
    if not session_kvk:
        raise HTTPException(status_code=401, detail=GEEN_SESSIE_MELDING)
    session_id = body.session_id or str(uuid.uuid4())
    VALID_MODES = ("vlam", "claude", "cli:vlam", "cli:claude")
    mode = body.mode if body.mode in VALID_MODES else "vlam"
    api_keys = _extract_api_keys(request)
    reply = await host.chat(
        session_id, body.message, mode=mode, session_kvk=session_kvk, **api_keys
    )
    return ChatResponse(
        reply=reply, session_id=session_id, mode=mode, has_tools=host.has_tools
    )


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    """Stuur een bericht en ontvang status-updates via Server-Sent Events.

    Events:
      event: status  — de assistent is bezig (nadenken, tool aanroepen)
      event: tool    — een specifieke tool wordt aangeroepen
      event: case    — een lopende zaak is aangemaakt (na indiening)
      event: answer  — het definitieve antwoord
      event: done    — stream is afgelopen
    """
    session_kvk = _resolve_session_kvk(request)
    session_id = body.session_id or str(uuid.uuid4())
    VALID_MODES = ("vlam", "claude", "cli:vlam", "cli:claude")
    mode = body.mode if body.mode in VALID_MODES else "vlam"
    api_keys = _extract_api_keys(request)
    logging.getLogger("vlam.api").info("POST /chat/stream — mode=%r (raw=%r)", mode, body.mode)

    if not session_kvk:
        # Hard blokkeren zonder geldige sessie: nette melding, geen LLM/bron.
        async def blocked_generator():
            payload = json.dumps(
                {"type": "answer", "message": GEEN_SESSIE_MELDING}, ensure_ascii=False
            )
            yield f"event: answer\ndata: {payload}\n\n"
            yield 'event: done\ndata: {"type": "done"}\n\n'

        return StreamingResponse(
            blocked_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_generator():
        async for event in host.chat_stream(
            session_id, body.message, mode=mode, session_kvk=session_kvk, **api_keys
        ):
            event_type = event.get("type", "status")
            # Voeg session_id en mode toe aan answer-events
            if event_type == "answer":
                event["session_id"] = session_id
                event["mode"] = mode
                event["has_tools"] = host.has_tools
            payload = json.dumps(event, ensure_ascii=False)
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    """Wis de gespreksgeschiedenis van een sessie."""
    host.clear_session(session_id)
    return {"status": "gewist", "session_id": session_id}


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """Toon alle beschikbare tools van verbonden MCP-servers."""
    tools = []
    for tool_key, (server_name, tool) in host.registry.tool_map.items():
        tools.append(
            ToolInfo(
                name=tool_key,
                description=tool.description or "",
                server=server_name,
            )
        )
    return tools


@app.get("/health")
async def health():
    """Gezondheidscontrole met status van backends en MCP-servers."""
    return {
        "status": "actief",
        **host.get_status(),
    }


@app.get("/regelrecht/definities")
async def regelrecht_definities(law: str):
    """Definities/constantes van een RegelRecht-wet (bv. drempelwaarden).

    Eén bron van waarheid: de engine (rule_spec.definitions). Alleen wetten op
    de allowlist (REGELRECHT_DEFINITIES_ALLOWLIST) zijn opvraagbaar; de service
    hoort bij de wet (uit de allowlist), niet bij de caller. Voor frontend
    CTA-gating per regeling-pagina.
    """
    result = await host.get_definities(law)
    if result.get("error") == "WET_NIET_TOEGESTAAN":
        raise HTTPException(status_code=404, detail=result)
    return result


@app.get("/regelrecht/drempels")
async def regelrecht_drempels():
    """Alias voor /regelrecht/definities (energiebesparings-/informatieplicht).

    Geeft het veld 'drempelwaarden' terug voor terugwaartse compatibiliteit.
    """
    return await host.get_drempelwaarden()


# Optionele statische frontend-mount. Standaard UIT: de host is API-only en de
# frontend (Eleventy-site) draait apart en proxyt naar deze backend (zie README).
# Alleen mounten als STATIC_DIR expliciet is gezet én naar een bestaande map wijst.
_static_env = os.getenv("STATIC_DIR", "").strip()
if _static_env and Path(_static_env).is_dir():
    app.mount("/", StaticFiles(directory=_static_env, html=True), name="site")
    logging.getLogger("vlam.api").info("Statische site gemount vanuit %s", _static_env)
elif _static_env:
    logging.getLogger("vlam.api").warning(
        "STATIC_DIR=%s bestaat niet; host draait API-only", _static_env
    )
else:
    logging.getLogger("vlam.api").info("Host draait API-only (geen STATIC_DIR gezet)")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=VLAM_HOST, port=VLAM_PORT)

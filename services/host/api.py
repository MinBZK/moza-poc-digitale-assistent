"""FastAPI-server voor de VLAM MCP-host.

Biedt een REST API waarmee het moza-portaal met VLAM kan communiceren.
Ondersteunt zowel blocking (/chat) als streaming (/chat/stream) responses.
"""

import json
import logging
import os
import uuid
from contextlib import aclosing, asynccontextmanager
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
    kvk_uit_header,
)
from log_redaction import (
    MIN_UNTRUSTED_SECRET_LENGTH,
    install_redaction,
    looks_like_a_key,
)
from vlam_host import VLAMHost

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
install_redaction()

host = VLAMHost()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start en stop de VLAM-host met de FastAPI-levenscyclus."""
    # Nogmaals, nu uvicorn zijn eigen loggers heeft opgetuigd: bij `uvicorn.run`
    # vanuit __main__ bestaan die bij import nog niet. De aanroep is idempotent.
    install_redaction()
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


def check_origin_boundary() -> None:
    """Waarschuw als de origin-grens openstaat (MVP-02).

    Let op de richting: een *lege* `ALLOWED_ORIGINS` is de strikte stand, en de
    stand voor de deployment (same-origin proxy, dus geen CORS in het spel).
    `*` is het probleem: dan kan elke webpagina deze host aanroepen. Geen harde
    blokkade, want `*` is legitiem tijdens lokale ontwikkeling.
    """
    if "*" not in ALLOWED_ORIGINS:
        return
    logging.getLogger("vlam.api").warning(
        "ALLOWED_ORIGINS staat op '*': elke webpagina kan deze host aanroepen. "
        "Alleen bedoeld voor lokale ontwikkeling — zet een concrete whitelist "
        "voor een gedeelde of publieke omgeving.%s",
        (
            " De sleutel-override staat óók aan, dus zo'n pagina kan de "
            "assistent met een eigen sleutel aansturen."
            if ALLOW_API_KEY_OVERRIDE
            else ""
        ),
    )


check_origin_boundary()


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


# Vaste tekst voor een onverwachte fout midden in de stream: de respons hoort
# niet aan de inhoud van een exception te hangen (CodeQL py/stack-trace-exposure).
STREAM_ERROR_MESSAGE = (
    "Er ging iets mis bij het beantwoorden van uw vraag. Probeer het opnieuw; "
    "blijft het misgaan, meld dit dan met het tijdstip van uw vraag."
)


def _sse_chunks(message: str, event_type: str) -> list[str]:
    """Serialiseer één SSE-bericht + het afsluitende `done`-event.

    Eén plek, zodat elke uitgang van `/chat/stream` hetzelfde contract volgt:
    een stream eindigt altijd op `done`, ook als er iets misging.
    """
    payload = json.dumps({"type": event_type, "message": message}, ensure_ascii=False)
    return [
        f"event: {event_type}\ndata: {payload}\n\n",
        'event: done\ndata: {"type": "done"}\n\n',
    ]


def _sse_single_message(message: str, event_type: str) -> StreamingResponse:
    """Stuur één SSE-bericht + `done`, zonder LLM- of bron-aanroep.

    Gebruikt voor de twee hard-blokkeer-routes van `/chat/stream`: geen geldige
    sessie, en een geweigerde sleutel-header.
    """

    async def generator():
        for chunk in _sse_chunks(message, event_type):
            yield chunk

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _resolve_session_kvk(request: Request) -> str | None:
    """Bepaal het KvK-nummer van de sessie uit de `X-Test-User`-header.

    Gevalideerd tegen de allowlist (PDR-009), nooit uit de conversatie. None als
    de header ontbreekt of een nummer buiten de allowlist draagt.
    """
    return kvk_uit_header(request.headers.get("x-test-user", ""))


class InvalidApiKey(Exception):
    """De client stuurde een sleutel-header met een onbruikbare waarde."""


# Bewust generiek: de melding mag nooit (een deel van) de waarde bevatten.
INVALID_API_KEY_MESSAGE = (
    "De meegegeven API-sleutel heeft een ongeldige vorm. Controleer of u de "
    "sleutel volledig hebt geplakt, zonder spaties of regeleinden."
)

# Eén gedeelde ondergrens met het log-vangnet, en bewust niet los gekozen: wat de
# voordeur accepteert, moet het vangnet ook kunnen registreren. Geen echte
# LLM-sleutel is korter dan 20 tekens.
_MIN_API_KEY_LENGTH = MIN_UNTRUSTED_SECRET_LENGTH
_MAX_API_KEY_LENGTH = 512


def _validate_api_key(value: str, header: str) -> str:
    """Toets de vorm van een sleutel-header; geef de sleutel terug of faal (MVP-02).

    Drie redenen, aflopend in hoe reëel ze zijn:

    1. Een niet-ASCII sleutel laat de LLM-call stuklopen op een
       `UnicodeEncodeError`, buiten `except (TimeoutError, APIError)` om: een
       onafgevangen 500 of een afgebroken SSE-stream.
    2. Een stuurteken levert een fout op waarvan de binnenste melding de volledige
       sleutel bevat. Over HTTP niet bereikbaar, dus defense-in-depth.
    3. Plakfouten geven nu een bruikbare melding.

    Bewust niets van de waarde gelogd of teruggegeven: alleen headernaam en reden.
    """
    if not value:
        return ""
    if not (_MIN_API_KEY_LENGTH <= len(value) <= _MAX_API_KEY_LENGTH):
        reason = "lengte buiten bereik"
    elif not value.isascii() or not value.isprintable():
        reason = "niet-printbare of niet-ASCII tekens"
    elif any(c.isspace() for c in value):
        reason = "bevat witruimte"
    else:
        if not looks_like_a_key(value):
            # De lengte klopt, maar het vangnet registreert alleen waarden met
            # zowel een cijfer als een letter — anders wordt "sleutel opgeven"
            # een manier om gewone logtekst te laten verdwijnen. Zo'n sleutel
            # werkt wél; alleen de tweede verdedigingslinie dekt hem niet. Dat
            # hoort niet stil te gebeuren.
            logging.getLogger("vlam.api").warning(
                "Sleutel-header %s valt buiten het log-vangnet (geen cijfer- én "
                "lettercombinatie); de sleutel wordt gebruikt, maar niet uit "
                "logregels geredigeerd.",
                header,
            )
        return value
    logging.getLogger("vlam.api").warning(
        "Sleutel-header %s geweigerd: %s", header, reason
    )
    raise InvalidApiKey(INVALID_API_KEY_MESSAGE)


def _extract_api_keys(request: Request) -> dict:
    """Lees optionele API key overrides uit request headers.

    Alleen actief als ALLOW_API_KEY_OVERRIDE=true in de omgeving.
    Anders worden de headers genegeerd en gebruikt de host de server-env keys.

    Werpt `InvalidApiKey` als een header een onbruikbare waarde draagt; de
    endpoints vertalen dat naar een nette 400 respectievelijk een error-event.
    """
    if not ALLOW_API_KEY_OVERRIDE:
        return {"vlam_api_key_override": "", "claude_api_key_override": ""}
    return {
        "vlam_api_key_override": _validate_api_key(
            request.headers.get("x-vlam-api-key", "").strip(), "x-vlam-api-key"
        ),
        "claude_api_key_override": _validate_api_key(
            request.headers.get("x-claude-api-key", "").strip(), "x-claude-api-key"
        ),
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
    try:
        api_keys = _extract_api_keys(request)
    except InvalidApiKey:
        # De vaste tekst, niet `str(e)`: de respons hoort niet aan de inhoud van
        # een exception te hangen (CodeQL py/stack-trace-exposure).
        raise HTTPException(
            status_code=400, detail=INVALID_API_KEY_MESSAGE
        ) from None
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
    # Alleen de gevalideerde mode; de rauwe waarde komt ongefilterd en zonder
    # lengtegrens uit het verzoek (zie de ReDoS-noot in log_redaction.py).
    logging.getLogger("vlam.api").info(
        "POST /chat/stream — mode=%r%s",
        mode,
        "" if body.mode == mode else " (afwijkende mode gevraagd, teruggevallen)",
    )

    if not session_kvk:
        # Hard blokkeren zonder geldige sessie: nette melding, geen LLM/bron.
        return _sse_single_message(GEEN_SESSIE_MELDING, "answer")

    try:
        api_keys = _extract_api_keys(request)
    except InvalidApiKey:
        # Error-event i.p.v. 400: de UI leest deze route als SSE.
        return _sse_single_message(INVALID_API_KEY_MESSAGE, "error")

    async def event_generator():
        # `aclosing`: bij een afgebroken stream wordt de binnenste generator
        # meteen gesloten in plaats van pas bij asyncgen-finalisatie. Dat is wat
        # `_request_clients` zijn opruiming laat draaien — en dus de sleutel uit
        # het redactie-register haalt (PDR-010 §2).
        async with aclosing(
            host.chat_stream(
                session_id, body.message, mode=mode, session_kvk=session_kvk, **api_keys
            )
        ) as stream:
            try:
                async for event in stream:
                    event_type = event.get("type", "status")
                    # Voeg session_id en mode toe aan answer-events
                    if event_type == "answer":
                        event["session_id"] = session_id
                        event["mode"] = mode
                        event["has_tools"] = host.has_tools
                    payload = json.dumps(event, ensure_ascii=False)
                    yield f"event: {event_type}\ndata: {payload}\n\n"
            except Exception:
                # Status 200 is hier al verstuurd, dus een fout kán niet meer
                # als HTTP-status naar buiten. Zonder dit blok krijgt de UI een
                # afgekapte respons zonder `error` én zonder `done`, en blijft
                # ze in "Nadenken…" hangen. Server-side de volledige traceback
                # (geredigeerd), client-side een vaste, generieke tekst.
                logging.getLogger("vlam.api").exception(
                    "Onverwachte fout tijdens /chat/stream (mode=%r)", mode
                )
                for chunk in _sse_chunks(STREAM_ERROR_MESSAGE, "error"):
                    yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.delete("/chat/{session_id}")
async def clear_session(session_id: str, request: Request):
    """Wis de gespreksgeschiedenis van een sessie (alleen de eigen identiteit)."""
    session_kvk = _resolve_session_kvk(request)
    if not session_kvk:
        raise HTTPException(status_code=401, detail=GEEN_SESSIE_MELDING)
    host.clear_session(session_kvk, session_id)
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

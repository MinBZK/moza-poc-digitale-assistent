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
    kvk_uit_header,
)
from log_redaction import installeer_redactie
from vlam_host import VLAMHost

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
installeer_redactie()

host = VLAMHost()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start en stop de VLAM-host met de FastAPI-levenscyclus."""
    # Nogmaals, nu uvicorn zijn eigen loggers heeft opgetuigd: bij `uvicorn.run`
    # vanuit __main__ bestaan die bij import nog niet. De aanroep is idempotent.
    installeer_redactie()
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


def controleer_origin_grens() -> None:
    """Waarschuw luid als de origin-grens wagenwijd openstaat (MVP-02).

    Let op de richting: een *lege* `ALLOWED_ORIGINS` is de strikte stand — dan
    staat er geen enkele cross-origin toegang open. Dat is precies goed voor de
    deployment, waar de frontend via een same-origin reverse proxy praat en er
    dus helemaal geen CORS aan te pas komt.

    `*` is het probleem: dan kan elke willekeurige webpagina de browser van een
    bezoeker dit endpoint laten aanroepen. Met de sleutel-override aan telt daar
    bij op dat zo'n pagina de assistent ook met een eigen sleutel kan aansturen.
    Een sleutel van een ánder tabblad kan er niet mee gestolen worden (dat
    verhindert de browser zelf), maar de host wordt wel een open doorgeefluik.

    Bewust geen harde blokkade: `*` is legitiem tijdens lokale ontwikkeling.
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


controleer_origin_grens()


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


def _sse_enkel_bericht(melding: str, event_type: str) -> StreamingResponse:
    """Stuur één SSE-bericht + `done`, zonder LLM- of bron-aanroep.

    Gebruikt voor de twee hard-blokkeer-routes van `/chat/stream`: geen geldige
    sessie, en een geweigerde sleutel-header.
    """

    async def generator():
        payload = json.dumps(
            {"type": event_type, "message": melding}, ensure_ascii=False
        )
        yield f"event: {event_type}\ndata: {payload}\n\n"
        yield 'event: done\ndata: {"type": "done"}\n\n'

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


class OngeldigeSleutel(Exception):
    """De client stuurde een sleutel-header met een onbruikbare waarde."""


# Bewust generiek: de melding mag nooit (een deel van) de waarde bevatten.
ONGELDIGE_SLEUTEL_MELDING = (
    "De meegegeven API-sleutel heeft een ongeldige vorm. Controleer of u de "
    "sleutel volledig hebt geplakt, zonder spaties of regeleinden."
)

_MIN_SLEUTEL_LENGTE = 8
_MAX_SLEUTEL_LENGTE = 512


def _valideer_sleutel(waarde: str, header: str) -> str:
    """Toets de vorm van een sleutel-header; geef de sleutel terug of faal (MVP-02).

    Drie redenen, in volgorde van hoe reëel ze zijn:

    1. Een niet-ASCII sleutel laat de uitgaande LLM-call stuklopen op een
       `UnicodeEncodeError`. Die valt buiten `except (TimeoutError, APIError)`
       en levert dus een onafgevangen 500 of een halverwege afgebroken
       SSE-stream op. De melding bevat de sleutel niet, maar het is een lelijke
       faalmodus die we hier goedkoop voorkomen.
    2. Een sleutel met een stuurteken (bv. een regeleinde) levert bij het
       opbouwen van het verzoek een fout op waarvan de binnenste melding de
       *volledige sleutel* bevat ("Illegal header value b'sk-ant-...'"). Over
       normale HTTP kan zo'n waarde ons niet bereiken — clients en servers
       weigeren stuurtekens in header-waarden — dus dit is defense-in-depth
       voor het geval de waarde ooit uit een andere bron komt.
    3. Plakfouten (spatie erin, half gekopieerd) geven nu een duidelijke melding
       in plaats van het generieke "de assistent is niet bereikbaar".

    Er wordt bewust niets van de waarde gelogd of teruggegeven — alleen de
    headernaam en de reden-categorie.
    """
    if not waarde:
        return ""
    if not (_MIN_SLEUTEL_LENGTE <= len(waarde) <= _MAX_SLEUTEL_LENGTE):
        reden = "lengte buiten bereik"
    elif not waarde.isascii() or not waarde.isprintable():
        reden = "niet-printbare of niet-ASCII tekens"
    elif any(c.isspace() for c in waarde):
        reden = "bevat witruimte"
    else:
        return waarde
    logging.getLogger("vlam.api").warning(
        "Sleutel-header %s geweigerd: %s", header, reden
    )
    raise OngeldigeSleutel(ONGELDIGE_SLEUTEL_MELDING)


def _extract_api_keys(request: Request) -> dict:
    """Lees optionele API key overrides uit request headers.

    Alleen actief als ALLOW_API_KEY_OVERRIDE=true in de omgeving.
    Anders worden de headers genegeerd en gebruikt de host de server-env keys.

    Werpt `OngeldigeSleutel` als een header een onbruikbare waarde draagt; de
    endpoints vertalen dat naar een nette 400 respectievelijk een error-event.
    """
    if not ALLOW_API_KEY_OVERRIDE:
        return {"vlam_api_key_override": "", "claude_api_key_override": ""}
    return {
        "vlam_api_key_override": _valideer_sleutel(
            request.headers.get("x-vlam-api-key", "").strip(), "x-vlam-api-key"
        ),
        "claude_api_key_override": _valideer_sleutel(
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
    except OngeldigeSleutel:
        # Bewust de vaste tekst en niet `str(e)`: de respons hoort niet aan de
        # inhoud van een exception te hangen (CodeQL py/stack-trace-exposure).
        # Vandaag is die inhoud onze eigen generieke melding, maar dat breekt
        # zodra iemand deze exception ergens anders met andere tekst opwerpt.
        # De reden staat al server-side in de log, met de headernaam erbij.
        raise HTTPException(
            status_code=400, detail=ONGELDIGE_SLEUTEL_MELDING
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
    # Log de gevalideerde mode, en van de rauwe waarde alleen of die afweek —
    # niet de waarde zelf. Die komt ongefilterd uit het verzoek en had geen
    # lengtegrens: een `mode` van 64 KB hield de logverwerking tientallen
    # seconden bezig en daarmee de hele event loop (zie log_redaction.py).
    logging.getLogger("vlam.api").info(
        "POST /chat/stream — mode=%r%s",
        mode,
        "" if body.mode == mode else " (afwijkende mode gevraagd, teruggevallen)",
    )

    if not session_kvk:
        # Hard blokkeren zonder geldige sessie: nette melding, geen LLM/bron.
        return _sse_enkel_bericht(GEEN_SESSIE_MELDING, "answer")

    try:
        api_keys = _extract_api_keys(request)
    except OngeldigeSleutel:
        # Geen 400 maar een error-event: de UI leest deze route als SSE.
        # En de vaste tekst i.p.v. `str(e)`, om dezelfde reden als bij /chat.
        return _sse_enkel_bericht(ONGELDIGE_SLEUTEL_MELDING, "error")

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

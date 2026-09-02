"""FastAPI-server voor de VLAM MCP-host.

Biedt een REST API waarmee het moza-portaal met VLAM kan communiceren.
Ondersteunt zowel blocking (/chat) als streaming (/chat/stream) responses.
"""

import json
import logging
import os
import time
import uuid
from contextlib import aclosing, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    ALLOW_API_KEY_OVERRIDE,
    ALLOWED_ORIGINS,
    MAX_VRAAG_TEKENS,
    TEST_KVK_NUMMERS,
    VLAM_HOST,
    VLAM_PORT,
    kvk_uit_header,
)
from errors import FoutMelding, maak_fout, naar_event
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


@app.middleware("http")
async def vang_onverwachte_fouten(request: Request, call_next):
    """Vang alles wat nergens anders is afgevangen.

    Zonder dit vangnet geeft FastAPI `{"detail": "Internal Server Error"}` terug:
    Engels, zonder code en zonder handelingsperspectief — precies de melding waar
    dit project vanaf wilde. De exception zelf gaat naar de log, niet naar de
    client (CodeQL `py/stack-trace-exposure`).

    Bewust een middleware en geen `exception_handler`: die laatste draait in
    Starlette's `ServerErrorMiddleware`, buiten `CORSMiddleware`, waardoor de
    foutrespons geen CORS-headers krijgt en een browser de melding niet mág
    lezen. Even bewust staat deze registratie vóór die van `CORSMiddleware`:
    Starlette zet de laatst geregistreerde middleware bovenaan, dus alleen zo
    komt dit vangnet binnen de CORS-laag te staan en krijgt de foutrespons de
    headers die de browser nodig heeft.
    """
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 — vangnet, de melding is generiek
        # Type erbij: de melding stuurt de gebruiker naar de beheerder, dus die
        # heeft iets nodig om mee te beginnen. Bewust geen volledige traceback:
        # die kan een sleutel meedragen en het redactie-vangnet uit PR #44 is
        # nog niet gemerged (zie NEXT_STEPS, MVP-02).
        logging.getLogger("vlam.api").error(
            "Onafgevangen fout op %s [%s]: %s", request.url.path, type(exc).__name__, exc
        )
        fout = maak_fout("HOST_FOUT")
        return JSONResponse(status_code=fout.http_status, content=naar_event(fout))


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


@app.exception_handler(RequestValidationError)
async def ongeldige_aanvraag(request: Request, exc: RequestValidationError):
    """Een verzoek dat niet aan het model voldoet (bv. `message` ontbreekt).

    FastAPI geeft hier standaard een Engelse lijst pydantic-fouten terug; die is
    voor een gebruiker onleesbaar en voor de frontend niets waard. De 422-status
    blijft staan: dat is de afgesproken semantiek voor een verzoek dat niet aan
    het model voldoet, en clients rekenen erop. Alleen de body verandert.
    """
    fout = maak_fout("LEGE_VRAAG" if _mist_bericht(exc) else "AANVRAAG_ONGELDIG")
    return JSONResponse(status_code=422, content=naar_event(fout))


def _mist_bericht(exc: RequestValidationError) -> bool:
    """Ontbrak het veld `message`, of was het leeg?

    Alleen dán is "typ uw vraag" het juiste advies. Een verkeerd type (bv. een
    getal) is een fout in de aanroepende software; die krijgt de neutrale
    melding, anders krijgt de gebruiker de schuld van een bug.
    """
    return any(
        "message" in (fout.get("loc") or ())
        and (fout.get("type") == "missing" or fout.get("input") is None)
        for fout in exc.errors()
    )


# --- Request/Response modellen ---


class ChatRequest(BaseModel):
    """Inkomend chatbericht."""

    message: str
    session_id: str | None = None
    mode: str = "vlam"  # "vlam" (met MCP-tools) of "claude" (zonder tools)
    # Toestemming voor de Business Wallet (PDR-008), expliciet door de
    # frontend gestuurd (de "Delen"-knop). `None`/`False` betekent hier "nog
    # niet gegeven in dit verzoek", niet "ingetrokken" - eenmaal gegeven blijft
    # gegeven voor de rest van de sessie (VLAMHost.toestemming).
    toestemming: bool | None = None
    # Formulierantwoorden van de ondernemer (radioknoppen), gestructureerd door
    # de frontend in plaats van platgeslagen tot een zin die het model weer
    # moet interpreteren. De host filtert op wat de routeringstabel kent.
    opgaven: dict[str, object] | None = None


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


# Zonder geldige sessie (MVP-01/PDR-009) raadpleegt de host géén bron en roept
# hij het LLM niet aan; de identiteit wordt server-side bepaald. De melding komt
# uit de foutcatalogus, zodat er één plek is waar teksten staan.


def _geen_sessie_fout():
    """Geen geldige sessie: ligt het aan de gebruiker of aan de configuratie?

    Is `TEST_KVK_NUMMERS` leeg, dan komt niemand er ooit door en is "log eerst
    in" een doodlopend advies: er is in deze PoC geen inlog die dat oplost.
    """
    return maak_fout("GEEN_SESSIE" if TEST_KVK_NUMMERS else "SESSIE_NIET_INGESTELD")


def _controleer_vraag(bericht: str) -> FoutMelding | None:
    """Weiger een lege of buitensporig lange vraag met een concrete melding.

    Zonder deze check gaat een leeg bericht gewoon naar het LLM en komt de
    gebruiker verderop uit bij een vage fout; een bericht zonder bovengrens
    belandt ongelezen in de gespreksgeschiedenis.
    """
    if not (bericht or "").strip():
        return maak_fout("LEGE_VRAAG")
    if len(bericht) > MAX_VRAAG_TEKENS:
        return maak_fout("VRAAG_TE_LANG", maximum=f"{MAX_VRAAG_TEKENS} tekens")
    return None


def _sse_melding(payload: dict) -> StreamingResponse:
    """Stuur één event plus `done` terug, zonder het LLM of een bron te raken."""

    async def generator():
        yield f"event: {payload['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield 'event: done\ndata: {"type": "done"}\n\n'

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
    "De ingevulde toegangssleutel heeft een ongeldige vorm. Controleer bij "
    "Instellingen of u de sleutel volledig hebt geplakt, zonder spaties of "
    "regeleinden."
)

# Eén gedeelde ondergrens met het log-vangnet, en bewust niet los gekozen: wat de
# voordeur accepteert, moet het vangnet ook kunnen registreren. Geen echte
# LLM-sleutel is korter dan 20 tekens.
_MIN_API_KEY_LENGTH = MIN_UNTRUSTED_SECRET_LENGTH
_MAX_API_KEY_LENGTH = 512


# `/chat` heeft (nog) geen authenticatie, dus iedereen die de host bereikt kan
# geweigerde sleutel-headers op verzoeksnelheid produceren — en daarmee de logs
# vollopen (BIO 12.4.1/12.4.2). De weigering blijft zichtbaar, maar hooguit één
# WARNING per venster; de onderdrukte weigeringen worden meegeteld en gemeld,
# zodat een aanhoudende stroom juist opvalt in plaats van te verdrinken.
_KEY_REJECTION_LOG_INTERVAL = 60.0
_key_rejection_state = {"laatste_log": None, "onderdrukt": 0}


def _reset_key_rejection_throttle() -> None:
    """Zet de throttle terug op nul (voor tests en voor `startup`)."""
    _key_rejection_state["laatste_log"] = None
    _key_rejection_state["onderdrukt"] = 0


def _log_key_rejection(header: str, reason: str) -> None:
    """Meld een geweigerde sleutel-header — headernaam en reden, nooit de waarde."""
    nu = time.monotonic()
    laatste = _key_rejection_state["laatste_log"]
    if laatste is not None and nu - laatste < _KEY_REJECTION_LOG_INTERVAL:
        _key_rejection_state["onderdrukt"] += 1
        return
    onderdrukt = _key_rejection_state["onderdrukt"]
    _key_rejection_state["laatste_log"] = nu
    _key_rejection_state["onderdrukt"] = 0
    logging.getLogger("vlam.api").warning(
        "Sleutel-header %s geweigerd: %s%s",
        header,
        reason,
        (
            f" ({onderdrukt} eerdere weigeringen onderdrukt in de afgelopen "
            f"{_KEY_REJECTION_LOG_INTERVAL:.0f}s)"
            if onderdrukt
            else ""
        ),
    )


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
    _log_key_rejection(header, reason)
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


def _fout_respons(fout) -> JSONResponse:
    """Eén vorm voor elke HTTP-foutmelding: het event-object op topniveau.

    Niet via `HTTPException(detail=...)`: dat nest de melding onder `detail`,
    terwijl het vangnet en de validatiehandler 'm op topniveau zetten. Twee
    vormen op dezelfde API dwingt elke client tot twee codepaden.
    """
    return JSONResponse(status_code=fout.http_status, content=naar_event(fout))


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    """Stuur een bericht naar de assistent en ontvang een antwoord."""
    session_kvk = _resolve_session_kvk(request)
    if not session_kvk:
        return _fout_respons(_geen_sessie_fout())
    fout = _controleer_vraag(body.message)
    if fout:
        return _fout_respons(fout)
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
        session_id,
        body.message,
        mode=mode,
        session_kvk=session_kvk,
        toestemming=body.toestemming,
        opgaven=body.opgaven,
        **api_keys,
    )
    return ChatResponse(
        reply=reply, session_id=session_id, mode=mode, has_tools=host.has_tools
    )


@app.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request):
    """Stuur een bericht en ontvang status-updates via Server-Sent Events.

    Events:
      event: status    — de assistent is bezig (nadenken, tool aanroepen)
      event: tool      — een specifieke tool wordt aangeroepen
      event: case      — een lopende zaak is aangemaakt (na indiening)
      event: bron_fout — een bron viel uit; het gesprek loopt door (PDR-011)
      event: answer    — het definitieve antwoord
      event: error     — het gesprek eindigt met een foutmelding (PDR-011)
      event: done      — stream is afgelopen

    `answer` en `error` zijn de twee eindpunten; er komt er altijd precies één,
    gevolgd door `done`. `status`, `tool`, `case` en `bron_fout` zijn tussentijds.
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
        # Blijft een `answer`-event: de frontend toont dat als gewone tekst en
        # niet als storing, want dit is geen fout maar een instructie. Wel in de
        # payload-vorm van het foutcontract, zodat `code` en `herstelbaar`
        # meekomen en de UI er straks op kan sturen.
        return _sse_melding(naar_event(_geen_sessie_fout(), "answer"))

    fout = _controleer_vraag(body.message)
    if fout:
        return _sse_melding(naar_event(fout))

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
                session_id,
                body.message,
                mode=mode,
                session_kvk=session_kvk,
                toestemming=body.toestemming,
                opgaven=body.opgaven,
                **api_keys,
            )
        ) as stream:
            try:
                async for event in stream:
                    event_type = event.get("type", "status")
                    # Session_id en mode horen bij elk event dat een beurt afsluit,
                    # niet alleen bij `answer`. Sinds PDR-011 eindigen sommige
                    # beurten op een `error`-event ("te veel stappen", "geen
                    # antwoord"), en juist die meldingen vragen de gebruiker het
                    # opnieuw te proberen. Zonder het server-gemunte session_id
                    # start die tweede poging een nieuw gesprek en is de context
                    # weg — precies wanneer die het hardst nodig is.
                    if event_type in ("answer", "error"):
                        event["session_id"] = session_id
                        event["mode"] = mode
                        event["has_tools"] = host.has_tools
                    payload = json.dumps(event, ensure_ascii=False)
                    yield f"event: {event_type}\ndata: {payload}\n\n"
            except Exception:
                # Status 200 is hier al verstuurd, dus een fout kán niet meer als
                # HTTP-status naar buiten. Zonder dit blok krijgt de UI een
                # afgekapte respons zonder `error` én zonder `done`, en blijft ze
                # in "Nadenken…" hangen. Server-side de volledige traceback
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
        return _fout_respons(_geen_sessie_fout())
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
    return host.get_status()


@app.get("/regelrecht/definities")
async def regelrecht_definities(law: str):
    """Definities/constantes van een RegelRecht-wet (bv. drempelwaarden).

    Eén bron van waarheid: de engine (rule_spec.definitions). Alleen wetten op
    de allowlist (REGELRECHT_DEFINITIES_ALLOWLIST) zijn opvraagbaar; de service
    hoort bij de wet (uit de allowlist), niet bij de caller. Voor frontend
    CTA-gating per regeling-pagina.
    """
    result = await host.get_definities(law)
    code = result.get("error")
    if code:
        # Ook hier de catalogustekst, zodat de frontend dezelfde melding toont
        # als in de chat en er één plek is waar de formulering staat.
        fout = maak_fout(code, bron="regelrecht")
        return JSONResponse(
            status_code=fout.http_status, content={**result, **naar_event(fout)}
        )
    return result


@app.get("/regelrecht/drempels")
async def regelrecht_drempels():
    """Alias voor /regelrecht/definities (energiebesparings-/informatieplicht).

    Geeft het veld 'drempelwaarden' terug voor terugwaartse compatibiliteit.
    """
    result = await host.get_drempelwaarden()
    code = result.get("error")
    if code:
        # Gaf eerder een 200 met een foutcode erin, waardoor de frontend het als
        # geldig antwoord kon lezen.
        fout = maak_fout(code, bron="regelrecht")
        return JSONResponse(
            status_code=fout.http_status, content={**result, **naar_event(fout)}
        )
    return result


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

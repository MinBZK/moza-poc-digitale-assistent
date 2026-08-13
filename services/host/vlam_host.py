"""Host — orkestreert twee LLM-backends (VLAM en Claude) met dezelfde MCP-tools.

De host fungeert als tussenstap:
  Gebruiker → Host → LLM (VLAM/Mistral óf Claude) + MCP-tools → antwoord
"""

import asyncio
import functools
import json
import logging
import re
import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

import anthropic
import httpx
import openai

import regelrouting
from cli_executor import CLI_DIR, execute_cli_tool
from config import (
    ALLOW_API_KEY_OVERRIDE,
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_TIMEOUT,
    MCP_SERVERS,
    TOOL_TIMEOUT,
    VLAM_API_KEY,
    VLAM_BASE_URL,
    VLAM_MODEL_ID,
    VLAM_TIMEOUT,
    get_system_prompt,
)
from errors import (
    classificeer_llm_fout,
    classificeer_tool_fout,
    maak_fout,
    naar_event,
    naar_llm,
    verrijk_llm,
)
from feiten import feiten_uit_tool
from log_redaction import redact_always, redact_temporarily
from mcp_client import MCPToolRegistry
from regelloop import Uitkomst, volg_regel
from slots import vul_slots

logger = logging.getLogger("vlam.host")


@functools.cache
def _shared_ssl_context() -> ssl.SSLContext:
    """Eén geparste CA-bundel per proces, gedeeld door alle request-clients.

    `httpx` 0.28 cachet dit zelf niet, dus elke clientconstructie las de bundel
    (224 KB) opnieuw in — synchroon, in de event loop. De context is read-only in
    gebruik en dus veilig te delen; de TLS-handshake per verzoek blijft staan.
    """
    return httpx.create_ssl_context()

# Gebruiksvriendelijke labels voor tools (getoond in de UI tijdens verwerking)
TOOL_LABELS = {
    "kvk__mijn_bedrijf": "KvK Handelsregister raadplegen",
    "kvk__vestigingen": "KvK: vestigingen opzoeken",
    "kvk__eigenaar": "KvK: eigenaar opzoeken",
    "koop__zoek_regelgeving": "KOOP Regelingenbank doorzoeken",
    "koop__lees_regeling": "KOOP: wettekst lezen",
    "netbeheerder__verbruik": "Business Wallet: energieverbruik raadplegen",
    "regelrecht__execute_law": "RegelRecht: regel uitvoeren",
    "regelrecht__check": "RegelRecht: verplichting toetsen",  # CLI-transport (zie PDR-008)
    "rvo__zoek_regeling": "RVO: subsidieregeling zoeken",
    "rvo__indienen": "RVO: rapportage indienen",
}


def _tool_label(tool_key: str) -> str:
    """Geef een gebruiksvriendelijk label voor een tool-key."""
    return TOOL_LABELS.get(tool_key, tool_key)


# Wetten waarvan de frontend de definities/constantes mag opvragen
# (GET /regelrecht/definities). Per wet: de service en een optionele lokale
# fallback voor demo-robuustheid bij een onbereikbare engine. De allowlist
# voorkomt willekeurige wet-executies via de query-parameter.
REGELRECHT_DEFINITIES_ALLOWLIST: dict[str, dict] = {
    "omgevingswet/energiebesparing/informatieplicht": {
        "service": "RVO",
        "fallback": {
            "DREMPEL_ELEKTRICITEIT_KWH": 50000,
            "DREMPEL_GAS_M3": 25000,
            "DREMPEL_ONDERZOEK_ELEKTRICITEIT_KWH": 10000000,
            "DREMPEL_ONDERZOEK_GAS_M3": 170000,
            "RAPPORTAGE_FREQUENTIE_JAREN": 4,
        },
    },
}


# Tools waarvan het KvK-nummer server-side wordt bepaald door de sessie
# (MVP-01/PDR-009). De host injecteert/overschrijft het KvK-nummer vlak vóór de
# aanroep; het LLM en de gebruiker kunnen het niet kiezen.
_KVK_SESSIE_TOOLS = frozenset(
    {
        "kvk__mijn_bedrijf",
        "kvk__vestigingen",
        "kvk__eigenaar",
        "regelrecht__check",
        "rvo__indienen",
        "netbeheerder__verbruik",
    }
)
_INFORMATIEPLICHT_LAW = "omgevingswet/energiebesparing/informatieplicht"

# Sleutels die een identiteit dragen (KvK-nummer, BSN, RSIN, burgerservicenummer).
# Het LLM mag ze nooit meegeven aan de generieke execute_law-tool: identiteit komt
# uitsluitend uit de sessie. Case-insensitieve substring-match dekt ook varianten
# (kvk_nummer, KVK). NB: dit is deny-by-default op sleutelnaam; een echte allowlist
# per wet is een vervolgstap (zie NEXT_STEPS / BETA-02).
_IDENTITY_KEY_RE = re.compile(r"kvk|bsn|rsin|burgerservicenummer", re.IGNORECASE)


def _strip_identity_keys(value):
    """Verwijder identity-dragende sleutels (KvK/BSN) recursief uit dicts/lists."""
    if isinstance(value, dict):
        return {
            k: _strip_identity_keys(v)
            for k, v in value.items()
            if not _IDENTITY_KEY_RE.search(str(k))
        }
    if isinstance(value, list):
        return [_strip_identity_keys(v) for v in value]
    return value


def _arg_keys(arguments: dict) -> str:
    """Geef alleen de argument-namen terug voor logging (nooit de waarden).

    We loggen bewust geen argument-waarden: die kunnen het sessie-KvK-nummer
    bevatten (afgeleid van het `X-Test-User`-token) — dat hoort niet in de logs
    (privacy + het koppelt een sessie aan een bedrijf). Alleen de veldnamen zijn
    nuttig voor debugging en dragen geen identiteit.
    """
    return ", ".join(sorted(str(k) for k in (arguments or {})))


def _inject_session_kvk(tool_key: str, arguments: dict, kvk: str) -> dict:
    """Injecteer/overschrijf het sessie-KvK-nummer in de tool-argumenten.

    Geeft een nieuwe dict terug (muteert de input niet). Voor de generieke
    RegelRecht-tool zit het KvK-nummer in `parameters.KVK_NUMMER`, en alleen de
    informatieplicht-regel heeft het nodig — de maatregelen-regel gebruikt
    `parameters` als feiten en blijft ongemoeid.
    """
    # Eerst deny-by-default op topniveau: welke tool het ook is, een
    # identity-sleutel die het model meegaf gaat eruit. Zonder deze regel hing
    # de grens uit PDR-009 aan de vraag of een tool in `_KVK_SESSIE_TOOLS` staat,
    # en zou een tool die daar (nog) niet in zit een KvK-nummer uit de
    # conversatie kunnen doorgeven aan een bron.
    args = _strip_identity_keys(dict(arguments or {}))
    if tool_key in _KVK_SESSIE_TOOLS:
        args["kvk_nummer"] = kvk
    elif tool_key == "regelrecht__execute_law":
        # Deny-by-default: strip alle identity-sleutels (KvK/BSN) die het LLM
        # meegaf — in parameters én overrides, recursief — zodat identiteit nooit
        # uit de conversatie komt. Zet daarna de sessie-KvK alléén voor de wet die
        # het nodig heeft (informatieplicht). De maatregelen-regel gebruikt
        # parameters als feiten en krijgt geen KvK.
        raw = args.get("parameters")
        params = _strip_identity_keys(raw) if isinstance(raw, dict) else {}
        if str(args.get("law", "")).strip() == _INFORMATIEPLICHT_LAW:
            params["KVK_NUMMER"] = kvk
        args["parameters"] = params
        if "overrides" in args:
            args["overrides"] = _strip_identity_keys(args.get("overrides"))
    return args


def _regel_status_dict(uitkomst: Uitkomst) -> dict:
    """Vertaal `Uitkomst` naar wat de systeemprompt nodig heeft.

    Bij overschrijding van de rondegrens geeft `volg_regel` `klaar=False` mét
    `wacht_op=None` terug — een derde toestand naast de drie benoemde
    `wacht_op`-waarden (zie `regelloop.Uitkomst`). Zonder deze normalisatie
    valt dat geval stilzwijgend door de `wacht_op`-afhandeling in de prompt
    heen; hier wordt het expliciet "onbekend".
    """
    wacht_op = uitkomst.wacht_op or ("onbekend" if not uitkomst.klaar else None)
    return {
        "klaar": uitkomst.klaar,
        "wacht_op": wacht_op,
        "reden": uitkomst.reden,
        "resultaat": uitkomst.resultaat,
    }


def _opgaven_als_feiten(opgaven: dict[str, object] | None) -> dict[str, dict]:
    """Verpak de formulierantwoorden van de frontend tot feiten met herkomst.

    Alleen velden die `regelrouting.route()` kent mét `soort == "opgave"` komen
    door: een frontend mag daarmee geen willekeurig feit de kaart in schrijven,
    ook geen feit dat wél in de routeringstabel staat maar uit een andere bron
    hoort te komen (bv. `IS_WOONFUNCTIE`, een registratie).
    """
    feiten: dict[str, dict] = {}
    for naam, waarde in (opgaven or {}).items():
        veld = regelrouting.route(str(naam))
        if veld is None or veld.soort != "opgave":
            continue
        sleutel = veld.feitnaam or str(naam)
        feiten[sleutel] = {"waarde": waarde, "bron": veld.bron, "soort": veld.soort}
    return feiten


def _geen_sleutel_fout(backend: str = ""):
    """De melding als er geen bruikbare sleutel is voor het gekozen AI-model.

    Staat `ALLOW_API_KEY_OVERRIDE` uit, dan negeert de host een sleutel uit de
    UI stilzwijgend; "vul uw sleutel in bij Instellingen" is dan een doodlopend
    advies waar de gebruiker eindeloos in blijft hangen. Staat de override aan,
    dan noemt de melding wélke sleutel: er zijn er twee.
    """
    if ALLOW_API_KEY_OVERRIDE:
        return maak_fout("LLM_GEEN_SLEUTEL", backend=backend)
    return maak_fout("LLM_NIET_INGESTELD")


def _antwoord_events(
    tekst: str,
    afgekapt: bool = False,
    feiten: dict | None = None,
    maatregelen: list[dict] | None = None,
) -> list[dict]:
    """De events die bij dit antwoord horen.

    Een lege antwoordbel is voor de gebruiker niet te onderscheiden van een
    vastgelopen assistent (een OpenAI-compatibele proxy die content-filtert
    levert `content=None`); dan alleen een melding.

    De slots worden hier ingevuld, op de laatste plek voordat de tekst de deur
    uit gaat. Blijft er een slot onopgelost, dan gaat het antwoord niet mee: een
    zichtbare `{{…}}` is voor de respondent even verwarrend als een fout feit,
    en een half ingevuld rapport is erger dan een foutmelding.

    Breekt het antwoord af op `max_tokens`, dan gaat de deeltekst wél mee: die
    is meestal grotendeels bruikbaar en weggooien is een grotere achteruitgang
    dan de afbreking zelf. De melding gaat eraan vooraf als niet-terminaal
    event, zodat de gebruiker weet dat er meer was.

    `maatregelen` gaat alleen mee als deze beurt de EML-tool daadwerkelijk
    heeft aangeroepen (`vraagSpec` in digitale-assistent.js leest dit veld vóór
    het terugvalt op tekst parsen); anders draagt elk volgend antwoord een
    verouderd formulier mee.
    """
    tekst, ontbrekend = vul_slots(tekst, feiten or {})
    if ontbrekend:
        logger.error("Onopgeloste slots in het antwoord: %s", sorted(set(ontbrekend)))
        return [naar_event(maak_fout("ANTWOORD_ONVOLLEDIG"))]
    if not (tekst or "").strip():
        logger.error("Het model gaf een leeg antwoord terug")
        return [naar_event(maak_fout("LLM_LEEG_ANTWOORD"))]
    antwoord = {"type": "answer", "message": tekst}
    if maatregelen:
        antwoord["maatregelen"] = maatregelen
    if afgekapt:
        logger.warning("Het antwoord van het model is afgekapt op max_tokens")
        return [
            naar_event(maak_fout("LLM_ANTWOORD_AFGEKAPT"), "bron_fout"),
            antwoord,
        ]
    return [antwoord]


def _antwoord_tekst(tekst: str, afgekapt: bool = False, feiten: dict | None = None) -> str:
    """Hetzelfde als `_antwoord_events`, maar voor de niet-streamende paden.

    Daar is er maar één veld (`reply`), dus de melding gaat vóór de deeltekst
    in plaats van als apart event. Zonder dit zag een `/chat`-client een leeg
    antwoord of een halve zin zonder enige aanwijzing.

    De slots worden hier ingevuld, op de laatste plek voordat de tekst de deur
    uit gaat. Blijft er een slot onopgelost, dan gaat het antwoord niet mee: een
    zichtbare `{{…}}` is voor de respondent even verwarrend als een fout feit,
    en een half ingevuld rapport is erger dan een foutmelding.
    """
    tekst, ontbrekend = vul_slots(tekst, feiten or {})
    if ontbrekend:
        logger.error("Onopgeloste slots in het antwoord: %s", sorted(set(ontbrekend)))
        return maak_fout("ANTWOORD_ONVOLLEDIG").tekst
    if not (tekst or "").strip():
        logger.error("Het model gaf een leeg antwoord terug")
        return maak_fout("LLM_LEEG_ANTWOORD").tekst
    if afgekapt:
        logger.warning("Het antwoord van het model is afgekapt op max_tokens")
        return f"{maak_fout('LLM_ANTWOORD_AFGEKAPT').tekst}\n\n{tekst}"
    return tekst


# Foutcodes waarbij het bijbehorende assistent-bericht uit de geschiedenis
# moet: bij beide zag de respondent een foutmelding, geen antwoord (leeg bij
# LLM_LEEG_ANTWOORD, met onopgeloste `{{...}}`-slots bij ANTWOORD_ONVOLLEDIG).
# Blijft het bericht toch staan, dan gelooft het model dat het dát antwoord al
# gaf, en bij een structurele oorzaak (bv. een slot dat nooit oplost) wordt de
# fout plakkerig in plaats van eenmalig.
_HERSTEL_CODES = frozenset({"LLM_LEEG_ANTWOORD", "ANTWOORD_ONVOLLEDIG"})
_HERSTEL_TEKSTEN = frozenset(maak_fout(code).tekst for code in _HERSTEL_CODES)


def _is_afgekapt(respons_of_choice) -> bool:
    """Liep het model tegen zijn max_tokens aan?

    Anthropic zet `stop_reason="max_tokens"` op de respons, OpenAI
    `finish_reason="length"` op de choice.
    """
    return (
        getattr(respons_of_choice, "stop_reason", None) == "max_tokens"
        or getattr(respons_of_choice, "finish_reason", None) == "length"
    )


def _lees_tool_argumenten(ruwe_json: str | None) -> dict | None:
    """Parse de argumenten van een tool-call; `None` als het geen geldige JSON is.

    Stond eerder buiten de try/except, waardoor een malformed tool-call van het
    model de hele SSE-stream afbrak in plaats van een nette melding te geven.
    """
    try:
        argumenten = json.loads(ruwe_json or "{}")
    except (json.JSONDecodeError, TypeError):
        logger.error("Tool-call met onleesbare argumenten ontvangen")
        return None
    return argumenten if isinstance(argumenten, dict) else None


def _zoekterm(arguments: dict) -> str:
    """De zoekopdracht uit de argumenten, voor een concrete 'niets gevonden'-melding.

    Alleen velden die de gebruiker zelf noemt (trefwoord, BWB-ID); nooit een
    identiteit-dragend veld, dat hoort niet in een melding of log. De waarde komt
    van het LLM en gaat de melding in die het weer moet uitspreken, dus 'm eerst
    laten schoonmaken en afkappen (`schoon_echo` in `errors.py`).
    """
    args = arguments or {}
    return str(args.get("trefwoord") or args.get("bwb_id") or "")


async def _bron_aanroep(aanroep, tool_key: str, arguments: dict) -> tuple[str, object]:
    """Voer een bron-aanroep uit en vertaal een fout naar een nette melding.

    Geeft `(tool_resultaat, fout_of_None)` terug. Het tool-resultaat gaat naar
    het LLM; de fout (als die er is) naar de UI. Exception-teksten, paden en
    URL's blijven in de log: het LLM kan alles doorvertellen wat het ziet.
    """
    try:
        # Met een time-out: een bron die het verzoek aanneemt maar nooit
        # antwoordt (hangende upstream-call, deadlock in een handler) liet de
        # hele stream staan op dit `await`. Geen exception, dus ook het vangnet
        # in `chat_stream` hielp niet: de gebruiker zag een spinner die nooit
        # stopte. De TimeoutError landt in de SOURCE_UNAVAILABLE-melding.
        resultaat = await asyncio.wait_for(aanroep(), timeout=TOOL_TIMEOUT)
    except Exception as e:
        fout = classificeer_tool_fout(tool_key, e)
        _log_tool_error(tool_key, e, fout.code)
        return naar_llm(fout), fout

    fout = classificeer_tool_fout(tool_key, resultaat, _zoekterm(arguments))
    if fout is None:
        return resultaat, None
    logger.warning("Bron meldt een fout [%s/%s]", tool_key, fout.code)
    # Niet elke fout is er een voor de gebruiker: een tool-aanroep die het model
    # zelf corrigeert hoort niet als storing in de UI.
    return verrijk_llm(resultaat, fout), (fout if fout.zichtbaar else None)


def _extract_lopende_zaak(tool_name: str, result: str) -> dict | None:
    """Extraheer lopende_zaak uit een rvo__indienen resultaat."""
    if tool_name != "rvo__indienen":
        return None
    try:
        parsed = json.loads(result)
        data = parsed.get("data", parsed)
        return data.get("lopende_zaak")
    except (json.JSONDecodeError, AttributeError):
        return None


def maatregelen_voor_event(tool_naam: str, resultaat: str) -> list[dict] | None:
    """De geldende EML-maatregelen als veld voor het answer-event.

    De frontend (vraagSpec in digitale-assistent.js) leest `maatregelen` vóór het
    terugvalt op het parsen van de platte tekst, en verwacht `omschrijving` waar
    de MCP-server `naam` levert. Zonder die hermapping toont het formulier kale
    codes.
    """
    if tool_naam != "regelrecht__execute_law":
        return None
    try:
        data = json.loads(resultaat).get("data") or {}
        geldend = [
            {"code": m.get("code", ""), "omschrijving": m.get("naam", "")}
            for m in (data.get("maatregelen") or [])
            if m.get("van_toepassing")
        ]
    except (ValueError, AttributeError):
        return None
    return geldend or None


def _log_tool_error(tool_key: str, exc: Exception, code: str = "") -> None:
    """Log een mislukte tool-aanroep zonder de tekst van de exception.

    Die tekst kan argumentwaarden bevatten — bijvoorbeeld het sessie-KvK, zoals
    in "kvk_nummer 85234567 niet gevonden" — en zou daarmee `_arg_keys`
    ondergraven, dat juist bewust alleen veldnamen logt. Op DEBUG staat de
    volledige tekst wél; die stand kies je zelf, en dan weet je wat je logt.
    """
    logger.error(
        "Tool-aanroep mislukt [%s%s]: %s",
        tool_key,
        f"/{code}" if code else "",
        type(exc).__name__,
    )
    logger.debug("Tool-aanroep mislukt [%s] (volledige melding): %s", tool_key, exc)


def _log_tokens(backend: str, response) -> None:
    """Log token-gebruik uit een LLM-response (Anthropic of OpenAI)."""
    usage = getattr(response, "usage", None)
    if not usage:
        return
    # Anthropic: input_tokens / output_tokens
    # OpenAI:    prompt_tokens / completion_tokens
    input_t = getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None) or 0
    output_t = getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None) or 0
    total = input_t + output_t
    logger.info(
        "TOKENS [%s] input=%d output=%d total=%d",
        backend, input_t, output_t, total,
    )


# Tool-definities voor CLI-modus (onafhankelijk van MCP-registry)
#
# `fields` is overal optioneel: als het LLM een lijst velden meegeeft, vertaalt
# cli_executor dit naar `--fields v1,v2,...` op de onderliggende CLI-aanroep.
# Hiermee wordt dataminimalisatie afdwingbaar zonder muterende tools te raken.
_FIELDS_PARAM = {
    "type": "array",
    "items": {"type": "string"},
    "description": "Optioneel: alleen deze velden retourneren (dataminimalisatie). Laat leeg voor de volledige response.",
}

CLI_TOOL_DEFINITIONS_ANTHROPIC = [
    {
        "name": "kvk__mijn_bedrijf",
        "description": "Haal het KvK-basisprofiel op van het bedrijf van de ingelogde gebruiker. Geeft bedrijfsnaam, KvK-nummer, rechtsvorm, SBI-activiteiten, vestigingsadres en aantal medewerkers. Het profiel wordt automatisch verrijkt met BAG-gegevens (gebruiksdoel pand en is_woonfunctie) via het Kadaster. Veelgebruikte velden: naam, kvkNummer, statutaireNaam, totaalWerkzamePersonen, sbiActiviteiten, _embedded.hoofdvestiging, bag, is_woonfunctie.",
        "input_schema": {
            "type": "object",
            "properties": {"fields": _FIELDS_PARAM},
            "required": [],
        },
    },
    {
        "name": "kvk__vestigingen",
        "description": "Haal de lijst met vestigingen op van het bedrijf van de ingelogde gebruiker. Geeft per vestiging het adres, vestigingsnummer en de SBI-activiteiten. Sessie-gebonden, geen kvk_nummer nodig.",
        "input_schema": {
            "type": "object",
            "properties": {"fields": _FIELDS_PARAM},
            "required": [],
        },
    },
    {
        "name": "kvk__eigenaar",
        "description": "Haal de eigenaar-informatie op van het bedrijf van de ingelogde gebruiker. Retourneert rechtspersoon- of natuurlijk-persoon-gegevens afhankelijk van de rechtsvorm. Sessie-gebonden, geen kvk_nummer nodig.",
        "input_schema": {
            "type": "object",
            "properties": {"fields": _FIELDS_PARAM},
            "required": [],
        },
    },
    {
        "name": "koop__zoek_regelgeving",
        "description": "Doorzoek de KOOP Regelingenbank (wetten.overheid.nl) op trefwoord. Retourneert titel, identificatie (BWB-ID), type, organisatie en geldigheid. Veelgebruikte velden: titel, identifier, type.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trefwoord": {"type": "string", "description": "Zoekterm (trefwoord of frase)"},
                "onderwerp": {"type": "string", "description": "Filter op onderwerp (bijv. 'energie', 'milieu')"},
                "type_regeling": {"type": "string", "description": "Filter op type: 'wet', 'AMvB', 'ministerieleregeling', 'verdrag'"},
                "max_resultaten": {"type": "integer", "description": "Maximaal aantal resultaten (standaard 10, max 50)"},
                "fields": _FIELDS_PARAM,
            },
            "required": ["trefwoord"],
        },
    },
    {
        "name": "koop__lees_regeling",
        "description": "Haal de volledige inhoud van een regeling op aan de hand van het BWB-ID (begint met BWBR, BWBV of BWBB). Retourneert titel, datum en de tekst per artikel. Gebruik dit nadat de gebruiker met koop__zoek_regelgeving een specifieke regeling heeft gevonden of een BWB-ID noemt.",
        "input_schema": {
            "type": "object",
            "properties": {
                "bwb_id": {"type": "string", "description": "BWB-ID, bijv. 'BWBR0001840' (Grondwet) of 'BWBR0038472'"},
                "fields": _FIELDS_PARAM,
            },
            "required": ["bwb_id"],
        },
    },
    {
        "name": "regelrecht__check",
        "description": "Controleer of de Informatieplicht Energiebesparing van toepassing is op een bedrijf, op basis van het Besluit activiteiten leefomgeving. Veelgebruikte velden: voldoet_aan_voorwaarden, wettelijke_grondslag, ontbrekende_gegevens.",
        "input_schema": {
            "type": "object",
            "properties": {
                # kvk_nummer wordt server-side door de sessie bepaald (PDR-009),
                # niet door het LLM. De host injecteert het bij de aanroep.
                "jaarlijks_elektriciteitsverbruik_kwh": {"type": "number", "description": "Jaarlijks elektriciteitsverbruik in kWh"},
                "jaarlijks_gasverbruik_m3": {"type": "number", "description": "Jaarlijks gasverbruik in m³"},
                "is_woonfunctie": {"type": "boolean", "description": "Of het gebouw uitsluitend een woonfunctie heeft"},
                "fields": _FIELDS_PARAM,
            },
            "required": [],
        },
    },
    {
        "name": "rvo__zoek_regeling",
        "description": "Zoek beschikbare RVO-subsidies en regelingen op trefwoord. Retourneert naam, status, deadline en beschrijving. Veelgebruikte velden: naam, status, deadline.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trefwoord": {"type": "string", "description": "Zoekterm (bijv. 'energiebesparing', 'subsidie', 'warmtepomp')"},
                "fields": _FIELDS_PARAM,
            },
            "required": ["trefwoord"],
        },
    },
    {
        "name": "rvo__indienen",
        "description": "Dien een energiebesparingsrapportage in bij RVO namens de ondernemer. Dit is een muterende actie — vraag bevestiging aan de gebruiker.",
        "input_schema": {
            "type": "object",
            "properties": {
                # kvk_nummer wordt server-side door de sessie bepaald (PDR-009).
                "regeling_id": {"type": "string", "description": "Regeling-ID (bijv. 'EBR-2026')"},
                "maatregelen": {"type": "array", "items": {"type": "string"}, "description": "Lijst van genomen energiebesparingsmaatregelen"},
            },
            "required": ["regeling_id", "maatregelen"],
        },
    },
]

CLI_TOOL_DEFINITIONS_OPENAI = [
    {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
    for t in CLI_TOOL_DEFINITIONS_ANTHROPIC
]


class VLAMHost:
    """Orkestrator die twee LLM-backends koppelt aan MCP-servers."""

    def __init__(self):
        # Server-env-sleutels leven zo lang als het proces; laat het log-vangnet
        # ze bij naam kennen.
        redact_always(ANTHROPIC_API_KEY)
        redact_always(VLAM_API_KEY)
        self.claude_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self.vlam_client = (
            openai.AsyncOpenAI(
                api_key=VLAM_API_KEY,
                base_url=VLAM_BASE_URL,
            )
            if VLAM_API_KEY and VLAM_BASE_URL
            else None
        )
        self.registry = MCPToolRegistry()
        self.conversations: dict[str, list[dict]] = {}
        # Feiten per gesprek, geoogst uit tool-resultaten. Zelfde sleutel als
        # self.conversations, zodat één opruimmechanisme later allebei dekt -
        # geen van beide heeft nu een TTL.
        self.feiten: dict[str, dict] = {}
        # Toestemming voor de Business Wallet (PDR-008), per gesprek. Een
        # vastgelegde vlag, geen afleiding: uitsluitend gezet zodra de frontend
        # expliciet `toestemming: true` stuurt op het chat-contract (de
        # "Delen"-knop). Een geslaagde `netbeheerder__verbruik`-aanroep zet 'm
        # NIET (meer) — dat pad autoriseerde zichzelf: een aanroep die de vlag
        # nodig heeft om door de poort te komen, kon 'm ook zelf zetten zodra
        # hij eenmaal doorkwam. Eenmaal `True` blijft `True` binnen de sessie —
        # er is hier geen intrekking.
        self.toestemming: dict[str, bool] = {}
        # Houdt bij welke servers gelukt/mislukt zijn
        self.server_status: dict[str, str] = {}

    async def startup(self):
        """Verbind met alle geconfigureerde MCP-servers."""
        for name, path in MCP_SERVERS.items():
            try:
                await self.registry.register_server(name, path)
                self.server_status[name] = "verbonden"
            except Exception as e:
                logger.warning("Kan server '%s' niet starten: %s", name, e)
                self.server_status[name] = "niet beschikbaar"

        tool_count = len(self.registry.tool_map)
        backends = ["claude"]
        if self.vlam_client:
            backends.append("vlam")
        logger.info(
            "Host gestart — %d tools, backends: %s",
            tool_count,
            ", ".join(backends),
        )

    async def shutdown(self):
        """Sluit alle verbindingen."""
        await self.registry.disconnect_all()
        logger.info("Host afgesloten")

    @property
    def has_tools(self) -> bool:
        return len(self.registry.tool_map) > 0

    @property
    def bronnen_offline(self) -> list[str]:
        """MCP-bronnen die bij het starten niet beschikbaar kwamen."""
        return sorted(
            naam for naam, status in self.server_status.items() if status != "verbonden"
        )

    @property
    def cli_bronnen_offline(self) -> list[str]:
        """Bronnen die het CLI-transport niet kan bedienen.

        De netbeheerder heeft überhaupt geen wrapper (PDR-005/PDR-008: het
        CLI-transport loopt bewust achter), en een wrapper kan ontbreken in de
        installatie. Zonder deze lijst volgt het model in `cli:*`-modus de
        routeringstabel naar een tool die niet bestaat, en krijgt de gebruiker
        het advies zijn vraag opnieuw te stellen — wat per definitie niet helpt.
        """
        wrappers = {
            "kvk": "kvk-cli",
            "koop": "koop-cli",
            "regelrecht": "regelrecht-cli",
            "rvo": "rvo-cli",
        }
        ontbreekt = [
            bron for bron, script in wrappers.items() if not (CLI_DIR / script).is_file()
        ]
        # Alleen bronnen die er écht niet zijn. RegelRecht hoort er bewust NIET
        # bij: `regelrecht__check` werkt in dit transport prima. Dat de gedeelde
        # routeringstabel de MCP-naam `execute_law` voorschrijft is een
        # naamprobleem, geen beschikbaarheidsprobleem; dat wordt opgelost met
        # het CLI-blok in de systeemprompt (`cli_transport.md`). De hele bron
        # offline melden zou de assistent een onware storing laten uitspreken op
        # precies de vlaggenschipvraag van de PoC.
        return sorted({*ontbreekt, "netbeheerder"})

    def _system_prompt(
        self,
        mode: str,
        has_tools: bool | None = None,
        bronnen_offline: list[str] | None = None,
        cli_transport: bool = False,
        regel_status: dict | None = None,
    ) -> str:
        """Stel de systeemprompt samen, inclusief welke bronnen nu offline zijn.

        Zonder dat laatste weet het LLM niet dat een bron ontbreekt en praat het
        eroverheen. De CLI-paden geven hun eigen lijst mee (`cli_bronnen_offline`):
        de MCP-status zegt daar niets, maar het CLI-transport heeft zijn eigen
        gaten — er is bijvoorbeeld geen netbeheerder-wrapper. `regel_status` komt
        van `_regel_status`: wat de regelloop deze beurt al heeft bepaald.
        """
        return get_system_prompt(
            mode,
            self.has_tools if has_tools is None else has_tools,
            bronnen_offline=(
                self.bronnen_offline if bronnen_offline is None else bronnen_offline
            ),
            cli_transport=cli_transport,
            regel_status=regel_status,
        )

    def get_status(self) -> dict:
        """Geeft de status van backends en MCP-servers."""
        cli_tools = {
            "kvk": (CLI_DIR / "kvk-cli").is_file(),
            "koop": (CLI_DIR / "koop-cli").is_file(),
            "regelrecht": (CLI_DIR / "regelrecht-cli").is_file(),
            "rvo": (CLI_DIR / "rvo-cli").is_file(),
        }
        return {
            "backends": {
                "claude": bool(ANTHROPIC_API_KEY),
                "vlam": self.vlam_client is not None,
            },
            "servers": self.server_status,
            "cli": {k: "verbonden" if v else "niet beschikbaar" for k, v in cli_tools.items()},
            "tools": len(self.registry.tool_map),
        }

    async def get_definities(self, law: str) -> dict:
        """Definities/constantes (bv. drempelwaarden) van een RegelRecht-wet.

        Bron van waarheid: de engine (rule_spec.definitions), opgehaald via de
        regelrecht-tool. Alleen wetten op REGELRECHT_DEFINITIES_ALLOWLIST zijn
        opvraagbaar; per wet kan een lokale fallback gelden (demo-robuustheid).
        """
        spec = REGELRECHT_DEFINITIES_ALLOWLIST.get(law)
        if spec is None:
            return {
                "error": "WET_NIET_TOEGESTAAN",
                "law": law,
                "toegestaan": sorted(REGELRECHT_DEFINITIES_ALLOWLIST),
            }
        # De service hoort bij de wet (allowlist), niet bij de caller: pin 'm,
        # zodat geen door de caller bepaalde parameter de engine bereikt.
        service = spec["service"]
        tool_key = "regelrecht__execute_law"
        if tool_key in self.registry.tool_map:
            try:
                raw = await self.registry.call_tool(
                    tool_key, {"law": law, "service": service, "parameters": {}}
                )
                defs = json.loads(raw).get("data", {}).get("drempelwaarden")
                if defs:
                    return {
                        "definities": defs,
                        "bron": "RegelRecht (poc-machine-law)",
                        "service": service,
                        "law": law,
                    }
            except Exception as e:
                logger.warning(
                    "Definities uit RegelRecht ophalen mislukt (%s): %s", law, e
                )
        fallback = spec.get("fallback")
        if fallback:
            return {
                "definities": fallback,
                "bron": "lokale fallback (RegelRecht niet beschikbaar)",
                "service": service,
                "law": law,
            }
        return {"error": "BRON_NIET_BESCHIKBAAR", "service": service, "law": law}

    async def get_drempelwaarden(self) -> dict:
        """Alias voor de energiebesparings-/informatieplicht-drempelwaarden.

        Geeft het veld 'drempelwaarden' terug (terugwaartse compatibiliteit met
        GET /regelrecht/drempels).
        """
        res = await self.get_definities(
            "omgevingswet/energiebesparing/informatieplicht"
        )
        if "definities" in res:
            return {
                "drempelwaarden": res["definities"],
                "bron": res["bron"],
                "wet": res["law"],
            }
        return res

    @staticmethod
    async def _close_request_clients(clients: list) -> None:
        """Sluit de eigen clients van dit verzoek — en sla er geen over.

        `CancelledError` erft van `BaseException`, dus een `except Exception`
        ving die niet: bij een afgebroken SSE-stream stopte de lus bij de eerste
        client en bleef een volgende openstaan, mét de sleutel erin. We onthouden
        de annulering, ruimen alles op, en blazen haar daarna weer op zodat de
        afbreking niet stilletjes verdwijnt.
        """
        cancelled: asyncio.CancelledError | None = None
        for client in clients:
            try:
                await client.close()
            except asyncio.CancelledError as e:
                cancelled = e
            except Exception:  # sluiten mag nooit het antwoord breken
                # Volledige traceback: deze aanroep valt binnen de
                # redactie-scope, dus een sleutel erin wordt geredigeerd.
                logger.warning(
                    "Sluiten van request-client %s mislukt",
                    type(client).__name__,
                    exc_info=True,
                )
        if cancelled is not None:
            raise cancelled

    @asynccontextmanager
    async def _request_clients(
        self,
        vlam_api_key_override: str = "",
        claude_api_key_override: str = "",
        mode: str = "",
    ) -> AsyncGenerator[tuple, None]:
        """Lever (claude_client, vlam_client) voor de duur van één verzoek.

        Lokale clients i.p.v. `self.*` overschrijven (MVP-02). De host is één
        gedeeld object en de endpoints zijn async: bij twee gelijktijdige
        gesprekken kon de sleutel van A het verzoek van B bedienen, en daarna
        procesbreed blijven staan.

        Alleen de client van de gevraagde `mode` wordt gebouwd; de andere zou
        toch geen enkele call doen. Een lege of onbekende `mode` betekent
        "claude", net als de terugval in `chat`/`chat_stream`.

        Een override-client wordt na afloop gesloten: de sleutel overleeft het
        verzoek niet en de httpx-pool lekt niet weg. De server-env-clients zijn
        procesbreed en worden hier nooit gesloten.
        """
        claude = self.claude_client
        vlam = self.vlam_client
        own_clients: list = []
        wants_vlam = mode.split(":")[-1] == "vlam"

        # De redactie omsluit óók het opruimen: zowel een fout tijdens het
        # opbouwen als een httpx-fout tijdens `close()` hoort geredigeerd de
        # logs in. Vandaar dit `with` búiten de `try/finally` — andersom liep
        # de registratie af vóór het sluiten.
        with (
            redact_temporarily(claude_api_key_override),
            redact_temporarily(vlam_api_key_override),
        ):
            try:
                if claude_api_key_override and not wants_vlam:
                    claude = anthropic.AsyncAnthropic(
                        api_key=claude_api_key_override,
                        http_client=httpx.AsyncClient(verify=_shared_ssl_context()),
                    )
                    own_clients.append(claude)
                if vlam_api_key_override and wants_vlam:
                    if not VLAM_BASE_URL:
                        # Anders verdwijnt de sleutel zonder spoor en krijgt de
                        # gebruiker "vul uw sleutel in" — wat hij net deed.
                        logger.warning(
                            "VLAM-sleutel meegegeven, maar VLAM_BASE_URL is leeg: "
                            "de sleutel wordt genegeerd en het verzoek meldt dat de "
                            "backend niet geconfigureerd is. Zet VLAM_BASE_URL."
                        )
                    else:
                        vlam = openai.AsyncOpenAI(
                            api_key=vlam_api_key_override,
                            base_url=VLAM_BASE_URL,
                            http_client=httpx.AsyncClient(verify=_shared_ssl_context()),
                        )
                        own_clients.append(vlam)
                yield claude, vlam
            finally:
                await self._close_request_clients(own_clients)

    async def _regel_status(
        self, feiten: dict, session_kvk: str, conv_key: str
    ) -> AsyncGenerator[dict, None]:
        """Draai de regelloop en yield voortgang, met de uitkomst als laatste item.

        Dit is waar de regel de flow overneemt (taak 4): vóórdat het model iets
        ziet, heeft de host al opgehaald wat hij zelf kan. `volg_regel` roept
        tools rechtstreeks aan, buiten de dispatch van het model om, en krijgt
        daarom hier dezelfde twee dingen die een modelgestuurde tool-aanroep al
        kreeg: de sessie-KvK-injectie (`_inject_session_kvk`, PDR-009) en de
        oogst in de feitenkaart (`feiten_uit_tool`) — zonder dat laatste
        verdwijnen de gegevens die de lus zelf ophaalt weer, want `volg_regel`
        werkt op een eigen kopie van `feiten` en geeft die niet terug.

        `volg_regel` roept tools sequentieel aan binnen één coroutine en levert
        pas bij de allerlaatste stap iets op; zonder een kanaal ertussenuit
        blijft de UI blind voor wat de host ondertussen raadpleegt, en verschijnt
        er nooit een `bron_fout` als zo'n aanroep faalt (PDR-011). De achtergrond-
        taak zet elk tussenresultaat op een `asyncio.Queue` zodra het gebeurt.

        Elk item draagt `type` "tool" of "bron_fout" — bedoeld voor de client —
        behalve het laatste: dat draagt `type` "regel_status" met de uitkomst
        voor de systeemprompt, en gaat niet naar de client (de aanroeper filtert
        'm eruit).
        """
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def call_tool(tool_key: str, arguments: dict) -> str:
            arguments = _inject_session_kvk(tool_key, arguments, session_kvk)
            # Het `tool`-event gaat pas ná de aanroep uit: `volg_regel` stopt
            # weliswaar zelf al vóór een toestemmingsplichtig veld zonder
            # toestemming (regelloop.py), maar de poort is de enige plek die dat
            # afdwingt - mocht ze hier ooit toch weigeren, dan hoort er geen
            # event te komen dat een raadpleging meldt die niet plaatsvond.
            resultaat, fout, aangeroepen = await self._bron_aanroep_gated(
                partial(self.registry.call_tool, tool_key, arguments),
                tool_key,
                arguments,
                conv_key,
            )
            if aangeroepen:
                await queue.put(
                    {"type": "tool", "message": _tool_label(tool_key), "tool": tool_key}
                )
            if fout:
                await queue.put(naar_event(fout, "bron_fout"))
            feiten.update(feiten_uit_tool(tool_key, resultaat))
            return resultaat

        async def draai() -> None:
            try:
                uitkomst = await volg_regel(
                    law=_INFORMATIEPLICHT_LAW,
                    service=REGELRECHT_DEFINITIES_ALLOWLIST[_INFORMATIEPLICHT_LAW]["service"],
                    feiten=feiten,
                    call_tool=call_tool,
                    toestemming=self.toestemming.get(conv_key, False),
                )
            except Exception:
                # Een onverwachte fout hier (bv. onleesbare JSON van een bron)
                # mag de generator niet eeuwig laten wachten op een item dat
                # nooit komt: liever "onbekend" dan een hangende stream.
                logger.exception("Regelloop onverwacht gefaald [conv_key=%r]", conv_key)
                uitkomst = Uitkomst(
                    klaar=False, resultaat=None, wacht_op="onbekend", reden=""
                )
            await queue.put({"type": "regel_status", "status": _regel_status_dict(uitkomst)})

        taak = asyncio.create_task(draai())
        try:
            while True:
                item = await queue.get()
                yield item
                if item["type"] == "regel_status":
                    break
        finally:
            if not taak.done():
                taak.cancel()

    async def _regel_status_zonder_events(
        self, feiten: dict, session_kvk: str, conv_key: str
    ) -> dict | None:
        """`_regel_status` afdraaien zonder de tussentijdse events door te geven.

        Voor `chat()` (niet-streamend): er is geen kanaal om `tool`/`bron_fout`
        naar de client te sturen, dus alleen de uiteindelijke regel_status telt.
        """
        status = None
        async for event in self._regel_status(feiten, session_kvk, conv_key):
            if event["type"] == "regel_status":
                status = event["status"]
        return status

    async def chat(
        self,
        session_id: str,
        user_message: str,
        mode: str = "vlam",
        session_kvk: str = "",
        toestemming: bool | None = None,
        opgaven: dict[str, object] | None = None,
        vlam_api_key_override: str = "",
        claude_api_key_override: str = "",
    ) -> str:
        """Verwerk een gebruikersbericht en retourneer het antwoord.

        mode: "vlam" (Mistral via UbiOps) of "claude" (Anthropic).
        Beide modi hebben toegang tot dezelfde MCP-tools (indien beschikbaar).
        session_kvk: het server-side bepaalde KvK-nummer van de sessie (PDR-009);
        de host injecteert dit bij elke bron-aanroep.
        toestemming: expliciete toestemming voor de Business Wallet (PDR-008)
        van dít verzoek. `True` legt de vlag voor de rest van de sessie vast;
        `None`/`False` laat een eerder gegeven toestemming ongemoeid (geen
        intrekking via dit veld).
        opgaven: formulierantwoorden van de ondernemer (bv. HEEFT_KOELINSTALLATIE),
        vóór de regelloop in de feitenkaart gezet zodat de lus er niet opnieuw
        naar vraagt.
        """
        conv_key = self._conv_key(session_kvk, session_id, mode)
        if conv_key not in self.conversations:
            self.conversations[conv_key] = []
        messages = self.conversations[conv_key]
        feiten = self.feiten.setdefault(conv_key, {})
        if toestemming:
            self.toestemming[conv_key] = True
        feiten.update(_opgaven_als_feiten(opgaven))
        use_cli = mode.startswith("cli:")
        # Zie chat_stream: bij een leeg of onvolledig modelantwoord draaien we
        # de hele beurt terug (_HERSTEL_CODES), anders blokkeert een
        # assistent-bericht dat de respondent nooit zo zag elke volgende beurt
        # in deze sessie.
        herstelpunt = len(messages)
        messages.append({"role": "user", "content": user_message})

        async with self._request_clients(
            vlam_api_key_override, claude_api_key_override, mode
        ) as (claude, vlam):
            # De regel vóór het model (taak 4), pas ná de sleutelcontrole: een
            # verzoek zonder bruikbare sleutel eindigt hier zonder ooit een bron
            # te raadplegen (gelijk aan chat_stream). Alleen op het
            # MCP-transport — CLI heeft geen execute_law-tool en blijft
            # modelgeorkestreerd via regelrecht__check (cli_transport.md).
            if mode == "vlam":
                if not vlam:
                    return _geen_sleutel_fout("vlam").tekst
                regel_status = (
                    None
                    if use_cli
                    else await self._regel_status_zonder_events(feiten, session_kvk, conv_key)
                )
                antwoord = await self._chat_vlam(
                    messages, session_kvk, vlam, feiten, regel_status, conv_key
                )
            else:
                if not claude.api_key:
                    return _geen_sleutel_fout("claude").tekst
                regel_status = (
                    None
                    if use_cli
                    else await self._regel_status_zonder_events(feiten, session_kvk, conv_key)
                )
                antwoord = await self._chat_claude(
                    messages, session_kvk, claude, feiten, regel_status, conv_key
                )
            if antwoord in _HERSTEL_TEKSTEN:
                del messages[herstelpunt:]
            return antwoord

    # ------------------------------------------------------------------
    # Streaming — yieldt status-events voor de UI
    # ------------------------------------------------------------------

    async def chat_stream(
        self,
        session_id: str,
        user_message: str,
        mode: str = "vlam",
        session_kvk: str = "",
        toestemming: bool | None = None,
        opgaven: dict[str, object] | None = None,
        vlam_api_key_override: str = "",
        claude_api_key_override: str = "",
    ) -> AsyncGenerator[dict, None]:
        """Verwerk een bericht en yield status-events als dicts.

        Event-types:
          {"type": "status",    "message": "Nadenken..."}
          {"type": "tool",      "message": "Bedrijfsgegevens ophalen", "tool": "kvk__mijn_bedrijf"}
          {"type": "case",      "data": {...}}
          {"type": "bron_fout", "code": "SOURCE_UNAVAILABLE", ...}
          {"type": "answer",    "message": "Het antwoord...", "session_id": "..."}
          {"type": "error",     "code": "LLM_TIMEOUT", ...}
          {"type": "done"}

        `answer` en `error` zijn de eindpunten: er komt er altijd precies één,
        gevolgd door `done`. `bron_fout` is tussentijds — een bron viel uit maar
        het gesprek loopt door (PDR-011).

        toestemming: expliciete toestemming voor de Business Wallet (PDR-008)
        van dít verzoek. Zie `chat()`.
        opgaven: formulierantwoorden van de ondernemer. Zie `chat()`.
        """
        use_cli = mode.startswith("cli:")
        llm = mode.split(":")[-1] if use_cli else mode

        # De clients leven precies zo lang als deze stream (MVP-02/PDR-010): ze
        # komen als argument mee in plaats van via `self`, zodat twee
        # gelijktijdige verzoeken met verschillende sleutels elkaar niet raken.
        # De try eromheen is het vangnet van PDR-011 voor alles wat de loops zelf
        # niet afvangen; het opruimen van de clients hangt aan de contextmanager.
        try:
            async with self._request_clients(
                vlam_api_key_override, claude_api_key_override, mode
            ) as (claude, vlam):
                conv_key = self._conv_key(session_kvk, session_id, mode)
                if conv_key not in self.conversations:
                    self.conversations[conv_key] = []
                messages = self.conversations[conv_key]
                feiten = self.feiten.setdefault(conv_key, {})
                if toestemming:
                    self.toestemming[conv_key] = True
                feiten.update(_opgaven_als_feiten(opgaven))
                # Beginstand van deze beurt. Loopt de beurt stuk op een leeg of
                # onvolledig modelantwoord (_HERSTEL_CODES), dan draaien we
                # hierop terug: een assistent-bericht dat de respondent nooit zo
                # zag (leeg, of met onopgeloste `{{...}}`-slots) blijft anders in
                # de geschiedenis staan en laat élke volgende beurt in deze
                # sessie stuklopen op de Messages API. De melding zegt "probeer
                # het opnieuw", en dat moet dan ook kunnen.
                herstelpunt = len(messages)
                messages.append({"role": "user", "content": user_message})

                yield {"type": "status", "message": "Vraag analyseren…"}

                gen = None
                if llm == "vlam" and not vlam:
                    yield naar_event(_geen_sleutel_fout("vlam"))
                elif llm == "claude" and not claude.api_key:
                    yield naar_event(_geen_sleutel_fout("claude"))
                else:
                    # De regel vóór het model (taak 4), vóór de LLM-aanroep. Alleen
                    # voor het MCP-transport: het CLI-transport heeft geen
                    # execute_law-tool (cli_transport.md) en blijft modelgeorkestreerd
                    # via regelrecht__check. De tussentijdse events (tool/bron_fout)
                    # gaan meteen de stream in, zodat de respondent ziet dat er iets
                    # geraadpleegd wordt terwijl het gebeurt, niet pas achteraf.
                    regel_status = None
                    if not use_cli:
                        async for event in self._regel_status(feiten, session_kvk, conv_key):
                            if event["type"] == "regel_status":
                                regel_status = event["status"]
                            else:
                                yield event
                    if llm == "vlam":
                        gen = (
                            self._chat_vlam_cli_stream(messages, session_kvk, vlam, feiten)
                            if use_cli
                            else self._chat_vlam_stream(
                                messages, session_kvk, vlam, feiten, regel_status, conv_key
                            )
                        )
                    else:
                        gen = (
                            self._chat_cli_stream(messages, session_kvk, claude, feiten)
                            if use_cli
                            else self._chat_claude_stream(
                                messages, session_kvk, claude, feiten, regel_status, conv_key
                            )
                        )

                if gen is not None:
                    async for event in gen:
                        if event.get("code") in _HERSTEL_CODES:
                            del messages[herstelpunt:]
                        yield event
        except Exception as e:
            # Vangnet voor alles wat de loops zelf niet afvangen (een respons in
            # een onverwachte vorm, een fout in de foutafhandeling). Zonder dit
            # ontsnapt de exception uit de generator, is de HTTP-status allang
            # 200 verstuurd, en houdt de client een afgekapte stream over: geen
            # antwoord, geen melding, geen `done` — een eeuwig draaiende spinner.
            # `except Exception` laat CancelledError/GeneratorExit door, zodat
            # een client die wegvalt de stream nog steeds gewoon afbreekt.
            # Alleen een échte SDK-fout toeschrijven aan het AI-model; al het
            # overige komt uit de assistent zelf en verdient een eigen code,
            # anders zoekt iedereen die dit onderzoekt in de verkeerde hoek.
            if isinstance(e, anthropic.APIError | openai.APIError | TimeoutError):
                fout = classificeer_llm_fout(
                    e, llm, VLAM_TIMEOUT if llm == "vlam" else CLAUDE_TIMEOUT
                )
            else:
                fout = maak_fout("HOST_FOUT")
            logger.error("Onverwachte fout in de chat-stream [%s]: %s", fout.code, e)
            yield naar_event(fout)

        yield {"type": "done"}

    # ------------------------------------------------------------------
    # Claude (Anthropic API) — agentic loop met MCP-tools
    # ------------------------------------------------------------------

    async def _chat_claude_stream(
        self,
        messages: list[dict],
        session_kvk: str,
        claude,
        feiten: dict,
        regel_status: dict | None = None,
        conv_key: str = "",
    ) -> AsyncGenerator[dict, None]:
        """Claude agentic loop die status-events yieldt.

        `claude` is de client van dít verzoek (MVP-02) en is verplicht: geen
        stille terugval op de gedeelde server-client, zodat een vergeten
        argument niet ongemerkt de verkeerde sleutel gebruikt. `feiten` is de
        sessiekaart uit `self.feiten` (by reference) — alleen `.update()`en.
        `regel_status` is de uitkomst van de regelloop van vóór deze beurt
        (`_regel_status`); `None` als die niet gedraaid is (CLI-transport).
        `conv_key` gaat naar `_bron_aanroep_gated` (PDR-008): roept het model
        zelf `netbeheerder__verbruik` aan, dan weigert die poort de aanroep
        zolang toestemming niet vastligt — zie `_execute_tools`.
        """
        tools = self.registry.get_anthropic_tools()
        system_prompt = self._system_prompt("claude", regel_status=regel_status)

        # Per beurt (niet per iteratie): de tool-aanroep en het uiteindelijke
        # tekstantwoord zitten meestal in verschillende agentic-stappen.
        maatregelen_deze_beurt = None
        max_iterations = 10
        for _ in range(max_iterations):
            api_kwargs = {
                "model": CLAUDE_MODEL,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
            }
            if tools:
                api_kwargs["tools"] = tools

            try:
                response = await asyncio.wait_for(
                    claude.messages.create(**api_kwargs),
                    timeout=CLAUDE_TIMEOUT,
                )
                _log_tokens("claude", response)
            except Exception as e:
                fout = classificeer_llm_fout(e, "claude", CLAUDE_TIMEOUT)
                logger.error("Claude-call mislukt [%s]: %s", fout.code, e)
                yield naar_event(fout)
                return

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = [b for b in assistant_content if b.type == "tool_use"]
            if not tool_uses:
                text = "\n".join(
                    b.text for b in assistant_content if hasattr(b, "text")
                )
                for event in _antwoord_events(
                    text, _is_afgekapt(response), feiten, maatregelen_deze_beurt
                ):
                    yield event
                return

            # Het `tool`-event gaat pas ná de aanroep uit (niet ervoor): de
            # PDR-008-poort in `_execute_tools` kan een aanroep weigeren, en
            # dan is de bron niet geraadpleegd - een event vooraf zou dat aan
            # de client melden alsof het wel gebeurde.
            tool_results, bronfouten, aangeroepen = await self._execute_tools(
                tool_uses, session_kvk, conv_key
            )
            for naam in aangeroepen:
                yield {"type": "tool", "message": _tool_label(naam), "tool": naam}
            for fout in bronfouten:
                yield naar_event(fout, "bron_fout")
            # Emit lopende zaak als case-event bij succesvolle indiening
            for tu, tr in zip(tool_uses, tool_results, strict=True):
                inhoud = tr.get("content", "")
                feiten.update(feiten_uit_tool(tu.name, inhoud))
                maatregelen_deze_beurt = (
                    maatregelen_voor_event(tu.name, inhoud) or maatregelen_deze_beurt
                )
                zaak = _extract_lopende_zaak(tu.name, inhoud)
                if zaak:
                    yield {"type": "case", "data": zaak}
            messages.append({"role": "user", "content": tool_results})
            yield {"type": "status", "message": "Antwoord opstellen..."}

        yield naar_event(maak_fout("LLM_MAX_STAPPEN"))

    async def _chat_vlam_stream(
        self,
        messages: list[dict],
        session_kvk: str,
        vlam,
        feiten: dict,
        regel_status: dict | None = None,
        conv_key: str = "",
    ) -> AsyncGenerator[dict, None]:
        """VLAM agentic loop (native OpenAI tool-calling) die status-events yieldt.

        `vlam` is de client van dít verzoek (MVP-02), verplicht meegegeven.
        `feiten` is de sessiekaart uit `self.feiten` (by reference) — alleen
        `.update()`en. `regel_status` is de uitkomst van de regelloop van vóór
        deze beurt (`_regel_status`); `None` als die niet gedraaid is
        (CLI-transport). `conv_key` gaat naar `_bron_aanroep_gated` (PDR-008):
        roept het model zelf `netbeheerder__verbruik` aan, dan weigert die
        poort de aanroep zolang toestemming niet vastligt.
        """
        tools_openai = self.registry.get_openai_tools()
        system_prompt = self._system_prompt("vlam", regel_status=regel_status)
        openai_messages = self._to_openai_messages(messages, system_prompt)

        # Per beurt (niet per iteratie): de tool-aanroep en het uiteindelijke
        # tekstantwoord zitten meestal in verschillende agentic-stappen.
        maatregelen_deze_beurt = None
        max_iterations = 10
        for _ in range(max_iterations):
            api_kwargs = {
                "model": VLAM_MODEL_ID,
                "max_tokens": 4096,
                "messages": openai_messages,
            }
            if tools_openai:
                api_kwargs["tools"] = tools_openai

            try:
                response = await asyncio.wait_for(
                    vlam.chat.completions.create(**api_kwargs),
                    timeout=VLAM_TIMEOUT,
                )
                _log_tokens("vlam", response)
            except Exception as e:
                fout = classificeer_llm_fout(e, "vlam", VLAM_TIMEOUT)
                logger.error("VLAM-call mislukt [%s]: %s", fout.code, e)
                yield naar_event(fout)
                return

            # Een OpenAI-compatibele proxy kan een respons zonder choices geven
            # (bv. bij een content-filter). Zonder deze guard klapt `choices[0]`
            # met een IndexError buiten de except hierboven, en breekt de stream
            # af zonder antwoord, zonder foutmelding en zonder `done`.
            if not response.choices:
                logger.error("VLAM gaf een respons zonder choices")
                yield naar_event(maak_fout("LLM_ONBEKEND"))
                return

            choice = response.choices[0]
            assistant_msg = choice.message

            openai_messages.append(assistant_msg.model_dump(exclude_none=True))
            messages.append(
                {"role": "assistant", "content": assistant_msg.content or ""}
            )

            tool_calls = assistant_msg.tool_calls
            if not tool_calls:
                for event in _antwoord_events(
                    assistant_msg.content or "",
                    _is_afgekapt(choice),
                    feiten,
                    maatregelen_deze_beurt,
                ):
                    yield event
                return

            for tc in tool_calls:
                tool_key = tc.function.name
                arguments = _lees_tool_argumenten(tc.function.arguments)
                if arguments is None:
                    # Geen event: het model corrigeert dit zelf in de volgende
                    # ronde en het gesprek sluit gewoon af met een `answer`. Een
                    # melding zou een storing aankondigen die er niet is.
                    fout = maak_fout("LLM_TOOLCALL_ONLEESBAAR")
                    openai_messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": naar_llm(fout)}
                    )
                    continue
                arguments = _inject_session_kvk(tool_key, arguments, session_kvk)
                logger.info("Tool-aanroep [vlam]: %s (velden: %s)", tool_key, _arg_keys(arguments))
                # Het `tool`-event gaat pas ná de aanroep uit: de PDR-008-poort
                # kan hem weigeren, en dan is de bron niet geraadpleegd - een
                # event vooraf zou dat aan de client melden alsof het wel gebeurde.
                result, fout, aangeroepen = await self._bron_aanroep_gated(
                    partial(self.registry.call_tool, tool_key, arguments),
                    tool_key,
                    arguments,
                    conv_key,
                )
                if aangeroepen:
                    yield {
                        "type": "tool",
                        "message": _tool_label(tool_key),
                        "tool": tool_key,
                    }
                if fout:
                    yield naar_event(fout, "bron_fout")

                feiten.update(feiten_uit_tool(tool_key, result))
                maatregelen_deze_beurt = (
                    maatregelen_voor_event(tool_key, result) or maatregelen_deze_beurt
                )
                zaak = _extract_lopende_zaak(tool_key, result)
                if zaak:
                    yield {"type": "case", "data": zaak}

                openai_messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )

            yield {"type": "status", "message": "Antwoord opstellen..."}

        yield naar_event(maak_fout("LLM_MAX_STAPPEN"))

    # ------------------------------------------------------------------
    # CLI-modus — zelfde LLM (Claude), maar tools via CLI i.p.v. MCP
    # ------------------------------------------------------------------

    async def _chat_cli_stream(
        self, messages: list[dict], session_kvk: str, claude, feiten: dict
    ) -> AsyncGenerator[dict, None]:
        """Claude agentic loop die CLI-tools aanroept i.p.v. MCP-servers.

        `claude` is de client van dít verzoek (MVP-02), verplicht meegegeven.
        `feiten` is de sessiekaart uit `self.feiten` (by reference) — alleen
        `.update()`en.
        """
        tools = CLI_TOOL_DEFINITIONS_ANTHROPIC
        system_prompt = self._system_prompt(
            "claude", has_tools=True, bronnen_offline=self.cli_bronnen_offline, cli_transport=True
        )

        max_iterations = 10
        for _ in range(max_iterations):
            api_kwargs = {
                "model": CLAUDE_MODEL,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
            }
            if tools:
                api_kwargs["tools"] = tools

            try:
                response = await asyncio.wait_for(
                    claude.messages.create(**api_kwargs),
                    timeout=CLAUDE_TIMEOUT,
                )
                _log_tokens("claude", response)
            except Exception as e:
                fout = classificeer_llm_fout(e, "claude", CLAUDE_TIMEOUT)
                logger.error("Claude-call (CLI-modus) mislukt [%s]: %s", fout.code, e)
                yield naar_event(fout)
                return

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = [b for b in assistant_content if b.type == "tool_use"]
            if not tool_uses:
                text = "\n".join(
                    b.text for b in assistant_content if hasattr(b, "text")
                )
                for event in _antwoord_events(text, _is_afgekapt(response), feiten):
                    yield event
                return

            tool_results = []
            for tu in tool_uses:
                yield {
                    "type": "tool",
                    "message": f"CLI: {_tool_label(tu.name)}",
                    "tool": tu.name,
                }

                cli_args = _inject_session_kvk(tu.name, tu.input, session_kvk)
                logger.info("CLI tool-aanroep: %s (velden: %s)", tu.name, _arg_keys(cli_args))
                result, fout = await _bron_aanroep(
                    partial(execute_cli_tool, tu.name, cli_args), tu.name, cli_args
                )
                if fout:
                    yield naar_event(fout, "bron_fout")

                feiten.update(feiten_uit_tool(tu.name, result))
                zaak = _extract_lopende_zaak(tu.name, result)
                if zaak:
                    yield {"type": "case", "data": zaak}

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": result,
                    }
                )

            messages.append({"role": "user", "content": tool_results})
            yield {"type": "status", "message": "Antwoord opstellen..."}

        yield naar_event(maak_fout("LLM_MAX_STAPPEN"))

    # ------------------------------------------------------------------
    # VLAM + CLI — native tool-calling met CLI-tools i.p.v. MCP
    # ------------------------------------------------------------------

    async def _chat_vlam_cli_stream(
        self, messages: list[dict], session_kvk: str, vlam, feiten: dict
    ) -> AsyncGenerator[dict, None]:
        """VLAM agentic loop (native tool-calling) met CLI-tools i.p.v. MCP.

        `vlam` is de client van dít verzoek (MVP-02), verplicht meegegeven.
        `feiten` is de sessiekaart uit `self.feiten` (by reference) — alleen
        `.update()`en.
        """
        tools_openai = CLI_TOOL_DEFINITIONS_OPENAI
        system_prompt = self._system_prompt(
            "vlam", has_tools=True, bronnen_offline=self.cli_bronnen_offline, cli_transport=True
        )
        openai_messages = self._to_openai_messages(messages, system_prompt)

        max_iterations = 10
        for _ in range(max_iterations):
            try:
                response = await asyncio.wait_for(
                    vlam.chat.completions.create(
                        model=VLAM_MODEL_ID,
                        max_tokens=4096,
                        messages=openai_messages,
                        tools=tools_openai,
                    ),
                    timeout=VLAM_TIMEOUT,
                )
                _log_tokens("vlam", response)
            except Exception as e:
                fout = classificeer_llm_fout(e, "vlam", VLAM_TIMEOUT)
                logger.error("VLAM CLI-call mislukt [%s]: %s", fout.code, e)
                yield naar_event(fout)
                return

            if not response.choices:
                logger.error("VLAM gaf een respons zonder choices (CLI-modus)")
                yield naar_event(maak_fout("LLM_ONBEKEND"))
                return

            choice = response.choices[0]
            assistant_msg = choice.message
            openai_messages.append(assistant_msg.model_dump(exclude_none=True))
            messages.append(
                {"role": "assistant", "content": assistant_msg.content or ""}
            )

            tool_calls = assistant_msg.tool_calls
            if not tool_calls:
                for event in _antwoord_events(
                    assistant_msg.content or "", _is_afgekapt(choice), feiten
                ):
                    yield event
                return

            for tc in tool_calls:
                tool_key = tc.function.name
                yield {
                    "type": "tool",
                    "message": f"CLI: {_tool_label(tool_key)}",
                    "tool": tool_key,
                }

                arguments = _lees_tool_argumenten(tc.function.arguments)
                if arguments is None:
                    # Geen event: het model corrigeert dit zelf in de volgende
                    # ronde en het gesprek sluit gewoon af met een `answer`. Een
                    # melding zou een storing aankondigen die er niet is.
                    fout = maak_fout("LLM_TOOLCALL_ONLEESBAAR")
                    openai_messages.append(
                        {"role": "tool", "tool_call_id": tc.id, "content": naar_llm(fout)}
                    )
                    continue
                arguments = _inject_session_kvk(tool_key, arguments, session_kvk)
                logger.info("CLI tool-aanroep [vlam]: %s (velden: %s)", tool_key, _arg_keys(arguments))
                result, fout = await _bron_aanroep(
                    partial(execute_cli_tool, tool_key, arguments), tool_key, arguments
                )
                if fout:
                    yield naar_event(fout, "bron_fout")

                feiten.update(feiten_uit_tool(tool_key, result))
                zaak = _extract_lopende_zaak(tool_key, result)
                if zaak:
                    yield {"type": "case", "data": zaak}

                openai_messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": result}
                )

            yield {"type": "status", "message": "Antwoord opstellen..."}

        yield naar_event(maak_fout("LLM_MAX_STAPPEN"))

    # ------------------------------------------------------------------
    # Claude (Anthropic API) — blocking (non-streaming, backwards-compatibel)
    # ------------------------------------------------------------------

    async def _chat_claude(
        self,
        messages: list[dict],
        session_kvk: str,
        claude,
        feiten: dict,
        regel_status: dict | None = None,
        conv_key: str = "",
    ) -> str:
        """`claude` is de client van dít verzoek (MVP-02), verplicht meegegeven.

        `feiten` is de sessiekaart uit `self.feiten` (by reference) — alleen
        `.update()`en. `regel_status` is de uitkomst van de regelloop van vóór
        deze beurt (`_regel_status`). `conv_key` gaat naar `_execute_tools`,
        dat de PDR-008-poort toepast op elke tool-aanroep van het model.
        """
        if not claude.api_key:
            return _geen_sleutel_fout("claude").tekst
        tools = self.registry.get_anthropic_tools()
        system_prompt = self._system_prompt("claude", regel_status=regel_status)

        max_iterations = 10
        for _ in range(max_iterations):
            api_kwargs = {
                "model": CLAUDE_MODEL,
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": messages,
            }
            if tools:
                api_kwargs["tools"] = tools

            try:
                response = await asyncio.wait_for(
                    claude.messages.create(**api_kwargs),
                    timeout=CLAUDE_TIMEOUT,
                )
                _log_tokens("claude", response)
            except Exception as e:
                fout = classificeer_llm_fout(e, "claude", CLAUDE_TIMEOUT)
                logger.error("Claude-call mislukt [%s]: %s", fout.code, e)
                return fout.tekst

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            tool_uses = [b for b in assistant_content if b.type == "tool_use"]
            if not tool_uses:
                text = "\n".join(b.text for b in assistant_content if hasattr(b, "text"))
                return _antwoord_tekst(text, _is_afgekapt(response), feiten)

            tool_results, _, _ = await self._execute_tools(tool_uses, session_kvk, conv_key)
            for tu, tr in zip(tool_uses, tool_results, strict=True):
                feiten.update(feiten_uit_tool(tu.name, tr.get("content", "")))
            messages.append({"role": "user", "content": tool_results})

        return maak_fout("LLM_MAX_STAPPEN").tekst

    # ------------------------------------------------------------------
    # VLAM (OpenAI-compatibele API — UbiOps/Mistral) — agentic loop
    # ------------------------------------------------------------------

    async def _chat_vlam(
        self,
        messages: list[dict],
        session_kvk: str,
        vlam,
        feiten: dict,
        regel_status: dict | None = None,
        conv_key: str = "",
    ) -> str:
        """`vlam` is de client van dít verzoek (MVP-02), verplicht meegegeven.

        `feiten` is de sessiekaart uit `self.feiten` (by reference) — alleen
        `.update()`en. `regel_status` is de uitkomst van de regelloop van vóór
        deze beurt (`_regel_status`). `conv_key` gaat naar
        `_bron_aanroep_gated`, dat de PDR-008-poort toepast op elke
        tool-aanroep van het model.
        """
        tools_openai = self.registry.get_openai_tools()
        system_prompt = self._system_prompt("vlam", regel_status=regel_status)
        openai_messages = self._to_openai_messages(messages, system_prompt)

        max_iterations = 10
        for _ in range(max_iterations):
            api_kwargs = {
                "model": VLAM_MODEL_ID,
                "max_tokens": 4096,
                "messages": openai_messages,
            }
            if tools_openai:
                api_kwargs["tools"] = tools_openai

            try:
                response = await asyncio.wait_for(
                    vlam.chat.completions.create(**api_kwargs),
                    timeout=VLAM_TIMEOUT,
                )
                _log_tokens("vlam", response)
            except Exception as e:
                fout = classificeer_llm_fout(e, "vlam", VLAM_TIMEOUT)
                logger.error("VLAM-call mislukt [%s]: %s", fout.code, e)
                return fout.tekst

            if not response.choices:
                logger.error("VLAM gaf een respons zonder choices")
                return maak_fout("LLM_ONBEKEND").tekst

            choice = response.choices[0]
            assistant_msg = choice.message

            openai_messages.append(assistant_msg.model_dump(exclude_none=True))
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                }
            )

            tool_calls = assistant_msg.tool_calls
            if not tool_calls:
                return _antwoord_tekst(assistant_msg.content or "", _is_afgekapt(choice), feiten)

            for tc in tool_calls:
                tool_key = tc.function.name
                arguments = _lees_tool_argumenten(tc.function.arguments)
                if arguments is None:
                    result = naar_llm(maak_fout("LLM_TOOLCALL_ONLEESBAAR"))
                else:
                    arguments = _inject_session_kvk(tool_key, arguments, session_kvk)
                    logger.info(
                        "Tool-aanroep [vlam]: %s (velden: %s)", tool_key, _arg_keys(arguments)
                    )
                    result, _, _ = await self._bron_aanroep_gated(
                        partial(self.registry.call_tool, tool_key, arguments),
                        tool_key,
                        arguments,
                        conv_key,
                    )

                feiten.update(feiten_uit_tool(tool_key, result))
                openai_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    }
                )

        return maak_fout("LLM_MAX_STAPPEN").tekst

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _bron_aanroep_gated(
        self, aanroep, tool_key: str, arguments: dict, conv_key: str
    ) -> tuple[str, object, bool]:
        """`_bron_aanroep`, met de PDR-008-poort voor de Business Wallet ervoor.

        Dit is de enige plek waar een MCP-tool-aanroep de registry bereikt —
        model én regelloop lopen hier allebei doorheen. Zolang
        `self.toestemming[conv_key]` niet is vastgelegd, komt
        `netbeheerder__verbruik` de poort niet door: geen bron-aanroep, maar
        een tool-resultaat met de catalogusmelding, alsof de bron zelf weigerde.

        Vóór deze poort kon een geslaagde aanroep de vlag zetten die hij zelf
        nodig had om door te komen - een aanroep die zichzelf autoriseert.
        Prompt-instructies alleen bleken dat niet te stoppen: het model riep de
        tool zelf aan zodra de systeemprompt liet doorschemeren dat er verbruik
        nodig was. Deze poort staat daarom in de host, niet in de prompt.

        Geeft `(resultaat, fout_of_None, aangeroepen)` terug. `aangeroepen` is
        False zodra de poort heeft geweigerd: de bron is dan niet geraadpleegd,
        en de aanroeper mag daar geen `tool`-event voor tonen - dat zou de
        client iets laten zien dat niet gebeurd is.
        """
        if tool_key == "netbeheerder__verbruik" and not self.toestemming.get(conv_key, False):
            fout = maak_fout("TOESTEMMING_VEREIST", bron="netbeheerder")
            logger.warning(
                "Business Wallet geweigerd zonder vastgelegde toestemming [conv_key=%r]",
                conv_key,
            )
            return naar_llm(fout), fout, False
        resultaat, fout = await _bron_aanroep(aanroep, tool_key, arguments)
        return resultaat, fout, True

    async def _execute_tools(
        self, tool_uses, session_kvk: str, conv_key: str = ""
    ) -> tuple[list[dict], list, list[str]]:
        """Voer Anthropic tool_use-blokken uit via MCP-servers.

        Geeft de tool-resultaten terug plus de bronfouten die onderweg optraden,
        zodat de stream ze als `bron_fout`-event kan tonen terwijl het gesprek
        gewoon doorloopt. `conv_key` gaat naar `_bron_aanroep_gated`, dat de
        PDR-008-poort toepast (netbeheerder__verbruik zonder vastgelegde
        toestemming komt hier nooit door naar de registry).

        De derde waarde (`aangeroepen`) draagt de namen van de tools die de
        poort daadwerkelijk doorliet: alleen daarvoor mag de aanroeper een
        `tool`-event tonen. Een geweigerde aanroep staat wél in `tool_uses`
        (het model deed de poging), maar hoort hier niet in - anders meldt de
        UI een raadpleging die nooit plaatsvond.
        """
        tool_results = []
        bronfouten = []
        aangeroepen = []
        for tool_use in tool_uses:
            arguments = _inject_session_kvk(tool_use.name, tool_use.input, session_kvk)
            logger.info("Tool-aanroep [claude]: %s (velden: %s)", tool_use.name, _arg_keys(arguments))
            result, fout, ok = await self._bron_aanroep_gated(
                partial(self.registry.call_tool, tool_use.name, arguments),
                tool_use.name,
                arguments,
                conv_key,
            )
            if ok:
                aangeroepen.append(tool_use.name)
            if fout:
                bronfouten.append(fout)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use.id,
                    "content": result,
                }
            )
        return tool_results, bronfouten, aangeroepen

    @staticmethod
    def _to_openai_messages(messages: list[dict], system_prompt: str) -> list[dict]:
        """Converteer intern berichtformaat naar OpenAI-messages (voor eerste call)."""
        openai_msgs = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                openai_msgs.append({"role": msg["role"], "content": content})
        return openai_msgs

    @staticmethod
    def _conv_key(session_kvk: str, session_id: str, mode: str) -> str:
        """Bucketsleutel voor de gespreksgeschiedenis.

        Gepartitioneerd op identiteit (KvK) én het client-gekozen session_id
        (PDR-009): zo kan een geldig token met andermans session_id nooit diens
        historie — met bedrijfsdata — inzien. `|` als scheidingsteken zodat de
        mode (die zelf een `:` bevat, bv. `cli:vlam`) eenduidig blijft.
        """
        return f"{session_kvk}|{session_id}|{mode}"

    def clear_session(self, session_kvk: str, session_id: str):
        """Wis de gespreksgeschiedenis van een sessie (alle modi).

        Gescoped op identiteit (session_kvk): wist alleen de eigen buckets, niet
        die van een andere gebruiker met hetzelfde session_id. De sleutels worden
        exact herbouwd i.p.v. geparsed, zodat een `|` in het session_id niet stoort.
        """
        for mode in ("vlam", "claude", "cli:vlam", "cli:claude"):
            self.conversations.pop(self._conv_key(session_kvk, session_id, mode), None)

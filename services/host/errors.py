"""Foutcatalogus: elke faalsituatie krijgt een eigen, actionabele melding.

Waarom een catalogus en niet een `str(e)` per plek: de host faalde overal met
dezelfde zin ("De assistent is op dit moment niet bereikbaar"), of gaf de
exception-tekst door aan het LLM. De gebruiker wist dan niet wat er misging en
al helemaal niet wat hij eraan kon doen.

Elke melding bestaat uit twee delen:
  - `bericht` — wat er gebeurde, in gewone taal, zonder jargon of foutcode;
  - `actie`   — wat de gebruiker nu kan doen.

Het `code`-veld is voor de logs, de UI en de tests; het komt nooit in een zin
terecht. Exception-teksten, paden en URL's gaan naar de log, niet naar de
gebruiker en niet naar het LLM.
"""

import json
import logging
from dataclasses import dataclass, replace

import anthropic
import openai

logger = logging.getLogger("vlam.errors")


@dataclass(frozen=True)
class FoutMelding:
    """Eén faalsituatie, klaar om te tonen."""

    code: str
    bericht: str
    actie: str
    bron: str | None = None
    herstelbaar: bool = True
    http_status: int = 502

    @property
    def tekst(self) -> str:
        """De volledige melding als één string (vult het `message`-veld)."""
        return f"{self.bericht} {self.actie}".strip()


# --- Bronnen -----------------------------------------------------------------

# Hoe we een bron aan de gebruiker noemen, en waar hij terecht kan als de bron
# uitvalt. De sleutel is het server-voorvoegsel uit de tool-key (`koop__zoek...`).
BRON_LABELS: dict[str, str] = {
    "kvk": "het KvK Handelsregister",
    "koop": "de regelgeving-database (KOOP Regelingenbank)",
    "regelrecht": "de regeltoets (RegelRecht)",
    "rvo": "RVO",
    "netbeheerder": "uw Business Wallet (energiegegevens van de netbeheerder)",
}

BRON_ALTERNATIEF: dict[str, str] = {
    "kvk": "kvk.nl",
    "koop": "wetten.overheid.nl",
    "regelrecht": "rvo.nl",
    "rvo": "rvo.nl",
    "netbeheerder": "uw energierekening of het portaal van uw netbeheerder",
}


def bron_uit_tool(tool_key: str) -> str | None:
    """Haal de bronnaam uit een tool-key (`koop__zoek_regelgeving` -> `koop`)."""
    bron = str(tool_key or "").split("__", 1)[0]
    return bron if bron in BRON_LABELS else None


# --- Catalogus ---------------------------------------------------------------

# Invulwaarden die een melding nodig kan hebben. Ontbreekt er één bij het
# opbouwen, dan valt de zin terug op een neutrale formulering in plaats van een
# KeyError: een foutmelding mag nooit zélf de oorzaak van een fout worden.
_STANDAARD_INVULLING: dict[str, str] = {
    "bron_label": "de bron",
    "alternatief": "de website van de betreffende instantie",
    "seconden": "de ingestelde tijd",
    "maximum": "toegestaan",
    "veld": "een verplicht gegeven",
    "zoekterm": "uw zoekopdracht",
}


class _Invulling(dict):
    """Format-mapping die onbekende placeholders neutraal invult."""

    def __missing__(self, sleutel: str) -> str:
        return _STANDAARD_INVULLING.get(sleutel, "")


FOUTEN: dict[str, FoutMelding] = {
    # --- Het AI-model ---
    "LLM_TIMEOUT": FoutMelding(
        code="LLM_TIMEOUT",
        bericht="Het opstellen van het antwoord duurde langer dan {seconden}.",
        actie="Probeer het opnieuw, of stel uw vraag korter en concreter.",
        http_status=504,
    ),
    "LLM_GEEN_SLEUTEL": FoutMelding(
        code="LLM_GEEN_SLEUTEL",
        bericht="Er is geen API-sleutel ingesteld voor dit AI-model.",
        actie="Vul uw sleutel in via het instellingenpaneel en verstuur de vraag opnieuw.",
        herstelbaar=False,
        http_status=503,
    ),
    "LLM_SLEUTEL_ONGELDIG": FoutMelding(
        code="LLM_SLEUTEL_ONGELDIG",
        bericht="De API-sleutel wordt niet geaccepteerd door het AI-model.",
        actie="Controleer de sleutel in het instellingenpaneel en probeer het opnieuw.",
        herstelbaar=False,
        http_status=401,
    ),
    "LLM_TE_DRUK": FoutMelding(
        code="LLM_TE_DRUK",
        bericht="Het AI-model verwerkt op dit moment te veel verzoeken.",
        actie="Probeer het over een minuut opnieuw.",
        http_status=429,
    ),
    "LLM_OVERBELAST": FoutMelding(
        code="LLM_OVERBELAST",
        bericht="Het AI-model is tijdelijk niet beschikbaar.",
        actie="Probeer het over een minuut opnieuw.",
        http_status=503,
    ),
    "LLM_ONBEREIKBAAR": FoutMelding(
        code="LLM_ONBEREIKBAAR",
        bericht="Er is geen verbinding met het AI-model.",
        actie="Controleer uw netwerkverbinding en probeer het opnieuw.",
        http_status=503,
    ),
    "LLM_GESPREK_TE_LANG": FoutMelding(
        code="LLM_GESPREK_TE_LANG",
        bericht="Dit gesprek is te lang geworden om in één keer te verwerken.",
        actie=(
            "Begin een nieuw gesprek met de knop 'gesprek wissen', "
            "en stel uw vraag daarna opnieuw."
        ),
        herstelbaar=False,
        http_status=400,
    ),
    "LLM_VERZOEK_ONGELDIG": FoutMelding(
        code="LLM_VERZOEK_ONGELDIG",
        bericht="Het AI-model kon dit verzoek niet verwerken.",
        actie=(
            "Formuleer uw vraag anders, of begin een nieuw gesprek "
            "met de knop 'gesprek wissen'."
        ),
        http_status=400,
    ),
    "LLM_MODEL_ONBEKEND": FoutMelding(
        code="LLM_MODEL_ONBEKEND",
        bericht="Het ingestelde AI-model bestaat niet (meer).",
        actie=(
            "Dit is een instelling van de beheerder. "
            "Meld het bij de beheerder van deze omgeving."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "LLM_MAX_STAPPEN": FoutMelding(
        code="LLM_MAX_STAPPEN",
        bericht="Uw vraag vroeg meer stappen dan de assistent in één keer kan zetten.",
        actie=(
            "Splits uw vraag op. Bijvoorbeeld eerst 'geldt de energiebesparingsplicht "
            "voor mij?' en daarna 'welke maatregelen gelden er dan?'."
        ),
        http_status=504,
    ),
    "LLM_TOOLCALL_ONLEESBAAR": FoutMelding(
        code="LLM_TOOLCALL_ONLEESBAAR",
        bericht="Het AI-model gaf een onleesbare opdracht aan een bron.",
        actie="Probeer het opnieuw, en formuleer uw vraag eventueel iets anders.",
    ),
    "LLM_ONBEKEND": FoutMelding(
        code="LLM_ONBEKEND",
        bericht="Het AI-model gaf een onverwachte reactie.",
        actie="Probeer het opnieuw. Blijft het misgaan, meld het bij de beheerder.",
    ),
    # --- De bronnen ---
    "SOURCE_UNAVAILABLE": FoutMelding(
        code="SOURCE_UNAVAILABLE",
        bericht="{bron_label} is op dit moment niet bereikbaar.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=503,
    ),
    "API_FOUT": FoutMelding(
        code="API_FOUT",
        bericht="{bron_label} gaf een fout terug op de aanvraag.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=502,
    ),
    "BRON_NIET_GESTART": FoutMelding(
        code="BRON_NIET_GESTART",
        bericht="{bron_label} is bij het starten van de assistent niet beschikbaar gekomen.",
        actie=(
            "Meld dit bij de beheerder van deze omgeving. "
            "De overige bronnen werken wel; u kunt daar wel vragen over stellen."
        ),
        herstelbaar=False,
        http_status=503,
    ),
    "BRON_NIET_BESCHIKBAAR": FoutMelding(
        code="BRON_NIET_BESCHIKBAAR",
        bericht="{bron_label} kon de gevraagde gegevens niet leveren.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=503,
    ),
    "NIET_GEVONDEN": FoutMelding(
        code="NIET_GEVONDEN",
        bericht="In {bron_label} is niets gevonden voor {zoekterm}.",
        actie="Probeer een ander of algemener trefwoord.",
        herstelbaar=False,
        http_status=404,
    ),
    "INPUT_INVALID": FoutMelding(
        code="INPUT_INVALID",
        bericht="De zoekopdracht voor {bron_label} was niet compleet.",
        actie="Noem een trefwoord waarop gezocht kan worden, bijvoorbeeld 'energiebesparing'.",
        herstelbaar=False,
        http_status=400,
    ),
    "ONTBREKEND_VELD": FoutMelding(
        code="ONTBREKEND_VELD",
        bericht="Er ontbreekt een gegeven om {bron_label} te kunnen raadplegen: {veld}.",
        actie="Geef dit gegeven door, dan gaat de assistent verder.",
        herstelbaar=False,
        http_status=400,
    ),
    "ONTBREKENDE_VELDEN": FoutMelding(
        code="ONTBREKENDE_VELDEN",
        bericht="Er ontbreken gegevens om {bron_label} te kunnen raadplegen: {veld}.",
        actie="Geef deze gegevens door, dan gaat de assistent verder.",
        herstelbaar=False,
        http_status=400,
    ),
    "EXECUTION_ERROR": FoutMelding(
        code="EXECUTION_ERROR",
        bericht="De regeltoets kon niet worden uitgevoerd op de aangeleverde gegevens.",
        actie=(
            "Probeer het opnieuw. Blijft het misgaan, kijk dan op rvo.nl "
            "of neem contact op met RVO."
        ),
        bron="regelrecht",
        http_status=502,
    ),
    "WET_NIET_TOEGESTAAN": FoutMelding(
        code="WET_NIET_TOEGESTAAN",
        bericht="Deze regeling kan de assistent niet toetsen.",
        actie=(
            "De assistent toetst op dit moment alleen de energiebesparings- "
            "en informatieplicht. Kijk voor andere regelingen op rvo.nl."
        ),
        bron="regelrecht",
        herstelbaar=False,
        http_status=404,
    ),
    "CLI_FOUT": FoutMelding(
        code="CLI_FOUT",
        bericht="{bron_label} kon niet worden geraadpleegd.",
        actie="Probeer het over een minuut opnieuw, of kijk rechtstreeks op {alternatief}.",
        http_status=502,
    ),
    "ONBEKENDE_TOOL": FoutMelding(
        code="ONBEKENDE_TOOL",
        bericht="De assistent probeerde een bron te raadplegen die hier niet beschikbaar is.",
        actie=(
            "Stel uw vraag opnieuw. Blijft het misgaan, meld het bij de beheerder "
            "van deze omgeving."
        ),
        herstelbaar=False,
        http_status=501,
    ),
    "TOOL_ONVERWACHT": FoutMelding(
        code="TOOL_ONVERWACHT",
        bericht="{bron_label} gaf een onverwachte fout.",
        actie="Probeer het opnieuw. Blijft het misgaan, meld het bij de beheerder.",
    ),
    # --- De vraag van de gebruiker ---
    "GEEN_SESSIE": FoutMelding(
        code="GEEN_SESSIE",
        bericht=(
            "U bent niet ingelogd, dus de assistent kan uw bedrijfsgegevens niet gebruiken."
        ),
        actie=(
            "Log eerst in. Zonder geldige sessie raadpleegt de assistent "
            "geen overheidsbronnen."
        ),
        herstelbaar=False,
        http_status=401,
    ),
    "LEGE_VRAAG": FoutMelding(
        code="LEGE_VRAAG",
        bericht="Er is geen vraag meegestuurd.",
        actie=(
            "Typ uw vraag in het tekstvak en verstuur die opnieuw. Bijvoorbeeld: "
            "'Geldt de energiebesparingsplicht voor mijn bedrijf?'"
        ),
        herstelbaar=False,
        http_status=400,
    ),
    "VRAAG_TE_LANG": FoutMelding(
        code="VRAAG_TE_LANG",
        bericht="Uw vraag is langer dan {maximum}.",
        actie="Kort uw vraag in, of splits die op in meerdere vragen.",
        herstelbaar=False,
        http_status=413,
    ),
}


def maak_fout(code: str, **invulling) -> FoutMelding:
    """Bouw een `FoutMelding` uit de catalogus, met de placeholders ingevuld.

    Een onbekende code levert `LLM_ONBEKEND` op in plaats van een KeyError: een
    fout in de foutafhandeling mag het gesprek niet alsnog laten klappen.
    """
    sjabloon = FOUTEN.get(code)
    if sjabloon is None:
        logger.warning("Onbekende foutcode opgevraagd: %s", code)
        sjabloon = FOUTEN["LLM_ONBEKEND"]

    bron = invulling.pop("bron", None) or sjabloon.bron
    # Lege waarden weglaten, zodat de neutrale formulering uit
    # _STANDAARD_INVULLING inspringt in plaats van een gat in de zin.
    velden = _Invulling({k: v for k, v in invulling.items() if v not in (None, "")})
    if bron:
        velden.setdefault("bron_label", BRON_LABELS.get(bron, "de bron"))
        velden.setdefault(
            "alternatief",
            BRON_ALTERNATIEF.get(bron, _STANDAARD_INVULLING["alternatief"]),
        )
    return replace(
        sjabloon,
        bericht=_hoofdletter(sjabloon.bericht.format_map(velden)),
        actie=_hoofdletter(sjabloon.actie.format_map(velden)),
        bron=bron,
    )


def _hoofdletter(zin: str) -> str:
    """Begin de zin met een hoofdletter zonder de rest te raken.

    Nodig omdat een zin met een bron-label kan beginnen ("de regelgeving-
    database ..."); `str.capitalize()` zou de rest verkleinen (KvK -> kvk).
    """
    return zin[:1].upper() + zin[1:]


# --- Classificatie van LLM-fouten -------------------------------------------

# Volgorde telt: `APITimeoutError` erft van `APIConnectionError`, dus de
# specifieke variant moet eerst gecontroleerd worden. Beide SDK's gebruiken
# dezelfde klassenamen in hun eigen namespace.
_LLM_REGELS: tuple[tuple[tuple[type, ...], str], ...] = (
    ((anthropic.APITimeoutError, openai.APITimeoutError, TimeoutError), "LLM_TIMEOUT"),
    (
        (
            anthropic.AuthenticationError,
            openai.AuthenticationError,
            anthropic.PermissionDeniedError,
            openai.PermissionDeniedError,
        ),
        "LLM_SLEUTEL_ONGELDIG",
    ),
    ((anthropic.RateLimitError, openai.RateLimitError), "LLM_TE_DRUK"),
    ((anthropic.NotFoundError, openai.NotFoundError), "LLM_MODEL_ONBEKEND"),
    (
        (anthropic.InternalServerError, openai.InternalServerError),
        "LLM_OVERBELAST",
    ),
    (
        (anthropic.APIConnectionError, openai.APIConnectionError),
        "LLM_ONBEREIKBAAR",
    ),
)

# Signalen in een 400-melding die op een te lange context wijzen. Het type is
# hier hetzelfde (BadRequestError), alleen de tekst verschilt per aanbieder.
_CONTEXT_SIGNALEN = ("context", "token", "too long", "maximum length", "te lang")


def classificeer_llm_fout(
    exc: BaseException, backend: str = "", timeout: int | None = None
) -> FoutMelding:
    """Vertaal een exception uit de Anthropic/OpenAI-SDK naar een melding.

    Mapt op exceptie-type, niet op tekst: de tekst van een SDK verandert, het
    type niet. `backend` en `timeout` dienen alleen om de melding concreet te
    maken (hoeveel seconden er is gewacht).
    """
    seconden = f"{timeout} seconden" if timeout else ""
    for typen, code in _LLM_REGELS:
        if isinstance(exc, typen):
            return maak_fout(code, seconden=seconden)

    if isinstance(exc, anthropic.BadRequestError | openai.BadRequestError):
        tekst = str(exc).lower()
        if any(signaal in tekst for signaal in _CONTEXT_SIGNALEN):
            return maak_fout("LLM_GESPREK_TE_LANG")
        return maak_fout("LLM_VERZOEK_ONGELDIG")

    # Overige APIStatusError: val terug op de statuscode.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        if status >= 500:
            return maak_fout("LLM_OVERBELAST")
        if status in (401, 403):
            return maak_fout("LLM_SLEUTEL_ONGELDIG")
        if status == 429:
            return maak_fout("LLM_TE_DRUK")

    logger.warning(
        "Onverwacht type LLM-fout (%s) op backend %r", type(exc).__name__, backend
    )
    return maak_fout("LLM_ONBEKEND")


# --- Classificatie van bronfouten -------------------------------------------


def _veldnamen(payload: dict) -> str:
    """Beschrijf welk gegeven ontbreekt, zonder waarden uit de payload te tonen."""
    velden = payload.get("ontbrekende_gegevens") or payload.get("velden")
    if isinstance(velden, list) and velden:
        return ", ".join(str(v) for v in velden)
    return _STANDAARD_INVULLING["veld"]


def classificeer_tool_fout(
    tool_key: str, resultaat: object, zoekterm: str = ""
) -> FoutMelding | None:
    """Vertaal een tool-resultaat of -exception naar een melding.

    Geeft `None` terug als er niets aan de hand is, zodat de aanroeper dit als
    enkele check kan gebruiken op zowel geslaagde als mislukte aanroepen.
    """
    bron = bron_uit_tool(tool_key)
    invulling = {"bron": bron, "zoekterm": f"'{zoekterm}'" if zoekterm else ""}

    if isinstance(resultaat, BaseException):
        # FileNotFoundError eerst: die erft van OSError, maar betekent hier iets
        # anders (het serverscript zelf ontbreekt) dan een verbinding die wegvalt.
        if isinstance(resultaat, FileNotFoundError):
            return maak_fout("BRON_NIET_GESTART", **invulling)
        if isinstance(resultaat, TimeoutError | OSError):
            return maak_fout("SOURCE_UNAVAILABLE", **invulling)
        return maak_fout("TOOL_ONVERWACHT", **invulling)

    if not isinstance(resultaat, str) or not resultaat.strip().startswith("{"):
        return None

    try:
        payload = json.loads(resultaat)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None

    code = payload.get("error")
    if not isinstance(code, str) or not code:
        return None
    return maak_fout(code, veld=_veldnamen(payload), **invulling)


# --- Uitgaande vormen --------------------------------------------------------


def naar_event(fout: FoutMelding, type_: str = "error") -> dict:
    """Bouw de SSE-payload.

    `message` blijft de volledige zin, zodat een frontend die alleen dat veld
    kent blijft werken; `bericht`/`actie`/`code` maken een retry-knop en een
    bron-vermelding in de UI mogelijk.
    """
    return {
        "type": type_,
        "code": fout.code,
        "message": fout.tekst,
        "bericht": fout.bericht,
        "actie": fout.actie,
        "bron": fout.bron,
        "herstelbaar": fout.herstelbaar,
    }


_LLM_INSTRUCTIE = (
    "Geef de gebruikersmelding letterlijk door aan de gebruiker, in uw eigen "
    "antwoordopmaak. Verzin GEEN gegevens en gebruik GEEN eigen kennis als "
    "vervanging voor wat deze bron had moeten leveren."
)


def naar_llm(fout: FoutMelding) -> str:
    """Bouw het tool-resultaat dat het LLM krijgt.

    Bevat bewust geen exception-tekst, pad of URL: het LLM kan alles wat het
    hier ziet doorvertellen aan de gebruiker. De technische oorzaak staat in de
    log, niet in het gesprek.
    """
    return json.dumps(
        {
            "error": fout.code,
            "bron": fout.bron,
            "gebruikersmelding": fout.tekst,
            "instructie": _LLM_INSTRUCTIE,
        },
        ensure_ascii=False,
    )


def verrijk_llm(resultaat: str, fout: FoutMelding) -> str:
    """Voeg de gebruikersmelding toe aan een bron-antwoord dat al een fout meldt.

    Bewust verrijken en niet vervangen: sommige foutantwoorden dragen informatie
    die het LLM nodig heeft om verder te kunnen (RegelRecht meldt bijvoorbeeld
    in `ontbrekende_gegevens` welke feiten het nog aan de gebruiker moet vragen).
    Het `message`-veld van de bron gaat er wél uit: dat is een technische tekst
    die het LLM anders kan doorvertellen.
    """
    try:
        payload = json.loads(resultaat)
    except (json.JSONDecodeError, ValueError):
        return naar_llm(fout)
    if not isinstance(payload, dict):
        return naar_llm(fout)
    payload.pop("message", None)
    payload["gebruikersmelding"] = fout.tekst
    payload["instructie"] = _LLM_INSTRUCTIE
    return json.dumps(payload, ensure_ascii=False)

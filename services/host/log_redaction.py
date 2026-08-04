"""Vangnet: sleutel-achtige tokens uit logregels redigeren (MVP-02).

Dit is nadrukkelijk een *tweede* verdedigingslinie. De eerste is dat de host
geen sleutels logt: de foutafhandeling rond LLM-calls geeft generieke meldingen,
en `_valideer_sleutel` in `api.py` weigert waarden die anders in een
bibliotheek-foutmelding terecht zouden komen. Dit vangnet dekt wat we niet
vooraf zien: een onverwachte traceback, een toekomstige `exc_info=True`, of een
bibliotheek die een verzoek-header in zijn eigen debuglog zet.

Bewust géén generieke entropie-detectie: dat zou ook tool-resultaten, KvK-nummers
en sessie-ID's raken. We redigeren herkenbare sleutelvormen. Dat betekent ook
dat een sleutel in een onbekend formaat hier doorheen kan komen — het vangnet
vervangt de maatregelen erboven niet.

Aangehaakt op de *formatter* en niet op een `logging.Filter`: een filter draait
vóór het formatteren en ziet `record.exc_text` dan nog niet, dus tracebacks
zouden erdoorheen glippen.
"""

import logging
import re
from collections import Counter
from contextlib import contextmanager

REDACTIE = "[SLEUTEL-GEREDIGEERD]"

# Patroonherkenning dekt alleen sleutels met een herkenbare vorm. De
# VLAM-backend gebruikt UbiOps-tokens zonder zo'n voorvoegsel; die zouden er
# dus doorheen glippen — precies het geval waarin je denkt gedekt te zijn.
# Daarom kennen we de sleutels die op dit moment in gebruik zijn ook bij naam.
#
# Een Counter en geen set: twee gelijktijdige verzoeken kunnen dezelfde sleutel
# gebruiken, en dan mag het aflopen van het ene verzoek de registratie van het
# andere niet weghalen.
_geheimen: Counter = Counter()

# Twee drempels, omdat de herkomst verschilt.
#
# Een server-env-sleutel komt van de beheerder: die vertrouwen we, een lengte-
# check volstaat.
#
# Een sleutel uit een verzoek komt van de gebruiker, en die is dus door een
# aanvaller te kiezen. Zou elke opgegeven waarde geredigeerd worden, dan kan
# iemand gewone logtekst opgeven ("Tool-aanroep", een KvK-nummer) en die tijdens
# zijn eigen verzoek onzichtbaar maken — een vangnet tegen sleutellekken zou dan
# een middel worden om sporen te wissen. Daarom moet zo'n waarde er ook als een
# sleutel uitzien: lang genoeg, en een mengsel van letters en cijfers. Dat sluit
# natuurlijke logtekst uit en laat elke realistische API-sleutel door.
_MIN_GEHEIM_LENGTE = 8
_MIN_GEHEIM_LENGTE_ONVERTROUWD = 20


def _lijkt_op_een_sleutel(waarde: str) -> bool:
    """Streng genoeg dat gewone logtekst niet als 'geheim' geregistreerd raakt."""
    return (
        len(waarde) >= _MIN_GEHEIM_LENGTE_ONVERTROUWD
        and any(c.isdigit() for c in waarde)
        and any(c.isalpha() for c in waarde)
    )


def registreer_geheim(waarde: str) -> None:
    """Registreer een sleutel die voor de rest van het proces bestaat.

    Voor de server-env-sleutels: die leven zo lang als de host en kunnen in een
    bibliotheek-traceback opduiken. Herkomst is de beheerder, niet een verzoek.
    """
    if waarde and len(waarde) >= _MIN_GEHEIM_LENGTE:
        _geheimen[waarde] += 1


@contextmanager
def geheim_geregistreerd(waarde: str):
    """Registreer een sleutel uit een verzoek, alleen voor de duur daarvan.

    Zo houdt de redactie de sleutel niet langer vast dan de LLM-client zelf
    (PDR-010: een sleutel overleeft het verzoek niet). Waarden die niet op een
    sleutel lijken worden genegeerd — zie de toelichting bij de drempels.
    """
    if not waarde or not _lijkt_op_een_sleutel(waarde):
        yield
        return
    _geheimen[waarde] += 1
    try:
        yield
    finally:
        _geheimen[waarde] -= 1
        if _geheimen[waarde] <= 0:
            del _geheimen[waarde]

# Elk patroon vervangt óf de hele match, óf alles ná groep 1 (het "label").
#
# Alle herhalingen zijn bovenbegrensd, en dat is geen stijlkeuze. Een onbegrensde
# `*` of `{n,}` vóór een literal geeft polynomiaal terugkrabbelen: de eerdere
# versie van het api-key-patroon deed er op invoer als "a-a-a-…" viermaal zo lang
# over bij tweemaal zoveel tekens (16k tekens ≈ 1,7 s). Omdat er logregels zijn
# die door de gebruiker aangeleverde tekst bevatten, was dat een DoS-route: één
# verzoek van 64 KB hield de event loop ruim 30 seconden bezet. Met een
# bovengrens is het aantal terugkrabbelstappen per positie constant en dus
# lineair in de lengte van de regel. CodeQL merkt dit aan als py/polynomial-redos.
#
# De bovengrenzen liggen ruim boven elke realistische sleutel (256 tekens; een
# Anthropic-sleutel is er ~100).
_MAX = 256

_PATRONEN: list[tuple[re.Pattern, bool]] = [
    # Anthropic: sk-ant-... (ook admin-/oauth-varianten)
    (re.compile(rf"sk-ant-[A-Za-z0-9._\-]{{6,{_MAX}}}"), False),
    # OpenAI-stijl: sk-... / sk-proj-...
    (re.compile(rf"\bsk-[A-Za-z0-9._\-]{{16,{_MAX}}}"), False),
    # JWT: drie base64url-segmenten, begint bij een JSON-header ({"alg" → eyJ).
    # Distinctief genoeg om zonder label te redigeren.
    (
        re.compile(
            rf"\beyJ[A-Za-z0-9_\-]{{8,{_MAX}}}\.[A-Za-z0-9_\-]{{8,{_MAX}}}"
            rf"(?:\.[A-Za-z0-9_\-]{{0,{_MAX}}})?"
        ),
        False,
    ),
    # Token-achtige headers: "Token <x>", "X-Api-Token: <x>"
    (
        re.compile(rf"(?i)\b(token['\"]?[ \t]{{0,4}}[:=][ \t]{{0,4}}['\"]?)[A-Za-z0-9._\-]{{8,{_MAX}}}"),
        True,
    ),
    # Authorization: Bearer <token>
    (
        re.compile(rf"(?i)\b(bearer[ \t]{{1,4}})[A-Za-z0-9._\-]{{8,{_MAX}}}"),
        True,
    ),
    # Toewijzingen: api_key=..., apikey: "...", x-claude-api-key: ...
    # De prefix vóór "api" is bewust kort begrensd: dat dekt headernamen als
    # "x-claude-" en houdt het terugkrabbelen constant.
    (
        re.compile(
            rf"(?i)\b([a-z0-9\-]{{0,20}}api[-_]?key['\"]?[ \t]{{0,4}}[:=][ \t]{{0,4}}['\"]?)"
            rf"[A-Za-z0-9._\-]{{8,{_MAX}}}"
        ),
        True,
    ),
]


def redigeer(tekst: str) -> str:
    """Vervang bekende sleutels en herkenbare sleutelvormen door een marker.

    Eerst de sleutels die we bij naam kennen (exacte vervanging, werkt ongeacht
    het formaat — nodig voor VLAM/UbiOps-tokens zonder herkenbaar voorvoegsel),
    daarna de patronen voor sleutels die we niet kennen.
    """
    # Momentopname: loggen kan ook vanuit een worker-thread gebeuren, terwijl de
    # event loop een sleutel registreert of opruimt.
    for geheim in list(_geheimen):
        if geheim in tekst:
            tekst = tekst.replace(geheim, REDACTIE)
    for patroon, behoud_label in _PATRONEN:
        tekst = patroon.sub(
            (r"\1" + REDACTIE) if behoud_label else REDACTIE, tekst
        )
    return tekst


class RedigerendeFormatter(logging.Formatter):
    """Omhulsel om een bestaande formatter dat de uitvoer redigeert."""

    def __init__(self, binnenste: logging.Formatter):
        super().__init__()
        self.binnenste = binnenste

    def format(self, record: logging.LogRecord) -> str:
        return redigeer(self.binnenste.format(record))


def _omhul(handler: logging.Handler) -> None:
    if isinstance(handler.formatter, RedigerendeFormatter):
        return  # al aangehaakt (idempotent)
    handler.setFormatter(RedigerendeFormatter(handler.formatter or logging.Formatter()))


def installeer_redactie() -> None:
    """Haak de redactie aan op alle bestaande log-handlers.

    Ook op de uvicorn-loggers: die hebben `propagate=False` en eigen handlers,
    dus alleen de root afdekken is niet genoeg. Idempotent, zodat een tweede
    aanroep (bv. bij het opstarten van de app, ná uvicorn) niets stukmaakt.
    """
    for handler in logging.getLogger().handlers:
        _omhul(handler)
    # Kopie: een import of een andere thread kan tijdens het itereren een logger
    # aanmaken, en dat zou hier anders een RuntimeError geven — bij het opstarten
    # van de host, waar dat het hele proces onderuit haalt.
    for naam in list(logging.root.manager.loggerDict):
        logger = logging.getLogger(naam)
        for handler in getattr(logger, "handlers", []):
            _omhul(handler)

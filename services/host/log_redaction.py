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

# Onder deze lengte registreren we niets: een kort fragment zou gewone tekst
# kunnen raken. Sluit aan op de ondergrens van `api._valideer_sleutel`.
_MIN_GEHEIM_LENGTE = 8


def registreer_geheim(waarde: str) -> None:
    """Registreer een sleutel die voor de rest van het proces bestaat.

    Voor de server-env-sleutels: die leven zo lang als de host en kunnen in een
    bibliotheek-traceback opduiken.
    """
    if waarde and len(waarde) >= _MIN_GEHEIM_LENGTE:
        _geheimen[waarde] += 1


@contextmanager
def geheim_geregistreerd(waarde: str):
    """Registreer een sleutel voor de duur van één verzoek en haal 'm daarna weg.

    Zo houdt de redactie de sleutel niet langer vast dan de LLM-client zelf
    (PDR-010: een sleutel overleeft het verzoek niet).
    """
    if not waarde or len(waarde) < _MIN_GEHEIM_LENGTE:
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
_PATRONEN: list[tuple[re.Pattern, bool]] = [
    # Anthropic: sk-ant-... (ook admin-/oauth-varianten)
    (re.compile(r"sk-ant-[A-Za-z0-9._\-]{6,}"), False),
    # OpenAI-stijl: sk-... / sk-proj-...
    (re.compile(r"\bsk-[A-Za-z0-9._\-]{16,}"), False),
    # JWT: drie base64url-segmenten, begint bij een JSON-header ({"alg" → eyJ).
    # Distinctief genoeg om zonder label te redigeren.
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}(?:\.[A-Za-z0-9_\-]+)?"), False),
    # Token-achtige headers: "Token <x>", "X-Api-Token: <x>"
    (re.compile(r"(?i)\b(token['\"]?\s*[:=]\s*['\"]?)[A-Za-z0-9._\-]{8,}"), True),
    # Authorization: Bearer <token>
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{8,}"), True),
    # Toewijzingen: api_key=..., apikey: "...", x-claude-api-key: ...
    (
        re.compile(
            r"(?i)\b([a-z0-9\-]*api[-_]?key['\"]?\s*[:=]\s*['\"]?)"
            r"[A-Za-z0-9._\-]{8,}"
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

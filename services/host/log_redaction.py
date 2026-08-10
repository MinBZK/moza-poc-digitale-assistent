"""Vangnet: sleutel-achtige tokens uit logregels redigeren (MVP-02).

Tweede verdedigingslinie — de eerste is dat de host geen sleutels logt. Dit dekt
wat we niet vooraf zien: een onverwachte traceback, een bibliotheek die zijn
eigen headers logt. Geen entropie-heuristiek, want die raakt ook tool-resultaten
en KvK-nummers.

Aangehaakt op de formatter en niet op een `logging.Filter`: een filter draait
vóór het formatteren en ziet `record.exc_text` dan nog niet.
"""

import logging
import re
from collections import Counter
from contextlib import contextmanager

REDACTED = "[SLEUTEL-GEREDIGEERD]"

# Patronen zien alleen sleutels met een herkenbare vorm; een UbiOps-token heeft
# die niet. Daarom kennen we de sleutels die nu in gebruik zijn ook bij naam.
# Counter i.p.v. set: twee verzoeken kunnen dezelfde sleutel gebruiken, en dan
# mag het aflopen van het ene de registratie van het andere niet wissen.
_literals_to_redact: Counter = Counter()

# Twee drempels, want de herkomst verschilt. Een server-sleutel komt van de
# beheerder. Een sleutel uit een verzoek is door een aanvaller te kiezen: zonder
# vormeis kan iemand gewone logtekst opgeven ("Tool-aanroep", een KvK-nummer) en
# die tijdens zijn eigen verzoek onzichtbaar maken.
_MIN_SECRET_LENGTH = 8
# Publiek, want `api._validate_api_key` hangt zijn ondergrens hieraan op: elke
# sleutel die de voordeur binnenkomt hoort ook registreerbaar te zijn. Stonden de
# twee drempels los van elkaar, dan liepen ze uit elkaar en viel er stil een gat
# (sleutels van 8–19 tekens gingen wél naar de provider, maar het log-vangnet
# kende ze niet).
MIN_UNTRUSTED_SECRET_LENGTH = 20


def looks_like_a_key(value: str) -> bool:
    """Streng genoeg dat gewone logtekst niet als geheim geregistreerd raakt."""
    return (
        len(value) >= MIN_UNTRUSTED_SECRET_LENGTH
        and any(c.isdigit() for c in value)
        and any(c.isalpha() for c in value)
    )


def redact_always(value: str) -> None:
    """Voor server-env-sleutels: die leven zo lang als het proces."""
    if value and len(value) >= _MIN_SECRET_LENGTH:
        _literals_to_redact[value] += 1


@contextmanager
def redact_temporarily(value: str):
    """Voor een sleutel uit een verzoek: registratie duurt zo lang als het verzoek.

    Zo houdt de redactie de sleutel niet langer vast dan de LLM-client zelf
    (PDR-010). Waarden die niet op een sleutel lijken worden genegeerd.
    """
    if not value or not looks_like_a_key(value):
        yield
        return
    _literals_to_redact[value] += 1
    try:
        yield
    finally:
        _literals_to_redact[value] -= 1
        if _literals_to_redact[value] <= 0:
            del _literals_to_redact[value]

# Elk patroon vervangt de hele match, óf alles ná groep 1 (het "label").
# Alle herhalingen zijn bovenbegrensd: een onbegrensde `*` vóór een literal geeft
# polynomiaal terugkrabbelen, en logregels kunnen gebruikerstekst bevatten
# (py/polynomial-redos; 64 KB kostte ruim 30 s). 256 ligt ruim boven elke sleutel.
_MAX = 256

_PATTERNS: list[tuple[re.Pattern, bool]] = [
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


# Geen enkel patroon hierboven kan matchen zonder dat één van deze substrings in
# de regel staat: `sk-` voor de twee sk-patronen, `eyj` voor JWT, en `token` /
# `bearer` / `apikey|api-key|api_key` voor de drie label-patronen. Een kale
# `in`-check is orden goedkoper dan zes regexen over élke logregel, en de dekking
# blijft per constructie gelijk.
#
# Twee valkuilen, allebei uitgeprobeerd: een trigger-*regex* kost zelf meer dan
# hij bespaart, en filteren op kaal "api" helpt niets — de logger heet `vlam.api`,
# dus dan triggert elke regel alsnog.
_PATTERN_TRIGGERS = ("sk-", "eyj", "token", "bearer", "apikey", "api-key", "api_key")


def redact(text: str) -> str:
    """Vervang bekende sleutels en herkenbare sleutelvormen door een marker.

    Eerst de sleutels die we bij naam kennen (werkt ongeacht het formaat), daarna
    de patronen voor sleutels die we niet kennen.
    """
    # Momentopname: loggen kan ook vanuit een worker-thread komen.
    for secret in list(_literals_to_redact):
        if secret in text:
            text = text.replace(secret, REDACTED)
    lowered = text.lower()
    if not any(trigger in lowered for trigger in _PATTERN_TRIGGERS):
        return text
    for pattern, keep_label in _PATTERNS:
        text = pattern.sub(
            (r"\1" + REDACTED) if keep_label else REDACTED, text
        )
    return text


class RedactingFormatter(logging.Formatter):
    """Omhulsel om een bestaande formatter dat de uitvoer redigeert."""

    def __init__(self, inner: logging.Formatter):
        super().__init__()
        self.inner = inner

    def format(self, record: logging.LogRecord) -> str:
        return redact(self.inner.format(record))


def _wrap_formatter(handler: logging.Handler) -> None:
    if isinstance(handler.formatter, RedactingFormatter):
        return  # al aangehaakt (idempotent)
    handler.setFormatter(RedactingFormatter(handler.formatter or logging.Formatter()))


def install_redaction() -> None:
    """Haak de redactie aan op alle bestaande log-handlers; idempotent.

    Ook op de uvicorn-loggers: die hebben `propagate=False` en eigen handlers,
    dus alleen de root afdekken is niet genoeg.
    """
    for handler in logging.getLogger().handlers:
        _wrap_formatter(handler)
    # Kopie: een import of thread kan tijdens het itereren een logger aanmaken,
    # en een RuntimeError hier haalt het opstarten onderuit.
    for name in list(logging.root.manager.loggerDict):
        logger = logging.getLogger(name)
        for handler in getattr(logger, "handlers", []):
            _wrap_formatter(handler)

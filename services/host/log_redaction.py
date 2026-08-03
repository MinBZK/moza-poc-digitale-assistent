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

REDACTIE = "[SLEUTEL-GEREDIGEERD]"

# Elk patroon vervangt óf de hele match, óf alles ná groep 1 (het "label").
_PATRONEN: list[tuple[re.Pattern, bool]] = [
    # Anthropic: sk-ant-... (ook admin-/oauth-varianten)
    (re.compile(r"sk-ant-[A-Za-z0-9._\-]{6,}"), False),
    # OpenAI-stijl: sk-... / sk-proj-...
    (re.compile(r"\bsk-[A-Za-z0-9._\-]{16,}"), False),
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
    """Vervang herkenbare sleutelvormen in `tekst` door een vaste marker."""
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
    for naam in logging.root.manager.loggerDict:
        logger = logging.getLogger(naam)
        for handler in getattr(logger, "handlers", []):
            _omhul(handler)

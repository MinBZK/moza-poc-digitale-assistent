"""Pytest-setup voor de host-tests.

Forceer lege LLM-credentials *vóór* de eerste import van `config`/`vlam_host`.
Die modules lezen de keys op import-tijd (`from config import VLAM_API_KEY`),
en `config.load_dotenv()` zou anders een lokale `.env` oppikken — wat de tests
afhankelijk maakt van de ontwikkelomgeving. Door de keys hier expliciet leeg te
zetten, slaat `load_dotenv(override=False)` ze over en zijn de tests
deterministisch (CI == lokaal), zonder echte credentials te vereisen.
"""

import logging
import os

for _key in ("ANTHROPIC_API_KEY", "VLAM_API_KEY"):
    os.environ[_key] = ""

import pytest  # noqa: E402  — pas ná het leegzetten van de credentials

import log_redaction  # noqa: E402


def _alle_handlers() -> list[logging.Handler]:
    handlers = list(logging.getLogger().handlers)
    for name in list(logging.root.manager.loggerDict):
        handlers.extend(getattr(logging.getLogger(name), "handlers", []))
    return handlers


@pytest.fixture(autouse=True)
def schone_redactie_state():
    """Houd de procesbrede redactie-state binnen één test.

    `_literals_to_redact` en de door `install_redaction()` omhulde formatters
    zijn globaal. Zonder herstel wordt de suite volgorde-afhankelijk: een test
    die een sleutel registreert of de root-handlers omhult, verandert wat een
    latere test meet.
    """
    formatters = [(h, h.formatter) for h in _alle_handlers()]
    bewaard = log_redaction._literals_to_redact.copy()
    yield
    log_redaction._literals_to_redact.clear()
    log_redaction._literals_to_redact.update(bewaard)
    for handler, formatter in formatters:
        handler.setFormatter(formatter)

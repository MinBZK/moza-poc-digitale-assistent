"""Pytest-setup voor de host-tests.

Forceer de omgeving *vóór* de eerste import van `config`/`vlam_host`. Die
modules lezen hun instellingen op import-tijd (`from config import ...`), en
`config.load_dotenv()` zou anders een lokale `.env` oppikken — wat de tests
afhankelijk maakt van de ontwikkelomgeving.

De LLM-keys gaan leeg: geen echte credentials nodig, geen netwerk.

De KvK-allowlist krijgt juist wél de drie testprofielen. Die stand hoort bij de
tests die "een gebruiker buiten de allowlist" beproeven: dat scenario bestaat
alleen als er een allowlist ís. Zonder deze regel hing de uitkomst af van de
aan- of afwezigheid van een (gitignored) `.env`, waardoor de suite lokaal groen
kon zijn en in CI niet.
"""

import logging
import os

for _key in ("ANTHROPIC_API_KEY", "VLAM_API_KEY"):
    os.environ[_key] = ""

os.environ["TEST_KVK_NUMMERS"] = "85234567,62345681,56789012"

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

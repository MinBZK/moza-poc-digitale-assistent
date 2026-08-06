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

import os

for _key in ("ANTHROPIC_API_KEY", "VLAM_API_KEY"):
    os.environ[_key] = ""

os.environ["TEST_KVK_NUMMERS"] = "85234567,62345681,56789012"

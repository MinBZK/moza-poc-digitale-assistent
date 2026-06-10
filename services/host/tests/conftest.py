"""Pytest-setup voor de host-tests.

Forceer lege LLM-credentials *vóór* de eerste import van `config`/`vlam_host`.
Die modules lezen de keys op import-tijd (`from config import VLAM_API_KEY`),
en `config.load_dotenv()` zou anders een lokale `.env` oppikken — wat de tests
afhankelijk maakt van de ontwikkelomgeving. Door de keys hier expliciet leeg te
zetten, slaat `load_dotenv(override=False)` ze over en zijn de tests
deterministisch (CI == lokaal), zonder echte credentials te vereisen.
"""

import os

for _key in ("ANTHROPIC_API_KEY", "VLAM_API_KEY"):
    os.environ[_key] = ""

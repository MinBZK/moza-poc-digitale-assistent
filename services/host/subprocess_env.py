"""Gedeelde env-allowlist voor subprocessen (MCP-servers én CLI-wrappers).

Geen van beide kindprocessen heeft een LLM-sleutel nodig; ze in extra processen
laten leven vergroot alleen het lek-oppervlak (PDR-010 §4). Het MCP-transport had
zo'n allowlist al, het CLI-transport gaf de volledige `os.environ` door — deze
module is de ene plek waar de regel vastligt.

NB: PDR-007 beschrijft de stand van vóór MVP-02 ("de host geeft nu expliciet
`os.environ` door"); dat is met deze module bijgesteld. Zie de bijstellingsregel
in PDR-007 zelf.

Beide lijsten delen een systeembasis en hebben hun eigen app-config: de
MCP-servers en de CLI-scripts lezen deels andere variabelen. `test_subprocess_env.py`
leest de namen uit de servers en de bash-scripts, zodat de lijsten niet stil
kunnen gaan afwijken van wat er werkelijk gelezen wordt.
"""

import os

# Systeem: nodig om überhaupt een proces te starten en uitgaand verkeer te doen.
_SYSTEM = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    "TMPDIR", "TEMP", "TMP", "TERM",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT",
    # Zonder deze breekt uitgaand verkeer in omgevingen die een forward proxy
    # afdwingen; ze ontbraken tot nu toe ook in de MCP-allowlist.
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
)

# App-config die de MCP-servers zelf uitlezen — precies de namen die in een
# `os.getenv(...)` in services/mcp/*/server.py staan, niet meer en niet minder.
# `KVK_TEST_API_KEY` stond hier eerder, maar geen enkele server leest die uit de
# omgeving (het is een literal in services/mcp/kvk/server.py); `KOOP_SRU_URL` en
# `KOOP_SRU_CONNECTION` wórden wél gelezen maar stonden alleen in _CLI_CONFIG,
# waardoor die config de MCP-koop-server nooit bereikte.
_MCP_CONFIG = (
    "DEMO_KVK_NUMMER", "REGELRECHT_RPC_URL", "BAG_API_KEY",
    "KOOP_SRU_URL", "KOOP_SRU_CONNECTION",
)

# App-config die de bash-wrappers uitlezen (services/cli/lib/config.sh en de
# `${VAR:-default}`-regels boven in koop-cli / regelrecht-cli).
_CLI_CONFIG = (
    "KVK_API_BASE", "KVK_API_KEY", "KVK_SESSIE_NUMMER", "KVK_AUDIT_LOG",
    "REGELRECHT_RPC_URL", "KOOP_SRU_URL", "KOOP_SRU_CONNECTION",
)

MCP_ALLOWLIST: tuple[str, ...] = _SYSTEM + _MCP_CONFIG
CLI_ALLOWLIST: tuple[str, ...] = _SYSTEM + _CLI_CONFIG

# Namen die nooit een kindproces in mogen, wat de aanroeper ook meegeeft.
NEVER_PASS_THROUGH: tuple[str, ...] = ("ANTHROPIC_API_KEY", "VLAM_API_KEY")


def subprocess_env(allowlist: tuple[str, ...], extra: dict | None = None) -> dict:
    """Bouw de omgeving voor een kindproces: alleen de allowlist, plus `extra`.

    `extra` is per-aanroep-config die de host injecteert (bv. `KVK_SESSIE_NUMMER`
    voor de kvk-cli, PDR-009), los van de proces-omgeving.
    """
    env = {k: v for k, v in os.environ.items() if k in allowlist}
    if extra:
        env.update(extra)
    # `extra` gaat bewust buiten de allowlist om, dus een aanroeper kan hier
    # alsnog een LLM-sleutel in duwen. Deze twee regels maken van
    # NEVER_PASS_THROUGH een invariant in plaats van een afspraak die alleen in
    # een test bestaat.
    for name in NEVER_PASS_THROUGH:
        env.pop(name, None)
    return env

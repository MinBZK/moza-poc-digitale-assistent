"""Gedeelde env-allowlist voor subprocessen (MCP-servers én CLI-wrappers).

Geen van beide kindprocessen heeft een LLM-sleutel nodig; ze in extra processen
laten leven vergroot alleen het lek-oppervlak (PDR-007). Het MCP-transport had
zo'n allowlist al, het CLI-transport gaf de volledige `os.environ` door — deze
module is de ene plek waar de regel vastligt.

Beide lijsten delen een systeembasis en hebben hun eigen app-config: de
MCP-servers en de CLI-scripts lezen andere variabelen.
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

# App-config die de MCP-servers zelf uitlezen.
_MCP_CONFIG = (
    "DEMO_KVK_NUMMER", "REGELRECHT_RPC_URL", "BAG_API_KEY", "KVK_TEST_API_KEY",
)

# App-config die de bash-wrappers uitlezen (services/cli/lib/config.sh en de
# `${VAR:-default}`-regels boven in koop-cli / regelrecht-cli).
_CLI_CONFIG = (
    "KVK_API_BASE", "KVK_API_KEY", "KVK_SESSIE_NUMMER", "KVK_AUDIT_LOG",
    "REGELRECHT_RPC_URL", "KOOP_SRU_URL", "KOOP_SRU_CONNECTION",
)

MCP_ALLOWLIST: tuple[str, ...] = _SYSTEM + _MCP_CONFIG
CLI_ALLOWLIST: tuple[str, ...] = _SYSTEM + _CLI_CONFIG

# Vangnet voor de test: de allowlists noemen deze namen simpelweg niet.
NEVER_PASS_THROUGH: tuple[str, ...] = ("ANTHROPIC_API_KEY", "VLAM_API_KEY")


def subprocess_env(allowlist: tuple[str, ...], extra: dict | None = None) -> dict:
    """Bouw de omgeving voor een kindproces: alleen de allowlist, plus `extra`.

    `extra` is per-aanroep-config die de host injecteert (bv. `KVK_SESSIE_NUMMER`
    voor de kvk-cli, PDR-009), los van de proces-omgeving.
    """
    env = {k: v for k, v in os.environ.items() if k in allowlist}
    if extra:
        env.update(extra)
    return env

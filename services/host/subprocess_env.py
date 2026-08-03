"""Gedeelde env-allowlist voor subprocessen (MCP-servers én CLI-wrappers).

De host start twee soorten kindprocessen: de vijf MCP-servers (stdio) en de
bash-CLI-wrappers. Geen van beide heeft een LLM-sleutel nodig. Ze in extra
processen laten leven vergroot het lek-oppervlak zonder dat er iets tegenover
staat (PDR-007: identiteit/config bij de bron; sleutel-blootstelling
minimaliseren).

Het MCP-transport had zo'n allowlist al; het CLI-transport gaf de volledige
`os.environ` door — dezelfde regel werd dus door het ene pad wel en door het
andere niet gevolgd. Deze module is de ene plek waar dat vastligt.

Beide lijsten delen een systeembasis (interpreter kunnen starten, TLS en een
eventuele forward proxy kunnen gebruiken) en hebben daarnaast hun eigen
app-config: de MCP-servers en de CLI-scripts lezen andere variabelen.
"""

import os

# Systeem: nodig om überhaupt een proces te starten en uitgaand verkeer te doen.
_SYSTEEM = (
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

MCP_ALLOWLIST: tuple[str, ...] = _SYSTEEM + _MCP_CONFIG
CLI_ALLOWLIST: tuple[str, ...] = _SYSTEEM + _CLI_CONFIG

# Wat er onder geen beding in een kindproces terecht mag komen. Puur een
# vangnet voor de test: de allowlists noemen deze namen simpelweg niet.
NOOIT_DOORGEVEN: tuple[str, ...] = ("ANTHROPIC_API_KEY", "VLAM_API_KEY")


def subprocess_env(allowlist: tuple[str, ...], extra: dict | None = None) -> dict:
    """Bouw de omgeving voor een kindproces: alleen de allowlist, plus `extra`.

    `extra` is per-aanroep-config die de host zelf injecteert (bijvoorbeeld
    `KVK_SESSIE_NUMMER` voor de kvk-cli, PDR-009) en staat los van wat er in de
    proces-omgeving toevallig gezet is.
    """
    env = {k: v for k, v in os.environ.items() if k in allowlist}
    if extra:
        env.update(extra)
    return env

"""Configuratie voor de VLAM MCP-host."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Pad-basis relatief aan dit bestand
BASE_DIR = Path(__file__).resolve().parent
SERVERS_DIR = BASE_DIR.parent / "mcp"
PROJECT_ROOT = BASE_DIR.parent.parent

# Zoek .env op meerdere plekken (eerste die bestaat wint)
for _env_path in [
    BASE_DIR / ".env",          # services/host/.env
    BASE_DIR.parent / ".env",   # services/.env
    PROJECT_ROOT / ".env",      # project root .env
]:
    if _env_path.is_file():
        load_dotenv(_env_path)
        break
else:
    load_dotenv()  # fallback: zoek in cwd

# Claude API (Anthropic)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# VLAM API (UbiOps/Mistral — OpenAI-compatibele API)
# Base URL en model-ID hebben zinvolle defaults (zie PDR-001) zodat een frontend
# met alleen een API-key-override ook werkt als de server-env deze niet expliciet zet.
VLAM_API_KEY = os.getenv("VLAM_API_KEY", "")
VLAM_BASE_URL = os.getenv(
    "VLAM_BASE_URL",
    "https://api.demo.vlam.ai/v2.1/projects/poc/openai-compatible/v1",
)
VLAM_MODEL_ID = os.getenv(
    "VLAM_MODEL_ID",
    "ubiops-deployment/bzk-dig-mistralmedium-flexibel//chat-model",
)

# MCP-servers: naam → pad naar server.py
# Relatieve paden uit .env worden opgelost t.o.v. de host-directory (BASE_DIR)
# Waarden waarmee een bron bewust wordt uitgezet. Een lege of afwezige waarde
# betekende "gebruik het standaardpad", dus een bron weglaten uit de configuratie
# schakelde hem niet uit - hij startte gewoon. De enige uitweg was hem laten
# falen, en dan staat er een fout in de log voor iets dat je expres deed.
_UIT = frozenset({"", "uit", "off", "none", "geen"})


def _resolve_server_path(env_key: str, default: Path) -> Path | None:
    """Het pad naar een MCP-server, of None als die bewust uitstaat.

    Uitzetten is een besluit en hoort er ook zo uit te zien: `MCP_SERVER_X=` (of
    `uit`) laat de bron weg, terwijl de variabele helemaal weglaten het
    standaardpad houdt. Zo verdwijnt een bron nooit door een vergeten regel.
    """
    raw = os.getenv(env_key)
    if raw is None:
        return default
    if raw.strip().lower() in _UIT:
        return None
    p = Path(raw)
    if not p.is_absolute():
        p = (BASE_DIR / p).resolve()
    return p

_MCP_SERVERS_RUW: dict[str, Path | None] = {
    "kvk": _resolve_server_path("MCP_SERVER_KVK", SERVERS_DIR / "kvk" / "server.py"),
    "koop": _resolve_server_path("MCP_SERVER_KOOP", SERVERS_DIR / "koop" / "server.py"),
    "regelrecht": _resolve_server_path("MCP_SERVER_REGELRECHT", SERVERS_DIR / "regelrecht" / "server.py"),
    "rvo": _resolve_server_path("MCP_SERVER_RVO", SERVERS_DIR / "rvo" / "server.py"),
    "netbeheerder": _resolve_server_path(
        "MCP_SERVER_NETBEHEERDER", SERVERS_DIR / "netbeheerder" / "server.py"
    ),
}

# Alleen de bronnen die aanstaan. Een uitgezette bron is geen storing: hij hoort
# niet in `server_status` als "niet beschikbaar" te belanden, maar simpelweg
# afwezig te zijn - `bronnen_offline` telt hem dan mee en de assistent belooft
# hem niet meer.
MCP_SERVERS: dict[str, Path] = {
    naam: pad for naam, pad in _MCP_SERVERS_RUW.items() if pad is not None
}

# Host
VLAM_HOST = os.getenv("VLAM_HOST", "0.0.0.0")
VLAM_PORT = int(os.getenv("VLAM_PORT", "8000"))

# Timeouts (seconden) — per LLM-call, niet per sessie
VLAM_TIMEOUT = int(os.getenv("VLAM_TIMEOUT", "30"))
CLAUDE_TIMEOUT = int(os.getenv("CLAUDE_TIMEOUT", "60"))

# Time-out per bron-aanroep (seconden), voor MCP én CLI. Zonder deze grens kan
# een bron die
# het verzoek aanneemt maar nooit antwoordt de hele SSE-stream laten hangen: geen
# antwoord, geen foutmelding, geen afsluiting. Het CLI-transport heeft daarbinnen
# een eigen grens per subprocess: maximaal 30 s, en altijd 5 s korter dan deze.
TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT", "45"))

# Maximale lengte van één vraag. Zonder bovengrens belandt een willekeurig lang
# bericht ongelezen in de gespreksgeschiedenis en faalt de LLM-call verderop met
# een vage melding; hiermee weet de gebruiker meteen wat er mis is. Ruim boven
# een normale vraag, ver onder het contextvenster van beide modellen.
MAX_VRAAG_TEKENS = int(os.getenv("MAX_VRAAG_TEKENS", "4000"))

# Security: CORS-origins en API-key overrides
# ALLOWED_ORIGINS: komma-gescheiden lijst, leeg = geen CORS toegestaan
# (browser-toegang van een andere origin wordt geweigerd). Zet expliciet
# `ALLOWED_ORIGINS=*` voor lokale dev, of een whitelist voor productie:
#   ALLOWED_ORIGINS=https://moza.overheid.nl,https://moza-test.overheid.nl
# Voorheen viel een lege/ontbrekende waarde stilletjes terug op "*"; dat is
# bewust verwijderd zodat een vergeten env-var niet onbedoeld de API openzet.
_origins_raw = os.getenv("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _origins_raw.split(",") if o.strip()] if _origins_raw else []
)
# ALLOW_API_KEY_OVERRIDE: als true (de default), worden x-vlam-api-key en
# x-claude-api-key uit de UI gerespecteerd. Dit is geen slordige default maar de
# dragende aanname van de deployment: die draait zonder LLM-sleutels en elke
# tester brengt zijn eigen sleutel mee (PDR-010). Zet op "false" zodra er wél
# server-env keys staan; de headers worden dan genegeerd.
#
# Wat er aan de kant van de host tegenover staat (MVP-02): een sleutel leeft
# precies één verzoek (`vlam_host._request_clients`), wordt op vorm getoetst
# vóór gebruik (`api._validate_api_key`), gaat nooit mee naar een subprocess
# (`subprocess_env.py`) en wordt uit logregels geredigeerd (`log_redaction.py`).
ALLOW_API_KEY_OVERRIDE: bool = os.getenv("ALLOW_API_KEY_OVERRIDE", "true").lower() in (
    "true",
    "1",
    "yes",
)

# Toegestane KvK-nummers voor de gesloten testgroep (MVP-01 / PDR-009 addendum).
# De frontend stuurt `X-Test-User: <kvk-nummer>` van de gekozen persona; de host
# valideert dat hiertegen en injecteert het nummer server-side bij elke
# bron-aanroep. Geen geheim (de nummers staan publiek in de frontend), wel een
# grens: zonder allowlist zou de KvK-server willekeurige nummers opvragen.
# Formaat: TEST_KVK_NUMMERS="85234567,62345681,56789012". BETA-02 vervangt de
# lijst door echte authenticatie; de vorm blijft gelijk.
def _parse_kvk_allowlist(raw: str) -> frozenset[str]:
    return frozenset(k.strip() for k in raw.split(",") if k.strip())


TEST_KVK_NUMMERS: frozenset[str] = _parse_kvk_allowlist(
    os.getenv("TEST_KVK_NUMMERS", "")
)


def kvk_uit_header(waarde: str | None) -> str | None:
    """Valideer het KvK-nummer uit de `X-Test-User`-header tegen de allowlist.

    None bij een lege header of een nummer erbuiten => de host blokkeert.
    """
    if not waarde:
        return None
    kvk = waarde.strip()
    return kvk if kvk in TEST_KVK_NUMMERS else None


# System prompt — assembled from modular blocks
from prompts.composer import compose_system_prompt as get_system_prompt  # noqa: E402

__all__ = [
    "ALLOW_API_KEY_OVERRIDE",
    "ALLOWED_ORIGINS",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "MAX_VRAAG_TEKENS",
    "MCP_SERVERS",
    "TOOL_TIMEOUT",
    "TEST_KVK_NUMMERS",
    "kvk_uit_header",
    "VLAM_API_KEY",
    "VLAM_BASE_URL",
    "VLAM_HOST",
    "VLAM_MODEL_ID",
    "VLAM_PORT",
    "VLAM_TIMEOUT",
    "CLAUDE_TIMEOUT",
    "get_system_prompt",
]

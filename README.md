# PoC MOZa Digitale Assistent

![Project Status](https://img.shields.io/badge/life_cycle-pre_alpha-red)
![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/MinBZK/moza-poc-digitale-assistent/badge)

Proof of Concept Digitale Assistent voor MijnOverheid Zakelijk (MOZa): een
AI-gestuurde assistent die ondernemers helpt bij vragen over
overheidsdienstverlening.

## Inleiding

De assistent ontsluit overheidsbronnen (KvK, KOOP, RegelRecht, RVO) als tools
voor een Large Language Model via het [Model Context Protocol](https://modelcontextprotocol.io/)
(MCP). Een FastAPI-host orkestreert het gesprek; per bron is er een MCP-server.

## Doel

Dit Open Source project is opgezet als PoC voor het verantwoord inzetten van
generatieve AI als runtime-component in een digitale overheidsdienst, conform
de [MCP-standaard voor Generieke Interactieservices](https://gemmaonline.nl/index.php/MCP-standaard).
De PoC bestaat uit de volgende onderdelen:

- **host**: FastAPI-service met LLM-orkestratie (Claude of VLAM/Mistral) en MCP-clients
- **mcp**: Vier MCP-servers (KvK, KOOP, RegelRecht, RVO)
- **cli**: Equivalente CLI-tools voor on-demand gebruik en als fallback

## Vereisten

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package/project manager)
- Docker (optioneel: voor containerized draaien)
- `ANTHROPIC_API_KEY` of VLAM-credentials

## Snel starten

```bash
# 1) Dependencies installeren
uv sync

# 2) .env aanmaken (vul minimaal ANTHROPIC_API_KEY in)
cp services/host/.env.example services/host/.env

# 3) Host starten
uv run uvicorn api:app --app-dir services/host --reload --port 8000
```

De assistent is bereikbaar op `http://localhost:8000`:

| Endpoint | Doel |
|----------|------|
| `POST /chat` | Conversatie (één response): body `{ "message": "...", "mode": "vlam" }` (`mode` is optioneel, default `vlam`; gebruik `claude` voor Anthropic) |
| `POST /chat/stream` | Idem maar als Server-Sent Events stream |
| `GET /health` | Health-check van host en MCP-servers |
| `GET /tools` | Lijst van beschikbare MCP-tools |
| `DELETE /chat/{session_id}` | Wis sessie |

### Met Docker

```bash
cp services/host/.env.example services/host/.env   # eerste keer
docker compose up --build
```

### Tests draaien

```bash
uv run pytest
```

`services/host/tests/test_smoke.py` checkt importeerbaarheid; uitgebreide
manuele scripts (vereisen API-keys) staan in `services/host/scripts/`.

### Lint

```bash
uv run ruff check .
```

## Configuratie

Belangrijkste env-variabelen (zie `services/host/.env.example`):

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-20250514

VLAM_API_KEY=...
VLAM_BASE_URL=https://api...
VLAM_MODEL_ID=ubiops-deployment/...

# Paden naar MCP-server-scripts (in Docker via compose overschreven)
MCP_SERVER_KVK=../mcp/kvk/server.py
MCP_SERVER_KOOP=../mcp/koop/server.py
MCP_SERVER_REGELRECHT=../mcp/regelrecht/server.py
MCP_SERVER_RVO=../mcp/rvo/server.py
```

## Architectuur en beslissingen

Architectuur- en routerings-beslisboom staan in
[`docs/architecture.md`](docs/architecture.md). Ontwerpbeslissingen zijn
vastgelegd als Product Decision Records in
[`docs/decisions/`](docs/decisions/).

## Licentie

Dit project is gelicenseerd onder de [EUPL-1.2](LICENSE).

## AI-verantwoording

De code in deze PoC is grotendeels gegenereerd met generatieve AI (Claude Code);
alle niet-testcode wordt menselijk gereviewd en testcode wordt functioneel
beproefd. Zie [DISCLAIMER.md](DISCLAIMER.md) voor de disclaimer en
[docs/ai-verantwoording.md](docs/ai-verantwoording.md) voor de volledige
verantwoording, getoetst aan de Overheidsbrede handreiking voor de verantwoorde
inzet van generatieve AI.

## Ondersteuning

Zie [SUPPORT.md](SUPPORT.md) voor informatie over hoe en waar je hulp kunt krijgen.

## Governance

Zie [GOVERNANCE.md](GOVERNANCE.md) voor informatie over de governance-structuur
van dit project.

# `services/host`: FastAPI-host van de Digitale Assistent

De host is de tussenstap tussen browser en LLM. Eén proces, twee LLM-backends (VLAM en Claude), twee transportmechanismen voor tools (MCP en CLI).

> Quickstart, endpoints en .env-configuratie staan in de [root README](../../README.md). Architectuur en routering in [`../../docs/architecture.md`](../../docs/architecture.md). Ontwerpbeslissingen in [`../../docs/decisions/`](../../docs/decisions/).

## Wat staat waar

| Bestand | Doel |
|---|---|
| `api.py` | FastAPI-applicatie. Endpoints: `POST /chat`, `POST /chat/stream`, `GET /health`, `GET /tools`, `DELETE /chat/{session_id}`, en `/<path>` voor het mounten van een statische frontend-build. |
| `vlam_host.py` | Orkestratie-laag: agentic loops voor Claude en VLAM, in MCP- en CLI-modus. Bevat ook `CLI_TOOL_DEFINITIONS_*` (zie waarschuwing hieronder). |
| `mcp_client.py` | `MCPToolRegistry` en `MCPServerConnection`: onderhoudt verbindingen met de vier MCP-servers. |
| `cli_executor.py` | Vertaalt `tool_use`-blokken naar CLI-commando's en voert ze uit als subprocess. |
| `config.py` | `.env`-laden, MCP-server-paden, timeout-instellingen, CORS- en API-key-overrides. |
| `prompts/` | Modulaire systeemprompts. `composer.py` zet identity + shared + model-specific blokken samen tot één prompt. |
| `prompts/blocks/` | Prompt-blokken: `identity/`, `shared/` (met `domain/`), `model_specific/`. |
| `prompts/examples/` | Few-shot voorbeelden (naast `blocks/`, niet eronder). |
| `Dockerfile` | Container-opzet voor de host (zie [`../../compose.yaml`](../../compose.yaml) voor de volledige stack). |
| `tests/test_smoke.py` | Pytest smoke-tests: importeerbaarheid en basis-status zonder API-keys. |
| `scripts/run_scenarios.py` | Handmatige mock-based scenario's voor de chat-stream: event-volgorde bij happy path en foutcondities. |
| `scripts/check_vlam_toolcalling.py` | Handmatige integratie-test tegen het VLAM-endpoint: één tool-aanroep, geen MCP-server nodig. |
| `scripts/check_vlam_toolcalling_chain.py` | Idem, maar met een 3-rondes chain met meerdere tools. Onderbouwt waarom PDR-002 en PDR-003 ongeldig zijn verklaard. |

## Handmatige integratie-scripts

`uv run pytest` (zie root README) dekt alleen smoke. Voor de scripts in `scripts/` is een geldige `.env` met API-keys nodig:

```bash
uv run python services/host/scripts/run_scenarios.py
uv run python services/host/scripts/check_vlam_toolcalling.py
uv run python services/host/scripts/check_vlam_toolcalling_chain.py
```

Zie ook [`../../docs/test-vragen.md`](../../docs/test-vragen.md) voor handmatige testvragen per tool en toolcombinatie.

## MCP-servers valideren tegen de standaard

```bash
../../scripts/validate-mcp-servers.sh
```

Dit script draait `mcp-standaard validate` tegen alle vier servers, inclusief functionele resource-checks via `--test-uri`. Zonder die test-URIs blijft een type-mismatch op `ReadResourceContents` (zie [PDR-006 § A](../../docs/decisions/PDR-006-feasibility-conclusie.md#a-bug-in-de-kvk--en-koop-resource-implementatie-opgelost-in-deze-pr)) onzichtbaar in de check-output. Voer dit script ook uit na elke wijziging in `services/mcp/*/server.py`.

Vereist `uv` en de repo `moza-mcp-standaard-poc` lokaal (default-pad: `../moza-mcp-standaard-poc` of zet `STANDAARD_REPO`-env).

## Aandachtspunten

**Sync tussen `CLI_TOOL_DEFINITIONS_*` en `cli_executor.py`**: de CLI-modus gebruikt twee handmatige bronnen die op elkaar moeten passen: de tool-definities die het LLM ziet (`vlam_host.py`) en de commando-mapping die wordt uitgevoerd (`cli_executor.py`). MCP doet dit automatisch via `tools/list`. Zie [PDR-005, "CLI tool-definities zijn hardcoded"](../../docs/decisions/PDR-005-cli-vs-mcp-transport.md) en [PDR-006 § B](../../docs/decisions/PDR-006-feasibility-conclusie.md#b-synchronisatie-tussen-host-en-cli-is-niet-automatisch) voor de nu bekende sync-gaten.

**`_site/` in deze map**: wordt aangemaakt door de FastAPI-mount op runtime, niet handmatig beheren. Staat in `.gitignore`.

**Streaming events**: de UI verwacht `status`, `tool`, `case`, `answer`, `error` en `done`. Zie de docstrings van `chat_stream` voor het exacte contract.

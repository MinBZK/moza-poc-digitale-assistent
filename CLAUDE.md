# CLAUDE.md

Richtlijnen voor Claude Code (en andere AI-assistenten) bij het werken in deze
repository. Houd dit bestand kort en actueel; verwijs voor diepgang naar de
docs in plaats van details te dupliceren.

## Wat dit is

Proof of Concept van de **Digitale Assistent** voor MijnOverheid Zakelijk (MOZa):
een AI-assistent die ondernemers helpt met vragen over overheidsdienstverlening.
Een FastAPI-host orkestreert een gesprek tussen een LLM en vijf overheidsbronnen
(KvK, KOOP, RegelRecht, RVO, netbeheerder-mock), ontsloten als tools via het Model Context Protocol
(MCP) of als CLI-wrappers.

Dit is **experimentele PoC-code**, geen productie. Geen persoonsgegevens; alleen
fictieve/testdata. Zie [`DISCLAIMER.md`](DISCLAIMER.md) en
[`docs/ai-verantwoording.md`](docs/ai-verantwoording.md).

## Veelgebruikte commando's

```bash
uv sync                                    # dependencies installeren
uv run uvicorn api:app --app-dir services/host --reload --port 8000   # host starten
uv run pytest                              # smoke-tests (geen API-keys nodig)
uv run ruff check .                        # lint
docker compose up --build                  # volledige stack via Docker
./scripts/validate-mcp-servers.sh          # MCP-servers tegen de standaard valideren
```

Handmatige integratie-scripts (vereisen een `.env` met echte API-keys) staan in
`services/host/scripts/` — zie [`services/host/README.md`](services/host/README.md).

## Architectuur in het kort

- **`services/host/`** — FastAPI-host (één proces). `api.py` (endpoints),
  `vlam_host.py` (orkestratie / agentic loops), `mcp_client.py` (MCP-verbindingen),
  `cli_executor.py` (CLI-transport), `config.py` (env/CORS/timeouts),
  `prompts/` (modulaire systeemprompts, samengesteld door `composer.py`).
- **`services/mcp/{kvk,koop,regelrecht,rvo,netbeheerder}/server.py`** — vijf
  MCP-servers (Python, als stdio-subprocessen gestart door de host).
- **`services/cli/`** — Bash CLI-wrappers (alternatief transport, on-demand).
- **`docs/`** — `architecture.md` (routering + scenario's), `decisions/` (PDR's),
  `deploy-zad.md` (deployen + debug-valkuilen), `test-vragen.md`,
  `ai-verantwoording.md`.

Vier `mode`-waarden op `/chat`: `vlam`, `claude` (MCP-transport) en `cli:vlam`,
`cli:claude` (CLI-transport). Default `vlam`. De host werkt ook zónder
MCP-servers/CLI-tools (antwoordt dan op eigen kennis).

Volledig overzicht en de routerings-beslisboom: [`docs/architecture.md`](docs/architecture.md).

## Conventies en valkuilen

- **PDR's zijn leidend voor ontwerpkeuzes.** Leg nieuwe beslissingen vast in
  [`docs/decisions/`](docs/decisions/) volgens de conventies in
  [`docs/decisions/README.md`](docs/decisions/README.md). Ongeldig verklaarde
  PDR's blijven staan (audit-trail) — verwijder ze niet.
- **CLI-tooldefinities zijn dubbel onderhouden.** `CLI_TOOL_DEFINITIONS_ANTHROPIC`
  in `vlam_host.py` (wat het LLM ziet) moet synchroon blijven met de
  commando-mapping in `cli_executor.py`. MCP doet dit automatisch via `tools/list`;
  CLI niet. Zie PDR-005/PDR-006.
- **Muterende tools vereisen bevestiging.** `rvo__indienen` is de enige muterende
  tool (`readOnlyHint=False`); bevestiging wordt afgedwongen via `ToolAnnotations`
  én de systeemprompt.
- **Dataminimalisatie** loopt via de optionele `fields`-parameter op read-tools.
- **Security-defaults zijn streng.** `ALLOWED_ORIGINS` is leeg → geen CORS tenzij
  expliciet gezet (bij `*` waarschuwt de host bij het opstarten). Zie `config.py`.
- **De LLM-sleutel komt van de gebruiker** (`ALLOW_API_KEY_OVERRIDE` default
  `true`, PDR-010): de deployment draait zonder LLM-sleutels. Daar hoort aan de
  host-kant bij dat een sleutel precies één verzoek leeft
  (`vlam_host._request_clients` — geef de client als argument door, val niet
  terug op gedeelde state), op vorm wordt getoetst (`api._validate_api_key`),
  nooit een subprocess in gaat (`subprocess_env.py`) en uit logregels wordt
  geredigeerd (`log_redaction.py`).
- **Naamgeving: technische termen Engels, domeintermen Nederlands.** Dus
  `_extract_api_keys`, `redact_temporarily`, `install_redaction` — maar
  `kvk_uit_header`, `_inject_session_kvk`, `lopende_zaak`. Commentaar,
  docstrings en testnamen zijn Nederlands. Vaste technische idiomen blijven
  Engels en worden niet vertaald (retry, backoff, timeout, allowlist, redaction,
  context manager). Twijfel? Staat de Engelse vorm in de documentatie van dát
  patroon, dan niet vertalen.
- **Commentaar legt het *waarom* vast**, niet het *wat* dat de code al toont.
  Houd het kort. Geen slagen om de arm ("voorlopig", "later beter") — schrijf
  alsof het naar productie gaat; toekomstig werk alleen als `TODO(#issue)`. Geen
  verwijzingen naar PR-nummers, review-labels of `NEXT_STEPS.md` in comments:
  die rotten. Beschrijf het probleem, niet hoe het ontdekt werd.
- **`services/host/_site/`** wordt op runtime gemount; niet handmatig beheren
  (staat in `.gitignore`).
- **Ruff** dekt `E9, F, I, W, UP, B` (zie `pyproject.toml`); pycodestyle `E4`/`E7`
  (o.a. bare-except `E722`) zijn bewust nog niet aan. Host-modules staan als
  `known-first-party` voor importgroepering.
- **Met AI gegenereerde commits** krijgen een `Co-Authored-By`-trailer.
- **Werk [`NEXT_STEPS.md`](NEXT_STEPS.md) bij vóór elke commit.** Vink afgeronde
  punten af en voeg nieuwe open punten toe (incl. openstaande review-bevindingen),
  zodat de werklijst de actuele staat van de repo blijft volgen.

## Werkwijze

- **Git.** Nooit direct naar `main`; alles via een feature branch en een PR.
  Prefixen: `feat/`, `fix/`, `chore/`, `docs/`. Voeg bij het aanmaken van een PR
  geen reviewer toe.
- **Issues.** Titel en inleiding zijn functioneel: de PO moet aanleiding, effect
  en acceptatiecriteria kunnen volgen zonder code-kennis. Technische details in
  een aparte sectie verderop ("Voor de techneut"). Formuleer acceptatiecriteria
  als gedrag, niet als implementatie.
- **Tests.** Happy én unhappy paths. Kies testdata die het gedrag uitlokt, niet
  de makkelijkste die slaagt: bij lijsten altijd leeg, één én meerdere (een lijst
  van 1 verbergt "geeft de enige terug" i.p.v. "kiest de juiste"). Bundel
  cardinaliteiten met `pytest.mark.parametrize`.
- **Reviews.** Classificeer bevindingen op ernst (hoog/medium/laag); hoog pak je
  direct aan, laag mag naar `NEXT_STEPS.md`.
- **Build-output.** "Groen" zegt alleen iets als er geen onverklaarde nieuwe
  waarschuwingen bij komen. Trieer ze, of accepteer ze expliciet met reden.
- **`gh` is niet geïnstalleerd.** Gebruik de GitHub-API via `curl` (de repo is
  publiek, dus lezen kan zonder token): `curl -s
  "https://api.github.com/repos/MinBZK/moza-poc-digitale-assistent/pulls"`.

## Verantwoorde inzet van AI

Niet-testcode wordt menselijk gereviewd vóór merge via de pull-request-workflow
(met `CODEOWNERS`); testcode wordt functioneel beproefd. Zie
[`docs/ai-verantwoording.md`](docs/ai-verantwoording.md). De AI-governance van
het *product zelf* (de runtime-assistent) staat los in `docs/preparation/` (IAMA,
AI-verordening, en per databron een eigen DPIA/AVG-voorbereiding); dit verschilt
van de verantwoording van het ontwikkelgereedschap.

## Verwante repositories

- [`MinBZK/MijnOverheidZakelijk`](https://github.com/MinBZK/MijnOverheidZakelijk) — hoofdrepo (SUPPORT, GOVERNANCE, SECURITY centraal).
- `MinBZK/moza-poc` — de Eleventy-frontend/portal die deze backend via HTTP aanroept.
- [`MinBZK/moza-mcp-standaard-poc`](https://github.com/MinBZK/moza-mcp-standaard-poc) — de MCP-standaard waartegen `validate-mcp-servers.sh` valideert.

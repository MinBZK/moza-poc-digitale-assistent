# PDR-007: Demo-persona's, netbeheerder-bron en EML-maatregelbepaling

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-06-11 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | PDR-003 (orkestratie), [PDR-006](PDR-006-feasibility-conclusie.md) |

## Context

Voor de Dag van de Toekomst (18 juni 2026) demonstreren we de ideale flow van
de informatieplicht energiebesparing: proactief attenderen, gegevens bij de
bron raadplegen, en een machine-uitvoerbare regel die bepaalt welke
maatregelen gelden. Daarvoor is een tweede testcasus nodig (Claudia van Dam /
Koffiezaak Noon, horeca, verbruik boven de drempel) naast de bestaande
demo-gebruiker (Robin Vogel / Test BV Donald), plus een verbruiksbron en een
maatregelbepaling. De frontend (dashboard, melding, persona-keuze) leeft in
`MinBZK/moza-poc`; deze repo levert alleen de assistent-backend.

## Beslissingen

### 1. Persona-selectie via omgevingsvariabele (`DEMO_KVK_NUMMER`)

De KvK-server bindt de sessie aan één KvK-nummer. Voor de demo is dat nummer
nu instelbaar via `DEMO_KVK_NUMMER`; mock-persona's die niet in de KvK Test
API bestaan worden volledig lokaal geserveerd (`MOCK_PROFIELEN`). Wisselen
van persona = host herstarten. Bewust simpel gehouden voor de demo.

**Bevindingen voor de echte bouw** (sessie-gebonden identiteit, MVP-01):

- De identiteit hoort uit de authenticatie (eHerkenning) te komen en per
  *request* te gelden, niet per *serverproces*. De huidige MCP-servers zijn
  stateful subprocessen met één identiteit voor hun hele levensduur; echte
  multi-tenancy vraagt identiteit-doorvoer per tool-aanroep (bv. via een
  sessie-token in de MCP-context) óf per-sessie serverinstanties.
- De MCP Python SDK geeft subprocessen standaard een **minimale** omgeving
  mee (alleen HOME/PATH e.d.) — config via env bereikte de servers nooit.
  De host geeft nu expliciet `os.environ` door (`mcp_client.py`). Dit gold
  ook al voor `REGELRECHT_RPC_URL`.

  > **Bijgesteld door PDR-010 (MVP-02).** "Expliciet `os.environ` doorgeven" is
  > vervangen door een expliciete allowlist per transport
  > (`services/host/subprocess_env.py`): de config die de servers uitlezen komt
  > erdoor, LLM-sleutels niet. Dit PDR blijft staan als audit-trail; voor de
  > actuele regel geldt PDR-010 §4.
- Mock-persona's moeten de échte API-vorm volgen (KvK Basisprofiel), anders
  wijkt downstream-gedrag (adres-extractie, BAG-verrijking) af tussen mock
  en echt.

### 2. Netbeheerder als vijfde MCP-bron (mock)

Nieuw: `services/mcp/netbeheerder/server.py` met read-only tool `verbruik`
(jaarverbruik elektriciteit/gas per KvK-nummer). Hiermee raadpleegt de
assistent verbruik bij de bron in plaats van het aan de ondernemer te vragen.
Alleen Noon heeft mock-data; voor onbekende nummers meldt de server "geen
gegevens" en valt de assistent terug op uitvragen — de bestaande
Donald-flow blijft daardoor ongewijzigd. In productie vereist dit een echte
netbeheerder-koppeling mét machtiging van de ondernemer.

### 3. EML-maatregelbepaling in de RegelRecht-server (lokale mock)

De bepaling welke EML-maatregelen gelden (op basis van bedrijfstak en
feitelijke bedrijfskenmerken zoals koel-/afzuiginstallatie) staat als tool
`maatregelen` in de **RegelRecht-server** — regelevaluatie hoort bij
RegelRecht, ook al is dit nog een lokale mock naast de proxy naar
poc-machine-law. De provenance markeert dit expliciet als lokale mock
(`EML_SOURCE_LABEL`). **Vervolgstap:** verhuist naar de poc-machine-law
engine zodra die EML-regels ondersteunt; de tool-interface kan dan gelijk
blijven. De feitelijke vragen blijven bewust bij de ondernemer (alleen
feiten, geen regelinterpretatie) en worden als `bedrijfskenmerken`
meegegeven aan `rvo__indienen` ("bewaard voor de volgende ronde").

**Addendum (2026-06-11):** de vervolgstap is uitgevoerd — de EML-bepaling
draait nu als wet `omgevingswet/energiebesparing/maatregelen` in de
poc-machine-law engine (zie
`docs/superpowers/specs/2026-06-11-eml-naar-engine-design.md` en
MinBZK/poc-machine-law#483). Daarbij is de structuur gemoderniseerd naar de
EML 2023 (één lijst, onderdelen Gebouwen/Faciliteiten/Processen, echte
maatregelcodes; het bedrijfstak-model en de `sbi_code`-parameter zijn
vervallen) en worden de feitelijke vragen niet meer hardcoded gesteld maar
door de assistent afgelezen uit de wet-spec (parameter-descriptions). De
lokale mock blijft als fallback met eigen provenance-label. Bekende
beperking voor de echte bouw: per-maatregel boolean outputs schalen niet
naar de volledige EML (~150 maatregelen) — daarvoor is een
list/map-uitbreiding van de engine nodig.

### 4. Geautomatiseerde toets als onderdeel van de indienings-response

De omgevingsdienst-toets (stap 4 van de flow) is een mock-veld `toets` in de
`rvo__indienen`-response plus journal/taken in de lopende zaak. Deterministisch
"AKKOORD" — de demo toont het patroon (zelfde machine-uitvoerbare regel,
geen herstelronde), niet een echte toetsservice.

## Buiten scope (frontend, `MinBZK/moza-poc`)

Stap 0/1 van de flow (proactieve notificatie op het dashboard, melding
openen, persona-keuze) mockt de frontend zelf; deze backend levert daar
bewust geen endpoint voor.

## Gevolgen

- CLI-transport (cli:vlam/cli:claude) kent de nieuwe tools **niet**
  (netbeheerder/maatregelen ontbreken in `CLI_TOOL_DEFINITIONS_ANTHROPIC` en
  `cli_executor`); de demo draait op MCP-transport (default `vlam`/`claude`).
- `validate-mcp-servers.sh` valideert nu vijf servers.
- Tests in `services/host/tests/test_demo_personas.py` borgen de
  demo-invarianten (drempel, BAG-fallback, EML-logica, Donald ongewijzigd).

## Addendum (2026-06-19): besluit 4 (geautomatiseerde toets) herzien

Besluit 4 introduceerde een geautomatiseerde omgevingsdienst-toets die de
rapportage direct als "AKKOORD" markeerde (geen herstelronde). Dat is
**teruggedraaid**: een PoC mag bij een muterende overheidsactie geen directe
goedkeuring suggereren. Na `rvo__indienen` is de status nu "in behandeling
genomen" en verwijst de assistent naar 'Lopende zaken'; de respons claimt nooit
dat de rapportage is goedgekeurd, akkoord of getoetst is.

- Het `toets: AKKOORD`-blok is uit de `rvo__indienen`-respons verwijderd; de
  `lopende_zaak` toont status "In behandeling" met een taak "Beoordeling door de
  omgevingsdienst".
- Systeemprompt (`tool_usage.md`) en de voorbeeldflow instrueren expliciet: nooit
  directe goedkeuring melden, altijd naar 'Lopende zaken' verwijzen.
- De `lopende_zaak` is verrijkt met `organisatie` + `onderwerp` (naast het stabiele
  `referentienummer`) zodat de frontend geen eigen fallback-registry meer nodig heeft.
- De rest van besluit 4 (de zaak verschijnt onder 'Lopende zaken') blijft gelden.

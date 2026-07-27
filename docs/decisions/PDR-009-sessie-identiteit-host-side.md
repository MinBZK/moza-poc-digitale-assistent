# PDR-009: Bedrijfsidentiteit server-side bepaald door de host-sessie

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-07-27 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | [PDR-005](PDR-005-cli-vs-mcp-transport.md), [PDR-007](PDR-007-demo-persona-en-netbeheerder-bron.md), [PDR-008](PDR-008-generieke-regelrecht-tool-en-wallet.md) |

## Context

Tot nu toe was de assistent hard gekoppeld aan één testbedrijf. Het actieve
KvK-nummer stond als proces-globale constante in de KvK-server
(`SESSIE_KVK_NUMMER = os.getenv("DEMO_KVK_NUMMER") or "68750110"`), en om een
andere persona te tonen moest de hele backend met een andere `DEMO_KVK_NUMMER`
herstart worden. Voor een demo werkt dat, maar voor een test met echte
ondernemers is het onbruikbaar: iedereen zou hetzelfde (test)bedrijf zien.

Daarnaast namen twee tools het KvK-nummer als **invoer** van het LLM:
`regelrecht__execute_law` (via `parameters.KVK_NUMMER`) / `regelrecht__check`
en `rvo__indienen` (via `kvk_nummer`). Daardoor kon het model — of een handige
gebruiker — in het gesprek een *ander* KvK-nummer laten gebruiken dan dat van de
ingelogde persoon. Identiteit hoort niet door de conversatie bepaald te worden.

Dit is issue **MVP-01** (echte bedrijfsidentiteit via sessie). Echte inlog via
eHerkenning/DigiD is bewust een apart Beta-ticket (BETA-02) en volgt de
NL GOV-authenticatiestandaarden (OAuth-NL-profiel / OIDC-NLGOV, zie de
Logius IAM-standaarden). Dit PDR gaat alleen over de gesloten testgroep.

## Beslissingen

### 1. De host is de identiteits-autoriteit, niet de MCP-server

De security-grens verschuift van *"elke MCP-server kent zijn eigen
sessie-KvK via env"* naar *"de host bepaalt het KvK-nummer per request en
injecteert het bij elke bron-aanroep"*. De MCP-servers worden hierdoor
stateless multi-tenant: ze bedienen het KvK-nummer dat de host meegeeft. Omdat
alléén de host met de MCP-servers praat (stdio-subprocessen, niet publiek), is
de host het enige vertrouwde punt waar identiteit wordt vastgesteld.

### 2. Identiteit via een vertrouwd token in een HTTP-header

De frontend stuurt per request de header **`X-Test-User: <token>`**. De host
mapt dat token naar een KvK-nummer via een vooraf ingestelde lijst
(`TEST_USERS` in de env: `token:kvk,token:kvk,...`). Dit sluit aan op het al
bestaande patroon waarin de frontend `X-VLAM-API-Key` / `X-Claude-API-Key` door
de nginx-proxy (ZAD-hosting) naar de backend stuurt — bewezen werkend transport,
buiten de conversatie-payload en dus niet in de gespreksgeschiedenis of logs.

Het token staat los van de `session_id` (die blijft puur een gespreks-bucket).
Identiteit wordt per request opnieuw uit het token afgeleid; er is geen
server-side sessie-store die door een geraden `session_id` te kapen valt.

### 3. Het KvK-nummer wordt server-side geïnjecteerd en overschreven

De host injecteert het sessie-KvK vlak vóór elke bron-aanroep, in álle
transport-paden (MCP en CLI, Claude en VLAM):

- `kvk__mijn_bedrijf` / `kvk__vestigingen` / `kvk__eigenaar` → `kvk_nummer` toegevoegd;
- `regelrecht__check` (CLI) en `rvo__indienen` → `kvk_nummer` **overschreven**;
- `regelrecht__execute_law` (MCP) → `parameters.KVK_NUMMER` **overschreven**, maar
  alléén voor de informatieplicht-regel (de maatregelen-regel gebruikt
  `parameters` als feiten en krijgt géén KvK-injectie).

Wat het LLM ook invult, de sessie-waarde wint. Aanvullend wordt `kvk_nummer`
**uit de LLM-zichtbare tool-schema's gehaald** (de Anthropic/OpenAI-defs én de
MCP `tools/list`), zodat het model de parameter niet eens kan meegeven.

### 4. Geen geldige sessie ⇒ hard blokkeren

Zonder (of met onbekend) token beantwoordt de host de vraag niet: `/chat` geeft
HTTP 401 met een nette melding ("log eerst in"), en er wordt géén LLM- of
bron-aanroep gedaan. Zo lekt er nooit per ongeluk andermans bedrijfsdata.

### 5. Het demo-KvK-nummer is geen default-voor-iedereen meer

De hardcoded `or "68750110"` verdwijnt uit de KvK-server. `DEMO_KVK_NUMMER`
blijft bestaan als optionele **dev-fallback** voor wie de KvK-server standalone
draait (buiten de host, zonder sessie); wordt die niet gezet én injecteert de
host geen KvK, dan geeft de server een expliciete fout in plaats van stilzwijgend
Test BV Donald te tonen.

## Alternatieven overwogen

- **Per-sessie MCP-subprocessen starten (env per proces).** Verworpen: één
  subprocess per gebruiker schaalt niet, en het houdt de identiteit alsnog in de
  server in plaats van bij de host. De gedeelde, persistente MCP-verbindingen
  (PDR-005) zouden vervallen.
- **`session_id` hergebruiken als identiteit.** Verworpen: `session_id` is
  client-gegenereerd en raadbaar; dan zou een gebruiker met andermans
  `session_id` diens bedrijf zien. Een apart, niet-geraden token is nodig.
- **KvK-nummer als invoer laten, maar server-side valideren.** Verworpen: zolang
  de parameter in het schema staat, blijft het model 'm invullen en moet elke
  server de check dupliceren. Strippen + injecteren is robuuster en centraal.
- **Echte eHerkenning nu al.** Buiten scope: dat is BETA-02 en vergt de
  NL GOV-authenticatiestandaarden; voor een gesloten testgroep is een token
  voldoende en veel sneller.

## Consequenties

- Persona wisselen kan nu **zonder de backend te herstarten**: een ander token
  volstaat. De frontend-beperking ("herstart backend bij persona-wissel") vervalt
  zodra de frontend het token meestuurt.
- De KvK-server cachet nu **per KvK-nummer** in plaats van globaal.
- **CLI-kanttekening:** `regelrecht__check` en `rvo__indienen` krijgen het
  geïnjecteerde KvK-nummer via hun argumenten en werken dus meteen. De
  `kvk-cli`-tools (`basisprofiel get/vestigingen/eigenaar`) lezen nog steeds
  `DEMO_KVK_NUMMER` uit de env; het CLI-transport loopt bewust achter (PDR-005/008)
  en de demo draait op MCP, dus dit blijft een bekende beperking van het CLI-pad.
- Muteren blijft achter bevestiging (`rvo__indienen`, PDR-007); dat staat los van
  deze wijziging.
- Vervolg: BETA-02 vervangt de token-lijst door echte authenticatie; de
  injectie- en hard-block-logica in de host blijft dan ongewijzigd — alleen de
  bron van het KvK-nummer verandert (van token-map naar auth-claim).

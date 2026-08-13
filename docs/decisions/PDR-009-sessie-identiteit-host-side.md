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

> **Achterhaald door het [addendum van 2026-08-03](#addendum-2026-08-03-token-indirectie-vervalt-kvk-nummer-in-de-header).**
> Het token is vervangen door het KvK-nummer zelf, met een allowlist
> (`TEST_KVK_NUMMERS`). De rest van deze paragraaf beschrijft de oorspronkelijke
> keuze en blijft staan als audit-trail.

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

## Addendum (2026-07-29): drie testprofielen in plaats van één

Bij het lokaal beproeven bleek één testprofiel te smal. De frontend
(`MinBZK/moza-poc`) kent negentien persona's, maar de backend had alleen
mockdata voor Koffiezaak Noon. Wisselde een tester naar een andere persona, dan
was er geen bedrijf om te tonen. Daarom is de gesloten testgroep uitgebreid naar
drie profielen, gekozen op **verschil in uitkomst** en niet op verscheidenheid
op zichzelf:

| KvK | Bedrijf | Persona | Uitkomst informatieplicht |
|---|---|---|---|
| 85234567 | Koffiezaak Noon | `koffiezaak` | geldt, via elektriciteit |
| 62345681 | Kwekerij De Bloesem | `bloemenkweker` | geldt, via gas + elektriciteit |
| 56789012 | Roots & Locks | `haarstylist` | geldt niet, onder beide drempels |
| 61234570 | Vogel Bouwregie B.V. | `bouwmanagement` | geldt, via elektriciteit |

Zo doorloopt een gebruikerstest alle takken van dezelfde regel, inclusief de
negatieve uitkomst — die anders nooit getoond wordt, terwijl juist daar de
uitleg van de assistent telt.

**Persona's zonder token blijven bewust geblokkeerd.** Het alternatief (elke
persona een token geven en de KvK-server laten terugvallen op de Test API) is
verworpen: dan krijgt een tester een leeg of vreemd bedrijfsprofiel te zien, wat
verwarrender is dan een expliciet "log eerst in". Een profiel toevoegen vereist
dus mockdata in zowel de KvK- als de netbeheerder-server;
`services/host/tests/test_testprofielen.py` faalt als er één ontbreekt.

**Bijvangst — een gat in de injectie.** De uitbreiding legde bloot dat
`mcp_client._strip_kvk_param` `kvk_nummer` uit *alle* LLM-zichtbare schema's
knipt, terwijl `vlam_host._KVK_SESSIE_TOOLS` het maar voor vijf tools
terug-injecteerde. `netbeheerder__verbruik` viel daarbuiten en kreeg dus altijd
een lege `kvk_nummer`, waardoor de informatieplicht-flow (PDR-007) strandde op
"ontbrekend verbruik". De tool is aan de injectie-set toegevoegd; een test
(`test_kvk_injectie_dekking.py`) leest nu de echte tool-definities uit de
MCP-servers en faalt zodra een tool wél `kvk_nummer` vraagt maar buiten de
injectie valt. Strippen en injecteren horen één lijst te delen; tot die
refactor bewaakt de test de koppeling.

## Addendum (2026-08-03): token-indirectie vervalt, KvK-nummer in de header

De oorspronkelijke opzet gebruikte een **token** in de `X-Test-User`-header, dat
de host via `TEST_USERS` (`token:kvk`-paren) naar een KvK-nummer mapte. Dat
token is vervangen door het **KvK-nummer zelf**; `TEST_KVK_NUMMERS` is nu een
allowlist van toegestane nummers.

**Aanleiding.** Het token beschermde niets. De KvK-nummers van de testpersona's
staan al publiek in `_data/personas.json` in de open frontend-repo
(`MinBZK/moza-poc`), dus er viel geen geheim te bewaren. Wat het token wél
kostte: een GitHub-secret (`MOZA_TEST_USERS`) voor de frontend-build, een
tweede lijst in de backend-env die daar exact mee moest matchen, en een stille
faalmodus wanneer die twee uit de pas liepen — de assistent antwoordde dan
overal "log eerst in" zonder enige aanwijzing waarom. Bovendien belandde het
token alsnog in de paginabron (`window.MOZA_TEST_USERS`), waardoor de
onraadbaarheid in de praktijk niet bestond.

**Wat níét verandert.** De garantie die deze PDR draagt, staat los van waar het
nummer vandaan komt: het LLM ziet `kvk_nummer` niet (het is uit álle
LLM-zichtbare tool-schema's gestript) en de host injecteert het server-side vlak
vóór elke bron-aanroep, in alle vier de transport-paden. Noemt de gebruiker in
het gesprek een ander KvK-nummer, dan blijft het sessie-nummer leidend. Dat is
end-to-end beproefd op zowel de Claude- als de VLAM-backend.

**Waarom een header en niet de URL.** Een query-parameter (`?kvk=...`) is
overwogen en verworpen: nginx logt standaard de volledige request-regel, en dat
geldt ook voor proxy-logs, browserhistorie en `Referer`-headers. Dat zou de
log-hygiëne uit deze PDR (`_pad_zonder_kvk`, `_arg_keys`, audit-logs met alleen
veldnamen) in één keer ongedaan maken. Een header wordt niet gelogd tenzij je
daar expliciet om vraagt.

**Waarom de allowlist blijft.** Zonder grens zou de KvK-server voor een
willekeurig meegestuurd nummer de echte KvK Test API gaan bevragen. De allowlist
is dus geen geheim maar een begrenzing, en levert tegelijk het "log eerst
in"-gedrag op dat MVP-01 vereist.

**Consequentie voor de frontend.** De hele token-machinerie vervalt:
`_data/testUsers.js`, `window.MOZA_TEST_USERS` in `base.njk`, de
`MOZA_TEST_USERS` build-arg in `Containerfile` en de drie workflows, en het
GitHub-secret. De frontend stuurt het `kvkNummer` van de actieve persona
rechtstreeks mee.

**Wat dit expliciet níét is.** De gebruiker kan de headerwaarde in de browser
wijzigen en zo een andere testpersona worden. Dat kon met het token ook al — de
persona-keuze is client-side en het token stond in de paginabron. Voor een
gesloten testgroep met uitsluitend fictieve data is dat aanvaardbaar; het is
géén authenticatie. Echte identiteitsvaststelling (eHerkenning/DigiD, NL GOV
OAuth/OIDC) is BETA-02. De *vorm* blijft dan gelijk — header naar binnen,
server-side valideren, server-side injecteren — alleen de allowlist wordt
vervangen door de authenticatie.

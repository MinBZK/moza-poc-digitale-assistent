# PDR-008: Eén generieke RegelRecht-tool en energiegegevens via de Wallet

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-06-16 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | [PDR-005](PDR-005-cli-vs-mcp-transport.md), [PDR-007](PDR-007-demo-persona-en-netbeheerder-bron.md) |

## Context

RegelRecht is één engine (`poc-machine-law`); de MCP-server is daar een proxy
op. Toch exposeerde die server twee aparte tools (`check` en `maatregelen`),
elk gekoppeld aan één wet. Dat wekt de indruk dat "EML" een aparte
voorziening is naast RegelRecht, terwijl het gewoon een wet in dezelfde engine
is (`omgevingswet/energiebesparing/maatregelen`).

Daarnaast haalde de demo het energieverbruik op via een directe bevraging van
een netbeheerder-mock (PDR-007). Voor de Dag van de Toekomst willen we het
model van de **EU Business Wallet** tonen: de ondernemer *houdt* een
verbruiks-attestatie (afgegeven door de netbeheerder) in zijn wallet en
*deelt* die met toestemming — gegevens komen "uit de wallet", niet uit een
stille achtergrond-query. Zie
<https://digital-strategy.ec.europa.eu/nl/policies/business-wallets>.

## Beslissingen

### 1. Eén generieke RegelRecht-tool: `execute_law(law, parameters, overrides, service)`

De RegelRecht-server biedt nog maar één tool, `regelrecht__execute_law`, die
de uit te voeren wet via de parameter `law` kiest. Dit spiegelt wat de engine
zelf aanbiedt (`execute_law`) en maakt EML geen aparte tool meer.

- De **EML-maatregelenwet** behoudt intern haar twee-staps-flow (eerst lege
  parameters → `benodigde_feiten` uit de rule-spec, daarna de feiten) én de
  lokale fallback bij een onbereikbare engine (PDR-007-addendum). Bij die wet
  *zijn* de `parameters` de feiten.
- **Andere wetten** (zoals `.../informatieplicht`) gaan generiek naar de engine
  en worden vereenvoudigd teruggegeven; geen lokale fallback.
- **Trade-off:** het LLM moet nu law-namen en engine-parameternamen
  (HOOFDLETTERS, `overrides` per service) kennen. Ondervangen via de
  tool-beschrijving, de bijgewerkte voorbeeldprompts en de
  parameter-descriptions in de rule-spec.

### 2. Energiegegevens via de (EU Business) Wallet — demo-presentatielaag

De verbruiksgegevens worden gepresenteerd als een door de wallet gedeelde
**verifiable credential**: uitgever (issuer) = netbeheerder-mock, houder =
de ondernemer, mét expliciete toestemming. De bron die de gebruiker ziet is
de **Wallet**; de netbeheerder is de uitgever.

**Bewust GEEN echte wallet-/MCP-koppeling.** De wallet is voor de demo een
presentatie-/toestemmingslaag bovenop de bestaande netbeheerder-mock (die de
attestatie "uitgeeft"). Er komt geen aparte wallet-MCP-server. De
respons-`provenance` zet `source` op de wallet en voegt `issuer` toe; de data
bevat een `credential`- en een `toestemming`-blok.

### 3. De feitelijke vragen staan in het regel-model, niet in de wet

Belangrijk om niet verkeerd voor te stellen: de **vraagteksten** ("Heeft het
bedrijf een koel- of vriesinstallatie?") staan **niet in de wet/regeling**. De
EML (ministeriële regeling) bevat per maatregel de *toepasselijkheids-
voorwaarden* (de uitgangssituatie waaronder een maatregel geldt). De stap van
"voorwaarde" naar "vraag aan de ondernemer" is **mensenwerk in het regel-model
(wetsanalyse)**: wie de regeling in `poc-machine-law` modelleert, vertaalt elke
benodigde voorwaarde naar een parameter én schrijft daar een `description` bij —
en díe description tonen wij als vraag.

Gevolg: de assistent verzint de vragen niet (hij leest ze af uit de rule-spec),
maar de bron van waarheid is de **regel-definitie**, niet de wettekst. De
juistheid van de vragen hangt dus af van wie het regel-model schrijft en
reviewt (te beleggen verantwoordelijkheid: de regelhouder/RVO valideert dat
parameters + vraagteksten de EML getrouw weergeven).

### 4. Geverifieerde runtime-status (2026-06-16)

Tegen het live engine-endpoint (`REGELRECHT_RPC_URL`) gecontroleerd:

- De **informatieplicht-wet draait live** op de engine en geeft parameter-
  beschrijvingen terug (bv. `IS_WOONFUNCTIE` → "Of het pand uitsluitend een
  woonfunctie heeft"). Het vraag-uit-de-rule-spec-mechanisme werkt daar dus echt.
- De **maatregelen-wet is wél gemerged** (`poc-machine-law#483`:
  `laws/omgevingswet/energiebesparing/maatregelen/RVO-2024-01-01.yaml`, service
  `RVO`), maar het **gedeployde engine-endpoint draait nog een oude build** en
  kent de wet niet ("No rules found for law: ..."). Merge in de repo ≠ herdeploy
  van de draaiende instance. De EML-stap van de demo draait daarom **op de lokale
  fallback** — de EML-vraagteksten komen nu uit `EML_FALLBACK_VRAGEN` in
  `services/mcp/regelrecht/server.py`.
  - **Geverifieerd:** de YAML uit #483 komt exact overeen met onze call-signature
    en fallback (zelfde law-pad, service, parameternamen en `eml_*`-outputs). Er
    is dus **geen wijziging in deze repo nodig**; zodra de engine-instance is
    ververst, schakelt `_maatregelen` automatisch over van fallback naar engine
    (provenance flipt van "lokale fallback" naar "RegelRecht (poc-machine-law)").
  - **Actie (poc-machine-law-kant):** de instance achter `REGELRECHT_RPC_URL`
    opnieuw deployen/laden vanaf de gemergede main (mogelijk release/tag-bump of
    cache-/herstart nodig). Daarna verifiëren met `services/host/scripts/check_eml_engine.py`.

Dit nuanceert het PDR-007-addendum ("draait nu als wet in de engine"): dat geldt
zodra de engine-instance #483 serveert; tot die tijd is de fallback de
feitelijke bron.

## Gevolgen

- **CLI-transport** (cli:vlam/cli:claude) houdt voorlopig `regelrecht__check`
  (loopt achter, conform PDR-005/PDR-007). De demo draait op MCP (default
  `vlam`/`claude`), waar `regelrecht__execute_law` geldt. De voorbeeldprompts
  zijn bijgewerkt naar de generieke tool.
- **Frontend (`MinBZK/moza-poc`)** toont de Wallet als **databron** (los van de
  capabilities/tools) en kent een expliciet deel-/toestemmingsmoment. Zie de
  losse implementatie-prompts bij deze wijziging.
- **Tests** borgen de dispatch (`_execute_law`) en de wallet-credential met
  toestemming; de bestaande EML- en demo-invarianten blijven gelden.
- **Vervolg (echte bouw):** een echte EUDI/Business Wallet-presentatie
  (OpenID4VP, credential-uitgifte door de netbeheerder) valt buiten de PoC.

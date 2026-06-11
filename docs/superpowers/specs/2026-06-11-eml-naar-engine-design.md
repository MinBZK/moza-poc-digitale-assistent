# Design: EML-maatregelbepaling naar de poc-machine-law engine

| Veld | Waarde |
|---|---|
| Datum | 2026-06-11 |
| Status | Goedgekeurd ontwerp, implementatie vóór 18 juni 2026 (Dag van de Toekomst) |
| Gerelateerd | PDR-007 (§3, "vervolgstap"), `services/mcp/regelrecht/server.py` |
| Repo's | `MinBZK/poc-machine-law` (wet-YAML) + deze repo (omschakeling) |

## Context en doel

De bepaling welke EML-maatregelen (Erkende Maatregelenlijst, subset Horeca)
gelden staat nu als **lokale mock** in de RegelRecht-MCP-server
(`EML_HORECA` + `_geldende_maatregelen()`). PDR-007 §3 benoemt als
vervolgstap: verhuizen naar de poc-machine-law engine zodra die EML-regels
ondersteunt, met gelijkblijvende tool-interface.

Dit design voert die vervolgstap uit, vóór de demo van 18 juni: de
EML-bepaling wordt een machine-uitvoerbare wet in de engine; de
MCP-server wordt een dunne proxy (zoals hij voor `check_informatieplicht`
al is). De demo-flow en de tool-interface `regelrecht__maatregelen`
veranderen niet.

## Gekozen aanpak (optie A): per-maatregel outputs

De engine kan geen lijst-van-objecten als output uitdrukken (`CONCAT` is
string-only, `FOREACH` alleen aggregatie via `combine`). Daarom krijgt
**elke EML-maatregel een eigen boolean output** in de wet-YAML. Dat past
bij de aard van de EML: elke maatregel ís een regel met een eigen
toepasselijkheidsvoorwaarde en eigen grondslag — en de engine levert dan
per maatregel explainability.

Verworpen alternatieven:

- *Booleans per voorwaardegroep* (koeling/afzuiging): minimale YAML, maar
  de maatregelenlijst zelf blijft dan regelkennis in de MCP-server — half
  verhaal.
- *Engine uitbreiden met een list/map-operatie*: engine-core wijzigen één
  week voor de demo is onverantwoord.

## Deel 1 — wet-YAML in poc-machine-law

Nieuw bestand:
`laws/omgevingswet/energiebesparing/maatregelen/RVO-2024-01-01.yaml`
(schema v0.1.7, zelfde conventies als
`laws/omgevingswet/energiebesparing/informatieplicht/RVO-2024-01-01.yaml`).

Kern van het ontwerp:

```yaml
law: omgevingswet/energiebesparing/maatregelen
service: "RVO"
name: Erkende Maatregelenlijst energiebesparing (subset Horeca)
legal_basis:
  law: "Besluit activiteiten leefomgeving"
  bwb_id: "BWBR0041330"
  article: "5.15"          # energiebesparingsplicht; EML als invulling

properties:
  parameters:
    - name: "BEDRIJFSTAK"          # maakt expliciet dat dit de horeca-subset is
      type: "string"
      required: true
    - name: "HEEFT_KOELINSTALLATIE"     # feit, geleverd door ondernemer
      type: "boolean"
      required: true
    - name: "HEEFT_AFZUIGINSTALLATIE"   # feit, geleverd door ondernemer
      type: "boolean"
      required: true

  output:
    # per EML-maatregel één boolean; naam van de maatregel in description
    - name: "eml_h01_van_toepassing"
      description: "LED-verlichting in verblijfsruimten"
      type: "boolean"
      citizen_relevance: primary
    # ... idem voor H02, H03, H10, H11, H20, H21

requirements:
  - all:
      - subject: "$BEDRIJFSTAK"
        operation: EQUALS
        value: "horeca"

actions:
  - output: "eml_h01_van_toepassing"   # "altijd"-maatregelen
    value: true
  # ...
  - output: "eml_h10_van_toepassing"   # conditionele maatregelen
    value: "$HEEFT_KOELINSTALLATIE"
  - output: "eml_h20_van_toepassing"
    value: "$HEEFT_AFZUIGINSTALLATIE"
  # ...
```

Ontwerpkeuzes:

- **Feiten als `parameters`, niet als `sources`.** De bedrijfskenmerken
  (koel-/afzuiginstallatie) staan nergens geregistreerd; de ondernemer
  levert ze (PDR-007 §3). Parameters maken dat expliciet en vereisen geen
  brontabellen in de engine.
- **`BEDRIJFSTAK`-requirement `EQUALS "horeca"`** maakt eerlijk dat dit de
  horeca-subset is. Andere bedrijfstak → `requirements_met: false`, geen
  outputs; de MCP-server vertaalt dat naar "geen maatregelbepaling
  beschikbaar voor deze bedrijfstak".
- **Per output een `legal_basis`** (Bal art. 5.15; explanation verwijst
  naar de betreffende EML-maatregel), conform de conventies van de
  bestaande informatieplicht-YAML.
- Elke maatregel krijgt altijd een output (true/false), zodat de
  bestaande tool-semantiek (`van_toepassing` per maatregel) behouden
  blijft.

Validatie: schema-validatie van poc-machine-law (`script/`) + pre-commit
aldaar. PR naar `MinBZK/poc-machine-law` main.

## Deel 2 — omschakeling in deze repo

`services/mcp/regelrecht/server.py`:

1. `_bepaal_maatregelen` (de tool-handler voor `maatregelen`) roept
   `execute_law` aan via de bestaande `_rpc_call`, met
   `service: "RVO"`, `law: "omgevingswet/energiebesparing/maatregelen"`
   en de drie parameters. Zelfde patroon als `_check_informatieplicht`.
   De tool-input `sbi_code` wordt in de server vertaald naar
   `BEDRIJFSTAK` (SBI 55–56 → `"horeca"`, anders de bestaande
   "geen maatregelenlijst beschikbaar"-melding); die vertaling is
   presentatie-/routeringslogica en blijft bewust buiten de wet-YAML.
2. **Mapping engine-response → bestaande tool-vorm.** De
   `execute_law`-response bevat `output` (de booleans) én `rule_spec`
   (de volledige wet-spec). De server bouwt daaruit de bestaande
   lijst-vorm: per output `eml_<id>_van_toepassing` een item
   `{id, naam, van_toepassing}` met `naam` uit de output-`description`
   in `rule_spec`. De maatregelnamen komen dus uit de engine; de
   MCP-server bevat geen regelkennis meer.
3. **Lokale mock blijft als fallback.** Bij `SOURCE_UNAVAILABLE` of een
   onbruikbare response valt de server terug op de huidige lokale
   evaluatie (`EML_HORECA`). De provenance vermeldt eerlijk welke route
   is gebruikt: `"RegelRecht (poc-machine-law)"` bij de engine,
   het bestaande `EML_SOURCE_LABEL` ("lokale mock") bij fallback.
   De demo kan daardoor niet stuk door deze omschakeling.
4. Tool-interface (`regelrecht__maatregelen`, inputschema, outputvorm)
   blijft ongewijzigd — geen wijzigingen in host, prompts of frontend.

## Deploy-sporen (risico demo 18 juni)

| Spoor | Wat | Wanneer |
|---|---|---|
| a | PR poc-machine-law mergen; digilab-deploy van `ui.lac.apps.digilab.network` vóór 18/6 | voorkeursroute |
| b | Engine lokaal draaien (Dockerfile aanwezig) en `REGELRECHT_RPC_URL` ernaar wijzen (werkt sinds de env-doorvoer-fix in `mcp_client.py`) | als (a) niet op tijd lukt |
| vangnet | Fallback naar lokale mock (deel 2, punt 3) | altijd actief |

## Tests

- Bestaande EML-invarianten in `services/host/tests/test_demo_personas.py`
  blijven gelden (zelfde tool-output) — geen aanpassing nodig.
- Nieuw: unit-test voor de mapping engine-response → lijst-vorm
  (op basis van een vaste voorbeeld-response, geen netwerktoegang).
- Nieuw: test dat fallback naar de lokale mock werkt als de engine
  onbereikbaar is, en dat de provenance het juiste label draagt.
- Handmatig integratiescript (vereist netwerk) naast de bestaande
  scripts in `services/host/scripts/`: end-to-end `maatregelen` tegen de
  echte engine voor Noon (horeca, koeling + afzuiging → 7 maatregelen,
  alle 7 `van_toepassing: true`).

## Documentatie

- PDR-007 §3 krijgt een addendum: vervolgstap uitgevoerd, met verwijzing
  naar dit design en de poc-machine-law PR. (PDR zelf blijft staan,
  conform `docs/decisions/README.md`.)

## Buiten scope / bevindingen voor de echte bouw

- **Schaalbaarheid**: per-maatregel outputs schalen niet naar de volledige
  EML (~150 maatregelen over alle bedrijfstakken). Voor de echte bouw is
  een list/map-uitbreiding van de engine (of een aparte
  maatregelen-resource) nodig. Vastleggen in het PDR-addendum.
- Volledige EML (andere bedrijfstakken, terugverdientijd-criteria) blijft
  buiten scope; dit is de demo-subset Horeca.
- CLI-transport kent `maatregelen` al niet (PDR-007 "Gevolgen") — blijft zo.

# Design: EML-maatregelbepaling naar de poc-machine-law engine

| Veld | Waarde |
|---|---|
| Datum | 2026-06-11 (herzien: EML 2023-structuur, feiten uit engine) |
| Status | Ontwerp ter review, implementatie vóór 18 juni 2026 (Dag van de Toekomst) |
| Gerelateerd | PDR-007 (§3, "vervolgstap"), `services/mcp/regelrecht/server.py` |
| Repo's | `MinBZK/poc-machine-law` (wet-YAML) + deze repo (omschakeling) |

## Context en doel

De bepaling welke EML-maatregelen gelden staat nu als **lokale mock** in de
RegelRecht-MCP-server (`EML_HORECA` + `_geldende_maatregelen()`), in de
verouderde per-bedrijfstak-stijl en met de feitelijke vragen hardcoded in
de tool-description. PDR-007 §3 benoemt als vervolgstap: verhuizen naar de
poc-machine-law engine, met gelijkblijvende tool-interface.

Dit design voert die vervolgstap uit vóór de demo van 18 juni, met twee
aanscherpingen ten opzichte van het eerste ontwerp:

1. **Huidige EML-structuur (2023).** De echte EML is sinds 2023 één lijst
   (Staatscourant 2023-15844, gewijzigd okt 2023), georganiseerd in drie
   categorieën — *Gebouwen*, *Faciliteiten*, *Processen* — met per
   maatregel een code (bv. FD3 "Pas nachtafdekking toe bij semi-verticale
   koelmeubels") en toepasselijkheidscriteria. Géén bedrijfstak-lijsten
   meer. De demo-subset volgt die structuur met échte EML 2023-codes.
2. **Feitelijke vragen uit de engine, niet hardcoded.** Welke feiten de
   ondernemer moet leveren volgt uit de wet-YAML (parameters); de
   assistent leest ze af in plaats van dat ze in tool-description of
   prompt staan.

## Gekozen aanpak: per-maatregel outputs (optie A, herzien)

De engine kan geen lijst-van-objecten als output uitdrukken (`CONCAT` is
string-only, `FOREACH` alleen aggregatie via `combine`). Daarom krijgt
**elke EML-maatregel een eigen boolean output** in de wet-YAML. Dat past
bij de aard van de EML: elke maatregel ís een regel met eigen
toepasselijkheidscriteria en grondslag — en de engine levert per maatregel
explainability.

Verworpen alternatieven: booleans per voorwaardegroep (lijst blijft dan
regelkennis in de MCP-server) en engine uitbreiden met een
list/map-operatie (engine-core wijzigen één week voor de demo).

## Deel 1 — wet-YAML in poc-machine-law

Nieuw bestand:
`laws/omgevingswet/energiebesparing/maatregelen/RVO-2024-01-01.yaml`
(schema v0.1.7, conventies van de bestaande informatieplicht-YAML).

```yaml
law: omgevingswet/energiebesparing/maatregelen
service: "RVO"
name: Erkende Maatregelenlijst energiebesparing (EML 2023, demo-subset)
legal_basis:
  law: "Besluit activiteiten leefomgeving"
  bwb_id: "BWBR0041330"
  article: "5.15"          # energiebesparingsplicht; EML als erkende invulling

properties:
  parameters:
    # De feiten die de ondernemer levert. De description IS de vraag
    # die de assistent aan de ondernemer stelt (afgelezen, niet hardcoded).
    - name: "HEEFT_KOELINSTALLATIE"
      description: "Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?"
      type: "boolean"
      required: true
    - name: "HEEFT_AFZUIGINSTALLATIE"
      description: "Heeft het bedrijf een afzuiginstallatie (keuken/ventilatie)?"
      type: "boolean"
      required: true

  output:
    # Per EML 2023-maatregel één boolean. Echte code als naam-suffix,
    # categorie + officiële maatregelnaam in de description.
    - name: "eml_fd3_van_toepassing"
      description: "Faciliteiten — Pas nachtafdekking toe bij semi-verticale koelmeubels"
      type: "boolean"
      citizen_relevance: primary
    # ... overige subset-maatregelen (Gebouwen / Faciliteiten / Processen)

requirements: []   # EML 2023 geldt ongeacht bedrijfstak

actions:
  - output: "eml_<code>_van_toepassing"   # onvoorwaardelijke maatregelen
    value: true
  - output: "eml_fd3_van_toepassing"      # conditionele maatregelen
    value: "$HEEFT_KOELINSTALLATIE"
  # ...
```

Demo-subset: de ~7 maatregelen die de huidige mock dekt (LED-verlichting,
waterzijdig inregelen, deurdranger, koel-/vriescelisolatie, nachtafdekking
koelmeubelen, tijd-/aanwezigheidsschakeling afzuiging, frequentieregeling
afzuigventilator), maar dan met de **echte EML 2023-codes en officiële
namen** uit de RVO-publicatie
(`erkende-maatregelenlijst-eml-2023-v-1-3.pdf` / RVO-informatiebank) —
opzoeken is een implementatiestap. Per output een `legal_basis`
(Bal art. 5.15; explanation verwijst naar de EML-maatregelcode).

Ontwerpkeuzes:

- **Feiten als `parameters`, niet als `sources`.** De bedrijfskenmerken
  staan nergens geregistreerd; de ondernemer levert ze (PDR-007 §3).
  De parameter-`description` is letterlijk de vraagtekst.
- **Geen bedrijfstak meer.** EML 2023 kent geen bedrijfstak-lijsten;
  `requirements` is leeg, de wet geldt voor iedere onderneming met
  energiebesparingsplicht. `BEDRIJFSTAK`/`sbi_code` vervallen.
- Elke maatregel krijgt altijd een output (true/false), zodat de
  tool-semantiek (`van_toepassing` per maatregel) behouden blijft.

Validatie: schema-validatie van poc-machine-law (`script/`) + pre-commit
aldaar. PR naar `MinBZK/poc-machine-law` main.

## Deel 2 — omschakeling in deze repo

`services/mcp/regelrecht/server.py` — de tool `maatregelen` wordt een
engine-proxy met een **twee-staps-flow**:

1. **Nieuw inputschema (generiek).** `sbi_code`, `koelinstallatie` en
   `afzuiginstallatie` vervallen als named properties. Eén optionele
   property `feiten` (object, boolean-waarden). De description instrueert:
   "Roep eerst aan zónder feiten; de tool meldt welke feitelijke vragen
   aan de ondernemer gesteld moeten worden."
2. **Stap 1 — vragen aflezen.** Aanroep zonder (volledige) feiten →
   server roept `execute_law` aan → engine antwoordt met
   `missing_required: true` plus de volledige wet-spec (`rule_spec`);
   de server leest de vragen af uit
   `rule_spec.properties.parameters[].description` → server geeft terug:
   `{"benodigde_feiten": [{"naam": "HEEFT_KOELINSTALLATIE", "vraag": "Heeft het bedrijf ..."}, ...]}`.
   De assistent stelt die vragen letterlijk; niets is hardcoded.
3. **Stap 2 — maatregelen bepalen.** Aanroep mét feiten → `execute_law`
   met de feiten als parameters → server mapt de response naar de
   lijst-vorm: per output `eml_<code>_van_toepassing` een item
   `{code, naam, categorie, van_toepassing}` met naam/categorie uit de
   output-`description` in `rule_spec`. Alle regelkennis komt uit de
   engine.
4. **Lokale mock blijft als fallback**, omgebouwd naar dezelfde
   twee-staps-flow en EML 2023-vorm. Bij `SOURCE_UNAVAILABLE` of een
   onbruikbare response serveert de server lokaal; provenance vermeldt
   eerlijk de route (`"RegelRecht (poc-machine-law)"` vs. het bestaande
   lokale-mock-label). De demo kan niet stuk door de omschakeling.

**Impact buiten de server** (interface wijzigt — dit is de prijs van de
twee aanscherpingen):

- `services/host/prompts/`: de hardcoded feitelijke vragen
  ("koelinstallatie? afzuiginstallatie?") vervangen door de
  patroon-instructie: eerst `maatregelen` aanroepen, de gemelde vragen
  stellen, daarna opnieuw aanroepen met de antwoorden.
- `services/host/tests/test_demo_personas.py`: EML-invarianten aanpassen
  aan de twee-staps-flow en EML 2023-codes; Donald-invariant
  (geen netbeheerder-data) blijft ongewijzigd.
- CLI-transport kende `maatregelen` al niet (PDR-007) — geen impact.

## Deploy-sporen (risico demo 18 juni)

| Spoor | Wat | Wanneer |
|---|---|---|
| a | PR poc-machine-law mergen; digilab-deploy van `ui.lac.apps.digilab.network` vóór 18/6 | voorkeursroute |
| b | Engine lokaal draaien (Dockerfile aanwezig) en `REGELRECHT_RPC_URL` ernaar wijzen (werkt sinds de env-doorvoer-fix in `mcp_client.py`) | als (a) niet op tijd lukt |
| vangnet | Fallback naar lokale mock (deel 2, punt 4) | altijd actief |

## Tests

- Unit-test mapping engine-response → lijst-vorm (vaste
  voorbeeld-response, geen netwerk).
- Unit-test twee-staps-flow: zonder feiten → `benodigde_feiten` met de
  vraagteksten uit de YAML; met feiten → maatregelenlijst.
- Test dat fallback naar de lokale mock werkt bij onbereikbare engine,
  met het juiste provenance-label, in béíde stappen.
- Aangepaste EML-invarianten in `test_demo_personas.py` (EML 2023-codes;
  koeling+afzuiging → alle subset-maatregelen `van_toepassing: true`).
- Handmatig integratiescript naast de bestaande scripts in
  `services/host/scripts/`: end-to-end twee-staps-flow tegen de echte
  engine voor Noon.

## Documentatie

- PDR-007 §3 krijgt een addendum: vervolgstap uitgevoerd, mét de
  structuurwijziging naar EML 2023 (bedrijfstak-model vervallen) en het
  vragen-uit-de-engine-patroon; verwijzing naar dit design en de
  poc-machine-law PR. (PDR blijft staan, conform
  `docs/decisions/README.md`.)

## Buiten scope / bevindingen voor de echte bouw

- **Schaalbaarheid**: per-maatregel outputs schalen niet naar de volledige
  EML (~150 maatregelen). Voor de echte bouw is een list/map-uitbreiding
  van de engine (of een maatregelen-resource) nodig. Vastleggen in het
  PDR-addendum.
- **Toepasselijkheidscriteria versimpeld**: de echte EML 2023 kent per
  maatregel rijkere criteria (technisch, economisch) dan de twee
  demo-booleans. De demo-subset reduceert dat bewust tot
  koel-/afzuiginstallatie.
- Volledige EML (alle ~150 maatregelen, terugverdientijd-criteria) blijft
  buiten scope.

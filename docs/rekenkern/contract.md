# Clientcontract van de rekenkern

**Versie 1.0.0** · besluit in [PDR-018](../decisions/PDR-018-clientcontract-rekenkern.md) ·
schema's in [`services/rekenkern/schema/`](../../services/rekenkern/schema/) (ook in elke bundel onder `schema/`)

De rekenkern rekent in de browser van de ondernemer. De afnemer laadt de bundel
en roept de kern aan; feiten en uitkomsten gaan nooit naar een server. De
DA-backend heeft geen route die rekent. Dit document beschrijft wat de afnemer
de kern geeft en wat hij terugkrijgt.

## De bundel

Een release-asset `rekenkern-<versie>.zip` met één map:

| Bestand | Inhoud |
|---|---|
| `pkg/da_rekenkern.js`, `pkg/da_rekenkern_bg.wasm` | De kern (wasm-bindgen, `--target web`) |
| `wetten.json` | `{ "wetten": { "<pad in het corpus>": "<YAML>" } }`, de gepinde wetversies |
| `worker.js` | Web Worker die de kern laadt en verzoeken afhandelt |
| `rekenkern-node.mjs` | Dezelfde kern in Node, voor tests en scripts |
| `schema/*.schema.json` | De JSON Schema's van dit contract |
| `manifest.json` | Naam, versie, engine (repo + commit), corpus (repo + revisie + aantal wetversies), contractversie en een SHA-256 per bestand |

`worker.js` en `rekenkern-node.mjs` toetsen de WASM en `wetten.json` aan het
manifest voordat ze laden. Een afwijking geeft `REKENKERN_BUNDEL_ONGELDIG`.

## Twee ingangen

**`bereken(verzoek)`** rekent één uitkomst van één wet. Dit is de ingang voor
een aanvraag: de afnemer levert de feiten uit de bronnen die de ondernemer
bevestigde. Er zit geen vraagmodel of aanname tussen.

**`orienteer(keuzes)`** is de oriëntatie "iemand aannemen": vier antwoorden
gaan naar feiten (de zuinigste lezing), de kern rekent elke uitkomst die de
antwoorden kunnen openen, en geeft per aanroep het antwoord van `bereken` plus
wat een scherm toont. De vertaling van antwoorden naar feiten is een
oriëntatie, geen besluit (zie PDR-018).

Daarnaast: `kiesDoelgroep(huidig, waarde, aan)`, `doelgroepen()`,
`balans(uitkomsten, kosten)`, `allowlist()` en `versie()`.

## Verzoek

[`verzoek.schema.json`](../../services/rekenkern/schema/verzoek.schema.json)

```json
{
  "wet": "participatiewet",
  "output": "heeft_recht_op_lks",
  "peildatum": "2026-07-01",
  "parameters": { "loonwaarde_percentage": 60, "datum_aanvraag_lks": "2026-02-01" },
  "uitleggen": ["hoogte_lks_eurocent_per_maand"]
}
```

`parameters` zijn gegevens op naam, zoals het corpus ze declareert: boolean,
getal, tekst of datum (`YYYY-MM-DD`), of `null` voor "niet ingevuld".

### Allowlist

Alleen deze `wet#output`, met deze extra outputs in `uitleggen`. Elk ander
verzoek wordt geweigerd voordat de engine iets ziet.

| wet | output | uitleggen |
|---|---|---|
| participatiewet | heeft_recht_op_lks | hoogte_lks_eurocent_per_maand |
| wet_arbeidsongeschiktheidsvoorziening_jonggehandicapten | heeft_recht_op_loondispensatie | aanspraak_beloning_per_uur_eurocent |
| wet_tegemoetkomingen_loondomein | heeft_recht_op_lkv | hoogte_lkv_per_jaar_eurocent, categorie_lkv |
| ziektewet | heeft_recht_op_no_risk_polis | duur_no_risk_polis_jaren |
| participatiewet | mag_proefplaatsing_aangaan | |
| participatiewet | heeft_aanspraak_op_begeleiding_op_de_werkplek | |
| wet_werk_en_inkomen_naar_arbeidsvermogen | mag_jobcoaching_toekennen | mag_werkplekaanpassing_toekennen |

Peildatum: alleen `2026-07-01`.

## Antwoord

[`antwoord.schema.json`](../../services/rekenkern/schema/antwoord.schema.json)

```json
{
  "wet": "participatiewet",
  "output": "heeft_recht_op_lks",
  "peildatum": "2026-07-01",
  "outputs": { "heeft_recht_op_lks": true, "hoogte_lks_eurocent_per_maand": 89740.8 },
  "graaf": { "beslissingen": ["…"], "knopen": ["…"], "randen": ["…"], "markeringen": ["…"] },
  "uitleg": { "kort": ["…"], "motivering": ["…"], "volledig": ["…"], "voorbehouden": ["…"] }
}
```

- **`outputs`**: de gevraagde output en de `uitleggen`, met de exacte waarde
  van de engine. Een uitkomst die niet te bepalen is, is
  `{"__unknown": true, "missing": [{"name": "…"}]}`.
- **`graaf`**: de minimale beslisgraaf (Bos, Schuth en Chen, JURIX 2026).
  Knopen `decision`, `rule`, `fact`, `calculation` en `law`. Randen:
  - `has_fact`: een regel gebruikt een gegeven;
  - `satisfied`, `failed` of `unknown`: een voorwaarde was wel, niet of nog
    niet vervuld (van de voorwaarde naar de knoop die hem gebruikt);
  - `used_in`: een berekening voedt een knoop;
  - `based_on`: een knoop rust op een artikel.

  Een vergelijking draagt haar operator en operanden, met de letterlijke
  drempels uit het model. `markeringen` noemt wat het corpus bij deze uitkomst
  uitdrukkelijk niet meerekent, met de vindplaats.
- **`uitleg`**: tekst uit de graaf, zonder taalmodel. `kort` noemt de uitkomst
  en het bedrag. `motivering` geeft de voorwaarden die de uitkomst direct
  dragen, met gegevens en vindplaats. `volledig` is de hele graaf als boom.
  `voorbehouden` komt uit de markeringen.

## Oriëntatie

[`keuzes.schema.json`](../../services/rekenkern/schema/keuzes.schema.json),
[`orientatie.schema.json`](../../services/rekenkern/schema/orientatie.schema.json)

```json
{ "doelgroepen": ["bijstand"], "uren": 32, "loonwaarde": 60, "uurloon": 1499 }
```

Het antwoord heeft `keuzes`, `antwoorden` (een antwoord per aanroep, in de
volgorde van de allowlist, bedragen eerst) en `uitkomsten`
(`regels`, `overige` en `aannames`, zoals het portaal ze toonde). Bedragen
staan in eurocent per jaar.

## Fouten

[`fout.schema.json`](../../services/rekenkern/schema/fout.schema.json)

Elke functie geeft JSON-tekst terug: `{"ok": true, …}` of
`{"ok": false, "fout": {"code", "bericht"}}`. De code is stabiel. Het bericht
is voor de ontwikkelaar en hoort niet op het scherm van de ondernemer.

| Code | Wanneer | Wat de afnemer doet |
|---|---|---|
| `REKENKERN_VERZOEK_ONGELDIG` | Geen geldige JSON, onbekend veld, onbekende doelgroep, uren/loonwaarde/uurloon buiten bereik | Verzoek herstellen; een programmeerfout |
| `REKENKERN_NIET_TOEGESTAAN` | `wet#output` of `uitleggen` buiten de allowlist | Niet rekenen; de bundel kent deze uitkomst niet |
| `REKENKERN_PEILDATUM_ONBEKEND` | Andere peildatum dan in het contract | Peildatum `2026-07-01` gebruiken, of een nieuwere bundel |
| `REKENKERN_PARAMETER_ONGELDIG` | Een parameterwaarde die de engine niet kan lezen | Waarde herstellen |
| `REKENKERN_WETTEN_ONGELDIG` | `wetten.json` leeg of onleesbaar | Bundel opnieuw ophalen |
| `REKENKERN_ENGINE` | De engine faalt, bijvoorbeeld door een ontbrekend verplicht gegeven | Melden; het bericht noemt het gegeven |
| `REKENKERN_BUNDEL_ONGELDIG` | Een bestand past niet bij `manifest.json` (alleen worker en Node-lader) | Bundel opnieuw ophalen; niet rekenen |

## Worker

```js
const worker = new Worker(new URL("rekenkern/worker.js", location), { type: "module" });
worker.postMessage({ id: 1, soort: "orienteer", keuzes: { doelgroepen: ["bijstand"], uren: 32, loonwaarde: 60, uurloon: 1499 } });
worker.onmessage = ({ data }) => { /* { id, ok, orientatie, ms } of { id, ok: false, fout } */ };
```

Soorten: `bereken` (`verzoek`), `orienteer` (`keuzes`), `kiesDoelgroep`
(`huidig`, `waarde`, `aan`), `balans` (`uitkomsten`, `kosten`), `doelgroepen`,
`allowlist` en `manifest`.

## Privacy

De kern doet geen netwerkverzoeken en logt niets. Een afnemer stuurt een
graaf alleen naar `POST /uitleg` als de ondernemer daar zelf om vraagt ("Leg
dit uit in gewone taal"). Die graaf bevat dan de feiten van de berekening. De
host logt alleen de naam van de regeling, het aantal regels en de uitslag van
de toets (PDR-016).

## Versies

- **Contract** (`manifest.contract`): een patch is een verduidelijking. Een
  minor voegt iets toe, zoals een veld of een uitkomst op de allowlist. Een
  major verandert of verwijdert iets.
- **Bundel** (`manifest.versie`): de versie van de crate. Een nieuwe pin van
  het corpus of de engine is een nieuwe bundelversie, ook als het contract
  gelijk blijft.

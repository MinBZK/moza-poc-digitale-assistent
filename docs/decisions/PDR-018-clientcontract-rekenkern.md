# PDR-018: Rekenen gebeurt bij de afnemer, volgens een clientcontract, niet via een endpoint

| Veld | Waarde |
|---|---|
| Status | Voorgesteld |
| Datum | 2026-10-26 |
| Beslisser(s) | Projectteam Digitale assistent 2.0 |
| Gerelateerd | [PDR-016](PDR-016-uitleg-in-gewone-taal-uit-de-beslisgraaf.md) (uitleg), [PDR-017](PDR-017-bron-en-pinning-van-de-rekenkern.md) (bron en pinning), [PDR-011](PDR-011-foutmeldingen-catalogus.md) (foutcatalogus) |

## Context

Wat een ondernemer over een werknemer invult (doelgroep, uren, loonwaarde,
uurloon), en wat daaruit volgt, zijn gegevens over een persoon met een
arbeidsbeperking. De oriëntatie hoeft die gegevens nergens heen te sturen: de
regels zijn bekend en de engine draait in de browser. Een rekenendpoint op de
DA-backend zou de gegevens wel naar een server brengen, met logging, audit en
telemetrie als risico.

## Beslissing

1. **Geen HTTP-route die rekent.** De DA levert de kern (PDR-017) en een
   contract. De afnemer rekent in de browser van de ondernemer. Feiten,
   uitkomsten en grafen staan niet in logs, audit of telemetrie van de
   DA-backend.
2. **Het contract** staat in [`../rekenkern/contract.md`](../rekenkern/contract.md),
   met JSON Schema's in `services/rekenkern/schema/` (ook in elke bundel):
   verzoek, keuzes, antwoord, oriëntatie en fout. De schema's worden getoetst
   tegen echte uitvoer van de kern (`services/rekenkern/tests/schema.rs`).
3. **Een allowlist van zeven `wet#output`**, met per uitkomst de toegestane
   extra outputs, en één peildatum. Wat er niet op staat, weigert de kern
   voordat de engine iets ziet. Zo rekent een bundel alleen wat getest en
   besproken is, en kan een afnemer de kern niet gebruiken als algemene
   engine voor gegevens die hij niet nodig heeft.
4. **Twee ingangen.** `bereken` is de zuivere engine-aanroep, voor de
   aanvraag: feiten uit bevestigde bronnen, geen aannames. `orienteer` voegt
   het vraagmodel van de oriëntatie toe. Zo blijft de aanvraag los van de
   oriëntatielaag, zoals de notitie van 26 oktober vraagt.
5. **Elk antwoord draagt zijn uitleg**: de minimale beslisgraaf
   (decision/rule/fact/calculation/law; has_fact, satisfied/failed, used_in,
   plus `unknown` en `based_on`), de markeringen van het corpus, en tekst uit
   de graaf zonder taalmodel (`kort`, `motivering`, `volledig`,
   `voorbehouden`).
6. **Foutcodes `REKENKERN_*`** zijn stabiel en horen bij het contract. Ze
   ontstaan alleen in de client en staan daarom niet in `errors.py` van de
   host; de afnemer vertaalt ze naar een melding voor de ondernemer.
7. **`/uitleg` aanvaardt de graaf van de kern** (`uitleg.normaliseer_graaf`).
   Dat is de enige plek waar een graaf naar de host kan gaan, en alleen als
   de ondernemer zelf om een uitleg in gewone taal vraagt.

## Alternatieven overwogen

- **Een rekenendpoint op de DA-backend.** Afgewezen om de gegevens. Het zou
  ook de host afhankelijk maken van de engine en van het corpus, en de
  oriëntatie trager maken.
- **Geen allowlist: de hele engine met alle wetten.** Afgewezen. Het contract
  zou dan alles zijn wat het corpus kan, ongetest en zonder grens.
- **Het oude formaat van de portaalbundel nabootsen** (`model.stappen`,
  `afleidingen`, `bereken(json, presentaties, sjablonen, wetten)`). Afgewezen:
  dat houdt de oude uitleglaag in leven. Het portaal stapt over op dit
  contract, in een eigen opdracht.
- **De graaf in de vorm van de oude `/uitleg`** (geneste `doorslaggevend`).
  Afgewezen: die vorm is een presentatie, geen getypeerde graaf. De host zet
  de nieuwe vorm om; de oude vorm blijft werken tot het portaal over is.

## Consequenties

- Een afnemer haalt een release, toetst het manifest en laadt `worker.js`.
  Voor tests en scripts is er `rekenkern-node.mjs`.
- De tests van de verhuisde stappen staan in `services/rekenkern/tests/`:
  vraag 1, de uitkomsten per geval, het voorbehoud, de aanroepen en de balans
  (overgenomen uit de portaaltests), plus de referentieset, de bekende
  bedragen, de allowlist en het manifest. De portaaltests van route,
  schermen en opslag blijven in het portaal.
- Een uitbreiding van de allowlist is een minor van het contract en vraagt
  een aanpassing van `ALLOWLIST`, het schema, dit document en de tests.
- De markeringen in de graaf beantwoorden de open vraag uit de notitie: de
  engine geeft ze al in de trace mee. Een afnemer kan het voorbehoud dus uit
  het corpus tonen. De oriëntatie zet daarnaast nog `voorbehoud` op de regel
  (`zes_maanden`, `samenloop`), zoals het portaal deed. Dat vervalt zodra het
  portaal de markeringen toont.

# PDR-017: De Digitale assistent rekent niet; de afnemer rekent met de regelrecht-engine

| Veld | Waarde |
|---|---|
| Status | Voorgesteld |
| Datum | 2026-11-23 |
| Beslisser(s) | Projectteam Digitale assistent 2.0 |
| Gerelateerd | [PDR-016](PDR-016-uitleg-in-gewone-taal-uit-de-beslisgraaf.md) (uitleg in gewone taal), [PDR-011](PDR-011-foutmeldingen-catalogus.md) (foutcatalogus); regelrecht-corpus-FCV PDR 0003 (vragenmodel naast het corpus) en PDR 0005 (berekening blijft in de browser; aangevuld 27 oktober 2026) |

## Context

De oriëntatie "iemand aannemen" rekent uit wat regelingen een werkgever
opleveren. Wat de werkgever daarvoor invult (doelgroep, uren, loonwaarde,
uurloon), gaat over een werknemer, vaak iemand met een arbeidsbeperking. Die
gegevens horen niet op een server terecht te komen.

PR #78 stelde voor dat de Digitale assistent een eigen rekenkern levert: een
bundel met de regelrecht-engine, een allowlist van uitkomsten, een vraagmodel
en een contract. Op 27 oktober 2026 is besloten dat het rekenen bij RegelRecht
hoort. Het portaal (moza-portaal, `personeel/iemand-aannemen`) rekent sindsdien
in de browser met de regelrecht-engine (WASM), op een gepinde engine en een
gepind corpus. Het vragenmodel van de oriëntatie staat als gegevens naast
het corpus van het Financieel CV. PR #78 is daarom gesloten; de code staat
onder de tag `archief/rekenkern-iemand-aannemen`.

## Beslissing

1. **De Digitale assistent rekent niet.** Er komt geen HTTP-route die rekent
   en geen rekenkern in deze repository.
2. **De afnemer rekent, met de regelrecht-engine.** Een portaal of ander
   afnemer rekent in de browser van de ondernemer, met de kern en het corpus
   van RegelRecht.
3. **Geen feiten in de host.** Feiten, uitkomsten en grafen komen niet in
   logs, audit of telemetrie van de host. `/uitleg` logt alleen de naam van de
   regeling, aantallen en de uitslag van de toets.
4. **`/uitleg` alleen op verzoek.** Een graaf gaat alleen naar de host als de
   ondernemer zelf om een uitleg in gewone taal vraagt (PDR-016).

## Alternatieven overwogen

- **Een rekenkern in de Digitale assistent (PR #78).** Afgewezen. Er zouden
  twee plekken zijn die de regels uitvoeren en die apart bijgehouden moeten
  worden, en de gepinde engine liep al achter op het corpus.
- **Een rekenendpoint op de host.** Afgewezen om de gegevens: die zouden dan
  wel naar een server gaan.

## Consequenties

- De concepten PDR-017 (bron en pinning van de rekenkern), PDR-018
  (clientcontract) en PDR-019 (reken dit uit in het gesprek) uit PR #78 zijn
  niet aangenomen. Dit document vervangt het deel van PDR-018 dat blijft
  gelden. Het idee van PDR-019 staat als issue, voor als het gesprek
  terugkomt.
- De beslisgraaf en de uitleg zonder taalmodel uit PR #78 blijven bewaard
  onder de tag `archief/rekenkern-iemand-aannemen`.
- `/uitleg` blijft de graafvorm aannemen die het portaal nu stuurt
  (`afleiding.uitkomst`). Een tweede vorm komt er pas als een afnemer die
  nodig heeft.

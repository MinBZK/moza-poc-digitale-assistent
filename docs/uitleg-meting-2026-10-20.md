# Meting uitleg in gewone taal, 20 oktober 2026

Eerste meting van `POST /uitleg` (PDR-016) op de casus Koen uit "Iemand
aannemen met afstand tot de arbeidsmarkt": 32 uur per week, loonwaarde 60
procent, doelgroepregister. De negen beslisgrafen komen uit de kern van
regelrecht-uitleg (`uitleg bereken`, engine `0a1a76c8`, corpus `42054d7d`),
het model is Claude (`CLAUDE_MODEL` van de host), via
`services/cli/uitleg-cli batch`. Eén aanroep per uitkomst, ongeveer duizend
tokens per aanroep.

## Toets

| Uitkomst | Toets | Woorden | Zin gem. | Te lang |
|---|---|---|---|---|
| heeft_aanspraak_op_begeleiding_op_de_werkplek | geslaagd | 30 | 9,0 | 0 |
| heeft_recht_op_lks | geslaagd | 78 | 7,5 | 0 |
| hoogte_lks_eurocent_per_maand | geslaagd | 66 | 7,9 | 0 |
| mag_proefplaatsing_aangaan | geslaagd | 65 | 10,3 | 0 |
| heeft_recht_op_loondispensatie (nee) | geslaagd | 36 | 9,0 | 0 |
| is_arbeidsbeperkte | geslaagd | 60 | 10,8 | 0 |
| heeft_recht_op_lkv | geslaagd | 48 | 7,3 | 0 |
| hoogte_lkv_per_jaar_eurocent | geslaagd | 71 | 8,9 | 0 |
| heeft_recht_op_no_risk_polis | geslaagd | 58 | 9,2 | 1 |

Negen van negen door de toets: elk bedrag en percentage staat in de graaf,
elk wetsartikel is genoemd, geen tekst boven 120 woorden. Zinnen gemiddeld 7
tot 11 woorden (grens uit `tone.md`: 15).

## Wat de toets niet zag

De toets controleert getallen en de grond. Een menselijke lezing van de negen
teksten vond drie soorten afwijkingen die daar doorheen komen:

1. **Omgedraaide rekenstap.** De graaf van het loonkostenvoordeel kiest met
   `MAX` het hoogste van drie tegemoetkomingen (€ 1.680,64, € 0,00, € 0,00).
   Het model schreef: "Het laagste bedrag is € 1.680,64." De bedragen klopten,
   de redenering niet. Sinds deze meting kent de toets `omgedraaide_stappen`
   (MAX met "laagste", MIN met "hoogste") en zegt het prompt het erbij.
2. **Jargon uit de graaf.** "Uw werknemer voldoet aan grond 38b lid 1a" en
   "voldoet aan de voorwaarden van lid 2e": het model neemt namen van knopen
   over waar de graaf geen gewone woorden geeft. De motivering per artikel uit
   de kern heeft die woorden wel; die meegeven is de volgende stap.
3. **Perspectief.** Loonkostensubsidie is voor de werkgever; het model
   schreef bij het bedrag "Uw werknemer heeft recht op loonkostensubsidie" en
   bij het recht "U heeft recht". Wie ontvangt, staat niet in de graaf. In de
   eerste ronde (vóór de rolregel in het prompt) stond er zelfs "U werkt 32
   uur per week".

Niet gevonden: verzonnen voorwaarden, verzonnen bedragen, een verkeerde
uitkomst (ja/nee), een ontbrekende niet-vervulde voorwaarde (loondispensatie
noemt correct de ene voorwaarde die niet voldaan is).

## Wat dit zegt voor het onderzoek

Dit is precies wat Bos, Schuth en Chen (JURIX 2026) beschrijven: de
graaf-conditie houdt de getallen en de grond trouw, en wat overblijft zijn
redenering en perspectief, die een deterministische toets niet ziet.
Begrijpelijk is niet hetzelfde als juridisch juist. Voor het gebruikersonderzoek
betekent dat: laat deelnemers de taalmodeltekst lezen naast de afleiding, en
leg vast waar ze de tekst geloven terwijl de afleiding iets anders zegt.

## Reproduceren

```bash
# 1. Grafen uit de kern (regelrecht-uitleg, branch feat/engine-live)
cd packages && cargo run -q --features bron --bin uitleg -- bereken invoer.json > uit.json
# 2. Host met sleutel
set -a; source services/host/.env; set +a
uv run uvicorn api:app --app-dir services/host --port 8000
# 3. Meting
UITLEG_KVK=85234567 services/cli/uitleg-cli batch <map-met-uit.json> --bewaar antwoorden/
```

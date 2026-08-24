# PDR-013: Time-outgrenzen op basis van meting, met levensteken en herkansingen

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-08-24 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | [PDR-002](PDR-002-vlam-timeout-fallback.md) (vervangt de grenzen daaruit), [PDR-011](PDR-011-foutmeldingen-catalogus.md) |

## Context

Tijdens het gebruikersonderzoek van 20 augustus (11:00–12:00) viel de assistent
tweemaal weg: het antwoord bleef lang uit, daarna kwam een foutmelding, en de
volgende beurt werkte weer. Geen uitrol in dat uur, geen incident bij de
LLM-aanbieder, bronnen en regelloop antwoorden binnen seconden. Wat overbleef
was de LLM-aanroep zelf: één `messages.create` zonder streaming, hard
afgebroken door `asyncio.wait_for(..., 60)`.

Die 60 seconden (en 30 voor VLAM) komen uit PDR-002 van maart 2026. Daar was
het een aanname bij een andere situatie: een kleine prompt, antwoorden van een
paar honderd tokens, en een UbiOps-endpoint dat na 20–110 seconden met een 500
crashte. De grens was een bescherming tegen een vastgelopen platform, niet een
maat voor een normaal antwoord. PDR-002 werd in april ongeldig verklaard, maar
de getallen bleven staan en zijn nooit herijkt terwijl de prompt groeide.

Meting op 24 augustus, dezelfde persona en flow als het onderzoek
(`scripts/onderzoeksflow.py`, mode `claude`, mét prompt-caching):

| beurt | Claude-call | tokens in / uit |
|---|---|---|
| toets afgerond | 11,3 s | 19.948 / 506 |
| maatregelen-vragen | 12,7 s | 23.318 / 597 |
| formulier ingevuld | 19,8 s | 27.862 / 928 |
| rapport | 20,6 s | 28.987 / 1.382 |
| indienen | 16,3 s | 30.943 / 909 |

De zwaarste beurt zit in normale omstandigheden op een derde van de grens.
Twee dingen maken de rest op: een staart in de latency van de API, en de
retry die de SDK zelf doet. `AsyncAnthropic()` en `AsyncOpenAI()` retryen
standaard twee keer met backoff bij een 429, 5xx of verbindingsfout — binnen
dezelfde 60 seconden, onzichtbaar voor de host. Een model dat "te druk" is
werd zo als "time-out" gemeld, met het advies de vraag korter te maken.

## Beslissing

1. **Grenzen op basis van meting, op één plek.** `CLAUDE_TIMEOUT` = 180 s,
   `VLAM_TIMEOUT` = 120 s (`config.py`). De regel: grens ≈ 3× de gemeten
   duur van de zwaarste beurt, plus ruimte voor één herkansing. Herijken
   zodra de prompt of het antwoord groeit; de meting hierboven is het
   ijkpunt. `LLM_MAX_TOKENS` = 2.048 (langste gemeten antwoord 1.382):
   ruim, maar een model dat doorpraat loopt tegen deze grens vóór de
   time-out.
2. **Levensteken tijdens de aanroep.** `_llm_aanroep` (`vlam_host.py`)
   stuurt elke `LLM_HARTSLAG_INTERVAL` (10 s) een `status`-event zolang het
   model werkt. De frontend breekt af na 90 s stilte; met een levensteken
   telt die stilte per event, niet per aanroep.
3. **Geen SDK-retries; herkansingen in de host.** Beide clients staan op
   `max_retries=0`. Meldt het model "te druk", "tijdelijk weg" of
   "onbereikbaar" (`LLM_TE_DRUK`, `LLM_OVERBELAST`, `LLM_ONBEREIKBAAR`),
   dan probeert de host het `LLM_HERKANSINGEN` (2) keer opnieuw, met een
   `status`-event per herkansing ("Het AI-model is druk. Ik probeer het nog
   een keer...") en een wachttijd die verdubbelt (2 s, 4 s), binnen dezelfde
   grens. Twee, omdat een verbindingsfout in een korte reeks komt: bij het
   nameten viel één herkansing na 2 s daar nog middenin. Faalt ook de
   laatste, dan krijgt de gebruiker de melding die bij de oorzaak hoort
   (PDR-011), niet "time-out".

De grenzen uit PDR-002 zijn hiermee vervangen; de rest van PDR-002 was al
ongeldig.

## Alternatieven overwogen

### A. Alleen de grens verhogen

- (+) Eén regel in de config.
- (−) De SDK-retry blijft de tijd opeten, en "te druk" blijft "time-out" heten.
- (−) Zonder levensteken staat de respondent 180 s naar "Antwoord
  opstellen..." te kijken zonder te weten of er nog iets gebeurt.

### B. Streaming LLM-call (`messages.stream`)

- (+) De echte oplossing: tekst komt binnen terwijl het model werkt, en de
  time-out wordt "N seconden zonder token" in plaats van "het hele antwoord
  in N seconden".
- (−) De zes agentic loops parsen nu een complete respons (tool-calls,
  `stop_reason`, usage). Streaming vraagt een herschrijving van die loops
  en van de slot-substitutie (`slots.py`) die op de volledige tekst werkt.
  Niet haalbaar vóór het onderzoek van 25 en 27 augustus. Staat op
  `NEXT_STEPS.md` als vervolg; deze PDR is de tussenstand die het onderzoek
  moet dragen.

### C. Grens meeschalen met de promptlengte

- (+) Past zichzelf aan.
- (−) De duur hangt vooral aan het aantal uitvoertokens en aan de API, niet
  aan de invoer. Een formule suggereert precisie die er niet is; een gemeten
  vaste grens met een herijkregel is eerlijker.

## Consequenties

1. **Gebruiker.** Een beurt die 60–180 s duurt komt nu aan in plaats van
   weg te vallen; tussendoor blijft de status zichtbaar. Bij een druk model
   ziet hij dat de assistent het nog een keer probeert.
2. **Foutmeldingen.** `LLM_TIMEOUT` noemt de nieuwe grens ("langer dan 180
   seconden"). `LLM_TE_DRUK` en `LLM_OVERBELAST` komen weer voor in de logs
   en in de UI, waar ze eerder als time-out verscholen zaten.
3. **Frontend (`MinBZK/moza-poc`).** Geen wijziging nodig: de stilte-grens
   van 90 s blijft, het levensteken van 10 s houdt hem weg van die grens.
4. **Herijken.** `tests/test_llm_aanroep_grenzen.py` bewaakt de ondergrens
   van de instellingen. Groeit de zwaarste beurt boven een derde van de
   grens, dan hoort de grens mee te groeien — en de meting in deze PDR
   opnieuw gedaan te worden.
5. **Vervolg.** Streaming (alternatief B) is de structurele oplossing; deze
   PDR neemt de scherpe kanten weg tot die er is.

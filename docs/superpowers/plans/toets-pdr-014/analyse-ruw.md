# Ruwe analyse per run

## f22f063 (5 runs)

| run | beurten | totaal s | s per beurt | 1e bron | 1e wet | 1e uitkomst | toezegging vóór bron | 'ingediend' zonder indienen | datums | zoek_regeling | execute_law | bron_fouten | controles fout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 6 | 63.0 | [6.0, 34.0, 9.8, 4.9, 4.5, 3.8] | 2 | 2 | 2 | geen | - | - | 0 | 2 | - | 8/32 |
| 2 | 6 | 49.4 | [4.6, 18.2, 9.7, 8.9, 4.3, 3.7] | 2 | 2 | 2 | geen | - | - | 0 | 2 | - | 7/31 |
| 3 | 6 | 59.4 | [10.6, 27.2, 9.2, 4.3, 4.2, 3.5] | 2 | 2 | 2 | geen | - | - | 0 | 2 | - | 7/31 |
| 4 | 6 | 103.7 | [5.7, 40.4, 10.1, 3.8, 4.5, 4.0] | 2 | 2 | 2 | geen | - | - | 0 | 2 | - | 7/30 |
| 5 | 6 | 54.0 | [3.5, 28.0, 9.3, 4.8, 4.5, 3.9] | 2 | 2 | 2 | geen | - | - | 0 | 2 | - | 7/32 |

Duur per beurt over alle runs: mediaan 4.8 s, max 40.4 s, som per run mediaan 59 s

### Beurt 1 per run (wat de ondernemer leest vóór enige bron)

**run 1** (6.0 s, tools: geen) — toezeggingen: geen

> Om dat te beoordelen, wil ik twee dingen raadplegen en gebruiken:
>
> - Uw bedrijfsgegevens uit het KvK Handelsregister.
> - Uw energieverbruik uit uw Business Wallet - een attestatie, afgegeven door uw netbeheerder.
>
> Mag ik deze gegevens voor u ophalen en gebruiken?


**run 2** (4.6 s, tools: geen) — toezeggingen: geen

> Om dit te beoordelen, wil ik twee dingen raadplegen en gebruiken:
>
> - Uw bedrijfsgegevens uit het KvK Handelsregister
> - Uw energieverbruik uit uw Business Wallet - een attestatie, afgegeven door uw netbeheerder
>
> Mag ik deze gegevens voor u ophalen en gebruiken?


**run 3** (10.6 s, tools: geen) — toezeggingen: geen

> Om dit te beoordelen, wil ik twee dingen raadplegen en gebruiken:
>
> - Uw bedrijfsgegevens uit het KvK Handelsregister.
> - Uw energieverbruik uit uw Business Wallet - een attestatie, afgegeven door uw netbeheerder.
>
> Mag ik deze gegevens voor u ophalen en gebruiken?


**run 4** (5.7 s, tools: geen) — toezeggingen: geen

> Om dat te beoordelen, wil ik twee dingen raadplegen en gebruiken:
>
> - Uw bedrijfsgegevens uit het KvK Handelsregister.
> - Uw energieverbruik uit uw Business Wallet - een attestatie, afgegeven door uw netbeheerder.
>
> Mag ik deze gegevens voor u ophalen en gebruiken?


**run 5** (3.5 s, tools: geen) — toezeggingen: geen

> Om dat te beoordelen, wil ik twee dingen raadplegen en gebruiken:
>
> - Uw bedrijfsgegevens uit het KvK Handelsregister.
> - Uw energieverbruik uit uw Business Wallet - een attestatie, afgegeven door uw netbeheerder.
>
> Mag ik deze gegevens voor u ophalen en gebruiken?


### Tools per beurt

- run 1: b1[-] → b2[kvk__mijn_bedrijf, netbeheerder__verbruik, regelrecht__execute_law] → b3[regelrecht__execute_law] → b4[-] → b5[-] → b6[-]
- run 2: b1[-] → b2[kvk__mijn_bedrijf, netbeheerder__verbruik, regelrecht__execute_law] → b3[regelrecht__execute_law] → b4[-] → b5[-] → b6[-]
- run 3: b1[-] → b2[kvk__mijn_bedrijf, netbeheerder__verbruik, regelrecht__execute_law] → b3[regelrecht__execute_law] → b4[-] → b5[-] → b6[-]
- run 4: b1[-] → b2[kvk__mijn_bedrijf, netbeheerder__verbruik, regelrecht__execute_law] → b3[regelrecht__execute_law] → b4[-] → b5[-] → b6[-]
- run 5: b1[-] → b2[kvk__mijn_bedrijf, netbeheerder__verbruik, regelrecht__execute_law] → b3[regelrecht__execute_law] → b4[-] → b5[-] → b6[-]

### Gefaalde controles van het meetscript

- run 1: het antwoord noemt het gasverbruik van het scherm (198.000); twee vragen als velden (1); antwoord blijft onder 15 woorden per zin (score 48); het formulier heet 'Vragen van de assistent'; antwoord blijft onder 15 woorden per zin (score 56); rvo__indienen is aangeroepen; er komt een case-event voor 'Lopende zaken'; de rapportage gaat 'in behandeling', niet 'goedgekeurd'
- run 2: het antwoord noemt het gasverbruik van het scherm (198.000); twee vragen als velden (1); antwoord blijft onder 15 woorden per zin (score 44); het formulier heet 'Vragen van de assistent'; rvo__indienen is aangeroepen; er komt een case-event voor 'Lopende zaken'; de rapportage gaat 'in behandeling', niet 'goedgekeurd'
- run 3: het antwoord noemt het gasverbruik van het scherm (198.000); twee vragen als velden (1); antwoord blijft onder 15 woorden per zin (score 44); het formulier heet 'Vragen van de assistent'; rvo__indienen is aangeroepen; er komt een case-event voor 'Lopende zaken'; de rapportage gaat 'in behandeling', niet 'goedgekeurd'
- run 4: het antwoord noemt het gasverbruik van het scherm (198.000); twee vragen als velden (1); de frontend kan van de maatregelen een formulier maken; antwoord blijft onder 15 woorden per zin (score 64); rvo__indienen is aangeroepen; er komt een case-event voor 'Lopende zaken'; de rapportage gaat 'in behandeling', niet 'goedgekeurd'
- run 5: het antwoord noemt het gasverbruik van het scherm (198.000); twee vragen als velden (1); het formulier heet 'Vragen van de assistent'; antwoord blijft onder 15 woorden per zin (score 53); rvo__indienen is aangeroepen; er komt een case-event voor 'Lopende zaken'; de rapportage gaat 'in behandeling', niet 'goedgekeurd'

## main (5 runs)

| run | beurten | totaal s | s per beurt | 1e bron | 1e wet | 1e uitkomst | toezegging vóór bron | 'ingediend' zonder indienen | datums | zoek_regeling | execute_law | bron_fouten | controles fout |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 7 | 145.9 | [10.8, 12.3, 26.7, 12.8, 23.9, 31.0, 28.4] | 1 | 1 | 3 | geen | - | 1 december 2026 | 0 | 16 | 1:TOESTEMMING_VEREIST(kvk), 2:TOESTEMMING_VEREIST(netbeheerder) | 7/44 |
| 2 | 7 | 162.6 | [6.7, 6.5, 43.2, 14.5, 8.4, 31.6, 16.0] | 1 | 1 | 3 | geen | - | 1 december 2026 | 0 | 15 | 1:TOESTEMMING_VEREIST(kvk) | 8/44 |
| 3 | 7 | 105.7 | [16.0, 7.7, 22.2, 9.3, 8.6, 24.5, 17.6] | 1 | 1 | 3 | geen | - | 1 december 2026 | 0 | 14 | 1:TOESTEMMING_VEREIST(kvk) | 7/44 |
| 4 | 7 | 94.8 | [4.6, 10.9, 20.3, 10.7, 6.3, 25.2, 16.8] | 1 | 1 | 3 | geen | - | 1 december 2026 | 0 | 14 | 1:TOESTEMMING_VEREIST(kvk), 2:TOESTEMMING_VEREIST(netbeheerder) | 8/44 |
| 5 | 7 | 125.0 | [35.7, 14.7, 20.1, 5.6, 6.2, 24.9, 17.8] | 1 | 1 | 3 | geen | - | 1 december 2026 | 0 | 14 | 1:TOESTEMMING_VEREIST(kvk) | 4/44 |

Duur per beurt over alle runs: mediaan 16.0 s, max 43.2 s, som per run mediaan 125 s

### Beurt 1 per run (wat de ondernemer leest vóór enige bron)

**run 1** (10.8 s, tools: ['regelrecht__execute_law', 'regelrecht__execute_law']) — toezeggingen: geen

> Er zijn twee zaken om u te melden.
>
> Voor het KvK Handelsregister is eerst uw akkoord nodig. Geef toestemming via de "Delen"-knop en stel daarna uw vraag opnieuw.
>
> Uit RegelRecht blijkt ondertussen dat ik ook nog twee gegevens nodig heb om de toets af te ronden:
>
> 1. Uw jaarlijks energieverbruik (elektriciteit in kWh en gas in m³)
> 2. Of uw pand uitsluitend een woonfunctie heeft
>
> Zodra ik uw KvK-gegevens heb opgehaald, kan ik de woonfunctie daar al uitlezen. Dan hoeft u dat zelf niet op te zoeken.
>
> Geeft u eerst toestemming via de "Delen"-knop?
>
> Bron: RegelRecht (art. 5.15 Besluit activiteiten leefomgeving)


**run 2** (6.7 s, tools: ['regelrecht__execute_law']) — toezeggingen: geen

> Voor het opzoeken van uw bedrijfsgegevens in het Handelsregister heb ik uw akkoord nodig. Geef toestemming via de "Delen"-knop en stuur uw vraag daarna opnieuw.
>
> Zodra ik uw gegevens heb, vraag ik ook of ik uw energieverbruik uit uw Business Wallet mag ophalen. Dan kan ik de toets meteen uitvoeren.


**run 3** (16.0 s, tools: ['regelrecht__execute_law']) — toezeggingen: geen

> Om uw bedrijfsgegevens op te halen, is eerst uw akkoord nodig. Geef toestemming via de "Delen"-knop en verstuur uw vraag daarna opnieuw.
>
> Zodra ik uw gegevens heb, check ik ook of uw energieverbruik uit uw Business Wallet beschikbaar is. Daarvoor vraag ik apart om uw toestemming.


**run 4** (4.6 s, tools: ['regelrecht__execute_law']) — toezeggingen: geen

> Voor het opvragen van uw bedrijfsgegevens bij de Kamer van Koophandel is uw toestemming nodig.
>
> Geeft u toestemming via de "Delen"-knop, en stelt u daarna uw vraag opnieuw? Dan kan ik direct verder met de toets.


**run 5** (35.7 s, tools: ['regelrecht__execute_law']) — toezeggingen: geen

> Voor het ophalen van uw bedrijfsgegevens uit het KvK Handelsregister is uw akkoord nodig. Geeft u toestemming via de "Delen"-knop? Daarna kan ik de toets meteen uitvoeren.


### Tools per beurt

- run 1: b1[regelrecht__execute_law, regelrecht__execute_law] → b2[regelrecht__execute_law, kvk__mijn_bedrijf, regelrecht__execute_law, kvk__mijn_bedrijf] → b3[regelrecht__execute_law, netbeheerder__verbruik, regelrecht__execute_law, regelrecht__execute_law, netbeheerder__verbruik] → b4[regelrecht__execute_law, regelrecht__execute_law, regelrecht__execute_law] → b5[regelrecht__execute_law, regelrecht__execute_law] → b6[regelrecht__execute_law, regelrecht__execute_law] → b7[regelrecht__execute_law, regelrecht__execute_law, rvo__indienen]
- run 2: b1[regelrecht__execute_law] → b2[regelrecht__execute_law, kvk__mijn_bedrijf, regelrecht__execute_law, kvk__mijn_bedrijf] → b3[regelrecht__execute_law, netbeheerder__verbruik, regelrecht__execute_law, regelrecht__execute_law, netbeheerder__verbruik] → b4[regelrecht__execute_law, regelrecht__execute_law, regelrecht__execute_law] → b5[regelrecht__execute_law, regelrecht__execute_law] → b6[regelrecht__execute_law, regelrecht__execute_law] → b7[regelrecht__execute_law, regelrecht__execute_law, rvo__indienen]
- run 3: b1[regelrecht__execute_law] → b2[regelrecht__execute_law, kvk__mijn_bedrijf, regelrecht__execute_law, kvk__mijn_bedrijf] → b3[regelrecht__execute_law, netbeheerder__verbruik, regelrecht__execute_law, regelrecht__execute_law, netbeheerder__verbruik] → b4[regelrecht__execute_law, regelrecht__execute_law] → b5[regelrecht__execute_law, regelrecht__execute_law] → b6[regelrecht__execute_law, regelrecht__execute_law] → b7[regelrecht__execute_law, regelrecht__execute_law, rvo__indienen]
- run 4: b1[regelrecht__execute_law] → b2[regelrecht__execute_law, kvk__mijn_bedrijf, regelrecht__execute_law, kvk__mijn_bedrijf] → b3[regelrecht__execute_law, netbeheerder__verbruik, regelrecht__execute_law, regelrecht__execute_law, netbeheerder__verbruik] → b4[regelrecht__execute_law, regelrecht__execute_law] → b5[regelrecht__execute_law, regelrecht__execute_law] → b6[regelrecht__execute_law, regelrecht__execute_law] → b7[regelrecht__execute_law, regelrecht__execute_law, rvo__indienen]
- run 5: b1[regelrecht__execute_law] → b2[regelrecht__execute_law, kvk__mijn_bedrijf, regelrecht__execute_law, kvk__mijn_bedrijf] → b3[regelrecht__execute_law, netbeheerder__verbruik, regelrecht__execute_law, regelrecht__execute_law, netbeheerder__verbruik] → b4[regelrecht__execute_law, regelrecht__execute_law] → b5[regelrecht__execute_law, regelrecht__execute_law] → b6[regelrecht__execute_law, regelrecht__execute_law] → b7[regelrecht__execute_law, regelrecht__execute_law, rvo__indienen]

### Gefaalde controles van het meetscript

- run 1: geen foutmelding; geen foutmelding; antwoord blijft onder 15 woorden per zin (score 54); de frontend kan hier ook uit de tekst een formulier maken; antwoord blijft onder 15 woorden per zin (score 43); de frontend kan van de maatregelen een formulier maken; antwoord blijft onder 15 woorden per zin (score 28)
- run 2: geen foutmelding; de assistent vraagt om toestemming; antwoord blijft onder 15 woorden per zin (score 70); antwoord blijft onder 15 woorden per zin (score 58); de frontend kan hier ook uit de tekst een formulier maken; antwoord blijft onder 15 woorden per zin (score 43); de frontend kan van de maatregelen een formulier maken; antwoord blijft onder 15 woorden per zin (score 59)
- run 3: geen foutmelding; de assistent vraagt om toestemming; antwoord blijft onder 15 woorden per zin (score 71); antwoord blijft onder 15 woorden per zin (score 53); de frontend kan hier ook uit de tekst een formulier maken; de frontend kan van de maatregelen een formulier maken; antwoord blijft onder 15 woorden per zin (score 44)
- run 4: geen foutmelding; geen foutmelding; antwoord blijft onder 15 woorden per zin (score 56); de frontend kan hier ook uit de tekst een formulier maken; antwoord blijft onder 15 woorden per zin (score 53); de frontend kan van de maatregelen een formulier maken; antwoord blijft onder 15 woorden per zin (score 39); antwoord blijft onder 15 woorden per zin (score 62)
- run 5: geen foutmelding; de frontend kan hier ook uit de tekst een formulier maken; de frontend kan van de maatregelen een formulier maken; antwoord blijft onder 15 woorden per zin (score 33)

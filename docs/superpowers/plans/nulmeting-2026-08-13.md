# Nulmeting onderzoeksflow — 2026-08-13

**Doel:** vastleggen hoe vaak de vier bekende, intermitterende bevindingen
optreden vóórdat taak 3 t/m 7 (feiten uit de bron, slot-substitutie) ze
repareren. Zonder dit ijkpunt is een latere verbetering een bewering, geen
meting.

- **Datum:** 2026-08-13
- **Modus:** `vlam`
- **KvK:** `62345681` (Kwekerij De Bloesem — plicht via gas en elektriciteit,
  onder de onderzoeksdrempel na taak 1)
- **Commit-hash waarop gemeten is:** `f22f0634f7dc3e35492859c4e9732847320240e7`
- **Host:** `http://127.0.0.1:8000`, vijf bronnen verbonden
- **Runs:** 5, met
  `uv run python services/host/scripts/onderzoeksflow.py --mode vlam --kvk 62345681 --runs 5 --json ...`

## Samenvatting per controle

Alle controles waarvan de teller "hoe vaak deze controle daadwerkelijk
draaide" per run gelijk is (de meeste draaien elke run precies één keer).
De taalniveau-controle (B1) is hier samengevoegd: het script registreert hem
per beurt onder een reden die de gemeten score bevat, dus in de ruwe JSON
staat hij als tientallen aparte 1/1-regels. Samengevoegd: **24/30** (som van
de losse tellers).

| Controle | Score |
|---|---|
| backend vlam is beschikbaar | 5/5 |
| alle vijf de bronnen zijn verbonden | 5/5 |
| geen foutmelding | 30/30 |
| geen bron geraadpleegd voor toestemming (PDR-008) | 5/5 |
| de assistent vraagt om toestemming | 5/5 |
| kvk__mijn_bedrijf is aangeroepen | 5/5 |
| netbeheerder__verbruik is aangeroepen | 5/5 |
| regelrecht__execute_law is aangeroepen | 5/5 |
| het antwoord noemt de bedrijfsnaam van het scherm | 5/5 |
| het antwoord noemt het elektriciteitsverbruik van het scherm (420.000) | 5/5 |
| het antwoord noemt het gasverbruik van het scherm (140.000) | 5/5 |
| elk genoemd adres is dat van het scherm (Hoefweg 210) | 1/1 (vuurt alleen als het antwoord een adresregel bevat; dat gebeurde in 1 van de 5 runs) |
| de frontend kan hier een formulier van maken (stap 3, de twee vragen) | 5/5 |
| twee vragen als velden (2) | 5/5 |
| **de frontend kan van de maatregelen een formulier maken (stap 4, EML)** | **1/5** |
| het formulier heet 'Erkende Maatregelenlijst (EML 2023)' | 1/1 (vuurt alleen als spec niet None is) |
| nog niet ingediend zonder bevestiging | 5/5 |
| de assistent vraagt eerst om bevestiging | 5/5 |
| rvo__indienen is aangeroepen (na bevestiging) | 5/5 |
| er komt een case-event voor 'Lopende zaken' | 5/5 |
| de rapportage gaat 'in behandeling', niet 'goedgekeurd' | 4/5 |
| antwoord blijft onder 15 woorden per zin (B1, samengevoegd over alle beurten) | 24/30 |

Ruwe JSON: zie taak-2-report.md. Ruwe log van de vijf runs: zie taak-2-report.md
(volledige stdout is niet in git opgenomen, wel het rapport).

## Duiding tegen de vier bekende bevindingen

1. **Het formulier rendert niet (stap 4, EML-maatregelen).** Bevestigd en
   ernstiger dan "1 op 3": **4 van de 5 runs** faalden hier (run 1, 3, 4, 5).
   Alleen run 2 leverde output die `parse_vraag` tot een formulier kon maken.
   Dit is de dominante bevinding van deze nulmeting.
2. **Verzonnen adres.** Niet waargenomen deze meting: de adrescontrole vuurde
   maar in 1 van de 5 runs (de assistent noemt een adres niet in elke beurt),
   en dat ene geval klopte met het scherm. De lage vuurfrequentie betekent dat
   deze meting weinig zegt over hoe vaak het feitelijk misgaat — vier runs
   gaven simpelweg geen adres, dus geen signaal in beide richtingen.
3. **Bevestig-deadlock.** Niet waargenomen: `rvo__indienen` is in alle 5 runs
   na de bevestigingsvraag aangeroepen.
4. **Verzonnen drempelwaarden.** Niet automatisch gemeten: er is geen
   assertie in `onderzoeksflow.py` die drempelwaarden in de tekst tegen de
   bron controleert (dat is precies wat taak 3 t/m 5 gaat toevoegen — de
   feitenkaart en slot-substitutie). Dit blijft dus een blinde vlek van de
   huidige nulmeting.

Bijvangst buiten de vier bekende bevindingen: de zin "in behandeling, niet
goedgekeurd" viel in run 1 weg (4/5) en de taalniveau-toets (B1) faalde op 6
van de 30 beurten (24/30) — geen van beide hoort bij deze taak, maar ze horen
wel in het beeld voor wie de volgende taken plant.

## Herhalen

```bash
env -u ANTHROPIC_API_KEY uv run uvicorn api:app --app-dir services/host --port 8000
# in een andere shell:
uv run python services/host/scripts/onderzoeksflow.py \
  --mode vlam --kvk 62345681 --runs 5 --json /tmp/nulmeting-vlam.json
```

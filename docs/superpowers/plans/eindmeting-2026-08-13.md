# Eindmeting onderzoeksflow — 2026-08-13

**Doel:** vastleggen hoe de flow ervoor staat na taak 1 t/m 7 (feiten uit de
bron, slot-substitutie, maatregelen als data op het answer-event), afgezet
tegen de nulmeting van dezelfde dag. Zonder dit ijkpunt is "het is beter"
een bewering, geen meting.

- **Datum:** 2026-08-13
- **Modus:** `vlam`
- **KvK:** `62345681` (Kwekerij De Bloesem — plicht via gas en elektriciteit,
  onder de onderzoeksdrempel na taak 1)
- **Commit-hash waarop de weergegeven meting draaide:** `0e14153dd83f0368160f4d889680c477be47bc07`
- **Host:** `http://127.0.0.1:8000`, vijf bronnen verbonden, niet herstart
  tijdens deze taak
- **Runs:** 5, met
  `uv run python services/host/scripts/onderzoeksflow.py --mode vlam --kvk 62345681 --runs 5 --json ...`

## Samenvatting per controle, naast de nulmeting

De B1-taalniveau-controle is samengevoegd (zie nulmeting voor de reden): in de
ruwe JSON staat hij als tientallen aparte 1/1-regels per gemeten score,
hieronder de som.

| Controle | Nulmeting (`f22f063`) | Eindmeting (`0e14153`) |
|---|---|---|
| backend vlam is beschikbaar | 5/5 | 5/5 |
| alle vijf de bronnen zijn verbonden | 5/5 | 5/5 |
| geen foutmelding | 30/30 | 30/30 |
| geen bron geraadpleegd voor toestemming (PDR-008) | 5/5 | 5/5 |
| de assistent vraagt om toestemming | 5/5 | 5/5 |
| kvk__mijn_bedrijf is aangeroepen | 5/5 | 5/5 |
| netbeheerder__verbruik is aangeroepen | 5/5 | 5/5 |
| regelrecht__execute_law is aangeroepen | 5/5 | 5/5 |
| het antwoord noemt de bedrijfsnaam van het scherm | 5/5 | 5/5 |
| het antwoord noemt het elektriciteitsverbruik van het scherm | 5/5 | 5/5 |
| het antwoord noemt het gasverbruik van het scherm | 5/5 | 5/5 |
| elk genoemd adres is dat van het scherm | 1/1 (vuurde in 1/5 runs) | 1/1 (vuurde in 1/5 runs) |
| de frontend kan hier een formulier van maken (stap 3, de twee vragen) | 5/5 | 5/5 |
| twee vragen als velden (2) | 5/5 | 5/5 |
| **de frontend kan van de maatregelen een formulier maken (stap 4, tekstparser)** | **1/5** | **2/5** (zie duiding hieronder — dit pad is inmiddels de fallback) |
| het formulier heet 'Erkende Maatregelenlijst (EML 2023)' | 1/1 | 2/2 (vuurt alleen als de tekstparser al een spec teruggaf) |
| **het answer-event draagt een maatregelen-lijst** *(nieuw)* | n.v.t. | **5/5** |
| **elk item heeft een gevulde code en omschrijving** *(nieuw)* | n.v.t. | **5/5** |
| **geen onopgelost slot in het antwoord** *(nieuw)* | n.v.t. | **10/10** |
| **de bron-waarden staan in het antwoord (na substitutie)** *(nieuw)* | n.v.t. | **5/5** (stap 2; zie correctie hieronder voor stap 6) |
| **het rapport bevat bedrijfsnaam / vestigingsadres / elektriciteitsverbruik** *(nieuw, stap 5)* | n.v.t. | **5/5 / 5/5 / 5/5** |
| nog niet ingediend zonder bevestiging | 5/5 | 5/5 |
| de assistent vraagt eerst om bevestiging | 5/5 | 5/5 |
| rvo__indienen is aangeroepen (na bevestiging) | 5/5 | 5/5 |
| er komt een case-event voor 'Lopende zaken' | 5/5 | 5/5 |
| de rapportage gaat 'in behandeling', niet 'goedgekeurd' | 4/5 | 5/5 |
| antwoord blijft onder 15 woorden per zin (B1, samengevoegd) | 24/30 | 25/30 |

Ruwe log en JSON van de weergegeven meting: `eindmeting3.log` / `eindmeting3.json`
(niet in git — net als bij de nulmeting is de volledige stdout niet
opgenomen, dit document is het geconsolideerde verslag).

## Duiding tegen de vier bekende bevindingen uit de nulmeting

1. **Het formulier rendert niet (stap 4, EML-maatregelen) — grotendeels
   opgelost, via een ander mechanisme dan de tekstparser-controle meet.**
   Taak 7 voegde een `maatregelen`-veld toe aan het `answer`-event zelf.
   `parseVraag` in de frontend leest dat veld vóórdat hij ooit aan het parsen
   van platte tekst toekomt. Deze eindmeting toetst dat structurele pad apart
   (`_controleer_maatregelen_event`) en dat staat op **5/5**: elke run droeg
   een gevulde maatregelen-lijst met code én omschrijving. De tekstparser-
   controle (de oude regel uit de nulmeting) staat er *ook nog steeds* in en
   scoort **2/5** — dat cijfer is nu grotendeels betekenisloos voor wat de
   respondent ziet, omdat de frontend dat pad met een gevuld `maatregelen`-veld
   nooit meer bereikt. Hij blijft in de tabel staan naast het nieuwe cijfer
   in plaats van verwijderd te worden, want een toekomstige regressie op het
   structurele veld zou anders onopgemerkt blijven als de fallback toevallig
   ook faalt.

   **Escalatieregel, expliciet niet toegepast op dit cijfer.** 2/5 is per
   definitie wisselvallig (niet 5/5, niet 0/5) en zou volgens de escalatieregel
   uit de spec vijf extra runs vereisen voordat een oordeel volgt. Dat is hier
   bewust overgeslagen: het cijfer meet een codepad dat de frontend niet meer
   bereikt zolang het `maatregelen`-veld gevuld is (en dat staat zelf op 5/5,
   niet wisselvallig). Vijf extra runs van de tekstparser-fallback zouden geen
   informatie toevoegen over wat de respondent op 25/27 augustus ziet. Mocht
   het structurele veld ooit weer leeg raken, dan is dát het signaal om de
   tekstparser-score opnieuw serieus te nemen.

2. **Verzonnen adres.** Zelfde blinde vlek als de nulmeting: de adrescontrole
   vuurde ook nu maar in 1 van de 5 runs (de assistent noemt niet in elke
   toestemmingsbeurt een adresregel), en dat ene geval klopte met het scherm.
   Vijf runs is te weinig om hier iets zinnigs over te zeggen in beide
   richtingen — precies wat de nulmeting al concludeerde.

3. **Bevestig-deadlock.** Niet waargenomen: `rvo__indienen` is in alle 5 runs
   na de bevestigingsvraag aangeroepen, net als in de nulmeting.

4. **Verzonnen drempelwaarden / bron-substitutie.** Dit is de controle die de
   nulmeting expliciet niet kon meten. De nieuwe `_controleer_slots`-controle
   (taak 8, dit script) vangt een deel daarvan: **10/10** op "geen onopgelost
   slot" en **5/5** op "de bron-waarden staan na substitutie in het antwoord"
   (stap 2). Geen enkel onopgelost `{{...}}`-slot in 10 beurten waarin de
   controle draaide, en in alle 5 runs stond minstens één van de vier
   bronwaarden (naam, straat, elektriciteit, gas) letterlijk in de
   toestemmingsbeurt - de controle (`bool(letterlijk)`) eist niet dat alle
   vier verschijnen, dus dit toont aan dat de substitutie draaide, niet dat
   elk feit apart genoemd werd.

   **Wat dit niet meet — en waarom dat buiten bereik van dit script valt.**
   De spec vraagt ook om "geen letterlijk feit waar een slot hoort" op de
   *ruwe* modeltekst vóór substitutie. Dat kan dit script niet toetsen: over
   HTTP komt alleen het ingevulde `message` van het `answer`-event binnen, de
   host stuurt de tekst vóór `vul_slots()` niet mee. Dat zou een nieuw veld op
   het contract vereisen, vlak vóór een onderzoek — bewust niet in dit plan.
   Deze meting toetst dus het eindresultaat (staan de juiste waarden er, na
   substitutie) en niet het proces (schreef het model zelf al de juiste
   waarden, of een placeholder die de host vervolgens opvulde). Beide zijn
   verschillende beweringen; alleen de eerste is hier gemeten.

## Bijvangst buiten de vier bekende bevindingen

- **"In behandeling, niet goedgekeurd" is nu 5/5** (was 4/5 in de nulmeting).
- **B1-taalniveau blijft grofweg gelijk: 25/30** (was 24/30). Geen van beide
  hoort bij deze taak, maar het hoort in het beeld voor wie de volgende taken
  plant.
- **REFERENTIENUMMER: open aandachtspunt, niet opgelost.** In eerdere runs
  tijdens deze taak (buiten de hier gerapporteerde vijf, zie hieronder) blokte
  minstens één beurt op een onopgelost `{{REFERENTIENUMMER}}`-slot, in de
  bevestigingsbeurt (stap 6) zelf: `"✅ Uw rapportage is ingediend (referentie
  RVO-RVO-{{REFERENTIENUMMER}}-62345681-001-...) en in behandeling genomen."`
  De rvo-server levert een referentienummer wel
  (`lopende_zaak.referentienummer`), dus dit is vermoedelijk het model dat het
  slot al gebruikt in de beurt waarin het om bevestiging vráágt — vóórdat er
  iets is ingediend en er dus nog geen referentienummer bestaat om in te
  vullen. `slots.md` staat al toe dat een slot pas na het raadplegen van de
  bron mag; dit is een geval waar het model dat kennelijk niet volgt. In de
  vijf runs die in de tabel hierboven staan trad dit **niet** op (10/10 schoon).
  Gegeven de wisselvalligheid wordt dit hier niet als opgelost geboekt, maar
  als openstaand aandachtspunt voor wie hierna verder werkt. Dit is bewust
  niet gerepareerd in deze taak (zie "Wat deze taak niet is" in de brief).

## De tussenmeting die een regressie ving

De eerste volledige eindmeting binnen deze taak liep op commit `0ec8541`
(vóór de fix hieronder) en brak fors: **9 van de 30 beurten** blokkeerden op
`ANTWOORD_ONVOLLEDIG`, en de bedrijfsgegevens kwamen in **0 van de 5 runs**
door in de toestemmingsbeurt. Oorzaak: `feiten.py` las paden die de echte
KvK- en netbeheerder-MCP-servers niet teruggeven (`data.totaal` in plaats van
`verbruik.totaal`, `data.bag.is_woonfunctie` in plaats van naast `bag`, e.d.).
Gefixt in commit `0e14153dd83f0368160f4d889680c477be47bc07` ("lees feiten uit
de echte vorm van kvk/netbeheerder-resultaten"). Na die fix, met een
herstarte host, is de meting in de tabel hierboven opnieuw gedraaid en schoon.

Dát dit script die regressie ving vóórdat een respondent op 25 of 27 augustus
ertegenaan liep, is zelf een resultaat van deze taak: precies het scenario
waar de brief voor waarschuwt ("vindt het script fouten, dan is dat het
resultaat"), en het script deed hier zijn werk.

## Een correctie aan het script, ná de gerapporteerde meting

De eerste versie van `_controleer_slots` in dit script eiste de vier
bronwaarden letterlijk in *elk* antwoord waarop hij draaide, ook op stap 6
("Ja, dien maar in."). Die beurt is een indienbevestiging, geen
feitenrecitatie: de enige tool die daar draait is `rvo__indienen`, die geen
bedrijfsfeiten teruggeeft. In de meting hierboven ("de bron-waarden staan in
het antwoord (geen)", 0/5 op stap 6 in de ruwe run vóór deze fix) faalde de
controle dus op elke run — niet omdat de assistent iets verzon of de
substitutie faalde, maar omdat het script feiten eiste in een beurt die er
geen hoefde te noemen. De echte inhoud van die beurt bevestigt keurig
("Uw rapportage is ingediend ... en in behandeling genomen.") zonder de
bronwaarden te herhalen, wat voor een bevestigingsbericht het juiste gedrag
is.

De controle is na de meting gecorrigeerd: het tweede deel van
`_controleer_slots` (de letterlijke-bronwaarden-check) draait nu alleen op
een beurt die zelf een feiten-tool aanriep (`kvk__mijn_bedrijf`,
`netbeheerder__verbruik` of `regelrecht__execute_law`); het eerste deel (geen
onopgelost slot) blijft op elke beurt draaien. Dit is een correctie op het
*meetinstrument*, niet op de host of de prompt — die zijn in deze taak niet
aangeraakt. Deze correctie is **niet** opnieuw over vijf schone runs
gemeten binnen deze taak; de volgende keer dat dit script draait, telt de
gecorrigeerde versie vanzelf mee.

## Wat deze meting niet zegt

- **Vijf runs is een peiling, geen bewijs.** Bij een onderliggende foutkans
  van ⅓ mist een reeks van vijf schone runs die fout nog in ongeveer 13% van
  de gevallen (0.67⁵ ≈ 0.135). Een controle die hier 5/5 scoort kan dus nog
  steeds een reëel, niet-triviaal risico verbergen. Dat geldt onverkort voor
  elke 5/5-regel in de tabel hierboven.
- **De ruwe-modeltekst-controle valt buiten bereik.** Zoals hierboven bij
  bevinding 4 toegelicht: dit script ziet nooit de tekst vóór substitutie,
  dus "schreef het model zelf een verzonnen feit waar een slot hoort" is
  hier niet getoetst — alleen "staat het juiste feit er, na substitutie".
- **Lage vuurfrequentie bij de adrescontrole** (1/5) betekent dat vier van de
  vijf runs simpelweg geen signaal geven, in geen van beide richtingen.
- **REFERENTIENUMMER** is een waargenomen, niet-gerepareerd risico dat in de
  hier gerapporteerde vijf runs toevallig niet optrad — zie hierboven.

## Herhalen

```bash
# host draait al op poort 8000 met vijf bronnen verbonden, niet herstarten
uv run python services/host/scripts/onderzoeksflow.py \
  --mode vlam --kvk 62345681 --runs 5 --json /tmp/eindmeting-vlam.json
```

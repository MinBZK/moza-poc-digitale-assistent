# Beoordeling van de toets van PDR-014 door een tweede lezer

> Momentopname. Deze beoordeling is gemaakt vóór de correcties die erop
> volgden (zie "Wat de beoordeling veranderde" in het rapport). De
> regelnummers verwijzen naar de PDR van dat moment en kloppen niet meer; de
> bestanden `runs-main.json` en `runs-f22f063.json` heten nu
> `main/main-run*.json` en `f22f063/f22f063-run*.json` en bevatten de
> volledige events. De cijfers 28 (eerste beurten) en 8 (weigeringen in de flow) zijn
> in rapport en PDR vervangen door 37 en 7 (14 met de losse vragen erbij). Onder C.4 klopt "f22f063 run 2"
> niet: alleen main run 2 noemt loonkostensubsidie en banenafspraak. Punt C.3
> (termijnuitspraak in beurt 7) is achterhaald: die zin volgt een promptvoorbeeld
> ("Bij de volgende ronde ({{VOLGENDE_DEADLINE}})") en de instructie
> "volgende rapportageronde" in `tool_usage.md`; wie het slot vulde is uit de
> run-JSON niet te zien. Punt C.6 zegt
> "drie bronnen": het zijn twee bronnen plus de toets. De beperkingen in het
> rapport zijn hernummerd (de peiling-beperking is nu 3).
> De doorlooptijden "94,8–162,6 s" zijn wandkloktijd inclusief wachten buiten
> de beurten; de som van de beurten is 95–146 s.

Datum 2026-09-02. Gelezen: PDR-014, het meetrapport van 2 september, de
bestanden onder `toets-pdr-014/` (runs-main.json, runs-f22f063.json,
vage-vragen.json, engine-runs.json, analyse-ruw.md, meet.py, analyse.py) en
`assets/pdr-014/log3-250000-engine.txt`. Alle aantallen hieronder zijn met
python3 nageteld in de JSON; waar ik afwijk van het rapport staat dat erbij.

## A. Oordeel per claim

| ID | Oordeel over het rapport | Toelichting en bewijs |
|---|---|---|
| C1 | **akkoord, met nuance** | Engine 10/10 identiek per case: E2 `"250.000"` → input 250, `requirements_met=false`, `plicht=null`; E4 `-65000` idem (engine-runs.json, log3 aanroep 2 en 4). Verwijzing naar Kloof trede 5 en Onderbouwing A klopt. Nuance: de engine geeft **geen uitkomst**, niet "plicht vervalt" (zie B2). De hostnormalisatie zelf is niet gemeten: E1 is een door het script genormaliseerde aanroep, geen host-run. |
| C2 | **akkoord als meetuitkomst, niet akkoord als bewijskracht** | Regex van analyse.py op beurt 1 van de flow: 0/10 treffers (nageteld). Op de vage vragen is de regex door het script níet toegepast (analyse-ruw.md bevat alleen de flow); toegepast geeft hij treffers in 5/9 main-antwoorden (`geldt`, "Deadline: 31 december 2026") en 1/9 f22f063. De "0 in 28" is dus 10 geteld plus 18 met de hand gelezen; die lezing (RVO-bron, voorbehoud) is verdedigbaar. Maar de proef heeft weinig kracht: beurt 1 van de flow is per ontwerp een toestemmingsvraag, en de arbeidsmarktvraag wordt 6/6 op promptniveau geweigerd, zodat B4/B5-vertaling nooit in beeld komt. De PDR-zin in Kloof ("De eerste beurt raakt per ontwerp geen bron aan") wordt bovendien zelf tegengesproken op main (zie B1); het rapport beoordeelt alleen de tweede helft van die zin. |
| C3 | **akkoord** | `is ingediend` zonder `rvo__indienen`: 0/5 main, 0/5 f22f063 (nageteld). Verwijzing Onderbouwing A (eindmeting 13 augustus, REFERENTIENUMMER) klopt en de PDR presenteert het daar al als historisch geval. |
| C4 | **akkoord** | Datum-regex over alle beurten: main 5/5 alleen "1 december 2026", "2027" komt nergens voor; f22f063 noemt geen datum (nageteld). Verwijzing naar `5989bf8` in Onderbouwing A klopt. |
| C5 | **akkoord** | f22f063: `execute_law` eerst in beurt 2 (5/5), uitkomst beurt 2 (5/5), mediaan 4,85 s, beurt 2 = 18,2–40,4 s. main: `execute_law` in beurt 1 (5/5), uitkomst beurt 3 (5/5), mediaan 16,0 s, max 43,2 s, runs 94,8–162,6 s. Alles nageteld en juist. Let op: de Onderbouwing-zin (r. 423-424) staat expliciet als "Vóór 13 augustus" en wordt door f22f063 bevestigd; alleen de Kloof-zin (r. 105, "tweede of derde") staat in de tegenwoordige tijd. "Met lege parameters" is uit de gecommitte data niet te controleren (geen parameters in runs-main.json). |
| C6 | **niet akkoord (deels)** | `rvo__zoek_regeling` 0× in 10 flow-runs en `execute_law` 14/15/14/14/16 per run: klopt. De toeschrijving "dat is de regelloop, niet het model" is uit de gecommitte data niet te controleren (geen herkomst per aanroep) en wordt tegengesproken door de variatie: run 1 beurt 1 heeft 2 `execute_law` tegen 1 in runs 2-5, en runs 1-2 beurt 4 hebben 3 tegen 2 in runs 3-5. Een deterministische host-lus varieert niet; de 0-2 extra aanroepen per run zijn dus vermoedelijk van het model. In run 1 beurt 1 geeft het model bovendien de engine-melding door ("Uit RegelRecht blijkt ondertussen dat ik ook nog twee gegevens nodig heb"): dat is het patroon van figuur 4 uit de PDR (model roept de wet zelf aan, krijgt ontbrekende gegevens), zonder de valse storingsmelding. "Niet meer waargenomen" is te sterk; "niet aantoonbaar uit deze data" is houdbaar. |
| C7 | **niet akkoord op aantal en toeschrijving; akkoord op de poort** | `TOESTEMMING_VEREIST` op main: run 1 (kvk, netbeheerder), 2 (kvk), 3 (kvk), 4 (kvk, netbeheerder), 5 (kvk) = **7**, niet 8. De netbeheerder-weigering in beurt 2 komt in 2/5 runs voor; een host-lus die "de wallet-route probeert" zou dat 5/5 of 0/5 doen. Herkomst is uit runs-main.json niet af te leiden (`bron_fouten` heeft alleen code en bron). De conclusie dat het model het niet was, rust op event-streams die niet in git staan. Wel juist: `netbeheerder__verbruik` staat in geen enkele beurt < 3 in de tools, en PDR-008-controle 5/5 op beide hosts. Verwijzing naar de poort-bullet klopt; de PDR-tekst staat daar in de verleden tijd, alleen het onderschrift van figuur 5 in de tegenwoordige. |
| C8 | **akkoord** | main: controle "deze beurt voegt iets toe" 5/5 (één controle per run, beurt 4). f22f063: beurt 4, 5 en 6 herhalen de vier vragen in runs 1, 2, 3, 5 en drie ervan in run 4 (nageteld op trefwoorden). Verwijzing naar Onderbouwing A (r. 433-436) en D klopt. |
| C9 | **akkoord, met nuance in de formulering** | De controle "execute_law vóór elke andere bron" bestaat één keer per run: 5/5, geen 35/35. Het 35/35 is wel afleidbaar uit de tool-volgorde: in alle 35 main-beurten is `regelrecht__execute_law` de eerste tool. PDR-008 5/5, "KvK niet vóór akkoord" 5/5, "KvK-akkoord opent de wallet niet" 5/5 (nageteld). Verwijzing naar "De architectuur is al opgeschoven" klopt. |
| C10 | **akkoord, verkeerd voorbeeld** | "vraagt om toestemming" 3/5 (runs 2 en 3 zonder vraagteken), "geen foutmelding" 28/35, runs 94,8–162,6 s, f22f063 beurt 2 18-40 s: alles nageteld. Maar de 7 gefaalde "geen foutmelding" zijn precies de `TOESTEMMING_VEREIST`-weigeringen die het rapport elders aan de host toeschrijft; als bewijs voor "gedrag wisselt per run" is dat het verkeerde voorbeeld. De echte variatie zit in 3/5, in de extra `execute_law`-aanroepen (C6) en in de wisselende doorverwijzingen bij de arbeidsmarktvraag (UWV, gemeente, RVO, Juridisch Loket, branchevereniging, HR-adviseur, arbeidsdeskundige, per run anders). |

## B. Uitspraken in de PDR die de gegevens niet dragen en die het rapport niet noemt

1. **Kloof, r. 91-92:** "De eerste beurt raakt per ontwerp geen bron aan (toestemming eerst, PDR-008)." Op main roept beurt 1 in 5/5 flow-runs en 9/9 vage vragen `regelrecht__execute_law` aan, en bij de subsidievraag 3/3 ook `rvo__zoek_regeling`. Alleen toestemmingsplichtige bronnen blijven onaangeroerd. De zin klopt voor f22f063 (0 tools in beurt 1, 5/5 en 9/9), niet voor de huidige host. Het rapport citeert de zin bij C2 maar toetst alleen het toezeggingsdeel.
2. **Onderbouwing A, r. 327-329:** "De opgave `250.000` kWh werd door de engine als tweehonderdvijftig gelezen, waarmee de plicht onterecht verviel" en "Een tikfout `-5000` liet de plicht eveneens vervallen." De engine geeft in E2 en E4 `requirements_met=false` en `plicht=null`, 10/10: geen uitkomst, geen "nee". Het onderschrift van figuur 3 ("er komt geen uitkomst") is wel juist; de lopende tekst niet. Of de host van 19 augustus "geen uitkomst" als "plicht vervalt" toonde, staat niet in deze data. Merk op dat `"90.000"` gas ook 90 wordt; de PDR noemt alleen elektriciteit.
3. **Kloof, r. 128-129:** "zelfs daar komt een verkeerd getal zonder melding door." Half waar: E2 en E4 hebben `missing=[]` (geen veldmelding), maar wel `requirements_met=false`. Er ís een signaal, alleen geen aanwijsbaar veld.
4. **Onderbouwing A, r. 457-458:** "voor B4, B5 en B6 is hij al vervangen door code, voor één wet." Op main kiest het model bij "Welke subsidies en verplichtingen" zelf `rvo__zoek_regeling` (3/3) en doet het bij de arbeidsmarktvraag in 1/3 runs een regelingskeuze uit modelkennis ("regelingen zoals loonkostensubsidie of de banenafspraak"). B4 is buiten de ene flow dus nog steeds een modelstap; de zin geldt alleen binnen de informatieplicht-flow.
5. **Onderbouwing A, r. 437-438:** "de zwaarste gemeten 20 seconden" (rooktest 25 augustus). Op main nu 43,2 s (run 2 beurt 3) en 35,7 s in een toestemmingsbeurt zonder bronraadpleging (run 5 beurt 1). Het rapport geeft de nieuwe cijfers wel, maar wijst deze verouderde zin niet aan.

## C. Bevindingen die de PDR sterker maken en die het rapport niet benoemt

1. **De regel is niet wat de tijd kost.** engine-runs.json: mediaan 54-63 ms per aanroep, max 154 ms, 60/60 identiek. Tegenover 16 s mediaan per beurt op main betekent dat dat vrijwel alle tijd in model en gesprek zit. Dit is het hardste argument voor "de regel draait als eerste" (Beslissing 1) en ontbreekt in het rapport.
2. **De engine meldt zelf wat hij mist, met vraagtekst.** E5 en E6 geven 10/10 `missing_fields` met `name`, `description` ("Of het pand uitsluitend een woonfunctie heeft") en `suggestion`. Dat is precies de route van PDR-008 die de PDR in de tabel "Velden" als "werkt live" opvoert (r. 248); hier staat het gemeten bewijs.
3. **Een termijnuitspraak van het model ná de toets.** Main beurt 7 in runs 2, 3, 4 en 5: "Bij de volgende rapportageronde (1 december 2026) staat het voorwerk al klaar." De datum komt uit de engine, de koppeling aan "volgende ronde" (die na indienen in 2026 niet 1 december 2026 kan zijn) is van het model. Klein, maar het is het gedrag waarvoor de guardrail (r. 415-416) bestaat, en het rapport zegt dat termijnproblemen "niet meer waargenomen" zijn.
4. **Modelkennis kiest regelingen buiten de flow.** Arbeidsmarktvraag: main run 2 en f22f063 run 2 noemen "loonkostensubsidie" en "banenafspraak" zonder bron; de doorverwijzingen wisselen per run. Bevestigt Onderbouwing B ("Modelkennis veroudert sneller dan het model") in de eerste beurt, ook al is het geen toezegging.
5. **Het patroon van figuur 4 komt nog voor, in milde vorm.** Zie C6: main run 1 beurt 1, twee `execute_law`-aanroepen en het model dat de ontbrekende velden doorgeeft. Het onderschrift van figuur 4 hoeft dus niet alleen historisch te zijn.
6. **De oude flow doet drie bronnen en de toets in één modelbeurt van 18-40 s** (f22f063 beurt 2, 5/5), zonder tussentijds zicht. Dat is r. 424-426 letterlijk gemeten; het rapport meldt het alleen als tijd.
7. **Het deel dat "overeind bleef" (Beslissing 3) scoort op main 5/5** op bronwaarden in het antwoord (Hoefweg 210, 420.000, 140.000), "nog niet ingediend zonder bevestiging", "vraagt eerst om bevestiging" en "in behandeling, niet goedgekeurd". Het nulmeting-gat "4/5 in behandeling" (r. 405-407) is daarmee gedicht; het rapport laat dat liggen.

## D. De twee beperkingen vooraf, en wat ontbreekt

**Beperking 1 (oude host, nieuwe engine): terecht, maar onvolledig.** Het script van 13 augustus verwacht ook andere mockdata: de controle "gasverbruik van het scherm (198.000)" faalt 5/5 terwijl de wallet 140.000 levert, dezelfde waarde als op main. Van de 7-8 gefaalde controles per f22f063-run zijn er zo minstens 4 (gas, vier vragen, indienen, case-event, in behandeling) artefacten van script en mock, niet van modelgedrag. Beurt 3 van f22f063 is overigens wél geldig (de wet draait en de vier vragen worden gesteld); alleen 4-6 zijn dood.

**Beperking 2 (vijf runs is een peiling): terecht**, (2/3)^5 = 13%. Het rapport houdt zich eraan.

**Wat de auteur mist:**

1. **De analyse is niet reproduceerbaar uit de repo.** `analyse.py` leest `x["events"]` en zoekt `*-run*.json`; de gecommitte `runs-*.json` zijn lijsten zonder events. Draaien geeft een traceback (geprobeerd). Alle herkomst-uitspraken (host versus model bij `execute_law` en `TOESTEMMING_VEREIST`, "met lege parameters") rusten op streams die niet in git staan.
2. **De toezegging-detectie meet weinig.** De regex draait alleen op beurt 1 van de flow, die per ontwerp een toestemmingsvraag is; de kolom "toezegging vóór bron" is op main leeg per constructie (eerste bron = beurt 1, dus geen beurten ervoor). Op de vage vragen is hij niet toegepast. De regex geeft valse treffers (`geldt`, `lijkt`) en mist wat de PDR bedoelt ("u komt in aanmerking", "recht op", "kunt u aanvragen", een regeling bij naam uit modelkennis). Het oordeel "0 toezeggingen" is een handmatige lezing, geen meting.
3. **De vage vragen zijn niet vaag genoeg of buiten scope.** Eén van de drie is vaag, en die weigert de prompt in 6/6 runs; de andere twee zijn de flowvraag in andere woorden. Het PDR-voorbeeld "hoe zit dat dan met die verplichting" is niet getest. B4/B5-vertaling is in geen enkele run in beeld gekomen; "niet bevestigd" betekent hier "niet getoetst".
4. **Het vergelijk main versus f22f063 is niet gelijkwaardig.** Andere scripts (7 tegen 6 beurten, 44 tegen 30-32 controles), ander toestemmingsmodel (twee akkoorden tegen één), andere verwachte mockdata. Het verschil 125 tegen 59 s per run bevat dus een extra beurt, een extra toestemmingsronde en het draaien van de regelloop in elke beurt; het rapport noemt de beurt wel, de rest niet.
5. **Twee tellingen kloppen niet.** `TOESTEMMING_VEREIST` op main is 7, niet 8. "Stel uw vraag opnieuw" staat in 4/5 eerste beurten en 0/5 tweede beurten van de flow (dus 4/10, geen "8/8"); op de vage vragen met weigering wel 6/6.
6. **Eén persona, één backend.** Alleen `claude`/sonnet-4-6, alleen een bedrijf met volledige wallet. De paden "ondernemer typt verbruik als tekst" (`af6924d`) en de hostnormalisatie (`cdde0e0`) zijn in de chat niet gemeten; C1 zegt alleen iets over de engine.

## E. Eindoordeel

Het rapport komt op de nageteld controleerbare punten (C1, C3, C4, C5, C8, C9, C10) overeen met de gegevens, met twee kleine telfouten (7 in plaats van 8; 4/10 in plaats van 8/8), maar de toeschrijving van alle `execute_law`- en `TOESTEMMING_VEREIST`-variatie aan de host (C6, C7) is uit de gecommitte data niet te controleren en wordt door de run-tot-run-variatie eerder tegengesproken dan gesteund. De PDR komt overeen met wat het rapport voorstelt te corrigeren, maar daarbovenop dragen de gegevens twee zinnen niet die het rapport laat staan: "de eerste beurt raakt per ontwerp geen bron aan" (op main onwaar) en "de plicht verviel" bij `250.000` en `-65000` (de engine geeft geen uitkomst). Het sterkste meetbare argument voor de beslissing, engine 60 ms tegen 16 s per chatbeurt, staat in de data en in geen van beide documenten.

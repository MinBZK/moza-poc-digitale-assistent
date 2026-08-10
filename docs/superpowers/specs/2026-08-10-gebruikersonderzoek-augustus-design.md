# Ontwerp: klaar voor het gebruikersonderzoek van 25 en 27 augustus 2026

| Veld | Waarde |
|---|---|
| Datum | 2026-08-10 |
| Status | Vastgesteld |
| Onderzoek | 25 en 27 augustus 2026, begeleid, max. 1 uur per sessie |
| Testscript | `docs/sessies/gebruikersonderzoek /Testscript_MoZa_DA.docx` (mapnaam eindigt op een spatie; niet in git) |
| Gerelateerd | PDR-009 (sessie-identiteit), PDR-010 (sleutel van de gebruiker), PDR-011 (foutmeldingen), PR #44, PR #45 |
| Repo's | `MinBZK/moza-poc-digitale-assistent` (backend), `MinBZK/poc-moza` (frontend) |

## Doel

Op **21 augustus** staat een omgeving die de respondenten door het testscript
draagt zonder dat de onderzoeker technisch hoeft in te grijpen: één gedeelde link,
de respondent klikt en typt, verder niets.

Dit is een voorbereidingsontwerp, geen productontwerp. Het beschrijft wat er moet
gebeuren om te kunnen meten, niet wat de assistent zou moeten worden. Elk werkstuk
hieronder krijgt een eigen implementatieplan en een eigen branch; dit document is
de coördinatie ertussen.

## Wat het onderzoek meet

Uit het testscript, omdat het bepaalt waar de voorbereiding wél en niet op stuurt:

- De respondent speelt **Robin Vogel**, vindt de assistent zelf op MijnOverheid
  Zakelijk, en stelt zijn eigen vraag over de energiebesparingsverplichting.
- Er wordt bewust **niet gestuurd**: "laat de respondent zelf typen en de
  conversatie voeren".
- Het script vraagt door op drie dingen: het **wachten** ("wat vond je van de manier
  waarop je zag dat de assistent bezig was"), het **begrijpen** ("wat was lastig te
  snappen", "kun je navertellen welke concrete vervolgstap je moet zetten") en het
  **vertrouwen** ("zou je hiernaar handelen zonder het ergens anders te checken").

Daaruit volgt de prioritering: begrijpelijkheid en een flow zonder doodlopers wegen
zwaar; visuele rijkdom weegt niet, want er is in het script geen moment waarop de
respondent daarop reageert vóórdat hij de tekst heeft gezien.

## Uitgangssituatie: drie blokkades

Vastgesteld op 2026-08-10 door de code te lezen, niet door aan te nemen.

1. **Geen sleutel, geen assistent.** De deployment draait bewust zonder
   LLM-sleutels (PDR-010, `docs/deploy-zad.md`); de frontend leest de sleutel uit
   `localStorage`. De respondent werkt in zijn eigen browser op zijn eigen machine,
   dus zonder ingreep krijgt hij op elke vraag "de backend is niet geconfigureerd".
2. **De standaardpersona bestaat niet in de backend.** `_data/personas.json` kent
   19 persona's; de actieve is `bouwmanagement` (Vogel Bouwregie B.V., KvK
   61234570). De backend-allowlist `TEST_KVK_NUMMERS` kent alleen 85234567,
   62345681 en 56789012. Een respondent die inlogt en meteen een vraag stelt,
   krijgt "Log eerst in om uw bedrijfsgegevens te kunnen gebruiken".
3. **Drie lagen tonen drie bedrijven.** `header-overheid.njk` hardcodeert "Robin
   Vogel van Bloom B.V.", het persona-systeem wijst naar Vogel Bouwregie, en de
   assistent antwoordt over het bedrijf achter het meegestuurde KvK-nummer. De
   scriptvraag "is dit gericht op jouw specifieke situatie?" is onbeantwoordbaar
   zolang dat uiteenloopt.

## Besluiten

### 1. Een tijdelijke serversleutel, als expliciete afwijking van PDR-010

De ZAD-component krijgt een aparte Anthropic-sleutel met spend limit;
`ALLOW_API_KEY_OVERRIDE=false`, zodat de sleutel-headers genegeerd worden en
niemand iets hoeft in te voeren.

Afgewezen: respondenten een sleutel geven. Ze zien hem, en `localStorage` betekent
dat hij ná de sessie in hun browser achterblijft — ook nadat de schermopname is
gewist. Dat is precies het risico dat PDR-010 wilde vermijden, en het schendt de
eigen regel uit dat PDR ("nooit `localStorage`").

Het geaccepteerde restrisico is dat `/chat` geen authenticatie heeft: wie de host
bereikt, verbruikt de sleutel. Draagbaar omdat de backend internal-only is en het
venster twee dagen beslaat. Dit wordt vastgelegd als **addendum op PDR-010**, met
de intrekdatum (27 augustus 2026) erin — niet als stille configwijziging.

### 2. Robin Vogel is bloemenkweker

De onderzoekslink zet de persona vast: `?persona=bloemenkweker` wint van
`localStorage` en van de `actief`-vlag. Dat is Kwekerij De Bloesem, KvK 62345681,
420.000 kWh en 198.000 m³ per jaar.

Waarom deze en niet de andere twee: De Bloesem is **al** indieningsplichtig op
zowel elektriciteit als gas, dus er hoeft geen verbruik verzonnen te worden, en
glastuinbouw met dat verbruik is het enige van de drie dat een echte ondernemer
meteen geloofwaardig vindt. Roots & Locks (haarstylist, 56789012) valt onder beide
drempels en zou verzonnen data vragen voor een eenmanszaak; Koffiezaak Noon
(85234567) werkt ook, maar voegt niets toe.

Gevolg voor het script: de rolbeschrijving moet "Robin Vogel, bloemenkweker bij
Kwekerij De Bloesem" worden. Dat is een aanpassing in het testscript, geen code.

### 3. Vier werkstukken vóór het onderzoek, één erna

W5 (RegelRecht visueel) wordt in deze ronde géén productiecode maar een klikbaar
concept dat ná de taken wordt voorgelegd. Zie de motivering onder "Wat het
onderzoek meet".

## Werkstukken

### W0 — Onderzoeksomgeving werkend

**Repo:** backend + ZAD-componentconfig.

- Aparte Anthropic-sleutel met spend limit op de component; `ALLOW_API_KEY_OVERRIDE=false`.
- Addendum op PDR-010: afweging, periode, intrekdatum, restrisico.
- `docs/deploy-zad.md` bijwerken zodat de beschreven stand klopt met de werkelijke.
- **Na te lopen:** de frontend toont nu "Vul uw API-sleutel in via het
  instellingenpaneel" als foutmelding (`digitale-assistent.js:779`). Met een
  serversleutel hoort die tekst nooit meer te verschijnen. PR #45 herschrijft
  precies deze foutmeldingen, dus dit pad wordt ná W1 geverifieerd.
- **Klaar als:** één echte vraag via de gedeelde link een antwoord geeft, in een
  schone browser zonder localStorage.

### W1 — PR #45 (foutmeldingen, PDR-011) mergen

**Repo:** backend. **Uiterste datum: 16 augustus.**

- Volgorde: PR #44 eerst, daarna #45 rebasen.
- Conflictgebied is `vlam_host.py`; beide PR's herschrijven de dispatch. Eén punt
  moet bewust landen: #45 vervangt `f"Fout bij tool '{tool_key}': {e}"` door
  `_bron_aanroep`, en dat is dezelfde plek waar #44 de logging aanpakte. De
  exception-tekst hoort daarna niet meer als tool-resultaat naar het LLM te gaan.
- Menselijke review is verplicht (`CODEOWNERS`) en is de traagste stap in de
  planning. Beleg de reviewer nu.
- **Klaar als:** gemerged in main, suite groen, `run_scenarios.py` groen.

### W2 — Persona kloppend maken over drie lagen

**Repo's:** backend + frontend.

- Backend: `MOCK_EIGENAREN["62345681"]` krijgt Robin Vogel als natuurlijk persoon,
  zodat `kvk__eigenaar` niet met een VOF zonder gezicht antwoordt.
- Frontend: `header-overheid.njk` persona-gedreven maken in plaats van "Robin Vogel
  van Bloom B.V." hard te coderen.
- `personas.json[13]` naast `MOCK_PROFIELEN["62345681"]` leggen: naam, adres,
  personeelsaantal en SBI moeten hetzelfde zeggen. Verschillen wegwerken of
  bewust vastleggen.
- **Klaar als:** met `?persona=bloemenkweker` tonen de header, de pagina
  Bedrijfsgegevens en het antwoord van de assistent hetzelfde bedrijf.

### W3 — B1-Nederlands

**Repo:** backend. **Na W1**, want het raakt dezelfde promptbestanden.

- Nieuw promptblok `prompts/blocks/shared/taalniveau.md`: korte zinnen, actieve
  vorm, geen juridisch jargon zonder uitleg, vaktermen één keer uitleggen.
- Vaste testset van tien realistische ondernemersvragen.
- Als regressiebewaking een offline leesbaarheidsmaat: de Flesch-Douma-index, de
  Nederlandse variant van Flesch Reading Ease, te berekenen uit zins- en
  woordlengte zonder externe dienst. **Deze maat meet vorm, geen begrip** — een
  korte zin kan onbegrijpelijk zijn, en een index is geen B1-certificaat. Ze vangt
  dat een antwoord plotseling veel juridischer wordt; of het werkelijk B1 is,
  beoordeelt een mens aan dezelfde tien antwoorden.
- **Risico, expliciet:** een LLM naar B1 duwen kost nuance, en dit gaat over een
  wettelijke verplichting. De guardrails ("dit is geen juridisch advies") en de
  bronverwijzing blijven staan, ook als de tekst daardoor langer wordt.
- **Klaar als:** de tien antwoorden zijn beoordeeld door een mens en de maat draait
  in de suite.

### W4 — Volledige doorloop en dry run

**Vanaf 18 augustus, minimaal drie dagen, want gevonden blokkades moeten nog gefixt.**

- Het volledige script als bloemenkweker, op de deployment, via de gedeelde link,
  in een schone browser zonder localStorage.
- Tien afdwalingen testen: de respondent typt vrij en het script stuurt bewust
  niet, dus buiten-scope-vragen, halve vragen en vervolgvragen horen erbij.
- Bevindingenlijst; blokkades vóór 21 augustus opgelost.
- Dry run met een collega die het script niet kent.
- **Klaar als:** de dry run zonder ingrijpen door het script komt.

### W5 — RegelRecht visueel, als concept

**Ná 27 augustus bouwen; vóór het onderzoek alleen als concept.**

- Los, klikbaar HTML-concept met twee of drie varianten: verbruik afgezet tegen de
  drempel, de berekening als stappen, en een "wat als"-variant.
- Wordt ná de taken voorgelegd: "stel dat het er zo uitzag — helpt dat?"
- **Klaar als:** het concept toonbaar is en de vraag in het script staat.

## Buiten scope

Geen nieuwe assistent-functionaliteit, geen authenticatie op `/chat`, geen
frontend-refactor, en geen aanpak van de openstaande lage reviewpunten uit PR #44.

## Kritiek pad en risico's

W0 en W2 kunnen direct beginnen. W1 is de traagste vanwege de verplichte review en
bepaalt daarmee de rest: **te laat mergen eet de dry run op**. W3 kan pas ná W1
omdat het dezelfde promptbestanden raakt. W4 kan pas als de rest staat.

| Risico | Gevolg | Beheersing |
|---|---|---|
| PR #45 niet gemerged op 16 augustus | W3 en W4 schuiven, geen dry run | Reviewer nu beleggen; anders W3 laten vallen en met W1+W2 het onderzoek in |
| Sleutel niet op de component vóór 18 augustus | W4 kan niet draaien | W0 als eerste oppakken; het is de traagste beslissing buiten je eigen team |
| Respondent typt iets wat de assistent niet aankan | Doodloper midden in de sessie | De tien afdwalingen in W4; PR #45 dekt hier het meeste van af |
| B1 kost nuance | Onjuist beeld van een wettelijke plicht | Guardrails blijven; menselijke beoordeling van de tien antwoorden |

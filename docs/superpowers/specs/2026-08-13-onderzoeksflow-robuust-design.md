# Design: feiten uit de bron in de onderzoeksflow

Status: vastgesteld 2026-08-13
Branch: `feat/onderzoeksflow-verificatie`
Aanleiding: gebruikersonderzoek 25 en 27 augustus 2026

## Context en doel

Het onderzoek van 25 en 27 augustus toetst **of ondernemers deze oplossing
willen**, of dat hun behoefte om iets anders vraagt. Het is geen usability-test
van een product waarover al besloten is.

Dat bepaalt wat "robuust" hier betekent. Elk defect dat de respondent laat
reageren op de *uitvoering* in plaats van op het *idee* is geen schoonheidsfout
maar een meetfout: zijn oordeel gaat dan over iets anders dan de vraag die we
stellen. Ziet een kweker een verkeerd adres van zijn eigen bedrijf, dan
concludeert hij "het klopt niet" en niet "ik wil dit niet" — en dat verschil is
achteraf niet meer uit de opname te halen.

Het doel is dus smal: **wegnemen wat de meting besmet, en niets daarbuiten
polijsten.**

Respondent is Robin Vogel als bloemenkweker bij Kwekerij De Bloesem
(KvK 62345681). Modus `vlam`; `claude` is nu onbruikbaar (zie Nulmeting) en
wordt later toegevoegd.

## Nulmeting

Drie volledige doorlopen van de zes-beurten-flow tegen een draaiende host, met
echte MCP-bronnen en de live RegelRecht-engine
(`services/host/scripts/onderzoeksflow.py`).

| Bevinding | Frequentie | Besmet de meting? |
|---|---|---|
| Verzonnen vestigingsadres in het RVO-rapport | 1 van 3 | ja, fataal |
| Verzonnen of onjuist onderbouwde drempelwaarden | 2 van 3 | ja |
| EML-formulier rendert niet | 1 van 3 | ja |
| Bevestig-deadlock bij indienen | 1 van 3 | ja |
| Taalfouten ("importante", "MaatregelenListe") | elke run | deels |
| Zinnen boven 15 woorden (B1) | 2-3 per run | nee |

De eerste vier zijn intermitterend. Dat is bepalend voor de verificatie: één
groene doorloop zegt bij een foutkans van een derde vrijwel niets.

Los daarvan blokkerend: de Anthropic-sleutel in `.env` heeft geen krediet
(`Your credit balance is too low`). De foutmelding die de gebruiker daarbij
ziet is `LLM_VERZOEK_ONGELDIG` met de actie "Formuleer uw vraag anders" — een
handeling die het probleem nooit oplost.

## Grondoorzaken

**De drempelwaarden bereiken het model nooit.** De engine levert ze wel, maar
alleen op de aanroep met lege parameters:

| aanroep | door wie | `rule_spec.definitions` | `input` |
|---|---|---|---|
| lege parameters | host, voor `GET /regelrecht/drempels` | compleet | leeg |
| gevulde parameters | het model, tijdens de flow | leeg | de gebruikte waarden |

`_simplify_result` vult `drempelwaarden` uitsluitend uit `definitions` en geeft
`input` niet door. Het model doet altijd de tweede aanroep en krijgt dus niets,
terwijl tool-beschrijving én `tool_usage.md` zeggen dat de waarden in het
resultaat staan en dat het geen eigen getallen mag noemen. Die instructie is
niet op te volgen; het gat wordt met verzinsels gevuld.

**Feiten worden naverteld in plaats van gelezen.** Het rapport vóór indiening
vraagt acht feiten (bedrijfsnaam, KvK, adres, gebruiksdoel, woonfunctie,
verbruik, bedrijfskenmerken, berekening). Die kwamen uit tools in beurt 2 en 4;
het rapport volgt in beurt 6. Het model reconstrueert dan uit gespreksgeheugen.
Daar ontstond "Bloemenlaan 12" terwijl de KvK-tool "Hoefweg 210" had geleverd.

**Prompt en frontend-parser spreken elkaar tegen.** `format.md` schrijft
formulieren voor als `- Label: ___ eenheid`. `parseVraag` in
`digitale-assistent.js` slaat regels die met `-` beginnen over en wil genummerde
regels die op `?` eindigen of ` / ` bevatten. Het formulier verschijnt alleen
als het model toevallig van zijn eigen instructie afwijkt.

**Het `answer`-event draagt geen structuur.** Het bevat `has_tools`, `message`,
`mode`, `session_id`, `type`. `vraagSpec` leest `payload.maatregelen` en
`payload.velden` vóór het terugvalt op tekst parsen — de frontend is dus al
gebouwd op een gestructureerd contract dat de backend nooit is gaan vullen.
Tekstparsing is de fallback die permanent aanstaat.

## Uitgangspunt

**Overal waar het model nu feiten navertelt, komen die feiten direct uit de
bron.** Het model verwoordt de uitkomst; het houdt hem niet vast.

Dat is één principe in plaats van vier losse reparaties, en het sluit aan bij wat
de host al doet: `_extract_lopende_zaak` leest het tool-resultaat van
`rvo__indienen` en stuurt een `case`-event dat het model niet aanraakt. Lopende
zaken is daarom altijd correct.

## Deel 1 — het doorgeefluik

In `services/mcp/regelrecht/server.py`, `_simplify_result`, twee velden erbij,
allebei uit de engine en geen lokale kopie:

- **`gebruikte_waarden`** — uit `input`, met de `$`-prefix eraf: de getallen
  waarop déze uitkomst berust.
- **`drempelwaarden`** — uit `definitions`, opgehaald met de lege-parameter-
  aanroep die aantoonbaar werkt. Per wet cachen: de constanten van een wet
  veranderen niet binnen een sessie, en zonder cache kost dit een extra RPC per
  toets.

`tool_usage.md` verwijst daarna naar die twee velden in plaats van naar een veld
dat niet bestaat.

De hardgecodeerde `fallback` in `REGELRECHT_DEFINITIES_ALLOWLIST` blijft
staan als noodpad, maar wordt in de gewone flow niet meer gebruikt. Hij is een
kopie van wetsconstanten die stil kan afdrijven; dat is een bestaand risico dat
dit ontwerp niet vergroot en niet oplost.

## Deel 2 — het model schrijft geen feiten meer, maar slots

Het model construeert geen tekst met feiten erin. Het schrijft plaatshouders, en
de host vult die in uit de bron:

```
model:  "Uw bedrijf {{BEDRIJFSNAAM}} verbruikt {{ELEKTRICITEIT_KWH}} kWh per
         jaar. Dat ligt boven de drempel van {{DREMPEL_ELEKTRICITEIT_KWH}} kWh."

host:   "Uw bedrijf Kwekerij De Bloesem verbruikt 420.000 kWh per jaar. Dat ligt
         boven de drempel van 50.000 kWh."
```

Een feit dat het model nooit schrijft, kan het niet fout schrijven. Dat is
sterker dan de feiten vers in de prompt leggen: dat maakt verzinnen alleen
onwaarschijnlijker.

De winst zit ook in de verificatie. Een fout adres is nu alleen te betrappen
door het met het juiste te vergelijken; een verzonnen waarde als "Bloemenlaan 12"
staat in geen enkele feitenkaart en matcht dus nergens mee. Met slots wordt de
regel structureel — "dit antwoord hoort `{{VESTIGINGSADRES}}` te bevatten" — en
dat vangt ook wat waardevergelijking mist.

### Substitutie in de host, niet in de frontend

De frontend heeft de feiten niet. Daar invullen betekent ze alsnog meesturen
(dus het gestructureerde contract tóch bouwen), plus een wijziging in
`MinBZK/moza-poc`, plus zorgvuldigheid rond `innerHTML`: `digitale-assistent.js`
zet `p.innerHTML = parseMarkdown(text)`, en waarden die daar ongeëscaped in
landen zijn een injectiepad — nu laag risico omdat ze uit onze eigen mocks
komen, maar het is de verkeerde kant op.

De host heeft de feitenkaart al. Eén plek, geen tweede repo, even deterministisch.

### Syntax

`{{SLOT}}`. Niet `[SLOT]`: dat botst met markdown-links, en de frontend parseert
markdown. Niet `___`: dat betekent in `format.md` al "hier vult de gebruiker iets
in", en die twee betekenissen door elkaar halen is vragen om verwarring.

Eén bekende overlap: `MinBZK/moza-poc` is een Eleventy-site en `{{ }}` is
Nunjucks-syntax. Dat botst niet, omdat chatberichten via `parseMarkdown` in de
DOM komen en niet door de templating heen gaan. Het wordt wél een probleem zodra
iemand een assistent-antwoord in een template rendert — vandaar dat de host
substitueert en er nooit een onopgelost slot uitgaat.

### Slotwoordenboek

Vast en gesloten. Elk slot heeft één bron en één weergaveregel; de host formatteert
(duizendtallen, datums, ja/nee), zodat opmaak niet meer per antwoord verschilt.

| bron | slots |
|---|---|
| `kvk__mijn_bedrijf` | `BEDRIJFSNAAM`, `KVK_NUMMER`, `VESTIGINGSADRES`, `VESTIGINGSNUMMER`, `RECHTSVORM`, `WOONFUNCTIE`, `GEBRUIKSDOEL` |
| `netbeheerder__verbruik` | `ELEKTRICITEIT_KWH`, `GAS_M3`, `PEILJAAR`, `NETBEHEERDER` |
| `regelrecht__execute_law` | `DREMPEL_ELEKTRICITEIT_KWH`, `DREMPEL_GAS_M3`, `DREMPEL_ONDERZOEK_ELEKTRICITEIT_KWH`, `DREMPEL_ONDERZOEK_GAS_M3`, `VOLGENDE_DEADLINE`, `RAPPORTAGE_FREQUENTIE_JAREN`, `RAPPORTAGE_METHODE`, `BEVOEGD_GEZAG` |
| `rvo__indienen` | `REFERENTIENUMMER` |

### Oordelen als slot

RegelRecht geeft `heeft_energiebesparingsplicht`, `heeft_informatieplicht` en
`heeft_onderzoeksplicht` al terug. Die worden `OORDEEL_*`-slots die op "wel" of
"niet" resolven, zodat het model schrijft: "De informatieplicht geldt
{{OORDEEL_INFORMATIEPLICHT}} voor uw bedrijf."

Dit is het minst elegante deel van het ontwerp en dat hoort gezegd. Een slot dat
een woord middenin een zin bepaalt maakt de zinsbouw stroef, en het model moet
de zin eromheen zo formuleren dat beide waarden passen. Het alternatief — het
oordeel als vrije tekst laten en achteraf toetsen — laat precies de fout staan
die we in run 1 zagen: juiste conclusie, verkeerde onderbouwing.

### Grenzen

**Het lost verkeerd redeneren niet op, alleen verkeerd onthouden.** Slots dekken
feiten en oordelen. De redenering ertussen ("dat ligt boven de drempel") blijft
tekst van het model.

**Half meedoen is de reële faalmodus.** Het model kan sommige feiten als slot
schrijven en andere letterlijk. Drie regels in de host vangen dat af:

1. Een letterlijke waarde die in de feitenkaart voorkomt is een overtreding.
2. Een slot dat niet opgelost kan worden — bron nog niet geraadpleegd, of een
   naam buiten het woordenboek — is een **harde fout**. `{{VESTIGINGSADRES}}` in
   beeld besmet de meting net zo goed als een fout adres.
3. Het rapport vóór indiening moet de voorgeschreven slots bevatten.

Regel 2 maakt "Verzin GEEN informatie" uit `guardrails.md` voor het eerst
mechanisch: het model kán een feit niet noemen dat het niet heeft.

### Feitenkaart

De substitutie heeft een bron nodig. De host oogst uit elk tool-resultaat de
canonieke feiten, op dezelfde plek waar `_extract_lopende_zaak` nu al meeleest:

| tool | feiten |
|---|---|
| `kvk__mijn_bedrijf` | bedrijfsnaam, KvK-nummer, vestigingsadres, vestigingsnummer, woonfunctie, gebruiksdoel |
| `netbeheerder__verbruik` | elektriciteit, gas, peiljaar, netbeheerder |
| `regelrecht__execute_law` | `gebruikte_waarden`, `drempelwaarden`, `uitkomsten`, bedrijfskenmerken |

Opgeslagen op dezelfde sleutel als `self.conversations`.

De kaart hoeft niet elke beurt de prompt in: het model heeft de wáárden niet
meer nodig, alleen de slotnamen. Wat wél per beurt de prompt in gaat is **welke
slots nu beschikbaar zijn** — dus welke bronnen al geraadpleegd zijn. De
systeemprompt wordt per beurt opnieuw gebouwd (`_system_prompt`) en
`bronnen_offline` is het bestaande precedent voor dynamische toestand die zo de
prompt in gaat.

Dat scheelt ook context: acht feiten per beurt meesturen kost tokens die nu naar
de slotnamen gaan, en die lijst is korter en stabiel.

### Reikwijdte

Slots overal waar een feit valt, niet alleen in het rapport. Het oordeel in
beurt 2 bevat bedrijfsnaam en verbruik en is het eerste dat de respondent leest;
daar een gat laten zou de duurste plek zijn om het over te slaan.

De vereiste-slots-controle (regel 3 hierboven) geldt wél alleen voor het
rapport, omdat daar in `tool_usage.md` vastligt welke velden erin horen. Voor de
andere antwoorden gelden regel 1 en 2.

### Verworpen alternatief

Een live correctie in de host — de foute regel opsporen en vervangen vlak vóór
verzending — is overwogen en verworpen. De host zou dan modeltekst herschrijven
op patroonherkenning, en dat is een nieuwe klasse fouten twaalf dagen voor een
onderzoek. Slots doen hetzelfde werk vooraf en zonder gokken.

## Deel 3 — het maatregelen-formulier deterministisch

De host leest hetzelfde tool-resultaat dat hij al langs ziet komen en hangt de
geldende maatregelen aan het `answer`-event:

```json
{"type": "answer", "message": "…",
 "maatregelen": [{"code": "GC1", "omschrijving": "Pas een klokregeling toe …"}]}
```

`vraagSpec` leest `payload.maatregelen` vóór de tekstfallback. Geen wijziging in
`MinBZK/moza-poc` nodig.

Drie details, elk ervan sloopt het stilletjes:

1. **Veldnaam.** De frontend leest `m.omschrijving || m.titel || m.beschrijving`.
   `_eml_lijst` produceert `naam`. Zonder hermapping toont het formulier kale
   codes zonder tekst.
2. **Filteren op `van_toepassing`.** De engine geeft ook de niet-geldende terug
   (`eml_fe4`, `eml_gd1` op `false`).
3. **Alleen op de juiste beurt.** Het veld hangt er alleen aan als de
   maatregelen-tool in díe beurt een lijst opleverde; anders draagt elk volgend
   antwoord een verouderd formulier mee.

## Deel 4 — verificatie

**Herhaling als acceptatiecriterium.** Tien doorlopen per modus. Bij een
foutkans van een derde mist vijf runs de fout nog in 13 procent van de gevallen;
tien runs in ongeveer 1,7 procent. Eén groene doorloop is geen bewijs.

**Eerst een nulmeting** op de huidige code, zodat we een gemeten foutpercentage
hebben in plaats van een indruk.

`services/host/scripts/onderzoeksflow.py` krijgt erbij:

- **geen onopgelost slot** in enig antwoord — een `{{…}}` op het scherm is een
  even harde fout als een verkeerd feit
- **geen letterlijk feit waar een slot hoort** — elke waarde uit de feitenkaart
  die letterlijk in de tekst staat betekent dat het model het slot omzeild heeft
- **elke ingevulde waarde gelijk aan de bron**, zodat de substitutie zelf ook
  getoetst is en niet alleen het model
- **de vereiste slots in het rapport**, conform `tool_usage.md`
- het `answer`-event draagt `maatregelen` met `code` én `omschrijving`,
  gefilterd op geldend
- de flow haalt het einde: `rvo__indienen`, een `case`-event, "in behandeling"
- per run een regel machineleesbare uitvoer, zodat tien runs te aggregeren zijn

De eerste twee controles vervangen de waardevergelijking uit het vorige ontwerp.
Die kon een verzonnen adres alleen vinden door het met het juiste te vergelijken;
deze twee vangen ook een waarde die nergens vandaan komt.

Een tweede meetlat draait op de **ruwe** modeltekst vóór substitutie. Anders
toetst het script het werk van de host en niet dat van het model, en zie je niet
of het model zich aan de slots houdt.

**Acceptatie:** tien opeenvolgende runs zonder besmettende bevinding.
B1-afwijkingen en taalfouten worden als getal gerapporteerd en blokkeren niet.

## Besluiten

**Persona houdt geen onderzoeksplicht.** De Bloesem raakt met 198.000 m³ gas de
onderzoeksdrempel van 170.000 en krijgt `heeft_onderzoeksplicht: true` — een
zwaardere verplichting waarvoor de assistent geen handelingsperspectief biedt.
Zegt de respondent dan "dit helpt me niet", dan is niet vast te stellen of dat
over de behoefte gaat of over een gat in de implementatie.

Het gasverbruik van 62345681 gaat daarom naar **140.000 m³**: onder de
onderzoeksdrempel, ruim boven de gasdrempel van 25.000, dus de informatieplicht
blijft gelden. De Bloesem is de enige persona met dit probleem; Noon, Roots &
Locks en Vogel Bouwregie blijven onder beide onderzoeksdrempels.

Dit raakt geen frontend-pariteit: `personas.json` bevat geen verbruiksgegevens,
die komen uitsluitend uit de netbeheerder-mock.

**Radioknoppen zijn met een browser bevestigd.** Geen open risico meer.

**Taalfouten wachten op de Claude-sleutel.** Zodra die werkt worden beide modi
gemeten en wordt de moduskeuze een gemeten beslissing in plaats van een aanname.

## Buiten scope

- Gestructureerd rapport-event plus renderer in `MinBZK/moza-poc` (optie C).
- Live correctie van modeltekst door de host.
- De onbegrensde `self.conversations` zonder TTL. De feitenkaart erft dat
  probleem en wordt daarom op dezelfde sleutel gehouden, zodat één
  opruimmechanisme later allebei dekt. Voor een begeleide sessie met een handvol
  gesprekken is het geen probleem, maar het hoort niet stilzwijgend te groeien.
- De misleidende foutmelding bij een LLM-billingfout (`LLM_VERZOEK_ONGELDIG` met
  actie "formuleer uw vraag anders"). Hoort in de foutcatalogus van PDR-011,
  niet in deze branch.

## Te controleren tijdens de implementatie

- `test_demo_personas.py` bevat een drempeltest die is toegevoegd omdat het
  testscript uit elkaar valt als het verbruik onder de drempel zakt. 140.000
  blijft boven 25.000, dus die hoort te slagen — narekenen, niet aannemen.
- De pariteitstest met `MinBZK/moza-poc` moet groen blijven.
- `.env.example` beschrijft 62345681 als "plicht via gas", terwijl De Bloesem ook
  boven de elektriciteitsdrempel van 50.000 kWh zit. Het is plicht via beide. We
  raken die mockdata toch aan voor het gasverbruik, dus de regel gaat mee.

# PDR-011: Foutmeldingen uit één catalogus, met wat er misging én wat je kunt doen

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-08-05 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | [PDR-001](PDR-001-dual-llm-backend.md), [PDR-005](PDR-005-cli-vs-mcp-transport.md), [PDR-009](PDR-009-sessie-identiteit-host-side.md) |

## Context

De host faalde overal op dezelfde manier. Zes agentic loops in `vlam_host.py`
vingen `(TimeoutError, APIError)` af en gaven letterlijk dezelfde zin terug,
of het model nu een time-out had, een 401 op de sleutel gaf of overbelast was:

> "De assistent is op dit moment niet bereikbaar. Controleer uw API-sleutel of probeer het later opnieuw."

Voor de gebruiker verschilt dat wezenlijk: bij een time-out helpt opnieuw
proberen, bij een geweigerde sleutel niet. Hij kon uit de melding niet afleiden
welke van de twee het was.

Daaronder zat hetzelfde patroon. Een falende tool leverde
`f"Fout bij tool '{naam}': {e}"` op als tool-resultaat: het LLM kreeg de rauwe
exception (met bestandspaden en interne URL's) en mocht zelf bedenken wat het
daarover zou vertellen. Een bron die bij het starten niet opkwam bestond
simpelweg niet meer voor het model, dat er dan overheen praatte of terugviel op
eigen kennis. En een vraag buiten het taakgebied werd afgewezen met één vaste
zin zonder enige brug terug naar wat wél kon.

De MCP-servers hadden al wél foutcodes (`SOURCE_UNAVAILABLE`, `NIET_GEVONDEN`,
`INPUT_INVALID`, `ONTBREKEND_VELD`, `EXECUTION_ERROR`); de host deed er alleen
niets mee.

Voor het gebruikersonderzoek is dat het kernprobleem: een deelnemer die
vastloopt op "er ging iets mis" levert geen bruikbare observatie op. We willen
weten of mensen de assistent begrijpen, niet of ze een generieke foutmelding
kunnen raden.

## Beslissingen

### 1. Eén catalogus, in code, met bericht én actie gescheiden

Alle meldingen staan in `services/host/errors.py` als `FoutMelding`-objecten met
een `code`, een `bericht` (wat er gebeurde) en een `actie` (wat de gebruiker nu
kan doen). De splitsing is niet cosmetisch: ze dwingt af dat elke melding een
handelingsperspectief heeft. Een test faalt op een melding zonder `actie`.

Alternatief overwogen: de teksten in de systeemprompt zetten en het model laten
formuleren. Verworpen omdat het model juist níét beschikbaar is in precies de
gevallen die het vaakst misgaan (time-out, geweigerde sleutel, overbelasting).

### 2. Classificeren op exceptie-type, niet op tekst

`classificeer_llm_fout` mapt SDK-excepties op codes: `APITimeoutError` naar
`LLM_TIMEOUT`, `AuthenticationError` naar `LLM_SLEUTEL_ONGELDIG`,
`RateLimitError` naar `LLM_TE_DRUK`, enzovoort — voor beide SDK's, die dezelfde
klassenamen in hun eigen namespace gebruiken. Foutteksten van een aanbieder
veranderen zonder aankondiging; typen niet. Alleen bij een `BadRequestError`
kijken we wél naar de tekst, omdat "context te lang" en "ongeldige parameter"
hetzelfde type delen maar een ander advies verdienen.

De `except`-clausules zijn tegelijk verbreed van `(TimeoutError, APIError)` naar
`Exception`. Een fout die daarbuiten viel (bijvoorbeeld een
`UnicodeEncodeError`) gaf een onafgevangen 500 of een afgebroken SSE-stream:
geen melding, maar een doodlopende UI.

### 3. Het LLM krijgt een instructie, geen exception

Bij een mislukte bron-aanroep krijgt het model een JSON-resultaat met
`gebruikersmelding` (de kant-en-klare zin) en `instructie` ("geef dit letterlijk
door, verzin geen gegevens"). De exception-tekst blijft in de log.

Waar de bron zélf een foutcode teruggeeft, verrijken we het antwoord in plaats
van het te vervangen: RegelRecht meldt in `ontbrekende_gegevens` welke feiten
het model nog aan de gebruiker moet vragen, en die informatie is nodig om verder
te kunnen. Het technische `message`-veld van de bron gaat er wel uit.

Dit lost meteen een openstaande bevinding op: de host gaf exception-inhoud door
aan het LLM, dat het aan de gebruiker kon doorvertellen.

### 4. Het model weet welke bronnen eruit liggen

`server_status` wist al welke MCP-server niet opkwam, maar die kennis bereikte
het model niet. De systeemprompt krijgt nu een blok
(`prompts/blocks/shared/bronnen_status.md`) met de uitgevallen bronnen, hun
gebruikersnaam en het alternatief — alleen als er iets uitligt. De CLI-paden
geven een lege lijst mee: die gebruiken een ander transport, dus de MCP-status
zegt daar niets.

### 5. Afwijzen mag, doodlopen niet

Voor "de vraag valt buiten het taakgebied" en "de vraag is onduidelijk" bestaat
geen codepad — het model formuleert. Daarom staat het in de prompt, in de vorm
van een patroon (benoem het herkende onderwerp, zeg dat het buiten het taakgebied
valt, geef een concrete voorbeeldvraag die wél kan) plus twee few-shot
voorbeelden, die in deze codebase het sterkste stuursignaal zijn.

### 6. Het SSE-contract blijft achterwaarts compatibel

Het `error`-event krijgt `code`, `bericht`, `actie`, `bron` en `herstelbaar`
erbij. Het bestaande `message`-veld blijft de volledige zin, zodat de huidige
frontend zonder wijziging blijft werken. Een mislukte bron midden in een gesprek
levert een nieuw `bron_fout`-event op; onbekende event-types worden door de
frontend genegeerd, dus dat kan vooruitlopen op de UI-wijziging.

## Consequenties

- (+) Elk foutscenario heeft een eigen melding met handelingsperspectief; een
  test bewaakt dat elke code die een bronserver uitstuurt in de catalogus staat.
- (+) Geen paden, URL's of exception-teksten meer richting gebruiker of LLM.
- (+) De UI kan op `code` en `herstelbaar` sturen (retry-knop, bron-badge).
- (-) De catalogus is een tweede plek die bijgewerkt moet worden als een bron een
  nieuwe foutcode introduceert. De broncode-scan in
  `tests/test_foutmeldingen_catalogus.py` maakt dat een falende test in plaats
  van een stille regressie.
- (-) De meldingen zijn Nederlands en niet vertaalbaar. Bewust: de hele assistent
  is eentalig; meertaligheid is een apart vraagstuk.
- (-) "Probeer het over een minuut opnieuw" is een schatting, geen berekende
  wachttijd. `Retry-After`-verwerking valt buiten dit ticket (zie BETA-04).

## Wat dit niet oplost

Het systematisch beproeven van élke bron bij uitval blijft **MVP-09**; dit PDR
levert het mechanisme en de meldingen, niet de volledige uitvaltest.

## Bijlage: het contract voor de frontend

De UI-kant is een apart ticket in
[`MinBZK/moza-poc`](https://github.com/MinBZK/moza-poc). Deze bijlage is het
contract waar dat ticket op kan bouwen.

### Het `error`-event

```json
{
  "type": "error",
  "code": "LLM_TIMEOUT",
  "message": "Het opstellen van het antwoord duurde langer dan 60 seconden. Probeer het opnieuw, of stel uw vraag korter en concreter.",
  "bericht": "Het opstellen van het antwoord duurde langer dan 60 seconden.",
  "actie": "Probeer het opnieuw, of stel uw vraag korter en concreter.",
  "bron": null,
  "herstelbaar": true
}
```

`message` is `bericht` + `actie` en blijft gevuld, zodat de huidige frontend
zonder wijziging blijft werken. `bron` is de servernaam (`kvk`, `koop`,
`regelrecht`, `rvo`, `netbeheerder`) of `null`.

### Het `bron_fout`-event

Zelfde vorm, `type: "bron_fout"`. Verschil: dit is **geen** eindpunt van het
gesprek. Een bron viel uit terwijl de assistent doorwerkt; het `answer`-event
volgt daarna gewoon. Bedoeld om inline te tonen ("KOOP is even niet bereikbaar")
zonder de chat af te breken. Onbekende event-types worden door de huidige
frontend genegeerd, dus dit kan vooruitlopen op de UI-wijziging.

### Wat de UI ermee kan

- **`herstelbaar: true`** → toon een "probeer opnieuw"-knop die het laatste
  bericht opnieuw verstuurt. Bij `false` heeft dat geen zin (ongeldige sleutel,
  lege vraag, bron niet gestart) en hoort de knop weg te blijven.
- **`bron`** → toon bij welke bron het misging, in dezelfde bewoording als de
  databronnen-weergave.
- **`code`** → stem de bestaande generieke `catch`-fallbacks in
  `assets/javascript/digitale-assistent.js` erop af. Die vangen nu alleen
  HTTP-statussen af; met een `code` in het event kan de melding uit de backend
  komen in plaats van uit een tweede, parallel onderhouden lijst in de frontend.
- **`bericht` / `actie` apart** → de actie kan visueel apart, bijvoorbeeld als
  knop of als tweede regel, in plaats van als één lap tekst.

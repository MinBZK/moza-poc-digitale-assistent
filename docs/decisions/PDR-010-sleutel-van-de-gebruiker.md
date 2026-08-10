# PDR-010: De LLM-sleutel komt van de gebruiker, niet van de server

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-08-03 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | [PDR-001](PDR-001-dual-llm-backend.md), [PDR-007](PDR-007-demo-persona-en-netbeheerder-bron.md), [PDR-009](PDR-009-sessie-identiteit-host-side.md) |

## Context

De host praat met twee LLM-backends (PDR-001) en heeft daarvoor een API-sleutel
nodig. Er zijn twee plekken waar die vandaan kan komen: de server-omgeving, of
de gebruiker zelf via de UI (de headers `x-vlam-api-key` / `x-claude-api-key`,
achter de vlag `ALLOW_API_KEY_OVERRIDE`).

De draaiende deployment gebruikt sinds het begin de tweede route: er staat geen
enkele LLM-sleutel op de ZAD-component, alleen `ZAD_API_KEY` voor de deploy zelf
(`.github/workflows/production.yml`). Die keuze stond tot nu toe alleen in
workflow-commentaar, niet in een PDR — terwijl het wel degelijk een beslissing
met gevolgen is.

Aanleiding om het alsnog vast te leggen: ticket **MVP-02**. De eerste lezing van
dat ticket was "zet de override uit, sleutels horen op de server". Een evaluatie
van de bestaande code liet zien dat dat de zaak zou verplaatsen in plaats van
oplossen, en drie concrete gaten in de huidige uitvoering blootlegde die er los
van staan.

## Beslissing

### 1. De sleutel blijft van de gebruiker komen

Geen gedeelde server-sleutel voor de gesloten testgroep. Redenen:

- **Geen gedeelde pot om leeg te trekken.** Met een server-sleutel wordt "wie de
  host kan bereiken, verbruikt onze sleutel" het nieuwe risico. De host heeft
  geen rate limiting en geen authenticatie op `/chat`; de enige grenzen zijn de
  internal-only deployment en de `X-Test-User`-allowlist uit PDR-009 — en die
  header is geen geheim, de KvK-nummers staan publiek in de frontend.
- **De kosten liggen waar het gebruik ligt.** Elke tester brengt zijn eigen
  sleutel mee.
- **Er staat geen secret op een PoC-deployment.** Niets te roteren, niets te
  lekken bij een misconfiguratie van de component.

De server-env-route blijft wél bestaan en werkt ongewijzigd (lokaal draaien, en
een eventuele latere omslag). Staat er een server-sleutel én stuurt de client er
een mee, dan wint die van de client, per verzoek.

### 2. Een sleutel leeft precies één verzoek

De host maakt per verzoek een eigen LLM-client aan en sluit die na afloop. Geen
sleutel in gedeelde state, geen sleutel die het verzoek overleeft.

Dit was het echte gat. `chat`/`chat_stream` zetten de per-verzoek client op
`self.claude_client` / `self.vlam_client` en herstelden die in een `finally`.
De host is één gedeeld object en de endpoints zijn async: bij twee gelijktijdige
gesprekken kon de sleutel van gebruiker A het verzoek van gebruiker B bedienen
en daarna procesbreed blijven staan. `tests/test_key_isolation.py` reproduceert
dat en faalt op de oude implementatie.

### 3. Een sleutel wordt op vorm getoetst vóór gebruik

`_validate_api_key` in `api.py` weigert waarden die niet-ASCII zijn, stuurtekens
of witruimte bevatten, of buiten een redelijke lengte vallen. `/chat` antwoordt
met 400, `/chat/stream` met een `error`-event. De melding en de logregel noemen
alleen de headernaam en de reden, nooit iets van de waarde.

### 4. Kindprocessen krijgen geen LLM-sleutel

MCP-servers én CLI-wrappers draaien met een env-allowlist
(`subprocess_env.py`). Geen van beide heeft een LLM-sleutel nodig.

### 5. Een logging-vangnet, expliciet als tweede linie

`log_redaction.py` redigeert herkenbare sleutelvormen uit alles wat naar een
log-handler gaat, inclusief tracebacks. Bewust geen entropie-heuristiek — die
zou tool-resultaten, KvK-nummers en sessie-ID's raken. Een sleutel in een
onbekend formaat komt er dus doorheen; dit vervangt beslissing 2 t/m 4 niet.

Daarnaast kent het vangnet de sleutels van het lopende verzoek bij naam, en
daar geldt een vormeis: minstens 20 tekens, met zowel een cijfer als een letter.
Zonder die eis wordt "een sleutel opgeven" een manier om gewone logtekst te
laten verdwijnen. `api._validate_api_key` hangt zijn ondergrens daarom aan
diezelfde constante (`MIN_UNTRUSTED_SECRET_LENGTH`): wat de voordeur accepteert,
is registreerbaar. Stonden de twee drempels los, dan liepen ze uit elkaar en
ontstond er stil een gat. Wat overblijft is een sleutel zónder cijfer: die werkt,
maar valt buiten het vangnet — en dat wordt bij aanvaarding als `WARNING` gemeld
in plaats van stil geaccepteerd.

## Alternatieven overwogen

**Server-sleutel, override helemaal verwijderen.** De oorspronkelijke lezing van
MVP-02. Verworpen omdat het het risico verplaatst (zie hierboven) en omdat het
de deployment zou breken: er staat geen secret op de component, dus dat moet er
eerst bij. Blijft een reële optie zodra er authenticatie op `/chat` zit
(BETA-02); dan verandert de afweging wezenlijk.

**Sleutel-override achter een dev-only vlag.** Klinkt strenger dan het is: de
gedeelde-state-bug uit beslissing 2 zou blijven bestaan zolang iemand de vlag
kan aanzetten. Bovendien is de "dev"-omgeving hier precies de omgeving waarin de
testgroep werkt.

**Clients cachen op een hash van de sleutel.** Zou de TLS-handshake per verzoek
besparen. Verworpen: dan houd je gebruikerssleutels in geheugen tussen verzoeken
in, wat beslissing 2 juist ondergraaft. Voor een PoC weegt de handshake niet op
tegen die eigenschap.

**Sleutel in een server-side sessie parkeren** (één keer invoeren, daarna in de
host bewaren). Comfortabeler voor de tester, maar het maakt van de host een
sleutelbewaarplaats met alle gevolgen van dien (levensduur, opruimen, geheugen,
crashdumps). Niet passend voor een PoC zonder secret store.

## Consequenties

**Geaccepteerde restrisico's** — inherent aan deze opzet, niet weg te
programmeren in de host:

- De sleutel reist door de browser van de gebruiker en over het netwerk naar de
  host. Afgedekt met HTTPS, een strikte origin-grens en opslag alleen in de
  browsersessie.
- De gebruiker plakt zijn sleutel in een webformulier. Dat vraagt om een
  duidelijke waarschuwing in de UI en om een sleutel met beperkte rechten;
  beide horen bij de frontend (`MinBZK/moza-poc`).
- Het vangnet in `log_redaction.py` dekt bekende sleutelvormen, geen willekeurige.

**Gevolgen voor de code:**

- `ALLOW_API_KEY_OVERRIDE` houdt default `true`. Dat is hier géén losse
  security-default maar de dragende aanname van de deployment; `false` betekent
  dat er een server-sleutel moet staan.
- De LLM-client gaat als verplicht argument door de `_chat_*`-paden. Een nieuw
  dispatch-pad moet die meekrijgen — er is bewust geen terugval op een gedeelde
  client, zodat een vergeten argument meteen breekt in plaats van stilletjes de
  verkeerde sleutel te gebruiken.
- Bij `ALLOWED_ORIGINS=*` waarschuwt de host bij het opstarten.

**Wanneer dit PDR herzien moet worden:** zodra `/chat` echte authenticatie krijgt
(BETA-02) of de assistent buiten een gesloten testgroep gebruikt wordt. Dan is
een server-sleutel met rate limiting per geauthenticeerde gebruiker
waarschijnlijk de betere kant op.

## Addendum (2026-08-10): tijdelijke serversleutel voor het gebruikersonderzoek

Voor het gebruikersonderzoek van **25 en 27 augustus 2026** wijkt de deployment
tijdelijk af van beslissing 1.

De ondernemers die meedoen werken in hun eigen browser op hun eigen machine. Hun
een sleutel laten invoeren betekent dat we die aan onderzoeksdeelnemers geven:
ze zien hem, en de frontend bewaart hem in `localStorage` — dus hij blijft na de
sessie in hun browser achter, ook nadat de schermopname gewist is. Dat is precies
het risico dat dit PDR wilde vermijden, en het gaat bovendien in tegen de eigen
spelregel hierboven ("nooit `localStorage`").

In dat venster geldt daarom: een **aparte Anthropic-sleutel met spend limit** op
de ZAD-component, en `ALLOW_API_KEY_OVERRIDE=false`, zodat de sleutel-headers
genegeerd worden en niemand iets hoeft in te voeren.

**Geaccepteerd restrisico.** `/chat` heeft geen authenticatie, dus wie de host
bereikt verbruikt deze sleutel. Draagbaar omdat de backend internal-only is en
het venster twee dagen beslaat. Het is nadrukkelijk niet de stand daarbuiten.

**Intrekken.** De sleutel wordt na 27 augustus 2026 ingetrokken en
`ALLOW_API_KEY_OVERRIDE` gaat terug naar `true`. Zolang dat niet gebeurd is,
staat er een gedeelde sleutel op een onauthenticeerde host — dan is dit geen
tijdelijke afwijking meer maar een stille verslechtering.

**Nog te wegen restrisico, los van dit venster.** Met een eigen sleutel loopt het
gesprek via het provideraccount van de tester: zonder verwerkersovereenkomst met
BZK en zonder zicht op retentie of training-opt-out. Bij fictieve data
ongevaarlijk, maar het is een reëel gevolg van de architectuurkeuze. Zie het
"LLM-knelpunt" in `docs/preparation/kvk-gegevens.md`.

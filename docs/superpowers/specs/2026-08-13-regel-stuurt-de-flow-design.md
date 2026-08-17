# Design: de regel stuurt de flow, de host routeert, het model converseert

Status: deel 1 goedgekeurd 2026-08-13; deel 2 t/m 5 ingevuld door de uitvoerder
Branch: `feat/herkomst-zichtbaar` (afgetakt van `feat/onderzoeksflow-verificatie`)
Voorganger: `2026-08-13-onderzoeksflow-robuust-design.md`

## Aanleiding

Toetsing van de vorige branch tegen de RegelRecht-filosofie
(https://regelrecht.rijks.app/) legde drie dingen bloot.

**De herkomst van een waarde verdwijnt.** Elke MCP-server verpakt zijn antwoord
als `{"data": …, "provenance": {source, timestamp, version}}` — §4.1 van de
MCP-standaard. `feiten_uit_tool` leest `.get("data")` en laat de provenance
vallen. Een waarde in de feitenkaart is daarna naam→waarde zonder bron.

**Er zijn drie kopieën van dezelfde wetsconstanten.** De engine is
gezaghebbend; daarnaast staat `REGELRECHT_DEFINITIES_ALLOWLIST["fallback"]` in
de host en `KWH_GRENS = 50000` / `GAS_GRENS = 25000` in
`digitale-assistent.js`. Het endpoint `GET /regelrecht/drempels`, dat volgens
zijn eigen docstring bestaat als "één bron van waarheid ... voor frontend
CTA-gating", wordt nergens aangeroepen. De frontend vertelt de ondernemer dus
"boven de grens van 50.000" op gezag van een eigen constante.

**Een lokale kopie doet zich voor als de wet.** `_eml_fallback` in de
regelrecht-MCP-server geeft dezelfde vorm terug als de engine, zonder enige
markering. Valt de engine weg, dan presenteert de assistent onze kopie als de
regel. Dat botst met "de juridische geldigheid blijft bij de oorspronkelijke
wetgeving".

En één gat dat de vorige branch miste: **feiten die de ondernemer zelf aanlevert
hebben geen bron.** De twee vragen over koel- en afzuiginstallatie gaan van de
chat rechtstreeks in `rvo__indienen` als `bedrijfskenmerken`. Er is geen
oogster, geen slot, geen herkomst. De frontend heeft ze wél gestructureerd — de
respondent klikt radioknoppen — maar `digitale-assistent.js` slaat ze plat:

```js
// Vraag-formulier: stel het antwoord samen en stuur het als chatbericht terug.
var bericht = "Mijn antwoorden: " + delen.join("; ") + ".";
```

## Uitgangspunten

Van de opdrachtgever, en ze sturen alles hieronder:

1. **Waarden komen uit RegelRecht** voor drempels, berekeningen en oordelen.
   Situatie-specifieke gegevens komen uit KvK, de Business Wallet, of van de
   ondernemer zelf.
2. **RegelRecht wordt zo vroeg mogelijk ingezet.**
3. **Zo min mogelijk stappen die het model bepaalt.**

Punt 2 en 3 samen zijn een architectuurwijziging, geen aanpassing: de regel
gaat de flow sturen.

## Deel 1 — de orkestratielus (goedgekeurd)

De engine declareert zelf wat hij mist, laag voor laag. Nagemeten tegen de live
engine op 2026-08-13:

| aanroep | requirements_met | mist |
|---|---|---|
| `{}` | false | `KVK_NUMMER`, `IS_WOONFUNCTIE` |
| `+ KVK_NUMMER, IS_WOONFUNCTIE` | false | `JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH`, `JAARLIJKS_GASVERBRUIK_M3` |
| `+ verbruik` | true | — (uitkomst volgt) |

De host krijgt daarom een lus die vóór het model draait:

```
1. roep de wet aan met wat we al hebben (eerste keer: niets)
2. requirements_met? -> klaar, uitkomst beschikbaar
3. anders: welke velden mist hij?
4. per veld, volgens de routeringstabel:
     automatisch beschikbaar        -> ophalen, terug naar 1
     vraagt toestemming             -> stoppen, model laat toestemming vragen
     alleen de ondernemer weet het  -> stoppen, model laat het formulier tonen
```

De lus draait door zolang hij zelf verder kan. Bij het eerste verzoek haalt de
host het KvK-nummer uit de sessie en de woonfunctie uit de BAG-verrijking, en
stopt waar toestemming nodig is. Het model komt pas in beeld om te vrágen.

**De toestemmingspoort blijft.** De aanroep met lege parameters raakt geen
persoonsgegevens; dat is een wet die zichzelf beschrijft. Zodra de lus verbruik
nodig heeft, geldt PDR-008 onverkort: geen bron vóór akkoord. Die controle staat
op 5/5 en mag niet zakken.

**Het model hoort via de prompt wat het moet vragen.** De host zet de openstaande
behoefte per beurt in de systeemprompt, naast `bronnen_status.md` — hetzelfde
precedent als `bronnen_offline`. Het model krijgt de vraagtekst aangereikt in
plaats van hem uit een tool-resultaat te vissen.

## Deel 2 — de routeringstabel en herkomst

*Ingevuld door de uitvoerder; niet vooraf goedgekeurd.*

Eén tabel in de host, expliciet en op één plek, zodat de latere uitbreiding naar
een tweede wet daar landt en niet door de code verspreid raakt:

| veld | bron | soort | toestemming nodig |
|---|---|---|---|
| `KVK_NUMMER` | sessie (`X-Test-User`) | identiteit | nee |
| `IS_WOONFUNCTIE` | `kvk__mijn_bedrijf` (BAG-verrijking) | registratie | nee |
| `JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH` | `netbeheerder__verbruik` | attestatie | **ja** |
| `JAARLIJKS_GASVERBRUIK_M3` | `netbeheerder__verbruik` | attestatie | **ja** |
| `HEEFT_KOELINSTALLATIE` | de ondernemer, via het formulier | opgave | n.v.t. |
| `HEEFT_AFZUIGINSTALLATIE` | de ondernemer, via het formulier | opgave | n.v.t. |

**Herkomst wordt niet meegedragen maar afgeleid.** Een feit ontstaat op het
moment dat de host een bron raadpleegt; de bron is er dan per definitie bij. Dat
lost het probleem structureel op in plaats van met een tweede dict die kan
uitlopen — precies hoe de provenance de eerste keer verdween.

Een feit wordt daarom `{"waarde": …, "bron": …, "soort": …}`. `vul_slots` leest
`waarde`; de rapportweergave (deelproject A) leest de rest.

**Waarom `soort` erbij.** Het onderscheidt een wetsconstante van een opgave van
de ondernemer van een registratie. Deelproject A heeft dat nodig om per waarde
het juiste te tonen ("afgegeven door", "opgegeven door u", "uit de regel"), en
het maakt zichtbaar dat "koelinstallatie: ja" geen uitspraak van RegelRecht is.

**Wat er níét in de tabel staat, komt er niet in.** Vraagt de wet een veld dat de
tabel niet kent, dan stopt de lus en meldt de host dat expliciet in de log. Geen
raden, geen doorschuiven naar het model.

## Deel 3 — antwoorden van de ondernemer als data

*Ingevuld door de uitvoerder; niet vooraf goedgekeurd.*

De frontend heeft de antwoorden gestructureerd en gooit ze weg. Het contract
krijgt er een optioneel veld bij op `POST /chat/stream`:

```json
{"message": "…", "session_id": "…", "mode": "vlam",
 "opgaven": {"HEEFT_KOELINSTALLATIE": true, "HEEFT_AFZUIGINSTALLATIE": false}}
```

De host neemt die op in de feitenkaart met bron "de ondernemer" en soort
"opgave", vóórdat de orkestratielus draait. Daarmee is een opgave toerekenbaar
aan wie hem deed, in plaats van aan het model dat een zin interpreteerde.

**Terugvalpad.** Zolang de frontend nog geen `opgaven` stuurt, blijft de huidige
route werken: het model leest de antwoorden uit het chatbericht en geeft ze mee
aan de wet. Die waarden krijgen dan bron "model, uit het gesprek" — expliciet
zwakker gelabeld, zodat het verschil zichtbaar is in plaats van weggepoetst.

**De frontend-kant hoort erbij.** `digitale-assistent.js` stuurt de
formulierantwoorden als `opgaven` mee in plaats van ze plat te slaan tot een
zin. Dat gebeurt in `MinBZK/poc-moza`, een tweede repo op een eigen branch:
commits daar blijven lokaal tot iemand ze heeft gezien.

## Deel 4 — de drie kopieën

*Ingevuld door de uitvoerder; niet vooraf goedgekeurd.*

**`_eml_fallback` maakt zich kenbaar.** Hij geeft nu dezelfde vorm terug als de
engine. Er komt een expliciet veld bij dat zegt dat dit een lokale kopie is en
dat RegelRecht niet bereikbaar was, en de prompt draagt het model op dat te
melden. Een respondent hoort te weten wanneer hij naar onze weergave van de
regel kijkt in plaats van naar de regel.

**De drempelwaarden-fallback in de host blijft**, ongewijzigd, met dezelfde
labeling die er al is (`bron: "lokale fallback (RegelRecht niet beschikbaar)"`).
Hij wordt in de gewone flow niet gebruikt.

**De frontend-constanten verdwijnen.** `KWH_GRENS = 50000` en
`GAS_GRENS = 25000` in `digitale-assistent.js` worden vervangen door een
ophaal uit `GET /regelrecht/drempels` — het endpoint dat daar al voor bestaat en
nooit is aangeroepen. Faalt die ophaal, dan toont de wallet-kaart de waarden
zonder grensvergelijking in plaats van met een grens uit eigen code: liever geen
oordeel dan een oordeel op eigen gezag.

## Deel 5 — verificatie

*Ingevuld door de uitvoerder; niet vooraf goedgekeurd.*

`services/host/scripts/onderzoeksflow.py` bestaat en meet de flow end-to-end. Die
blijft de maatstaf; de eindmeting van de vorige branch is het ijkpunt.

Eisen aan deze branch:

- Elke bestaande controle blijft op zijn huidige score. Zakt er één, dan is dat
  een regressie en geen detail. Met name: geen bron vóór toestemming (5/5),
  geen onopgelost slot (10/10), rapport bevat bedrijfsnaam, verbruik en adres
  (5/5 elk).
- Nieuw: elk feit in de kaart heeft een bron en een soort.
- Nieuw: de wet is aangeroepen vóór enige andere bron.
- Nieuw: geen enkel veld is aan de wet meegegeven dat niet uit de
  routeringstabel komt.
- Vijf runs, met de escalatieregel uit de vorige spec: blijft één controle
  wisselvallig, dan tien runs voor díe controle.

## Buiten scope

- Deelproject A: het gestructureerde rapport-event met een renderer die per
  waarde de bron toont. Dit ontwerp levert de gegevens die A nodig heeft.
- Een generieke routeringstabel voor meerdere wetten. Bewust één wet nu; de
  tabel staat als aparte eenheid zodat de uitbreiding daar landt.
- De onbegrensde `self.conversations`/`VLAMHost.feiten` zonder TTL.

## Openstaande bevindingen die deze branch erft

Uit `NEXT_STEPS.md`, MVP-13: de statische slotlijst, de onuitvoerbare actie bij
`ANTWOORD_ONVOLLEDIG`, `_OORDELEN` dat `None` niet wegfiltert, twee van drie
`OORDEEL_`-slots die nergens gedemonstreerd worden, en de twee nooit gebouwde
spec-regels tegen "half meedoen". Geen daarvan blokkeert dit ontwerp.

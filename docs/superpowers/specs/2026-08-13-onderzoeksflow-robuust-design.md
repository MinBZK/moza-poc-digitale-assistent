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

## Deel 2 — feiten uit de bron, elke beurt

**Feitenkaart per sessie.** De host oogst uit elk tool-resultaat de canonieke
feiten, op dezelfde plek waar `_extract_lopende_zaak` nu al meeleest:

| tool | feiten |
|---|---|
| `kvk__mijn_bedrijf` | bedrijfsnaam, KvK-nummer, vestigingsadres, vestigingsnummer, woonfunctie, gebruiksdoel |
| `netbeheerder__verbruik` | elektriciteit, gas, peiljaar, netbeheerder |
| `regelrecht__execute_law` | `gebruikte_waarden`, `drempelwaarden`, `uitkomsten`, bedrijfskenmerken |

Opgeslagen op dezelfde sleutel als `self.conversations`.

**Elke beurt terug de prompt in**, als samengesteld blok naast
`bronnen_status.md`. De systeemprompt wordt per beurt opnieuw gebouwd
(`_system_prompt`), en `bronnen_offline` is het bestaande precedent voor
dynamische toestand die zo de prompt in gaat.

De promptregel wordt scherper dan "toon de bekende gegevens": neem deze waarden
letterlijk over, en staat een waarde er niet bij, zeg dan dat je hem niet hebt.
Dat is wat `guardrails.md` al eist met "Verzin GEEN informatie", nu met een bron
om het aan op te hangen.

**Grens van deze maatregel.** Dit haalt de gemeten oorzaak weg — reconstructie
uit een lang gesprek — maar maakt verzinnen niet onmogelijk. Volledig dichtzetten
vraagt dat de feiten niet meer door het model heen gaan, en dat is een
gestructureerd rapport-event met een nieuwe renderer in `MinBZK/moza-poc`.
Bewust niet nu: een frontend-wijziging die niemand vóór 25 augustus in een
browser heeft gezien is een groter risico dan wat het wegneemt.

Een live correctie in de host — de foute regel vervangen vlak vóór verzending —
is overwogen en verworpen. De host zou dan modeltekst herschrijven op
patroonherkenning, en dat is een nieuwe klasse fouten twaalf dagen voor een
onderzoek.

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

- elk feit in het antwoord tegen de feitenkaart (adres doet dat al; verbruik,
  KvK-nummer, bedrijfsnaam en vestigingsnummer erbij)
- elk getal in de berekening moet voorkomen in `drempelwaarden` of
  `gebruikte_waarden` — dat vangt ook een verzonnen drempel die toevallig klopt
- het `answer`-event draagt `maatregelen` met `code` én `omschrijving`,
  gefilterd op geldend
- de flow haalt het einde: `rvo__indienen`, een `case`-event, "in behandeling"
- per run een regel machineleesbare uitvoer, zodat tien runs te aggregeren zijn

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
- `.env.example` beschrijft 62345681 als "plicht via gas", terwijl De Bloesem met
  420.000 kWh ook boven de elektriciteitsdrempel zit. Onjuist maar onschadelijk;
  meenemen als het toch geraakt wordt.
- De misleidende foutmelding bij een LLM-billingfout (`LLM_VERZOEK_ONGELDIG` met
  actie "formuleer uw vraag anders"). Hoort in de foutcatalogus van PDR-011,
  niet in deze branch.

## Te controleren tijdens de implementatie

- `test_demo_personas.py` bevat een drempeltest die is toegevoegd omdat het
  testscript uit elkaar valt als het verbruik onder de drempel zakt. 140.000
  blijft boven 25.000, dus die hoort te slagen — narekenen, niet aannemen.
- De pariteitstest met `MinBZK/moza-poc` moet groen blijven.

# PDR-016: Uitleg in gewone taal komt uit de beslisgraaf, als eigen dienst naast het gesprek

| Veld | Waarde |
|---|---|
| Status | Voorgesteld |
| Datum | 2026-10-20 |
| Beslisser(s) | Projectteam Digitale assistent 2.0 |
| Gerelateerd | [PDR-009](PDR-009-sessie-identiteit-host-side.md) (sessie), [PDR-010](PDR-010-sleutel-van-de-gebruiker.md) (sleutel per verzoek), [PDR-011](PDR-011-foutmeldingen-catalogus.md) (foutcatalogus), [PDR-013](PDR-013-timeoutgrenzen-op-basis-van-meting.md) (grenzen en herkansingen); de koerswijziging in PDR-014 (chat geparkeerd) |

## Context

De Digitale assistent 2.0 vult een aanvraag vooraf in en laat de
regelrecht-engine de uitkomst berekenen. Het portaal (moza-portaal, route
`personeel/iemand-aannemen`) toont bij elke uitkomst "Waarom deze uitkomst?",
afgeleid uit de uitvoering: de beslissende voorwaarden, de motivering per
artikel en de volledige afleiding, zonder taalmodel. Die tekst is trouw aan de
wet, maar ambtelijk ("het college heeft vastgesteld dat").

Bos, Schuth en Chen, *From Rules as Executed to Citizen Explanation* (JURIX
2026), vergeleken drie manieren om zo'n uitvoering aan een burger uit te
leggen: een vrij prompt, een platte lijst feiten en een getypeerde
beslisgraaf met een beperkt prompt. De graaf-variant hield de uitleg het
best trouw aan de uitvoering, en het paper waarschuwt dat begrijpelijk niet
hetzelfde is als juridisch juist.

Het portaal bouwde die graaf-variant eerst zelf: het prompt stond in de
frontend en ging als gewoon chatbericht naar `/chat` met `mode: "claude"`.
Dat werkt, maar het prompt leeft dan in de verkeerde laag (het portaal weet
niets van modellen), de toets achteraf ontbreekt, en een tweede afnemer (een
ander portaal, een script voor het gebruikersonderzoek, een agent) zou het
prompt moeten kopiëren.

## Beslissing

1. **Uitleg is een eigen dienst van de host, geen gesprek.** `POST /uitleg`
   neemt een beslisgraaf (`afleiding.uitkomst` uit de kern van
   regelrecht-uitleg), de naam van de regeling en de korte samenvatting van de
   kern, en geeft één tekst terug. Geen gespreksgeschiedenis, geen tools, geen
   bronnen: het model krijgt uitsluitend de graaf en het systeemprompt in
   `services/host/uitleg.py`. Sessie en sleutel werken als bij `/chat`
   (PDR-009, PDR-010); grenzen, levensteken en herkansingen komen uit dezelfde
   `_llm_aanroep` (PDR-013); fouten uit de catalogus (PDR-011), met twee nieuwe
   codes: `UITLEG_GRAAF_ONGELDIG` en `UITLEG_GRAAF_TE_GROOT`.
2. **De graaf blijft de toetssteen.** De dienst toetst het antwoord
   deterministisch tegen de graaf en geeft de uitkomst mee (`toets`): elk
   bedrag en elk percentage in de tekst moet in de graaf staan, het
   wetsartikel moet genoemd zijn, en de leesbaarheid wordt gemeten
   (`taalniveau.meet`, een vormmaat). Een afgekeurde tekst gaat wél terug,
   met `geslaagd: false`: de afnemer beslist wat hij toont. Zo kan het
   gebruikersonderzoek ook meten hoe vaak het model afwijkt.
3. **De deterministische afleiding blijft in de kern (Rust) en blijft
   leidend.** De taalmodeltekst is een leeslaag eronder, altijd met de
   vermelding dat de afleiding geldt bij twijfel. De host maakt geen
   juridische uitspraak; hij verwoordt.
4. **Dezelfde module heeft twee andere ingangen.** De MCP-server
   `services/mcp/uitleg/server.py` (tools `verwoord`, `toets`, `regels`)
   vraagt het model van de aanroepende client via MCP-sampling, zodat de
   server zelf geen sleutel kent; een client zonder sampling krijgt het prompt
   terug. De CLI `services/cli/uitleg-cli` doet `regels`, `toets` en
   `verzoek` lokaal (via `python uitleg.py`), `verwoord` via de host, en
   `batch` over een map: de meting voor het onderzoek. Alle drie roepen
   `uitleg.graaf_regels`, `bouw_prompt` en `toets` aan; het prompt staat op
   één plek. De server is geen bron van de host en wordt niet door de host
   gestart: de chat is geparkeerd (PDR-014) en het portaal gebruikt het
   endpoint.

## Alternatieven overwogen

- **Prompt in het portaal, via `/chat`.** Werkt, maar het prompt hoort niet in
  de frontend, de toets ontbreekt, en elke afnemer kopieert het prompt. Dit
  was de eerste versie en is vervangen.
- **Taalmodel in de kern van regelrecht-uitleg.** Afgewezen: de kern is
  deterministisch en dat is precies wat de uitleg trouw houdt. Een taalmodel
  in die laag maakt de toetssteen zelf onbetrouwbaar.
- **Alleen de deterministische tekst, geen taalmodel.** Blijft het
  uitgangspunt in het portaal; het taalmodel staat achter een knop. Of de
  taalmodeltekst beter begrepen wordt én trouw blijft, is juist de
  onderzoeksvraag; daarom allebei.
- **De tekst afkeuren en niet tonen bij een mislukte toets.** Afgewezen voor
  de PoC: de afnemer (en het onderzoek) wil zien wat het model deed. Een
  productieversie kan hier strenger zijn; de `toets` maakt dat mogelijk
  zonder de dienst te veranderen.

## Consequenties

- Het portaal stuurt de graaf en de samenvatting, niet een prompt. De
  frontendcode wordt kleiner en kent geen modelinstructies meer.
- De prompt-grens `MAX_VRAAG_TEKENS` geldt ook hier. De graaf wordt diepte-eerst
  ingekort tot zestig regels en zes niveaus; past hij dan nog niet, dan komt
  `UITLEG_GRAAF_TE_GROOT` terug en toont het portaal alleen de afleiding.
- De graaf bevat waarden, namen van variabelen en artikelnummers, geen
  persoonsgegevens. Het KVK-nummer uit de sessie wordt niet aan het model
  gegeven.
- De eerste meting (20 oktober 2026, negen uitkomsten, Claude) staat in
  [`../uitleg-meting-2026-10-20.md`](../uitleg-meting-2026-10-20.md): alle
  negen door de toets, één inhoudelijke fout die de toets niet zag (een
  MAX als "laagste"). Dat is de grens van een deterministische toets op
  getallen; de toets kent sindsdien de omgedraaide rekenstap, maar begrip en
  redenering blijven een menselijk oordeel.
- `tests/test_uitleg_ingangen.py` draait de MCP-server als subproces met een
  client mét en zonder sampling, en de CLI-stappen zonder host.
- `tests/test_uitleg.py` bewaakt: graaf naar regels (grenzen, bedragen), de
  toets (verzonnen bedrag, verzonnen percentage, artikel ontbreekt), de
  aanroep zonder tools, en het endpoint zonder sessie, zonder sleutel, met een
  ongeldige graaf en met een leeg antwoord.

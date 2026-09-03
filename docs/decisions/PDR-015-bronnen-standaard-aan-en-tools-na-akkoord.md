# PDR-015: Bronnen staan standaard aan, uitzetten is een woord, en tools die akkoord vergen staan pas na het akkoord in de lijst

| Veld | Waarde |
|---|---|
| Status | Geaccepteerd |
| Datum | 2026-09-03 |
| Beslisser(s) | Projectteam poc-moza |
| Gerelateerd | [PDR-008](PDR-008-generieke-regelrecht-tool-en-wallet.md) (toestemming per bron), [PDR-011](PDR-011-foutmeldingen-catalogus.md), [PDR-014](PDR-014-chat-geparkeerd-tot-de-vertaling-naar-wet-klopt.md) (meting van 2 september) |

## Context

Voor het gebruikersonderzoek van augustus stond de Business Wallet op de
onderzoeksomgeving uit: de respondent gaf zijn verbruik zelf op. Dat gebeurde
met `MCP_SERVER_NETBEHEERDER=uit` in de omgeving van het ZAD-component, en die
omgeving staat buiten deze repository. Na het onderzoek bleef die instelling
stil staan, terwijl de code, `compose.yaml` en `.env.example` de wallet allemaal
aan hebben. Niets in de host maakte het verschil zichtbaar.

Twee afspraken uit de configuratie maakten dat erger. Een lege waarde zette een
bron uit, terwijl een variabele leegmaken in een beheer-UI de gewone handeling
is voor "terug naar standaard". En `/health` meldde altijd `actief`, ook met een
bron minder.

Daarnaast liet de meting van 2 september (PDR-014, figuur 5) zien dat het model
in vrijwel elke eerste beurt het Handelsregister probeerde aan te roepen vóór
het akkoord, en de wallet drie keer. De poort uit PDR-008 weigerde alle
veertien, maar elke weigering kostte een extra modelbeurt en een bronfout in
het scherm, en het statusblok in de prompt noemde altijd de Business Wallet,
ook als de host op akkoord voor de KvK wachtte.

## Beslissing

1. **Elke bron staat aan tenzij iemand hem met een woord uitzet.** Een
   afwezige of lege `MCP_SERVER_<BRON>` betekent het standaardpad. Uitzetten kan
   alleen met een uitzet-woord (`uit`, `off`, `none`, `geen`, `false`, `no`,
   `nee`, `0`, `disabled`; de lijst is `_UIT` in `config.py`, en een test
   bewaakt dat `.env.example` en `docs/deploy-zad.md` dezelfde woorden noemen).
2. **Een uitgezette bron is zichtbaar, geen storing.** `config.MCP_SERVERS_UIT`
   kent per uitgezette bron de variabele; de host waarschuwt bij het opstarten
   en `GET /health` toont de bron onder `bronnen_uit`. `status` is `actief` of
   `gedegradeerd`, en `gedegradeerd` betekent uitsluitend dat een ingerichte
   bron niet opkwam (`niet beschikbaar` in `servers`). De drie velden zijn een
   contract voor wie `/health` leest; de readiness-probe van ZAD kijkt alleen
   naar de HTTP-status.
3. **Tools van bronnen die akkoord vergen staan pas na het akkoord in de
   lijst van het model**, en alleen zolang het deelverzoek in het scherm staat
   (`wacht_op == "toestemming"`). Buiten die stand blijft de lijst heel en is
   de poort uit PDR-008 de grens, zodat een bron waarvoor nooit een deelverzoek
   kwam bereikbaar blijft. Het statusblok en de harde regel in de prompt noemen
   de bron waarop het systeem wacht, voor de regeltoets en voor de
   maatregelenlijst met dezelfde formulering. Dit geldt voor het MCP-transport;
   het CLI-transport heeft geen poort (PDR-005) en zegt dat in zijn eigen
   promptblok.
4. **Het meetscript toetst tegen de vijf bekende bronnen**, niet tegen wat
   `servers` toevallig bevat, en meldt storing en uitgezet apart.

## Alternatieven overwogen

- **Leeg blijft uitzetten, alleen beter documenteren.** Afgewezen: de
  valkuil verdwijnt niet, hij wordt op drie plekken uitgelegd. Een omgeving
  die de wallet nog met een lege waarde had uitgezet, zet hem met deze PDR
  aan; dat is de bedoelde richting en `bronnen_uit` laat het zien.
- **`gedegradeerd` ook bij een uitgezette bron.** Afgewezen: een
  onderzoeksomgeving die bewust zonder wallet draait, zou dan permanent
  gedegradeerd heten, en het woord verliest zijn betekenis voor echte
  storingen.
- **Alleen de promptregel aanscherpen, geen tool-filter.** Afgewezen: de
  meting van 2 september liet zien dat een harde promptregel het model niet
  tegenhield; een tool die het model niet ziet, roept het niet aan.
- **Altijd filteren zodra het akkoord ontbreekt.** Afgewezen: valt RegelRecht
  weg of komt de regelloop niet tot een deelverzoek, dan is er geen knop die
  het akkoord vastlegt en zou het Handelsregister onbereikbaar zijn.
- **De env-sleutels afleiden uit `BRON_LABELS`.** Afgewezen: `config` zou dan
  `errors` importeren (met de LLM-SDK's erachter) en een label zonder server
  zou een niet-bestaande server laten starten. De lijst staat expliciet in
   `config.py`; een test bindt hem aan de labels.

## Consequenties

- **ZAD-UI:** `MCP_SERVER_NETBEHEERDER` op `dabackend` en `dabackend-onderzoek`
  verwijderen of leegmaken; na de uitrol `/health` controleren op
  `actief [] verbonden` (zie `docs/deploy-zad.md`).
- **Frontend en monitoring:** `status` kan `gedegradeerd` zijn; wie op
  `actief` toetste, moet dat als storing lezen, niet als "assistent weg".
- **Tests:** conftest zet `MCP_SERVER_*` leeg, zodat de suite niet van de
  `.env` van de ontwikkelaar afhangt; `host_met_bronnen` is de ene fabriek
  voor een host met uitgezette of uitgevallen bronnen.
- **Meting:** de weigeringen uit figuur 5 van PDR-014 horen met deze PDR
  niet meer voor te komen in de flow. Dat is na te meten met
  `docs/superpowers/plans/toets-pdr-014/meet.py`; die hermeting is nog niet
  gedaan.

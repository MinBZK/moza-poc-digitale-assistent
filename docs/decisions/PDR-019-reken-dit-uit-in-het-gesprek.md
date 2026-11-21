# PDR-019: De assistent kan in een gesprek vragen "reken dit uit"; de browser rekent en houdt de uitkomst

| Veld | Waarde |
|---|---|
| Status | Voorgesteld (ontwerp, niet gebouwd) |
| Datum | 2026-10-26 |
| Beslisser(s) | Projectteam Digitale assistent 2.0 |
| Gerelateerd | [PDR-018](PDR-018-clientcontract-rekenkern.md) (clientcontract), [PDR-015](PDR-015-bronnen-standaard-aan-en-tools-na-akkoord.md) (tools na akkoord), [PDR-016](PDR-016-uitleg-in-gewone-taal-uit-de-beslisgraaf.md) (uitleg), PDR-014 (chat geparkeerd) |

## Context

In een gesprek kan een ondernemer vragen: "wat levert het op als ik iemand
uit de bijstand aanneem voor 32 uur?" Het taalmodel kan dat niet zelf
uitrekenen en mag de feiten niet krijgen (PDR-018). De rekenkern draait in
de browser. Er is dus een manier nodig waarop de assistent een berekening
voorstelt, het portaal hem uitvoert, en de uitkomst bij de ondernemer blijft.

## Voorstel

1. **Een clienttool `rekenkern__voorstel`.** De host geeft het model een tool
   die niets uitvoert. Het model vult een voorstel in:
   `{ ingang: "orienteer" | "bereken", keuzes | verzoek, reden }`. Alleen
   uitkomsten van de allowlist zijn mogelijk; het schema van de tool is het
   contractschema. De host valideert het voorstel tegen het schema en stuurt
   het als gebeurtenis `berekening_voorgesteld` in de SSE-stroom naar het
   portaal. De host rekent niet en bewaart het voorstel niet buiten de sessie.
2. **Het portaal toont het voorstel** ("De assistent wil dit voor u
   uitrekenen: 32 uur, bijstand, loonwaarde 60. Klopt dat?"). De ondernemer
   past aan of bevestigt. Na bevestiging rekent de worker. De uitkomst, met
   "Waarom deze uitkomst?" uit de kern, staat alleen in het portaal.
3. **Terug naar het gesprek alleen op keuze van de ondernemer.** Twee knoppen:
   "Bespreek de uitkomst met de assistent" stuurt alleen `uitleg.kort` mee in
   het volgende bericht, zichtbaar in het invoerveld voor verzending. "Leg uit
   in gewone taal" gebruikt `/uitleg` (PDR-016). Zonder keuze krijgt het
   model alleen "de ondernemer heeft de berekening bekeken", zonder
   uitkomst.
4. **Toolresultaat aan het model.** De tool geeft `{ status: "voorgelegd" }`
   terug, nooit een uitkomst. Het systeemprompt zegt dat de assistent geen
   bedragen noemt die de ondernemer niet zelf deelde.

## Alternatieven overwogen

- **De host rekent en geeft de uitkomst aan het model.** Afgewezen om de
  gegevens (PDR-018).
- **Het model geeft feiten, de browser rekent, de uitkomst gaat automatisch
  terug.** Afgewezen: de uitkomst komt dan zonder keuze van de ondernemer
  bij het model.
- **Een MCP-tool in de browser** (client-side MCP-server in het portaal).
  Interessant voor later. De MCP-standaard kent hier nog geen vorm voor een
  tool die bij de eindgebruiker draait met diens akkoord; het
  SSE-gebeurtenisvoorstel past op wat er nu is.

## Consequenties en open punten

- De chat is geparkeerd (PDR-014). Dit ontwerp is pas aan de orde als het
  gesprek terugkomt; daarom niet gebouwd.
- Nieuwe SSE-gebeurtenis en een clienttool zonder uitvoering vragen een
  aanpassing van `vlam_host.py` (tooldefinities voor MCP én CLI, PDR-005) en
  van het portaal.
- Open: hoort het voorstel in de toollijst pas na akkoord (PDR-015)? Het
  voorstel zelf deelt niets, dus voorstel: standaard aan.
- Open: hoe meet het gebruikersonderzoek of ondernemers begrijpen dat de
  uitkomst niet naar de assistent gaat?

<!-- bronnen: kvk, regelrecht, rvo -->
<!-- bronnen-optioneel: netbeheerder -->
# Voorbeeld: informatieplicht-flow met bronnen, feitelijke vragen en restvraag

Gebruiker: "Ik kreeg een melding dat de informatieplicht energiebesparing binnenkort voor mijn bedrijf geldt. Wat moet ik doen?"

Assistent (de host heeft de toets al vóór dit antwoord uitgevoerd - "STATUS VAN DE REGELTOETS" zegt dat er toestemming nodig is voor de Business Wallet; de assistent roept zelf NOG GEEN tools aan en vraagt dat EXPLICIET):

"Dat kan ik voor u uitzoeken. Daarvoor heb ik uw energieverbruik nodig uit uw Business Wallet. Dat is een attestatie, afgegeven door uw netbeheerder. Mag ik dat voor u ophalen en gebruiken?"

Gebruiker: "Ja, ga je gang." (verstuurd via de "Delen"-knop, die toestemming op dit verzoek vastlegt)

Assistent (de host heeft, zodra de toestemming vastlag, vóór dit antwoord zelf netbeheerder__verbruik aangeroepen en de toets daarmee meteen afgerond - "STATUS VAN DE REGELTOETS" zegt dat de uitkomst er al is; de assistent roept zelf geen tools meer aan en wacht niet op een volgende vraag):

"Op basis van uw gegevens is de toets afgerond:

**Geraadpleegde bronnen**
- KvK Handelsregister: {{BEDRIJFSNAAM}}, KvK {{KVK_NUMMER}}, {{VESTIGINGSADRES}}. Woonfunctie: {{WOONFUNCTIE}}.
- Uw Business Wallet: {{ELEKTRICITEIT_KWH}} kWh elektriciteit en {{GAS_M3}} m³ gas (peiljaar {{PEILJAAR}}). Uw netbeheerder gaf deze attestatie af. U hebt hem met mij gedeeld.
- RegelRecht (art. 5.15d Besluit activiteiten leefomgeving): uw elektriciteitsverbruik ligt boven de drempel uit RegelRecht. **De informatieplicht geldt {{OORDEEL_INFORMATIEPLICHT}} voor uw bedrijf.**

**Berekening**
- Elektriciteit: {{ELEKTRICITEIT_KWH}} kWh vs. de drempel uit RegelRecht - overschreden
- Aardgas: {{GAS_M3}} m³ vs. de drempel uit RegelRecht - niet overschreden
- Woonfunctie-uitzondering: nee

U hoeft dus niets op te zoeken. Om te bepalen wélke maatregelen gelden, heb ik nog een paar gegevens van u nodig. Die staan nergens geregistreerd; alleen u weet ze. U vult ze hieronder in. Uw antwoorden worden bewaard voor de volgende ronde."

(De vragen staan in "STATUS VAN DE REGELTOETS". De host draaide de regel zelf. Die wacht nu op een opgave. Het formulier komt uit de regel. De assistent verwijst ernaar. Hij bedenkt zelf geen vragen en geen categorieen.)

Gebruiker: (vult het formulier in en verstuurt het)

Assistent (de host heeft de maatregelentoets afgerond zodra de opgaven binnen waren - "STATUS VAN DE REGELTOETS" noemt de maatregelen die eruit kwamen; de assistent roept zelf geen tools aan):

"Dank u. Voor {{BEDRIJFSNAAM}} gelden de maatregelen uit de bijlage die op uw bedrijf van toepassing is. Kunt u per maatregel aangeven of deze is uitgevoerd?

1. Vergroot de persluchtbuffer - uitgevoerd / niet uitgevoerd? (FA1)
2. Vervang de verlichting door led - uitgevoerd / niet uitgevoerd? (GB3)

(Namen, codes en aantal komen uit de status. Noem er nooit een die daar niet staat.)

Gebruiker: "De eerste wel, de tweede nog niet."

Assistent (toont het VOLLEDIGE rapport met inputwaarden incl. bronnen, berekening, uitkomst, regeling en de maatregelenstatus, en vraagt akkoord):

"...Klopt dit overzicht en mag ik de rapportage indienen?"

Gebruiker: "Ja, dien maar in."

Assistent (na rvo__indienen met maatregelen-status en bedrijfskenmerken):

"✅ Uw rapportage is ingediend (referentie {{REFERENTIENUMMER}}) en in behandeling genomen. U vindt de status terug onder 'Lopende zaken'. U hoort het zodra er iets van u nodig is.

Uw antwoorden zijn bewaard. Bij de volgende ronde ({{VOLGENDE_DEADLINE}}) staat het voorwerk al klaar."

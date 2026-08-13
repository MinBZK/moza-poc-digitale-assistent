<!-- bronnen: kvk, regelrecht, rvo -->
<!-- bronnen-optioneel: netbeheerder -->
# Voorbeeld: informatieplicht-flow met bronnen, feitelijke vragen en restvraag

Gebruiker: "Ik kreeg een melding dat de informatieplicht energiebesparing binnenkort voor mijn bedrijf geldt. Wat moet ik doen?"

Assistent (roept NOG GEEN tools aan - vraagt EERST toestemming om gegevens te delen):

"Dat kan ik voor u uitzoeken. Om te beoordelen of de informatieplicht voor uw bedrijf geldt, wil ik twee dingen raadplegen en gebruiken:
- uw bedrijfsgegevens uit het KvK Handelsregister;
- uw energieverbruik uit uw Business Wallet - een attestatie, afgegeven door uw netbeheerder.

Mag ik deze gegevens voor u ophalen en gebruiken?"

Gebruiker: "Ja, ga je gang."

Assistent (pas NA toestemming: na kvk__mijn_bedrijf, netbeheerder__verbruik [Business Wallet] en regelrecht__execute_law met law "omgevingswet/energiebesparing/informatieplicht"):

"Dank u. Ik heb het voorwerk voor u gedaan. Dit heb ik met uw toestemming geraadpleegd:

**Geraadpleegde bronnen**
- KvK Handelsregister: {{BEDRIJFSNAAM}}, KvK {{KVK_NUMMER}}, café (SBI 56102), {{VESTIGINGSADRES}} - geen woonfunctie.
- Uw Business Wallet: {{ELEKTRICITEIT_KWH}} kWh elektriciteit en {{GAS_M3}} m³ gas (peiljaar {{PEILJAAR}}). Uw netbeheerder gaf deze attestatie af. U hebt hem met mij gedeeld.
- RegelRecht (art. 5.15d Besluit activiteiten leefomgeving): uw elektriciteitsverbruik ligt boven de drempel uit RegelRecht. **De informatieplicht geldt {{OORDEEL_INFORMATIEPLICHT}} voor uw bedrijf.**

**Berekening**
- Elektriciteit: {{ELEKTRICITEIT_KWH}} kWh vs. de drempel uit RegelRecht - overschreden
- Aardgas: {{GAS_M3}} m³ vs. de drempel uit RegelRecht - niet overschreden
- Woonfunctie-uitzondering: nee

U hoeft dus niets op te zoeken. Om te bepalen wélke maatregelen voor uw zaak gelden, heb ik nog twee feitelijke vragen. Deze staan nergens geregistreerd. Alleen u weet dit. Het blijft een feit dat u aanlevert, geen juridische beoordeling. Uw antwoorden worden bewaard voor de volgende rapportageronde.

1. Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?
2. Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?"

(De assistent las deze vragen af uit regelrecht__execute_law, law "omgevingswet/energiebesparing/maatregelen". Roep die tool met lege parameters aan, dan meldt hij de benodigde_feiten. De vraagteksten komen dus uit de regel zelf.)

Gebruiker: "Ja allebei."

Assistent (na regelrecht__execute_law met law "omgevingswet/energiebesparing/maatregelen" en parameters={"HEEFT_KOELINSTALLATIE": true, "HEEFT_AFZUIGINSTALLATIE": true}):

"Dank u. Op basis van de Erkende Maatregelenlijst (EML 2023) gelden voor {{BEDRIJFSNAAM}} 7 maatregelen. Kunt u per maatregel aangeven of deze is uitgevoerd?

1. Pas een klokregeling toe en regel deze in (ruimteverwarming) - uitgevoerd / niet uitgevoerd? (GC1)
2. Pas een weersafhankelijke regeling toe - uitgevoerd / niet uitgevoerd? (GC3)
3. Vervang gloei-, halogeen- en spaarlampen door LED-lampen - uitgevoerd / niet uitgevoerd? (GF4)
4. Pas nachtafdekking toe bij semi-verticale koelmeubels - uitgevoerd / niet uitgevoerd? (FD3)
5. Isoleer de wanden van koelcellen - uitgevoerd / niet uitgevoerd? (FD7)
6. Pas een laagdebiet afzuigkap toe bij grootkeukens - uitgevoerd / niet uitgevoerd? (FE4)
7. Pas een klokregeling toe op het ventilatiesysteem - uitgevoerd / niet uitgevoerd?" (GD1)

Gebruiker: "1 t/m 5 gedaan, 6 en 7 nog niet."

Assistent (toont het VOLLEDIGE rapport met inputwaarden incl. bronnen, berekening, uitkomst, regeling en de maatregelenstatus, en vraagt akkoord):

"...Klopt dit overzicht en mag ik de rapportage indienen?"

Gebruiker: "Ja, dien maar in."

Assistent (na rvo__indienen met maatregelen-status en bedrijfskenmerken):

"✅ Uw rapportage is ingediend (referentie {{REFERENTIENUMMER}}) en in behandeling genomen. U vindt de status terug onder 'Lopende zaken'. U hoort het zodra er iets van u nodig is.

Uw antwoorden (koelinstallatie, afzuiginstallatie) zijn bewaard. Bij de volgende ronde ({{VOLGENDE_DEADLINE}}) staat het voorwerk al klaar."

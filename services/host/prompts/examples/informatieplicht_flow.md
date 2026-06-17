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
- KvK Handelsregister: Koffiezaak Noon, KvK 85234567, café (SBI 56102), Witte de Withstraat 27, Rotterdam - geen woonfunctie (via BAG).
- Uw Business Wallet: energieverbruik-attestatie - 61.250 kWh elektriciteit en 9.800 m³ gas (peiljaar 2025), afgegeven door uw netbeheerder en met uw toestemming gedeeld.
- RegelRecht (art. 5.15d Besluit activiteiten leefomgeving): uw elektriciteitsverbruik ligt boven de drempel van 50.000 kWh - **de informatieplicht geldt voor uw bedrijf**.

**Berekening**
- Elektriciteit: 61.250 kWh vs. drempel 50.000 kWh - overschreden
- Aardgas: 9.800 m³ vs. drempel 25.000 m³ - niet overschreden
- Woonfunctie-uitzondering: nee

U hoeft dus niets op te zoeken. Om te bepalen wélke maatregelen voor uw zaak gelden, heb ik nog twee feitelijke vragen. Deze staan nergens geregistreerd - alleen u weet dit; het blijft een feit dat u aanlevert, geen juridische beoordeling. Uw antwoorden worden bewaard voor de volgende rapportageronde.

1. Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?
2. Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?"

(De assistent heeft deze vragen afgelezen uit regelrecht__execute_law met law "omgevingswet/energiebesparing/maatregelen": met lege parameters aangeroepen meldt de tool de benodigde_feiten - de vraagteksten komen uit de machine-uitvoerbare regel zelf.)

Gebruiker: "Ja allebei."

Assistent (na regelrecht__execute_law met law "omgevingswet/energiebesparing/maatregelen" en parameters={"HEEFT_KOELINSTALLATIE": true, "HEEFT_AFZUIGINSTALLATIE": true}):

"Dank u. Op basis van de Erkende Maatregelenlijst (EML 2023) gelden voor Koffiezaak Noon 7 maatregelen. Kunt u per maatregel aangeven of deze is uitgevoerd?

1. GC1 - Pas een klokregeling toe en regel deze in (ruimteverwarming) - uitgevoerd / niet uitgevoerd?
2. GC3 - Pas een weersafhankelijke regeling toe - uitgevoerd / niet uitgevoerd?
3. GF4 - Vervang gloei-, halogeen- en spaarlampen door LED-lampen - uitgevoerd / niet uitgevoerd?
4. FD3 - Pas nachtafdekking toe bij semi-verticale koelmeubels - uitgevoerd / niet uitgevoerd?
5. FD7 - Isoleer de wanden van koelcellen - uitgevoerd / niet uitgevoerd?
6. FE4 - Pas een laagdebiet afzuigkap toe bij grootkeukens - uitgevoerd / niet uitgevoerd?
7. GD1 - Pas een klokregeling toe op het ventilatiesysteem - uitgevoerd / niet uitgevoerd?"

Gebruiker: "1 t/m 5 gedaan, 6 en 7 nog niet."

Assistent (toont het VOLLEDIGE rapport met inputwaarden incl. bronnen, berekening, uitkomst, regeling en de maatregelenstatus, en vraagt akkoord):

"...Klopt dit overzicht en mag ik de rapportage indienen?"

Gebruiker: "Ja, dien maar in."

Assistent (na rvo__indienen met maatregelen-status en bedrijfskenmerken):

"✅ Uw rapportage is ingediend (referentie RVO-EBR-2026-85234567-001) en direct geautomatiseerd getoetst door de omgevingsdienst op dezelfde machine-uitvoerbare regel: **akkoord - in één keer goed, geen herstelronde**. U hoort alleen iets als er alsnog een afwijking wordt geconstateerd.

Uw antwoorden (koelinstallatie, afzuiginstallatie) zijn bewaard; bij de volgende ronde (2030) staat het voorwerk al klaar. U vindt de zaak terug onder 'Lopende zaken'."

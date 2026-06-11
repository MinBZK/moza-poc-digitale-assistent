# Voorbeeld: informatieplicht-flow met bronnen, feitelijke vragen en restvraag

Gebruiker: "Ik kreeg een melding dat de informatieplicht energiebesparing binnenkort voor mijn bedrijf geldt. Wat moet ik doen?"

Assistent (na kvk__mijn_bedrijf, netbeheerder__verbruik en regelrecht__check):

"Ik heb het voorwerk voor u gedaan. Dit heb ik geraadpleegd:

**Geraadpleegde bronnen**
- KvK Handelsregister: Koffiezaak Noon, KvK 85234567, café (SBI 56102), Witte de Withstraat 27, Rotterdam — geen woonfunctie (via BAG).
- Netbeheerder: jaarverbruik 61.250 kWh elektriciteit en 9.800 m³ gas (peiljaar 2025).
- RegelRecht (art. 5.15d Besluit activiteiten leefomgeving): uw elektriciteitsverbruik ligt boven de drempel van 50.000 kWh — **de informatieplicht geldt voor uw bedrijf**.

**Berekening**
- Elektriciteit: 61.250 kWh vs. drempel 50.000 kWh — overschreden
- Aardgas: 9.800 m³ vs. drempel 25.000 m³ — niet overschreden
- Woonfunctie-uitzondering: nee

U hoeft dus niets op te zoeken. Om te bepalen wélke maatregelen voor uw zaak gelden, heb ik nog twee feitelijke vragen. Deze staan nergens geregistreerd — alleen u weet dit; het blijft een feit dat u aanlevert, geen juridische beoordeling. Uw antwoorden worden bewaard voor de volgende rapportageronde.

1. Heeft u een koel- of vriesinstallatie?
2. Heeft u een afzuiginstallatie?"

Gebruiker: "Ja allebei."

Assistent (na regelrecht__maatregelen met sbi_code=56102, koelinstallatie=true, afzuiginstallatie=true):

"Dank u. Op basis van de Erkende Maatregelenlijst voor de horeca gelden voor Koffiezaak Noon 7 maatregelen. Kunt u per maatregel aangeven of deze is uitgevoerd?

1. LED-verlichting in verblijfsruimten — uitgevoerd / niet uitgevoerd?
2. Waterzijdig inregelen van het verwarmingssysteem — uitgevoerd / niet uitgevoerd?
3. Deurdranger of automatische deursluiting buitendeur — uitgevoerd / niet uitgevoerd?
4. Isolatie van koel- of vriescel — uitgevoerd / niet uitgevoerd?
5. Nachtafdekking van koelmeubelen — uitgevoerd / niet uitgevoerd?
6. Tijd- of aanwezigheidsschakeling op de afzuiginstallatie — uitgevoerd / niet uitgevoerd?
7. Frequentieregeling op de afzuigventilator — uitgevoerd / niet uitgevoerd?"

Gebruiker: "1 t/m 5 gedaan, 6 en 7 nog niet."

Assistent (toont het VOLLEDIGE rapport met inputwaarden incl. bronnen, berekening, uitkomst, regeling en de maatregelenstatus, en vraagt akkoord):

"...Klopt dit overzicht en mag ik de rapportage indienen?"

Gebruiker: "Ja, dien maar in."

Assistent (na rvo__indienen met maatregelen-status en bedrijfskenmerken):

"✅ Uw rapportage is ingediend (referentie RVO-EBR-2026-85234567-001) en direct geautomatiseerd getoetst door de omgevingsdienst op dezelfde machine-uitvoerbare regel: **akkoord — in één keer goed, geen herstelronde**. U hoort alleen iets als er alsnog een afwijking wordt geconstateerd.

Uw antwoorden (koelinstallatie, afzuiginstallatie) zijn bewaard; bij de volgende ronde (2030) staat het voorwerk al klaar. U vindt de zaak terug onder 'Lopende zaken'."

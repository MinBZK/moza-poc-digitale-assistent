<!-- bronnen: kvk, regelrecht -->
Voorbeeld: geen verplichting (RegelRecht)

Gebruiker: Ik verbruik 30.000 kWh elektriciteit en 15.000 m3 gas per jaar. Moet ik rapporteren?

Assistent roept tool aan: kvk__mijn_bedrijf()
Assistent ontvangt: bedrijfsgegevens uit het Handelsregister, BAG: is_woonfunctie: false

Assistent roept tool aan: regelrecht__execute_law(law="omgevingswet/energiebesparing/informatieplicht", parameters={"KVK_NUMMER": "<nummer>"}, overrides={"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 30000, "JAARLIJKS_GASVERBRUIK_M3": 15000, "IS_WOONFUNCTIE": false}})

Assistent:
De Informatieplicht Energiebesparing is niet van toepassing op {{BEDRIJFSNAAM}}.

Uw verbruik ligt onder beide drempels:
- Elektriciteit: 30.000 kWh (onder de drempel uit RegelRecht)
- Aardgas: 15.000 m³ (onder de drempel uit RegelRecht)

U hoeft nu niet te rapporteren. Komt uw verbruik later boven een drempel? Dan geldt de plicht alsnog.

Let op: ik kan momenteel alleen de energiebesparingsplicht toetsen. Er kunnen andere verplichtingen gelden.

Bron: RegelRecht (art. 5.15 Besluit activiteiten leefomgeving)

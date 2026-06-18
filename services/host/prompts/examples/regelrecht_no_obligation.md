Voorbeeld: geen verplichting (RegelRecht)

Gebruiker: Ik verbruik 30.000 kWh elektriciteit en 15.000 m3 gas per jaar. Moet ik rapporteren?

Assistent roept tool aan: kvk__mijn_bedrijf()
Assistent ontvangt: Test BV Donald, KvK 68750110, BAG: is_woonfunctie: false

Assistent roept tool aan: regelrecht__execute_law(law="omgevingswet/energiebesparing/informatieplicht", parameters={"KVK_NUMMER": "68750110"}, overrides={"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 30000, "JAARLIJKS_GASVERBRUIK_M3": 15000, "IS_WOONFUNCTIE": false}})

Assistent:
De Informatieplicht Energiebesparing is niet van toepassing op Test BV Donald.

Uw verbruik ligt onder beide drempels:
- Elektriciteit: 30.000 kWh (drempel: 50.000 kWh)
- Aardgas: 15.000 m³ (drempel: 25.000 m³)

U hoeft nu niet te rapporteren. Als uw verbruik in de toekomst boven een drempel komt, wordt de plicht wel van toepassing.

Let op: ik kan momenteel alleen de energiebesparingsplicht toetsen. Er kunnen andere verplichtingen gelden.

Bron: RegelRecht (art. 5.15 Besluit activiteiten leefomgeving)

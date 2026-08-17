"""De prompt leert het model slots te schrijven, en de voorbeelden doen het voor.

Een model imiteert voorbeelden sterker dan het een instructie volgt. Staat er in
een voorbeeld een letterlijk bedrijfsnaam, dan schrijft het model die ook - en
dan blokkeert de host het antwoord.
"""

import re
from pathlib import Path

from prompts.composer import compose_system_prompt

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
VOORBEELDEN = sorted((PROMPTS / "examples").glob("*.md"))

# Waarden uit de mockpersona's die nooit letterlijk in een voorbeeld horen: als
# het model ze imiteert, noemt het het bedrijf van iemand anders. Dit vangt ook
# SBI-activiteit en werkzame-personen-getallen: voor "Kwekerij De Bloesem" is
# "Teelt van appels en peren" plausibel genoeg om niet op te vallen, wat het
# juist het slechtste soort fout maakt.
_VERBODEN_LETTERLIJK = (
    "Koffiezaak Noon",
    "Test BV Donald",
    "Hoefweg 210",
    "Meent 88",
    "café (SBI 56102)",
    "01241 - Teelt van appels en peren",
    "Werkzame personen: 1",
)


def test_de_prompt_bevat_het_slotblok():
    prompt = compose_system_prompt("vlam", has_tools=True)
    assert "{{BEDRIJFSNAAM}}" in prompt
    assert "{{ELEKTRICITEIT_KWH}}" in prompt


def test_zonder_tools_geen_slotblok():
    """Zonder bronnen zijn er geen feiten, dus ook niets om in te vullen."""
    assert "{{BEDRIJFSNAAM}}" not in compose_system_prompt("vlam", has_tools=False)


def test_geen_voorbeeld_toont_een_letterlijk_bedrijfsfeit():
    overtredingen = []
    for pad in VOORBEELDEN:
        tekst = pad.read_text(encoding="utf-8")
        for waarde in _VERBODEN_LETTERLIJK:
            if waarde in tekst:
                overtredingen.append(f"{pad.name}: {waarde!r}")
    assert not overtredingen, (
        "voorbeelden tonen letterlijke feiten waar een slot hoort:\n  "
        + "\n  ".join(overtredingen)
    )


def test_elk_slot_in_de_voorbeelden_staat_in_het_woordenboek():
    """Een verzonnen slotnaam in een voorbeeld leert het model een slot dat de
    host niet kent, en dat blokkeert elk antwoord waarin het voorkomt."""
    from slots import _SLOT

    bekend = set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", (
        PROMPTS / "blocks" / "shared" / "slots.md"
    ).read_text(encoding="utf-8")))
    for pad in VOORBEELDEN:
        for naam in _SLOT.findall(pad.read_text(encoding="utf-8")):
            assert naam in bekend, f"{pad.name}: onbekend slot {naam}"

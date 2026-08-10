"""De assistent stuurt op B1 — en de voorbeelden doen dat ook (W3).

`prompts/blocks/shared/tone.md` schrijft B1 voor, met een harde grens van vijftien
woorden per zin. Een model imiteert de voorbeelden in zijn prompt echter sterker
dan het een abstracte instructie volgt. Demonstreren die voorbeelden zinnen van
twintig woorden, dan is de instructie in de praktijk een wens.

Deze tests bewaken de vorm, niet het begrip. Zie de docstring van taalniveau.py
voor wat de maat wél en niet zegt.
"""

from pathlib import Path

import pytest
from taalniveau import MAX_WOORDEN_PER_ZIN, meet

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
VOORBEELDEN = sorted((PROMPTS / "examples").glob("*.md"))


def _assistent_tekst(ruw: str) -> str:
    """Alleen wat de assistent zegt, niet de vraag of de tool-aanroep."""
    regels, aan = [], False
    for regel in ruw.splitlines():
        schoon = regel.strip()
        if schoon.startswith(("Gebruiker", "Voorbeeld")) or schoon.startswith(
            "Assistent roept tool aan"
        ):
            aan = False
            continue
        if schoon.startswith("Assistent") and schoon.endswith(":"):
            aan = True
            continue
        if aan:
            regels.append(regel)
    return "\n".join(regels)


def test_de_maat_ziet_een_lange_zin():
    """Vangnet op het meetinstrument zelf."""
    kort = meet("Dit is kort. Dat helpt.")
    lang = meet(
        "Deze zin is opzettelijk veel te lang gemaakt zodat de meting hem als "
        "overschrijding van de grens van vijftien woorden aanmerkt."
    )
    assert kort.aantal_te_lang == 0
    assert lang.aantal_te_lang == 1


def test_opsommingen_tellen_niet_als_zin():
    """Zonder deze schoonmaak meet je opmaak in plaats van taal.

    De voorbeelden staan vol regels als "Handelsnaam: Test BV" zonder punt; die
    aan elkaar plakken levert schijnzinnen van tientallen woorden op.
    """
    lijst = "Uw gegevens:\n- Handelsnaam: Test BV Donald\n- KvK-nummer: 68750110\n"
    assert meet(lijst) is None or meet(lijst).aantal_te_lang == 0


def test_tone_blok_is_zelf_vlot_leesbaar():
    """Het blok dat B1 voorschrijft, hoort zelf vlot leesbaar te zijn.

    Bewust op de score en niet op de zinslengte: dit is een regellijst, geen
    antwoord dat het model imiteert. Eén opsomming die verboden openingszinnen
    citeert mag daar best overheen gaan.
    """
    gemeten = meet((PROMPTS / "blocks" / "shared" / "tone.md").read_text())
    assert gemeten is not None
    assert gemeten.score >= 60, f"score {gemeten.score:.1f}"


@pytest.mark.parametrize("pad", VOORBEELDEN, ids=lambda p: p.name)
def test_voorbeeldantwoorden_demonstreren_de_regel_die_ze_leren(pad):
    """Het model imiteert deze antwoorden; ze horen dus B1 te zijn.

    Faalt deze test op een nieuw voorbeeld, dan is dat geen formaliteit: het
    voorbeeld leert het model precies het tegenovergestelde van tone.md.
    """
    gemeten = meet(_assistent_tekst(pad.read_text()))
    if gemeten is None:
        pytest.skip("geen assistent-proza in dit voorbeeld")
    assert gemeten.aantal_te_lang == 0, (
        f"{pad.name}: {gemeten.aantal_te_lang} zin(nen) boven "
        f"{MAX_WOORDEN_PER_ZIN} woorden — het model imiteert dit:\n  "
        + "\n  ".join(gemeten.te_lange_zinnen)
    )

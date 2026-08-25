"""Het maatregelen-formulier komt de beurt ná het oordeel; het model mag de
vragen intussen niet zelf uittikken.

Gezien op de onderzoeksomgeving (25 augustus): bij "de toets is afgerond"
somde het model de drie vragen en alle 23 categorieën op in proza. De
frontend maakt daar geen formulier van (regels eindigen op ")" of missen
"?"), dus de ondernemer typte los antwoorden in de chat. Een beurt later
kwam het echte formulier alsnog.
"""

from prompts.composer import compose_system_prompt

_KLAAR = {
    "klaar": True,
    "wacht_op": None,
    "resultaat": {"voldoet_aan_voorwaarden": True, "uitkomsten": {}},
}


def _prompt(**extra):
    status = {**_KLAAR, "maatregelen": {"klaar": False, "wacht_op": "opgave"}, **extra}
    return compose_system_prompt("claude", has_tools=True, regel_status=status)


def test_zonder_formulier_deze_beurt_mag_het_model_de_vragen_niet_noemen():
    prompt = _prompt()
    assert "Noem de vragen en de categorieën NIET zelf" in prompt
    assert "volgende beurt" in prompt


def test_met_formulier_deze_beurt_verwijst_het_model_ernaar():
    prompt = _prompt(vraag={"titel": "Erkende Maatregelenlijst", "velden": []})
    assert "Het formulier daarvoor staat bij dit antwoord" in prompt
    assert "Noem de vragen en de categorieën NIET zelf" not in prompt


def test_zonder_maatregelenregel_geen_van_beide():
    prompt = compose_system_prompt("claude", has_tools=True, regel_status=_KLAAR)
    assert "Noem de vragen en de categorieën NIET zelf" not in prompt
    assert "staat bij dit antwoord" not in prompt

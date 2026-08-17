"""De prompt mag geen contract leren dat de code niet meer levert.

Een instructie die naar een responsveld of een regelveld verwijst dat niet meer
bestaat, wordt door het model gewoon uitgevoerd: het roept de tool aan, ziet het
veld niet, en vult de rest zelf in. Dat is geen prompt-nuance maar waarneembaar
gedrag richting de respondent - hij krijgt vragen die niemand gesteld wil hebben.

Deze test leest de echte promptblokken en de echte routeringstabel, zodat een
volgende wetswijziging niet opnieuw een instructie laat staan die nergens meer op
aansluit.
"""

from pathlib import Path

import pytest

import regelrouting

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

# Responsvelden die de MCP-servers ooit teruggaven en nu niet meer. Een prompt
# die het model opdraagt zo'n veld te lezen, laat het model in het duister.
VERDWENEN_RESPONSVELDEN = ("benodigde_feiten",)

# Regelvelden uit de demo-subset van de maatregelenwet. De sectorbewuste versie
# kent ze niet meer; `regelrouting.HERKOMST` is daarvan de bron van waarheid.
VERDWENEN_REGELVELDEN = ("HEEFT_KOELINSTALLATIE", "HEEFT_AFZUIGINSTALLATIE")


def _promptbestanden() -> list[Path]:
    return sorted(PROMPTS.rglob("*.md"))


def test_er_zijn_promptbestanden_om_te_toetsen():
    """Anders slaagt deze test stilzwijgend op een leeg zoekresultaat."""
    assert _promptbestanden()


@pytest.mark.parametrize("veld", VERDWENEN_RESPONSVELDEN)
def test_geen_prompt_verwijst_naar_een_verdwenen_responsveld(veld):
    treffers = [
        f"{pad.relative_to(PROMPTS)}:{nr}"
        for pad in _promptbestanden()
        for nr, regel in enumerate(pad.read_text().splitlines(), 1)
        if veld in regel
    ]
    assert not treffers, (
        f"'{veld}' bestaat niet meer in de respons van een bron, maar de prompt "
        f"draagt het model op het te lezen: {treffers}"
    )


@pytest.mark.parametrize("veld", VERDWENEN_REGELVELDEN)
def test_geen_prompt_noemt_een_regelveld_dat_de_routering_niet_kent(veld):
    """Dubbele bewaking: het veld is weg uit de wet én uit de routeringstabel.

    De eerste assert is de vangrail voor deze test zelf. Komt het veld ooit
    terug in `HERKOMST`, dan is het weer een geldig regelveld en hoort deze
    test aangepast te worden in plaats van de prompt.
    """
    assert regelrouting.route(veld) is None, (
        f"{veld} staat weer in de routeringstabel; werk deze test bij"
    )
    treffers = [
        f"{pad.relative_to(PROMPTS)}:{nr}"
        for pad in _promptbestanden()
        for nr, regel in enumerate(pad.read_text().splitlines(), 1)
        if veld in regel
    ]
    assert not treffers, (
        f"De prompt noemt regelveld '{veld}', dat de wet niet meer vraagt: {treffers}"
    )


def test_de_prompt_verbiedt_het_model_de_maatregelenregel_zelf_te_starten():
    """De host draait die regel sinds de regelgestuurde flow zelf.

    Zonder deze regel in de prompt doet het model het er alsnog bij: het roept
    de wet aan met parameters die het uit het gesprek moet raden, krijgt
    ontbrekende gegevens terug, en vraagt de ondernemer iets wat de host al
    weet.
    """
    tekst = (PROMPTS / "blocks/shared/tool_usage.md").read_text()
    regels = [r for r in tekst.splitlines() if "maatregelenregel" in r or "maatregelen" in r]
    assert regels, "de prompt zegt niets over de maatregelen"
    # Bewust niet op de toolnaam gefilterd: de instructie hoort die tool juist
    # niet meer te noemen voor deze regel. Wat geteld wordt is het verbod zelf.
    assert any(
        ("niet zelf" in r.lower()) for r in regels
    ), "de prompt zegt nergens dat het model de maatregelenregel niet zelf mag starten"

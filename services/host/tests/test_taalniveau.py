"""De assistent stuurt op B1 — en de voorbeelden doen dat ook (W3).

`prompts/blocks/shared/tone.md` schrijft B1 voor, met een harde grens van vijftien
woorden per zin. Een model imiteert de voorbeelden in zijn prompt echter sterker
dan het een abstracte instructie volgt. Demonstreren die voorbeelden zinnen van
twintig woorden, dan is de instructie in de praktijk een wens.

Deze tests bewaken de vorm, niet het begrip. Zie de docstring van taalniveau.py
voor wat de maat wél en niet zegt.
"""

import re
from pathlib import Path

import pytest
from taalniveau import MAX_WOORDEN_PER_ZIN, Leesbaarheid, meet

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
VOORBEELDEN = sorted((PROMPTS / "examples").glob("*.md"))

# De leesbaarheidsindex van vandaag, per voorbeeld, als ondergrens.
#
# Bewust geen gezamenlijke drempel. De spreiding loopt van 25,5 tot 93,5 en dat
# verschil zit niet in slordigheid maar in wat er te zeggen valt: een voorbeeld
# dat wetten citeert draagt "Besluit activiteiten leefomgeving" en
# "milieubelastende activiteiten", en die namen zijn niet te vereenvoudigen
# zonder ze onjuist te maken. Eén drempel dwingt dan óf tot onwaarheid óf tot een
# getal dat zo laag staat dat het niets meer tegenhoudt.
#
# Wat een ratel wél kan: bewaken dat een voorbeeld niet juridischer wordt dan het
# was. Gaat een score omhoog, werk dan de waarde hier bij - dat is geen ruis maar
# een verbetering die vastgelegd hoort te worden.
BASISSCORE = {
    "buiten_scope_met_brug.md": 58.1,
    "informatieplicht_flow.md": 52.4,
    "koop_regelrecht_combined.md": 64.7,
    "koop_search.md": 25.5,
    "koop_specific_law.md": 38.9,
    "onduidelijke_vraag.md": 66.8,
    "regelrecht_no_obligation.md": 57.5,
}

# Speling op de ratel, zodat een komma of een woordje wisselen geen rode CI geeft.
MARGE = 2.0

# Onder dit aantal gemeten woorden zegt de index niets: één zin van vijftien
# woorden levert een getal op dat volledig door die ene zin bepaald wordt.
MIN_WOORDEN_VOOR_SCORE = 30


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


def _meet_voorbeeld(pad: Path) -> Leesbaarheid:
    """Meet één voorbeeld, of laat de test falen als er niets te meten valt.

    Bewust falen en niet overslaan. `_assistent_tekst` herkent het antwoord aan
    een regel die met "Assistent" begint en op een dubbele punt eindigt; schrijft
    iemand `**Assistent**`, dan levert de parser niets op. Bij een skip blijft de
    suite groen terwijl een voorbeeld met zinnen van dertig woorden ongemeten
    in de prompt zit - een test die niets meet en toch groen is, is precies de
    fout waar deze suite tegen bestaat.

    Levert dit een fout op, dan klopt óf het bestand óf de parser. Beide horen
    iemands aandacht te krijgen; geen van beide hoort stil te blijven.
    """
    gemeten = meet(_assistent_tekst(pad.read_text()))
    if gemeten is None:
        pytest.fail(
            f"{pad.name}: geen meetbaar assistent-proza gevonden. Het antwoord "
            f"hoort te beginnen na een regel als 'Assistent:' (of 'Assistent "
            f"(toelichting):'). Klopt de opmaak wel, dan loopt de parser in "
            f"_assistent_tekst achter op het bestandsformaat."
        )
    return gemeten


def test_afwijkende_opmaak_levert_geen_meting_op():
    """Legt de grens van de parser vast, want daar hangt _meet_voorbeeld op.

    Zonder deze test is niet zichtbaar dat de herkenning op één schrijfwijze
    berust, en zou iemand de fail-tak voor overdreven kunnen houden.
    """
    afwijkend = (
        "Gebruiker: Test?\n\n"
        "**Assistent**\n"
        "Dit is een opzettelijk veel te lange zin die de grens van vijftien "
        "woorden ruimschoots overschrijdt.\n"
    )
    assert meet(_assistent_tekst(afwijkend)) is None

    herkend = afwijkend.replace("**Assistent**", "Assistent:")
    gemeten = meet(_assistent_tekst(herkend))
    assert gemeten is not None and gemeten.aantal_te_lang == 1


GUARDRAILS = PROMPTS / "blocks" / "shared" / "guardrails.md"

# De zinnen die `guardrails.md` letterlijk voorschrijft ("Zeg met deze vaste
# zin: ..."). Dit is modeluitvoer die in een instructieblok woont, en daarmee de
# blinde vlek van de rest van deze suite: de voorbeelden worden gemeten, de
# blokken niet.
_VASTE_FORMULERING = re.compile(r'vaste (?:zin|formulering)[^"]*"([^"]+)"')


def _vaste_formuleringen() -> list[str]:
    gevonden = _VASTE_FORMULERING.findall(GUARDRAILS.read_text())
    assert gevonden, (
        "geen voorgeschreven zinnen gevonden in guardrails.md. Is de "
        "formulering 'vaste zin' veranderd, dan toetst deze test niets meer "
        "en hoort dat op te vallen in plaats van stil te slagen."
    )
    return gevonden


def test_voorgeschreven_zinnen_houden_zich_aan_de_regels_van_dezelfde_prompt():
    """Wat het model letterlijk moet zeggen, telt als antwoord en niet als regel.

    `format.md` verbiedt de em-dash als HARDE regel en `tone.md` staat maximaal
    vijftien woorden per zin toe. Een blok dat het model opdraagt een zin uit te
    spreken die daar overheen gaat, is geen instructie meer maar een uitzondering
    die zichzelf uitdeelt - en het model heeft geen manier om te zien welke van
    de twee regels wint.
    """
    for zin in _vaste_formuleringen():
        assert "—" not in zin, (
            f"voorgeschreven zin bevat een em-dash, wat format.md verbiedt: {zin}"
        )
        gemeten = meet(zin, alleen_proza=False)
        assert gemeten is not None and gemeten.aantal_te_lang == 0, (
            f"voorgeschreven zin gaat over {MAX_WOORDEN_PER_ZIN} woorden heen:\n  "
            + "\n  ".join(gemeten.te_lange_zinnen if gemeten else [zin])
        )


def test_de_voorbeelden_demonstreren_de_voorgeschreven_zinnen_letterlijk():
    """Anders leert het voorbeeld iets anders dan het blok voorschrijft.

    Precies dat ging hier mis: de zin in `buiten_scope_met_brug.md` werd korter
    gemaakt zonder `guardrails.md` mee te nemen, waarmee dezelfde prompt twee
    verschillende formuleringen ging voorschrijven en demonstreren. Het model
    imiteert dan het voorbeeld en de instructie wordt weer een wens - de fout
    die deze suite hoort te vangen.
    """
    voorbeelden = "\n".join(pad.read_text() for pad in VOORBEELDEN)
    for zin in _vaste_formuleringen():
        assert zin in voorbeelden, (
            f"guardrails.md schrijft deze zin letterlijk voor, maar geen enkel "
            f"voorbeeld demonstreert hem:\n  {zin}"
        )


# De twee NOOIT-regels uit format.md die machinaal te controleren zijn. Beide
# gaan over wat de assistent zégt, dus ze worden op de assistent-tekst getoetst
# en niet op het hele bestand: een tool-resultaat mag "BAG: is_woonfunctie" wel
# bevatten, want zo levert de bron het aan.
_VERBODEN_IN_ANTWOORD = {
    "—": "format.md verbiedt de em-dash als HARDE regel",
    "BAG": "format.md verbiedt BAG als bronvermelding; het hoort onder "
    "'KvK Handelsregister'",
    "Kadaster": "format.md verbiedt Kadaster als bronvermelding",
}


@pytest.mark.parametrize("pad", VOORBEELDEN, ids=lambda p: p.name)
def test_voorbeelden_overtreden_de_nooit_regels_van_format_md_niet(pad):
    """Een voorbeeld dat een verbod overtreedt, leert het model dat verbod weg.

    Dit is dezelfde fout als de vaste zin hierboven, maar dan de andere kant op:
    daar liep het blok uit de pas met het voorbeeld, hier het voorbeeld met het
    blok. `informatieplicht_flow.md` schreef "geen woonfunctie (via BAG)" terwijl
    format.md die bronvermelding letterlijk verbiedt - en de regel er meteen bij
    zet dat BAG-gegevens onder "KvK Handelsregister" vallen, wat op dezelfde
    regel al gebeurde.
    """
    antwoord = _assistent_tekst(pad.read_text())
    for term, reden in _VERBODEN_IN_ANTWOORD.items():
        overtreding = [r.strip() for r in antwoord.splitlines() if term in r]
        assert not overtreding, (
            f"{pad.name}: {term!r} in wat de assistent zegt - {reden}:\n  "
            + "\n  ".join(overtreding)
        )


def test_de_maat_ziet_een_lange_zin():
    """Vangnet op het meetinstrument zelf."""
    kort = meet("Dit is kort. Dat helpt.")
    lang = meet(
        "Deze zin is opzettelijk veel te lang gemaakt zodat de meting hem als "
        "overschrijding van de grens van vijftien woorden aanmerkt."
    )
    assert kort.aantal_te_lang == 0
    assert lang.aantal_te_lang == 1


def test_een_slot_telt_als_een_woord():
    """Bij verzending heeft `slots.py` er al één waarde van gemaakt - de
    `{{...}}`-vorm bestaat alleen in de prompt en moet dus ook als één woord
    meetellen, niet als evenveel woorden als er underscores in de slotnaam
    staan.

    Vóór de normalisatie in `taalniveau._zonder_slots` ging deze zin over de
    grens: veertien gewone woorden plus `{{VOLGENDE_DEADLINE}}` (dat de
    woordregex zonder normalisatie als twee woorden splitst) kwam op zestien.
    """
    veertien_woorden = " ".join(["woord"] * 14)
    zin = f"{veertien_woorden} {{{{VOLGENDE_DEADLINE}}}}."
    gemeten = meet(zin, alleen_proza=False)
    assert gemeten is not None
    assert gemeten.aantal_te_lang == 0


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
    gemeten = _meet_voorbeeld(pad)
    assert gemeten.aantal_te_lang == 0, (
        f"{pad.name}: {gemeten.aantal_te_lang} zin(nen) boven "
        f"{MAX_WOORDEN_PER_ZIN} woorden — het model imiteert dit:\n  "
        + "\n  ".join(gemeten.te_lange_zinnen)
    )


@pytest.mark.parametrize("pad", VOORBEELDEN, ids=lambda p: p.name)
def test_voorbeeldantwoorden_gebruiken_ook_alledaagse_woorden(pad):
    """De andere helft van B1: woordmoeilijkheid, niet alleen zinslengte.

    Flesch-Douma telt beide. Alleen op zinslengte toetsen laat de helft van de
    maat los, en die helft loopt de andere kant op: een lange zin opknippen
    zonder de vaktermen aan te pakken duwt de woorddichtheid juist omhoog. Dat
    is hier gebeurd - `regelrecht_no_obligation.md` zakte van 58,8 naar 56,9
    terwijl er een te lange zin uit ging.

    Het is een ratel per bestand en geen gezamenlijke drempel; zie de toelichting
    bij BASISSCORE. Een ratel bewijst geen B1 - hij bewijst alleen dat het niet
    slechter werd.
    """
    gemeten = _meet_voorbeeld(pad)
    if gemeten.woorden < MIN_WOORDEN_VOOR_SCORE:
        pytest.skip(
            f"{gemeten.woorden} woorden gemeten - te weinig voor een "
            f"leesbaarheidsindex. Flesch op een enkele zin is ruis: een getal "
            f"dat stellig oogt en niets zegt."
        )
    ondergrens = BASISSCORE[pad.name] - MARGE
    assert gemeten.score >= ondergrens, (
        f"{pad.name}: score {gemeten.score:.1f}, was {BASISSCORE[pad.name]:.1f} "
        f"({gemeten.woorden} woorden, gemiddeld "
        f"{gemeten.gemiddelde_zinslengte:.1f} woorden per zin) — de zinnen zijn "
        f"kort genoeg, de woorden niet."
    )


def test_elk_voorbeeld_heeft_een_vastgelegde_basisscore():
    """Een nieuw voorbeeld hoort een bewuste ondergrens te krijgen.

    Zonder deze test zou een voorbeeld dat niet in BASISSCORE staat een KeyError
    geven op een plek waar niemand hem verwacht, of - erger - stil buiten de
    ratel vallen als iemand dat met een .get() "oplost".
    """
    gemeten = {
        pad.name: _meet_voorbeeld(pad)
        for pad in VOORBEELDEN
    }
    hoort_erin = {
        naam
        for naam, meting in gemeten.items()
        if meting.woorden >= MIN_WOORDEN_VOOR_SCORE
    }
    assert hoort_erin == set(BASISSCORE), (
        f"BASISSCORE loopt niet gelijk met de voorbeelden. Ontbreekt: "
        f"{sorted(hoort_erin - set(BASISSCORE))}. Te veel: "
        f"{sorted(set(BASISSCORE) - hoort_erin)}."
    )

"""Het model moet wéten welke bron eruit ligt, anders praat het eroverheen.

`server_status` wist bij het starten al welke MCP-server niet opkwam, maar die
kennis bereikte het model niet: het kon dus over een bron praten die er niet is,
of terugvallen op eigen kennis. Deze test bewaakt de doorgifte van host naar
systeemprompt, en dat het blok verdwijnt zodra alles draait.
"""

import vlam_host
from prompts.composer import compose_system_prompt

KOP = "BESCHIKBAARHEID VAN BRONNEN"
BRONNEN = ("kvk", "koop", "regelrecht", "rvo", "netbeheerder")


def _host_met_status(status: dict) -> vlam_host.VLAMHost:
    host = vlam_host.VLAMHost()
    host.server_status = status
    return host


def test_alles_verbonden_geeft_geen_extra_blok():
    host = _host_met_status({"kvk": "verbonden", "koop": "verbonden"})
    assert host.bronnen_offline == []
    assert KOP not in host._system_prompt("claude", has_tools=True)


def test_uitgevallen_bron_staat_met_alternatief_in_de_prompt():
    host = _host_met_status({"kvk": "verbonden", "koop": "niet beschikbaar"})
    assert host.bronnen_offline == ["koop"]

    prompt = host._system_prompt("claude", has_tools=True)
    assert KOP in prompt
    assert "KOOP Regelingenbank" in prompt
    # Zonder alternatief is "de bron ligt eruit" nog steeds een doodlopend pad.
    assert "wetten.overheid.nl" in prompt
    # En de bron die het wél doet hoort er niet bij te staan.
    kop_tot_eind = prompt[prompt.index(KOP) :]
    assert "Handelsregister -" not in kop_tot_eind


def test_cli_paden_melden_de_mcp_status_niet():
    """CLI gebruikt een ander transport; de MCP-status zegt daar niets over."""
    host = _host_met_status({"koop": "niet beschikbaar"})
    prompt = host._system_prompt("claude", has_tools=True, bronnen_offline=[])
    assert KOP not in prompt


def test_composer_werkt_ook_zonder_het_nieuwe_argument():
    """Achterwaartse compatibiliteit: bestaande aanroepen blijven werken."""
    assert KOP not in compose_system_prompt("vlam", True)
    assert KOP not in compose_system_prompt("vlam", False)


def test_zonder_tools_maar_met_uitgevallen_bronnen_geen_eigen_kennis_instructie():
    """`no_tools.md` en het statusblok zeggen het tegenovergestelde.

    Het eerste draagt op om op eigen kennis te antwoorden, het tweede verbiedt
    dat juist. Samen in één prompt is slechter dan één van beide, dus vervangt
    het statusblok de andere.
    """
    host = _host_met_status(dict.fromkeys(BRONNEN, "niet beschikbaar"))
    prompt = host._system_prompt("claude", has_tools=False)

    assert "GEEN ENKELE BRON BESCHIKBAAR" in prompt
    assert "Beantwoord vragen op basis van je eigen kennis" not in prompt


def test_voorbeelden_met_een_uitgevallen_bron_verdwijnen():
    """Een voorbeeld is het sterkste stuursignaal in deze prompt.

    Een voorbeeld dat KOOP aanroept terwijl KOOP eruit ligt, demonstreert precies
    wat het statusblok net verbood.
    """
    host = _host_met_status({**dict.fromkeys(BRONNEN, "verbonden"), "koop": "niet beschikbaar"})
    prompt = host._system_prompt("claude", has_tools=True)
    voorbeelden = prompt.split("voorbeelden van goede antwoorden")[-1]

    assert "koop__" not in voorbeelden and "koop://" not in voorbeelden
    assert "kvk__" in voorbeelden, "voorbeelden van werkende bronnen blijven staan"


def test_bij_uitval_blijven_de_afwijzings_voorbeelden_staan_met_waarschuwing():
    """Die twee demonstreren een vórm, geen bron-flow: ze roepen niets aan.

    Ze wegfilteren zou het sterkste stuursignaal voor scope-detectie weghalen in
    precies de stand waarin een gebruiker het vaakst vastloopt. Hun brugvraag
    hangt wél aan een bron, dus die staat als `bronnen-optioneel` en levert een
    waarschuwing op in plaats van het hele voorbeeld te laten vallen.
    """
    host = _host_met_status(dict.fromkeys(BRONNEN, "niet beschikbaar"))
    prompt = host._system_prompt("claude", has_tools=False)

    assert "arbeidsrecht" in prompt, "het afwijzings-voorbeeld hoort te blijven"
    assert "niet beschikbaar. Sla de stap" in prompt, "mét de waarschuwing"
    assert "kvk__mijn_bedrijf" not in prompt, "geen tool-aanroepen voordoen zonder tools"
    # De instructie zelf blijft ook, dus het gedrag is dubbel gestuurd.
    assert "BENOEM het onderwerp" in prompt
    assert "GEEN ENKELE BRON BESCHIKBAAR" in prompt


# Woorden waarmee een blok een bron belooft zónder de toolnaam te noemen. Juist
# die beloftes zijn de reden dat de marker expliciet is en niet uit tool-namen
# wordt afgeleid; zonder deze lijst bewaakt de test precies dat niet.
# Waaraan je ziet dat een blok een cóncrete bron belooft: de toolnaam, of de
# naam waarmee de assistent die bron aan de gebruiker aanbiedt. Bewust NIET de
# domeinwoorden ("subsidies", "regelgeving"): die beschrijven het taakgebied en
# blijven waar ook als een bron eruit ligt. Ook niet elke losse vermelding van
# een naam: "overrides={\"RVO\": ...}" is een parameter van RegelRecht, en een
# wetsartikel dat naar RVO verwijst is een feit, geen aanbod.
BELOFTEN = {
    "kvk": ("Handelsregister", "kvk__"),
    "koop": ("KOOP Regelingenbank", "koop__", "koop://"),
    "regelrecht": ("RegelRecht", "regelrecht__"),
    "rvo": ("rvo__", "RVO-tool", "aan RVO", "bij RVO"),
    "netbeheerder": ("Business Wallet", "netbeheerder__"),
}


def _blokken_met_marker():
    from pathlib import Path

    from prompts.composer import BLOCKS_DIR, EXAMPLES_DIR

    return [
        *sorted(Path(EXAMPLES_DIR).glob("*.md")),
        *sorted((Path(BLOCKS_DIR) / "shared" / "domain").glob("*.md")),
    ]


def test_de_bronmarkers_kloppen_met_de_inhoud():
    """Elk blok dat een bron noemt, moet die bron ook declareren.

    De marker is de enige bron van waarheid voor de filtering; loopt hij uit de
    pas met de inhoud, dan belooft de assistent stilzwijgend iets wat hij niet
    kan waarmaken. Er wordt bewust óók op gewone taal gecontroleerd ("uw
    bedrijfsgegevens uit het Handelsregister"), want dat is precies waarom de
    marker expliciet is en niet uit tool-namen wordt afgeleid.
    """
    from prompts.composer import _bronnen_van_voorbeeld, _optionele_bronnen

    for pad in _blokken_met_marker():
        tekst = pad.read_text(encoding="utf-8")
        # Een bron mag als kern- óf als optionele bron gedeclareerd staan; beide
        # zorgen dat de composer weet dat het blok die bron aanstipt.
        gedeclareerd = _bronnen_van_voorbeeld(tekst) | _optionele_bronnen(tekst)
        # De markers zelf tellen niet mee als belofte.
        inhoud = tekst.split("-->")[-1]
        for bron, woorden in BELOFTEN.items():
            if any(woord in inhoud for woord in woorden):
                assert bron in gedeclareerd, (
                    f"{pad.name} noemt {bron} maar declareert die niet in de "
                    "`<!-- bronnen: ... -->`-marker; het blok blijft dan staan "
                    "terwijl die bron eruit ligt"
                )


def test_elk_blok_met_filtering_heeft_een_marker():
    """Zonder marker glipt een blok ongefilterd langs de beschikbaarheidscheck."""
    for pad in _blokken_met_marker():
        assert pad.read_text(encoding="utf-8").lstrip().startswith("<!-- bronnen:"), (
            f"{pad.name} mist de `<!-- bronnen: ... -->`-marker"
        )

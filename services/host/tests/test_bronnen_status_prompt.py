"""Het model moet wéten welke bron eruit ligt, anders praat het eroverheen.

`server_status` wist bij het starten al welke MCP-server niet opkwam, maar die
kennis bereikte het model niet: het kon dus over een bron praten die er niet is,
of terugvallen op eigen kennis. Deze test bewaakt de doorgifte van host naar
systeemprompt, en dat het blok verdwijnt zodra alles draait.
"""

import vlam_host
from prompts.composer import compose_system_prompt

KOP = "BESCHIKBAARHEID VAN BRONNEN"


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

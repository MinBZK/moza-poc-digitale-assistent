"""De foutcatalogus moet volledig en actionabel zijn.

De belofte van dit ticket is dat élk foutscenario een eigen melding heeft met
wat er misging én wat de gebruiker kan doen. Twee manieren waarop die belofte
stilletjes kan sneuvelen, allebei hier afgedekt:

1. Iemand voegt een melding toe zonder handelingsperspectief, of met een
   nietszeggende tekst ("er ging iets mis").
2. Een bronserver krijgt een nieuwe foutcode die de catalogus niet kent. De
   gebruiker ziet dan alsnog een generieke melding. De scan hieronder leest de
   échte broncode van de servers, net als `test_kvk_injectie_dekking.py`, zodat
   dit niet aan een handmatig bijgehouden lijstje hangt.
"""

import ast
from pathlib import Path

import pytest

from errors import (
    BRON_ALTERNATIEF,
    BRON_LABELS,
    FOUTEN,
    classificeer_tool_fout,
    maak_fout,
    naar_event,
    naar_llm,
)

SERVICES = Path(__file__).resolve().parent.parent.parent
BRONBESTANDEN = [
    *sorted((SERVICES / "mcp").glob("*/server.py")),
    SERVICES / "host" / "cli_executor.py",
    SERVICES / "host" / "vlam_host.py",
    SERVICES / "host" / "mcp_client.py",
]

# Formuleringen die precies het probleem zijn dat dit ticket oplost: ze vertellen
# de gebruiker niets over wat er gebeurde of wat hij eraan kan doen.
NIETSZEGGEND = (
    "iets ging mis",
    "er is een fout opgetreden",
    "onbekende fout",
    "er ging iets fout",
    "unknown error",
    "something went wrong",
)


def _foutcodes_uit_broncode(pad: Path) -> set[str]:
    """Verzamel elke code die dit bestand als `{"error": ...}` uitstuurt.

    Via de AST en niet via een regex, omdat KOOP de code met een inline
    if-expressie kiest (`"SOURCE_UNAVAILABLE" if ... else "NIET_GEVONDEN"`).
    """
    gevonden: set[str] = set()

    def _constanten(node) -> set[str]:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return {node.value}
        if isinstance(node, ast.IfExp):
            return _constanten(node.body) | _constanten(node.orelse)
        return set()

    boom = ast.parse(pad.read_text(encoding="utf-8"))
    for node in ast.walk(boom):
        if not isinstance(node, ast.Dict):
            continue
        for sleutel, waarde in zip(node.keys, node.values, strict=True):
            if isinstance(sleutel, ast.Constant) and sleutel.value == "error":
                gevonden |= _constanten(waarde)
    return gevonden


@pytest.mark.parametrize("code", sorted(FOUTEN))
def test_elke_melding_zegt_wat_er_gebeurde_en_wat_te_doen(code):
    melding = FOUTEN[code]
    assert melding.code == code, "de sleutel en het code-veld moeten gelijk zijn"
    assert melding.bericht.strip(), f"{code} heeft geen bericht"
    assert melding.actie.strip(), f"{code} heeft geen actie"
    # Een actie is een aanwijzing, geen los woord.
    assert len(melding.actie) >= 20, f"{code} geeft geen handelingsperspectief"
    # Aanhalingstekens eraf: een actie mag eindigen op een voorbeeldvraag.
    assert melding.bericht.rstrip("'\" ").endswith((".", "?", ":")), (
        f"{code}: bericht is geen zin"
    )
    assert melding.actie.rstrip("'\" ").endswith((".", "?")), f"{code}: actie is geen zin"


@pytest.mark.parametrize("code", sorted(FOUTEN))
def test_geen_nietszeggende_formuleringen(code):
    tekst = maak_fout(code).tekst.lower()
    for zinloos in NIETSZEGGEND:
        assert zinloos not in tekst, f"{code} valt terug op '{zinloos}'"


@pytest.mark.parametrize("code", sorted(FOUTEN))
def test_geen_openstaande_placeholders(code):
    """Elke melding moet ook zónder invulwaarden een lopende zin opleveren."""
    melding = maak_fout(code)
    for deel in (melding.bericht, melding.actie):
        assert "{" not in deel and "}" not in deel, f"{code} houdt een placeholder over"
        assert "  " not in deel, f"{code} heeft een gat in de zin"


@pytest.mark.parametrize("bron", sorted(BRON_LABELS))
def test_elke_bron_heeft_label_en_alternatief(bron):
    """Zonder alternatief is 'de bron ligt eruit' nog steeds een doodlopend pad."""
    assert BRON_LABELS[bron].strip()
    assert BRON_ALTERNATIEF[bron].strip()


@pytest.mark.parametrize("pad", BRONBESTANDEN, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_elke_uitgestuurde_foutcode_staat_in_de_catalogus(pad):
    codes = _foutcodes_uit_broncode(pad)
    ontbreekt = sorted(codes - set(FOUTEN))
    assert not ontbreekt, (
        f"{pad.relative_to(SERVICES)} stuurt foutcode(s) {ontbreekt} uit die niet in "
        "de catalogus staan; de gebruiker krijgt daarvoor geen specifieke melding. "
        "Voeg ze toe aan FOUTEN in services/host/errors.py."
    )


def test_scan_vindt_de_bekende_codes():
    """Vangnet onder de scan zelf: een stille lege uitkomst is geen bewijs."""
    codes = set()
    for pad in BRONBESTANDEN:
        codes |= _foutcodes_uit_broncode(pad)
    assert {"SOURCE_UNAVAILABLE", "NIET_GEVONDEN", "ONTBREKEND_VELD"} <= codes


def test_bronfout_noemt_de_bron_en_het_alternatief():
    melding = classificeer_tool_fout(
        "koop__zoek_regelgeving", '{"error": "SOURCE_UNAVAILABLE"}'
    )
    assert melding.code == "SOURCE_UNAVAILABLE"
    assert "KOOP" in melding.tekst
    assert "wetten.overheid.nl" in melding.tekst


def test_geslaagd_resultaat_levert_geen_melding():
    assert classificeer_tool_fout("kvk__mijn_bedrijf", '{"data": {"naam": "Noon"}}') is None
    assert classificeer_tool_fout("koop__lees_regeling", "gewone tekst") is None


def test_event_en_llm_vorm_dragen_dezelfde_melding():
    fout = maak_fout("SOURCE_UNAVAILABLE", bron="rvo")
    event = naar_event(fout)
    assert event["type"] == "error"
    assert event["code"] == "SOURCE_UNAVAILABLE"
    # `message` blijft de volledige zin, zodat een frontend die alleen dat veld
    # kent niets hoeft te veranderen.
    assert event["message"] == f"{event['bericht']} {event['actie']}"
    assert fout.tekst in naar_llm(fout)


def test_onbekende_code_klapt_niet():
    """Een fout in de foutafhandeling mag het gesprek niet alsnog breken."""
    melding = maak_fout("BESTAAT_NIET")
    assert melding.code == "LLM_ONBEKEND"
    assert melding.actie.strip()

"""De waarden waarop RegelRecht rekende, bereiken het model.

De engine levert de gebruikte waarden onder `input` en de constanten onder
`rule_spec.properties.definitions`. Dat laatste is alleen gevuld bij een aanroep
met lege parameters - precies de aanroep die het model nooit doet. Zonder dit
doorgeefluik moet het model getallen noemen die het niet heeft, terwijl de
prompt verbiedt ze uit eigen kennis te halen.
"""

import importlib.util
from pathlib import Path

import pytest

SERVER = (
    Path(__file__).resolve().parents[2] / "mcp" / "regelrecht" / "server.py"
)


@pytest.fixture(scope="module")
def regelrecht():
    spec = importlib.util.spec_from_file_location("mcp_regelrecht", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gebruikte_waarden_komen_mee_zonder_dollarprefix(regelrecht):
    structured = {
        "requirements_met": True,
        "output": {"heeft_informatieplicht": True},
        "input": {
            "$JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 420000,
            "$DREMPEL_ELEKTRICITEIT_KWH": 50000,
        },
    }
    resultaat = regelrecht._simplify_result(structured)
    assert resultaat["gebruikte_waarden"] == {
        "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 420000,
        "DREMPEL_ELEKTRICITEIT_KWH": 50000,
    }


def test_drempelwaarden_komen_uit_de_meegegeven_definities(regelrecht):
    """De echte engine geeft `definitions` leeg terug bij gevulde parameters.

    Dat is het geval dat telt: dit is de aanroep die het model doet.
    """
    structured = {
        "requirements_met": True,
        "output": {},
        "input": {},
        "rule_spec": {"properties": {"definitions": {}}},
    }
    resultaat = regelrecht._simplify_result(
        structured, definities={"DREMPEL_GAS_M3": 25000}
    )
    assert resultaat["drempelwaarden"] == {"DREMPEL_GAS_M3": 25000}


def test_zonder_input_geen_leeg_veld(regelrecht):
    """Een leeg veld suggereert dat er niets gebruikt is, en dat is iets anders
    dan dat we het niet weten."""
    resultaat = regelrecht._simplify_result(
        {"requirements_met": False, "output": {}, "input": {}}
    )
    assert "gebruikte_waarden" not in resultaat

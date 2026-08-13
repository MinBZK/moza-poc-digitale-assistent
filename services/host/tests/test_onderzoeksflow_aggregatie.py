"""De aggregatie over meerdere runs, los van de LLM-calls.

Het script zelf kost echte LLM-beurten en hoort niet in de suite. De optelsom
eroverheen is gewone code en moet wel gedekt zijn: die bepaalt of we straks
"vijf van de vijf" of "vier van de vijf" concluderen.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from onderzoeksflow import Uitkomst, aggregeer


def test_aggregeer_telt_per_controle_over_runs():
    runs = [
        [Uitkomst("stap4", True, "formulier"), Uitkomst("stap6", True, "indienen")],
        [Uitkomst("stap4", False, "formulier"), Uitkomst("stap6", True, "indienen")],
    ]
    resultaat = aggregeer(runs)
    assert resultaat["formulier"] == "1/2"
    assert resultaat["indienen"] == "2/2"


def test_aggregeer_bij_nul_runs_geeft_lege_samenvatting():
    assert aggregeer([]) == {}


def test_aggregeer_kent_een_controle_die_maar_in_een_run_voorkwam():
    """Een run die halverwege afbreekt levert minder controles op.

    Dan mag de noemer niet stilzwijgend het aantal runs worden: dat maakt een
    afgebroken run tot een gefaalde controle en dat is iets anders.
    """
    runs = [
        [Uitkomst("stap4", True, "formulier")],
        [],
    ]
    assert aggregeer(runs) == {"formulier": "1/1"}

"""De regel stuurt, de host haalt op.

De engine declareert laag voor laag wat hij mist. De lus draait door zolang hij
zelf verder kan en stopt waar toestemming nodig is of waar alleen de ondernemer
het antwoord heeft.
"""

import json

from regelloop import volg_regel


def _engine(stappen):
    """Een nep-engine die per aanroep de volgende stap teruggeeft."""
    beurten = iter(stappen)

    async def call_tool(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": next(beurten)})
        if naam == "kvk__mijn_bedrijf":
            return json.dumps({"data": {"is_woonfunctie": False}})
        raise AssertionError(f"onverwachte tool: {naam}")

    return call_tool


async def test_lus_haalt_op_wat_hij_zelf_kan():
    """Woonfunctie komt uit de KvK; daar is geen toestemming voor nodig."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"voldoet_aan_voorwaarden": True, "uitkomsten": {"heeft_informatieplicht": True}},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
    )
    assert uit.klaar is True
    assert uit.resultaat["uitkomsten"]["heeft_informatieplicht"] is True


async def test_lus_stopt_bij_een_bron_die_toestemming_vraagt():
    """PDR-008: geen bron vóór akkoord. De lus raadpleegt de wallet niet."""
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "JAARLIJKS_GASVERBRUIK_M3"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "toestemming"


async def test_lus_stopt_bij_iets_dat_alleen_de_ondernemer_weet():
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "HEEFT_KOELINSTALLATIE"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/maatregelen",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "opgave"


async def test_onbekend_veld_stopt_de_lus_in_plaats_van_te_raden():
    call_tool = _engine([
        {"ontbrekende_gegevens": [{"naam": "OMZET_2025"}]},
    ])
    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.klaar is False
    assert uit.wacht_op == "onbekend"
    assert "OMZET_2025" in uit.reden


async def test_lus_loopt_niet_eindeloos_als_een_bron_niets_oplevert():
    """Een bron die het gevraagde veld niet levert mag geen oneindige lus geven.

    De KvK-tool geeft hier geen `is_woonfunctie` terug (in tegenstelling tot
    `_engine`), dus blijft de wet elke ronde opnieuw om IS_WOONFUNCTIE vragen.
    Zonder rondegrens draait dit voor altijd door.
    """
    beurten = iter([
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
        {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]},
    ])

    async def _leeg_kvk(naam, arguments):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": next(beurten)})
        if naam == "kvk__mijn_bedrijf":
            return json.dumps({"data": {"naam": "Kwekerij De Bloesem"}})
        raise AssertionError(f"onverwachte tool: {naam}")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=_leeg_kvk,
        toestemming=True,
    )
    assert uit.klaar is False

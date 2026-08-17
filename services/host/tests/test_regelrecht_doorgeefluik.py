"""De waarden waarop RegelRecht rekende, bereiken het model.

De engine levert de gebruikte waarden onder `input` en de constanten onder
`rule_spec.properties.definitions`. Dat laatste is alleen gevuld bij een aanroep
met lege parameters - precies de aanroep die het model nooit doet. Zonder dit
doorgeefluik moet het model getallen noemen die het niet heeft, terwijl de
prompt verbiedt ze uit eigen kennis te halen.
"""

import asyncio
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


def test_missing_required_bereikt_het_model(regelrecht):
    """Het onderscheid tussen "geldt niet" en "nog onvolledig" zit in dit veld.

    `requirements_met: False` alléén is dubbelzinnig: dat geeft zowel een
    definitieve negatieve uitkomst als een onvolledige toets. `_simplify_result`
    liet `missing_required` tot nu toe onder de tafel vallen.
    """
    resultaat = regelrecht._simplify_result(
        {"requirements_met": False, "missing_required": False, "output": {}, "input": {}}
    )
    assert resultaat["missing_required"] is False


def test_missing_required_ontbreekt_als_de_engine_het_niet_meegeeft(regelrecht):
    """Geen stille default hier: geeft de engine het veld niet mee (oudere
    servervorm), dan moet de host-kant zelf de voorzichtige aanname kunnen
    maken - niet deze functie die alvast "niets mist" invult."""
    resultaat = regelrecht._simplify_result({"requirements_met": False})
    assert "missing_required" not in resultaat


# --- _definities_voor: caching, en juist NIET cachen bij een mislukte ophaal ---


def _rpc_structuredcontent(definities: dict) -> dict:
    return {
        "structuredContent": {
            "rule_spec": {"properties": {"definitions": definities}},
        }
    }


def test_definities_voor_cachet_bij_succes(regelrecht, monkeypatch):
    """Een tweede aanroep voor dezelfde wet doet geen nieuwe RPC."""
    regelrecht._definities_cache.clear()
    aanroepen = []

    async def nep_rpc(method, params):
        aanroepen.append(params)
        return _rpc_structuredcontent({"DREMPEL_GAS_M3": 25000})

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    eerste = asyncio.run(regelrecht._definities_voor("wet/succes", "RVO"))
    tweede = asyncio.run(regelrecht._definities_voor("wet/succes", "RVO"))

    assert eerste == {"DREMPEL_GAS_M3": 25000}
    assert tweede == {"DREMPEL_GAS_M3": 25000}
    assert len(aanroepen) == 1


def test_definities_voor_cachet_niet_bij_falen(regelrecht, monkeypatch):
    """Een mislukte ophaal geeft {} terug, maar legt de wet niet blijvend plat:
    een volgende aanroep probeert opnieuw in plaats van uit een lege cache te
    lezen."""
    regelrecht._definities_cache.clear()
    aanroepen = []

    async def nep_rpc_faalt(method, params):
        aanroepen.append(params)
        raise RuntimeError("RegelRecht RPC fout: tijdelijk niet bereikbaar")

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc_faalt)
    resultaat = asyncio.run(regelrecht._definities_voor("wet/falen", "RVO"))

    assert resultaat == {}
    assert "RVO/wet/falen" not in regelrecht._definities_cache

    asyncio.run(regelrecht._definities_voor("wet/falen", "RVO"))
    assert len(aanroepen) == 2  # opnieuw geprobeerd, niet uit cache beantwoord


def test_definities_voor_herstelt_na_falen(regelrecht, monkeypatch):
    """Na een mislukte en daarna geslaagde ophaal staat de goede waarde in de
    cache."""
    regelrecht._definities_cache.clear()
    pogingen = {"aantal": 0}

    async def nep_rpc_wisselend(method, params):
        pogingen["aantal"] += 1
        if pogingen["aantal"] == 1:
            raise RuntimeError("tijdelijke hik")
        return _rpc_structuredcontent({"DREMPEL_ELEKTRICITEIT_KWH": 50000})

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc_wisselend)
    eerste = asyncio.run(regelrecht._definities_voor("wet/herstel", "RVO"))
    tweede = asyncio.run(regelrecht._definities_voor("wet/herstel", "RVO"))

    assert eerste == {}
    assert tweede == {"DREMPEL_ELEKTRICITEIT_KWH": 50000}
    assert regelrecht._definities_cache["RVO/wet/herstel"] == {
        "DREMPEL_ELEKTRICITEIT_KWH": 50000
    }

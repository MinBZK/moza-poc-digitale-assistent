"""EML-maatregelbepaling: twee-staps-flow, engine-mapping en fallback.

De regelrecht-server bepaalt EML-maatregelen via de poc-machine-law engine
(wet omgevingswet/energiebesparing/maatregelen) en valt terug op een lokale
evaluatie als de engine onbereikbaar is. Deze tests draaien zonder netwerk.
"""

import asyncio
import importlib.util
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"


def _load_regelrecht():
    pad = MCP_DIR / "regelrecht" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_regelrecht_server", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RULE_SPEC = {
    "properties": {
        "parameters": [
            {
                "name": "HEEFT_KOELINSTALLATIE",
                "description": "Heeft het bedrijf een koel- of vriesinstallatie (koelcel, koelmeubel)?",
            },
            {
                "name": "HEEFT_AFZUIGINSTALLATIE",
                "description": "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?",
            },
        ],
        "output": [
            {
                "name": "eml_gf4_van_toepassing",
                "description": "Gebouwen, Binnenverlichting — Vervang gloei-, halogeen- en spaarlampen door LED-lampen",
            },
            {
                "name": "eml_fd3_van_toepassing",
                "description": "Faciliteiten, Productkoeling — Pas nachtafdekking toe bij semi-verticale koelmeubels",
            },
        ],
    }
}

ENGINE_RESULT_COMPLEET = {
    "structuredContent": {
        "success": True,
        "requirements_met": True,
        "missing_required": False,
        "output": {
            "eml_gf4_van_toepassing": True,
            "eml_fd3_van_toepassing": False,
        },
        "rule_spec": RULE_SPEC,
    }
}

ENGINE_RESULT_FEITEN_ONTBREKEN = {
    "structuredContent": {
        "success": True,
        "requirements_met": False,
        "missing_required": True,
        "output": {},
        "rule_spec": RULE_SPEC,
    }
}


def test_eml_lijst_mapt_engine_outputs_naar_maatregelen():
    regelrecht = _load_regelrecht()
    lijst = regelrecht._eml_lijst(ENGINE_RESULT_COMPLEET["structuredContent"])
    per_code = {m["code"]: m for m in lijst}
    assert per_code["GF4"]["van_toepassing"] is True
    assert per_code["GF4"]["naam"] == (
        "Vervang gloei-, halogeen- en spaarlampen door LED-lampen"
    )
    assert per_code["GF4"]["categorie"] == "Gebouwen, Binnenverlichting"
    assert per_code["FD3"]["van_toepassing"] is False


def test_eml_vragen_uit_rule_spec_minus_geleverde_feiten():
    regelrecht = _load_regelrecht()
    vragen = regelrecht._eml_vragen(RULE_SPEC, {"HEEFT_KOELINSTALLATIE": True})
    assert vragen == [
        {
            "naam": "HEEFT_AFZUIGINSTALLATIE",
            "vraag": "Heeft het bedrijf een afzuiginstallatie (keuken of ruimteventilatie)?",
        }
    ]


def test_maatregelen_zonder_feiten_geeft_vragen_uit_engine(monkeypatch):
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        assert params["arguments"]["law"] == regelrecht.EML_LAW
        return ENGINE_RESULT_FEITEN_ONTBREKEN

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(regelrecht._maatregelen({}))
    assert fallback is False
    namen = [v["naam"] for v in data["benodigde_feiten"]]
    assert namen == ["HEEFT_KOELINSTALLATIE", "HEEFT_AFZUIGINSTALLATIE"]


def test_maatregelen_met_feiten_geeft_lijst_uit_engine(monkeypatch):
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        assert params["arguments"]["parameters"] == {
            "HEEFT_KOELINSTALLATIE": True,
            "HEEFT_AFZUIGINSTALLATIE": False,
        }
        return ENGINE_RESULT_COMPLEET

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(
        regelrecht._maatregelen(
            {"feiten": {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": False}}
        )
    )
    assert fallback is False
    assert {m["code"] for m in data["maatregelen"]} == {"GF4", "FD3"}


def test_maatregelen_fallback_bij_onbereikbare_engine(monkeypatch):
    regelrecht = _load_regelrecht()

    async def kapot(method, params):
        raise regelrecht.httpx.ConnectError("engine offline")

    monkeypatch.setattr(regelrecht, "_rpc_call", kapot)

    # Stap 1: vragen komen dan uit de lokale fallback
    data, fallback = asyncio.run(regelrecht._maatregelen({}))
    assert fallback is True
    assert [v["naam"] for v in data["benodigde_feiten"]] == [
        "HEEFT_KOELINSTALLATIE",
        "HEEFT_AFZUIGINSTALLATIE",
    ]

    # Stap 2: lijst komt dan uit de lokale fallback (alle 7 subset-maatregelen)
    data, fallback = asyncio.run(
        regelrecht._maatregelen(
            {"feiten": {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": True}}
        )
    )
    assert fallback is True
    codes = {m["code"] for m in data["maatregelen"]}
    assert codes == {"GC1", "GC3", "GF4", "FD3", "FD7", "FE4", "GD1"}
    assert all(m["van_toepassing"] for m in data["maatregelen"])


def test_maatregelen_fallback_bij_onbruikbare_engine_response(monkeypatch):
    regelrecht = _load_regelrecht()

    for kapotte_response in ({}, {"structuredContent": {"success": False}}):

        async def nep_rpc(method, params, _response=kapotte_response):
            return _response

        monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
        data, fallback = asyncio.run(
            regelrecht._maatregelen(
                {"feiten": {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": True}}
            )
        )
        assert fallback is True
        assert len(data["maatregelen"]) == 7


def test_maatregelen_fallback_bij_missing_required_zonder_rule_spec(monkeypatch):
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        return {
            "structuredContent": {
                "success": True,
                "missing_required": True,
                "output": {},
                "rule_spec": {},
            }
        }

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(regelrecht._maatregelen({}))
    assert fallback is True
    assert [v["naam"] for v in data["benodigde_feiten"]] == [
        "HEEFT_KOELINSTALLATIE",
        "HEEFT_AFZUIGINSTALLATIE",
    ]


def test_execute_law_dispatcht_eml_naar_maatregelen(monkeypatch):
    """De generieke tool stuurt de maatregelen-wet door naar de EML-flow.

    De parameters ZIJN bij die wet de feiten; ze worden als zodanig
    doorgegeven aan de engine.
    """
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        assert params["arguments"]["law"] == regelrecht.EML_LAW
        assert params["arguments"]["parameters"] == {
            "HEEFT_KOELINSTALLATIE": True,
            "HEEFT_AFZUIGINSTALLATIE": False,
        }
        return ENGINE_RESULT_COMPLEET

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(
        regelrecht._execute_law(
            {
                "law": regelrecht.EML_LAW,
                "parameters": {
                    "HEEFT_KOELINSTALLATIE": True,
                    "HEEFT_AFZUIGINSTALLATIE": False,
                },
            }
        )
    )
    assert fallback is False
    assert {m["code"] for m in data["maatregelen"]} == {"GF4", "FD3"}


def test_execute_law_generieke_wet_gaat_rechtstreeks_naar_engine(monkeypatch):
    """Niet-EML-wetten (bv. informatieplicht) gaan generiek naar de engine.

    parameters en overrides worden ongewijzigd doorgegeven; de structured
    response wordt vereenvoudigd. Geen fallback voor deze wetten.
    """
    regelrecht = _load_regelrecht()
    gezien = {}

    async def nep_rpc(method, params):
        gezien.update(params["arguments"])
        return {
            "structuredContent": {
                "requirements_met": True,
                "output": {"informatieplicht": True},
                "law_metadata": {"name": "informatieplicht"},
            }
        }

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data, fallback = asyncio.run(
        regelrecht._execute_law(
            {
                "law": "omgevingswet/energiebesparing/informatieplicht",
                "parameters": {"KVK_NUMMER": "85234567"},
                "overrides": {"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 61250}},
            }
        )
    )
    assert fallback is False
    assert gezien["law"] == "omgevingswet/energiebesparing/informatieplicht"
    assert gezien["parameters"] == {"KVK_NUMMER": "85234567"}
    assert gezien["overrides"] == {"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 61250}}
    assert data["voldoet_aan_voorwaarden"] is True
    assert data["uitkomsten"] == {"informatieplicht": True}


def test_execute_law_zonder_law_geeft_nette_fout():
    regelrecht = _load_regelrecht()
    data, fallback = asyncio.run(regelrecht._execute_law({}))
    assert fallback is False
    assert data["error"] == "ONTBREKEND_VELD"


def test_maatregelen_normaliseert_feiten_keys_en_negeert_niet_boolse_waarden(
    monkeypatch,
):
    regelrecht = _load_regelrecht()
    gezien = {}

    async def nep_rpc(method, params):
        gezien.update(params["arguments"]["parameters"])
        return ENGINE_RESULT_COMPLEET

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    asyncio.run(
        regelrecht._maatregelen(
            {
                "feiten": {
                    "heeft_koelinstallatie": True,  # lowercase -> genormaliseerd
                    "HEEFT_AFZUIGINSTALLATIE": "nee",  # string -> geen antwoord
                }
            }
        )
    )
    assert gezien == {"HEEFT_KOELINSTALLATIE": True}

    # Fallback-route: zelfde normalisatie; de string-waarde telt niet als
    # antwoord, dus die vraag wordt opnieuw gesteld.
    async def kapot(method, params):
        raise regelrecht.httpx.ConnectError("engine offline")

    monkeypatch.setattr(regelrecht, "_rpc_call", kapot)
    data, fallback = asyncio.run(
        regelrecht._maatregelen(
            {
                "feiten": {
                    "heeft_koelinstallatie": True,
                    "HEEFT_AFZUIGINSTALLATIE": "nee",
                }
            }
        )
    )
    assert fallback is True
    assert [v["naam"] for v in data["benodigde_feiten"]] == [
        "HEEFT_AFZUIGINSTALLATIE"
    ]

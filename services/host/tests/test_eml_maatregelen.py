"""De maatregelbepaling loopt langs dezelfde weg als elke andere regel.

Er was een eigen pad voor deze wet: een twee-staps-flow die het model stuurde,
met een lokale kopie van zeven maatregelen als terugval. Beide zijn weg. De
regelloop in de host declareert nu generiek wat een wet mist, en de kopie gaf
iedereen de algemene bijlage - ook een kweker onder glas, voor wie een andere
bijlage geldt.

Deze tests draaien zonder netwerk.
"""

import asyncio
import importlib.util
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"

EML_LAW = "omgevingswet/energiebesparing/maatregelen"


def _load_regelrecht():
    pad = MCP_DIR / "regelrecht" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_regelrecht_server", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Twee volledige bijlagen plus de categorie-indeling: alleen de laatste is voor
# een client bruikbaar, de eerste twee zijn samen 255 maatregelen.
DEFINITIES_UIT_ENGINE = {
    "MAATREGELEN_ALGEMEEN": [{"code": "GC1"}, {"code": "FD3"}],
    "MAATREGELEN_GLASTUINBOUW": [{"code": "GK1"}],
    "CATEGORIEEN": [
        {"categorie": "Ruimteverwarming", "onderdeel": "Gebouwen", "lijsten": ["algemeen"]},
        {"categorie": "Tuinbouwkassen", "onderdeel": "Gebouwen", "lijsten": ["glastuinbouw"]},
    ],
}

ENGINE_RESULT = {
    "structuredContent": {
        "requirements_met": True,
        "missing_required": False,
        "law_metadata": {"name": "Erkende maatregelenlijst energiebesparing (EML 2023)"},
        "output": {
            "is_glastuinbouwsector": True,
            "bijlage_milieubelastende_activiteiten": "VIIaa",
            "bijlage_gebouwen": "XIVa",
            "aantal_maatregelen": 1,
            "maatregelen": [
                {
                    "code": "GK1",
                    "naam": "Breng beweegbare gevelschermen aan",
                    "categorie": "Tuinbouwkassen",
                    "bijlage": "XIVa",
                    "economische_randvoorwaarden": [
                        {"id": "1", "realisatiemoment": "Zelfstandig moment", "randvoorwaarde": "Bij een gasgebruik van ten minste 21 m³."}
                    ],
                }
            ],
        },
    }
}

ENGINE_RESULT_ONVOLLEDIG = {
    "structuredContent": {
        "requirements_met": False,
        "missing_required": True,
        "output": {},
        "missing_parameters": [
            {
                "missing_fields": [
                    {
                        "name": "AANWEZIGE_CATEGORIEEN",
                        "description": "De categorieen uit de erkende maatregelenlijst die bij het bedrijf voorkomen.",
                    }
                ]
            }
        ],
    }
}


def test_eml_gaat_generiek_naar_de_engine_zonder_eigen_pad(monkeypatch):
    """Parameters gaan ongewijzigd door; er is geen omweg meer voor deze wet."""
    regelrecht = _load_regelrecht()
    calls = []

    async def nep_rpc(method, params):
        calls.append(params["arguments"])
        return ENGINE_RESULT

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data = asyncio.run(
        regelrecht._execute_law(
            {
                "law": EML_LAW,
                "parameters": {
                    "TEELT_GEWASSEN_IN_KAS": True,
                    "AANWEZIGE_CATEGORIEEN": ["Tuinbouwkassen"],
                },
            }
        )
    )
    hoofdaanroep = calls[0]
    assert hoofdaanroep["law"] == EML_LAW
    assert hoofdaanroep["parameters"] == {
        "TEELT_GEWASSEN_IN_KAS": True,
        "AANWEZIGE_CATEGORIEEN": ["Tuinbouwkassen"],
    }
    assert data["voldoet_aan_voorwaarden"] is True
    assert data["uitkomsten"]["bijlage_gebouwen"] == "XIVa"


def test_lijstparameter_overleeft_de_aanroep(monkeypatch):
    """`AANWEZIGE_CATEGORIEEN` is een lijst, geen boolean.

    Het oude pad filterde parameters op `isinstance(v, bool)` - een categorielijst
    verdween daar geruisloos, waarna de wet eindeloos om hetzelfde veld bleef
    vragen.
    """
    regelrecht = _load_regelrecht()
    calls = []

    async def nep_rpc(method, params):
        calls.append(params["arguments"])
        return ENGINE_RESULT

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    asyncio.run(
        regelrecht._execute_law(
            {"law": EML_LAW, "parameters": {"AANWEZIGE_CATEGORIEEN": ["Perslucht", "Stoom"]}}
        )
    )
    assert calls[0]["parameters"]["AANWEZIGE_CATEGORIEEN"] == ["Perslucht", "Stoom"]


def test_ontbrekend_veld_komt_als_ontbrekende_gegevens_terug(monkeypatch):
    """De regelloop stuurt op `ontbrekende_gegevens`, niet op een eigen veldnaam."""
    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        return ENGINE_RESULT_ONVOLLEDIG

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data = asyncio.run(regelrecht._execute_law({"law": EML_LAW, "parameters": {}}))
    assert data["voldoet_aan_voorwaarden"] is False
    assert data["missing_required"] is True
    assert data["ontbrekende_gegevens"] == [
        {
            "naam": "AANWEZIGE_CATEGORIEEN",
            "beschrijving": "De categorieen uit de erkende maatregelenlijst die bij het bedrijf voorkomen.",
        }
    ]


def test_geen_lokale_kopie_meer_bij_een_onbereikbare_engine(monkeypatch):
    """Liever geen lijst dan onze lijst.

    De oude fallback gaf zeven maatregelen uit de algemene bijlage terug, ook aan
    een bedrijf voor wie de glastuinbouwbijlage geldt. Nu komt er een nette fout:
    de host meldt dat de bron niet beschikbaar is (PDR-011).
    """
    import httpx

    regelrecht = _load_regelrecht()

    async def nep_rpc(method, params):
        raise httpx.ConnectError("engine weg")

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data = asyncio.run(regelrecht._execute_law({"law": EML_LAW, "parameters": {}}))
    assert data["error"] == "SOURCE_UNAVAILABLE"
    assert "maatregelen" not in data


def test_definities_blijven_beperkt_tot_de_categorieindeling():
    """De twee bijlagen horen niet als constantenblok in elke respons.

    Ze zijn samen 255 maatregelen; wat een bedrijf aangaat staat gefilterd in
    `uitkomsten.maatregelen`.
    """
    regelrecht = _load_regelrecht()
    beperkt = regelrecht._bruikbare_definities(EML_LAW, DEFINITIES_UIT_ENGINE)
    assert set(beperkt) == {"CATEGORIEEN"}
    assert len(beperkt["CATEGORIEEN"]) == 2


def test_definities_van_andere_wetten_blijven_ongemoeid():
    regelrecht = _load_regelrecht()
    drempels = {"DREMPEL_ELEKTRICITEIT_KWH": 50000, "DREMPEL_GAS_M3": 25000}
    assert (
        regelrecht._bruikbare_definities(
            "omgevingswet/energiebesparing/informatieplicht", drempels
        )
        == drempels
    )


def test_execute_law_generieke_wet_gaat_rechtstreeks_naar_engine(monkeypatch):
    """Parameters en overrides gaan ongewijzigd door; de response wordt vereenvoudigd.

    Naast de hoofdaanroep volgt een tweede aanroep met lege parameters
    (_definities_voor, voor de drempelwaarden) - vandaar de lijst met calls
    in plaats van één dict.
    """
    regelrecht = _load_regelrecht()
    calls = []

    async def nep_rpc(method, params):
        calls.append(params["arguments"])
        return {
            "structuredContent": {
                "requirements_met": True,
                "output": {"informatieplicht": True},
                "law_metadata": {"name": "informatieplicht"},
            }
        }

    monkeypatch.setattr(regelrecht, "_rpc_call", nep_rpc)
    data = asyncio.run(
        regelrecht._execute_law(
            {
                "law": "omgevingswet/energiebesparing/informatieplicht",
                "parameters": {"KVK_NUMMER": "85234567"},
                "overrides": {"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 61250}},
            }
        )
    )
    hoofdaanroep = calls[0]
    assert hoofdaanroep["law"] == "omgevingswet/energiebesparing/informatieplicht"
    assert hoofdaanroep["parameters"] == {"KVK_NUMMER": "85234567"}
    assert hoofdaanroep["overrides"] == {"RVO": {"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 61250}}
    assert data["voldoet_aan_voorwaarden"] is True
    assert data["uitkomsten"] == {"informatieplicht": True}


def test_execute_law_zonder_law_geeft_nette_fout():
    regelrecht = _load_regelrecht()
    data = asyncio.run(regelrecht._execute_law({}))
    assert data["error"] == "ONTBREKEND_VELD"
    assert data["velden"] == ["law"]


def test_elke_respons_draagt_hetzelfde_herkomstlabel(monkeypatch):
    """Geen tweede label meer: er is geen pad dat een kopie kan opleveren."""
    regelrecht = _load_regelrecht()
    assert not hasattr(regelrecht, "_wrap_eml_provenance")
    assert not hasattr(regelrecht, "EML_FALLBACK_MAATREGELEN")

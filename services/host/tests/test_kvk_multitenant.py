"""KvK-server is multi-tenant: KvK-nummer per aanroep, geen hardcoded demo-bedrijf.

MVP-01/PDR-009: de host injecteert het sessie-KvK-nummer; de KvK-server bedient
dat nummer i.p.v. één proces-globaal (voorheen hardcoded 68750110). Draait
netwerkloos via de mock-persona 85234567 (Koffiezaak Noon).
"""

import importlib.util
from pathlib import Path

MCP_KVK = Path(__file__).resolve().parent.parent.parent / "mcp" / "kvk" / "server.py"
MOCK_KVK = "85234567"


def _load_server():
    spec = importlib.util.spec_from_file_location("mcp_kvk_server", MCP_KVK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_geen_hardcoded_demobedrijf_als_default():
    # AC2: 68750110 mag nergens meer als default-voor-iedereen in de code staan.
    source = MCP_KVK.read_text(encoding="utf-8")
    assert 'or "68750110"' not in source
    assert '"68750110"' not in source


def test_resolve_kvk_gebruikt_aanroep_argument():
    srv = _load_server()
    assert srv._resolve_kvk({"kvk_nummer": MOCK_KVK}) == MOCK_KVK


def test_resolve_kvk_zonder_kvk_en_zonder_demo_is_none(monkeypatch):
    monkeypatch.delenv("DEMO_KVK_NUMMER", raising=False)
    srv = _load_server()
    assert srv._resolve_kvk({}) is None


def test_resolve_kvk_valt_terug_op_demo_env_voor_standalone(monkeypatch):
    # Dev-fallback (standalone gebruik buiten de host), niet 68750110.
    monkeypatch.setenv("DEMO_KVK_NUMMER", MOCK_KVK)
    srv = _load_server()
    assert srv._resolve_kvk({}) == MOCK_KVK


async def test_basisprofiel_bedient_het_meegegeven_kvk():
    srv = _load_server()
    profiel = await srv._get_basisprofiel(MOCK_KVK)
    assert profiel["kvkNummer"] == MOCK_KVK


async def test_cache_is_per_kvk():
    srv = _load_server()
    await srv._get_basisprofiel(MOCK_KVK)
    # Cache is een dict gekeyd op KvK-nummer (geen enkel globaal profiel meer).
    assert isinstance(srv._profiel_cache, dict)
    assert MOCK_KVK in srv._profiel_cache


def test_api_logregel_bevat_geen_kvk_nummer():
    # De host maskeert het sessie-KvK al in zijn tool-call-logs; de KvK-server
    # logde het nummer alsnog via de volle API-URL, in dezelfde logstream.
    srv = _load_server()
    for pad, verwacht in [
        (f"/v1/basisprofielen/{MOCK_KVK}", "/v1/basisprofielen/<kvk>"),
        (
            f"/v1/basisprofielen/{MOCK_KVK}/vestigingen",
            "/v1/basisprofielen/<kvk>/vestigingen",
        ),
        (f"/v1/basisprofielen/{MOCK_KVK}/eigenaar", "/v1/basisprofielen/<kvk>/eigenaar"),
    ]:
        gemaskeerd = srv._pad_zonder_kvk(pad)
        assert gemaskeerd == verwacht
        assert MOCK_KVK not in gemaskeerd


def test_maskering_laat_overige_segmenten_ongemoeid():
    # Alleen een 8-cijferig pad-segment is een KvK-nummer; laat de rest staan,
    # anders wordt de logregel onbruikbaar voor debuggen.
    srv = _load_server()
    assert srv._pad_zonder_kvk("/v1/basisprofielen") == "/v1/basisprofielen"
    assert srv._pad_zonder_kvk("/v1/vestigingen/000052341288").endswith("000052341288")

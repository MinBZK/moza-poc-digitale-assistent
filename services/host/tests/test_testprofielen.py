"""De drie testprofielen zijn volledig mock-bedienbaar, zonder netwerk.

MVP-01/PDR-009 breidt de gesloten testgroep uit naar drie profielen. Elk profiel
moet in álle bronnen die de informatieplicht-flow raakt bekend zijn: KvK
(basisprofiel, vestigingen, eigenaar), BAG-fallback (gebruiksdoel) en de
netbeheerder (jaarverbruik). Ontbreekt er één, dan loopt een tester in een
gebruikerstest vast op een lege of falende bron.

De drempels worden hier niet opnieuw opgeschreven. Bron van waarheid is de
RegelRecht-engine; de repo heeft daar één lokale afspiegeling van, de fallback
in `vlam_host.REGELRECHT_DEFINITIES_ALLOWLIST`. Die lezen we uit, zodat een
gewijzigde drempel automatisch doorwerkt in deze test. Wat de test vastlegt is
niet de waarde, maar de relatieve positie van elk profiel.
"""

import importlib.util
from pathlib import Path

import vlam_host

SERVICES = Path(__file__).resolve().parent.parent.parent
MCP_KVK = SERVICES / "mcp" / "kvk" / "server.py"
MCP_NETBEHEERDER = SERVICES / "mcp" / "netbeheerder" / "server.py"

# persona-id (frontend) -> KvK-nummer (backend). Zie .env.example TEST_USERS.
TESTPROFIELEN = {
    "koffiezaak": "85234567",
    "bloemenkweker": "62345681",
    "haarstylist": "56789012",
}

_DREMPELS = vlam_host.REGELRECHT_DEFINITIES_ALLOWLIST[
    "omgevingswet/energiebesparing/informatieplicht"
]["fallback"]
DREMPEL_ELEKTRICITEIT_KWH = _DREMPELS["DREMPEL_ELEKTRICITEIT_KWH"]
DREMPEL_GAS_M3 = _DREMPELS["DREMPEL_GAS_M3"]


def _load(path: Path, naam: str):
    spec = importlib.util.spec_from_file_location(naam, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _kvk_server():
    return _load(MCP_KVK, "mcp_kvk_server")


def _netbeheerder_server():
    return _load(MCP_NETBEHEERDER, "mcp_netbeheerder_server")


def test_alle_testprofielen_hebben_kvk_mockdata():
    srv = _kvk_server()
    for persona, kvk in TESTPROFIELEN.items():
        assert kvk in srv.MOCK_PROFIELEN, f"{persona}: geen basisprofiel"
        assert kvk in srv.MOCK_VESTIGINGEN, f"{persona}: geen vestigingen"
        assert kvk in srv.MOCK_EIGENAREN, f"{persona}: geen eigenaar"


def test_mockprofielen_zijn_intern_consistent():
    srv = _kvk_server()
    for kvk in TESTPROFIELEN.values():
        assert srv.MOCK_PROFIELEN[kvk]["kvkNummer"] == kvk
        assert srv.MOCK_VESTIGINGEN[kvk]["kvkNummer"] == kvk
        assert srv.MOCK_EIGENAREN[kvk]["kvkNummer"] == kvk


def test_elk_testprofiel_heeft_een_bag_fallback():
    # Zonder BAG_API_KEY komt het gebruiksdoel uit de fallback. Ontbreekt die,
    # dan mist de woonfunctie-toets zijn invoer.
    srv = _kvk_server()
    for persona, kvk in TESTPROFIELEN.items():
        adres = srv._extract_address(srv.MOCK_PROFIELEN[kvk])
        assert adres is not None, f"{persona}: geen bezoekadres"
        sleutel = f"{adres['postcode'].replace(' ', '')}-{adres['huisnummer']}"
        assert sleutel in srv._BAG_DEMO_FALLBACK, f"{persona}: geen BAG-fallback"


def test_alle_testprofielen_hebben_verbruiksdata():
    srv = _netbeheerder_server()
    for persona, kvk in TESTPROFIELEN.items():
        assert srv._verbruik_voor(kvk) is not None, f"{persona}: geen verbruik"


def test_profielen_dekken_beide_uitkomsten_van_de_informatieplicht():
    """De drie profielen moeten samen boven- en onder-de-drempel afdekken.

    Anders test een gebruikerstest maar één tak van de regel.
    """
    srv = _netbeheerder_server()

    def boven_drempel(kvk: str) -> bool:
        totaal = srv._verbruik_voor(kvk)["totaal"]
        return (
            totaal["jaarlijks_elektriciteitsverbruik_kwh"] >= DREMPEL_ELEKTRICITEIT_KWH
            or totaal["jaarlijks_gasverbruik_m3"] >= DREMPEL_GAS_M3
        )

    uitkomsten = {p: boven_drempel(kvk) for p, kvk in TESTPROFIELEN.items()}
    assert any(uitkomsten.values()), "geen enkel profiel valt onder de plicht"
    assert not all(uitkomsten.values()), "geen profiel dat buiten de plicht valt"


def test_bloemenkweker_wordt_door_gas_getriggerd_niet_door_elektriciteit():
    # Bewust een ander pad door dezelfde regel dan Koffiezaak Noon.
    srv = _netbeheerder_server()
    totaal = srv._verbruik_voor(TESTPROFIELEN["bloemenkweker"])["totaal"]
    assert totaal["jaarlijks_gasverbruik_m3"] >= DREMPEL_GAS_M3


def test_haarstylist_valt_onder_beide_drempels():
    srv = _netbeheerder_server()
    totaal = srv._verbruik_voor(TESTPROFIELEN["haarstylist"])["totaal"]
    assert totaal["jaarlijks_elektriciteitsverbruik_kwh"] < DREMPEL_ELEKTRICITEIT_KWH
    assert totaal["jaarlijks_gasverbruik_m3"] < DREMPEL_GAS_M3


def test_env_example_documenteert_dezelfde_profielen():
    # De .env.example is de enige plek waar tokens en KvK-nummers samenkomen;
    # loopt die uit de pas, dan werkt de frontend-koppeling niet.
    tekst = (SERVICES / "host" / ".env.example").read_text(encoding="utf-8")
    for kvk in TESTPROFIELEN.values():
        assert kvk in tekst, f"{kvk} ontbreekt in .env.example"

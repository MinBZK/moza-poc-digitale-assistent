"""Guard: demo-persona's en de informatieplicht-flow (Dag van de Toekomst).

De flow voor Claudia van Dam / Koffiezaak Noon steunt op invarianten die
over drie MCP-servers verspreid staan (kvk, netbeheerder, regelrecht).
Deze tests borgen dat de mock-data consistent blijft: één afwijkend
KvK-nummer of een verbruik dat onder de drempel zakt, breekt de demo stil.

De MCP-servers staan buiten de pythonpath (services/host); we laden ze
per bestandspad. De servers starten geen verbindingen bij import.
"""

import importlib.util
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"

NOON_KVK = "85234567"


def _load(naam: str):
    """Laad een MCP-servermodule op bestandspad."""
    pad = MCP_DIR / naam / "server.py"
    spec = importlib.util.spec_from_file_location(f"mcp_{naam}_server", pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_noon_bestaat_in_kvk_mock():
    kvk = _load("kvk")
    profiel = kvk.MOCK_PROFIELEN[NOON_KVK]
    assert profiel["naam"] == "Koffiezaak Noon"
    hoofdactiviteit = profiel["sbiActiviteiten"][0]
    assert hoofdactiviteit["sbiCode"] == "56102"
    # Vestigingen en eigenaar horen bij hetzelfde nummer beschikbaar te zijn
    assert NOON_KVK in kvk.MOCK_VESTIGINGEN
    assert NOON_KVK in kvk.MOCK_EIGENAREN
    eigenaar = kvk.MOCK_EIGENAREN[NOON_KVK]["natuurlijkPersoon"]
    assert eigenaar["volledigeNaam"] == "Claudia van Dam"


def test_noon_adres_heeft_bag_fallback_zonder_woonfunctie():
    kvk = _load("kvk")
    adres = kvk.MOCK_PROFIELEN[NOON_KVK]["_embedded"]["hoofdvestiging"]["adressen"][0]
    key = f"{adres['postcode']}-{adres['huisnummer']}"
    bag = kvk._BAG_DEMO_FALLBACK[key]
    # De woonfunctie-uitzondering mag NIET gelden, anders vervalt de plicht
    assert bag["gebruiksdoelen"] != ["woonfunctie"]


def test_noon_verbruik_boven_elektriciteitsdrempel():
    netbeheerder = _load("netbeheerder")
    verbruik = netbeheerder._verbruik_voor(NOON_KVK)
    assert verbruik is not None, "Noon moet bekend zijn bij de netbeheerder-mock"
    totaal = verbruik["totaal"]
    # Kern van de demo: elektriciteit boven 50.000 kWh => informatieplicht geldt
    assert totaal["jaarlijks_elektriciteitsverbruik_kwh"] > 50_000
    assert totaal["jaarlijks_gasverbruik_m3"] < 25_000


def test_netbeheerder_onbekend_kvk_geeft_geen_data():
    netbeheerder = _load("netbeheerder")
    assert netbeheerder._verbruik_voor("68750110") is None, (
        "Test BV Donald hoort GEEN netbeheerder-data te hebben: de bestaande "
        "demo-flow (verbruik uitvragen bij de gebruiker) moet blijven werken."
    )


def test_eml_maatregelen_volgen_bedrijfskenmerken():
    regelrecht = _load("regelrecht")
    lijst = regelrecht._geldende_maatregelen(
        koelinstallatie=True, afzuiginstallatie=False
    )
    per_voorwaarde = {m["id"]: m["van_toepassing"] for m in lijst}
    # 'altijd'-maatregelen gelden onvoorwaardelijk
    assert per_voorwaarde["EML-H01"] is True
    # koelinstallatie=True activeert de koel-maatregelen
    assert per_voorwaarde["EML-H10"] is True
    # afzuiginstallatie=False deactiveert de afzuig-maatregelen
    assert per_voorwaarde["EML-H20"] is False


def test_eml_alle_kenmerken_true_geeft_alle_maatregelen():
    regelrecht = _load("regelrecht")
    lijst = regelrecht._geldende_maatregelen(
        koelinstallatie=True, afzuiginstallatie=True
    )
    assert all(m["van_toepassing"] for m in lijst)
    assert len(lijst) == len(regelrecht.EML_HORECA)

"""De mock-persona's zijn gelijk aan wat de frontend op het scherm toont.

De respondent van een gebruikersonderzoek leest zijn bedrijfsgegevens op de
pagina's Bedrijfsgegevens en Adresgegevens van MinBZK/moza-poc. Noemt de
assistent een ander getal, adres of vestigingsnummer, dan leest hij dat als een
fout van de assistent — ook als beide waarden op zichzelf verdedigbaar zijn.
De frontend is dus leidend en deze tests lezen hem echt uit.

Waarom uitlezen en niet overtypen: een overgetypte kopie legt de waarden van
gisteren vast. Wijzigt de frontend er één, dan blijft de kopie groen en loopt
precies het verschil dat deze test moet vangen ongezien door. Dat is hier al
een keer gebeurd.

Het bestand ligt in een andere repository. Staat die niet naast deze checkout,
dan slaan de tests over met een luide reden in plaats van stilletjes te slagen.
Zet MOZA_POC_PERSONAS naar het pad van `_data/personas.json` om ze te draaien
tegen een checkout die ergens anders staat.
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parent.parent.parent
MCP_KVK = SERVICES / "mcp" / "kvk" / "server.py"
MCP_NETBEHEERDER = SERVICES / "mcp" / "netbeheerder" / "server.py"

# Naast de repo (de gebruikelijke werkkopie), of expliciet via de omgeving. De
# upstream heet `moza-poc`, maar bestaande werkkopieën heten `poc-moza`; wie
# maar één van beide kent, laat de halve wereld stilletjes overslaan.
_ZUSTERMAPPEN = ("moza-poc", "poc-moza")
_KANDIDATEN = [
    SERVICES.parent.parent / naam / "_data" / "personas.json"
    for naam in _ZUSTERMAPPEN
]


def _personas_pad() -> Path:
    uit_omgeving = os.getenv("MOZA_POC_PERSONAS", "").strip()
    if uit_omgeving:
        return Path(uit_omgeving)
    for kandidaat in _KANDIDATEN:
        if kandidaat.is_file():
            return kandidaat
    return _KANDIDATEN[0]


def _laad_module(pad: Path, naam: str):
    spec = importlib.util.spec_from_file_location(naam, pad)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def personas() -> list[dict]:
    pad = _personas_pad()
    if not pad.is_file():
        gezocht = " of ".join(str(k) for k in _KANDIDATEN)
        pytest.skip(
            f"frontend-persona's niet gevonden ({gezocht}); zet "
            f"MOZA_POC_PERSONAS naar _data/personas.json van MinBZK/moza-poc. "
            f"Zonder dat bestand is de pariteit met het scherm ONGETOETST. "
            f"In CI hoort dit niet voor te komen: .github/workflows/test.yml "
            f"checkt de frontend uit en zet die variabele."
        )
    return json.loads(pad.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kvk():
    return _laad_module(MCP_KVK, "mcp_kvk_server")


@pytest.fixture(scope="module")
def netbeheerder():
    return _laad_module(MCP_NETBEHEERDER, "mcp_netbeheerder_server")


def _bedrijven(personas: list[dict]) -> dict[str, dict]:
    """Bedrijfsgegevens per KvK-nummer, alleen voor persona's die wij kennen."""
    return {p["bedrijf"]["kvkNummer"]: p for p in personas if p.get("bedrijf")}


def test_elke_actieve_frontend_persona_heeft_backend_data(
    personas, kvk, netbeheerder
):
    """De blokkade die het gebruikersonderzoek van augustus 2026 bijna sloopte.

    De frontend bepaalt welke persona de respondent te zien krijgt. Kent de
    backend dat KvK-nummer niet, dan leest de respondent zijn bedrijf op het
    scherm en krijgt hij van de assistent "log eerst in" — de sessie is dan
    voorbij voordat hij één vraag heeft kunnen stellen.
    """
    actief = [p for p in personas if p.get("actief")]
    assert actief, "de frontend zet geen enkele persona op actief"

    for persona in actief:
        nummer = persona["bedrijf"]["kvkNummer"]
        naam = f"{persona['id']} ({nummer})"
        assert nummer in kvk.MOCK_PROFIELEN, f"{naam}: geen basisprofiel"
        assert nummer in kvk.MOCK_VESTIGINGEN, f"{naam}: geen vestigingen"
        assert nummer in kvk.MOCK_EIGENAREN, f"{naam}: geen eigenaar"
        assert netbeheerder._verbruik_voor(nummer) is not None, (
            f"{naam}: geen verbruik, dus geen oordeel over de informatieplicht"
        )


def _allowlist_uit_env_example() -> set[str]:
    """De nummers uit de TEST_KVK_NUMMERS-regel zelf, niet uit het commentaar.

    Zoeken op "staat het nummer ergens in het bestand" slaagt al zodra iemand
    de persona in de commentaartabel documenteert — terwijl juist de waarde
    achter het `=`-teken bepaalt of de host de sessie toelaat.
    """
    tekst = (SERVICES / "host" / ".env.example").read_text(encoding="utf-8")
    for regel in tekst.splitlines():
        schoon = regel.lstrip("# ").strip()
        if schoon.startswith("TEST_KVK_NUMMERS="):
            waarde = schoon.split("=", 1)[1]
            return {n.strip() for n in waarde.split(",") if n.strip()}
    raise AssertionError("geen TEST_KVK_NUMMERS-regel in .env.example")


def test_actieve_persona_staat_in_de_allowlist(personas):
    """`TEST_KVK_NUMMERS` is de allowlist; ontbreekt het nummer, dan volgt 401."""
    allowlist = _allowlist_uit_env_example()
    for persona in personas:
        if not persona.get("actief"):
            continue
        nummer = persona["bedrijf"]["kvkNummer"]
        assert nummer in allowlist, (
            f"{persona['id']} ({nummer}) is actief in de frontend maar staat "
            f"niet in TEST_KVK_NUMMERS van .env.example; de host blokkeert "
            f"die sessie met 'log eerst in'"
        )


def test_allowlist_conftest_en_env_example_lopen_gelijk():
    """Drie lijsten, geen mechanisme dat ze koppelt.

    `.env.example` documenteert, `conftest.py` bepaalt wat de tests zien en de
    ZAD-component-config bepaalt wat productie ziet. Loopt de eerste op de
    tweede voor, dan valt elke test die als die persona rijdt om op "log eerst
    in" terwijl de mockdata compleet is. De derde staat in `docs/deploy-zad.md`
    en kan hiervandaan niet getoetst worden.
    """
    conftest = (SERVICES / "host" / "tests" / "conftest.py").read_text(
        encoding="utf-8"
    )
    for nummer in _allowlist_uit_env_example():
        assert nummer in conftest, (
            f"{nummer} staat in .env.example maar niet in conftest.py; onder "
            f"pytest weigert config.kvk_uit_header dat nummer"
        )


@pytest.mark.parametrize(
    "kvk_nummer",
    ["85234567", "62345681", "56789012", "61234570"],
)
def test_kerngegevens_volgen_het_scherm(personas, kvk, kvk_nummer):
    """Handelsnaam, rechtsvorm, vestigingsnummer en personeel, veld voor veld."""
    persona = _bedrijven(personas).get(kvk_nummer)
    assert persona is not None, (
        f"{kvk_nummer} zit in de backend-mock maar in geen enkele "
        f"frontend-persona; dan bedient de backend een bedrijf dat niemand ziet"
    )
    bedrijf = persona["bedrijf"]
    profiel = kvk.MOCK_PROFIELEN[kvk_nummer]
    hoofdvestiging = profiel["_embedded"]["hoofdvestiging"]

    assert profiel["naam"] == bedrijf["handelsnaam"]
    assert profiel["rechtsvorm"].lower() == bedrijf["rechtsvorm"].lower()
    assert hoofdvestiging["vestigingsnummer"] == bedrijf["vestigingsnummer"]
    assert kvk.MOCK_VESTIGINGEN[kvk_nummer]["vestigingen"][0][
        "vestigingsnummer"
    ] == bedrijf["vestigingsnummer"]

    vestigingsprofiel = kvk.MOCK_VESTIGINGSPROFIELEN[bedrijf["vestigingsnummer"]]
    assert (
        vestigingsprofiel["voltijdWerkzamePersonen"]
        == bedrijf["werkzamePersonenFulltime"]
    )
    assert (
        vestigingsprofiel["deeltijdWerkzamePersonen"]
        == bedrijf["werkzamePersonenParttime"]
    )
    # Het totaal is geen los feit maar de som; loopt dat uiteen, dan spreekt de
    # assistent zichzelf tegen tussen twee antwoorden over hetzelfde bedrijf.
    assert profiel["totaalWerkzamePersonen"] == (
        bedrijf["werkzamePersonenFulltime"] + bedrijf["werkzamePersonenParttime"]
    )
    assert hoofdvestiging["totaalWerkzamePersonen"] == (
        profiel["totaalWerkzamePersonen"]
    )
    # Het RSIN dat de assistent kán citeren komt uit kvk__eigenaar; dat is de
    # waarde die met het scherm moet kloppen. Het vestigingsprofiel draagt hem
    # ook, maar `_VESTIGINGSPROFIEL_VELDEN` mengt hem niet mee, dus alleen dáár
    # toetsen zou een spiegel bewaken die niemand leest.
    eigenaar = kvk.MOCK_EIGENAREN[kvk_nummer]
    assert eigenaar["rsin"] == bedrijf["rsinNummer"]
    if "rechtspersoon" in eigenaar:
        assert eigenaar["rechtspersoon"]["rsin"] == bedrijf["rsinNummer"]
    assert vestigingsprofiel["rsin"] == bedrijf["rsinNummer"]


def _normaliseer(adres: str) -> str:
    """Vergelijk adressen zonder over de postcode-spatie te struikelen.

    De KvK-API levert `2665KG`, het scherm toont `2665 KG`. Dat is opmaak, geen
    ander adres — maar een huisnummer of een plaats die verschilt, is dat wel.
    """
    return "".join(adres.split()).lower().replace(",", "")


@pytest.mark.parametrize(
    "kvk_nummer",
    ["85234567", "62345681", "56789012", "61234570"],
)
def test_bezoek_en_postadres_volgen_het_scherm(personas, kvk, kvk_nummer):
    bedrijf = _bedrijven(personas)[kvk_nummer]["bedrijf"]
    adressen = kvk.MOCK_PROFIELEN[kvk_nummer]["_embedded"]["hoofdvestiging"][
        "adressen"
    ]
    per_type = {adres["type"]: adres for adres in adressen}
    assert set(per_type) == {"bezoekadres", "correspondentieadres"}

    assert _normaliseer(per_type["bezoekadres"]["volledigAdres"]) == _normaliseer(
        bedrijf["vestigingsadresVolledig"]
    )
    assert _normaliseer(
        per_type["correspondentieadres"]["volledigAdres"]
    ) == _normaliseer(bedrijf["postadres"])


@pytest.mark.parametrize(
    "kvk_nummer",
    ["85234567", "62345681", "56789012", "61234570"],
)
def test_sbi_en_website_volgen_het_scherm(personas, kvk, kvk_nummer):
    bedrijf = _bedrijven(personas)[kvk_nummer]["bedrijf"]
    profiel = kvk.MOCK_PROFIELEN[kvk_nummer]

    uit_mock = [
        (a["sbiCode"], a["sbiOmschrijving"]) for a in profiel["sbiActiviteiten"]
    ]
    uit_frontend = [(s["code"], s["omschrijving"]) for s in bedrijf["sbi"]]
    assert uit_mock == uit_frontend

    websites = profiel["_embedded"]["hoofdvestiging"]["websites"]
    assert bedrijf["website"] in websites

"""Grenzen van de arbeidsmarkt-demo, vastgelegd als test.

De werksessie van 10 augustus 2026 gaat over de vraag hoever de assistent mag
gaan bij een vraag over het aannemen van iemand met een afstand tot de
arbeidsmarkt. Deze demo bouwt de smalle variant: landelijk kader, geen enkel
gegeven over de kandidaat, waarschuwen dát er een termijn is zonder te zeggen
welke, en de plichten altijd naast de rechten.

Die keuzes staan hier als test, niet als voornemen. Wie de demo verbreedt naar
individuele beoordeling, bedragen of kandidaatgegevens, laat deze tests vallen —
en dat is precies het moment waarop de sessie er weer bij moet komen.
"""

import importlib.util
import json
import re
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parent.parent.parent
UWV_SERVER = SERVICES / "mcp" / "uwv" / "server.py"
PROMPT_BLOK = (
    SERVICES / "host" / "prompts" / "blocks" / "shared" / "domain" / "arbeidsmarkt.md"
)


@pytest.fixture(scope="module")
def uwv():
    spec = importlib.util.spec_from_file_location("mcp_uwv_server_test", UWV_SERVER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(resultaat) -> dict:
    """Pak de `data` uit een MCP-respons met provenance-wrapper."""
    return json.loads(resultaat[0].text)["data"]


# ---------------------------------------------------------------------------
# De bron kent regelingen, geen personen
# ---------------------------------------------------------------------------


def test_bron_bevat_geen_veld_over_een_persoon(uwv):
    """Geen enkel datastructuur-veld gaat over een individuele kandidaat."""
    verboden = {
        "bsn",
        "burgerservicenummer",
        "naam_kandidaat",
        "geboortedatum",
        "diagnose",
        "beperking",
        "uitkering_kandidaat",
        "doelgroepregister_status",
        "in_doelgroepregister",
    }
    alles = json.dumps(
        {
            "regelingen": uwv.REGELINGEN,
            "plichten": uwv.ALTIJD_GELDENDE_PLICHTEN,
            "servicepunten": uwv.SERVICEPUNTEN,
        },
        ensure_ascii=False,
    )
    gevonden = sorted(v for v in verboden if f'"{v}"' in alles)
    assert not gevonden, f"bron bevat velden over een persoon: {gevonden}"


def test_bron_is_niet_op_persoon_gesleuteld(uwv):
    """Regelingen zijn gesleuteld op regeling, servicepunten op vestiging.

    Zou er ooit een dict per persoon in komen, dan is dat hier zichtbaar: de
    enige identificerende sleutel die deze bron kent is het KvK-nummer van de
    ingelogde ondernemer, en dat komt uit de sessie.
    """
    assert isinstance(uwv.REGELINGEN, list)
    assert {r["id"] for r in uwv.REGELINGEN} == {r["id"] for r in uwv.REGELINGEN}
    for sleutel in uwv.SERVICEPUNTEN:
        assert re.fullmatch(r"\d{8}", sleutel), (
            f"servicepunt-sleutel {sleutel!r} is geen KvK-nummer"
        )


async def test_geen_enkele_tool_vraagt_om_kandidaatgegevens(uwv):
    """De tool-schema's bieden het LLM geen enkele ingang om iets over een persoon mee te geven."""
    verdacht = re.compile(
        r"bsn|kandidaat|sollicitant|werknemer_|diagnose|uitkering|geboorte", re.IGNORECASE
    )
    for tool in await uwv.list_tools():
        for veld in (tool.inputSchema.get("properties") or {}):
            assert not verdacht.search(veld), (
                f"{tool.name}: parameter {veld!r} vraagt om een gegeven over een persoon"
            )


async def test_alle_tools_zijn_read_only(uwv):
    """Deze bron muteert niets; er valt hier niets in te dienen."""
    for tool in await uwv.list_tools():
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.destructiveHint is False, tool.name


# ---------------------------------------------------------------------------
# Geen bedragen, wel de waarschuwing dat er een termijn is
# ---------------------------------------------------------------------------


def test_geen_bedragen_in_de_bron(uwv):
    """Bedragen veranderen te vaak; een fout kost de ondernemer direct geld."""
    alles = json.dumps(uwv.REGELINGEN, ensure_ascii=False)
    assert "€" not in alles, "bron noemt een bedrag"
    assert not re.search(r"\beuro\b", alles, re.IGNORECASE), "bron noemt een bedrag"
    for regeling in uwv.REGELINGEN:
        assert not any("bedrag" in k for k in regeling), (
            f"{regeling['id']}: veld met een bedrag"
        )


def test_regeling_met_termijn_wijst_naar_een_loket(uwv):
    """Wel waarschuwen dát er een termijn is, niet zeggen welke.

    Dit is uitspraak 3 uit het sessiedossier: het schaderisico van zwijgen wordt
    afgevangen zonder een getal te claimen dat verouderd kan zijn.
    """
    for regeling in uwv.REGELINGEN:
        if regeling["heeft_termijn"]:
            assert regeling["controleer_termijn_bij"], (
                f"{regeling['id']}: heeft een termijn maar wijst niet naar een loket"
            )
        else:
            assert regeling["controleer_termijn_bij"] is None, regeling["id"]


# ---------------------------------------------------------------------------
# De plichten horen erbij
# ---------------------------------------------------------------------------


def test_elke_regeling_draagt_zijn_plichten(uwv):
    """Een overzicht met alleen voordelen is onvolledig — de bron dwingt dat af."""
    for regeling in uwv.REGELINGEN:
        assert regeling["plichten"], f"{regeling['id']}: geen plichten"


def test_elke_regeling_benoemt_wie_beoordeelt(uwv):
    """Het individuele oordeel ligt bij een bestuursorgaan, niet bij de assistent."""
    for regeling in uwv.REGELINGEN:
        assert regeling["uitvoerder"], f"{regeling['id']}: geen uitvoerder"
        assert regeling["wettelijk_kader"], f"{regeling['id']}: geen wettelijk kader"
        assert regeling["beoordeling_door"], f"{regeling['id']}: geen beoordelaar"


def test_altijd_geldende_plichten_zijn_apart_op_te_vragen(uwv):
    kaders = {p["plicht"] for p in uwv.ALTIJD_GELDENDE_PLICHTEN}
    assert "Doeltreffende aanpassing" in kaders
    assert "Gelijke behandeling" in kaders


# ---------------------------------------------------------------------------
# Gedrag van de tools
# ---------------------------------------------------------------------------


async def test_regelingen_geeft_het_landelijke_kader(uwv):
    data = _payload(await uwv.call_tool("regelingen", {}))
    assert data["aantal"] == len(uwv.REGELINGEN)
    assert "geen gegevens over personen" in data["reikwijdte"]
    assert data["beoordeling_ligt_bij"]


async def test_regelingen_filtert_op_soort(uwv):
    data = _payload(await uwv.call_tool("regelingen", {"soort": "begeleiding"}))
    assert data["aantal"] > 0
    assert {r["soort"] for r in data["regelingen"]} == {"begeleiding"}


async def test_onbekende_soort_geeft_nette_fout(uwv):
    resultaat = await uwv.call_tool("regelingen", {"soort": "onzin"})
    fout = json.loads(resultaat[0].text)
    assert fout["error"] == "ONBEKENDE_SOORT"


async def test_lkv_banenafspraak_draagt_de_wijziging_van_2026(uwv):
    """De regel die per 1-1-2026 veranderde is precies waar modelkennis faalt.

    Een taalmodel dat op oudere kennis leunt stuurt de ondernemer naar een
    doelgroepverklaring die voor deze doelgroep niet meer bestaat. De bron moet
    de wijziging dus expliciet dragen.
    """
    data = _payload(await uwv.call_tool("regelingen", {}))
    lkv = next(r for r in data["regelingen"] if r["id"] == "lkv-banenafspraak")
    assert lkv["gewijzigd_per"] == "2026-01-01"
    assert "doelgroepverklaring" in lkv["wijziging"].lower()


async def test_response_draagt_peildatum(uwv):
    resultaat = await uwv.call_tool("regelingen", {})
    provenance = json.loads(resultaat[0].text)["provenance"]
    assert provenance["peildatum"] == uwv.PEILDATUM
    assert provenance["mock"] is True


async def test_werkgeversservicepunt_werkt_per_vestiging(uwv):
    data = _payload(await uwv.call_tool("werkgeversservicepunt", {"kvk_nummer": "85234567"}))
    assert data["beschikbaar"] is True
    assert data["vestigingsplaats"] == "Rotterdam"


async def test_onbekend_kvk_nummer_verzint_geen_servicepunt(uwv):
    data = _payload(await uwv.call_tool("werkgeversservicepunt", {"kvk_nummer": "99999999"}))
    assert data["beschikbaar"] is False
    assert data["melding"]


# ---------------------------------------------------------------------------
# De grenzen staan ook in de systeemprompt
# ---------------------------------------------------------------------------


def test_promptblok_bevat_de_harde_grenzen():
    tekst = PROMPT_BLOK.read_text(encoding="utf-8").lower()
    for zin in [
        "vraag nooit naar gegevens over de kandidaat",
        "niet naar bsn",
        "niet naar diagnose",
        "zeg nooit of een concrete persoon in aanmerking komt",
        "vergelijk of rangschik nooit twee kandidaten",
        "presenteer een mens nooit als financieel voordeel",
    ]:
        assert zin in tekst, f"promptblok mist de grens: {zin!r}"


def test_promptblok_dwingt_plichten_en_termijnwaarschuwing_af():
    tekst = PROMPT_BLOK.read_text(encoding="utf-8").lower()
    assert "hetzelfde antwoord" in tekst, "plichten moeten naast de rechten staan"
    assert "noem de lengte van een termijn niet" in tekst
    assert "geen bedragen" in tekst
    assert "werkgeversservicepunt" in tekst


def test_domeinblok_zit_in_de_samengestelde_systeemprompt():
    from prompts.composer import compose_system_prompt

    prompt = compose_system_prompt(mode="claude", has_tools=True)
    assert "afstand tot de arbeidsmarkt" in prompt.lower()
    assert "uwv__regelingen" in prompt


def test_domeinblok_ontbreekt_als_er_geen_tools_zijn():
    """Zonder bronnen geen domeinkennis — anders antwoordt het model uit het geheugen.

    NB: de few-shot voorbeelden uit `examples/` laadt de composer wél altijd,
    ook zonder tools. Dat geldt voor alle bestaande voorbeelden en staat los van
    deze demo; daarom toetst deze test op het domeinblok zelf en niet op de
    toolnaam, die ook in het voorbeeld voorkomt.
    """
    from prompts.composer import compose_system_prompt

    domeinblok = PROMPT_BLOK.read_text(encoding="utf-8").strip()
    prompt = compose_system_prompt(mode="claude", has_tools=False)
    assert domeinblok not in prompt
    assert "Vraag NOOIT naar gegevens over de kandidaat" not in prompt

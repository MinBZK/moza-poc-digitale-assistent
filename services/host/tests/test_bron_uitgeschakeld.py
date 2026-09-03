"""Een bron die met een uitzet-woord is uitgezet, staat uit; een bron die niet opkwam, heeft
een storing. Het model krijgt ze allebei te horen, maar anders: over een storing
meldt het wat er mist, over een uitgezette bron zwijgt het.

`bronnen_offline` kijkt naar servers die ingericht zijn maar niet startten.
Een bron die bewust uitstaat (`MCP_SERVER_NETBEHEERDER=uit`, bijvoorbeeld om
een onderzoek op eigen opgaven te laten draaien) staat daar niet in, en hoort
apart zichtbaar te zijn; anders blijft de assistent hem beloven: "uw
energieverbruik haal ik op uit uw Business Wallet".

Een belofte over een bron die er niet is, is precies het soort vertrouwensfout
dat dit project wil vermijden. En het is erger dan een storing melden, want de
gebruiker heeft geen enkele aanwijzing dat er iets mist.
"""

from unittest.mock import AsyncMock

import pytest

import vlam_host
from config import MCP_SERVER_ENV_KEYS
from errors import BRON_LABELS

ALLE = sorted(BRON_LABELS)
LOGGER = "vlam.host"
UIT_GEVALLEN = [[], ["netbeheerder"], ["koop", "netbeheerder"]]


def _waarschuwingen(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelname == "WARNING"]


@pytest.mark.parametrize("uit", UIT_GEVALLEN)
def test_elke_uitgezette_bron_krijgt_een_eigen_waarschuwing(uit, caplog, host_met_bronnen):
    host = host_met_bronnen(uit=uit)
    with caplog.at_level("WARNING", logger=LOGGER):
        host._meld_uitgezette_bronnen()
    meldingen = _waarschuwingen(caplog)
    assert len(meldingen) == len(uit)
    for naam, melding in zip(sorted(uit), meldingen, strict=True):
        assert f"Bron '{naam}'" in melding
        assert BRON_LABELS[naam] in melding
        assert MCP_SERVER_ENV_KEYS[naam] in melding
        assert "maak hem leeg" in melding


def test_een_storing_is_geen_reden_voor_de_uitzet_waarschuwing(caplog, host_met_bronnen):
    with caplog.at_level("WARNING", logger=LOGGER):
        host_met_bronnen(storing=["koop"])._meld_uitgezette_bronnen()
    assert _waarschuwingen(caplog) == []


@pytest.mark.parametrize("uit", UIT_GEVALLEN)
def test_health_toont_de_uitgezette_bronnen_apart(uit, host_met_bronnen):
    """`servers` meldt storingen; een bewust uitgezette bron hoort daar niet
    tussen, maar wel zichtbaar zijn voor wie /health leest."""
    status = host_met_bronnen(uit=uit).get_status()
    assert status["bronnen_uit"] == sorted(uit)
    assert set(status["servers"]) == set(ALLE) - set(uit)


@pytest.mark.parametrize(
    ("uit", "storing", "verwacht"),
    [
        ([], [], "actief"),
        (["netbeheerder"], [], "actief"),
        (["koop", "netbeheerder"], [], "actief"),
        ([], ["koop"], "gedegradeerd"),
        ([], ["koop", "rvo"], "gedegradeerd"),
        (["netbeheerder"], ["koop"], "gedegradeerd"),
    ],
)
def test_health_status_is_gedegradeerd_bij_een_storing_niet_bij_een_uitgezette_bron(
    uit, storing, verwacht, host_met_bronnen
):
    """Een storing is een afwijking van wat is ingericht; een uitgezette bron is
    ingericht zoals hij is en staat apart onder `bronnen_uit`. Wie op `status`
    let ziet zo alleen echte storingen."""
    assert host_met_bronnen(uit=uit, storing=storing).get_status()["status"] == verwacht


@pytest.mark.parametrize("uit", UIT_GEVALLEN)
def test_startup_meldt_de_uitgezette_bronnen(uit, caplog, host_met_bronnen, monkeypatch):
    """Niet de private methode maar `startup()` zelf: de omgeving staat buiten de
    repo, dus de log bij het opstarten is de plek waar een bron die voor één
    onderzoek is uitgezet, zichtbaar blijft."""
    host = host_met_bronnen(uit=uit)
    monkeypatch.setattr(
        vlam_host, "MCP_SERVERS", {n: p for n, p in vlam_host.MCP_SERVERS.items() if n not in uit}
    )
    host.server_status = {}
    host.registry.register_server = AsyncMock()
    import asyncio

    with caplog.at_level("WARNING", logger=LOGGER):
        asyncio.run(host.startup())
    assert host.registry.register_server.await_count == len(ALLE) - len(uit)
    assert [n for n in ALLE if n not in uit] == sorted(host.server_status)
    assert [m.split("'")[1] for m in _waarschuwingen(caplog)] == sorted(uit)


def test_regelstatus_geeft_de_bron_van_de_maatregelen_toestemming_door():
    from regelloop import Uitkomst

    plicht = Uitkomst(klaar=True, wacht_op=None, reden="", resultaat={})
    maatregelen = Uitkomst(
        klaar=False, wacht_op="toestemming", reden="", resultaat=None,
        bron="Business Wallet", scope="netbeheerder",
    )
    status = vlam_host._regel_status_dict(plicht, maatregelen)
    assert status["maatregelen"]["toestemming_bron"] == "Business Wallet"


def test_verborgen_bronnen_volgen_het_akkoord_per_gesprek(host_met_bronnen):
    """Hetzelfde predicaat als de poort: een bron die akkoord vergt en dat
    akkoord in dit gesprek nog niet heeft, gaat niet naar het model."""
    host = host_met_bronnen()
    assert host._verborgen_bronnen("g1") == {"kvk", "netbeheerder"}
    host.toestemming["g1"] = {"kvk"}
    assert host._verborgen_bronnen("g1") == {"netbeheerder"}
    host.toestemming["g1"] = {"kvk", "netbeheerder"}
    assert host._verborgen_bronnen("g1") == frozenset()
    assert host._verborgen_bronnen("ander-gesprek") == {"kvk", "netbeheerder"}


def _tool(vorm: str, naam: str) -> dict:
    if vorm == "anthropic":
        return {"name": naam, "description": "", "input_schema": {}}
    return {"type": "function", "function": {"name": naam, "parameters": {}}}


@pytest.mark.parametrize(
    ("akkoord", "verwacht"),
    [
        (set(), ["regelrecht__execute_law"]),
        ({"kvk"}, ["kvk__mijn_bedrijf", "regelrecht__execute_law"]),
        ({"kvk", "netbeheerder"}, ["kvk__mijn_bedrijf", "netbeheerder__verbruik", "regelrecht__execute_law"]),
    ],
)
@pytest.mark.parametrize("vorm", ["anthropic", "openai"])
def test_de_tool_lijst_laat_bronnen_zonder_akkoord_weg(akkoord, verwacht, vorm, host_met_bronnen):
    host = host_met_bronnen()
    host.toestemming["g1"] = set(akkoord)
    alle = [_tool(vorm, n) for n in ("kvk__mijn_bedrijf", "netbeheerder__verbruik", "regelrecht__execute_law")]
    namen = [x.get("name") or x["function"]["name"] for x in host._tools_voor_model("g1", alle)]
    assert namen == verwacht


def test_de_poort_weigert_precies_wat_het_filter_verbergt(host_met_bronnen):
    """Filter en poort delen `_verborgen_bronnen`; dit toetst de poort zelf."""
    import asyncio

    host = host_met_bronnen()
    host.toestemming["g1"] = {"kvk"}

    async def aanroep():
        return {"data": {"ok": True}}

    async def draai():
        uit = {}
        for tool_key in ("kvk__mijn_bedrijf", "netbeheerder__verbruik", "regelrecht__execute_law"):
            _, fout, aangeroepen = await host._bron_aanroep_gated(aanroep, tool_key, {}, "g1")
            uit[tool_key] = (aangeroepen, fout.code if fout else None)
        return uit

    uit = asyncio.run(draai())
    assert uit["kvk__mijn_bedrijf"] == (True, None)
    assert uit["netbeheerder__verbruik"] == (False, "TOESTEMMING_VEREIST")
    assert uit["regelrecht__execute_law"] == (True, None)


def test_een_nieuw_gesprek_begint_zonder_akkoord(host_met_bronnen):
    host = host_met_bronnen()
    sleutel = host._conv_key("62345681", "s1", "claude")
    host.toestemming[sleutel] = {"kvk", "netbeheerder"}
    host.clear_session("62345681", "s1")
    assert sleutel not in host.toestemming
    assert host._verborgen_bronnen(sleutel) == {"kvk", "netbeheerder"}


def test_de_prompt_noemt_de_bronnen_waarvan_de_tools_verborgen_zijn(host_met_bronnen):
    """Anders schrijft de routeringstabel een tool voor die het model niet ziet."""
    host = host_met_bronnen()
    sleutel = host._conv_key("62345681", "s1", "claude")
    prompt = host._system_prompt("claude", has_tools=True, conv_key=sleutel)
    assert "AKKOORD NOG NIET VASTGELEGD" in prompt
    assert BRON_LABELS["kvk"] in prompt and BRON_LABELS["netbeheerder"] in prompt
    host.toestemming[sleutel] = {"kvk", "netbeheerder"}
    assert "AKKOORD NOG NIET VASTGELEGD" not in host._system_prompt("claude", has_tools=True, conv_key=sleutel)
    # Het CLI-transport filtert niet en krijgt het blok dus ook niet.
    assert "AKKOORD NOG NIET VASTGELEGD" not in host._system_prompt(
        "claude", has_tools=True, cli_transport=True, conv_key=sleutel
    )

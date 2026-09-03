"""Een bron die niet geconfigureerd is, staat uit; een bron die niet opkwam, heeft
een storing. Het model krijgt ze allebei te horen, maar anders: over een storing
meldt het wat er mist, over een uitgezette bron zwijgt het.

`bronnen_offline` keek alleen naar servers die wél in de configuratie stonden
maar niet startten. Schakel je een bron uit door hem uit de configuratie te
halen - bijvoorbeeld de Business Wallet, om een onderzoek op eigen opgaven te
laten draaien - dan stond hij nergens als "weg", en bleef de assistent hem
beloven: "uw energieverbruik haal ik op uit uw Business Wallet".

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


def test_een_niet_geconfigureerde_bron_staat_uit_en_is_geen_storing(host_met_bronnen):
    """De wallet uit de configuratie halen is genoeg om hem uit te schakelen."""
    host = host_met_bronnen(uit=["netbeheerder"])
    assert host.bronnen_uit == ["netbeheerder"]
    assert host.bronnen_offline == []


def test_een_gestarte_bron_telt_niet_als_weg(host_met_bronnen):
    assert host_met_bronnen().bronnen_offline == []


def test_een_bron_die_niet_opkwam_blijft_gemeld(host_met_bronnen):
    """Het bestaande geval mag niet sneuvelen met deze wijziging."""
    assert "koop" in host_met_bronnen(storing=["koop"]).bronnen_offline


def test_de_lijsten_blijven_gesorteerd_en_gescheiden(host_met_bronnen):
    """De lijsten gaan de prompt in; een dubbele bron leest als een fout."""
    host = host_met_bronnen(uit=["netbeheerder"], storing=["koop"])
    assert host.bronnen_offline == ["koop"]
    assert host.bronnen_uit == ["netbeheerder"]


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


def _tool(transport: str, naam: str) -> dict:
    if transport == "anthropic":
        return {"name": naam, "description": "", "input_schema": {}}
    return {"type": "function", "function": {"name": naam, "parameters": {}}}


def _namen(tools: list[dict]) -> list[str]:
    return [t.get("name") or t["function"]["name"] for t in tools]


ALLE_TOOLS = ("kvk__mijn_bedrijf", "netbeheerder__verbruik", "regelrecht__execute_law",
              "rvo__zoek_regeling", "koop__zoek")
VRIJ = ["regelrecht__execute_law", "rvo__zoek_regeling", "koop__zoek"]


@pytest.mark.parametrize("transport", ["anthropic", "openai"])
def test_tools_die_akkoord_vergen_staan_pas_na_akkoord_in_de_lijst(transport, host_met_bronnen):
    """De poort weigert een aanroep vóór akkoord al; maar een tool die het model
    niet ziet, roept het ook niet aan, en dat scheelt een beurt en een bronfout."""
    host = host_met_bronnen()
    alle = [_tool(transport, n) for n in ALLE_TOOLS]
    host._regel_status_laatst["g1"] = {"klaar": False, "wacht_op": "toestemming"}
    assert _namen(host._tools_voor_model("g1", alle)) == VRIJ
    host.toestemming["g1"] = {"kvk"}
    assert "kvk__mijn_bedrijf" in _namen(host._tools_voor_model("g1", alle))
    assert "netbeheerder__verbruik" not in _namen(host._tools_voor_model("g1", alle))
    host.toestemming["g1"] = {"kvk", "netbeheerder"}
    assert _namen(host._tools_voor_model("g1", alle)) == _namen(alle)


@pytest.mark.parametrize(
    "status",
    [None, {"klaar": False, "wacht_op": None}, {"klaar": False, "wacht_op": "onbekend"}],
)
def test_zonder_deelverzoek_blijft_de_lijst_heel(status, host_met_bronnen):
    """Kwam de regelloop niet tot een deelverzoek (RegelRecht weg, onleesbaar
    antwoord), dan is er geen knop om akkoord te geven; de tools verbergen zou
    het Handelsregister dan onbereikbaar maken. De poort blijft de grens."""
    host = host_met_bronnen()
    alle = [_tool("anthropic", n) for n in ALLE_TOOLS]
    if status is not None:
        host._regel_status_laatst["g1"] = status
    assert _namen(host._tools_voor_model("g1", alle)) == _namen(alle)


def test_een_ander_gesprek_deelt_het_akkoord_niet(host_met_bronnen):
    host = host_met_bronnen()
    alle = [_tool("anthropic", n) for n in ALLE_TOOLS]
    for g in ("g1", "g2"):
        host._regel_status_laatst[g] = {"klaar": True, "wacht_op": None}
    host.toestemming["g1"] = {"kvk", "netbeheerder"}
    assert _namen(host._tools_voor_model("g1", alle)) == _namen(alle)
    assert _namen(host._tools_voor_model("g2", alle)) == VRIJ

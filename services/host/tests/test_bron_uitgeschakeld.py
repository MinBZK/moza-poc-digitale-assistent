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


def test_elke_bron_heeft_een_omgevingsvariabele():
    """De waarschuwing noemt de variabele uit de configuratie; een bron zonder
    variabele zou een naam verzinnen die niemand kan zetten."""
    assert set(BRON_LABELS) == set(MCP_SERVER_ENV_KEYS)


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


def test_verborgen_bronnen_en_poort_zien_dezelfde_scope(host_met_bronnen):
    """Wat het filter verbergt, weigert de poort; wat het filter toont, laat de
    poort door. Anders toont de een een tool die de ander weigert."""
    host = host_met_bronnen()
    host.toestemming["g1"] = {"kvk"}
    verborgen = host._verborgen_bronnen("g1")
    for tool_key in ("kvk__mijn_bedrijf", "netbeheerder__verbruik", "regelrecht__execute_law"):
        scope = vlam_host.scope_uit_tool(tool_key)
        weigert = scope in vlam_host.TOESTEMMINGSPLICHTIGE_SCOPES and scope not in host.toestemming["g1"]
        assert (scope in verborgen) == weigert, tool_key


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

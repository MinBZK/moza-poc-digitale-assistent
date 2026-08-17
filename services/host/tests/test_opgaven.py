"""`opgaven` op het contract (taak 6).

De frontend structureert de formulierantwoorden (radioknoppen) al; zonder dit
veld slaat ze dat plat tot een zin die het model weer moet interpreteren, en is
een antwoord niet meer toerekenbaar aan wie hem gaf. Deze tests bewijzen twee
dingen: de opgaven landen als feiten met bron "de ondernemer" en soort "opgave"
vóórdat de orkestratielus draait (anders vraagt de lus er opnieuw om), en een
opgave die niet in de routeringstabel staat met `soort == "opgave"` wordt
geweigerd — een frontend mag geen willekeurig feit de kaart in schrijven.
"""

import json
import os
import types

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import vlam_host  # noqa: E402
from feiten import samenvoegen  # noqa: E402

SESSIE = "85234567"


def _fake_claude_client():
    async def _create(**kwargs):
        block = types.SimpleNamespace(type="text", text="Ik vraag het na.")
        return types.SimpleNamespace(content=[block], usage=None)

    return types.SimpleNamespace(api_key="x", messages=types.SimpleNamespace(create=_create))


async def _drain(gen):
    async for _ in gen:
        pass


# --- Rechtstreeks tegen de helper: filter en herkomst-verpakking -----------


def test_bekende_opgave_krijgt_bron_de_ondernemer_en_soort_opgave():
    feiten = vlam_host._opgaven_als_feiten({"MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": True})
    assert feiten == {
        "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": {
            "waarde": True,
            "bron": "de ondernemer",
            "soort": "opgave",
        }
    }


def test_opgave_niet_in_de_routeringstabel_wordt_geweigerd():
    feiten = vlam_host._opgaven_als_feiten({"OMZET_2025": 100_000})
    assert feiten == {}


def test_veld_in_de_routeringstabel_met_andere_soort_wordt_ook_geweigerd():
    """IS_WOONFUNCTIE staat wél in de tabel, maar als registratie (KvK) — niet
    als opgave. Een frontend mag zich niet voor die bron uitgeven."""
    feiten = vlam_host._opgaven_als_feiten({"IS_WOONFUNCTIE": True})
    assert feiten == {}


def test_lege_of_ontbrekende_opgaven_geven_geen_feiten():
    assert vlam_host._opgaven_als_feiten(None) == {}
    assert vlam_host._opgaven_als_feiten({}) == {}


def test_opgave_met_waarde_null_levert_geen_feit_op():
    """`opgaven` is een publiek HTTP-veld dat elke client kan vullen. Een
    `null` erin mag geen feit met `waarde=None` opleveren: dat gaat als
    parameter naar de wet en rendert als het woord "None" in het antwoord."""
    feiten = vlam_host._opgaven_als_feiten({"MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": None})
    assert feiten == {}


def test_opgave_met_waarde_false_blijft_wel_een_feit():
    """De None-filter mag niet per ongeluk ook falsy-maar-geldige waarden
    (False, 0, "") wegvangen - alleen None is geen antwoord."""
    feiten = vlam_host._opgaven_als_feiten({"MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": False})
    assert feiten["MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF"]["waarde"] is False


# --- Via de publieke ingang: landen vóór de regelloop draait ---------------


async def test_opgaven_landen_in_de_feitenkaart_voordat_de_lus_draait():
    """De eerste aanroep van de lus (`regelrecht__execute_law`) draagt de
    opgave al in zijn parameters — dat kan alleen als hij al in de feitenkaart
    stond vóórdat `volg_regel` zijn eerste ronde deed."""
    gezien_parameters = []

    class _Registry:
        tool_map = {"regelrecht__execute_law": ("regelrecht", {})}

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            gezien_parameters.append(dict(arguments.get("parameters") or {}))
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]}})

    host = vlam_host.VLAMHost()
    host.registry = _Registry()
    host.claude_client = _fake_claude_client()

    await _drain(
        host.chat_stream(
            "sess",
            "Geldt de informatieplicht voor mij?",
            mode="claude",
            session_kvk=SESSIE,
            opgaven={"MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": True},
        )
    )

    assert gezien_parameters, "de regelloop heeft de wet niet aangeroepen"
    assert gezien_parameters[0]["MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF"] is True

    conv_key = host._conv_key(SESSIE, "sess", "claude")
    assert host.feiten[conv_key]["MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF"] == {
        "waarde": True,
        "bron": "de ondernemer",
        "soort": "opgave",
    }


async def test_onbekende_opgave_landt_niet_in_de_feitenkaart():
    class _Registry:
        tool_map = {"regelrecht__execute_law": ("regelrecht", {})}

        def get_openai_tools(self):
            return []

        def get_anthropic_tools(self):
            return []

        async def call_tool(self, tool_key, arguments):
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "IS_WOONFUNCTIE"}]}})

    host = vlam_host.VLAMHost()
    host.registry = _Registry()
    host.claude_client = _fake_claude_client()

    await _drain(
        host.chat_stream(
            "sess",
            "hoi",
            mode="claude",
            session_kvk=SESSIE,
            opgaven={"WACHTWOORD": "geheim"},
        )
    )

    conv_key = host._conv_key(SESSIE, "sess", "claude")
    assert "WACHTWOORD" not in host.feiten.get(conv_key, {})


# --- Endpoint-bedrading: het contractveld bereikt de host -------------------


client = TestClient(api.app)


@pytest.fixture(autouse=True)
def _sessie(monkeypatch):
    monkeypatch.setattr(api, "kvk_uit_header", lambda w: SESSIE if w == SESSIE else None)


def test_chat_stream_endpoint_geeft_opgaven_door_aan_de_host(monkeypatch):
    gezien = {}

    async def _fake_stream(session_id, message, mode="vlam", session_kvk="", **kw):
        gezien.update(kw)
        yield {"type": "answer", "message": "ok"}
        yield {"type": "done"}

    monkeypatch.setattr(api.host, "chat_stream", _fake_stream)

    r = client.post(
        "/chat/stream",
        json={"message": "hoi", "opgaven": {"MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": True}},
        headers={"X-Test-User": SESSIE},
    )
    assert r.status_code == 200
    assert gezien.get("opgaven") == {"MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": True}


def test_chat_endpoint_geeft_opgaven_door_aan_de_host(monkeypatch):
    gezien = {}

    async def _fake_chat(session_id, message, mode="vlam", session_kvk="", **kw):
        gezien.update(kw)
        return "ok"

    monkeypatch.setattr(api.host, "chat", _fake_chat)

    r = client.post(
        "/chat",
        json={"message": "hoi", "opgaven": {"TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS": False}},
        headers={"X-Test-User": SESSIE},
    )
    assert r.status_code == 200
    assert gezien.get("opgaven") == {"TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS": False}


def test_correctie_op_een_registratie_komt_door_als_opgave():
    """De ondernemer mag de kas-afleiding uit de SBI-omschrijving corrigeren.

    `TEELT_GEWASSEN_IN_KAS` komt uit de KvK, maar het handelsregister kent het
    begrip "kas" niet: wij leiden het af uit "(onder glas)" in de
    SBI-omschrijving. Die afleiding is van ons, dus de ondernemer moet erover
    heen kunnen. De correctie draagt zichtbaar wie hem deed.
    """
    feiten = vlam_host._opgaven_als_feiten({"TEELT_GEWASSEN_IN_KAS": False})
    assert feiten["TEELT_IN_KAS"]["waarde"] is False
    assert feiten["TEELT_IN_KAS"]["soort"] == "opgave"
    assert "de ondernemer" in feiten["TEELT_IN_KAS"]["bron"]
    assert "KvK" in feiten["TEELT_IN_KAS"]["bron"]


def test_registratie_zonder_correctierecht_blijft_geweigerd():
    """Alleen expliciet gemarkeerde velden zijn corrigeerbaar.

    `IS_WOONFUNCTIE` komt uit de BAG-verrijking en is een waarneming, geen
    afleiding van ons; een client mag die niet overschrijven.
    """
    assert vlam_host._opgaven_als_feiten({"IS_WOONFUNCTIE": True}) == {}


def test_correctie_overleeft_een_latere_kvk_ophaling():
    """Zonder deze regel wint de laatste ophaling van de eerdere correctie."""
    feiten = {}
    samenvoegen(feiten, vlam_host._opgaven_als_feiten({"TEELT_GEWASSEN_IN_KAS": False}))
    samenvoegen(
        feiten,
        {"TEELT_IN_KAS": {"waarde": True, "bron": "KvK Handelsregister", "soort": "registratie"}},
    )
    assert feiten["TEELT_IN_KAS"]["waarde"] is False
    assert feiten["TEELT_IN_KAS"]["soort"] == "opgave"

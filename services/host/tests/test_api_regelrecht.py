"""Endpoint-laag: GET /regelrecht/drempels en /regelrecht/definities.

Draait netwerkloos: zonder lifespan starten er geen MCP-servers, dus de host
valt op de lokale fallback terug. Test de routing, de query-binding en de 404
bij een niet-toegestane wet.
"""

import os

# Maak host-constructie bij import robuust zonder echte sleutel (er worden geen
# LLM-calls gedaan: de /regelrecht-endpoints raken Anthropic/VLAM niet).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(api.app)


def test_drempels_endpoint_geeft_drempelwaarden():
    r = client.get("/regelrecht/drempels")
    assert r.status_code == 200
    body = r.json()
    assert body["drempelwaarden"]["DREMPEL_ELEKTRICITEIT_KWH"] == 50000
    assert body["drempelwaarden"]["DREMPEL_GAS_M3"] == 25000


def test_definities_informatieplicht_200():
    r = client.get(
        "/regelrecht/definities",
        params={"law": "omgevingswet/energiebesparing/informatieplicht"},
    )
    assert r.status_code == 200
    assert "definities" in r.json()


def test_definities_onbekende_wet_geeft_404():
    r = client.get("/regelrecht/definities", params={"law": "zorgtoeslagwet"})
    assert r.status_code == 404


def test_definities_zonder_law_geeft_422():
    r = client.get("/regelrecht/definities")
    assert r.status_code == 422

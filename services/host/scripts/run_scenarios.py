"""Scenario-tests voor de digitale-assistent-backend.

Laat per scenario zien welke events de frontend krijgt, zodat we
weten hoe de UI zich gedraagt bij geen API-sleutel, upstream-fouten,
en MCP- vs CLI-transport.

Run: python test_scenarios.py
"""

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

# Leeg de env-variabelen voordat config.py geladen wordt, zodat het
# lokale .env-bestand (met echte keys) niet wordt overgenomen.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["VLAM_API_KEY"] = ""

# De host-modules liggen een map hoger; zonder dit draait het script alleen als
# je toevallig in services/host staat.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic  # noqa: E402
import openai  # noqa: E402

import vlam_host  # noqa: E402
from config import ALLOW_API_KEY_OVERRIDE  # noqa: E402
from vlam_host import VLAMHost  # noqa: E402


def _geen_sleutel_code() -> str:
    """Welke melding hoort bij "geen sleutel" in deze omgeving?

    Staat de override uit, dan negeert de host een ingevulde sleutel en verwijst
    de melding naar de beheerder in plaats van naar het instellingenpaneel.
    """
    return "LLM_GEEN_SLEUTEL" if ALLOW_API_KEY_OVERRIDE else "LLM_NIET_INGESTELD"


async def collect(gen):
    return [event async for event in gen]


def summary(events):
    """Comprimeer een lijst events tot een leesbare samenvatting."""
    return [(e["type"], e.get("message", e.get("data", ""))[:80]) for e in events]


def assert_has_event(events, event_type, code=None):
    """Zoek een event, desgewenst met een specifieke foutcode.

    Op `code` en niet op een tekstfragment (PDR-011): de melding is bewust
    herschrijfbaar, de code is het contract. Zo breekt dit script niet op een
    betere formulering, wel op een verkeerde classificatie.
    """
    for e in events:
        if e["type"] != event_type:
            continue
        if code is None or e.get("code") == code:
            return e
    raise AssertionError(
        f"Geen {event_type!r}-event met code {code!r} gevonden. "
        f"Events: {summary(events)}"
    )


def make_fake_status_error():
    """Maak een APIStatusError die lijkt op een 401 van de upstream."""
    body = {"error": {"message": "invalid api key"}}
    response = AsyncMock(status_code=401)
    return anthropic.APIStatusError(
        message="Unauthorized", response=response, body=body
    )


async def scenario_health_no_config():
    """Scenario: /health zonder draaiende MCP-servers en zonder keys.

    Toont wat de frontend ontvangt: backends-flags, server_status-dict
    (leeg als startup() niet liep) en cli-dict (afhankelijk van welke
    binaries lokaal aanwezig zijn).
    """
    host = VLAMHost()
    status = host.get_status()
    assert status["backends"]["claude"] is False, "claude backend lijkt gekoppeld"
    assert status["backends"]["vlam"] is False, "vlam backend lijkt gekoppeld"
    assert status["servers"] == {}, f"servers = {status['servers']!r}"
    assert set(status["cli"]) == {"kvk", "koop", "regelrecht", "rvo"}
    return status


async def scenario_vlam_no_key():
    """VLAM geselecteerd, geen API-sleutel, geen override."""
    host = VLAMHost()
    events = await collect(host.chat_stream("s1", "hi", mode="vlam"))
    assert_has_event(events, "error", _geen_sleutel_code())
    assert_has_event(events, "done")
    return events


async def scenario_claude_no_key():
    """Claude geselecteerd, geen API-sleutel, geen override."""
    host = VLAMHost()
    events = await collect(host.chat_stream("s2", "hi", mode="claude"))
    assert_has_event(events, "error", _geen_sleutel_code())
    assert_has_event(events, "done")
    return events


async def scenario_cli_vlam_no_key():
    """CLI:vlam geselecteerd, geen API-sleutel — zelfde check als MCP."""
    host = VLAMHost()
    events = await collect(host.chat_stream("s3", "hi", mode="cli:vlam"))
    assert_has_event(events, "error", _geen_sleutel_code())
    return events


async def scenario_cli_claude_no_key():
    """CLI:claude geselecteerd, geen API-sleutel — zelfde check als MCP."""
    host = VLAMHost()
    events = await collect(host.chat_stream("s4", "hi", mode="cli:claude"))
    assert_has_event(events, "error", _geen_sleutel_code())
    return events


# Sleutels met de vorm die de host accepteert (minstens 20 tekens, cijfer én
# letter — zie api._validate_api_key en log_redaction.looks_like_a_key).
FAKE_CLAUDE_KEY = "sk-ant-fake000000000000000"
FAKE_VLAM_KEY = "vlamtoken-fake0123456789"


async def scenario_claude_upstream_error():
    """Claude met override-key, maar upstream retourneert 401.

    We vervangen de SDK-constructor, niet een host-methode: zo loopt het
    scenario door het échte `_request_clients`-pad, inclusief het sluiten van de
    override-client na afloop.
    """
    host = VLAMHost()

    class FakeClaudeClient:
        def __init__(self, api_key="", **_kwargs):
            self.api_key = api_key
            self.messages = SimpleNamespace(create=self._create)

        async def _create(self, **kwargs):
            raise make_fake_status_error()

        async def close(self):
            pass

    with patch.object(vlam_host.anthropic, "AsyncAnthropic", FakeClaudeClient):
        events = await collect(
            host.chat_stream(
                "s5", "hi", mode="claude", claude_api_key_override=FAKE_CLAUDE_KEY
            )
        )
    # 401 upstream = een geweigerde sleutel, geen algemene storing.
    assert_has_event(events, "error", "LLM_SLEUTEL_ONGELDIG")
    return events


async def scenario_vlam_upstream_error():
    """VLAM met override-key, maar upstream retourneert 500."""
    host = VLAMHost()

    class FakeVlamClient:
        def __init__(self, api_key="", **_kwargs):
            self.api_key = api_key
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        async def _create(self, **kwargs):
            raise openai.APIStatusError(
                message="Server error",
                response=AsyncMock(status_code=500),
                body={"error": "upstream"},
            )

        async def close(self):
            pass

    # Zonder base-url slaat `_request_clients` de vlam-override over.
    with (
        patch.object(vlam_host.openai, "AsyncOpenAI", FakeVlamClient),
        patch.object(vlam_host, "VLAM_BASE_URL", "https://vlam.test/v1"),
    ):
        events = await collect(
            host.chat_stream(
                "s6", "hi", mode="vlam", vlam_api_key_override=FAKE_VLAM_KEY
            )
        )
    # 500 upstream = het model ligt er tijdelijk uit.
    assert_has_event(events, "error", "LLM_OVERBELAST")
    return events


SCENARIOS = [
    ("health zonder configuratie", scenario_health_no_config),
    ("VLAM + MCP, geen key", scenario_vlam_no_key),
    ("Claude + MCP, geen key", scenario_claude_no_key),
    ("VLAM + CLI, geen key", scenario_cli_vlam_no_key),
    ("Claude + CLI, geen key", scenario_cli_claude_no_key),
    ("Claude + MCP, upstream 401", scenario_claude_upstream_error),
    ("VLAM + MCP, upstream 500", scenario_vlam_upstream_error),
]


async def main():
    passed = 0
    failed = 0
    for name, scenario in SCENARIOS:
        try:
            result = await scenario()
            if isinstance(result, list):
                print(f"PASS  {name}")
                for t, msg in summary(result):
                    print(f"        {t:8} {msg}")
            else:
                print(f"PASS  {name}")
                for k, v in result.items():
                    print(f"        {k}: {v}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print()
    print(f"{passed} geslaagd, {failed} mislukt")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""Kindprocessen krijgen geen LLM-sleutels mee (MVP-02).

De host start MCP-servers (stdio) en bash-CLI-wrappers. Geen van beide heeft
een LLM-sleutel nodig. Het MCP-transport had die grens al; het CLI-transport
gaf de volledige `os.environ` door. Deze tests borgen dat beide paden nu
dezelfde allowlist volgen — en dat de config die de scripts écht uitlezen er
wél doorheen komt, want een te strakke lijst breekt de bronnen stilletjes.
"""

import pytest

import cli_executor
import mcp_client
from subprocess_env import (
    CLI_ALLOWLIST,
    MCP_ALLOWLIST,
    NEVER_PASS_THROUGH,
    subprocess_env,
)

ALLE_LIJSTEN = [
    pytest.param(MCP_ALLOWLIST, id="mcp"),
    pytest.param(CLI_ALLOWLIST, id="cli"),
]


@pytest.mark.parametrize("allowlist", ALLE_LIJSTEN)
def test_llm_sleutels_staan_niet_op_de_allowlist(allowlist):
    assert not set(allowlist) & set(NEVER_PASS_THROUGH)


@pytest.mark.parametrize("allowlist", ALLE_LIJSTEN)
def test_llm_sleutels_komen_niet_in_de_env(monkeypatch, allowlist):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-GEHEIM")
    monkeypatch.setenv("VLAM_API_KEY", "vlam-GEHEIM")
    env = subprocess_env(allowlist)
    assert "ANTHROPIC_API_KEY" not in env
    assert "VLAM_API_KEY" not in env
    assert "GEHEIM" not in "".join(env.values())


@pytest.mark.parametrize("allowlist", ALLE_LIJSTEN)
def test_onbekende_variabelen_worden_weggelaten(monkeypatch, allowlist):
    monkeypatch.setenv("EEN_RANDOM_SECRET", "waarde")
    assert "EEN_RANDOM_SECRET" not in subprocess_env(allowlist)


@pytest.mark.parametrize(
    "name",
    [
        # Wat de bash-wrappers daadwerkelijk uitlezen: services/cli/lib/config.sh
        # plus de `${VAR:-default}`-regels boven in koop-cli en regelrecht-cli.
        "KVK_API_BASE",
        "KVK_API_KEY",
        "KVK_SESSIE_NUMMER",
        "KVK_AUDIT_LOG",
        "REGELRECHT_RPC_URL",
        "KOOP_SRU_URL",
        "KOOP_SRU_CONNECTION",
    ],
)
def test_cli_config_komt_er_wel_doorheen(monkeypatch, name):
    monkeypatch.setenv(name, "test-waarde")
    assert subprocess_env(CLI_ALLOWLIST)[name] == "test-waarde"


@pytest.mark.parametrize(
    "name", ["DEMO_KVK_NUMMER", "REGELRECHT_RPC_URL", "BAG_API_KEY", "KVK_TEST_API_KEY"]
)
def test_mcp_config_komt_er_wel_doorheen(monkeypatch, name):
    monkeypatch.setenv(name, "test-waarde")
    assert subprocess_env(MCP_ALLOWLIST)[name] == "test-waarde"


@pytest.mark.parametrize("allowlist", ALLE_LIJSTEN)
@pytest.mark.parametrize("name", ["PATH", "HOME", "HTTPS_PROXY", "SSL_CERT_FILE"])
def test_systeembasis_blijft_doorgegeven(monkeypatch, allowlist, name):
    """Zonder PATH start er niets; zonder proxy/TLS-vars breekt uitgaand verkeer."""
    monkeypatch.setenv(name, "test-waarde")
    assert subprocess_env(allowlist)[name] == "test-waarde"


def test_extra_overschrijft_de_proces_env(monkeypatch):
    """Per-aanroep-injectie (bv. het sessie-KvK) wint van de proces-omgeving."""
    monkeypatch.setenv("KVK_SESSIE_NUMMER", "00000000")
    env = subprocess_env(CLI_ALLOWLIST, {"KVK_SESSIE_NUMMER": "85234567"})
    assert env["KVK_SESSIE_NUMMER"] == "85234567"


async def test_cli_subprocess_krijgt_de_beperkte_env(monkeypatch):
    """End-to-end op het CLI-transport: wat gaat er echt naar create_subprocess_exec?"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-GEHEIM")
    monkeypatch.setenv("VLAM_API_KEY", "vlam-GEHEIM")
    vastgelegd = {}

    class _Proc:
        returncode = 0

        async def communicate(self):
            return b"{}", b""

    async def _fake_exec(*cmd, env=None, **kwargs):
        vastgelegd["env"] = env
        return _Proc()

    monkeypatch.setattr(cli_executor.asyncio, "create_subprocess_exec", _fake_exec)
    await cli_executor.execute_cli_tool("kvk__mijn_bedrijf", {"kvk_nummer": "85234567"})

    env = vastgelegd["env"]
    assert env is not None, "None betekent: het kindproces erft de hele omgeving"
    assert "ANTHROPIC_API_KEY" not in env
    assert "VLAM_API_KEY" not in env
    # De sessie-injectie uit PDR-009 moet er wél in zitten.
    assert env["KVK_SESSIE_NUMMER"] == "85234567"


def test_mcp_client_gebruikt_dezelfde_bron(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-GEHEIM")
    env = mcp_client._subprocess_env()
    assert "ANTHROPIC_API_KEY" not in env
    assert set(env) <= set(MCP_ALLOWLIST)

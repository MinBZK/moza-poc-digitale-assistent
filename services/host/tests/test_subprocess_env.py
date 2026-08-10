"""Kindprocessen krijgen geen LLM-sleutels mee (MVP-02).

De host start MCP-servers (stdio) en bash-CLI-wrappers. Geen van beide heeft
een LLM-sleutel nodig. Het MCP-transport had die grens al; het CLI-transport
gaf de volledige `os.environ` door. Deze tests borgen dat beide paden nu
dezelfde allowlist volgen — en dat de config die de scripts écht uitlezen er
wél doorheen komt, want een te strakke lijst breekt de bronnen stilletjes.
"""

import re
from pathlib import Path

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


# --- De allowlists tegen de bron, niet tegen een overgetypte lijst -----------
#
# Een handmatig bijgehouden kopie van "wat de scripts uitlezen" is dezelfde
# dubbel-onderhouden vorm die CLAUDE.md al bij CLI_TOOL_DEFINITIONS_ANTHROPIC
# benoemt: hij kan stil gaan afwijken. Deze tests lezen de namen daarom uit de
# servers en de bash-scripts zelf, zodat een nieuwe variabele die niet op de
# allowlist staat de suite laat vallen in plaats van de bron stilletjes te breken.

_REPO = Path(__file__).resolve().parents[3]

_GETENV = re.compile(r"""os\.getenv\(\s*["']([A-Z_][A-Z0-9_]*)["']""")
# `${VAR:-default}` en `${VAR:=default}`
_BASH_READ = re.compile(r"\$\{([A-Z_][A-Z0-9_]*):[-=]")
_BASH_ASSIGN = re.compile(r"^\s*(?:local\s+|export\s+)?([A-Z_][A-Z0-9_]*)=(.*)$", re.M)


def _mcp_env_namen() -> set[str]:
    namen = set()
    for server in sorted((_REPO / "services" / "mcp").glob("*/server.py")):
        namen |= set(_GETENV.findall(server.read_text()))
    return namen


def _cli_env_namen() -> set[str]:
    """Namen die de bash-wrappers uit de *omgeving* lezen.

    Een `${VAR:-...}` alléén is niet genoeg: `RESOURCE_ID` is een gewone
    scriptvariabele. Config uit de omgeving herken je eraan dat de toekenning
    naar zichzelf verwijst (`KVK_API_BASE="${KVK_API_BASE:-...}"`) of dat er
    helemaal geen toekenning is.
    """
    gelezen: set[str] = set()
    eigen_toekenning: set[str] = set()
    for script in sorted((_REPO / "services" / "cli").rglob("*")):
        if not script.is_file():
            continue
        tekst = script.read_text(errors="ignore")
        gelezen |= set(_BASH_READ.findall(tekst))
        for naam, rechterkant in _BASH_ASSIGN.findall(tekst):
            if f"${{{naam}" not in rechterkant:
                eigen_toekenning.add(naam)
    return gelezen - eigen_toekenning


def test_mcp_allowlist_dekt_wat_de_servers_uitlezen():
    ontbreekt = _mcp_env_namen() - set(MCP_ALLOWLIST)
    assert not ontbreekt, (
        f"MCP-servers lezen deze variabelen uit de omgeving, maar ze staan niet "
        f"op MCP_ALLOWLIST en bereiken de server dus nooit: {sorted(ontbreekt)}"
    )


def test_cli_allowlist_dekt_wat_de_scripts_uitlezen():
    ontbreekt = _cli_env_namen() - set(CLI_ALLOWLIST)
    assert not ontbreekt, (
        f"De CLI-wrappers lezen deze variabelen uit de omgeving, maar ze staan "
        f"niet op CLI_ALLOWLIST: {sorted(ontbreekt)}"
    )


def test_mcp_allowlist_bevat_geen_dode_namen():
    """Andersom: een naam die niemand uitleest suggereert dekking die er niet is.

    `KVK_TEST_API_KEY` stond hier terwijl het een literal in de kvk-server is.
    """
    from subprocess_env import _MCP_CONFIG

    dood = set(_MCP_CONFIG) - _mcp_env_namen()
    assert not dood, f"staat op _MCP_CONFIG maar wordt nergens uitgelezen: {sorted(dood)}"


@pytest.mark.parametrize("name", sorted(_cli_env_namen()))
def test_cli_config_komt_er_wel_doorheen(monkeypatch, name):
    monkeypatch.setenv(name, "test-waarde")
    assert subprocess_env(CLI_ALLOWLIST)[name] == "test-waarde"


@pytest.mark.parametrize("name", sorted(_mcp_env_namen()))
def test_mcp_config_komt_er_wel_doorheen(monkeypatch, name):
    monkeypatch.setenv(name, "test-waarde")
    assert subprocess_env(MCP_ALLOWLIST)[name] == "test-waarde"


@pytest.mark.parametrize("allowlist", ALLE_LIJSTEN)
@pytest.mark.parametrize("name", ["PATH", "HOME", "HTTPS_PROXY", "SSL_CERT_FILE"])
def test_systeembasis_blijft_doorgegeven(monkeypatch, allowlist, name):
    """Zonder PATH start er niets; zonder proxy/TLS-vars breekt uitgaand verkeer."""
    monkeypatch.setenv(name, "test-waarde")
    assert subprocess_env(allowlist)[name] == "test-waarde"


@pytest.mark.parametrize("naam", NEVER_PASS_THROUGH)
def test_extra_kan_een_llm_sleutel_niet_alsnog_doorduwen(naam):
    """`extra` gaat buiten de allowlist om — daar moet de grens ook gelden.

    Zonder afdwinging op runtime raadpleegde alleen een test deze tuple, terwijl
    `env.update(extra)` er ongefilterd doorheen ging.
    """
    env = subprocess_env(CLI_ALLOWLIST, {naam: "sk-ant-GEHEIM", "KVK_API_BASE": "ok"})
    assert naam not in env
    assert env["KVK_API_BASE"] == "ok", "de rest van extra hoort gewoon door te gaan"


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

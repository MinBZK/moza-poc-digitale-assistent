"""De twee andere ingangen op de uitleg-module (PDR-016): MCP-server en CLI.

De MCP-server draait als echt stdio-subproces, met een client die sampling
aanbiedt (het model is een recorder) en een client zonder sampling (krijgt het
prompt terug). De CLI-wrapper draait de lokale stappen; `verwoord` alleen als
dry-run, want dat vergt een host met sleutel.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CreateMessageResult, TextContent

SERVICES = Path(__file__).resolve().parents[2]
SERVER = SERVICES / "mcp" / "uitleg" / "server.py"
CLI = SERVICES / "cli" / "uitleg-cli"
FIXTURE = Path(__file__).parent / "fixtures" / "uitleg_graaf_lks.json"
BEDRAG = json.loads(FIXTURE.read_text())["hoogte_lks_eurocent_per_maand"]


def _data(resultaat) -> dict:
    """De `data` uit het provenance-omhulsel van één TextContent."""
    (blok,) = resultaat.content
    omhulsel = json.loads(blok.text)
    assert set(omhulsel["provenance"]) == {"source", "timestamp", "version"}
    return omhulsel["data"]


async def _met_server(sampling_callback=None):
    params = StdioServerParameters(
        command=sys.executable, args=[str(SERVER)], env={**os.environ, "PYTHONUNBUFFERED": "1"}
    )
    return stdio_client(params), sampling_callback


@pytest.mark.asyncio
async def test_mcp_server_publiceert_drie_tools_met_annotaties():
    ctx, _ = await _met_server()
    async with ctx as (lees, schrijf), ClientSession(lees, schrijf) as sessie:
        await sessie.initialize()
        tools = (await sessie.list_tools()).tools
        assert sorted(t.name for t in tools) == ["regels", "toets", "verwoord"]
        for t in tools:
            assert t.annotations.readOnlyHint is True
            assert t.description


@pytest.mark.asyncio
async def test_mcp_verwoord_via_sampling_geeft_tekst_en_toets():
    gezien: list = []

    async def model(context, params):
        gezien.append(params)
        return CreateMessageResult(
            role="assistant",
            content=TextContent(type="text", text="U krijgt € 897,41 per maand (artikel 10d)."),
            model="nep-model",
        )

    ctx, _ = await _met_server()
    async with ctx as (lees, schrijf), ClientSession(lees, schrijf, sampling_callback=model) as sessie:
        await sessie.initialize()
        r = await sessie.call_tool(
            "verwoord",
            {"regeling": "Loonkostensubsidie", "graaf": BEDRAG["graaf"], "samenvatting": BEDRAG["samenvatting"]},
        )
        data = _data(r)
    assert data["modus"] == "sampling"
    assert data["toets"]["geslaagd"] is True
    assert data["model"] == "nep-model"
    (params,) = gezien
    # Het model kreeg alleen de graaf en het systeemprompt: geen tools, geen geschiedenis.
    assert params.systemPrompt.startswith("U legt een ondernemer uit")
    assert len(params.messages) == 1
    assert "€ 897,41" in params.messages[0].content.text


@pytest.mark.asyncio
async def test_mcp_verwoord_zonder_sampling_geeft_het_prompt_terug():
    ctx, _ = await _met_server()
    async with ctx as (lees, schrijf), ClientSession(lees, schrijf) as sessie:
        await sessie.initialize()
        r = await sessie.call_tool(
            "verwoord", {"regeling": "Loonkostensubsidie", "graaf": BEDRAG["graaf"]}
        )
        data = _data(r)
    assert data["modus"] == "prompt"
    assert data["prompt"].startswith('Regeling: "Loonkostensubsidie"')
    assert "systeemprompt" in data


@pytest.mark.asyncio
async def test_mcp_toets_en_regels_werken_zonder_model():
    ctx, _ = await _met_server()
    async with ctx as (lees, schrijf), ClientSession(lees, schrijf) as sessie:
        await sessie.initialize()
        toets = _data(await sessie.call_tool(
            "toets", {"tekst": "U krijgt € 950,00 (artikel 10d).", "graaf": BEDRAG["graaf"]}
        ))
        regels = _data(await sessie.call_tool("regels", {"graaf": BEDRAG["graaf"]}))
    assert toets["geslaagd"] is False
    assert toets["onbekende_bedragen"] == ["€ 950,00"]
    assert regels["regels"][0].startswith("- uitkomst: hoogte_lks_eurocent_per_maand = € 897,41")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, argumenten, code",
    [
        ("verwoord", {"regeling": "X", "graaf": {"soort": "x"}}, "INPUT_INVALID"),
        # Een ontbrekende `regeling` vangt de SDK al op het schema; een lege is voor ons.
        ("verwoord", {"regeling": " ", "graaf": {"soort": "x", "waarde": 1}}, "ONTBREKEND_VELD"),
        ("toets", {"graaf": {"soort": "x", "waarde": 1}, "tekst": " "}, "ONTBREKEND_VELD"),
    ],
)
async def test_mcp_ongeldige_invoer_geeft_een_catalogusfout(tool, argumenten, code):
    ctx, _ = await _met_server()
    async with ctx as (lees, schrijf), ClientSession(lees, schrijf) as sessie:
        await sessie.initialize()
        data = _data(await sessie.call_tool(tool, argumenten))
    assert data["error"] == code
    assert data["velden"]


# --- CLI -----------------------------------------------------------------------


def _cli(*args, invoer: dict | None = None):
    env = {**os.environ, "UITLEG_PYTHON": sys.executable}
    return subprocess.run(
        ["bash", str(CLI), *args], capture_output=True, text=True, env=env, timeout=60
    )


def _verzoek_bestand(tmp_path: Path) -> Path:
    pad = tmp_path / "verzoek.json"
    pad.write_text(json.dumps({"regeling": "Loonkostensubsidie", **BEDRAG}), encoding="utf-8")
    return pad


def test_cli_regels_geeft_regels_en_prompt(tmp_path):
    r = _cli("regels", str(_verzoek_bestand(tmp_path)))
    assert r.returncode == 0, r.stderr
    uit = json.loads(r.stdout)
    assert uit["regels"][0].startswith("- uitkomst: hoogte_lks_eurocent_per_maand")
    assert "Beslisgraaf" in uit["prompt"]


def test_cli_toets_betrapt_een_verzonnen_bedrag(tmp_path):
    r = _cli("toets", str(_verzoek_bestand(tmp_path)), "--tekst", "U krijgt € 1.000,00 (artikel 10d).")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["onbekende_bedragen"] == ["€ 1.000,00"]


def test_cli_leest_de_uitvoer_van_uitleg_bereken(tmp_path):
    """Keten met de Rust-CLI: `uitleg bereken … | uitleg-cli verzoek --output …`."""
    bereken = tmp_path / "bereken.json"
    bereken.write_text(json.dumps({
        "afleidingen": {
            "hoogte_lks_eurocent_per_maand": {
                "afleiding": {"uitkomst": BEDRAG["graaf"]},
                "tekst": {"kort": [{"tekst": z, "technisch": False} for z in BEDRAG["samenvatting"]]
                          + [{"tekst": "intern", "technisch": True}]},
            }
        }
    }), encoding="utf-8")
    r = _cli("verzoek", str(bereken), "--output", "hoogte_lks_eurocent_per_maand", "--regeling", "LKS")
    assert r.returncode == 0, r.stderr
    verzoek = json.loads(r.stdout)
    assert verzoek["regeling"] == "LKS"
    assert verzoek["samenvatting"] == BEDRAG["samenvatting"]
    assert verzoek["graaf"]["soort"] == "uitkomst"
    ontbreekt = _cli("verzoek", str(bereken), "--output", "bestaat_niet")
    assert ontbreekt.returncode == 2
    assert json.loads(ontbreekt.stderr)["error"] == "NIET_GEVONDEN"


def test_cli_verwoord_dry_run_toont_het_verzoek_zonder_host(tmp_path):
    r = _cli("verwoord", str(_verzoek_bestand(tmp_path)), "--dry-run", "--mode", "vlam")
    assert r.returncode == 0, r.stderr
    assert "/uitleg" in r.stdout
    assert '"mode": "vlam"' in r.stdout


def test_cli_verwoord_zonder_kvk_weigert_met_catalogusfout(tmp_path):
    r = _cli("verwoord", str(_verzoek_bestand(tmp_path)))
    assert r.returncode == 1
    assert json.loads(r.stderr)["error"] == "ONTBREKEND_VELD"

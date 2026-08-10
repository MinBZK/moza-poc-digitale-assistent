"""CLI Executor — voert tool-calls uit via CLI in plaats van MCP.

Mapt dezelfde tool-namen (kvk__mijn_bedrijf, koop__zoek_regelgeving, etc.)
naar CLI-commando's. De LLM ziet dezelfde tools, maar de uitvoering gaat
via subprocess in plaats van MCP stdio.
"""

import asyncio
import json
import logging
from pathlib import Path

from subprocess_env import CLI_ALLOWLIST, subprocess_env

logger = logging.getLogger("vlam.cli")

# Pad naar de CLI-tools (relatief aan services/host/)
CLI_DIR = Path(__file__).resolve().parent.parent / "cli"


def _kvk_env(arguments: dict) -> dict | None:
    """Geef het sessie-KvK als env-override voor de kvk-cli (KVK_SESSIE_NUMMER).

    De kvk-cli leest het KvK-nummer uit die env-var; de host injecteert het
    sessie-KvK zo per aanroep, i.p.v. de proces-brede default (PDR-009).
    """
    kvk = str((arguments or {}).get("kvk_nummer") or "").strip()
    return {"KVK_SESSIE_NUMMER": kvk} if kvk else None


def _loggable_cmd(cmd: list[str]) -> str:
    """Geef alleen de CLI-tool + subcommando terug voor logging, geen argv-waarden.

    De positional argv-waarden kunnen het sessie-KvK-nummer bevatten (bv.
    `regelrecht-cli check <kvk>`); dat hoort niet in de logs (privacy — het
    koppelt een sessie aan een bedrijf). We loggen alleen de niet-waarde-tokens:
    de scriptnaam en de subcommando's/flags.
    """
    tokens = [Path(cmd[0]).name] if cmd else []
    tokens += [c for c in cmd[1:] if c.startswith("-") or c.isalpha()]
    return " ".join(tokens)


async def _run_cli(cmd: list[str], env: dict | None = None) -> str:
    """Voer een CLI-commando uit en retourneer de stdout.

    `env` bevat optionele extra omgevingsvariabelen bovenop de allowlist, o.a.
    het sessie-KvK-nummer voor de kvk-cli (PDR-009).

    Sinds MVP-02 krijgt het subprocess niet meer de volledige `os.environ` mee,
    maar dezelfde soort allowlist als de MCP-servers: geen LLM-sleutels in een
    bash-proces dat ze niet nodig heeft.
    """
    logger.info("$ %s", _loggable_cmd(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=subprocess_env(CLI_ALLOWLIST, env),
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

    stdout_str = stdout.decode().strip()
    stderr_str = stderr.decode().strip()

    if stderr_str:
        # Op DEBUG, niet op INFO: de stderr van de wrappers bevat de aangeroepen
        # URL, en daar staat het sessie-KvK-nummer in (services/cli/lib/request.sh).
        # Dat hoort niet standaard in de logs — zie `_arg_keys` in vlam_host.py,
        # dat om dezelfde reden alleen veldnamen logt. Op de foutroute hieronder
        # gaat de volledige stderr wél mee: daar weegt debugbaarheid zwaarder.
        logger.debug("  stderr: %s", stderr_str)
        logger.info("  stderr: %d bytes (zet DEBUG voor de inhoud)", len(stderr_str))

    # Log response grootte
    logger.info("  response: %d bytes", len(stdout_str))

    if proc.returncode != 0:
        # Log de volledige stderr server-side (nuttig voor debug) maar geef de
        # client alleen een generieke melding. Stderr kan API-keys, file-paden
        # of stack traces uit subprocess-output bevatten die niet bij de
        # frontend horen.
        logger.error(
            "  FOUT (exit %d): %s",
            proc.returncode,
            stderr_str or "(geen stderr)",
        )
        return json.dumps({
            "error": "CLI_FOUT",
            "message": f"CLI-tool faalde (exit {proc.returncode})",
        })

    return stdout.decode().strip()


def _append_fields(cmd: list[str], arguments: dict) -> list[str]:
    """Voeg --fields toe als het LLM specifieke velden vraagt (dataminimalisatie)."""
    fields = arguments.get("fields")
    if fields and isinstance(fields, list):
        cmd += ["--fields", ",".join(str(f) for f in fields)]
    return cmd


async def execute_cli_tool(tool_key: str, arguments: dict) -> str:
    """Vertaal een MCP tool-call naar een CLI-commando en voer uit."""

    if tool_key == "kvk__mijn_bedrijf":
        cmd = [
            str(CLI_DIR / "kvk-cli"),
            "basisprofiel", "get",
            "--provenance",
            "--output", "raw",
        ]
        return await _run_cli(_append_fields(cmd, arguments), env=_kvk_env(arguments))

    if tool_key == "kvk__vestigingen":
        cmd = [
            str(CLI_DIR / "kvk-cli"),
            "basisprofiel", "vestigingen",
            "--provenance",
            "--output", "raw",
        ]
        return await _run_cli(_append_fields(cmd, arguments), env=_kvk_env(arguments))

    if tool_key == "kvk__eigenaar":
        cmd = [
            str(CLI_DIR / "kvk-cli"),
            "basisprofiel", "eigenaar",
            "--provenance",
            "--output", "raw",
        ]
        return await _run_cli(_append_fields(cmd, arguments), env=_kvk_env(arguments))

    if tool_key == "koop__lees_regeling":
        bwb_id = arguments.get("bwb_id", "")
        cmd = [
            str(CLI_DIR / "koop-cli"),
            "regeling", "get", bwb_id,
            "--provenance",
            "--output", "raw",
        ]
        return await _run_cli(_append_fields(cmd, arguments))

    if tool_key == "koop__zoek_regelgeving":
        trefwoord = arguments.get("trefwoord", "")
        cmd = [
            str(CLI_DIR / "koop-cli"),
            "regeling", "zoek", trefwoord,
            "--provenance",
            "--output", "raw",
        ]
        onderwerp = arguments.get("onderwerp")
        if onderwerp:
            cmd += ["--onderwerp", onderwerp]
        type_regeling = arguments.get("type_regeling")
        if type_regeling:
            cmd += ["--type", type_regeling]
        max_resultaten = arguments.get("max_resultaten")
        if max_resultaten:
            cmd += ["--max", str(max_resultaten)]
        return await _run_cli(_append_fields(cmd, arguments))

    if tool_key == "regelrecht__check":
        kvk_nummer = arguments.get("kvk_nummer", "")
        cmd = [
            str(CLI_DIR / "regelrecht-cli"),
            "check", kvk_nummer,
            "--provenance",
            "--output", "raw",
        ]
        elektriciteit = arguments.get("jaarlijks_elektriciteitsverbruik_kwh")
        if elektriciteit is not None:
            cmd += ["--elektriciteit", str(elektriciteit)]
        gas = arguments.get("jaarlijks_gasverbruik_m3")
        if gas is not None:
            cmd += ["--gas", str(gas)]
        woonfunctie = arguments.get("is_woonfunctie")
        if woonfunctie:
            cmd += ["--woonfunctie"]
        return await _run_cli(_append_fields(cmd, arguments))

    if tool_key == "rvo__zoek_regeling":
        trefwoord = arguments.get("trefwoord", "")
        cmd = [
            str(CLI_DIR / "rvo-cli"),
            "regeling", "zoek", trefwoord,
            "--provenance",
            "--output", "raw",
        ]
        return await _run_cli(_append_fields(cmd, arguments))

    if tool_key == "rvo__indienen":
        kvk_nummer = arguments.get("kvk_nummer", "")
        regeling_id = arguments.get("regeling_id", "")
        maatregelen = arguments.get("maatregelen", [])
        maatregelen_csv = ",".join(maatregelen)
        cmd = [
            str(CLI_DIR / "rvo-cli"),
            "rapportage", "indienen",
            kvk_nummer, regeling_id, maatregelen_csv,
            "--confirm",
            "--provenance",
            "--output", "raw",
        ]
        return await _run_cli(cmd)

    return json.dumps({
        "error": "ONBEKENDE_TOOL",
        "message": f"CLI-vertaling niet beschikbaar voor: {tool_key}",
    })

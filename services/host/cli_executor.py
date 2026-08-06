"""CLI Executor — voert tool-calls uit via CLI in plaats van MCP.

Mapt dezelfde tool-namen (kvk__mijn_bedrijf, koop__zoek_regelgeving, etc.)
naar CLI-commando's. De LLM ziet dezelfde tools, maar de uitvoering gaat
via subprocess in plaats van MCP stdio.
"""

import asyncio
import contextlib
import json
import logging
import os
import signal
from pathlib import Path

from config import TOOL_TIMEOUT

logger = logging.getLogger("vlam.cli")

# Pad naar de CLI-tools (relatief aan services/host/)
CLI_DIR = Path(__file__).resolve().parent.parent / "cli"

# Eigen grens per subprocess, altijd strikt binnen `TOOL_TIMEOUT`. Zouden de twee
# elkaar kunnen kruisen, dan annuleert de buitenste grens het opruimen van de
# binnenste en blijft er alsnog een proces hangen.
CLI_TIMEOUT = max(5, min(30, TOOL_TIMEOUT - 5))


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


# Codes die de bash-wrappers zelf uitsturen. Alleen deze worden overgenomen: de
# wrappers interpoleren upstream-tekst ongeëscaped in hun fout-JSON, dus een
# antwoord van buiten kan er een tweede `"error"`-sleutel in schuiven en zo
# kiezen welke melding de gebruiker ziet (json.loads neemt de laatste).
_CLI_CODES = frozenset(
    {
        "NIET_TOEGESTAAN",
        "MISSING_DEPENDENCY",
        "INVALID_INPUT",
        "PARSE_FOUT",
        "API_FOUT",
        "LLM_TOOLCALL_ONGELDIG",
        "TOOL_NIET_IN_TRANSPORT",
        "SOURCE_UNAVAILABLE",
        "NIET_GEVONDEN",
        "EXECUTION_ERROR",
        "ONTBREKEND_VELD",
        "ONTBREKENDE_VELDEN",
    }
)


def _kill_procesgroep(proc) -> None:
    """Dood de wrapper én alles wat hij gestart heeft."""
    if proc.returncode is not None:
        return  # al afgelopen; killpg zou een hergebruikte PID kunnen raken
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


def _cli_fout(stderr: str) -> dict:
    """Lees de foutcode (en eventuele veldnamen) uit de stderr van een wrapper.

    Valt terug op `CLI_FOUT` als er geen bekende code in staat. De begeleidende
    tekst gaat nooit mee: die kan een pad of een interne URL bevatten en hoort in
    de log te blijven.
    """
    for regel in reversed((stderr or "").splitlines()):
        regel = regel.strip()
        if not regel.startswith("{"):
            continue
        try:
            payload = json.loads(regel)
        except (json.JSONDecodeError, ValueError):
            continue
        code = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(code, str) or code not in _CLI_CODES:
            continue
        fout = {"error": code}
        velden = payload.get("velden")
        if isinstance(velden, list) and velden:
            # Meesturen zodat de melding kan zeggen wélk gegeven ontbreekt;
            # `errors.py` schoont en vertaalt de namen.
            fout["velden"] = [str(v) for v in velden[:5]]
        return fout
    return {"error": "CLI_FOUT"}


async def _run_cli(cmd: list[str], env: dict | None = None) -> str:
    """Voer een CLI-commando uit en retourneer de stdout.

    `env` bevat optionele extra omgevingsvariabelen (bovenop de proces-env),
    o.a. het sessie-KvK-nummer voor de kvk-cli (PDR-009).
    """
    logger.info("$ %s", _loggable_cmd(cmd))

    subprocess_env = {**os.environ, **env} if env else None
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=subprocess_env,
        # Eigen procesgroep, zodat we bij een time-out niet alleen de wrapper
        # maar ook zijn kindprocessen (curl, jq, python3) kunnen doden.
        start_new_session=True,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=CLI_TIMEOUT)
    except (TimeoutError, asyncio.CancelledError):
        # Zonder dit bleef het subprocess draaien en stapelden ze op. Let op de
        # twee valkuilen die hier eerder in zaten: `proc.kill()` doodt alleen de
        # wrapper, terwijl een levend kleinkind de pipe openhoudt en `wait()`
        # daardoor nooit terugkeert; en na een geannuleerde `wait_for` levert
        # asyncio geen tweede annulering, dus een onbegrensde `wait()` hangt dan
        # permanent. Vandaar de procesgroep én een grens op het opruimen zelf.
        _kill_procesgroep(proc)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=5)
        raise

    stdout_str = stdout.decode().strip()
    stderr_str = stderr.decode().strip()

    if stderr_str:
        logger.info("  stderr: %s", stderr_str)

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
        # De wrappers schrijven een fout-JSON met een eigen code naar stderr
        # (NIET_TOEGESTAAN, MISSING_DEPENDENCY, INVALID_INPUT). Die code
        # doorgeven scheelt de gebruiker een zinloos "probeer het over een
        # minuut opnieuw" bij een fout die daar niet van overgaat.
        return json.dumps({
            **_cli_fout(stderr_str),
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
    try:
        return await _dispatch_cli_tool(tool_key, arguments)
    except (TypeError, AttributeError) as e:
        # Argumenten in de verkeerde vorm (bv. `maatregelen` als objecten in
        # plaats van strings). Het CLI-transport heeft geen schemavalidatie zoals
        # MCP, dus dat blijkt hier pas. Het is een fout van het model, niet van
        # de bron: melden als storing zou een niet-bestaande storing aankondigen
        # en het model beroven van de kans om te corrigeren.
        logger.error("Tool-argumenten in de verkeerde vorm voor %s: %s", tool_key, e)
        return json.dumps(
            {
                "error": "LLM_TOOLCALL_ONGELDIG",
                "validatiefout": f"argumenten voor {tool_key} hebben niet het verwachte type",
            },
            ensure_ascii=False,
        )


# Argumenten die een CLI-tool nodig heeft. De wrappers nemen ze positioneel aan,
# dus een ontbrekende waarde schuift de rest op: `rvo-cli indienen <kvk> "" "LED"`
# leest "LED" als regeling_id en meldt vervolgens dat de máátregelen ontbreken.
# De gebruiker krijgt dan de opdracht iets aan te leveren wat hij net gaf.
_VERPLICHTE_CLI_ARGUMENTEN = {
    "koop__lees_regeling": ("bwb_id",),
    "koop__zoek_regelgeving": ("trefwoord",),
    "rvo__zoek_regeling": ("trefwoord",),
    "rvo__indienen": ("kvk_nummer", "regeling_id", "maatregelen"),
    "regelrecht__check": ("kvk_nummer",),
}

# Bronnen zonder CLI-wrapper. Het CLI-transport loopt bewust achter op MCP
# (PDR-005/PDR-008); volgt het model tóch de routeringstabel daarheen, dan is
# "stel uw vraag opnieuw" een advies dat per definitie niet kan slagen.
_CLI_BRONNEN = {"kvk", "koop", "regelrecht", "rvo"}
_ALLE_BRONNEN = _CLI_BRONNEN | {"netbeheerder"}

# Tools die het model uit de gedeelde routeringstabel kan halen maar die dit
# transport niet heeft. Bewust GEEN alias naar de CLI-variant: die vertaalt wel
# de naam maar niet de argumenten, en draait bovendien ná `_inject_session_kvk`,
# waardoor een door het model meegegeven KvK-nummer de sessiegrens (PDR-009)
# zou omzeilen. Beter een eerlijke melding dan een halve vertaling.
_NIET_IN_CLI = {"regelrecht__execute_law", "netbeheerder__verbruik"}


def _ontbrekende_argumenten(tool_key: str, arguments: dict) -> list[str]:
    """Welke verplichte argumenten ontbreken (of zijn leeg)?"""
    return [
        naam
        for naam in _VERPLICHTE_CLI_ARGUMENTEN.get(tool_key, ())
        if not (arguments or {}).get(naam)
    ]


async def _dispatch_cli_tool(tool_key: str, arguments: dict) -> str:
    """Kies het CLI-commando dat bij deze tool hoort."""
    if tool_key in _NIET_IN_CLI:
        logger.warning("Tool %r bestaat niet in het CLI-transport", str(tool_key)[:80])
        return json.dumps({"error": "TOOL_NIET_IN_TRANSPORT"}, ensure_ascii=False)

    bron = tool_key.split("__", 1)[0]
    if bron not in _CLI_BRONNEN:
        # Onderscheid tussen "deze bron heeft hier geen wrapper" (wachten helpt
        # niet) en "het model verzon een naam" (opnieuw vragen kan wél helpen),
        # net als `MCPToolRegistry.call_tool` op het MCP-pad.
        code = "BRON_NIET_GESTART" if bron in _ALLE_BRONNEN else "ONBEKENDE_TOOL"
        logger.warning("Geen CLI-wrapper voor %r (tool %r)", bron, str(tool_key)[:80])
        return json.dumps({"error": code}, ensure_ascii=False)

    ontbreekt = _ontbrekende_argumenten(tool_key, arguments)
    if ontbreekt:
        # Vóór het opbouwen van het commando: anders schuiven de positionele
        # argumenten op en meldt de wrapper het verkeerde veld.
        logger.error("CLI-aanroep %s mist argumenten: %s", tool_key, ", ".join(ontbreekt))
        return json.dumps(
            {
                "error": "LLM_TOOLCALL_ONGELDIG",
                "validatiefout": f"{tool_key} mist: {', '.join(ontbreekt)}",
            },
            ensure_ascii=False,
        )

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

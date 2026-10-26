"""Maakt log3-250000-engine.txt en fig3-log-250000-engine.png voor PDR-014.

Vier aanroepen van de informatieplicht-regel tegen de echte engine, zonder
taalmodel: getallen zoals de host ze normaliseert, de opgave zoals de
ondernemer hem typte ("250.000"), een bedrijf boven de elektriciteitsdrempel,
en datzelfde bedrijf met een tikfout (-65000). De txt is de log; de png is
diezelfde log gerenderd, voor in de PDR.

    uv run python docs/decisions/assets/pdr-014/maak-log3.py

Vereist netwerktoegang; geen API-keys. Voor de png is Pillow nodig (staat niet
in de projectomgeving; val dan terug op `python3` van het systeem, of maak een
terminal-screenshot van de txt).
"""

import datetime
import json
import os
from pathlib import Path

import httpx

URL = os.getenv("REGELRECHT_RPC_URL", "https://ui.lac.projects.digilab.network/mcp/rpc")
LAW = "omgevingswet/energiebesparing/informatieplicht"
HIER = Path(__file__).parent
TXT = HIER / "log3-250000-engine.txt"
PNG = HIER / "fig3-log-250000-engine.png"


def _zoek(node: dict, naam: str) -> dict | None:
    if node.get("name") == naam:
        return node
    for kind in node.get("children", []):
        gevonden = _zoek(kind, naam)
        if gevonden:
            return gevonden
    return None


def _aanroep(regels: list[str], label: str, parameters: dict) -> None:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "execute_law",
            "arguments": {"service": "RVO", "law": LAW, "parameters": parameters},
        },
    }
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    regels.append(f"{ts} >>> POST {URL}")
    regels.append(f"{ts}     execute_law service=RVO law={LAW}")
    regels.append(f"{ts}     {label}")
    regels.append(f"{ts}     parameters = {json.dumps(parameters, ensure_ascii=False)}")
    s = httpx.post(URL, json=body, timeout=30).json()["result"]["structuredContent"]
    plicht = s["output"].get("heeft_energiebesparingsplicht")
    regels.append(
        f"{ts} <<< requirements_met = {s['requirements_met']}   "
        f"heeft_energiebesparingsplicht = {plicht if plicht is not None else '(geen uitkomst)'}"
    )
    invoer = {k: v for k, v in s["input"].items() if "VERBRUIK" in k}
    regels.append(f"{ts}     input zoals de engine hem las = {json.dumps(invoer)}")
    op = _zoek(s["path"], "Operation: GREATER_OR_EQUAL")
    if op:
        d = op["details"]
        regels.append(
            f"{ts}     toets elektriciteit: {d['subject_value']} >= {d['comparison_value']} -> {op['result']}"
        )
    regels.append("")


def maak_log() -> list[str]:
    basis = {"KVK_NUMMER": "62345681", "IS_WOONFUNCTIE": False}
    regels: list[str] = []
    _aanroep(regels, "(1) getallen, zoals de host ze sinds 19 augustus normaliseert",
             {**basis, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 250000, "JAARLIJKS_GASVERBRUIK_M3": 90000})
    _aanroep(regels, "(2) de opgave zoals de ondernemer hem typte ('250.000'), ongewijzigd doorgegeven",
             {**basis, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": "250.000", "JAARLIJKS_GASVERBRUIK_M3": "90.000"})
    _aanroep(regels, "(3) bedrijf boven de elektriciteitsdrempel, onder de gasdrempel: 65000 kWh, 20000 m3",
             {**basis, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 65000, "JAARLIJKS_GASVERBRUIK_M3": 20000})
    _aanroep(regels, "(4) hetzelfde bedrijf met een tikfout: -65000, ongewijzigd doorgegeven",
             {**basis, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": -65000, "JAARLIJKS_GASVERBRUIK_M3": 20000})
    while regels and regels[-1] == "":
        regels.pop()
    TXT.write_text("\n".join(regels) + "\n")
    return regels


def render(regels: list[str]) -> None:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow ontbreekt; txt is geschreven, png niet.")
        return
    import glob

    fonts = glob.glob("/usr/share/fonts/**/DejaVuSansMono.ttf", recursive=True) or glob.glob(
        "/usr/share/fonts/**/*Mono*.ttf", recursive=True
    )
    font = ImageFont.truetype(fonts[0], 22) if fonts else ImageFont.load_default(size=22)
    pad, lh = 28, 30
    w = int(max(font.getlength(r) for r in regels) + 2 * pad)
    h = len(regels) * lh + 2 * pad
    img = Image.new("RGB", (w, h), (24, 26, 30))
    d = ImageDraw.Draw(img)
    for i, r in enumerate(regels):
        kleur = (220, 222, 226)
        if ">>>" in r:
            kleur = (140, 190, 255)
        if "requirements_met = False" in r or "-> False" in r:
            kleur = (255, 120, 110)
        if "requirements_met = True" in r:
            kleur = (140, 220, 150)
        d.text((pad, pad + i * lh), r, font=font, fill=kleur)
    img.save(PNG)
    print(f"{PNG.name}: {img.size}")


if __name__ == "__main__":
    regels = maak_log()
    print("\n".join(regels))
    render(regels)

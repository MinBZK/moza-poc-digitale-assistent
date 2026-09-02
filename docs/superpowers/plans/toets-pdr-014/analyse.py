"""Analyseert de run-JSONs van meet.py tegen de claims van PDR-014.

    python3 analyse.py <map met *-runN.json> [<map> ...]  > rapport-ruw.md

Per run en per label: toezeggingen in beurt 1 (vóór enige bron), de beurt
waarin de wet voor het eerst draait, de beurt waarin de ondernemer voor het
eerst een uitkomst leest, duur per beurt, extra rondes, en de controles van het
meetscript zelf.
"""

import json
import re
import statistics
import sys
from pathlib import Path

# Uitspraken over wat geldt, bedragen, termijnen en indiening — de vier
# soorten toezegging die PDR-014 benoemt.
TOEZEGGING = {
    "geldt/van toepassing": re.compile(r"\b(geldt|van toepassing|verplicht|moet u|bent u verplicht)\b", re.I),
    "waarschijnlijk/mogelijk": re.compile(r"\b(waarschijnlijk|vermoedelijk|mogelijk geldt|lijkt|zal gelden)\b", re.I),
    "bedrag": re.compile(r"€\s?\d|\d+\s?euro", re.I),
    "termijn/deadline": re.compile(r"\b(uiterlijk|deadline|vóór \d|voor \d{1,2} \w+ 20\d\d|\d{1,2} (januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december) 20\d\d|binnen \d+ (maanden|weken|dagen))\b", re.I),
    "ingediend/goedgekeurd": re.compile(r"\b(is ingediend|ingediend\b.*referentie|goedgekeurd|is verwerkt)\b", re.I),
}
UITKOMST = re.compile(r"energiebesparingsplicht.{0,60}\b(geldt|niet)\b|\b(geldt|geldt niet)\b.{0,40}energiebesparingsplicht|energiebesparingsplicht:\s*(ja|nee)\b|de toets is afgerond", re.I | re.S)
DATUM = re.compile(r"\b\d{1,2} (januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december) 20\d\d\b", re.I)


def toezeggingen(tekst: str) -> dict[str, list[str]]:
    gevonden = {}
    for naam, rx in TOEZEGGING.items():
        hits = []
        for m in rx.finditer(tekst):
            zin_start = tekst.rfind(".", 0, m.start()) + 1
            zin_eind = tekst.find(".", m.end())
            zin = tekst[zin_start: zin_eind if zin_eind > 0 else None].strip().replace("\n", " ")
            hits.append(zin[:160])
        if hits:
            gevonden[naam] = hits
    return gevonden


def analyseer_run(run: dict) -> dict:
    b = run["beurten"]
    eerste_wet = next((x["nr"] for x in b if "regelrecht__execute_law" in x["tools"]), None)
    eerste_bron = next((x["nr"] for x in b if x["tools"]), None)
    eerste_uitkomst = next((x["nr"] for x in b if UITKOMST.search(x["antwoord"])), None)
    beurt1 = b[0] if b else {"antwoord": "", "tools": [], "seconden": None}
    t1 = toezeggingen(beurt1["antwoord"])
    # Uitspraken vóór de eerste bron: alle beurten tot (niet t/m) de eerste bron-beurt
    voor_bron = [x for x in b if eerste_bron is None or x["nr"] < eerste_bron]
    toez_voor_bron = {x["nr"]: toezeggingen(x["antwoord"]) for x in voor_bron}
    toez_voor_bron = {k: v for k, v in toez_voor_bron.items() if v}
    # Indienen-toezegging: 'ingediend' in een beurt zonder rvo__indienen
    ingediend_zonder = [x["nr"] for x in b if "rvo__indienen" not in x["tools"]
                        and re.search(r"\bis ingediend\b|ingediend\b.{0,40}referentie", x["antwoord"], re.I)]
    datums = sorted({m.group(0) for x in b for m in DATUM.finditer(x["antwoord"])})
    extra_rondes = {
        "rvo__zoek_regeling": sum(x["tools"].count("rvo__zoek_regeling") for x in b),
        "regelrecht__execute_law": sum(x["tools"].count("regelrecht__execute_law") for x in b),
    }
    bron_fouten = [f"{x['nr']}:{e.get('code')}({e.get('bron','')})" for x in b for e in x["events"] if e.get("type") in ("bron_fout", "error")]
    herhaalde_vraag = None
    for i in range(1, len(b)):
        vorige, deze = b[i - 1]["antwoord"], b[i]["antwoord"]
        if vorige and deze and vorige.strip()[:200] == deze.strip()[:200]:
            herhaalde_vraag = b[i]["nr"]
    return {
        "label": run["label"], "run": run["run"], "afgebroken": run.get("afgebroken"),
        "beurten": len(b), "totaal_s": run.get("totaal_seconden"),
        "seconden": [x["seconden"] for x in b],
        "tools_per_beurt": [x["tools"] for x in b],
        "eerste_bron_beurt": eerste_bron, "eerste_wet_beurt": eerste_wet,
        "eerste_uitkomst_beurt": eerste_uitkomst,
        "beurt1_tools": beurt1["tools"], "beurt1_s": beurt1["seconden"],
        "beurt1_toezeggingen": t1,
        "toezeggingen_voor_eerste_bron": toez_voor_bron,
        "ingediend_zonder_indienen": ingediend_zonder,
        "genoemde_datums": datums,
        "extra_rondes": extra_rondes,
        "bron_fouten": bron_fouten,
        "herhaald_antwoord_in_beurt": herhaalde_vraag,
        "controles_fout": [c["reden"] for c in run["controles"] if not c["ok"]],
        "controles_totaal": len(run["controles"]),
        "beurt1_antwoord": beurt1["antwoord"],
    }


def main(mappen: list[str]) -> None:
    runs = []
    for m in mappen:
        for f in sorted(Path(m).glob("*-run*.json")):
            runs.append(analyseer_run(json.loads(f.read_text())))
    print("# Ruwe analyse per run\n")
    for label in sorted({r["label"] for r in runs}):
        sel = [r for r in runs if r["label"] == label]
        print(f"## {label} ({len(sel)} runs)\n")
        print("| run | beurten | totaal s | s per beurt | 1e bron | 1e wet | 1e uitkomst | toezegging vóór bron | 'ingediend' zonder indienen | datums | zoek_regeling | execute_law | bron_fouten | controles fout |")
        print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sel:
            tz = "; ".join(f"b{k}: {', '.join(v.keys())}" for k, v in r["toezeggingen_voor_eerste_bron"].items()) or "geen"
            print(f"| {r['run']} | {r['beurten']} | {r['totaal_s']} | {r['seconden']} | {r['eerste_bron_beurt']} | {r['eerste_wet_beurt']} | {r['eerste_uitkomst_beurt']} | {tz} | {r['ingediend_zonder_indienen'] or '-'} | {', '.join(r['genoemde_datums']) or '-'} | {r['extra_rondes']['rvo__zoek_regeling']} | {r['extra_rondes']['regelrecht__execute_law']} | {', '.join(r['bron_fouten']) or '-'} | {len(r['controles_fout'])}/{r['controles_totaal']} |")
        print()
        alle_s = [s for r in sel for s in r["seconden"] if s]
        if alle_s:
            print(f"Duur per beurt over alle runs: mediaan {statistics.median(alle_s):.1f} s, max {max(alle_s):.1f} s, som per run mediaan {statistics.median([r['totaal_s'] for r in sel if r['totaal_s']]):.0f} s\n")
        print("### Beurt 1 per run (wat de ondernemer leest vóór enige bron)\n")
        for r in sel:
            print(f"**run {r['run']}** ({r['beurt1_s']} s, tools: {r['beurt1_tools'] or 'geen'}) — toezeggingen: {', '.join(r['beurt1_toezeggingen'].keys()) or 'geen'}\n")
            print("> " + r["beurt1_antwoord"].replace("\n", "\n> ")[:1200] + "\n")
            for soort, zinnen in r["beurt1_toezeggingen"].items():
                for z in zinnen[:3]:
                    print(f"- [{soort}] {z}")
            print()
        print("### Tools per beurt\n")
        for r in sel:
            print(f"- run {r['run']}: " + " → ".join(f"b{i+1}[{', '.join(t) or '-'}]" for i, t in enumerate(r["tools_per_beurt"])))
        print()
        print("### Gefaalde controles van het meetscript\n")
        for r in sel:
            print(f"- run {r['run']}: {'; '.join(r['controles_fout']) or 'geen'}")
        print()


if __name__ == "__main__":
    main(sys.argv[1:])

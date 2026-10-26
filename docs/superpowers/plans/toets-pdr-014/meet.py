"""Draait onderzoeksflow.draai() N keer en bewaart per run alles wat de analyse
nodig heeft: per beurt de vraag, de duur, de tools, de events en het antwoord,
plus de uitkomsten van de controles van het script zelf.

    uv run python meet.py --script <pad naar onderzoeksflow.py> --host http://127.0.0.1:8000 \
        --mode claude --runs 5 --label main --out <map>
"""

import argparse
import dataclasses
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import httpx


def laad(script: str):
    pad = Path(script).resolve()
    sys.path.insert(0, str(pad.parent))          # taalniveau e.d. naast het script
    sys.path.insert(0, str(pad.parent.parent))   # host-modules
    spec = importlib.util.spec_from_file_location("onderzoeksflow", pad)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["onderzoeksflow"] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--script", required=True)
    p.add_argument("--host", default="http://127.0.0.1:8000")
    p.add_argument("--mode", default="claude")
    p.add_argument("--kvk", default="62345681")
    p.add_argument("--runs", type=int, default=5)
    p.add_argument("--label", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()

    of = laad(a.script)
    uit = Path(a.out)
    uit.mkdir(parents=True, exist_ok=True)
    sleutel = os.getenv("ANTHROPIC_API_KEY" if "claude" in a.mode else "VLAM_API_KEY", "")
    persona = of.PERSONAS[a.kvk]

    origineel = of.Loop.beurt

    def geklokt(self, bericht, **kw):
        t0 = time.perf_counter()
        try:
            antwoord, tools, events = origineel(self, bericht, **kw)
        finally:
            duur = time.perf_counter() - t0
        self.tijden.append({"vraag": bericht, "seconden": round(duur, 1), "tools": tools,
                            "kw": {k: v for k, v in kw.items() if v is not None}})
        return antwoord, tools, events

    of.Loop.beurt = geklokt

    for nummer in range(1, a.runs + 1):
        print(f"\n{'#' * 70}\n# {a.label} RUN {nummer} van {a.runs}\n{'#' * 70}", flush=True)
        velden = {f.name for f in dataclasses.fields(of.Loop)}
        extra = {"api_key": sleutel} if "api_key" in velden else {}
        loop = of.Loop(host=a.host, kvk=a.kvk, mode=a.mode, **extra)
        loop.tijden = []
        start = time.time()
        fout = None
        try:
            of.draai(loop, persona)
        except httpx.HTTPError as e:
            fout = f"{type(e).__name__}: {e}"
            print(f"RUN {nummer} AFGEBROKEN: {fout}")
        beurten = []
        for i, t in enumerate(loop.transcript):
            tijd = loop.tijden[i] if i < len(loop.tijden) else {}
            antwoord = next((e.get("message", "") for e in t["events"] if e.get("type") == "answer"), "")
            beurten.append({
                "nr": i + 1,
                "vraag": t["vraag"],
                "seconden": tijd.get("seconden"),
                "tools": tijd.get("tools", []),
                "meegegeven": tijd.get("kw", {}),
                "events": t["events"],
                "antwoord": antwoord,
            })
        (uit / f"{a.label}-run{nummer}.json").write_text(json.dumps({
            "label": a.label, "run": nummer, "mode": a.mode, "kvk": a.kvk,
            "gestart": start, "totaal_seconden": round(time.time() - start, 1),
            "afgebroken": fout,
            "controles": [{"stap": u.stap, "ok": u.ok, "reden": u.reden, "detail": u.detail}
                          for u in loop.uitkomsten],
            "beurten": beurten,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"run {nummer} klaar in {round(time.time() - start)} s, {len(beurten)} beurten", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

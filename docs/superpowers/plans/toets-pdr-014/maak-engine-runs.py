"""Maakt engine-runs.json: zes invoercases, elk tien keer, tegen de echte engine.

Meet of de engine deterministisch is (identieke uitkomst per case) en hoe lang
een aanroep duurt. Geen taalmodel, geen sleutel; wel netwerk.

    uv run python docs/superpowers/plans/toets-pdr-014/maak-engine-runs.py
"""

import json
import os
import statistics
import time
from pathlib import Path

import httpx

URL = os.getenv("REGELRECHT_RPC_URL", "https://ui.lac.projects.digilab.network/mcp/rpc")
LAW = "omgevingswet/energiebesparing/informatieplicht"
RUNS = 10
UIT = Path(__file__).parent / "engine-runs.json"

BASIS = {"KVK_NUMMER": "62345681", "IS_WOONFUNCTIE": False}
CASES = {
    "E1 genormaliseerd 250000/90000": {
        **BASIS, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 250000, "JAARLIJKS_GASVERBRUIK_M3": 90000
    },
    "E2 string '250.000'/'90.000'": {
        **BASIS, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": "250.000", "JAARLIJKS_GASVERBRUIK_M3": "90.000"
    },
    "E3 65000/20000": {
        **BASIS, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": 65000, "JAARLIJKS_GASVERBRUIK_M3": 20000
    },
    "E4 tikfout -65000/20000": {
        **BASIS, "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": -65000, "JAARLIJKS_GASVERBRUIK_M3": 20000
    },
    "E5 leeg {}": {},
    "E6 alleen KVK+woonfunctie": BASIS,
}


def aanroep(parameters: dict) -> tuple[dict, float]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "execute_law",
            "arguments": {"service": "RVO", "law": LAW, "parameters": parameters},
        },
    }
    t0 = time.perf_counter()
    s = httpx.post(URL, json=body, timeout=30).json()["result"]["structuredContent"]
    return s, time.perf_counter() - t0


def main() -> None:
    uit = {}
    for naam, parameters in CASES.items():
        uitkomsten, duren = [], []
        for _ in range(RUNS):
            s, duur = aanroep(parameters)
            duren.append(duur)
            uitkomsten.append(json.dumps({
                "requirements_met": s["requirements_met"],
                "plicht": s["output"].get("heeft_energiebesparingsplicht"),
                "missing": s.get("missing_parameters"),
                "input": {k: v for k, v in s["input"].items() if "VERBRUIK" in k},
            }, sort_keys=True))
        uit[naam] = {
            "runs": RUNS,
            "identiek": len(set(uitkomsten)) == 1,
            "uitkomst": json.loads(uitkomsten[0]),
            "ms_mediaan": round(statistics.median(duren) * 1000),
            "ms_max": round(max(duren) * 1000),
        }
        print(naam, "| identiek:", uit[naam]["identiek"], "| ms mediaan/max",
              uit[naam]["ms_mediaan"], uit[naam]["ms_max"])
    UIT.write_text(json.dumps(uit, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()

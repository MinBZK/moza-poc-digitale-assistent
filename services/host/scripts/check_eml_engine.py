"""Handmatige integratiecheck: EML-maatregelen via de echte engine.

Draait de twee-staps-flow tegen REGELRECHT_RPC_URL (default: digilab).
Vereist netwerktoegang; geen API-keys nodig.

    uv run python services/host/scripts/check_eml_engine.py
"""

import asyncio
import json
import os

import httpx

RPC_URL = os.getenv(
    "REGELRECHT_RPC_URL",
    "https://ui.lac.apps.digilab.network/mcp/rpc",
)
LAW = "omgevingswet/energiebesparing/maatregelen"


async def _execute_law(client: httpx.AsyncClient, parameters: dict) -> dict:
    response = await client.post(
        RPC_URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "execute_law",
                "arguments": {
                    "service": "RVO",
                    "law": LAW,
                    "parameters": parameters,
                },
            },
        },
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise SystemExit(f"RPC-fout: {data['error']}")
    return data["result"].get("structuredContent", {})


async def main() -> None:
    async with httpx.AsyncClient() as client:
        # Stap 1: zonder feiten — engine moet melden wat er ontbreekt
        stap1 = await _execute_law(client, {})
        print("— Stap 1 (zonder feiten) —")
        print("missing_required:", stap1.get("missing_required"))
        params = (
            stap1.get("rule_spec", {}).get("properties", {}).get("parameters", [])
        )
        for p in params:
            print(f"  vraag: {p.get('name')}: {p.get('description')}")
        assert stap1.get("missing_required") is True, "verwacht: feiten ontbreken"

        # Stap 2: met feiten (Noon: koeling én afzuiging)
        stap2 = await _execute_law(
            client,
            {"HEEFT_KOELINSTALLATIE": True, "HEEFT_AFZUIGINSTALLATIE": True},
        )
        print("— Stap 2 (met feiten) —")
        outputs = stap2.get("output", {})
        print(json.dumps(outputs, indent=2, ensure_ascii=False))
        eml = {k: v for k, v in outputs.items() if k.startswith("eml_")}
        assert len(eml) == 7, f"verwacht 7 maatregelen, kreeg {len(eml)}"
        assert all(eml.values()), "Noon (koeling+afzuiging): alles van toepassing"
        print("OK — engine bepaalt de EML-maatregelen")


if __name__ == "__main__":
    asyncio.run(main())

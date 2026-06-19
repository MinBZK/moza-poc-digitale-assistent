"""rvo__indienen verrijkt de lopende_zaak voor de frontend.

De frontend leest het case-event en toont organisatie/onderwerp/referentienummer.
Die moeten in de lopende_zaak zitten zodat de frontend niets hoeft te verzinnen.
Na indienen claimt de respons geen directe goedkeuring (zie PDR-008-context).
"""

import importlib.util
import json
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent.parent / "mcp"


def _indien() -> dict:
    """Roep de rvo-indienen-handler aan en geef de geparste data terug."""
    pad = MCP_DIR / "rvo" / "server.py"
    spec = importlib.util.spec_from_file_location("mcp_rvo_server", pad)
    rvo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rvo)
    res = rvo._indienen(
        {
            "kvk_nummer": "85234567",
            "regeling_id": "EBR-2026",
            "maatregelen": ["GF4: uitgevoerd"],
            "bedrijfskenmerken": {"HEEFT_KOELINSTALLATIE": True},
        }
    )
    return json.loads(res[0].text)["data"]


def test_lopende_zaak_heeft_organisatie_onderwerp_referentie():
    zaak = _indien()["lopende_zaak"]
    assert zaak["organisatie"] == "Rijksdienst voor Ondernemend Nederland"
    assert zaak["onderwerp"] == "Informatieplicht energiebesparing"
    # referentienummer = stabiele sleutel voor idempotentie in de frontend
    assert zaak["referentienummer"] == "RVO-EBR-2026-85234567-001"
    assert zaak["status"] == "In behandeling"
    assert zaak["ingediend_op"]


def test_indienen_claimt_geen_directe_goedkeuring():
    data = _indien()
    # Geen geautomatiseerde-toets-AKKOORD-veld meer
    assert "toets" not in data
    blob = json.dumps(data, ensure_ascii=False).lower()
    assert "goedgekeurd" not in blob
    # De bevestiging verwijst naar 'in behandeling', niet naar goedkeuring
    assert "in behandeling" in data["bevestiging"].lower()

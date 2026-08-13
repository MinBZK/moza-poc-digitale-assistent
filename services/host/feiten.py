"""Canonieke feiten uit tool-resultaten, als bron voor slot-substitutie.

Het model schrijft `{{VESTIGINGSADRES}}`; de host vult in wat hier uit komt. Een
feit dat deze module niet oplevert, kan het model dus niet noemen - en dat is de
bedoeling: liever "die gegevens heb ik niet" dan een verzonnen adres in een
rapport dat namens de ondernemer naar RVO gaat.

Waarom hier en niet in de MCP-servers: die leveren de vorm van hun eigen bron.
De vertaling naar slotnamen is een keuze van de host, en één plek waar die keuze
staat is beter dan vijf servers die hem elk half maken.
"""

import json
import logging

logger = logging.getLogger("vlam.feiten")


def _bezoekadres(vestiging: dict) -> str | None:
    """Het bezoekadres, gekozen op type en niet op positie.

    De KvK-API zet het correspondentieadres eerst. Bij een postbus als postadres
    zou positie-kiezen het verkeerde adres opleveren - en dat is precies het
    adres dat de respondent op zijn scherm niet ziet staan.
    """
    for adres in vestiging.get("adressen") or []:
        if adres.get("type") == "bezoekadres":
            return adres.get("volledigAdres")
    return None


def _uit_kvk(data: dict) -> dict:
    vestiging = (data.get("_embedded") or {}).get("hoofdvestiging") or {}
    feiten = {
        "BEDRIJFSNAAM": data.get("naam"),
        "KVK_NUMMER": data.get("kvkNummer"),
        "RECHTSVORM": data.get("rechtsvorm"),
        "VESTIGINGSNUMMER": vestiging.get("vestigingsnummer"),
        "VESTIGINGSADRES": _bezoekadres(vestiging),
        "WOONFUNCTIE": (data.get("bag") or {}).get("is_woonfunctie"),
        "GEBRUIKSDOEL": (data.get("bag") or {}).get("gebruiksdoel"),
    }
    return {k: v for k, v in feiten.items() if v is not None}


def _uit_netbeheerder(data: dict) -> dict:
    totaal = data.get("totaal") or {}
    feiten = {
        "ELEKTRICITEIT_KWH": totaal.get("jaarlijks_elektriciteitsverbruik_kwh"),
        "GAS_M3": totaal.get("jaarlijks_gasverbruik_m3"),
        "PEILJAAR": data.get("peiljaar"),
        "NETBEHEERDER": data.get("netbeheerder"),
    }
    return {k: v for k, v in feiten.items() if v is not None}


# De uitkomsten van RegelRecht die als slot beschikbaar komen.
_OORDELEN = {
    "heeft_energiebesparingsplicht": "OORDEEL_ENERGIEBESPARINGSPLICHT",
    "heeft_informatieplicht": "OORDEEL_INFORMATIEPLICHT",
    "heeft_onderzoeksplicht": "OORDEEL_ONDERZOEKSPLICHT",
}

_UITKOMST_VELDEN = {
    "volgende_rapportage_deadline": "VOLGENDE_DEADLINE",
    "rapportage_frequentie_jaren": "RAPPORTAGE_FREQUENTIE_JAREN",
    "rapportage_methode": "RAPPORTAGE_METHODE",
    "bevoegd_gezag": "BEVOEGD_GEZAG",
}


def _uit_regelrecht(data: dict) -> dict:
    feiten: dict[str, object] = {}
    feiten.update(data.get("drempelwaarden") or {})
    feiten.update(data.get("gebruikte_waarden") or {})
    uitkomsten = data.get("uitkomsten") or {}
    for bron, slot in _OORDELEN.items():
        if bron in uitkomsten:
            feiten[slot] = uitkomsten[bron]
    for bron, slot in _UITKOMST_VELDEN.items():
        if uitkomsten.get(bron) is not None:
            feiten[slot] = uitkomsten[bron]
    return feiten


def _uit_rvo(data: dict) -> dict:
    zaak = data.get("lopende_zaak") or {}
    nummer = zaak.get("referentienummer")
    return {"REFERENTIENUMMER": nummer} if nummer else {}


_OOGSTERS = {
    "kvk__mijn_bedrijf": _uit_kvk,
    "netbeheerder__verbruik": _uit_netbeheerder,
    "regelrecht__execute_law": _uit_regelrecht,
    "rvo__indienen": _uit_rvo,
}


def feiten_uit_tool(tool_naam: str, resultaat: str) -> dict[str, object]:
    """Feiten uit één tool-resultaat, met slotnamen als sleutel.

    Een onbekende tool of onleesbaar resultaat levert een leeg dict op: een bron
    die rommel teruggeeft mag het gesprek niet laten klappen.
    """
    oogster = _OOGSTERS.get(tool_naam)
    if oogster is None:
        return {}
    try:
        data = json.loads(resultaat).get("data") or {}
    except (ValueError, AttributeError):
        logger.warning("Tool-resultaat van %s is geen leesbare JSON", tool_naam)
        return {}
    if not isinstance(data, dict):
        return {}
    return oogster(data)

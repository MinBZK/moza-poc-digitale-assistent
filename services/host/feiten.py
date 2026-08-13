"""Canonieke feiten uit tool-resultaten, als bron voor slot-substitutie.

Het model schrijft `{{VESTIGINGSADRES}}`; de host vult in wat hier uit komt. Een
feit dat deze module niet oplevert, kan het model dus niet noemen - en dat is de
bedoeling: liever "die gegevens heb ik niet" dan een verzonnen adres in een
rapport dat namens de ondernemer naar RVO gaat.

Waarom hier en niet in de MCP-servers: die leveren de vorm van hun eigen bron.
De vertaling naar slotnamen is een keuze van de host, en één plek waar die keuze
staat is beter dan vijf servers die hem elk half maken.

Elk feit draagt zijn herkomst (`waarde`, `bron`, `soort`) in plaats van alleen
zijn waarde: een tweede dict ernaast met dezelfde sleutels kan uit de pas lopen
met wat er werkelijk opgehaald is, en dat is precies hoe de provenance uit de
MCP-envelope eerder verdween.
"""

import json
import logging

import regelrouting

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


def _gebruiksdoel(bag: dict) -> str | None:
    """Het gebruiksdoel als leesbare tekst.

    De BAG geeft `gebruiksdoelen` als lijst - een pand kan er meerdere hebben
    (bv. kantoor- én industriefunctie). Een Python-lijstrepresentatie hoort niet
    in een rapporttekst voor de ondernemer, dus komma-gescheiden platgeslagen.
    """
    doelen = bag.get("gebruiksdoelen") or []
    return ", ".join(doelen) if doelen else None


def _met_herkomst(waarden: dict, bron: str, soort: str) -> dict:
    """Verpak platte waarden tot feiten met hun herkomst.

    None-waarden vallen weg: een feit zonder waarde is geen feit, en een lege
    plek is eerlijker dan een verzonnen invulling.
    """
    return {
        naam: {"waarde": waarde, "bron": bron, "soort": soort}
        for naam, waarde in waarden.items()
        if waarde is not None
    }


def _uit_kvk(data: dict) -> dict:
    vestiging = (data.get("_embedded") or {}).get("hoofdvestiging") or {}
    # `is_woonfunctie` zet de KvK-server naast `bag`, niet erin (server.py).
    feiten = {
        "BEDRIJFSNAAM": data.get("naam"),
        "KVK_NUMMER": data.get("kvkNummer"),
        "RECHTSVORM": data.get("rechtsvorm"),
        "VESTIGINGSNUMMER": vestiging.get("vestigingsnummer"),
        "VESTIGINGSADRES": _bezoekadres(vestiging),
        "WOONFUNCTIE": data.get("is_woonfunctie"),
        "GEBRUIKSDOEL": _gebruiksdoel(data.get("bag") or {}),
    }
    return _met_herkomst(feiten, "KvK Handelsregister", "registratie")


def _uit_netbeheerder(data: dict) -> dict:
    """Feiten uit de Business Wallet-credential (server.py: PDR-008).

    Zonder attestatie (`beschikbaar: False`) heeft de respons geen `verbruik`/
    `credential` - expliciet niets opleveren in plaats van op toeval te
    vertrouwen dat die sleutels dan wel ontbreken.
    """
    if not data.get("beschikbaar"):
        return {}
    totaal = (data.get("verbruik") or {}).get("totaal") or {}
    credential = data.get("credential") or {}
    feiten = {
        "ELEKTRICITEIT_KWH": totaal.get("jaarlijks_elektriciteitsverbruik_kwh"),
        "GAS_M3": totaal.get("jaarlijks_gasverbruik_m3"),
        "PEILJAAR": credential.get("peiljaar"),
        "NETBEHEERDER": credential.get("uitgegeven_door"),
    }
    return _met_herkomst(feiten, "Business Wallet", "attestatie")


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


def _herkomst_gebruikte_waarden(waarden: dict) -> dict:
    """Herkomst voor `gebruikte_waarden`: een echo, nooit een eigen waarneming.

    RegelRecht geeft hier terug wat WIJ als invoer instuurden — dat kan een
    feit uit de feitenkaart zijn dat de host er zelf in zette, maar net zo
    goed een override die het model verzon. Die twee zijn hier niet te
    onderscheiden, dus krijgt geen enkele waarde hier de soort van de
    oorspronkelijke bron (`attestatie`/`registratie`/`opgave`): dat zou een
    modelgestuurde override laten doorgaan voor een bevestigde attestatie.
    `echo` maakt expliciet dat dit alleen is wat wij instuurden.
    """
    feiten: dict[str, dict] = {}
    for naam, waarde in waarden.items():
        if waarde is None:
            continue
        veld = regelrouting.route(naam)
        sleutel = veld.feitnaam if veld and veld.feitnaam else naam
        feiten[sleutel] = {
            "waarde": waarde,
            "bron": "RegelRecht (doorgegeven invoer)",
            "soort": "echo",
        }
    return feiten


def _uit_regelrecht(data: dict) -> dict:
    feiten: dict[str, dict] = {}
    feiten.update(_met_herkomst(data.get("drempelwaarden") or {}, "RegelRecht", "wetsconstante"))
    feiten.update(_herkomst_gebruikte_waarden(data.get("gebruikte_waarden") or {}))
    uitkomsten = data.get("uitkomsten") or {}
    oordelen = {slot: uitkomsten[naam] for naam, slot in _OORDELEN.items() if naam in uitkomsten}
    uitkomstvelden = {
        slot: uitkomsten[naam]
        for naam, slot in _UITKOMST_VELDEN.items()
        if uitkomsten.get(naam) is not None
    }
    feiten.update(_met_herkomst(oordelen, "RegelRecht", "wetsconstante"))
    feiten.update(_met_herkomst(uitkomstvelden, "RegelRecht", "wetsconstante"))
    return feiten


def _uit_rvo(data: dict) -> dict:
    zaak = data.get("lopende_zaak") or {}
    nummer = zaak.get("referentienummer")
    return _met_herkomst({"REFERENTIENUMMER": nummer}, "RVO", "registratie")


_OOGSTERS = {
    "kvk__mijn_bedrijf": _uit_kvk,
    "netbeheerder__verbruik": _uit_netbeheerder,
    "regelrecht__execute_law": _uit_regelrecht,
    "rvo__indienen": _uit_rvo,
}


def feiten_uit_tool(tool_naam: str, resultaat: str) -> dict[str, dict]:
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

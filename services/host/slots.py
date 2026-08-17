"""Slots invullen uit de feitenkaart.

Het model schrijft `{{VESTIGINGSADRES}}`; deze module vult in wat de bron zei.
Wat hier niet ingevuld kan worden, blijft staan en wordt gemeld - de aanroeper
houdt het antwoord dan tegen. Een `{{…}}` op het scherm van een respondent is
even besmettend voor het onderzoek als een verkeerd feit.
"""

import re
from datetime import date

_SLOT = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

_MAANDEN = (
    "januari", "februari", "maart", "april", "mei", "juni",
    "juli", "augustus", "september", "oktober", "november", "december",
)

# Slots waarvan de waarde een oordeel is: die lezen als "geldt wel" / "geldt
# niet" en niet als ja/nee, omdat ze middenin een zin staan.
_OORDEELSLOTS = frozenset(
    {
        "OORDEEL_ENERGIEBESPARINGSPLICHT",
        "OORDEEL_INFORMATIEPLICHT",
        "OORDEEL_ONDERZOEKSPLICHT",
    }
)

# Slots die een jaartal(-achtige waarde) dragen, geen bedrag: een duizendtal-
# scheider maakt "2025" tot het onleesbare "2.025". Vast opgesomd i.p.v. een
# drempel op de waarde (bv. "< 10.000"): een jaartal test toevallig onder elke
# zinnige drempel, dus alleen de slotnaam is een betrouwbaar signaal.
# PEILJAAR is een kalenderjaar. RAPPORTAGE_FREQUENTIE_JAREN drukt een aantal
# jaren uit ("eens per 4 jaar") en blijft altijd klein - maar is qua soort
# hetzelfde als een jaartal en geen hoeveelheid, dus hoort hij in dezelfde lijst
# in plaats van toevallig goed te gaan omdat hij nooit de duizend haalt.
_GEEN_DUIZENDTAL = frozenset({"PEILJAAR", "RAPPORTAGE_FREQUENTIE_JAREN"})


def _als_datum(waarde: str) -> str | None:
    """ISO-datum met streepjes naar '1 december 2027'. Anders None.

    `date.fromisoformat` valideert echt: een niet-bestaande dag (30 februari),
    een niet-ISO volgorde (dag-maand-jaar) of een willekeurige string geven
    allemaal een `ValueError` in plaats van een verzonnen datum.

    Het ISO-basisformaat zonder streepjes (`20271201`) wordt bewust niet
    herkend, ook al accepteert Python het sinds 3.11. Anders leest een
    achtcijferig KvK-nummer waarvan de middelste cijfers toevallig een geldige
    maand en dag vormen als datum: 67890123 werd "23 januari 6789". De bronnen
    in dit systeem leveren datums altijd mét streepjes, dus er gaat niets
    verloren.
    """
    if waarde.count("-") != 2:
        return None
    try:
        d = date.fromisoformat(waarde)
    except ValueError:
        return None
    return f"{d.day} {_MAANDEN[d.month - 1]} {d.year}"


def _weergave(naam: str, waarde: object) -> str:
    """Eén waarde, zoals de respondent hem hoort te lezen.

    De opmaak hoort hier en niet bij het model: anders schrijft het de ene keer
    420000 en de andere keer 420.000, en dat verschil valt op het scherm op.
    """
    if isinstance(waarde, bool):
        if naam in _OORDEELSLOTS:
            return "wel" if waarde else "niet"
        return "ja" if waarde else "nee"
    if isinstance(waarde, int):
        if naam in _GEEN_DUIZENDTAL:
            return str(waarde)
        return f"{waarde:,}".replace(",", ".")
    if isinstance(waarde, float):
        return f"{waarde:,.2f}".replace(",", "~").replace(".", ",").replace("~", ".")
    tekst = str(waarde)
    return _als_datum(tekst) or tekst


def vul_slots(tekst: str, feiten: dict) -> tuple[str, list[str]]:
    """Vul `{{SLOT}}` in uit `feiten`.

    Geeft de ingevulde tekst terug plus de slots die niet opgelost konden worden.
    Die blijven letterlijk staan: stil weglaten levert een halve zin op waarvan
    niemand merkt dat er een feit uit verdwenen is.
    """
    ontbrekend: list[str] = []

    def vervang(match: re.Match) -> str:
        naam = match.group(1)
        if naam not in feiten:
            ontbrekend.append(naam)
            return match.group(0)
        waarde = feiten[naam]["waarde"]
        # De feitenkaart draagt ook waarden die geen zin in kunnen: de
        # categorieen uit de wet, de maatregelenlijst. Die horen gemeld te
        # worden, niet als Python-repr op het scherm van een respondent.
        if isinstance(waarde, list | dict | tuple | set):
            ontbrekend.append(naam)
            return match.group(0)
        return _weergave(naam, waarde)

    return _SLOT.sub(vervang, tekst or ""), ontbrekend

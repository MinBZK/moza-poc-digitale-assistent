"""Slots invullen uit de feitenkaart.

Het model schrijft `{{VESTIGINGSADRES}}`; deze module vult in wat de bron zei.
Wat hier niet ingevuld kan worden, blijft staan en wordt gemeld - de aanroeper
houdt het antwoord dan tegen. Een `{{…}}` op het scherm van een respondent is
even besmettend voor het onderzoek als een verkeerd feit.
"""

import re

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


def _als_datum(waarde: str) -> str | None:
    """ISO-datum naar '1 december 2027'. Geen datum? Dan None."""
    delen = waarde.split("-")
    if len(delen) != 3:
        return None
    try:
        jaar, maand, dag = (int(d) for d in delen)
        return f"{dag} {_MAANDEN[maand - 1]} {jaar}"
    except (ValueError, IndexError):
        return None


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
        return _weergave(naam, feiten[naam])

    return _SLOT.sub(vervang, tekst or ""), ontbrekend

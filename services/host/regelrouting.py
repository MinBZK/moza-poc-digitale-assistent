"""Welk veld van de regel uit welke bron komt.

De engine declareert wat hij mist; deze tabel zegt wie dat levert. Herkomst
wordt daardoor niet als metadata meegedragen maar afgeleid uit wie geraadpleegd
is - dat kan niet uit de pas lopen met de waarde.

Staat een veld hier niet, dan stopt de orkestratielus en meldt dat. Raden waar
een gegeven vandaan komt is precies wat dit ontwerp onmogelijk maakt.

Nu één wet. De tabel staat als aparte eenheid zodat een tweede wet hier landt en
niet door de host heen verspreid raakt.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Veld:
    """Waar één parameter van de regel vandaan komt.

    `tool` is None als geen enkele bron het kan leveren: dan weet alleen de
    ondernemer het en hoort het uit het formulier te komen.

    `feitnaam` is de naam waaronder dit gegeven in de feitenkaart staat, of None
    als die gelijk is aan de regelnaam. Dit voorkomt dat de RegelRecht-naamgeving
    en de feitenkaart-naamgeving uit de pas lopen.
    """

    bron: str
    soort: str  # identiteit | registratie | attestatie | opgave
    tool: str | None
    toestemming: bool
    feitnaam: str | None = None


HERKOMST: dict[str, Veld] = {
    "KVK_NUMMER": Veld("sessie", "identiteit", None, False),
    "IS_WOONFUNCTIE": Veld(
        "KvK Handelsregister", "registratie", "kvk__mijn_bedrijf", False,
        feitnaam="WOONFUNCTIE"
    ),
    "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": Veld(
        "Business Wallet", "attestatie", "netbeheerder__verbruik", True,
        feitnaam="ELEKTRICITEIT_KWH"
    ),
    "JAARLIJKS_GASVERBRUIK_M3": Veld(
        "Business Wallet", "attestatie", "netbeheerder__verbruik", True,
        feitnaam="GAS_M3"
    ),
    "HEEFT_KOELINSTALLATIE": Veld("de ondernemer", "opgave", None, False),
    "HEEFT_AFZUIGINSTALLATIE": Veld("de ondernemer", "opgave", None, False),
}


def route(veldnaam: str) -> Veld | None:
    """De bron van één veld, of None als we hem niet kennen."""
    return HERKOMST.get(veldnaam)

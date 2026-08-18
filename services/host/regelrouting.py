"""Welk veld van de regel uit welke bron komt.

De engine declareert wat hij mist; deze tabel zegt wie dat levert. Herkomst
wordt daardoor niet als metadata meegedragen maar afgeleid uit wie geraadpleegd
is - dat kan niet uit de pas lopen met de waarde.

Staat een veld hier niet, dan stopt de orkestratielus en meldt dat. Raden waar
een gegeven vandaan komt is precies wat dit ontwerp onmogelijk maakt.

Twee wetten delen deze tabel: de informatieplicht en de maatregelbepaling. Ze
overlappen in het KvK-nummer, en de velden die alleen de tweede vraagt staan er
gewoon naast - de tabel is per veld, niet per wet, zodat een derde wet die
opnieuw naar het verbruik vraagt hier niets hoeft toe te voegen.
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

    `corrigeerbaar` staat toe dat de ondernemer een waarde uit een registratie
    overschrijft. Dat is niet de regel maar de uitzondering: het geldt alleen waar
    wij een juridisch begrip uit een registratie áfleiden dat die registratie zelf
    niet kent - "telen in kassen" uit een SBI-omschrijving. De correctie komt
    binnen als opgave, met de ondernemer als bron, en `feiten.samenvoegen` laat
    hem daarna niet meer overschrijven door een volgende ophaling.

    `zelf_op_te_geven` staat toe dat de ondernemer een waarde aanlevert die
    normaal uit een bron komt. Dat is iets anders dan `corrigeerbaar`: daar
    weerspreekt hij een afleiding van ons, hier vervangt hij een bron die hij
    niet wil of kan raadplegen. Weigert hij de Business Wallet, dan is zijn
    eigen opgave de enige weg naar een uitkomst - zonder deze uitweg loopt de
    keten dood en komt hij niet tot een rapportage.

    De herkomst blijft eerlijk: zo'n waarde landt als opgave met de ondernemer
    als bron, naast een attestatie die door zijn netbeheerder is afgegeven. Dat
    onderscheid hoort de lezer van het rapport en van de zaak te zien.
    """

    bron: str
    soort: str  # identiteit | registratie | attestatie | opgave
    tool: str | None
    toestemming: bool
    feitnaam: str | None = None
    corrigeerbaar: bool = False
    zelf_op_te_geven: bool = False


HERKOMST: dict[str, Veld] = {
    "KVK_NUMMER": Veld("sessie", "identiteit", None, False),
    "IS_WOONFUNCTIE": Veld(
        "KvK Handelsregister", "registratie", "kvk__mijn_bedrijf", False,
        feitnaam="WOONFUNCTIE"
    ),
    "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": Veld(
        "Business Wallet", "attestatie", "netbeheerder__verbruik", True,
        feitnaam="ELEKTRICITEIT_KWH", zelf_op_te_geven=True
    ),
    "JAARLIJKS_GASVERBRUIK_M3": Veld(
        "Business Wallet", "attestatie", "netbeheerder__verbruik", True,
        feitnaam="GAS_M3", zelf_op_te_geven=True
    ),
    # Bepaalt welke bijlage van de erkende maatregelenlijst geldt (artikel 4.14,
    # tweede lid, en artikel 5.29, tweede lid, Omgevingsregeling). Het
    # handelsregister kent het begrip "kas" niet, maar de SBI-omschrijving noemt
    # telen onder glas; `feiten._teelt_in_kas` leidt daar een vermoeden uit af dat
    # de ondernemer kan corrigeren. De andere twee weet alleen hij: telen in een
    # gebouw dat geen kas is staat niet als zodanig in het register, en of het
    # verlaagde energiebelastingtarief gebruikt wordt is een fiscaal gegeven dat
    # geen van onze bronnen draagt.
    "TEELT_GEWASSEN_IN_KAS": Veld(
        "KvK Handelsregister", "registratie", "kvk__mijn_bedrijf", False,
        feitnaam="TEELT_IN_KAS", corrigeerbaar=True
    ),
    "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS": Veld("de ondernemer", "opgave", None, False),
    "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": Veld(
        "de ondernemer", "opgave", None, False
    ),
    "AANWEZIGE_CATEGORIEEN": Veld("de ondernemer", "opgave", None, False),
}


def route(veldnaam: str) -> Veld | None:
    """De bron van één veld, of None als we hem niet kennen."""
    return HERKOMST.get(veldnaam)

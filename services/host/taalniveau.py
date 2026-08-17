"""Leesbaarheid meten van wat de assistent zegt (B1-bewaking).

Dit is een **vormmaat, geen begripsmaat**. Ze telt zinslengte en lettergrepen;
een korte zin kan onbegrijpelijk zijn en een lange zin glashelder. Wat ze wél
kan: betrappen dat een tekst plotseling juridischer wordt. Gebruik haar als
regressiebewaking, nooit als bewijs dat iets B1 is — dat oordeel is menselijk.

Twee bekende beperkingen, allebei reëel in deze repo:

1. De lettergreepteller telt klinkergroepen. Voor het Nederlands is dat een
   benadering, en een eenzijdige: aangrenzende klinkers die wél splitsen gaan
   voor één groep door, dus de teller telt te weinig en nooit te veel. Gemeten
   op dertien woorden: zeven fout, alle zeven ondergeteld ("situatie" 3 i.p.v.
   4, "via" 1 i.p.v. 2, "energiebesparingsplicht" 7 i.p.v. 8). De fout zit dus
   juist in de Latijnse en samengestelde woorden die een tekst boven B1 tillen,
   en minder lettergrepen betekent een hogere score. Elke meting hier is een
   bovengrens. Voor regressiebewaking maakt dat niet uit — de fout is stelselmatig,
   dus verschillen tussen metingen blijven bruikbaar — maar lees een absolute
   score nooit als "dit haalt B1".
2. Een opsomming zonder afsluitende punt wordt als één lange zin gelezen. De
   prompt-voorbeelden staan er vol mee, dus `alleen_proza=True` laat regels
   zonder eindleesteken weg. Zonder die schoonmaak meet je vooral opmaak.
"""

import re
from dataclasses import dataclass

_KLINKERGROEP = re.compile(r"[aeiouyáéíóúàèìòùäëïöü]+", re.IGNORECASE)
_WOORD = re.compile(r"[A-Za-zÀ-ÿ']+")

# Een `{{SLOT}}` bestaat alleen in de prompt: bij verzending heeft `slots.py`
# er al één waarde van gemaakt ("1 december 2027"). `_WOORD` splitst op de
# underscore in de slotnaam, dus zonder normalisatie telt `{{VOLGENDE_DEADLINE}}`
# als twee lange woorden - een tussenvorm die een respondent nooit ziet, en die
# zowel de zinslengte als de lettergreepdichtheid optrekt.
_SLOT = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def _zonder_slots(tekst: str) -> str:
    return _SLOT.sub("X", tekst)


# Einde van een zin: een leesteken, eventueel gevolgd door een sluitend
# aanhalingsteken of haakje. Zonder die staart telt een geciteerde vraag
# ('... kunt u vragen: "Hoeveel verbruikt mijn bedrijf?"') als onafgemaakt.
_EINDE = re.compile(r"[.!?][)\"'”’]*$")
_SPLITS = re.compile(r"(?<=[.!?])[)\"'”’]*\s+")

# De grens die `prompts/blocks/shared/tone.md` zelf stelt.
MAX_WOORDEN_PER_ZIN = 15


def _lettergrepen(woord: str) -> int:
    return max(1, len(_KLINKERGROEP.findall(woord)))


@dataclass(frozen=True)
class Leesbaarheid:
    """Uitkomst van een meting."""

    zinnen: int
    woorden: int
    gemiddelde_zinslengte: float
    score: float
    te_lange_zinnen: list[str]

    @property
    def aantal_te_lang(self) -> int:
        return len(self.te_lange_zinnen)


def _zinnen_uit(tekst: str, alleen_proza: bool) -> list[str]:
    regels = []
    for regel in tekst.splitlines():
        schoon = regel.strip()
        if not schoon or schoon.startswith(("#", "|", "```")):
            continue
        schoon = re.sub(r"^[-*•]\s*", "", schoon)
        schoon = re.sub(r"^\d+[.)]\s*", "", schoon)
        if alleen_proza and not _EINDE.search(schoon):
            # De regel loopt niet af op een eindleesteken. Dat is een
            # opsommingsregel ("Handelsnaam: Test BV") of een kopregel boven een
            # opsomming ("Dit heb ik geraadpleegd:"), en die horen niet als zin
            # te tellen: aan de volgende regel geplakt maken ze er schijnzinnen
            # van dertig woorden van.
            #
            # Alleen het slotfragment weggooien, niet de hele regel. Zulke
            # kopregels dragen vaak eerst een paar complete zinnen ("Dank u. Ik
            # heb het voorwerk voor u gedaan. Dit heb ik geraadpleegd:") en die
            # zijn wel degelijk antwoordtekst. De hele regel laten vallen liet
            # dertig complete zinnen in de voorbeelden ongemeten, waaronder een
            # van zeventien woorden - een overschrijding die de test hoorde te
            # vangen en niet zag.
            compleet = [
                deel for deel in _SPLITS.split(schoon) if _EINDE.search(deel)
            ]
            if not compleet:
                continue
            schoon = " ".join(compleet)
        regels.append(schoon)
    samen = " ".join(regels)
    return [z.strip() for z in _SPLITS.split(samen) if z.strip()]


def meet(tekst: str, alleen_proza: bool = True) -> Leesbaarheid | None:
    """Meet een tekst. Geeft None als er niets te meten valt.

    De score is de Flesch-Douma-index, de Nederlandse variant van Flesch Reading
    Ease: hoger is makkelijker. Ruwweg geldt 60 en hoger als vlot leesbaar. Zie
    de moduledocstring voor wat deze maat níét zegt.
    """
    zinnen = _zinnen_uit(tekst, alleen_proza)
    # Slots normaliseren ná de zinssplitsing: die loopt op leestekens
    # (`_EINDE`/`_SPLITS`), waar een slotnaam nooit een van bevat, dus dit
    # verandert geen enkel splitspunt - alleen wat er als "woord" telt.
    genormaliseerd = [_zonder_slots(z) for z in zinnen]
    woorden = _WOORD.findall(" ".join(genormaliseerd))
    if not zinnen or not woorden:
        return None
    gemiddelde = len(woorden) / len(zinnen)
    per_woord = sum(_lettergrepen(w) for w in woorden) / len(woorden)
    return Leesbaarheid(
        zinnen=len(zinnen),
        woorden=len(woorden),
        gemiddelde_zinslengte=gemiddelde,
        score=206.84 - 0.77 * (per_woord * 100) - 0.93 * gemiddelde,
        te_lange_zinnen=[
            z
            for z, g in zip(zinnen, genormaliseerd, strict=True)
            if len(_WOORD.findall(g)) > MAX_WOORDEN_PER_ZIN
        ],
    )

"""Leesbaarheid meten van wat de assistent zegt (B1-bewaking).

Dit is een **vormmaat, geen begripsmaat**. Ze telt zinslengte en lettergrepen;
een korte zin kan onbegrijpelijk zijn en een lange zin glashelder. Wat ze wél
kan: betrappen dat een tekst plotseling juridischer wordt. Gebruik haar als
regressiebewaking, nooit als bewijs dat iets B1 is — dat oordeel is menselijk.

Twee bekende beperkingen, allebei reëel in deze repo:

1. De lettergreepteller telt klinkergroepen. Voor het Nederlands is dat een
   benadering: "ideeën" en "zee" worden verkeerd geteld.
2. Een opsomming zonder afsluitende punt wordt als één lange zin gelezen. De
   prompt-voorbeelden staan er vol mee, dus `alleen_proza=True` laat regels
   zonder eindleesteken weg. Zonder die schoonmaak meet je vooral opmaak.
"""

import re
from dataclasses import dataclass

_KLINKERGROEP = re.compile(r"[aeiouyáéíóúàèìòùäëïöü]+", re.IGNORECASE)
_WOORD = re.compile(r"[A-Za-zÀ-ÿ']+")

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
        if schoon.endswith(":"):
            # Een kopregel boven een opsomming ("Dit heb ik geraadpleegd:").
            # Niet aan de volgende zin plakken - dat maakte er schijnzinnen van
            # dertig woorden van - en zelf niet op lengte beoordelen.
            continue
        if alleen_proza and not schoon.endswith((".", "!", "?")):
            # Een opsommingsregel zonder eindleesteken; die hoort niet als zin
            # geteld te worden.
            continue
        regels.append(schoon)
    samen = " ".join(regels)
    return [z.strip() for z in re.split(r"(?<=[.!?])\s+", samen) if z.strip()]


def meet(tekst: str, alleen_proza: bool = True) -> Leesbaarheid | None:
    """Meet een tekst. Geeft None als er niets te meten valt.

    De score is de Flesch-Douma-index, de Nederlandse variant van Flesch Reading
    Ease: hoger is makkelijker. Ruwweg geldt 60 en hoger als vlot leesbaar. Zie
    de moduledocstring voor wat deze maat níét zegt.
    """
    zinnen = _zinnen_uit(tekst, alleen_proza)
    woorden = _WOORD.findall(" ".join(zinnen))
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
            z for z in zinnen if len(_WOORD.findall(z)) > MAX_WOORDEN_PER_ZIN
        ],
    )

"""Uitleg in gewone taal uit een beslisgraaf (PDR-016).

De regelrecht-engine levert per uitkomst een beslisgraaf: de uitkomst
bovenaan, daaronder de voorwaarden (voldaan of niet), de gegevens en de
berekening, elk met de wetsgrond. Deze module zet die graaf om in een korte
tekst voor een ondernemer. Dat is de Graph-conditie uit Bos, Schuth en Chen,
"From Rules as Executed to Citizen Explanation" (JURIX 2026): het taalmodel
krijgt uitsluitend de graaf en een beperkt prompt, geen vrije wettekst en geen
tools. De graaf blijft de toetssteen; `toets()` controleert achteraf of elk
bedrag en elk percentage in de tekst ook in de graaf staat en of het
wetsartikel genoemd is.

Drie stappen, elk los te gebruiken en te testen:

1. `graaf_regels()`  -- de graaf als ingesprongen regels (diepte-eerst, alleen
   de doorslaggevende knopen, begrensd in aantal en diepte).
2. `bouw_prompt()`   -- de regels in een prompt met de spelregels voor het model.
3. `toets()`         -- de tekst van het model tegen de graaf.

`verwoord()` rijgt de drie aaneen met een LLM-aanroep via de clients van de
host, zodat de sleutel van de gebruiker (PDR-010) en de grenzen met levensteken
en herkansingen (PDR-013) hetzelfde werken als in het gesprek.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from taalniveau import meet

if TYPE_CHECKING:
    from errors import FoutMelding

logger = logging.getLogger("uitleg")

# Alleen de standaardbibliotheek bovenaan: de MCP-server (services/mcp/uitleg)
# en de CLI draaien deze module zonder de host-afhankelijkheden. Wat de host
# nodig heeft (config, errors, vlam_host) komt pas in `verwoord` binnen.
# Dezelfde grens als `config.MAX_VRAAG_TEKENS`.
MAX_VRAAG_TEKENS = int(os.getenv("MAX_VRAAG_TEKENS", "4000"))

# Grenzen op de graaf: dieper dan dit zegt een ondernemer niets meer, en meer
# regels passen niet binnen MAX_VRAAG_TEKENS zonder de instructies te raken.
MAX_REGELS = 60
MAX_DIEPTE = 6
# Een uitleg is kort; meer tokens nodigt uit tot bijverzinnen.
MAX_UITLEG_TOKENS = 600

# Woorden die een graaf-knoop beschrijven; alles daarbuiten in een knoop is
# data van de engine en gaat niet mee (geen url's, geen citaties).
_SOORTEN = frozenset({"uitkomst", "voorwaarde", "gegeven", "berekening", "stap"})


def _euro(cent: object) -> str:
    """Eurocent naar het bedrag zoals de engine en de kern het tonen: € 1.234,56."""
    try:
        bedrag = round(float(cent)) / 100
    except (TypeError, ValueError):
        return str(cent)
    return "€ " + f"{bedrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eenheid(knoop: dict) -> str | None:
    """De eenheid van een knoop; een gegeven zonder eenheid draagt die vaak in zijn naam."""
    eenheid = knoop.get("eenheid")
    if eenheid:
        return str(eenheid)
    if "eurocent" in str(knoop.get("naam") or ""):
        return "eurocent"
    return None


def _waarde_tekst(knoop: dict) -> str | None:
    """De waarde voor de regel, of None als die de lezer niets zegt.

    Een tussenresultaat van een operator (DIVIDE = 89740.8) heeft geen naam en
    geen eenheid; het model kan er alleen een verzonnen getal van maken. De
    ja/nee van een voorwaarde of keuze blijft: die zegt welke tak gold.
    """
    waarde = knoop.get("waarde")
    if waarde is True:
        return "ja"
    if waarde is False:
        return "nee"
    if waarde is None:
        return "geen waarde"
    if not knoop.get("naam") and isinstance(waarde, int | float):
        return None
    if _eenheid(knoop) == "eurocent":
        return _euro(waarde)
    return str(waarde)


def _grond_tekst(knoop: dict) -> str:
    grond = knoop.get("grond")
    if not isinstance(grond, dict) or not grond.get("artikel"):
        return ""
    lid = f" lid {grond['lid']}" if grond.get("lid") else ""
    return f" [grond: {grond.get('wet', '')} art. {grond['artikel']}{lid}]"


def _herkomst_tekst(knoop: dict) -> str:
    herkomst = knoop.get("herkomst")
    if isinstance(herkomst, str):
        return f" (bron: {herkomst})"
    if isinstance(herkomst, dict) and herkomst.get("bron"):
        return f" (bron: {herkomst['bron']})"
    return ""


def graaf_geldig(graaf: object) -> bool:
    """Is dit een beslisgraaf zoals de kern van regelrecht-uitleg die maakt?

    Minimaal: een dict met `soort` en `waarde`, en `doorslaggevend` als lijst
    (mag ontbreken). Meer eisen we niet; de graaf komt uit eigen code, niet van
    de gebruiker, maar hij komt wel via het netwerk binnen.
    """
    if not isinstance(graaf, dict) or "soort" not in graaf or "waarde" not in graaf:
        return False
    kinderen = graaf.get("doorslaggevend", [])
    return isinstance(kinderen, list) and all(graaf_geldig(k) for k in kinderen)


def graaf_regels(graaf: dict) -> list[str]:
    """De graaf als ingesprongen regels: diepte-eerst, alleen doorslaggevende knopen."""
    regels: list[str] = []

    def loop(knoop: dict, diepte: int) -> None:
        if len(regels) >= MAX_REGELS or diepte > MAX_DIEPTE:
            return
        soort = str(knoop.get("soort", "stap"))
        naam = knoop.get("naam") or knoop.get("operator") or soort
        waarde = _waarde_tekst(knoop)
        regels.append(
            f"{'  ' * diepte}- {soort}: {naam}{'' if waarde is None else f' = {waarde}'}"
            f"{_grond_tekst(knoop)}{_herkomst_tekst(knoop)}"
        )
        for kind in knoop.get("doorslaggevend") or []:
            loop(kind, diepte + 1)

    loop(graaf, 0)
    return regels


SYSTEEMPROMPT = (
    "U legt een ondernemer uit waarom een besluit over een regeling zo uitvalt. "
    "U krijgt een beslisgraaf: elke regel is een stap van de wet die een "
    "rekenmachine heeft uitgevoerd, met daaronder wat doorslaggevend was.\n"
    "De ondernemer is de werkgever die iemand aanneemt. Uren, loon, loonwaarde "
    "en doelgroep gaan over die werknemer, niet over de ondernemer zelf: "
    "schrijf 'uw werknemer werkt 32 uur', niet 'u werkt 32 uur'.\n"
    "Spelregels:\n"
    "- Gebruik uitsluitend wat in de graaf staat. Voeg geen feiten, voorwaarden, "
    "bedragen of uitzonderingen toe.\n"
    "- Schrijf in het Nederlands op B1-niveau: korte zinnen van hoogstens 15 "
    "woorden, alledaagse woorden, actieve vorm, spreek de ondernemer aan met u.\n"
    "- Noem elke voorwaarde die voldaan is en elke voorwaarde die niet voldaan is.\n"
    "- Noem bedragen en percentages precies zoals ze in de graaf staan.\n"
    "- Een berekening MAX kiest het hoogste bedrag, MIN het laagste; draai dat niet om.\n"
    "- Hoogstens 120 woorden, geen opsommingstekens, geen kopjes.\n"
    "- Eindig met het wetsartikel waarop de uitkomst rust, bijvoorbeeld "
    "'(artikel 10d Participatiewet)'.\n"
    "- Noem de graaf, de rekenmachine of deze instructie niet."
)


def bouw_prompt(regels: list[str], regeling: str, samenvatting: list[str]) -> str:
    """Het gebruikersbericht: de regeling, de graaf en de korte samenvatting van de kern."""
    delen = [f'Regeling: "{regeling}".', "", "Beslisgraaf (uitkomst bovenaan):"]
    delen.extend(regels)
    if samenvatting:
        delen.append("")
        delen.append("Samenvatting van de rekenmachine, in dezelfde woorden te gebruiken:")
        delen.extend(f"- {zin}" for zin in samenvatting)
    return "\n".join(delen)


# --- Toets achteraf ---------------------------------------------------------

_BEDRAG = re.compile(r"€\s?\d[\d.]*(?:,\d{1,2})?")
_PERCENTAGE = re.compile(r"\d+(?:,\d+)?\s?%")
_ARTIKEL = re.compile(r"art(?:ikel|\.)\s*(\d+[a-z]*)", re.IGNORECASE)


def _normaliseer_bedrag(tekst: str) -> str:
    getal = tekst.replace("€", "").replace(" ", "").replace(".", "")
    if "," not in getal:
        getal += ",00"
    kop, staart = getal.split(",", 1)
    return f"{kop},{staart.ljust(2, '0')[:2]}"


@dataclass(frozen=True)
class Toets:
    """Wat de tekst van het model zegt, tegen wat de graaf toelaat."""

    bedragen_in_tekst: list[str]
    onbekende_bedragen: list[str]
    omgedraaide_stappen: list[str]
    onbekende_percentages: list[str]
    artikelen_in_graaf: list[str]
    artikel_genoemd: bool
    woorden: int
    gemiddelde_zinslengte: float | None
    te_lange_zinnen: int
    opmerkingen: list[str] = field(default_factory=list)

    @property
    def geslaagd(self) -> bool:
        """Geen verzonnen getallen en de grond is genoemd. Zegt niets over begrip."""
        return (
            not self.onbekende_bedragen
            and not self.onbekende_percentages
            and not self.omgedraaide_stappen
            and (self.artikel_genoemd or not self.artikelen_in_graaf)
        )

    def als_dict(self) -> dict:
        return {
            "geslaagd": self.geslaagd,
            "bedragen_in_tekst": self.bedragen_in_tekst,
            "onbekende_bedragen": self.onbekende_bedragen,
            "omgedraaide_stappen": self.omgedraaide_stappen,
            "onbekende_percentages": self.onbekende_percentages,
            "artikelen_in_graaf": self.artikelen_in_graaf,
            "artikel_genoemd": self.artikel_genoemd,
            "woorden": self.woorden,
            "gemiddelde_zinslengte": self.gemiddelde_zinslengte,
            "te_lange_zinnen": self.te_lange_zinnen,
            "opmerkingen": self.opmerkingen,
        }


def _buitenste_keuze(regels: list[str]) -> str | None:
    """MAX of MIN van de minst diepe berekening die kiest, of None."""
    gevonden = [
        (len(r) - len(r.lstrip()), m.group(1))
        for r in regels
        if (m := re.search(r": (MAX|MIN)\b", r))
    ]
    return min(gevonden)[1] if gevonden else None


def toets(tekst: str, regels: list[str], samenvatting: list[str] = ()) -> Toets:
    """Controleer de tekst tegen de graaf (en de samenvatting van de kern).

    Een bedrag of percentage dat niet in de graaf staat, is verzonnen of
    verrekend; beide horen niet in een uitleg die trouw is aan de uitvoering.
    De leesbaarheid komt uit `taalniveau.meet`: een vormmaat, geen begripsmaat.
    """
    bron = "\n".join([*regels, *samenvatting])
    bron_bedragen = {_normaliseer_bedrag(b) for b in _BEDRAG.findall(bron)}
    bron_percentages = {p.replace(" ", "") for p in _PERCENTAGE.findall(bron)}
    bron_artikelen = sorted({a.lower() for a in _ARTIKEL.findall(bron)})

    bedragen = _BEDRAG.findall(tekst)
    onbekend = sorted({b for b in bedragen if _normaliseer_bedrag(b) not in bron_bedragen})
    percentages = _PERCENTAGE.findall(tekst)
    onbekend_pct = sorted(
        {p for p in percentages if p.replace(" ", "") not in bron_percentages}
    )
    genoemd = {a.lower() for a in _ARTIKEL.findall(tekst)}
    artikel_genoemd = bool(genoemd & set(bron_artikelen))

    opmerkingen: list[str] = []
    # Een omgedraaide rekenstap: de graaf kiest het hoogste (MAX), de tekst zegt
    # "laagste". Bedragen kloppen dan nog, de redenering niet; dit is de fout
    # die de bedragencontrole mist.
    # Een graaf kan beide kennen (een MIN binnen een MAX); de tekst gaat over de
    # buitenste keuze, dus de minst diepe telt.
    omgedraaid: list[str] = []
    laag = re.search(r"\b(laagste|minste|kleinste)\b", tekst, re.IGNORECASE)
    hoog = re.search(r"\b(hoogste|meeste|grootste)\b", tekst, re.IGNORECASE)
    buitenste = _buitenste_keuze(regels)
    if buitenste == "MAX" and laag:
        omgedraaid.append(laag.group(1))
    if buitenste == "MIN" and hoog:
        omgedraaid.append(hoog.group(1))
    if omgedraaid:
        opmerkingen.append("De tekst draait een rekenstap om (hoogste en laagste).")
    if onbekend:
        opmerkingen.append("De tekst noemt een bedrag dat niet in de beslisgraaf staat.")
    if onbekend_pct:
        opmerkingen.append("De tekst noemt een percentage dat niet in de beslisgraaf staat.")
    if bron_artikelen and not artikel_genoemd:
        opmerkingen.append("De tekst noemt het wetsartikel niet.")

    leesbaarheid = meet(tekst)
    woorden = len(re.findall(r"[A-Za-zÀ-ÿ']+", tekst))
    if woorden > 150:
        opmerkingen.append("De tekst is langer dan 120 woorden.")
    return Toets(
        bedragen_in_tekst=bedragen,
        onbekende_bedragen=onbekend,
        omgedraaide_stappen=omgedraaid,
        onbekende_percentages=onbekend_pct,
        artikelen_in_graaf=bron_artikelen,
        artikel_genoemd=artikel_genoemd,
        woorden=woorden,
        gemiddelde_zinslengte=(
            leesbaarheid.gemiddelde_zinslengte if leesbaarheid else None
        ),
        te_lange_zinnen=leesbaarheid.aantal_te_lang if leesbaarheid else 0,
        opmerkingen=opmerkingen,
    )


# --- De aanroep ----------------------------------------------------------------


@dataclass(frozen=True)
class Uitleg:
    tekst: str
    toets: Toets
    regels: int
    mode: str


async def verwoord(
    host,
    *,
    graaf: dict,
    regeling: str,
    samenvatting: list[str],
    mode: str = "claude",
    vlam_api_key_override: str = "",
    claude_api_key_override: str = "",
) -> Uitleg | FoutMelding:
    """Zet de graaf om in gewone taal met het model van `mode`, en toets het antwoord.

    Geen gespreksgeschiedenis, geen tools, geen bronnen: één aanroep met het
    systeemprompt en de graaf. De sleutel leeft precies dit verzoek
    (`host._request_clients`, PDR-010).
    """
    from config import CLAUDE_MODEL, CLAUDE_TIMEOUT, VLAM_MODEL_ID, VLAM_TIMEOUT
    from errors import maak_fout
    from vlam_host import _geen_sleutel_fout, _llm_aanroep

    regels = graaf_regels(graaf)
    prompt = bouw_prompt(regels, regeling, samenvatting)
    if len(prompt) > MAX_VRAAG_TEKENS:
        return maak_fout("UITLEG_GRAAF_TE_GROOT", maximum=f"{MAX_VRAAG_TEKENS} tekens")

    backend = "vlam" if mode == "vlam" else "claude"
    async with host._request_clients(
        vlam_api_key_override, claude_api_key_override, backend
    ) as (claude, vlam):
        if backend == "vlam":
            if not vlam:
                return _geen_sleutel_fout("vlam")
            aanroep = partial(
                vlam.chat.completions.create,
                model=VLAM_MODEL_ID,
                max_tokens=MAX_UITLEG_TOKENS,
                messages=[
                    {"role": "system", "content": SYSTEEMPROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            grens = VLAM_TIMEOUT
        else:
            if not getattr(claude, "api_key", ""):
                return _geen_sleutel_fout("claude")
            aanroep = partial(
                claude.messages.create,
                model=CLAUDE_MODEL,
                max_tokens=MAX_UITLEG_TOKENS,
                system=SYSTEEMPROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            grens = CLAUDE_TIMEOUT

        respons = None
        async for event in _llm_aanroep(aanroep, backend, grens, label="Uitleg"):
            if event["type"] == "_resultaat":
                respons = event["resultaat"]
            elif event["type"] == "error":
                return maak_fout(event.get("code", "LLM_ONBEKEND"), backend=backend)

    tekst = _tekst_uit(respons, backend)
    if not tekst.strip():
        return maak_fout("LLM_LEEG_ANTWOORD")
    uitkomst = toets(tekst, regels, samenvatting)
    logger.info(
        "Uitleg [%s] %s: %d regels, %d woorden, toets %s",
        backend, regeling, len(regels), uitkomst.woorden,
        "geslaagd" if uitkomst.geslaagd else "afgekeurd",
    )
    return Uitleg(tekst=tekst.strip(), toets=uitkomst, regels=len(regels), mode=backend)


def _tekst_uit(respons, backend: str) -> str:
    """De platte tekst uit een Anthropic- of OpenAI-respons."""
    if respons is None:
        return ""
    if backend == "vlam":
        keuzes = getattr(respons, "choices", None) or []
        return "".join((k.message.content or "") for k in keuzes if getattr(k, "message", None))
    return "\n".join(
        getattr(b, "text", "") for b in getattr(respons, "content", []) or []
    )


# --- Opdrachtregel ---------------------------------------------------------------
#
# `python uitleg.py regels|toets|verzoek [bestand] [opties]`: de deterministische
# stappen zonder host, voor de CLI-wrapper (services/cli/uitleg-cli) en voor
# scripts. Het bestand is een verzoek voor /uitleg ({regeling, graaf,
# samenvatting}) of de uitvoer van `uitleg bereken` uit regelrecht-uitleg
# ({afleidingen: {naam: {afleiding: {uitkomst}, tekst: {kort}}}}); in dat
# laatste geval kiest --output de uitkomst.


def verzoek_uit(document: dict, output: str | None, regeling: str | None) -> dict:
    """Maak het verzoek voor /uitleg uit een verzoek of een `uitleg bereken`-uitvoer."""
    if "afleidingen" in document:
        afleidingen = document["afleidingen"]
        naam = output or next(iter(afleidingen), None)
        if naam not in afleidingen:
            raise KeyError(naam)
        a = afleidingen[naam]
        return {
            "regeling": regeling or naam,
            "graaf": a["afleiding"]["uitkomst"],
            "samenvatting": [
                r["tekst"] for r in a.get("tekst", {}).get("kort", []) if not r.get("technisch")
            ],
        }
    return {
        "regeling": regeling or document.get("regeling", ""),
        "graaf": document.get("graaf"),
        "samenvatting": list(document.get("samenvatting", [])),
    }


def _cli(argv: list[str]) -> int:
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(prog="uitleg", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="opdracht", required=True)
    for naam, hulp in (
        ("regels", "de graaf als regels, met het prompt"),
        ("toets", "toets een tekst tegen de graaf"),
        ("verzoek", "het verzoek voor /uitleg, uit een `uitleg bereken`-uitvoer"),
    ):
        p = sub.add_parser(naam, help=hulp)
        p.add_argument("bestand", nargs="?", help="JSON-bestand; zonder: stdin")
        p.add_argument("--output", help="uitkomst uit een `uitleg bereken`-uitvoer")
        p.add_argument("--regeling", help="naam van de regeling")
        if naam == "toets":
            p.add_argument("--tekst", help="de tekst van het model")
            p.add_argument("--tekst-bestand", help="bestand met de tekst van het model")
    args = parser.parse_args(argv)

    bron = open(args.bestand, encoding="utf-8") if args.bestand else sys.stdin
    with bron:
        document = json.load(bron)
    try:
        verzoek = verzoek_uit(document, args.output, args.regeling)
    except KeyError as e:
        print(json.dumps({"error": "NIET_GEVONDEN", "message": f"Geen uitkomst {e}."}), file=sys.stderr)
        return 2
    if not graaf_geldig(verzoek["graaf"]):
        print(
            json.dumps({"error": "INVALID_INPUT", "message": "Geen geldige beslisgraaf."}),
            file=sys.stderr,
        )
        return 2
    regels = graaf_regels(verzoek["graaf"])

    if args.opdracht == "verzoek":
        uit = verzoek
    elif args.opdracht == "regels":
        uit = {
            "regels": regels,
            "prompt": bouw_prompt(regels, verzoek["regeling"], verzoek["samenvatting"]),
            "systeemprompt": SYSTEEMPROMPT,
        }
    else:
        if args.tekst_bestand:
            with open(args.tekst_bestand, encoding="utf-8") as f:
                tekst = f.read()
        else:
            tekst = args.tekst or ""
        if not tekst.strip():
            print(
                json.dumps({"error": "INVALID_INPUT", "message": "Geen tekst om te toetsen."}),
                file=sys.stderr,
            )
            return 2
        uit = toets(tekst, regels, verzoek["samenvatting"]).als_dict()
    print(json.dumps(uit, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(_cli(sys.argv[1:]))

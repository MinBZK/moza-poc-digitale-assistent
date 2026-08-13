"""Loopt de flow van het gebruikersonderzoek af tegen een draaiende host.

Waarom dit script bestaat: de tests in `tests/` meten bestanden op schijf. Wat
een respondent op 25 en 27 augustus 2026 werkelijk op zijn scherm krijgt komt
uit een echt LLM, langs echte bronnen, en gaat door een frontend die de platte
tekst van de assistent tot een formulier parseert. Geen van die drie schakels
wordt door de suite gedekt.

Draaien (host moet al luisteren op --host):

    uv run python services/host/scripts/onderzoeksflow.py --mode vlam
    uv run python services/host/scripts/onderzoeksflow.py --mode claude --kvk 85234567

Exitcode 0 als alle controles slagen, 1 als er één faalt. Elke controle noemt
wat er misging en waarom dat erg is, zodat het rapport zonder deze code te lezen
te begrijpen is.

LET OP: dit kost echte LLM-calls. Het is geen CI-test en hoort niet in de
pytest-suite; draai het bewust, vóór een sessie en na een promptwijziging.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taalniveau import MAX_WOORDEN_PER_ZIN, meet  # noqa: E402

# ---------------------------------------------------------------------------
# De frontend-parser, nagebouwd
#
# `MinBZK/moza-poc` krijgt van de host alleen `message` als platte tekst; er zit
# geen gestructureerd veld in het answer-event. De radiovelden die de respondent
# ziet worden dus uit die tekst geparsed door `parseVraag` in
# assets/javascript/digitale-assistent.js. Levert die parser niets op, dan krijgt
# de respondent geen formulier maar een lap tekst.
#
# Deze functie volgt die JS-implementatie regel voor regel. Wijkt de frontend af,
# dan wijkt dit script af en meet het het verkeerde - vandaar de verwijzing.
# ---------------------------------------------------------------------------

_BRON = re.compile(r"^bron\s*:\s*(.+)$", re.IGNORECASE)
_GENUMMERD = re.compile(r"^(\d+)[.)]\s+(.+)$")
_BULLET = re.compile(r"^[•·*-]")
_EML_CODE = re.compile(r"^[A-Z]{1,4}\d+$")


@dataclass
class VraagSpec:
    titel: str
    intro: str
    velden: list[str]
    bron: str


def parse_vraag(bericht: str) -> VraagSpec | None:
    """Port van parseVraag() uit digitale-assistent.js. None = geen formulier."""
    velden: list[str] = []
    intro_regels: list[str] = []
    bron = ""
    zag_vraag = False

    for ruwe_regel in (bericht or "").split("\n"):
        regel = ruwe_regel.strip()
        if not regel:
            continue
        if m := _BRON.match(regel):
            bron = m.group(1).rstrip(". ").strip()
            continue
        if m := _GENUMMERD.match(regel):
            inhoud = m.group(2)
            # Alleen een genummerde regel die een vraag stelt of twee opties
            # aanbiedt wordt een veld. De rest valt weg, ook als het inhoudelijk
            # een keuze is.
            if inhoud.rstrip().endswith("?") or " / " in inhoud:
                velden.append(_veldnaam(inhoud))
                zag_vraag = True
            continue
        if not zag_vraag and not _BULLET.match(regel):
            intro_regels.append(regel)

    if not velden:
        return None

    intro = " ".join(intro_regels).strip()
    is_eml = bool(re.search(r"erkende maatregelenlijst|eml", intro, re.IGNORECASE)) or any(
        _EML_CODE.match(v) for v in velden
    )
    return VraagSpec(
        titel="Erkende Maatregelenlijst (EML 2023)" if is_eml else "Vragen van de assistent",
        intro=intro,
        velden=velden,
        bron=bron,
    )


def _veldnaam(inhoud: str) -> str:
    """De `naam` die parseVeldRegel aan een veld geeft."""
    schoon = inhoud.rstrip().rstrip("?").strip()
    if " / " in schoon:
        voor = schoon.rsplit(" / ", 1)[0]
        if " - " in voor:
            return voor.rsplit(" - ", 1)[0].strip()
    return schoon


# ---------------------------------------------------------------------------
# Persona's: wat er op het scherm staat, en dus wat de assistent moet noemen
# ---------------------------------------------------------------------------


@dataclass
class Persona:
    kvk: str
    naam: str
    plaats: str
    straat: str
    elektriciteit: str
    gas: str
    plicht: bool


PERSONAS = {
    "62345681": Persona(
        "62345681", "Kwekerij De Bloesem", "Bleiswijk", "Hoefweg 210", "420.000", "140.000", True
    ),
    "85234567": Persona(
        "85234567", "Koffiezaak Noon", "Rotterdam", "Meent 88", "61.250", "9.800", True
    ),
    "56789012": Persona(
        "56789012",
        "Roots & Locks",
        "Rotterdam",
        "Witte de Withstraat 18",
        "8.400",
        "1.200",
        False,
    ),
}

# Een adresregel in het antwoord: "Vestigingsadres: <iets>". Als de assistent
# hier een straat noemt, moet het die van het scherm zijn.
_ADRESREGEL = re.compile(r"^.*(?:vestigingsadres|adres)\s*:\s*(.+)$", re.IGNORECASE)


def _controleer_adres(loop: Loop, stap: str, antwoord: str, persona: Persona) -> None:
    """Noemt de assistent een adres, dan moet het dat van het scherm zijn.

    Dit is geen vormfout maar een verzonnen feit: de respondent leest zijn adres
    op de pagina Adresgegevens en ziet het in het rapport dat namens hem naar RVO
    gaat. Twee verschillende adressen betekent dat een van beide gelogen is, en
    de respondent weet welke.
    """
    regels = [
        m.group(1).strip()
        for regel in antwoord.splitlines()
        if (m := _ADRESREGEL.match(regel.strip()))
    ]
    if not regels:
        return
    fout = [r for r in regels if persona.straat.lower() not in r.lower()]
    loop.controleer(
        stap,
        not fout,
        f"elk genoemd adres is dat van het scherm ({persona.straat})",
        "verzonnen adres in het antwoord:\n" + "\n".join(f"- {r}" for r in fout),
    )


@dataclass
class Uitkomst:
    stap: str
    ok: bool
    reden: str
    detail: str = ""


@dataclass
class Loop:
    host: str
    kvk: str
    mode: str
    session_id: str | None = None
    uitkomsten: list[Uitkomst] = field(default_factory=list)
    transcript: list[dict] = field(default_factory=list)

    def controleer(self, stap: str, ok: bool, reden: str, detail: str = "") -> None:
        self.uitkomsten.append(Uitkomst(stap, ok, reden, detail))
        vlag = "OK  " if ok else "FOUT"
        print(f"  [{vlag}] {reden}")
        if not ok and detail:
            for regel in detail.splitlines():
                print(f"         {regel}")

    def beurt(self, bericht: str) -> tuple[str, list[str], list[dict]]:
        """Eén beurt zoals de frontend hem stuurt. Geeft (antwoord, tools, events)."""
        events: list[dict] = []
        with httpx.Client(timeout=300.0) as client:
            with client.stream(
                "POST",
                f"{self.host}/chat/stream",
                headers={"X-Test-User": self.kvk},
                json={
                    "message": bericht,
                    "session_id": self.session_id,
                    "mode": self.mode,
                },
            ) as respons:
                respons.raise_for_status()
                for regel in respons.iter_lines():
                    if regel.startswith("data: "):
                        events.append(json.loads(regel[6:]))

        antwoord = ""
        tools = []
        self.transcript.append({"vraag": bericht, "events": events})
        for e in events:
            if e.get("type") == "tool":
                tools.append(e.get("name") or e.get("tool") or "?")
            elif e.get("type") == "answer":
                antwoord = e.get("message", "")
                self.session_id = e.get("session_id") or self.session_id
        return antwoord, tools, events


def _fouten(events: list[dict]) -> list[str]:
    return [
        f"{e.get('code', '?')}: {e.get('bericht') or e.get('message', '')}"
        for e in events
        if e.get("type") in ("error", "bron_fout")
    ]


def _b1(loop: Loop, stap: str, antwoord: str) -> None:
    """Toets het antwoord aan de regel die tone.md zelf stelt."""
    gemeten = meet(antwoord)
    if gemeten is None:
        return
    loop.controleer(
        stap,
        gemeten.aantal_te_lang == 0,
        f"antwoord blijft onder {MAX_WOORDEN_PER_ZIN} woorden per zin "
        f"(score {gemeten.score:.0f})",
        "\n".join(f"- {z}" for z in gemeten.te_lange_zinnen),
    )


def draai(loop: Loop, persona: Persona) -> None:
    print(f"\n=== gezondheid ({loop.mode}) ===")
    gezond = httpx.get(f"{loop.host}/health", timeout=30.0).json()
    loop.controleer(
        "health",
        gezond["backends"].get("vlam" if loop.mode.endswith("vlam") else "claude", False),
        f"backend {loop.mode} is beschikbaar",
        json.dumps(gezond["backends"]),
    )
    ontbreekt = [n for n, s in gezond["servers"].items() if s != "verbonden"]
    loop.controleer(
        "health",
        not ontbreekt,
        "alle vijf de bronnen zijn verbonden",
        f"niet verbonden: {ontbreekt}",
    )

    print("\n=== 1. vraag naar de plicht (toestemming eerst) ===")
    antwoord, tools, events = loop.beurt("Geldt de energiebesparingsplicht voor mijn bedrijf?")
    loop.controleer("stap1", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    loop.controleer(
        "stap1",
        not tools,
        "geen bron geraadpleegd voor toestemming (PDR-008)",
        f"wel aangeroepen: {tools}",
    )
    loop.controleer(
        "stap1",
        "?" in antwoord,
        "de assistent vraagt om toestemming",
        antwoord[:300],
    )
    _b1(loop, "stap1", antwoord)

    print("\n=== 2. toestemming geven ===")
    antwoord, tools, events = loop.beurt("Ja, ga je gang.")
    loop.controleer("stap2", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    for verwacht in ("kvk__mijn_bedrijf", "netbeheerder__verbruik", "regelrecht__execute_law"):
        loop.controleer(
            "stap2", verwacht in tools, f"{verwacht} is aangeroepen", f"aangeroepen: {tools}"
        )
    for waarde, wat in (
        (persona.naam, "de bedrijfsnaam van het scherm"),
        (persona.elektriciteit, "het elektriciteitsverbruik van het scherm"),
        (persona.gas, "het gasverbruik van het scherm"),
    ):
        loop.controleer(
            "stap2", waarde in antwoord, f"het antwoord noemt {wat} ({waarde})", antwoord[:400]
        )
    _controleer_adres(loop, "stap2", antwoord, persona)
    _b1(loop, "stap2", antwoord)

    print("\n=== 3. maatregelen opvragen: de twee feitelijke vragen ===")
    antwoord, tools, events = loop.beurt("Welke maatregelen gelden er voor mijn bedrijf?")
    loop.controleer("stap3", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    spec = parse_vraag(antwoord)
    loop.controleer(
        "stap3",
        spec is not None,
        "de frontend kan hier een formulier van maken",
        "parse_vraag gaf None: de respondent krijgt platte tekst in plaats van "
        "radioknoppen.\n" + antwoord[:400],
    )
    if spec:
        loop.controleer(
            "stap3", len(spec.velden) == 2, f"twee vragen als velden ({len(spec.velden)})", str(spec.velden)
        )
    _b1(loop, "stap3", antwoord)

    print("\n=== 4. de twee vragen beantwoorden: het EML-formulier ===")
    antwoord, tools, events = loop.beurt(
        "Ja, we hebben een koelinstallatie. Een afzuiginstallatie hebben we niet."
    )
    loop.controleer("stap4", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    spec = parse_vraag(antwoord)
    loop.controleer(
        "stap4",
        spec is not None,
        "de frontend kan van de maatregelen een formulier maken",
        "parse_vraag gaf None. De maatregelen staan wel in de tekst, maar niet in "
        "een vorm die de frontend tot radioknoppen maakt: genummerde regels moeten "
        "op '?' eindigen of ' / ' bevatten, en regels die met '-' beginnen worden "
        "genegeerd.\n" + antwoord[:600],
    )
    if spec:
        loop.controleer(
            "stap4",
            spec.titel.startswith("Erkende Maatregelenlijst"),
            f"het formulier heet '{spec.titel}'",
            str(spec),
        )
    _b1(loop, "stap4", antwoord)

    print("\n=== 5. maatregelen invullen: rapport, nog niet indienen ===")
    antwoord, tools, events = loop.beurt(
        "GC1 is uitgevoerd, GC3 niet, GF4 is uitgevoerd, FD3 niet, FD7 is uitgevoerd."
    )
    loop.controleer("stap5", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    # rvo__indienen is de enige muterende tool en mag niet ongevraagd draaien.
    # Draait hij hier al, dan is de bevestigingsplicht uit CLAUDE.md/PDR-003 stuk
    # en dient de assistent namens de respondent iets in bij RVO.
    loop.controleer(
        "stap5",
        "rvo__indienen" not in tools,
        "nog niet ingediend zonder bevestiging",
        f"aangeroepen: {tools}\n{antwoord[:400]}",
    )
    loop.controleer(
        "stap5",
        "?" in antwoord,
        "de assistent vraagt eerst om bevestiging",
        antwoord[:500],
    )
    _b1(loop, "stap5", antwoord)

    print("\n=== 6. bevestigen: rapportage indienen ===")
    antwoord, tools, events = loop.beurt("Ja, dien maar in.")
    loop.controleer("stap6", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    loop.controleer(
        "stap6",
        "rvo__indienen" in tools,
        "rvo__indienen is aangeroepen",
        f"aangeroepen: {tools}\n{antwoord[:400]}",
    )
    zaken = [e for e in events if e.get("type") == "case"]
    loop.controleer(
        "stap6",
        bool(zaken),
        "er komt een case-event voor 'Lopende zaken'",
        "zonder dit event ziet de respondent zijn zaak niet terug in de UI.\n"
        + antwoord[:400],
    )
    loop.controleer(
        "stap6",
        "in behandeling" in antwoord.lower(),
        "de rapportage gaat 'in behandeling', niet 'goedgekeurd'",
        "een PoC hoort geen besluit te suggereren dat niet genomen is.\n"
        + antwoord[:400],
    )
    _controleer_adres(loop, "stap6", antwoord, persona)
    _b1(loop, "stap6", antwoord)


def aggregeer(runs: list[list[Uitkomst]]) -> dict[str, str]:
    """Per controle: hoe vaak geslaagd van hoe vaak uitgevoerd.

    De noemer is het aantal keren dat de controle daadwerkelijk draaide, niet
    het aantal runs. Een run die halverwege afbreekt heeft die controle niet
    uitgevoerd, en dat is iets anders dan hem niet halen.
    """
    tellers: dict[str, list[int]] = {}
    for run in runs:
        for uitkomst in run:
            geslaagd, totaal = tellers.setdefault(uitkomst.reden, [0, 0])
            tellers[uitkomst.reden] = [geslaagd + int(uitkomst.ok), totaal + 1]
    return {reden: f"{g}/{t}" for reden, (g, t) in tellers.items()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="http://127.0.0.1:8000")
    p.add_argument("--kvk", default="62345681", choices=sorted(PERSONAS))
    p.add_argument("--transcript", help="schrijf alle events naar dit JSON-bestand")
    p.add_argument("--mode", default="vlam", choices=["vlam", "claude", "cli:vlam", "cli:claude"])
    p.add_argument("--runs", type=int, default=1, help="aantal doorlopen")
    p.add_argument("--json", help="schrijf een machineleesbare samenvatting hierheen")
    a = p.parse_args()

    persona = PERSONAS[a.kvk]
    print(f"Persona: {persona.naam} ({persona.kvk}), modus {a.mode}, host {a.host}")

    alle_runs: list[list[Uitkomst]] = []
    for nummer in range(1, a.runs + 1):
        print(f"\n{'#' * 70}\n# RUN {nummer} van {a.runs}\n{'#' * 70}")
        loop = Loop(host=a.host, kvk=a.kvk, mode=a.mode)
        try:
            draai(loop, persona)
        except httpx.HTTPError as e:
            print(f"RUN {nummer} AFGEBROKEN: {type(e).__name__}: {e}")
        alle_runs.append(loop.uitkomsten)

    if a.transcript:
        Path(a.transcript).write_text(
            json.dumps(loop.transcript, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\ntranscript weggeschreven naar {a.transcript} (laatste run)")

    samenvatting = aggregeer(alle_runs)
    print(f"\n{'=' * 70}\nSAMENVATTING OVER {a.runs} RUN(S)")
    for reden, score in sorted(samenvatting.items()):
        geslaagd, totaal = (int(x) for x in score.split("/"))
        vlag = "OK  " if geslaagd == totaal else "FOUT"
        print(f"  [{vlag}] {score}  {reden}")

    if a.json:
        Path(a.json).write_text(
            json.dumps(
                {
                    "modus": a.mode,
                    "kvk": a.kvk,
                    "runs": a.runs,
                    "samenvatting": samenvatting,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nsamenvatting weggeschreven naar {a.json}")

    alles_groen = all(
        score.split("/")[0] == score.split("/")[1] for score in samenvatting.values()
    )
    return 0 if alles_groen else 1


if __name__ == "__main__":
    raise SystemExit(main())

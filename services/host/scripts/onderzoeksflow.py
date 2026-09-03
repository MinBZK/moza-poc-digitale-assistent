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

Taak 8 vroeg om drie extra controles op de regelgestuurde flow (taak 1 t/m 7):
elk feit draagt bron en soort, de wet is aangeroepen vóór elke andere bron, en
geen veld aan de wet meegegeven dat niet uit de routeringstabel komt. Van die
drie staat er hier maar één (`_controleer_wet_eerst`) - de andere twee kunnen
niet, en dat is hieronder verantwoord in plaats van ze weg te laten.

- **Wél gemeten: de wet vóór elke andere bron.** `_regel_status` in
  vlam_host.py yieldt een `tool`-event voor élke aanroep die de
  orkestratielus zelf doet, óók herhaalde rondes van `regelrecht__execute_law`
  zelf - niet alleen aanroepen die het model start. Die events komen al over
  de SSE-stream die dit script toch al leest; er is geen hostlog of
  debug-endpoint voor nodig.
- **Niet gemeten: elk feit heeft een bron en een soort.** De feitenkaart
  (`vlam_host.py: self.feiten`) verlaat het hostproces nooit: geen SSE-event
  draagt hem, geen endpoint geeft hem terug, en geen bestaande logregel dumpt
  hem (`slots.py:vul_slots` gebruikt alleen `feit["waarde"]`, nooit `bron`/
  `soort`). Dat toevoegen is een wijziging aan de host, en die mag deze taak
  niet maken. Wat wél met code lezen is vast te stellen: elke plek die iets in
  de feitenkaart schrijft - `feiten.py:_met_herkomst`,
  `feiten.py:_herkomst_gebruikte_waarden`, `vlam_host.py:_opgaven_als_feiten`
  - zet bron én soort onvoorwaardelijk. Dat is een aanwijzing dat de eis
  klopt, geen meting dat hij dat ook echt doet op een draaiende host.
- **Niet gemeten: geen veld aan de wet meegegeven buiten de routeringstabel.**
  De parameters die `regelrecht__execute_law` binnenkrijgen zijn nergens
  zichtbaar: het `tool`-event op de SSE-stream draagt geen argumenten, en
  zowel `vlam_host.py:_arg_keys` als `server.py:_audit_log` in de
  regelrecht-server loggen bewust alleen de bovenste sleutelnamen
  (`law, parameters, service`), nooit wat er ín `parameters` zit - dat is
  privacy-by-design (PDR-009: geen waarden in de log). Voor de
  orkestratielus zelf is dit een garantie van de code
  (`regelloop.py:_parameters_uit_feiten` loopt alleen over
  `regelrouting.HERKOMST`), maar het model kan `regelrecht__execute_law` ook
  zelf rechtstreeks aanroepen (zie de bevinding hieronder) en dáár is met de
  huidige logging niets van te zien.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from taalniveau import MAX_WOORDEN_PER_ZIN, meet  # noqa: E402

import errors  # noqa: E402
import regelrouting  # noqa: E402

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


# Wat de respondent op elk regelveld antwoordt. De sleutels zijn de veldnamen
# uit de wet, niet uit dit script: vraagt een nieuwe versie van de wet om een
# veld dat hier niet staat, dan hoort de meting daarop te falen en niet stil
# een formulier onbeantwoord te laten. Precies dat ging mis toen de wet van de
# demo-subset (koel-/afzuiginstallatie) naar de sectorbewuste versie ging: het
# script bleef de oude twee vragen beantwoorden, het formulier bleef openstaan
# en alle stappen erna maten niets meer.
_OPGAVE_ANTWOORDEN: dict[str, object] = {
    "TEELT_GEWASSEN_IN_KAS": True,
    "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS": False,
    "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": True,
    # Twee categorieën, uit twee verschillende onderdelen: één categorie
    # verbergt of de groepering meekomt, en de hele lijst maakt van de meting
    # een uitputtende inventarisatie.
    "AANWEZIGE_CATEGORIEEN": ["Binnenverlichting", "Perslucht"],
    # De demo-subset van vóór de sectorbewuste wet. Blijft staan zodat de
    # meting ook tegen een engine met de oude wet doorloopt.
    "HEEFT_KOELINSTALLATIE": True,
    "HEEFT_AFZUIGINSTALLATIE": False,
}

_JA_NEE = {True: "Ja", False: "Nee"}


def vraag_uit_events(events: list[dict]) -> dict | None:
    """De gestructureerde vraag-spec van het answer-event, of None.

    De frontend leest `payload.vraag` vóór ze de tekst gaat parsen
    (`vraagSpec` in digitale-assistent.js). Dit script deed dat niet en las
    alleen de tekst, waardoor het de veldnamen niet kende en het formulier dus
    niet kon invullen.
    """
    for event in reversed(events):
        if event.get("type") == "answer" and event.get("vraag"):
            return event["vraag"]
    return None


def beantwoord_vraag(vraag: dict) -> tuple[str, dict, list[str]]:
    """Vul het formulier zoals de frontend het verstuurt.

    Geeft (bericht, opgaven, onbeantwoord) terug. `bericht` is de tekst die de
    respondent ziet vertrekken, `opgaven` de losse waarden op het chat-contract
    — dezelfde tweedeling als in digitale-assistent.js, waar `delen` voor de
    mens is en `opgaven` voor de regel. `onbeantwoord` noemt de velden waarvoor
    dit script geen antwoord kent; die lijst hoort leeg te zijn.
    """
    delen: list[str] = []
    opgaven: dict[str, object] = {}
    onbeantwoord: list[str] = []
    for veld in vraag.get("velden") or []:
        naam = veld.get("naam", "")
        if naam not in _OPGAVE_ANTWOORDEN:
            onbeantwoord.append(naam)
            continue
        waarde = _OPGAVE_ANTWOORDEN[naam]
        opgaven[naam] = waarde
        if isinstance(waarde, list):
            delen.append("Aanwezig: " + ", ".join(waarde))
        else:
            delen.append(f"{veld.get('label') or naam}: {_JA_NEE[bool(waarde)]}")
    return " ".join(delen), opgaven, onbeantwoord


def maatregelen_uit_events(events: list[dict]) -> list[dict]:
    """De maatregelen die het answer-event draagt, of een lege lijst."""
    for event in reversed(events):
        if event.get("type") == "answer" and event.get("maatregelen"):
            return event["maatregelen"]
    return []


def status_per_maatregel(maatregelen: list[dict]) -> str:
    """De status van élke maatregel, zoals het formulier hem verstuurt.

    Twee dingen zaten hier eerder fout. De codes stonden vast in dit bestand
    (`GC1`, `FD3`), en die bestaan niet meer zodra de bijlage die voor dit
    bedrijf geldt andere maatregelen bevat. En de zin dekte maar twee
    maatregelen, terwijl de rapportage over álle geldende maatregelen gaat: de
    assistent vroeg dan terecht om de overige eenentwintig en kwam nooit aan
    indienen toe. De frontend rendert per maatregel een radioknop en stuurt ze
    in één keer terug; dat is wat hier wordt nagebootst.

    Om en om uitgevoerd/niet uitgevoerd, zodat het rapport beide gevallen
    draagt: alles op één waarde verbergt of de assistent het onderscheid
    overneemt.
    """
    codes = [m.get("code", "") for m in maatregelen if m.get("code")]
    if not codes:
        return "De eerste maatregel is uitgevoerd, de tweede nog niet."
    delen = [
        f"{code}: {'uitgevoerd' if i % 2 == 0 else 'niet uitgevoerd'}"
        for i, code in enumerate(codes)
    ]
    return "Status per maatregel: " + "; ".join(delen) + "."


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
        "14.800",
        "1.900",
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


# Tools die daadwerkelijk één van de vier persona-feiten opleveren die
# `_controleer_slots` letterlijk terugzoekt (naam, straat, elektriciteit, gas) -
# zie `feiten.py:_uit_kvk` / `_uit_netbeheerder`. `regelrecht__execute_law` hoort
# hier bewust NIET bij: sinds de orkestratielus (taak 4, `regelloop.volg_regel`)
# draait die op élke beurt opnieuw, ook een kale bevestiging als stap 6, en
# levert zelf geen bedrijfsfeit terug - alleen een regel-oordeel
# (`voldoet_aan_voorwaarden`/`ontbrekende_gegevens`). Stond hij toch in de
# verzameling, dan telt elke beurt als "er draaide een feiten-tool", ook een
# beurt die terecht geen enkel feit herhaalt.
_FEITENTOOLS = {"kvk__mijn_bedrijf", "netbeheerder__verbruik"}

# Uit de routeringstabel afgeleid, niet hardgecodeerd: welke bronnen de
# orkestratielus zelf mag raadplegen (elk veld met een `tool`), en welke
# daarvan toestemming vergen (PDR-008). Loopt de tabel uit met een tweede wet,
# dan lopen deze verzamelingen vanzelf mee.
_ROUTETOOLS = {veld.tool for veld in regelrouting.HERKOMST.values() if veld.tool}
_TOESTEMMINGSTOOLS = {
    veld.tool for veld in regelrouting.HERKOMST.values() if veld.tool and veld.toestemming
}


def _geraadpleegde_toestemmingstools(tools: list[str], events: list[dict]) -> list[str]:
    """Toestemmingsplichtige tools die de host ook écht raadpleegde, niet alleen probeerde.

    Een naam in `tools` komt uit een `tool`-event en bewijst op zichzelf niet
    dat de bron geraadpleegd is: de PDR-008-poort in
    `vlam_host._bron_aanroep_gated` kan de aanroep hebben geweigerd
    (`TOESTEMMING_VEREIST`) zonder de bron te raken. Sinds taak 8 stuurt de
    host bij zo'n weigering geen `tool`-event meer, maar deze controle heet
    "is deze bron geraadpleegd" en moet dat blijven meten ook als die garantie
    ooit verzwakt — vandaar de expliciete kruiscontrole tegen een
    `bron_fout`-event met code TOESTEMMING_VEREIST, in plaats van blind op de
    aanwezigheid van de naam in `tools` te vertrouwen. Poging en raadpleging
    zijn niet hetzelfde, en een controle die zegt te meten of een bron is
    geraadpleegd mag niet slagen of falen op een poging die geweigerd werd.
    """
    geweigerd = {
        e.get("bron")
        for e in events
        if e.get("type") == "bron_fout" and e.get("code") == "TOESTEMMING_VEREIST"
    }
    return [
        t for t in tools if t in _TOESTEMMINGSTOOLS and errors.bron_uit_tool(t) not in geweigerd
    ]


def _controleer_wet_eerst(loop: Loop, stap: str, tools: list[str]) -> None:
    """De wet is aangeroepen vóór elke andere bron uit de routeringstabel.

    Zichtbaar zonder hostlog: `_regel_status` in vlam_host.py yieldt een
    `tool`-event voor élke aanroep die de orkestratielus zelf doet — ook
    `regelrecht__execute_law` zelf, en ook herhaalde rondes — niet alleen voor
    aanroepen die het model via zijn eigen tool-dispatch start. De volgorde in
    `tools` (zoals deze module die al uit de SSE-stream opbouwt) weerspiegelt
    dus de werkelijke aanroepvolgorde van de host, inclusief de lus. Dat is
    waarom deze controle geen hostlog of debug-endpoint nodig heeft, in
    tegenstelling tot de twee controles die dat wel doen (zie de toelichting
    bovenaan dit bestand).

    Draait alleen als er in deze beurt daadwerkelijk een andere bron uit de
    routeringstabel is aangeroepen (`_ROUTETOOLS` minus de wet zelf) - anders
    is er niets om de volgorde tegen af te zetten.
    """
    andere_bron = [t for t in _ROUTETOOLS if t != "regelrecht__execute_law"]
    eerste_andere = min(
        (i for i, t in enumerate(tools) if t in andere_bron), default=None
    )
    if eerste_andere is None:
        return
    eerste_wet = min(
        (i for i, t in enumerate(tools) if t == "regelrecht__execute_law"), default=None
    )
    loop.controleer(
        stap,
        eerste_wet is not None and eerste_wet < eerste_andere,
        "regelrecht__execute_law is aangeroepen vóór elke andere bron uit de routeringstabel",
        f"volgorde: {tools}",
    )


def _controleer_slots(
    loop: Loop, stap: str, antwoord: str, persona: Persona, tools: list[str]
) -> None:
    """Geen onopgelost slot, en de bron-waarden staan er na substitutie wél.

    Let op wat dit niet is. De spec noemt ook "geen letterlijk feit waar een slot
    hoort", en die controle hoort op de RUWE modeltekst vóór substitutie. Die
    krijgt dit script niet: over HTTP komt alleen het ingevulde antwoord binnen.
    Wil je dat toetsen, dan moet de host de ruwe tekst meesturen achter een
    debug-vlag - bewust niet in dit plan, want dat is een nieuw veld op het
    contract vlak voor een onderzoek.

    Wat hier overblijft is nog steeds het meeste waard: een onopgelost slot
    betekent dat het model een feit noemde dat de bron niet had, en ontbrekende
    bron-waarden betekenen dat de substitutie niet gedraaid heeft.

    De tweede controle draait alleen op een beurt die zelf een feiten-tool
    aanriep (`_FEITENTOOLS`: `kvk__mijn_bedrijf` of `netbeheerder__verbruik`).
    Op stap 6 ("Ja, dien maar in.") is `rvo__indienen` de enige tool die iets
    nieuws doet; de assistent bevestigt daar terecht zonder de feiten te
    herhalen, en die beurt heeft niets nieuws om te substitueren.

    Let op: `regelrecht__execute_law` telt hier expliciet niet mee, ook al
    raadpleegt de host die op elke beurt (zie `_FEITENTOOLS`-docstring
    hierboven). Een eerdere versie van deze controle gebruikte wél de volle
    `_BRONTOOLS`-verzameling (mét de wet) als poort, en die vuurde daardoor op
    stap 6: de host draait de regelloop nu op elke beurt, dus
    `regelrecht__execute_law` stond altijd in `tools`, en de controle eiste
    dan een letterlijk bedrijfsfeit in een beurt die alleen een indien-
    bevestiging is. Dat is geen verzonnen feit of gefaalde substitutie, maar
    een meetfout: de poort testte "raadpleegde deze beurt een bron uit
    `_BRONTOOLS`" terwijl hij "noemde deze beurt een feit dat een bron moest
    leveren" bedoelde te testen. Met `_FEITENTOOLS` vuurt de controle alleen
    nog op een beurt die de KvK of de Business Wallet zelf raadpleegde.
    """
    loop.controleer(
        stap,
        "{{" not in antwoord,
        "geen onopgelost slot in het antwoord",
        antwoord[:400],
    )
    if not any(t in _FEITENTOOLS for t in tools):
        return
    letterlijk = [
        waarde
        for waarde in (persona.naam, persona.straat, persona.elektriciteit, persona.gas)
        if waarde in antwoord
    ]
    loop.controleer(
        stap,
        bool(letterlijk),
        f"de bron-waarden staan in het antwoord ({', '.join(letterlijk) or 'geen'})",
        "de host heeft de slots niet ingevuld, of het model noemde de feiten niet",
    )


def _controleer_maatregelen_event(loop: Loop, stap: str, events: list[dict]) -> None:
    """Het answer-event draagt de maatregelen als data, niet alleen als tekst.

    `parseVraag` in digitale-assistent.js leest `maatregelen` op het answer-event
    vóór het terugvalt op regels tekst parsen (zie de commit die dit veld
    toevoegde). Zolang dat veld leeg blijft, hangt het formulier alsnog af van
    hoe het model de beurt toevallig formatteerde - precies wat de tekstparser-
    controle hierboven meet. Die controle blijft staan: ze meet de fallback, dit
    hier meet de structurele fix.
    """
    antwoorden = [e for e in events if e.get("type") == "answer"]
    laatste = antwoorden[-1] if antwoorden else {}
    maatregelen = laatste.get("maatregelen")
    loop.controleer(
        stap,
        bool(maatregelen),
        "het answer-event draagt een maatregelen-lijst",
        json.dumps(laatste, ensure_ascii=False)[:400],
    )
    if maatregelen:
        onvolledig = [m for m in maatregelen if not m.get("code") or not m.get("omschrijving")]
        loop.controleer(
            stap,
            not onvolledig,
            "elk item heeft een gevulde code en omschrijving",
            json.dumps(onvolledig, ensure_ascii=False),
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
    api_key: str = ""

    def controleer(self, stap: str, ok: bool, reden: str, detail: str = "") -> None:
        self.uitkomsten.append(Uitkomst(stap, ok, reden, detail))
        vlag = "OK  " if ok else "FOUT"
        print(f"  [{vlag}] {reden}")
        if not ok and detail:
            for regel in detail.splitlines():
                print(f"         {regel}")

    def _headers(self) -> dict[str, str]:
        """Sessie-identiteit, en de LLM-sleutel als de host er zelf geen heeft.

        Een deployment draait bewust zonder server-side sleutel (PDR-010): die
        komt van de gebruiker, via een header. Zonder deze meting kun je zo'n
        omgeving dus niet meten - en juist die omgeving is degene waarop de
        respondent straks werkt.
        """
        headers = {"X-Test-User": self.kvk}
        if self.api_key:
            veld = "X-Claude-API-Key" if "claude" in self.mode else "X-VLAM-API-Key"
            headers[veld] = self.api_key
        return headers

    def beurt(
        self,
        bericht: str,
        *,
        toestemming: bool | None = None,
        opgaven: dict | None = None,
    ) -> tuple[str, list[str], list[dict]]:
        """Eén beurt zoals de frontend hem stuurt. Geeft (antwoord, tools, events).

        `toestemming` gaat alleen mee als hij expliciet is meegegeven — precies
        zoals de "Delen"-knop het `toestemming`-veld op het chat-contract vult
        (PDR-008). Zonder deze parameter kan dit script het akkoord van de
        respondent niet meer nabootsen: sinds de PDR-008-poort in de host
        (`vlam_host._bron_aanroep_gated`) stelt platte tekst als "Ja, ga je
        gang." de Business Wallet niet meer open.

        `opgaven` gaat mee zoals het vraag-formulier van de frontend het vult:
        de losse antwoorden per regelveld, naast de tekst van het bericht. Een
        antwoord dat alleen in de tekst staat moet het model opnieuw
        interpreteren; als opgave is het toerekenbaar aan het veld.
        """
        payload: dict = {
            "message": bericht,
            "session_id": self.session_id,
            "mode": self.mode,
        }
        if toestemming is not None:
            payload["toestemming"] = toestemming
        if opgaven:
            payload["opgaven"] = opgaven

        events: list[dict] = []
        with httpx.Client(timeout=300.0) as client:
            with client.stream(
                "POST",
                f"{self.host}/chat/stream",
                headers=self._headers(),
                json=payload,
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
    # Toets tegen de vijf bekende bronnen, niet tegen wat `servers` toevallig
    # bevat: een bewust uitgezette bron staat daar niet in en zou anders
    # ongemerkt passeren. Eén controle, met in de toelichting het verschil
    # tussen een storing en een uitgezette bron (de Business Wallet hoort aan).
    # /health is het contract (PDR-015): `status` zegt of een ingerichte bron
    # niet opkwam, `bronnen_uit` welke bronnen bewust uitstaan. De Business
    # Wallet hoort aan, dus allebei horen leeg respectievelijk "actief" te zijn.
    uit = sorted(gezond.get("bronnen_uit", []))
    storing = sorted(n for n, s in gezond["servers"].items() if s != "verbonden")
    loop.controleer(
        "health",
        gezond.get("status") == "actief" and not uit,
        "alle vijf de bronnen zijn verbonden (geen storing, geen bron uitgezet)",
        f"status: {gezond.get('status')}; storing: {storing}; bewust uitgezet: {uit}",
    )

    print("\n=== 1. vraag naar de plicht (toestemming eerst) ===")
    antwoord, tools, events = loop.beurt("Geldt de energiebesparingsplicht voor mijn bedrijf?")
    loop.controleer("stap1", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    geraadpleegd = _geraadpleegde_toestemmingstools(tools, events)
    loop.controleer(
        "stap1",
        not geraadpleegd,
        "geen toestemmingsplichtige bron geraadpleegd vóór toestemming (PDR-008)",
        f"wel geraadpleegd: {geraadpleegd} (alle genoemde tools: {tools})",
    )
    loop.controleer(
        "stap1",
        "?" in antwoord,
        "de assistent vraagt om toestemming",
        antwoord[:300],
    )
    # Sinds toestemming-per-bron raadpleegt de host óók de KvK niet meer
    # zonder akkoord: stap 1 eindigt in het deelverzoek voor het
    # Handelsregister, en er is nog geen enkele persoonsbron aangeraakt.
    loop.controleer(
        "stap1",
        "kvk__mijn_bedrijf" not in tools,
        "de KvK is niet geraadpleegd vóór akkoord",
        f"aangeroepen: {tools}",
    )
    _controleer_wet_eerst(loop, "stap1", tools)
    _b1(loop, "stap1", antwoord)

    print("\n=== 2a. akkoord voor het Handelsregister ===")
    antwoord, tools, events = loop.beurt("Ja, ga je gang.", toestemming=True)
    loop.controleer("stap2", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    loop.controleer(
        "stap2",
        "kvk__mijn_bedrijf" in tools,
        "kvk__mijn_bedrijf is aangeroepen (ná akkoord voor de KvK)",
        f"aangeroepen: {tools}",
    )
    loop.controleer(
        "stap2",
        "netbeheerder__verbruik" not in tools,
        "het KvK-akkoord opent de Business Wallet niet",
        f"aangeroepen: {tools}",
    )

    print("\n=== 2b. akkoord voor de Business Wallet ===")
    antwoord, tools, events = loop.beurt("Ja, dat mag ook.", toestemming=True)
    loop.controleer("stap2", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    for verwacht in ("netbeheerder__verbruik", "regelrecht__execute_law"):
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
    _controleer_slots(loop, "stap2", antwoord, persona, tools)
    _controleer_wet_eerst(loop, "stap2", tools)
    _b1(loop, "stap2", antwoord)

    print("\n=== 3. maatregelen opvragen: de vragen die de wet stelt ===")
    # De orkestratielus draait beide regels op rij, dus het formulier kan al bij
    # stap 2 zijn meegekomen. Dan is deze beurt er een die niets toevoegt - dat
    # is een bevinding, geen reden om de vraag-spec te missen.
    vraag = vraag_uit_events(events)
    vraag_kwam_eerder = vraag is not None
    antwoord, tools, events = loop.beurt("Welke maatregelen gelden er voor mijn bedrijf?")
    loop.controleer("stap3", not _fouten(events), "geen foutmelding", "\n".join(_fouten(events)))
    vraag = vraag_uit_events(events) or vraag
    loop.controleer(
        "stap3",
        vraag is not None,
        "het answer-event draagt een gestructureerde vraag-spec",
        "zonder `vraag` op het event moet de frontend de tekst parsen; de "
        "veldnamen van de wet gaan dan verloren.\n" + antwoord[:400],
    )
    loop.controleer(
        "stap3",
        not vraag_kwam_eerder,
        "deze beurt voegt iets toe (het formulier stond er nog niet)",
        "het formulier kwam al bij stap 2 mee; deze beurt kost de respondent "
        "tijd zonder hem verder te helpen.",
    )
    spec = parse_vraag(antwoord)
    loop.controleer(
        "stap3",
        spec is not None,
        "de frontend kan hier ook uit de tekst een formulier maken",
        "parse_vraag gaf None: valt het `vraag`-veld weg, dan krijgt de "
        "respondent platte tekst in plaats van radioknoppen.\n" + antwoord[:400],
    )
    _controleer_wet_eerst(loop, "stap3", tools)
    _b1(loop, "stap3", antwoord)

    print("\n=== 4. het formulier invullen: de opgaven van de ondernemer ===")
    bericht, opgaven, onbeantwoord = beantwoord_vraag(vraag or {})
    loop.controleer(
        "stap4",
        vraag is not None and not onbeantwoord,
        "dit script kent een antwoord op elk veld dat de wet vraagt",
        f"geen antwoord voor: {onbeantwoord}. Vul `_OPGAVE_ANTWOORDEN` aan; "
        "zonder antwoord blijft het formulier open en meten de stappen hierna "
        "niets.",
    )
    antwoord, tools, events = loop.beurt(
        bericht or "Ik weet niet welke gegevens u nodig hebt.", opgaven=opgaven
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
    _controleer_maatregelen_event(loop, "stap4", events)
    _controleer_wet_eerst(loop, "stap4", tools)
    _b1(loop, "stap4", antwoord)

    print("\n=== 5. maatregelen invullen: rapport, nog niet indienen ===")
    antwoord, tools, events = loop.beurt(
        status_per_maatregel(maatregelen_uit_events(events))
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
    for waarde, wat in (
        (persona.naam, "bedrijfsnaam"),
        (persona.straat, "vestigingsadres"),
        (persona.elektriciteit, "elektriciteitsverbruik"),
    ):
        loop.controleer(
            "stap5", waarde in antwoord, f"het rapport bevat {wat}", antwoord[:400]
        )
    _controleer_wet_eerst(loop, "stap5", tools)
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
    _controleer_slots(loop, "stap6", antwoord, persona, tools)
    _controleer_wet_eerst(loop, "stap6", tools)
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
    p.add_argument(
        "--api-key",
        default="",
        help="LLM-sleutel voor een host zonder eigen sleutel (PDR-010); "
        "valt terug op ANTHROPIC_API_KEY / VLAM_API_KEY uit de omgeving",
    )
    a = p.parse_args()
    sleutel = a.api_key or os.getenv(
        "ANTHROPIC_API_KEY" if "claude" in a.mode else "VLAM_API_KEY", ""
    )

    persona = PERSONAS[a.kvk]
    print(f"Persona: {persona.naam} ({persona.kvk}), modus {a.mode}, host {a.host}")

    alle_runs: list[list[Uitkomst]] = []
    for nummer in range(1, a.runs + 1):
        print(f"\n{'#' * 70}\n# RUN {nummer} van {a.runs}\n{'#' * 70}")
        loop = Loop(host=a.host, kvk=a.kvk, mode=a.mode,
            api_key=sleutel,
        )
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

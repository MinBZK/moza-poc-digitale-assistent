"""Compose system prompts from modular blocks.

Reads .md files from the blocks/ and examples/ directories and assembles
them into a single system prompt. Shared blocks ensure consistency between
VLAM and Claude; model-specific hints allow targeted tuning.
"""

import re
from pathlib import Path

BLOCKS_DIR = Path(__file__).parent / "blocks"
EXAMPLES_DIR = Path(__file__).parent / "examples"

SEPARATOR = "\n\n---\n\n"


def _load(relative_path: str) -> str:
    """Load a block file relative to BLOCKS_DIR."""
    return (BLOCKS_DIR / relative_path).read_text(encoding="utf-8").strip()


def _load_if_exists(relative_path: str) -> str | None:
    """Load a block file if it exists, otherwise return None."""
    path = BLOCKS_DIR / relative_path
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


def _load_domain_blocks(onbereikbaar: set[str]) -> list[str]:
    """Load the domain knowledge blocks for sources that are reachable.

    Same reasoning as the example filter: a block explaining what KOOP can do,
    while KOOP is down, promises something the assistant cannot deliver. These
    blocks name their sources in prose as often as by tool name, so they carry
    the same explicit `<!-- bronnen: ... -->` marker as the examples rather than
    relying on a tool-prefix match.
    """
    domain_dir = BLOCKS_DIR / "shared" / "domain"
    if not domain_dir.exists():
        return []
    blokken = []
    for pad in sorted(domain_dir.glob("*.md")):
        tekst = pad.read_text(encoding="utf-8").strip()
        gebruikt = _bronnen_van_voorbeeld(tekst)
        # Alleen weglaten als élke genoemde bron eruit ligt. Een blok dat twee
        # bronnen beschrijft blijft nuttig zolang er één werkt; een voorbeeld
        # daarentegen demonstreert één concrete flow en is bij één ontbrekende
        # stap niet meer na te doen.
        if gebruikt and gebruikt <= onbereikbaar:
            continue
        blokken.append(_OPTIONEEL_MARKER.sub("", _BRONNEN_MARKER.sub("", tekst)).strip())
    return blokken


_BRONNEN_MARKER = re.compile(r"<!--\s*bronnen:\s*([^>]*?)\s*-->")
_OPTIONEEL_MARKER = re.compile(r"<!--\s*bronnen-optioneel:\s*([^>]*?)\s*-->")


def _bronnen_van_voorbeeld(tekst: str) -> set[str]:
    """Read the `<!-- bronnen: ... -->` marker at the top of an example.

    Explicit rather than inferred from tool names: examples also promise sources
    in plain language ("uw bedrijfsgegevens uit het Handelsregister"), and a
    promise the assistant cannot keep is exactly what the availability block is
    there to prevent.
    """
    return _marker_inhoud(_BRONNEN_MARKER, tekst)


def _marker_inhoud(patroon: re.Pattern, tekst: str) -> set[str]:
    match = patroon.search(tekst)
    if not match:
        return set()
    return {deel.strip() for deel in match.group(1).split(",") if deel.strip()}


def _optionele_bronnen(tekst: str) -> set[str]:
    """Bronnen die een blok aanstipt maar niet nodig heeft.

    Een voorbeeld dat één stap met een uitgevallen bron toont is nog steeds
    bruikbaar voor de overige stappen; alleen als de kernbron eruit ligt is de
    hele demonstratie niet meer na te doen. Zonder dit onderscheid verdween het
    volledige informatieplicht-voorbeeld uit elke CLI-prompt, alleen omdat het
    CLI-transport geen netbeheerder-wrapper heeft.
    """
    return _marker_inhoud(_OPTIONEEL_MARKER, tekst)


def _load_examples(
    has_tools: bool, bronnen_offline: list[str], bronnen_uit: list[str]
) -> list[str]:
    """Load the few-shot example blocks that still make sense right now.

    Examples are the strongest steering signal in this prompt, which cuts both
    ways: an example that calls `koop__zoek_regelgeving` — or merely offers to —
    while KOOP is down demonstrates exactly what the availability block just
    forbade. Drop any example that leans on a source the model cannot reach.
    """
    if not EXAMPLES_DIR.exists():
        return []
    storing = set(bronnen_offline)
    onbereikbaar = storing | set(bronnen_uit)
    bruikbaar = []
    for pad in sorted(EXAMPLES_DIR.glob("*.md")):
        tekst = pad.read_text(encoding="utf-8").strip()
        gebruikt = _bronnen_van_voorbeeld(tekst)
        if not has_tools and gebruikt:
            continue
        if gebruikt & onbereikbaar:
            continue
        # Een aangestipte bron die eruit ligt maakt het voorbeeld niet onbruikbaar,
        # maar de stap die 'm gebruikt moet er wel uit.
        # Alleen een storing krijgt een waarschuwing. Een bron die uitstaat
        # verdwijnt stil: de waarschuwing hier is precies de zin die het model
        # tegen de gebruiker naspreekt ("de Business Wallet is niet beschikbaar").
        kwijt = _optionele_bronnen(tekst) & storing
        schoon = _OPTIONEEL_MARKER.sub("", _BRONNEN_MARKER.sub("", tekst)).strip()
        if kwijt:
            schoon = (
                f"{schoon}\n\n(LET OP: in deze omgeving is "
                f"{', '.join(sorted(kwijt))} niet beschikbaar. Sla de stap die "
                "die bron gebruikt over en vraag de gegevens aan de gebruiker.)"
            )
        bruikbaar.append(schoon)
    return bruikbaar


def _compose_bronnen_status(bronnen_offline: list[str], has_tools: bool) -> str | None:
    """Build the block listing the sources that are currently unavailable.

    Without this the model has no idea a source is missing: it either invents an
    answer or reports a vague failure. Labels and alternatives are reused from
    the error catalogue (`errors.py`) so the wording matches what the user sees
    when a source fails mid-conversation.

    With no tools at all this block replaces `no_tools.md` rather than joining
    it: that block tells the model to answer from its own knowledge, which is
    the opposite of what this one says. Two contradicting instructions in one
    prompt is worse than either instruction alone.
    """
    if not bronnen_offline:
        return None
    from errors import BRON_ALTERNATIEF, BRON_LABELS

    regels = [
        f"- {BRON_LABELS.get(bron, bron)} - alternatief voor de gebruiker: "
        f"{BRON_ALTERNATIEF.get(bron, 'de website van de betreffende instantie')}"
        for bron in bronnen_offline
    ]
    bestand = "shared/bronnen_status.md" if has_tools else "shared/geen_bronnen.md"
    return _load(bestand).replace("{bronnen}", "\n".join(regels))


def _compose_bronnen_uit(bronnen_uit: list[str]) -> str | None:
    """Het blok voor bronnen die bewust uitstaan: zwijgen, niet melden.

    Het storingsblok zegt "meld welke bron niet beschikbaar is". Voor een bron
    die uitstaat is dat verkeerd: de gebruiker ervaart dan een storing in iets
    dat in zijn omgeving nooit heeft bestaan, midden in een flow die verder
    werkt. Zonder dit blok noemt het model de bron toch, want de routeringstabel
    en `tool_usage.md` schrijven hem voor.
    """
    if not bronnen_uit:
        return None
    from errors import BRON_LABELS

    regels = [f"- {BRON_LABELS.get(bron, bron)}" for bron in bronnen_uit]
    return _load("shared/bronnen_uit.md").replace("{bronnen}", "\n".join(regels))


def _regel_status_klaar_tekst(resultaat: dict) -> str:
    """Tekst voor een afgeronde toets: de uitkomst, niet de interne sleutelnaam.

    `voldoet_aan_voorwaarden` is de naam van het RegelRecht-veld, geen
    juridisch oordeel op zich; die vertaalslag hoort hier, niet in de prompt
    met de rauwe sleutelnaam erin (`missing_required`, `voldoet_aan_voorwaarden`
    lezen als jargon, niet als een uitspraak richting de ondernemer).
    """
    if not resultaat.get("voldoet_aan_voorwaarden"):
        return (
            "De regeltoets is afgerond: deze verplichting geldt niet voor uw "
            "bedrijf. Meld dat aan de ondernemer en vermeld dat de uitkomst uit "
            "RegelRecht komt."
        )
    delen = ["De regeltoets is afgerond: de verplichting geldt voor uw bedrijf."]
    uitkomsten = resultaat.get("uitkomsten") or {}
    for veld, label in (
        ("heeft_informatieplicht", "de informatieplicht"),
        ("heeft_onderzoeksplicht", "de onderzoeksplicht"),
        ("heeft_energiebesparingsplicht", "de energiebesparingsplicht"),
    ):
        if veld in uitkomsten:
            waarde = "geldt" if uitkomsten[veld] else "geldt niet"
            delen.append(f"{label.capitalize()} {waarde}.")
    if uitkomsten.get("volgende_rapportage_deadline"):
        delen.append(
            f"Eerstvolgende rapportagedeadline: {uitkomsten['volgende_rapportage_deadline']}."
        )
    if uitkomsten.get("rapportage_frequentie_jaren"):
        delen.append(
            f"Rapportagefrequentie: elke {uitkomsten['rapportage_frequentie_jaren']} jaar."
        )
    delen.append(
        "Formuleer uw antwoord op basis hiervan en vermeld dat de uitkomst uit "
        "RegelRecht komt."
    )
    return " ".join(delen)


def _maatregelen_status_tekst(maatregelen: dict | None) -> str | None:
    """Tekst voor de tweede regel in de keten: de erkende maatregelen.

    De host draait die regel zelf zodra de energiebesparingsplicht geldt
    (artikel 5.15d Bal draagt op te rapporteren over de getroffen erkende
    maatregelen). Het model hoeft dus niet te besluiten dát de lijst nodig is —
    alleen te vertellen wat eruit kwam, of te vragen wat er nog aan ontbreekt.
    """
    if not maatregelen:
        return None
    wacht_op = maatregelen.get("wacht_op")
    if wacht_op == "opgave":
        return (
            "Voor de erkende maatregelen is nog nodig welke installaties en "
            "gebouwdelen bij dit bedrijf voorkomen. Vraag dat via het formulier "
            "en verzin de categorieën niet zelf."
        )
    if wacht_op == "toestemming":
        return (
            "De maatregelenlijst wacht nog op toestemming van de ondernemer voor "
            "een bron. Vraag daar EXPLICIET om."
        )
    if not maatregelen.get("klaar"):
        return (
            "De erkende maatregelen zijn op dit moment niet te bepalen. Meld dat "
            "eerlijk in plaats van een lijst te noemen die u niet hebt."
        )
    uitkomsten = (maatregelen.get("resultaat") or {}).get("uitkomsten") or {}
    lijst = uitkomsten.get("maatregelen") or []
    if not lijst:
        return (
            "De maatregelentoets is afgerond en levert voor de opgegeven "
            "categorieën geen erkende maatregelen op. Meld dat als uitkomst."
        )
    delen = [
        f"De maatregelentoets is afgerond: {len(lijst)} erkende maatregelen uit "
        "de bijlage die voor dit bedrijf geldt."
    ]
    bijlagen = [
        uitkomsten.get("bijlage_milieubelastende_activiteiten"),
        uitkomsten.get("bijlage_gebouwen"),
    ]
    genoemd = [b for b in bijlagen if b]
    if genoemd:
        delen.append(
            "Het gaat om bijlage " + " en ".join(genoemd) + " van de Omgevingsregeling."
        )
    invoer = _gebruikte_waarden_tekst(maatregelen.get("resultaat") or {})
    if invoer:
        delen.append(invoer)
    delen.append("De maatregelen zijn: " + _maatregelen_opsomming(lijst) + ".")
    delen.append(
        "Noem de maatregelen uit deze lijst en verzin er geen bij. Elke "
        "maatregel geldt onder de randvoorwaarden die erbij staan; presenteer ze "
        "als voorwaarden om na te gaan, niet als vaststaand."
    )
    return " ".join(delen)


# Hoe een regelveld van de maatregelenwet in gewone taal heet. De prompt noemt
# nooit een rauwe veldnaam (zie `reden` hierboven); een veld dat hier niet
# staat blijft dus weg in plaats van als jargon door te lekken.
_INVOER_LABELS = {
    "TEELT_GEWASSEN_IN_KAS": "teelt in kassen",
    "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS": "teelt in een gebouw dat geen kas is",
    "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF": (
        "gebruikt het verlaagde energiebelastingtarief voor de glastuinbouw"
    ),
}


def _gebruikte_waarden_tekst(resultaat: dict) -> str | None:
    """Op welke antwoorden de maatregelentoets is gebaseerd.

    Zonder deze zin ziet het model wel dát de toets klaar is, maar niet waarmee
    gerekend is. Een feit dat de host uit een registratie heeft afgeleid - "teelt
    in kassen", uit de SBI-omschrijving - las het model dan als een aanname die
    het niet mocht doen, en het bleef de ondernemer die vraag stellen terwijl de
    toets allang een antwoord had.
    """
    gebruikt = resultaat.get("gebruikte_waarden") or {}
    delen = [
        f"{label}: {'ja' if gebruikt[veld] else 'nee'}"
        for veld, label in _INVOER_LABELS.items()
        if isinstance(gebruikt.get(veld), bool)
    ]
    if not delen:
        return None
    return (
        "De toets rekende met de antwoorden die er al zijn (" + "; ".join(delen)
        + "). Vraag die niet opnieuw."
    )


def _maatregelen_opsomming(lijst: list) -> str:
    """De maatregelen als `code - naam (categorie)`, gescheiden door puntkomma's."""
    delen = []
    for maatregel in lijst:
        if not isinstance(maatregel, dict):
            continue
        code, naam = maatregel.get("code", ""), maatregel.get("naam", "")
        categorie = maatregel.get("categorie", "")
        tekst = f"{code} - {naam}".strip(" -")
        if categorie:
            tekst = f"{tekst} ({categorie})"
        delen.append(tekst)
    return "; ".join(delen)


# Dezelfde vorm die `slots._SLOT` invult; buiten deze vorm kan de host niets.
_SLOTNAAM = re.compile(r"[A-Z0-9_]+")


def _geoogste_feiten_tekst(feiten: dict | None) -> str | None:
    """Welke feiten de host al heeft opgehaald, als tekst voor de prompt.

    `tool_usage.md` verwijst voor de bedrijfsgegevens naar "STATUS VAN DE
    REGELTOETS" - zonder deze regel bevat dat blok alleen de uitkomsttekst
    (`voldoet_aan_voorwaarden`, `uitkomsten`) en geen enkel opgehaald feit,
    waardoor die verwijzing niet klopt. De namen komen 1-op-1 overeen met de
    plaatshouders uit `slots.md`, zodat het model ze meteen kan gebruiken in
    plaats van er zelf een tool voor te overwegen.
    """
    if not feiten:
        return None
    namen = ", ".join(f"{{{{{naam}}}}}" for naam in sorted(_bruikbare_slots(feiten)))
    if not namen:
        return None
    return f"Al opgehaald en met bron beschikbaar: {namen}."


def _bruikbare_slots(feiten: dict) -> list[str]:
    """De feitnamen die de host ook echt in een zin kan invullen.

    De feitenkaart is breder dan de slotlijst: `gebruikte_waarden` van de
    maatregelenwet levert ook de rekenvariabelen van de engine mee - `current`,
    `current.categorie`, `VIIaa`, `gemeente`, `is_glastuinbouwsector`. Werden
    die als plaatshouder aangeboden, dan ging het twee kanten op fout. Een naam
    met kleine letters valt buiten `slots._SLOT`, wordt dus niet ingevuld én
    niet als onopgelost gemeld: `{{gemeente}}` bleef letterlijk op het scherm
    staan. En een naam met een lijst erachter - de 28 categorieen, de
    maatregelenlijst - werd wél ingevuld, met de Python-weergave van die lijst.

    Twee eisen dus: de naam moet de slot-vorm hebben, en de waarde moet in een
    zin passen. De feitenkaart zelf blijft ongemoeid; die draagt die waarden
    terecht, want de regelloop voert ze als wetsparameter weer op.
    """
    return [
        naam
        for naam, feit in feiten.items()
        if _SLOTNAAM.fullmatch(naam)
        and not isinstance((feit or {}).get("waarde"), list | dict | tuple | set)
    ]


def _compose_regel_status(regel_status: dict | None, feiten: dict | None = None) -> str | None:
    """Bouw het blok dat vertelt wat de regelloop deze beurt al heeft bepaald.

    `regelloop.volg_regel` draait vóór het model de beurt ziet en haalt zelf op
    wat hij kan; dit is het enige kanaal waarlangs het model dat te weten komt
    — om toestemming vragen, de ondernemer een vraag stellen die de wet nodig
    heeft, of melden dat RegelRecht al een uitkomst gaf. Naar het model van
    `_compose_bronnen_status`: zelfde precedent, dezelfde redenering ("vertel
    het model wat de host al weet").

    De tekst bevat bewust GEEN interne veldnamen of wetpaden uit `reden` (die
    is voor de log, niet voor de prompt) — foutmeldingen komen uit een
    catalogus in gewone taal, niet uit een f-string met technische
    identifiers erin (zie `errors.py`).
    """
    if not regel_status:
        return None
    wacht_op = regel_status.get("wacht_op")
    if wacht_op == "toestemming":
        status = (
            "Voor het energieverbruik uit de Business Wallet is toestemming van "
            "de ondernemer nodig (PDR-008). Vraag daar EXPLICIET om voordat u die "
            "bron noemt of gebruikt, en wacht op een duidelijk antwoord."
        )
    elif wacht_op == "opgave":
        status = (
            "Er is een gegeven nodig dat alleen de ondernemer weet. Vraag dat via "
            "het formulier; dit is geen gegeven dat u zelf kunt opzoeken of "
            "aannemen."
        )
    elif wacht_op == "onbekend":
        status = (
            "De assistent kan dit op dit moment niet automatisch bepalen. Meld "
            "dat eerlijk aan de ondernemer in plaats van te gokken of de vraag "
            "over te slaan."
        )
    else:
        status = _regel_status_klaar_tekst(regel_status.get("resultaat") or {})
    maatregelen_tekst = _maatregelen_status_tekst(regel_status.get("maatregelen"))
    if maatregelen_tekst:
        status = f"{status} {maatregelen_tekst}"
    feiten_tekst = _geoogste_feiten_tekst(feiten)
    if feiten_tekst:
        status = f"{status} {feiten_tekst}"
    return _load("shared/regel_status.md").replace("{status}", status)


def compose_system_prompt(
    mode: str,
    has_tools: bool,
    bronnen_offline: list[str] | None = None,
    cli_transport: bool = False,
    regel_status: dict | None = None,
    feiten: dict | None = None,
    bronnen_uit: list[str] | None = None,
) -> str:
    """Assemble the system prompt from modular blocks.

    Args:
        mode: "vlam" or "claude".
        has_tools: Whether MCP tools are available.
        bronnen_offline: Sources that failed to start, by server name.
        bronnen_uit: Sources deliberately left out of this environment, by
            server name. Like `bronnen_offline` they drop the blocks and
            examples that lean on them, but the model is told to never
            mention them instead of reporting them as unavailable.
        cli_transport: True for the `cli:*` modes, which offer a smaller set of
            tools than the shared routing table describes.
        regel_status: What the rule loop (`regelloop.volg_regel`) already
            determined this turn, or None if it did not run (CLI transport).
        feiten: The facts harvested so far this conversation (`VLAMHost.feiten`),
            named in the "STATUS VAN DE REGELTOETS" block so `tool_usage.md`'s
            reference to it for company data is actually true.

    Returns:
        Complete system prompt string.
    """
    blocks: list[str] = []

    # 1. Identity (per model)
    blocks.append(_load(f"identity/{mode}.md"))

    # 2. Shared blocks (core consistency)
    blocks.append(_load("shared/tone.md"))
    blocks.append(_load("shared/reasoning.md"))
    blocks.append(_load("shared/format.md"))
    blocks.append(_load("shared/guardrails.md"))

    # 3. Tool instructions OR no-tools fallback
    status = _compose_bronnen_status(bronnen_offline or [], has_tools)
    uit = _compose_bronnen_uit(bronnen_uit or [])
    onbereikbaar = set(bronnen_offline or []) | set(bronnen_uit or [])
    if has_tools:
        # Vóór tool_usage: de slotregel geldt voor élk antwoord, ook voor
        # antwoorden die geen tool gebruiken maar wel een eerder feit noemen.
        blocks.append(_load("shared/slots.md"))
        blocks.append(_load("shared/tool_usage.md"))
        blocks.extend(_load_domain_blocks(onbereikbaar))
        if cli_transport:
            # De routeringstabel is gedeeld met het MCP-transport en noemt tools
            # die hier anders heten of ontbreken. Dat is een naamprobleem, geen
            # storing, dus het hoort in een eigen blok en niet in de
            # beschikbaarheidslijst.
            blocks.append(_load("shared/cli_transport.md"))
        regel = _compose_regel_status(regel_status, feiten)
        if regel:
            blocks.append(regel)  # wat de regelloop deze beurt al bepaalde
        if status:
            blocks.append(status)  # welke bronnen nu uitliggen
        if uit:
            blocks.append(uit)  # welke bronnen hier niet bestaan
    elif status:
        # Geen enkele tool én bronnen die hadden moeten draaien: eerlijk melden
        # dat het nu niet lukt, in plaats van op eigen kennis antwoorden.
        blocks.append(status)
    else:
        blocks.append(_load("shared/no_tools.md"))

    # 4. Model-specific hints (optional fine-tuning per model)
    hint = _load_if_exists(f"model_specific/{mode}_hints.md")
    if hint:
        blocks.append(hint)

    # 5. Few-shot examples (strongest consistency signal)
    examples = _load_examples(has_tools, bronnen_offline or [], bronnen_uit or [])
    if examples:
        blocks.append("Hieronder volgen voorbeelden van goede antwoorden:")
        blocks.extend(examples)

    return SEPARATOR.join(blocks)

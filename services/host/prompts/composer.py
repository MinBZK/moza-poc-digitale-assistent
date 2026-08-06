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


def _load_domain_blocks(bronnen_offline: list[str]) -> list[str]:
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
    onbereikbaar = set(bronnen_offline)
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


def _load_examples(has_tools: bool, bronnen_offline: list[str]) -> list[str]:
    """Load the few-shot example blocks that still make sense right now.

    Examples are the strongest steering signal in this prompt, which cuts both
    ways: an example that calls `koop__zoek_regelgeving` — or merely offers to —
    while KOOP is down demonstrates exactly what the availability block just
    forbade. Drop any example that leans on a source the model cannot reach.
    """
    if not EXAMPLES_DIR.exists():
        return []
    onbereikbaar = set(bronnen_offline)
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
        kwijt = _optionele_bronnen(tekst) & onbereikbaar
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


def compose_system_prompt(
    mode: str,
    has_tools: bool,
    bronnen_offline: list[str] | None = None,
    cli_transport: bool = False,
) -> str:
    """Assemble the system prompt from modular blocks.

    Args:
        mode: "vlam" or "claude".
        has_tools: Whether MCP tools are available.
        bronnen_offline: Sources that failed to start, by server name.
        cli_transport: True for the `cli:*` modes, which offer a smaller set of
            tools than the shared routing table describes.

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
    if has_tools:
        blocks.append(_load("shared/tool_usage.md"))
        blocks.extend(_load_domain_blocks(bronnen_offline or []))
        if cli_transport:
            # De routeringstabel is gedeeld met het MCP-transport en noemt tools
            # die hier anders heten of ontbreken. Dat is een naamprobleem, geen
            # storing, dus het hoort in een eigen blok en niet in de
            # beschikbaarheidslijst.
            blocks.append(_load("shared/cli_transport.md"))
        if status:
            blocks.append(status)  # welke bronnen nu uitliggen
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
    examples = _load_examples(has_tools, bronnen_offline or [])
    if examples:
        blocks.append("Hieronder volgen voorbeelden van goede antwoorden:")
        blocks.extend(examples)

    return SEPARATOR.join(blocks)

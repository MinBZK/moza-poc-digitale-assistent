"""De regel stuurt, de host haalt op.

`regelrecht__execute_law` declareert laag voor laag wat hij mist
(`ontbrekende_gegevens`). Deze lus haalt daarvan op wat hij zelf kan via
`regelrouting.route()` en stopt zodra iets toestemming vergt (PDR-008), alleen
de ondernemer het weet, of het gevraagde veld onbekend is. Het model orkestreert
hier niets meer - het volgt straks alleen wat de lus teruggeeft (taak 4).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import regelrouting
from feiten import feiten_uit_tool

CallTool = Callable[[str, dict], Awaitable[str]]

# Ruim boven de drie lagen die de informatieplicht kent (KvK, Business Wallet,
# opgave). Zonder grens blijft een bron die het gevraagde veld niet levert de
# wet erom laten vragen en draait de lus rond.
MAX_RONDES = 5


@dataclass(frozen=True)
class Uitkomst:
    """Waar de lus is gestopt en waarom.

    `wacht_op` is None als de regel klaar is; anders "toestemming", "opgave" of
    "onbekend". De aanroeper vertaalt dat naar wat het model moet doen.
    """

    klaar: bool
    resultaat: dict | None
    wacht_op: str | None
    reden: str


def _parameters_uit_feiten(feiten: dict) -> dict:
    """Vertaal de feitenkaart terug naar regel-parameternamen.

    De feitenkaart kent `GAS_M3`, de regel vraagt `JAARLIJKS_GASVERBRUIK_M3`.
    `regelrouting.HERKOMST` legt die vertaling al vast (`feitnaam`); hier wordt
    hem in de andere richting gebruikt.
    """
    parameters = {}
    for veldnaam, veld in regelrouting.HERKOMST.items():
        sleutel = veld.feitnaam or veldnaam
        feit = feiten.get(sleutel)
        if feit is not None:
            parameters[veldnaam] = feit["waarde"]
    return parameters


async def volg_regel(
    law: str,
    service: str,
    feiten: dict,
    call_tool: CallTool,
    toestemming: bool,
) -> Uitkomst:
    """Voer `law` uit en haal ontbrekende gegevens op zolang de lus dat zelf kan."""
    feiten = dict(feiten)

    for _ in range(MAX_RONDES):
        parameters = _parameters_uit_feiten(feiten)
        ruw = await call_tool(
            "regelrecht__execute_law",
            {"law": law, "service": service, "parameters": parameters},
        )
        data = json.loads(ruw).get("data") or {}

        if data.get("voldoet_aan_voorwaarden"):
            return Uitkomst(klaar=True, resultaat=data, wacht_op=None, reden="")

        ontbrekend = data.get("ontbrekende_gegevens") or []
        if not ontbrekend:
            if not data.get("missing_required", True):
                # De engine heeft alles getoetst en niets ontbreekt: dit is een
                # definitieve negatieve uitkomst ("de verplichting geldt
                # niet"), geen onbekende toestand. Zonder `missing_required`
                # (oudere servervorm) blijft de voorzichtige aanname staan:
                # mogelijk mist er nog iets.
                return Uitkomst(klaar=True, resultaat=data, wacht_op=None, reden="")
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="onbekend",
                reden=f"{law} voldoet niet en geeft geen ontbrekende gegevens op.",
            )

        veldnaam = ontbrekend[0]["naam"]
        veld = regelrouting.route(veldnaam)
        if veld is None:
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="onbekend",
                reden=f"{veldnaam} heeft geen bekende herkomst.",
            )
        if veld.toestemming and not toestemming:
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="toestemming",
                reden=f"{veldnaam} komt uit {veld.bron}; dat vergt akkoord van de ondernemer.",
            )
        if veld.tool is None:
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="opgave",
                reden=f"{veldnaam} weet alleen de ondernemer; dat hoort uit het formulier te komen.",
            )

        tool_ruw = await call_tool(veld.tool, {})
        feiten.update(feiten_uit_tool(veld.tool, tool_ruw))

    return Uitkomst(
        klaar=False,
        resultaat=None,
        wacht_op=None,
        reden=(
            f"{law} vraagt na {MAX_RONDES} rondes nog steeds om hetzelfde gegeven; "
            "gestopt om een oneindige lus te voorkomen."
        ),
    )

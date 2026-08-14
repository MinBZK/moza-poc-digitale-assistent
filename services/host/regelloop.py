"""De regel stuurt, de host haalt op.

`regelrecht__execute_law` declareert laag voor laag wat hij mist
(`ontbrekende_gegevens`). Deze lus haalt daarvan op wat hij zelf kan via
`regelrouting.route()` en stopt zodra iets toestemming vergt (PDR-008), alleen
de ondernemer het weet, het gevraagde veld onbekend is, of een ronde geen
nieuw feit opleverde (storing, lege BAG). Het model orkestreert hier niets
meer - het volgt straks alleen wat de lus teruggeeft (taak 4).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import regelrouting
from feiten import feiten_uit_tool, samenvoegen

CallTool = Callable[[str, dict], Awaitable[str]]

# Vangnet voor het geval élke ronde wél een nieuw feit oplevert maar de wet
# nooit voldaan raakt: de eigenlijke bescherming tegen een bron die niets
# oplevert zit in de voortgangscontrole verderop (geen nieuw feit -> direct
# stoppen, ná één aanroep in plaats van vijf).
MAX_RONDES = 5


@dataclass(frozen=True)
class Uitkomst:
    """Waar de lus is gestopt en waarom.

    `wacht_op` is None als de regel klaar is (`klaar=True`) - maar ook als de
    lus vastliep zonder voortgang (rondegrens bereikt, of een bron leverde het
    gevraagde veld niet): dan is `klaar=False` én `wacht_op=None`, een derde
    toestand naast de drie genoemde waarden. De aanroeper (`_regel_status_dict`
    in `vlam_host.py`) vertaalt die combinatie naar "onbekend".
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

    Een feit met `soort == "echo"` telt niet mee: dat is alleen wat WIJ als
    invoer instuurden, teruggekaatst door RegelRecht - nooit een eigen
    waarneming. Zou dit meetellen, dan wordt een `overrides`-waarde die het
    model verzint een feit dat de host de volgende ronde zelf weer als
    wetsinvoer aanbiedt, en komt een verzonnen getal terug als "uit
    RegelRecht" zonder wallet, zonder toestemming, zonder spoor.
    """
    parameters = {}
    for veldnaam, veld in regelrouting.HERKOMST.items():
        sleutel = veld.feitnaam or veldnaam
        feit = feiten.get(sleutel)
        if feit is not None and feit.get("soort") != "echo":
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

        sleutels_voor = set(feiten)
        tool_ruw = await call_tool(veld.tool, {})
        samenvoegen(feiten, feiten_uit_tool(veld.tool, tool_ruw))
        if set(feiten) == sleutels_voor:
            # Deze ronde leverde geen enkel nieuw feit op: `veld.bron` gaf
            # niet het gevraagde veld terug (storing, lege BAG). Nog vier
            # rondes dezelfde twee aanroepen herhalen - elk met een eigen
            # timeout - helpt dan niet; de volgende ronde zou identiek
            # verlopen. Direct stoppen in plaats van MAX_RONDES vol te maken.
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op=None,
                reden=f"{veld.bron} leverde {veldnaam} niet op; gestopt zonder voortgang.",
            )

    return Uitkomst(
        klaar=False,
        resultaat=None,
        wacht_op=None,
        reden=(
            f"{law} vraagt na {MAX_RONDES} rondes nog steeds om hetzelfde gegeven; "
            "gestopt om een oneindige lus te voorkomen."
        ),
    )

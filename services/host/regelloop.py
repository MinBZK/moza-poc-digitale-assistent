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

    `velden` staat alleen gevuld bij `wacht_op == "opgave"`: de velden die de
    ondernemer moet aanleveren, met de beschrijving die de wet er zelf bij geeft.
    De host maakt daar het formulier van, zodat de vraagtekst uit de wet komt en
    niet uit de frontend of het model.
    """

    klaar: bool
    resultaat: dict | None
    wacht_op: str | None
    reden: str
    velden: tuple[dict, ...] = ()
    # Alleen gevuld bij `wacht_op == "toestemming"`: welke bron akkoord vergt.
    # `bron` is het label voor de respondent ("KvK Handelsregister"), `scope`
    # de sleutel waaronder de host het akkoord vastlegt ("kvk"). Toestemming
    # geldt per bron, niet per gesprek: een akkoord voor het Handelsregister
    # zet niet stilzwijgend ook de Business Wallet open.
    bron: str | None = None
    scope: str | None = None


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
    toestemming: frozenset[str] | set[str],
    beschikbare_tools: set[str] | None = None,
) -> Uitkomst:
    """Voer `law` uit en haal ontbrekende gegevens op zolang de lus dat zelf kan.

    `toestemming` is de verzameling bronscopes waarvoor de ondernemer akkoord
    heeft gegeven ("kvk", "netbeheerder"). Per bron, niet als één vlag: het
    deelverzoek benoemt een bron, dus het akkoord hoort niet breder te zijn
    dan wat er gevraagd is.
    """
    feiten = dict(feiten)

    for _ in range(MAX_RONDES):
        parameters = _parameters_uit_feiten(feiten)
        ruw = await call_tool(
            "regelrecht__execute_law",
            {"law": law, "service": service, "parameters": parameters},
        )
        try:
            data = json.loads(ruw).get("data") or {}
        except (ValueError, AttributeError):
            data = None
        if not isinstance(data, dict):
            # Geen JSON-object: de bron gaf iets terug dat de lus niet kan
            # lezen. Doorgaan zou hetzelfde antwoord nog vier keer ophalen;
            # stoppen met een reden laat in de log zien wat er misging.
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op=None,
                reden=f"{law}: RegelRecht gaf een onleesbaar antwoord; gestopt.",
            )

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
        # Bestaat de bron niet in deze omgeving - de wallet staat uit voor dit
        # onderzoek, of de server kwam niet op - dan is toestemming vragen
        # zinloos en verwarrend: de ondernemer zegt ja voor iets dat er niet is,
        # de aanroep faalt alsnog, en pas daarna komt de vraag die meteen
        # gesteld had kunnen worden. Weet hij het antwoord zelf, dan vragen we
        # het meteen.
        bron_ontbreekt = (
            beschikbare_tools is not None
            and veld.tool is not None
            and veld.tool not in beschikbare_tools
        )
        if bron_ontbreekt and (veld.zelf_op_te_geven or veld.corrigeerbaar):
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="opgave",
                reden=f"{veld.bron} is hier niet beschikbaar; de ondernemer geeft {veldnaam} zelf op.",
                velden=tuple(
                    {"naam": item["naam"], "beschrijving": item.get("beschrijving", "")}
                    for item in ontbrekend
                    if (route := regelrouting.route(item["naam"])) is not None
                    and (
                        route.tool is None
                        or route.zelf_op_te_geven
                        or route.corrigeerbaar
                    )
                ),
            )
        scope = (veld.tool or "").split("__", 1)[0] or None
        if veld.toestemming and scope not in toestemming:
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="toestemming",
                reden=f"{veldnaam} komt uit {veld.bron}; dat vergt akkoord van de ondernemer.",
                bron=veld.bron,
                scope=scope,
            )
        if veld.tool is None:
            # Alle openstaande velden die de ondernemer moet opgeven, niet alleen
            # het eerste: één formulier met vier vragen is beter dan vier beurten
            # met elk één vraag, en de lus zou na elk antwoord toch weer op de
            # volgende stuiten. De beschrijving komt van de wet zelf - dat is de
            # vraagtekst zoals de wetgever hem stelt.
            openstaand = tuple(
                {"naam": item["naam"], "beschrijving": item.get("beschrijving", "")}
                for item in ontbrekend
                if (route := regelrouting.route(item["naam"])) is not None
                and route.tool is None
            )
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="opgave",
                reden=f"{veldnaam} weet alleen de ondernemer; dat hoort uit het formulier te komen.",
                velden=openstaand,
            )

        # Voortgang is niet "er kwam een sleutel bij" maar "de bron leverde het
        # veld waarvoor we hem aanriepen". Op de sleutelverzameling meten ging
        # twee kanten op fout. Een wallet die alleen elektriciteit teruggeeft
        # terwijl de regel om gas vroeg leverde wél nieuwe sleutels (peiljaar,
        # netbeheerder), dus ging de lus door en raadpleegde dezelfde wallet nog
        # een keer - voor de ondernemer een tweede deelverzoek voor gegevens die
        # hij net gedeeld heeft. En een attestatie die een bestaand echofeit
        # overschreef leverde géén nieuwe sleutel, waarna de lus "onbekend"
        # meldde terwijl het antwoord er net was.
        #
        # `_parameters_uit_feiten` is hier de juiste maat: die zegt welke feiten
        # als wetsinvoer kunnen dienen, en negeert daarbij echo's.
        tool_ruw = await call_tool(veld.tool, {})
        samenvoegen(feiten, feiten_uit_tool(veld.tool, tool_ruw))
        geen_voortgang = veldnaam not in _parameters_uit_feiten(feiten)
        # Levert de bron het gevraagde veld niet, dan is de ondernemer soms nog
        # een weg: bij een afleiding van ons (`corrigeerbaar`) weet hij het
        # beter, en bij een bron die hij niet wil of kan raadplegen
        # (`zelf_op_te_geven`) weet hij het gewoon zelf. Zonder die uitweg loopt
        # de keten dood op een bron die er niet is - een uitgeschakelde wallet,
        # een storing, een ontbrekende credential - en komt hij niet tot een
        # rapportage.
        if geen_voortgang and (veld.corrigeerbaar or veld.zelf_op_te_geven):
            # De bron leverde het niet, maar dit veld mág de ondernemer zeggen:
            # het is een afleiding van ons uit een registratie, geen waarneming
            # van die registratie zelf. Zonder deze uitweg loopt een bedrijf
            # zonder de benodigde inschrijving vast op "onbekend" terwijl de
            # ondernemer het antwoord gewoon weet.
            return Uitkomst(
                klaar=False,
                resultaat=None,
                wacht_op="opgave",
                reden=f"{veld.bron} leverde {veldnaam} niet op; de ondernemer kan het zelf opgeven.",
                velden=({"naam": veldnaam, "beschrijving": ontbrekend[0].get("beschrijving", "")},),
            )
        if geen_voortgang:
            # Deze ronde leverde geen bruikbare wetsinvoer op: `veld.bron` gaf
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

"""De ondernemer mag zijn verbruik zelf aanleveren.

Weigert hij de Business Wallet, dan stopte de keten. Zijn getallen kwamen via het
model bij RegelRecht terecht en kaatsten terug als `echo` - en een echo negeert
`_parameters_uit_feiten` bewust, want anders komt een door het model verzonnen
getal terug als "uit RegelRecht". Gevolg: de host kwam nooit voorbij "wacht op
toestemming", de maatregelenregel draaide niet, en er ontstond geen zaak. Wie
niet deelde, kwam niet tot een rapportage.

Een opgave is iets anders dan een echo. Ze benoemt zichzelf: in het rapport en in
de zaak staat "opgegeven door u" naast "afgegeven door uw netbeheerder". Verzint
het model een getal, dan ziet de ondernemer het staan als het zijne en kan hij
het weerspreken - bij een echo stond er "uit RegelRecht" en zag niemand het.
"""

import regelrouting
from regelloop import _parameters_uit_feiten
from vlam_host import _opgaven_als_feiten

ELEKTRA = "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"
GAS = "JAARLIJKS_GASVERBRUIK_M3"


def test_de_routering_staat_een_eigen_opgave_toe():
    for naam in (ELEKTRA, GAS):
        veld = regelrouting.route(naam)
        assert veld.zelf_op_te_geven, f"{naam} kan de ondernemer niet zelf opgeven"


def test_de_wallet_blijft_de_eerste_bron():
    """Zelf opgeven is de uitweg, niet de hoofdroute.

    Het veld houdt zijn attestatie-herkomst en zijn toestemmingsplicht: de host
    haalt het nog steeds bij de Business Wallet op als de ondernemer akkoord
    gaat.
    """
    veld = regelrouting.route(ELEKTRA)
    assert veld.soort == "attestatie"
    assert veld.toestemming is True
    assert veld.tool == "netbeheerder__verbruik"


def test_een_opgegeven_verbruik_landt_als_opgave():
    feiten = _opgaven_als_feiten({ELEKTRA: 420000, GAS: 140000})
    assert feiten["ELEKTRICITEIT_KWH"]["waarde"] == 420000
    assert feiten["ELEKTRICITEIT_KWH"]["soort"] == "opgave"
    assert "ondernemer" in feiten["ELEKTRICITEIT_KWH"]["bron"]


def test_een_opgegeven_verbruik_is_bruikbaar_als_wetsinvoer():
    """De kern: hierop liep het vast. Een echo telt niet mee, een opgave wel."""
    feiten = _opgaven_als_feiten({ELEKTRA: 420000, GAS: 140000})
    parameters = _parameters_uit_feiten(feiten)
    assert parameters[ELEKTRA] == 420000
    assert parameters[GAS] == 140000


def test_een_echo_blijft_geweerd():
    """De bescherming die er stond mag niet sneuvelen met deze wijziging."""
    feiten = {
        "ELEKTRICITEIT_KWH": {
            "waarde": 999999,
            "bron": "RegelRecht (doorgegeven invoer)",
            "soort": "echo",
        }
    }
    assert ELEKTRA not in _parameters_uit_feiten(feiten)


def test_een_registratie_blijft_dicht_voor_de_client():
    """`opgaven` is een publiek HTTP-veld; niet elk veld mag eruit gevuld worden.

    De woonfunctie komt uit het Handelsregister en is geen kwestie van zeggen.
    """
    assert _opgaven_als_feiten({"IS_WOONFUNCTIE": True}) == {}


# --- De lus vraagt het zelf, als de bron niets levert -------------------------


async def test_lus_vraagt_de_ondernemer_als_de_wallet_niets_levert():
    """Zonder deze uitweg loopt de keten dood op een bron die er niet is.

    Levert de Business Wallet niets - uitgeschakeld voor dit onderzoek, een
    storing, of geen credential - dan stopte de lus met `wacht_op=None`, wat
    naar buiten "onbekend" heet. De ondernemer weet zijn jaarverbruik gewoon;
    hem vragen is beter dan afhaken.
    """
    import json

    from regelloop import volg_regel

    async def call_tool(naam, argumenten):
        if naam == "regelrecht__execute_law":
            return json.dumps(
                {"data": {"ontbrekende_gegevens": [{"naam": ELEKTRA, "beschrijving": "Jaarverbruik elektriciteit"}]}}
            )
        if naam == "netbeheerder__verbruik":
            return json.dumps({"data": {"beschikbaar": False}})
        raise AssertionError(naam)

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=True,
    )
    assert uit.wacht_op == "opgave", f"lus stopte op {uit.wacht_op!r}: {uit.reden}"
    assert any(v["naam"] == ELEKTRA for v in uit.velden)


async def test_geen_deelverzoek_voor_een_bron_die_er_niet_is():
    """Staat de wallet uit, dan is toestemming vragen zinloos en verwarrend.

    De toestemmingscontrole stond vóór de aanroep, dus een uitgeschakelde
    netbeheerder leverde eerst een deelverzoek op voor een bron die niet
    bestaat. De ondernemer zegt ja, de aanroep faalt alsnog, en pas daarna komt
    de vraag die meteen gesteld had kunnen worden.
    """
    import json

    from regelloop import volg_regel

    async def call_tool(naam, argumenten):
        if naam == "regelrecht__execute_law":
            return json.dumps(
                {"data": {"ontbrekende_gegevens": [{"naam": ELEKTRA, "beschrijving": "Jaarverbruik"}]}}
            )
        raise AssertionError(f"{naam} had niet aangeroepen mogen worden")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
        beschikbare_tools=set(),
    )
    assert uit.wacht_op == "opgave", f"kreeg {uit.wacht_op!r}: {uit.reden}"
    assert any(v["naam"] == ELEKTRA for v in uit.velden)


async def test_met_wallet_blijft_toestemming_gewoon_gelden():
    """De tegenproef: is de bron er wel, dan eerst akkoord vragen (PDR-008)."""
    import json

    from regelloop import volg_regel

    async def call_tool(naam, argumenten):
        if naam == "regelrecht__execute_law":
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": ELEKTRA}]}})
        raise AssertionError("de wallet mag niet geraadpleegd worden zonder akkoord")

    uit = await volg_regel(
        law="omgevingswet/energiebesparing/informatieplicht",
        service="RVO",
        feiten={},
        call_tool=call_tool,
        toestemming=False,
        beschikbare_tools={"netbeheerder__verbruik", "kvk__mijn_bedrijf"},
    )
    assert uit.wacht_op == "toestemming"

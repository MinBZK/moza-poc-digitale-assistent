"""Toestemming geldt per bron, en volgt altijd op een deelverzoek.

Het gebruikersonderzoek wil dat de assistent óók om akkoord vraagt voordat het
Handelsregister wordt geraadpleegd. Dat kan niet met één vlag per gesprek: dan
zou een "Delen" voor de KvK stilzwijgend ook de Business Wallet openzetten -
precies het soort verrassing dat een vertrouwensonderzoek niet hebben wil.

Drie afspraken, elk hier vastgelegd:
1. het akkoord hoort bij de bron waar het laatste deelverzoek om vroeg;
2. een `toestemming: true` zonder openstaand deelverzoek legt niets vast
   (akkoord volgt op een vraag, het is geen blanco cheque - PDR-008);
3. de poort weigert elke tool van een toestemmingsplichtige bron zolang die
   bron geen akkoord heeft, wie de aanroep ook initieert.
"""

import json

import pytest

from vlam_host import TOESTEMMINGSPLICHTIGE_SCOPES, VLAMHost

KVK = "62345681"
CONV = "62345681|sessie-a|claude"


@pytest.fixture
def host():
    return VLAMHost()


def test_de_scopes_komen_uit_de_routeringstabel():
    """Eén bron van waarheid: wie een veld toestemmingsplichtig maakt in de
    tabel, heeft daarmee ook de poort voor die bron aangezet."""
    assert TOESTEMMINGSPLICHTIGE_SCOPES == {"kvk", "netbeheerder"}


def test_akkoord_landt_op_de_gevraagde_bron_en_alleen_daar(host):
    host._toestemming_gevraagd[CONV] = "kvk"
    host._leg_toestemming_vast(CONV)
    assert host.toestemming[CONV] == {"kvk"}
    assert CONV not in host._toestemming_gevraagd, "het verzoek is beantwoord"


def test_akkoord_zonder_openstaand_verzoek_legt_niets_vast(host):
    host._leg_toestemming_vast(CONV)
    assert host.toestemming.get(CONV, set()) == set()


def test_tweede_akkoord_komt_naast_het_eerste(host):
    """De respondent zegt twee keer ja, tegen twee verschillende bronnen."""
    host._toestemming_gevraagd[CONV] = "kvk"
    host._leg_toestemming_vast(CONV)
    host._toestemming_gevraagd[CONV] = "netbeheerder"
    host._leg_toestemming_vast(CONV)
    assert host.toestemming[CONV] == {"kvk", "netbeheerder"}


def test_nieuw_gesprek_begint_zonder_openstaand_verzoek(host):
    host._toestemming_gevraagd[CONV] = "kvk"
    host.clear_session(KVK, "sessie-a")
    assert CONV not in host._toestemming_gevraagd


async def _poort(host, tool_key):
    async def aanroep(_tool, _args):
        return json.dumps({"data": {}})

    return await host._bron_aanroep_gated(aanroep, tool_key, {}, CONV)


@pytest.mark.parametrize(
    "tool_key",
    ["kvk__mijn_bedrijf", "kvk__eigenaar", "kvk__vestigingen", "netbeheerder__verbruik"],
)
async def test_de_poort_weigert_elke_plichtige_tool_zonder_akkoord(host, tool_key):
    """Het akkoord gaat over de bron, niet over één endpoint: ook kvk__eigenaar
    en kvk__vestigingen wachten op het akkoord voor het Handelsregister."""
    _resultaat, fout, aangeroepen = await _poort(host, tool_key)
    assert aangeroepen is False
    assert fout is not None and fout.code == "TOESTEMMING_VEREIST"


async def test_akkoord_voor_de_ene_bron_opent_de_andere_niet(host):
    host.toestemming[CONV] = {"kvk"}
    _resultaat, fout, aangeroepen = await _poort(host, "netbeheerder__verbruik")
    assert aangeroepen is False
    _resultaat, fout, aangeroepen = await _poort(host, "kvk__mijn_bedrijf")
    assert aangeroepen is True


async def test_niet_plichtige_bronnen_gaan_gewoon_door(host):
    """RegelRecht, KOOP en RVO dragen geen persoonsgegevens uit een register;
    daar hoort geen deelverzoek voor te komen."""
    for tool_key in ("regelrecht__execute_law", "koop__zoek_regelgeving", "rvo__zoek_regeling"):
        _resultaat, _fout, aangeroepen = await _poort(host, tool_key)
        assert aangeroepen is True, tool_key

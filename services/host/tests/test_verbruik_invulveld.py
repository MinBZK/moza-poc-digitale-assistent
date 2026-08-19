"""Met de wallet uit levert de ondernemer zijn verbruik zelf aan - als getal.

Twee dingen gingen daar mis. Het formulier bood elk niet-categorieveld aan als
ja/nee-vraag, ook "Jaarlijks elektriciteitsverbruik in kWh" - waarop ja noch
nee een antwoord is. En wat de ondernemer vervolgens typt is een string in
Nederlandse notatie: gemeten tegen de echte engine leest die "250.000" als
tweehonderdvijftig, waarmee de plicht onterecht vervalt. Beide horen bij de
host thuis: het formulier zegt wat voor invoer het wil, en de invoer wordt
genormaliseerd vóórdat hij de wet in gaat.
"""

import pytest

import regelrouting
from regelloop import Uitkomst
from vlam_host import _als_getal, _opgaven_als_feiten, _vraag_uit_uitkomst


def test_verbruik_is_een_invulveld_geen_ja_nee_vraag():
    uitkomst = Uitkomst(
        klaar=False, resultaat=None, wacht_op="opgave", reden="",
        velden=(
            {"naam": "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH", "beschrijving": "Elektriciteit (kWh)"},
            {"naam": "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS", "beschrijving": "Teelt in gebouw?"},
        ),
    )
    vraag = _vraag_uit_uitkomst(uitkomst, {}, {})
    per_naam = {v["naam"]: v for v in vraag["velden"]}
    verbruik = per_naam["JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH"]
    assert verbruik["type"] == "getal"
    assert "opties" not in verbruik, "opties maken er in de frontend ja/nee-knoppen van"
    # De echte keuzevraag blijft gewoon een keuzevraag.
    assert per_naam["TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS"]["opties"] == ["Ja", "Nee"]


@pytest.mark.parametrize(
    "invoer, verwacht",
    [
        ("250000", 250000),
        ("250.000", 250000),   # Nederlandse duizendtallen - engine las hier 250
        ("250.000,5", 250000.5),
        ("60.000", 60000),
        ("1.5", 1.5),
        (420000, 420000),
    ],
)
def test_nederlandse_notatie_wordt_genormaliseerd(invoer, verwacht):
    assert _als_getal(invoer) == verwacht


@pytest.mark.parametrize("invoer", ["abc", "", None, True])
def test_onleesbare_invoer_wordt_geen_stil_verkeerd_getal(invoer):
    assert _als_getal(invoer) is None


def test_opgave_van_verbruik_landt_genormaliseerd_in_de_feitenkaart():
    feiten = _opgaven_als_feiten({"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": "250.000"})
    assert feiten["ELEKTRICITEIT_KWH"]["waarde"] == 250000


def test_onleesbaar_verbruik_blijft_open_in_plaats_van_fout_door_te_gaan():
    feiten = _opgaven_als_feiten({"JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH": "veel"})
    assert "ELEKTRICITEIT_KWH" not in feiten


def test_alleen_getalvelden_worden_genormaliseerd():
    """Een keuzeveld dat toevallig op een getal lijkt blijft ongemoeid."""
    assert regelrouting.route("AANWEZIGE_CATEGORIEEN").invoer == "keuze"
    feiten = _opgaven_als_feiten({"AANWEZIGE_CATEGORIEEN": ["Binnenverlichting"]})
    assert feiten["AANWEZIGE_CATEGORIEEN"]["waarde"] == ["Binnenverlichting"]

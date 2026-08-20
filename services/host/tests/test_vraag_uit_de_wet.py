"""Het formulier komt uit de wet, niet uit de frontend.

De erkende maatregelenlijst kent 28 categorieën, verdeeld over drie onderdelen.
Zou de frontend die lijst zelf kennen, dan is er een vierde kopie van
regelkennis die kan gaan afwijken - naast de wet, de host-fallback en de
inmiddels verwijderde EML-kopie in de MCP-server. De host bouwt het formulier
daarom uit `ontbrekende_gegevens` (veldnamen en vraagteksten) en `CATEGORIEEN`
(de keuzelijst), allebei uit de wet.
"""

import pytest

from regelloop import Uitkomst
from vlam_host import _vraag_uit_uitkomst

CATEGORIEEN = [
    {"categorie": "Binnenverlichting", "onderdeel": "Gebouwen", "lijsten": ["algemeen"]},
    {"categorie": "Tuinbouwkassen", "onderdeel": "Gebouwen", "lijsten": ["glastuinbouw"]},
    {"categorie": "Perslucht", "onderdeel": "Faciliteiten", "lijsten": ["algemeen"]},
    {"categorie": "Glastuinbouw", "onderdeel": "Processen", "lijsten": ["glastuinbouw"]},
]

VELDEN = (
    {
        "naam": "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS",
        "beschrijving": "Teelt het bedrijf gewassen in een gebouw dat geen kas is?",
    },
    {
        "naam": "AANWEZIGE_CATEGORIEEN",
        "beschrijving": "De categorieen uit de erkende maatregelenlijst die bij het bedrijf voorkomen.",
    },
)


def _wacht_op_opgave(velden=VELDEN):
    return Uitkomst(klaar=False, resultaat=None, wacht_op="opgave", reden="", velden=velden)


def test_vraagteksten_komen_uit_de_wet():
    """De beschrijving bij de parameter is de vraag zoals de wetgever hem stelt."""
    vraag = _vraag_uit_uitkomst(_wacht_op_opgave(), {"CATEGORIEEN": CATEGORIEEN})
    per_naam = {v["naam"]: v for v in vraag["velden"]}
    assert per_naam["TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS"]["label"] == (
        "Teelt het bedrijf gewassen in een gebouw dat geen kas is?"
    )
    assert per_naam["TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS"]["type"] == "radio"
    assert per_naam["TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS"]["opties"] == ["Ja", "Nee"]


def test_categorieen_gaan_gegroepeerd_per_onderdeel_mee():
    """Getrapt: eerst het onderdeel, dan de categorieën die daaronder vallen."""
    vraag = _vraag_uit_uitkomst(_wacht_op_opgave(), {"CATEGORIEEN": CATEGORIEEN})
    veld = next(v for v in vraag["velden"] if v["naam"] == "AANWEZIGE_CATEGORIEEN")
    assert veld["type"] == "categorieen"
    groepen = {g["onderdeel"]: g["opties"] for g in veld["groepen"]}
    assert groepen == {
        "Faciliteiten": ["Perslucht"],
        "Gebouwen": ["Binnenverlichting", "Tuinbouwkassen"],
        "Processen": ["Glastuinbouw"],
    }


def test_onderdelen_staan_in_een_vaste_volgorde():
    """Anders wisselt het formulier van vorm tussen twee gesprekken."""
    vraag = _vraag_uit_uitkomst(_wacht_op_opgave(), {"CATEGORIEEN": CATEGORIEEN})
    veld = next(v for v in vraag["velden"] if v["naam"] == "AANWEZIGE_CATEGORIEEN")
    assert [g["onderdeel"] for g in veld["groepen"]] == ["Faciliteiten", "Gebouwen", "Processen"]


def test_zonder_categorieen_uit_de_wet_wordt_de_categorievraag_vrije_invoer():
    """Geen zelfbedachte keuzelijst - maar de vraag weglaten bleek erger: het
    model somt de categorieen dan in proza op en de respondent typt los in
    de chat, buiten het formulier om (op de onderzoeksomgeving gebeurd)."""
    vraag = _vraag_uit_uitkomst(_wacht_op_opgave(), {})
    per_naam = {v["naam"]: v for v in vraag["velden"]}
    assert set(per_naam) == {"TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS", "AANWEZIGE_CATEGORIEEN"}
    assert per_naam["AANWEZIGE_CATEGORIEEN"]["type"] == "tekst"
    assert "groepen" not in per_naam["AANWEZIGE_CATEGORIEEN"]


def test_ook_met_alleen_de_categorievraag_komt_er_een_formulier():
    """Voorheen viel het formulier dan helemaal weg; zie hierboven waarom niet."""
    alleen_categorieen = ({"naam": "AANWEZIGE_CATEGORIEEN", "beschrijving": "x"},)
    vraag = _vraag_uit_uitkomst(_wacht_op_opgave(alleen_categorieen), None)
    assert vraag is not None
    assert vraag["velden"][0]["type"] == "tekst"


def test_veld_zonder_beschrijving_valt_terug_op_de_naam():
    """Een wet zonder description mag geen leeg label opleveren."""
    vraag = _vraag_uit_uitkomst(
        _wacht_op_opgave(({"naam": "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF", "beschrijving": ""},)),
        {"CATEGORIEEN": CATEGORIEEN},
    )
    assert vraag["velden"][0]["label"] == "MAAKT_GEBRUIK_VAN_VERLAAGD_ENERGIEBELASTINGTARIEF"


def test_rommel_in_de_categorielijst_wordt_overgeslagen():
    """Een kapot element mag de andere categorieën niet meenemen in zijn val."""
    vraag = _vraag_uit_uitkomst(
        _wacht_op_opgave(),
        {"CATEGORIEEN": ["niet een dict", {"categorie": "Perslucht"}, CATEGORIEEN[0]]},
    )
    veld = next(v for v in vraag["velden"] if v["naam"] == "AANWEZIGE_CATEGORIEEN")
    assert {g["onderdeel"]: g["opties"] for g in veld["groepen"]} == {"Gebouwen": ["Binnenverlichting"]}


def test_dubbele_categorie_komt_er_maar_een_keer_in():
    """Een categorie kan in beide bijlagen staan; de ondernemer ziet hem één keer."""
    dubbel = [CATEGORIEEN[0], dict(CATEGORIEEN[0])]
    vraag = _vraag_uit_uitkomst(_wacht_op_opgave(), {"CATEGORIEEN": dubbel})
    veld = next(v for v in vraag["velden"] if v["naam"] == "AANWEZIGE_CATEGORIEEN")
    assert veld["groepen"] == [{"onderdeel": "Gebouwen", "opties": ["Binnenverlichting"]}]


@pytest.mark.parametrize("wacht_op", ["toestemming", "onbekend", None])
def test_alleen_bij_een_opgave_hoort_een_formulier(wacht_op):
    """Wacht de regel op toestemming, dan is de vraag "mag ik de bron raadplegen",
    en geen formulier over installaties."""
    uitkomst = Uitkomst(klaar=False, resultaat=None, wacht_op=wacht_op, reden="", velden=VELDEN)
    assert _vraag_uit_uitkomst(uitkomst, {"CATEGORIEEN": CATEGORIEEN}) is None


def test_een_afgeronde_regel_vraagt_niets():
    uitkomst = Uitkomst(klaar=True, resultaat={"uitkomsten": {}}, wacht_op=None, reden="")
    assert _vraag_uit_uitkomst(uitkomst, {"CATEGORIEEN": CATEGORIEEN}) is None

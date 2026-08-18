"""Een afleiding van ons hoort de ondernemer te zien, en te kunnen corrigeren.

`TEELT_GEWASSEN_IN_KAS` staat niet in het Handelsregister. Wij lezen "(onder
glas)" uit de SBI-omschrijving en maken daar een juridische kwalificatie van
(artikel 3.205 Bal). Die bepaalt welke bijlage van de erkende maatregelenlijst
geldt - en dus welke maatregelen de ondernemer straks moet rapporteren.

De routeringstabel markeert het veld als `corrigeerbaar`: de ondernemer mág er
overheen. Alleen kreeg hij het nooit te zien. Van de vier velden die de wet
vraagt was er één al voor hem ingevuld, buiten beeld, op grond van een aanname.
"""

import pytest

from regelloop import Uitkomst
from vlam_host import _vraag_uit_uitkomst

DEFINITIES = {
    "CATEGORIEEN": [
        {"categorie": "Perslucht", "onderdeel": "Faciliteiten"},
        {"categorie": "Binnenverlichting", "onderdeel": "Gebouwen"},
    ]
}


def _uitkomst() -> Uitkomst:
    return Uitkomst(
        klaar=False,
        resultaat=None,
        wacht_op="opgave",
        reden="",
        velden=(
            {"naam": "AANWEZIGE_CATEGORIEEN", "beschrijving": "Welke categorieen komen voor?"},
        ),
    )


def _veld(vraag: dict, naam: str) -> dict | None:
    return next((v for v in vraag["velden"] if v["naam"] == naam), None)


def test_het_afgeleide_veld_staat_in_het_formulier():
    feiten = {"TEELT_IN_KAS": {"waarde": True, "bron": "KvK Handelsregister", "soort": "registratie"}}
    vraag = _vraag_uit_uitkomst(_uitkomst(), DEFINITIES, feiten)
    assert _veld(vraag, "TEELT_GEWASSEN_IN_KAS") is not None


def test_het_afgeleide_veld_draagt_de_afgeleide_waarde():
    """Voorgevuld, zodat de ondernemer ziet wát wij hebben aangenomen."""
    feiten = {"TEELT_IN_KAS": {"waarde": True, "bron": "KvK Handelsregister", "soort": "registratie"}}
    veld = _veld(_vraag_uit_uitkomst(_uitkomst(), DEFINITIES, feiten), "TEELT_GEWASSEN_IN_KAS")
    assert veld["waarde"] == "Ja"


@pytest.mark.parametrize("waarde,verwacht", [(True, "Ja"), (False, "Nee")])
def test_beide_uitkomsten_van_de_afleiding(waarde, verwacht):
    """Geen kas gevonden is óók een waarneming, geen onwetendheid."""
    feiten = {"TEELT_IN_KAS": {"waarde": waarde, "bron": "KvK", "soort": "registratie"}}
    veld = _veld(_vraag_uit_uitkomst(_uitkomst(), DEFINITIES, feiten), "TEELT_GEWASSEN_IN_KAS")
    assert veld["waarde"] == verwacht


def test_het_veld_noemt_waar_de_afleiding_vandaan_komt():
    """Anders is het voor de ondernemer niet te beoordelen of hij moet corrigeren."""
    feiten = {"TEELT_IN_KAS": {"waarde": True, "bron": "KvK Handelsregister", "soort": "registratie"}}
    veld = _veld(_vraag_uit_uitkomst(_uitkomst(), DEFINITIES, feiten), "TEELT_GEWASSEN_IN_KAS")
    toelichting = veld.get("toelichting", "")
    assert "Handelsregister" in toelichting or "SBI" in toelichting


def test_zonder_afleiding_geen_extra_veld():
    """Heeft de KvK niets opgeleverd, dan vraagt de lus het zelf al als opgave.

    Het veld twee keer in hetzelfde formulier zetten is erger dan het weglaten.
    """
    vraag = _vraag_uit_uitkomst(_uitkomst(), DEFINITIES, feiten={})
    assert _veld(vraag, "TEELT_GEWASSEN_IN_KAS") is None


def test_zonder_feiten_blijft_het_formulier_werken():
    vraag = _vraag_uit_uitkomst(_uitkomst(), DEFINITIES, None)
    assert vraag is not None
    assert _veld(vraag, "AANWEZIGE_CATEGORIEEN") is not None

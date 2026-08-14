"""De maatregelen gaan als data mee, niet als tekst.

vraagSpec() in digitale-assistent.js leest payload.maatregelen vóór het
terugvalt op het parsen van de platte tekst. Zolang de backend dat veld niet
vult, hangt het formulier af van hoe het model die beurt formatteert - en dat
verschilt per beurt.

De wet levert de maatregelen die voor dit bedrijf gelden al gefilterd op: staat
een maatregel in `uitkomsten.maatregelen`, dan valt hij onder de bijlage die
voor dit bedrijf geldt én in een categorie die bij het bedrijf voorkomt. Er is
dus geen `van_toepassing`-vlag meer om op te filteren.
"""

import json

from vlam_host import maatregelen_uit_status, maatregelen_voor_event


def _envelope(uitkomsten: dict) -> str:
    return json.dumps(
        {"data": {"uitkomsten": uitkomsten}, "provenance": {"source": "test"}}
    )


def _maatregel(code: str, naam: str, categorie: str = "Ruimteverwarming", bijlage: str = "XIV") -> dict:
    return {"code": code, "naam": naam, "categorie": categorie, "bijlage": bijlage}


def test_een_maatregel_gaat_mee_met_code_omschrijving_categorie_en_bijlage():
    resultaat = _envelope(
        {"maatregelen": [_maatregel("GC1", "Pas een klokregeling toe en regel deze in")]}
    )
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) == [
        {
            "code": "GC1",
            "omschrijving": "Pas een klokregeling toe en regel deze in",
            "categorie": "Ruimteverwarming",
            "bijlage": "XIV",
        }
    ]


def test_meerdere_maatregelen_gaan_allemaal_mee_in_volgorde():
    """Eén maatregel verbergt 'geeft de enige terug' i.p.v. 'geeft ze allemaal'
    (CLAUDE.md). Drie stuks, uit twee verschillende bijlagen."""
    resultaat = _envelope(
        {
            "maatregelen": [
                _maatregel("GK1", "Breng beweegbare gevelschermen aan", "Tuinbouwkassen", "XIVa"),
                _maatregel("PT1", "Pas meerdere schakelgroepen toe", "Glastuinbouw", "VIIaa"),
                _maatregel("GF4", "Vervang lampen door LED", "Binnenverlichting", "XIVa"),
            ]
        }
    )
    velden = maatregelen_voor_event("regelrecht__execute_law", resultaat)
    assert [v["code"] for v in velden] == ["GK1", "PT1", "GF4"]
    assert [v["bijlage"] for v in velden] == ["XIVa", "VIIaa", "XIVa"]


def test_naam_wordt_omschrijving():
    """De frontend leest m.omschrijving; de wet levert m.naam.

    Zonder deze hermapping toont het formulier kale codes zonder tekst.
    """
    resultaat = _envelope({"maatregelen": [_maatregel("GF4", "Vervang lampen door LED")]})
    velden = maatregelen_voor_event("regelrecht__execute_law", resultaat)
    assert velden[0]["omschrijving"] == "Vervang lampen door LED"


def test_malvormd_element_valt_weg_maar_de_rest_blijft():
    """Eén kapot element mag de andere maatregelen niet meenemen in zijn val.

    De oude vorm liet de hele oogst op `None` uitkomen omdat `.get()` op een
    string een AttributeError gooit die buiten de lus gevangen werd. Nu wordt
    per element gefilterd: de ondernemer ziet de maatregelen die wél kloppen.
    """
    resultaat = _envelope(
        {
            "maatregelen": [
                _maatregel("GC1", "Pas een klokregeling toe"),
                "niet een dict",
                _maatregel("FD3", "Pas nachtafdekking toe"),
            ]
        }
    )
    velden = maatregelen_voor_event("regelrecht__execute_law", resultaat)
    assert [v["code"] for v in velden] == ["GC1", "FD3"]


def test_maatregel_zonder_code_valt_weg():
    """Een maatregel zonder code kan de ondernemer niet rapporteren."""
    resultaat = _envelope(
        {"maatregelen": [{"naam": "Naamloos"}, _maatregel("GC1", "Pas een klokregeling toe")]}
    )
    velden = maatregelen_voor_event("regelrecht__execute_law", resultaat)
    assert [v["code"] for v in velden] == ["GC1"]


def test_lege_maatregelenlijst_geeft_geen_veld():
    """Geen maatregelen is een uitkomst, geen formulier.

    De wet kan legitiem nul maatregelen opleveren (geen enkele categorie
    aanwezig); dan hoort er geen leeg formulier mee te gaan.
    """
    assert maatregelen_voor_event("regelrecht__execute_law", _envelope({"maatregelen": []})) is None


def test_zonder_maatregelen_geen_veld():
    """Anders draagt elk volgend antwoord een verouderd formulier mee."""
    assert maatregelen_voor_event("regelrecht__execute_law", _envelope({})) is None


def test_informatieplicht_uitkomst_levert_geen_maatregelen():
    """Beide regels lopen langs dezelfde tool; alleen de tweede draagt maatregelen."""
    resultaat = _envelope({"heeft_informatieplicht": True, "rapportage_frequentie_jaren": 4})
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) is None


def test_andere_tool_levert_niets():
    assert maatregelen_voor_event("kvk__mijn_bedrijf", _envelope({"naam": "x"})) is None


def test_kapot_resultaat_gooit_niet():
    assert maatregelen_voor_event("regelrecht__execute_law", "geen json") is None


def test_data_geen_dict_gooit_niet():
    """`data` kan een lijst of string zijn; `.get()` daarop gooit een AttributeError."""
    resultaat = json.dumps({"data": ["niet een dict"]})
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) is None


def test_uitkomsten_geen_dict_gooit_niet():
    resultaat = json.dumps({"data": {"uitkomsten": "niet een dict"}})
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) is None


# --- De host draait de regel zelf; het model roept hem niet meer aan ---------


def _status(maatregelen, klaar=True):
    return {"klaar": True, "wacht_op": None, "reden": "", "resultaat": {},
            "maatregelen": {"klaar": klaar, "wacht_op": None, "reden": "",
                            "resultaat": {"uitkomsten": {"maatregelen": maatregelen}}}}


def test_maatregelen_komen_uit_de_regelloop():
    """Sinds de host de maatregelenregel zelf draait, komt de lijst niet meer uit
    een tool-aanroep van het model.

    Zonder deze weg draagt het answer-event geen maatregelen meer en valt het
    formulier terug op het parsen van de tekst die het model die beurt toevallig
    schreef - precies wat de gestructureerde overdracht moest vervangen.
    """
    velden = maatregelen_uit_status(_status([_maatregel("GK1", "Breng gevelschermen aan", "Tuinbouwkassen", "XIVa")]))
    assert velden == [
        {
            "code": "GK1",
            "omschrijving": "Breng gevelschermen aan",
            "categorie": "Tuinbouwkassen",
            "bijlage": "XIVa",
        }
    ]


def test_zonder_tweede_regel_geen_maatregelen():
    """Geldt de energiebesparingsplicht niet, dan draait de maatregelenregel niet."""
    assert maatregelen_uit_status({"klaar": True, "wacht_op": None, "resultaat": {}}) is None


def test_een_wachtende_regel_levert_geen_lijst():
    """Wacht de regel nog op de categorieen, dan is er niets te tonen."""
    assert maatregelen_uit_status(_status([], klaar=False)) is None


def test_geen_regelstatus_gooit_niet():
    """Op het CLI-transport draait de lus niet; dan is er geen status."""
    assert maatregelen_uit_status(None) is None


def test_uitkomsten_geen_dict_in_status_gooit_niet():
    status = {"maatregelen": {"resultaat": {"uitkomsten": "niet een dict"}}}
    assert maatregelen_uit_status(status) is None

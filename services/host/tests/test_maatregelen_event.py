"""De maatregelen gaan als data mee, niet als tekst.

vraagSpec() in digitale-assistent.js leest payload.maatregelen vóór het
terugvalt op het parsen van de platte tekst. Zolang de backend dat veld niet
vult, hangt het formulier af van hoe het model die beurt formatteert - en dat
verschilt per beurt.
"""

import json

from vlam_host import maatregelen_voor_event


def _envelope(data: dict) -> str:
    return json.dumps({"data": data, "provenance": {"source": "test"}})


def test_alleen_geldende_maatregelen_gaan_mee():
    resultaat = _envelope(
        {
            "maatregelen": [
                {"code": "GC1", "naam": "Pas een klokregeling toe", "van_toepassing": True},
                {"code": "FE4", "naam": "Iets anders", "van_toepassing": False},
            ]
        }
    )
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) == [
        {"code": "GC1", "omschrijving": "Pas een klokregeling toe"}
    ]


def test_meerdere_geldende_maatregelen_gaan_allemaal_mee():
    """Eén overblijvende maatregel verbergt 'geeft de enige terug' i.p.v.
    'kiest de juiste' (CLAUDE.md). Drie geldende, twee niet-geldende."""
    resultaat = _envelope(
        {
            "maatregelen": [
                {"code": "GC1", "naam": "Pas een klokregeling toe", "van_toepassing": True},
                {"code": "GC3", "naam": "Pas een weersafhankelijke regeling toe", "van_toepassing": True},
                {"code": "FE4", "naam": "Iets anders", "van_toepassing": False},
                {"code": "FD3", "naam": "Pas nachtafdekking toe", "van_toepassing": True},
                {"code": "GD1", "naam": "Nog iets anders", "van_toepassing": False},
            ]
        }
    )
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) == [
        {"code": "GC1", "omschrijving": "Pas een klokregeling toe"},
        {"code": "GC3", "omschrijving": "Pas een weersafhankelijke regeling toe"},
        {"code": "FD3", "omschrijving": "Pas nachtafdekking toe"},
    ]


def test_malvormd_element_tussen_geldende_maatregelen_laat_de_hele_extractie_stuklopen():
    """Vastleggen wat er nu gebeurt: één kapot element tussen twee geldende
    maatregelen levert `None` op voor de hele lijst, niet de twee geldende.

    `m.get("van_toepassing")` op een niet-dict gooit een AttributeError; de
    `except (ValueError, AttributeError)` in `maatregelen_voor_event` vangt die
    voor de hele oogst, niet per element."""
    resultaat = _envelope(
        {
            "maatregelen": [
                {"code": "GC1", "naam": "Pas een klokregeling toe", "van_toepassing": True},
                "niet een dict",
                {"code": "FD3", "naam": "Pas nachtafdekking toe", "van_toepassing": True},
            ]
        }
    )
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) is None


def test_naam_wordt_omschrijving():
    """De frontend leest m.omschrijving; _eml_lijst produceert m.naam.

    Zonder deze hermapping toont het formulier kale codes zonder tekst.
    """
    resultaat = _envelope(
        {"maatregelen": [{"code": "GF4", "naam": "Vervang lampen door LED", "van_toepassing": True}]}
    )
    velden = maatregelen_voor_event("regelrecht__execute_law", resultaat)
    assert velden[0]["omschrijving"] == "Vervang lampen door LED"


def test_zonder_maatregelen_geen_veld():
    """Anders draagt elk volgend antwoord een verouderd formulier mee."""
    assert maatregelen_voor_event("regelrecht__execute_law", _envelope({})) is None


def test_andere_tool_levert_niets():
    assert maatregelen_voor_event("kvk__mijn_bedrijf", _envelope({"naam": "x"})) is None


def test_kapot_resultaat_gooit_niet():
    assert maatregelen_voor_event("regelrecht__execute_law", "geen json") is None


def test_data_geen_dict_gooit_niet():
    """`data` kan een lijst of string zijn; `.get()` daarop gooit een AttributeError."""
    resultaat = json.dumps({"data": ["niet een dict"]})
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) is None


def test_maatregel_geen_dict_gooit_niet():
    """Eén malvormd element in de lijst mag de hele extractie niet laten crashen."""
    resultaat = _envelope({"maatregelen": ["niet een dict"]})
    assert maatregelen_voor_event("regelrecht__execute_law", resultaat) is None

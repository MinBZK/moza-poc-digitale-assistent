"""Het maatregelen-formulier komt de beurt ná het oordeel; het model mag de
vragen intussen niet zelf uittikken.

Gezien op de onderzoeksomgeving (25 augustus): bij "de toets is afgerond"
somde het model de drie vragen en alle 23 categorieën op in proza. De
frontend maakt daar geen formulier van (regels eindigen op ")" of missen
"?"), dus de ondernemer typte los antwoorden in de chat. Een beurt later
kwam het echte formulier alsnog.
"""

import pytest

from prompts.composer import compose_system_prompt

_KLAAR = {
    "klaar": True,
    "wacht_op": None,
    "resultaat": {"voldoet_aan_voorwaarden": True, "uitkomsten": {}},
}


def _prompt(**extra):
    status = {**_KLAAR, "maatregelen": {"klaar": False, "wacht_op": "opgave"}, **extra}
    return compose_system_prompt("claude", has_tools=True, regel_status=status)


def test_zonder_formulier_deze_beurt_mag_het_model_de_vragen_niet_noemen():
    prompt = _prompt()
    assert "Noem de vragen en de categorieën NIET zelf" in prompt
    assert "volgende beurt" in prompt


def test_met_formulier_deze_beurt_verwijst_het_model_ernaar():
    prompt = _prompt(vraag={"titel": "Erkende Maatregelenlijst", "velden": []})
    assert "Het formulier daarvoor staat bij dit antwoord" in prompt
    assert "Noem de vragen en de categorieën NIET zelf" not in prompt


def test_zonder_maatregelenregel_geen_van_beide():
    prompt = compose_system_prompt("claude", has_tools=True, regel_status=_KLAAR)
    assert "Noem de vragen en de categorieën NIET zelf" not in prompt
    assert "staat bij dit antwoord" not in prompt


# --- wat als formulier op het scherm staat, komt niet ook in tekst ------------

_MAATREGELEN_KLAAR = {
    "klaar": True,
    "wacht_op": None,
    "resultaat": {
        "uitkomsten": {
            "maatregelen": [
                {"code": "FA1", "omschrijving": "Vergroot de persluchtbuffer"},
                {"code": "GF2", "omschrijving": "Vervang TL8-buizen door LED-buizen"},
            ]
        }
    },
}


def test_verbruiksformulier_erbij_dan_geen_vragen_in_tekst():
    status = {"klaar": False, "wacht_op": "opgave", "vraag": {"titel": "Gegevens voor de toets", "velden": []}}
    prompt = compose_system_prompt("claude", has_tools=True, regel_status=status)
    assert "herhaal de vragen NIET" in prompt


def test_verbruiksformulier_nog_niet_dan_gewone_instructie():
    status = {"klaar": False, "wacht_op": "opgave"}
    prompt = compose_system_prompt("claude", has_tools=True, regel_status=status)
    assert "herhaal de vragen NIET" not in prompt


def test_maatregelenlijst_als_formulier_dan_niet_opsommen():
    status = {**_KLAAR, "maatregelen": _MAATREGELEN_KLAAR, "maatregelen_lijst_erbij": True}
    prompt = compose_system_prompt("claude", has_tools=True, regel_status=status)
    assert "Som de maatregelen NIET op" in prompt
    assert "FA1" in prompt, "de lijst zelf blijft in de prompt (nodig voor het rapport later)"


def test_maatregelenlijst_al_getoond_dan_wel_per_stuk_voor_het_rapport():
    status = {**_KLAAR, "maatregelen": _MAATREGELEN_KLAAR, "maatregelen_lijst_erbij": False}
    prompt = compose_system_prompt("claude", has_tools=True, regel_status=status)
    assert "Som de maatregelen NIET op" not in prompt
    assert "Noem de maatregelen uit deze lijst" in prompt


def test_de_host_zet_de_vlag_alleen_de_eerste_keer():
    import vlam_host

    host = vlam_host.VLAMHost()
    status = {**_KLAAR, "maatregelen": _MAATREGELEN_KLAAR}
    assert host._met_lijst_vlag(status, "62345681:a")["maatregelen_lijst_erbij"] is True
    host.markeer_maatregelen_gemeld("62345681:a")
    assert host._met_lijst_vlag(status, "62345681:a")["maatregelen_lijst_erbij"] is False
    assert host._met_lijst_vlag(_KLAAR, "62345681:a") == _KLAAR


# --- een al bepaalde regel gaat niet opnieuw naar de engine -------------------


@pytest.mark.asyncio
async def test_model_aanroep_van_een_klaar_bepaalde_regel_krijgt_de_uitkomst_van_de_host():
    """Het model riep de maatregelenregel zelf aan (met eigen overrides), kreeg
    "ontbrekende gegevens" en meldde een technisch probleem dat er niet was."""
    import json
    import types

    import vlam_host

    aangeroepen = []

    class _Registry:
        tool_map = {"regelrecht__execute_law": object()}

        async def call_tool(self, naam, args):
            aangeroepen.append(naam)
            return json.dumps({"data": {"ontbrekende_gegevens": [{"naam": "X"}]}})

    host = vlam_host.VLAMHost()
    host.registry = _Registry()
    host._regel_status_laatst["62345681:a"] = {
        "klaar": True,
        "resultaat": {"voldoet_aan_voorwaarden": True},
        "maatregelen": {"klaar": True, "resultaat": {"uitkomsten": {"maatregelen": [{"code": "FA1"}]}}},
    }
    tool_use = types.SimpleNamespace(
        id="t1",
        name="regelrecht__execute_law",
        input={"law": vlam_host._MAATREGELEN_LAW, "parameters": {}, "overrides": {"RVO": {}}},
    )
    results, fouten, gebruikt = await host._execute_tools([tool_use], "62345681", "62345681:a")
    assert aangeroepen == [], "geen verse engine-aanroep"
    assert json.loads(results[0]["content"])["data"]["uitkomsten"]["maatregelen"][0]["code"] == "FA1"
    assert fouten == [] and gebruikt == []


@pytest.mark.asyncio
async def test_een_nog_niet_bepaalde_regel_gaat_gewoon_naar_de_bron():
    import json
    import types

    import vlam_host

    aangeroepen = []

    class _Registry:
        tool_map = {"regelrecht__execute_law": object()}

        async def call_tool(self, naam, args):
            aangeroepen.append(naam)
            return json.dumps({"data": {"voldoet_aan_voorwaarden": False}})

    host = vlam_host.VLAMHost()
    host.registry = _Registry()
    host._regel_status_laatst["62345681:a"] = {"klaar": False, "maatregelen": {"klaar": False}}
    tool_use = types.SimpleNamespace(
        id="t1", name="regelrecht__execute_law",
        input={"law": vlam_host._MAATREGELEN_LAW, "parameters": {}},
    )
    results, _, gebruikt = await host._execute_tools([tool_use], "62345681", "62345681:a")
    assert aangeroepen == ["regelrecht__execute_law"]
    assert gebruikt == ["regelrecht__execute_law"]

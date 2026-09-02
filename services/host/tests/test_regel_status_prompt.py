"""Het model moet weten wat de regelloop deze beurt al heeft bepaald.

`_compose_regel_status` heeft vier takken (toestemming/opgave/onbekend/klaar);
zonder dekking hier kan elk daarvan breken zonder dat de suite het merkt -
precies wat er gebeurde met de "voldoet_aan_voorwaarden"-lek en de interne
veldnamen uit `reden` (C2/I3/I4 uit de taak-4-review).
"""

import pytest

from prompts.composer import _compose_regel_status, compose_system_prompt

KOP = "STATUS VAN DE REGELTOETS"


def _blok(regel_status: dict) -> str:
    """Alleen het regel_status-blok zelf, niet de hele samengestelde prompt.

    De rest van de prompt (voorbeelden, tool_usage.md) noemt legitiem
    dezelfde interne namen (HEEFT_KOELINSTALLATIE, de wetpaden) voor de nog
    wél modelgeorkestreerde stappen; een "niet in de hele prompt"-check zou
    daar valse positieven op geven.
    """
    blok = _compose_regel_status(regel_status)
    assert blok is not None
    return blok


def test_geen_regel_status_geeft_geen_blok():
    assert _compose_regel_status(None) is None
    assert _compose_regel_status({}) is None


def test_regel_status_landt_in_de_samengestelde_prompt():
    """Bedrading: het blok verschijnt ook echt in `compose_system_prompt`."""
    prompt = compose_system_prompt(
        "claude",
        True,
        regel_status={"klaar": False, "wacht_op": "toestemming", "reden": "x", "resultaat": None},
    )
    assert KOP in prompt


def test_toestemming_vraagt_expliciet_en_wacht():
    blok = _blok(
        {
            "klaar": False,
            "wacht_op": "toestemming",
            "reden": "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH komt uit Business Wallet; dat vergt akkoord van de ondernemer.",
            "resultaat": None,
        }
    )
    assert "Business Wallet" in blok
    assert "EXPLICIET" in blok
    # Geen interne veldnaam of wetpad uit `reden` in de prompt (I3): dat is
    # voor de log, niet voor het model.
    assert "JAARLIJKS_ELEKTRICITEITSVERBRUIK_KWH" not in blok


def test_opgave_verwijst_naar_het_formulier():
    blok = _blok(
        {
            "klaar": False,
            "wacht_op": "opgave",
            "reden": "HEEFT_KOELINSTALLATIE weet alleen de ondernemer; dat hoort uit het formulier te komen.",
            "resultaat": None,
        }
    )
    assert "formulier" in blok
    assert "HEEFT_KOELINSTALLATIE" not in blok


def test_onbekend_meldt_eerlijk_niet_te_kunnen_bepalen():
    blok = _blok(
        {
            "klaar": False,
            "wacht_op": "onbekend",
            "reden": "omgevingswet/energiebesparing/informatieplicht vraagt na 5 rondes nog steeds om hetzelfde gegeven.",
            "resultaat": None,
        }
    )
    assert "niet automatisch bepalen" in blok
    assert "omgevingswet/energiebesparing/informatieplicht" not in blok


def test_klaar_positief_noemt_de_uitkomst_niet_de_sleutelnaam():
    blok = _blok(
        {
            "klaar": True,
            "wacht_op": None,
            "reden": "",
            "resultaat": {
                "voldoet_aan_voorwaarden": True,
                "uitkomsten": {
                    "heeft_informatieplicht": True,
                    "heeft_onderzoeksplicht": False,
                    "volgende_rapportage_deadline": "2027-12-01",
                    "rapportage_frequentie_jaren": 4,
                },
            },
        }
    )
    assert "geldt voor uw bedrijf" in blok
    assert "informatieplicht geldt." in blok
    assert "onderzoeksplicht geldt niet." in blok
    assert "2027-12-01" in blok
    assert "elke 4 jaar" in blok
    assert "uit RegelRecht komt" in blok
    # De rauwe sleutelnaam hoort niet letterlijk in de prompttekst te staan
    # (I4): die nodigt uit het als jargon/juridisch label te lezen.
    assert "voldoet_aan_voorwaarden" not in blok


def test_status_blok_noemt_de_geoogste_feitnamen():
    """`tool_usage.md` verwijst voor de bedrijfsgegevens naar dit blok; zonder
    de feitnamen erin klopt die verwijzing niet - het blok bevatte tot dusver
    alleen de uitkomsttekst, geen enkel opgehaald feit."""
    blok = _compose_regel_status(
        {
            "klaar": False,
            "wacht_op": "toestemming",
            "reden": "x",
            "resultaat": None,
        },
        feiten={
            "BEDRIJFSNAAM": {"waarde": "Kwekerij De Bloesem", "bron": "KvK", "soort": "registratie"},
            "VESTIGINGSADRES": {"waarde": "Hoefweg 210", "bron": "KvK", "soort": "registratie"},
        },
    )
    assert "{{BEDRIJFSNAAM}}" in blok
    assert "{{VESTIGINGSADRES}}" in blok


def test_status_blok_zonder_feiten_blijft_werken():
    """Geen feiten (nog niets opgehaald, of CLI-transport) mag niet crashen en
    voegt geen loze zin toe."""
    blok = _compose_regel_status(
        {"klaar": False, "wacht_op": "toestemming", "reden": "x", "resultaat": None},
        feiten=None,
    )
    assert "Al opgehaald" not in blok


def _maatregelen_status(aantal: int = 2) -> dict:
    """Een afgeronde maatregelentoets zoals `_regel_status_dict` hem oplevert."""
    lijst = [
        {"code": "FA1", "naam": "Vergroot de persluchtbuffer.", "categorie": "Perslucht"},
        {"code": "GB3", "naam": "Vervang de verlichting door led.", "categorie": "Binnenverlichting"},
    ][:aantal]
    return {
        "klaar": True,
        "wacht_op": None,
        "reden": "",
        "resultaat": {
            "voldoet_aan_voorwaarden": True,
            "uitkomsten": {
                "maatregelen": lijst,
                "bijlage_milieubelastende_activiteiten": "VIIaa",
                "bijlage_gebouwen": "XIVa",
            },
            "gebruikte_waarden": {
                "TEELT_GEWASSEN_IN_KAS": True,
                "TEELT_GEWASSEN_IN_GEBOUW_GEEN_KAS": False,
                "AANWEZIGE_CATEGORIEEN": ["Perslucht", "Binnenverlichting"],
            },
        },
    }


def test_maatregelenblok_noemt_de_maatregelen_zelf():
    """Het model kan alleen maatregelen noemen die het ook krijgt.

    Het blok droeg alleen een telling ("23 erkende maatregelen") plus de
    opdracht ze te noemen. Omdat de orkestratielus de tool buiten de
    modeldispatch om aanroept, staat het resultaat nergens in de context: op de
    codes uit het formulier antwoordde de assistent "dat zijn geen codes die ik
    herken".
    """
    blok = _blok({**_maatregelen_status(0), "maatregelen": _maatregelen_status()})
    assert "FA1" in blok
    assert "Vergroot de persluchtbuffer." in blok
    assert "GB3" in blok
    assert "Vervang de verlichting door led." in blok


def test_maatregelenblok_noemt_de_waarden_waarop_de_toets_rekende():
    """Anders vraagt het model een afgeleid feit alsnog aan de ondernemer.

    `TEELT_IN_KAS` leidt de host af uit de SBI-omschrijving. Zag het model
    alleen de naam van dat feit en niet de waarde, dan behandelde het de
    afleiding als een aanname die het niet mocht doen ("ik neem geen
    aannames") en bleef het de vraag stellen, beurt na beurt.
    """
    blok = _blok({**_maatregelen_status(0), "maatregelen": _maatregelen_status()})
    assert "in kassen" in blok.lower()
    assert "ja" in blok.lower()
    # Geen rauwe regelveldnaam in de prompttekst, net als bij `reden` (I3/I4).
    assert "TEELT_GEWASSEN_IN_KAS" not in blok


def test_maatregelenblok_zonder_lijst_blijft_werken():
    """Een afgeronde toets zonder maatregelen mag geen lege opsomming geven."""
    status = _maatregelen_status(0)
    status["resultaat"]["uitkomsten"]["maatregelen"] = []
    blok = _blok({**status, "maatregelen": status})
    assert "geen erkende maatregelen" in blok


def test_klaar_negatief_meldt_dat_de_verplichting_niet_geldt():
    """C4: `voldoet_aan_voorwaarden: False` zonder ontbrekende gegevens is een
    definitief "nee", geen onbekende toestand — en dat moet het model ook zo
    lezen, niet als "kan ik niet bepalen"."""
    blok = _blok(
        {
            "klaar": True,
            "wacht_op": None,
            "reden": "",
            "resultaat": {"voldoet_aan_voorwaarden": False, "uitkomsten": {}},
        }
    )
    assert "geldt niet voor uw bedrijf" in blok
    assert "niet automatisch bepalen" not in blok
    assert "onbekend" not in blok.lower()


# --- Welke feitnamen het model aangeboden krijgt -----------------------------


def _feit(waarde):
    return {"waarde": waarde, "bron": "RegelRecht", "soort": "wetsconstante"}


def test_alleen_bruikbare_plaatshouders_worden_aangeboden():
    """Het model krijgt alleen namen die de host ook echt kan invullen.

    De feitenkaart bevat naast echte feiten ook rekenvariabelen van de
    regelengine: `gebruikte_waarden` van de maatregelenwet leverde onder meer
    `current`, `current.categorie`, `VIIaa`, `XIVa`, `gemeente` en
    `is_glastuinbouwsector`. Die werden alle 35 als plaatshouder aangeboden.

    Twee manieren waarop dat op het scherm belandt. Een naam met kleine letters
    wordt niet ingevuld en ook niet als onopgelost herkend, dus `{{gemeente}}`
    blijft letterlijk staan. En een naam met een lijst erachter wordt wél
    ingevuld, met de Python-weergave van die lijst.
    """
    feiten = {
        "BEDRIJFSNAAM": _feit("Kwekerij De Bloesem"),
        "ELEKTRICITEIT_KWH": _feit(420000),
        "gemeente": _feit("gemeente"),
        "current.categorie": _feit("Perslucht"),
        "VIIaa": _feit(True),
        "is_glastuinbouwsector": _feit(True),
        "CATEGORIEEN": _feit([{"categorie": "Perslucht"}]),
        "maatregelen": _feit([{"code": "FA1"}]),
    }
    blok = _compose_regel_status(
        {"klaar": False, "wacht_op": "toestemming", "reden": "x", "resultaat": None},
        feiten=feiten,
    )
    assert "{{BEDRIJFSNAAM}}" in blok
    assert "{{ELEKTRICITEIT_KWH}}" in blok
    for ongewenst in ("gemeente", "current.categorie", "VIIaa", "is_glastuinbouwsector"):
        assert ongewenst not in blok, f"{ongewenst} wordt nog als plaatshouder aangeboden"
    for lijstnaam in ("CATEGORIEEN", "maatregelen"):
        assert f"{{{{{lijstnaam}}}}}" not in blok, (
            f"{lijstnaam} draagt een lijst en hoort geen plaatshouder te zijn"
        )


def test_zonder_bruikbare_feiten_geen_lege_zin():
    """Alleen onbruikbare namen mag geen 'Al opgehaald en met bron beschikbaar: .'"""
    blok = _compose_regel_status(
        {"klaar": False, "wacht_op": "toestemming", "reden": "x", "resultaat": None},
        feiten={"current": _feit("x"), "maatregelen": _feit([1, 2])},
    )
    assert "Al opgehaald" not in blok


@pytest.mark.parametrize(
    "bron",
    ["KvK Handelsregister", "Business Wallet"],
)
def test_toestemming_noemt_de_bron_waarop_het_systeem_wacht(bron):
    """Het statusblok noemde altijd de Business Wallet, ook als de host op akkoord
    voor het Handelsregister wachtte; het model riep dan de KvK-tool aan en de
    poort moest hem weigeren. De status weet welke bron het is."""
    prompt = compose_system_prompt(
        "claude",
        has_tools=True,
        regel_status={"wacht_op": "toestemming", "toestemming_bron": bron},
    )
    andere = "Business Wallet" if bron != "Business Wallet" else "KvK Handelsregister"
    assert f"Voor de bron {bron} is eerst toestemming" in prompt
    assert f"Voor de bron {andere}" not in prompt
    assert "NIET zelf aan" in prompt


def test_toestemming_zonder_bron_valt_terug_op_de_wallet():
    prompt = compose_system_prompt(
        "claude", has_tools=True, regel_status={"wacht_op": "toestemming"}
    )
    assert "Voor de bron de Business Wallet is eerst toestemming" in prompt

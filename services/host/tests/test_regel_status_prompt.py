"""Het model moet weten wat de regelloop deze beurt al heeft bepaald.

`_compose_regel_status` heeft vier takken (toestemming/opgave/onbekend/klaar);
zonder dekking hier kan elk daarvan breken zonder dat de suite het merkt -
precies wat er gebeurde met de "voldoet_aan_voorwaarden"-lek en de interne
veldnamen uit `reden` (C2/I3/I4 uit de taak-4-review).
"""

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

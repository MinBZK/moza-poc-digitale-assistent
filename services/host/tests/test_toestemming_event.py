"""Het deelverzoek gaat als data mee, niet als zin in de tekst.

Sinds de toestemmingspoort (`_bron_aanroep_gated`, PDR-008) gaat er geen
`tool`-event meer uit voor een aanroep die geweigerd wordt. De frontend hing
haar Business Wallet-kaart juist aan dát event, dus de kaart verscheen niet
meer - en omdat toestemming alleen nog via het contractveld `toestemming`
binnenkomt, had de respondent geen enkele manier meer om akkoord te geven. De
flow liep daarmee dood op precies de stap die het onderzoek wil meten.

Dit veld is de tegenhanger van `vraag` en `maatregelen`: de host vertelt de
frontend wát hij nodig heeft, in plaats van de frontend de tekst van het model
te laten interpreteren.
"""

from vlam_host import _antwoord_events, toestemming_uit_status


def _answer(events: list[dict]) -> dict:
    """Het answer-event uit een reeks events."""
    return next(e for e in events if e["type"] == "answer")


def test_wachten_op_toestemming_levert_een_deelverzoek_op():
    verzoek = toestemming_uit_status({
        "klaar": False,
        "wacht_op": "toestemming",
        "toestemming_bron": "Business Wallet",
        "toestemming_scope": "netbeheerder",
    })
    assert verzoek is not None
    assert verzoek["bron"] == "Business Wallet"
    assert "netbeheerder" in verzoek["omschrijving"]


def test_deelverzoek_benoemt_de_kvk_als_daar_op_gewacht_wordt():
    """Toestemming is per bron; de kaart hoort te zeggen wélke."""
    verzoek = toestemming_uit_status({
        "klaar": False,
        "wacht_op": "toestemming",
        "toestemming_bron": "KvK Handelsregister",
        "toestemming_scope": "kvk",
    })
    assert verzoek is not None
    assert verzoek["bron"] == "KvK Handelsregister"
    assert "Handelsregister" in verzoek["omschrijving"]


def test_zonder_wachten_geen_deelverzoek():
    """Elk ander wachtwoord dan toestemming mag geen kaart oproepen.

    Anders krijgt de respondent een deelverzoek bij een formuliervraag of bij
    een afgeronde toets - en went hij eraan het weg te klikken.
    """
    for status in (
        {"klaar": False, "wacht_op": "opgave"},
        {"klaar": False, "wacht_op": "onbekend"},
        {"klaar": True, "wacht_op": None},
        {},
        None,
    ):
        assert toestemming_uit_status(status) is None


def test_deelverzoek_landt_op_het_answer_event():
    events = _antwoord_events(
        "Mag ik uw energieverbruik ophalen?",
        toestemming_nodig={"bron": "Business Wallet"},
    )
    assert _answer(events)["toestemming_nodig"] == {"bron": "Business Wallet"}


def test_geen_deelverzoek_geen_veld():
    """Een antwoord zonder deelverzoek draagt het veld niet mee.

    Zelfde regel als bij `maatregelen`: een veld dat blijft staan laat de
    frontend een kaart tonen die bij een eerdere beurt hoorde.
    """
    events = _antwoord_events("De plicht geldt voor uw bedrijf.")
    assert "toestemming_nodig" not in _answer(events)


def test_elk_antwoordpad_geeft_het_deelverzoek_door():
    """Beide dispatch-paden moeten het veld meesturen, niet één.

    Dezelfde valkuil als bij de sessie-KvK (PDR-009): een waarde die op het ene
    pad wél en op het andere niet wordt doorgegeven, valt niet op tot een
    respondent net dat pad raakt. `_antwoord_events` wordt aangeroepen vanuit de
    Claude- en de VLAM-stream; een nieuw pad zonder deze doorgifte breekt hier.
    """
    import ast
    from pathlib import Path

    bron = Path(__file__).resolve().parent.parent / "vlam_host.py"
    boom = ast.parse(bron.read_text())
    aanroepen = [
        knoop
        for knoop in ast.walk(boom)
        if isinstance(knoop, ast.Call)
        and isinstance(knoop.func, ast.Name)
        and knoop.func.id == "_antwoord_events"
    ]
    assert aanroepen, "geen enkele aanroep van _antwoord_events gevonden"

    zonder = [
        ast.unparse(knoop)[:80]
        for knoop in aanroepen
        if not any(
            "toestemming_uit_status" in ast.unparse(arg) for arg in knoop.args
        )
        and not any(
            sleutel.arg == "toestemming_nodig" for sleutel in knoop.keywords
        )
    ]
    assert not zonder, f"antwoordpad zonder deelverzoek: {zonder}"

"""Het logging-vangnet redigeert sleutelvormen (MVP-02).

Tweede verdedigingslinie: de host hoort geen sleutels te loggen, maar een
onverwachte traceback of een bibliotheek die zijn eigen verzoek-headers logt,
mag geen sleutel op schijf zetten. Getest op wat het wél vangt én op wat het
bewust niet aanraakt (KvK-nummers, sessie-ID's, gewone tekst).
"""

import io
import logging
import time

import pytest

from log_redaction import (
    REDACTIE,
    RedigerendeFormatter,
    geheim_geregistreerd,
    installeer_redactie,
    redigeer,
    registreer_geheim,
)

SLEUTEL = "sk-ant-api03-ZEERGEHEIM1234567890abcdefg"
# Een VLAM/UbiOps-achtig token: geen voorvoegsel, geen structuur. Precies wat
# patroonherkenning niet kan zien.
VORMLOOS = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


@pytest.mark.parametrize(
    "regel",
    [
        pytest.param(f"Claude-call mislukt: {SLEUTEL}", id="anthropic-sleutel"),
        pytest.param(f"Illegal header value b'{SLEUTEL}'", id="in-foutmelding"),
        pytest.param("token: sk-proj-abcdefghijklmnopqrstuvwxyz012345", id="openai-stijl"),
        pytest.param("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdef", id="bearer"),
        pytest.param(
            "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NSJ9.AbCdEf123", id="kale-jwt"
        ),
        pytest.param("api_key=abcdefghijklmnop", id="toewijzing"),
        pytest.param('{"apikey": "abcdefghijklmnop"}', id="json-veld"),
        pytest.param("x-claude-api-key: abcdefghijklmnop", id="headernaam"),
    ],
)
def test_redigeert_sleutelvormen(regel):
    resultaat = redigeer(regel)
    assert REDACTIE in resultaat
    assert "ZEERGEHEIM" not in resultaat
    assert "abcdefghijklmnop" not in resultaat
    assert "eyJhbGciOiJIUzI1NiJ9" not in resultaat


@pytest.mark.parametrize(
    "regel",
    [
        # Bewust geen entropie-heuristiek: dit zou anders vals-positief raken.
        "Tool-aanroep [claude]: kvk__mijn_bedrijf (velden: ['naam'])",
        "Server 'kvk' verbonden — 3 tools beschikbaar",
        "sessie 85234567|3f9a1c2e-0b44-4d1e-9f8a-2b6c7d8e9f01|vlam",
        "CORS allow_origins=['https://moza.overheid.nl']",
        "GET /health HTTP/1.1 200",
    ],
)
def test_laat_gewone_logregels_ongemoeid(regel):
    assert redigeer(regel) == regel


# --- Sleutels die we bij naam kennen -----------------------------------------
#
# Patroonherkenning ziet alleen sleutels met een herkenbare vorm. De VLAM-backend
# gebruikt UbiOps-tokens zonder voorvoegsel; zonder deze registratie zou de helft
# van de backends buiten het vangnet vallen.


def test_vormloos_token_ontsnapt_zonder_registratie():
    """Vastleggen wat patroonherkenning niet kan: dit is de reden voor het register."""
    assert VORMLOOS in redigeer(f"call mislukt: {VORMLOOS}")


def test_geregistreerd_geheim_wordt_wel_geredigeerd():
    with geheim_geregistreerd(VORMLOOS):
        resultaat = redigeer(f"call mislukt: {VORMLOOS}")
    assert VORMLOOS not in resultaat
    assert REDACTIE in resultaat


def test_registratie_stopt_na_het_verzoek():
    with geheim_geregistreerd(VORMLOOS):
        pass
    assert VORMLOOS in redigeer(f"call mislukt: {VORMLOOS}")


def test_twee_verzoeken_met_dezelfde_sleutel_storen_elkaar_niet():
    """Het aflopen van het ene verzoek mag de registratie van het andere niet wissen."""
    with geheim_geregistreerd(VORMLOOS):
        with geheim_geregistreerd(VORMLOOS):
            pass
        # Het binnenste verzoek is klaar, het buitenste nog niet.
        assert VORMLOOS not in redigeer(f"fout: {VORMLOOS}")
    assert VORMLOOS in redigeer(f"fout: {VORMLOOS}")


def test_te_korte_waarde_wordt_niet_geregistreerd():
    """Anders zou een kort fragment gewone logtekst kunnen verminken."""
    with geheim_geregistreerd("abc"):
        assert redigeer("abc is een gewoon woord") == "abc is een gewoon woord"


# Een sleutel uit een verzoek is door een aanvaller te kiezen. Zonder vormeis kan
# iemand gewone logtekst opgeven en die tijdens zijn eigen verzoek onzichtbaar
# maken — het vangnet tegen sleutellekken wordt dan een middel om sporen te
# wissen. Deze waarden moeten dus genegeerd worden.
@pytest.mark.parametrize(
    "kwaadaardig",
    [
        pytest.param("85234567", id="kvk-nummer"),
        pytest.param("Tool-aanroep", id="logfragment"),
        pytest.param("netbeheerder__verbruik", id="toolnaam-lang-genoeg"),
        pytest.param("geweigerd", id="woord"),
        pytest.param("abcdefghijklmnopqrstuvwxyz", id="lang-maar-zonder-cijfers"),
        pytest.param("12345678901234567890", id="lang-maar-zonder-letters"),
    ],
)
def test_logtekst_als_sleutel_wordt_niet_geregistreerd(kwaadaardig):
    regel = "Tool-aanroep [claude]: netbeheerder__verbruik kvk 85234567 geweigerd"
    with geheim_geregistreerd(kwaadaardig):
        assert redigeer(regel) == regel


def test_echte_sleutelvormen_worden_wel_geregistreerd():
    """De vormeis mag geen realistische sleutel buitensluiten."""
    for echt in [
        "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",          # UbiOps-achtig, 32 hex
        "sk-ant-api03-AbCdEf1234567890xyz",           # Anthropic
        "ubiops-token-9f8e7d6c5b4a3210",              # met streepjes
    ]:
        with geheim_geregistreerd(echt):
            assert echt not in redigeer(f"fout: {echt}"), echt


def test_registreer_geheim_is_blijvend():
    registreer_geheim("SERVER-SLEUTEL-abcdefgh")
    assert "SERVER-SLEUTEL-abcdefgh" not in redigeer("fout: SERVER-SLEUTEL-abcdefgh")


# --- Terugkrabbelen begrensd houden ------------------------------------------


def test_redactie_blijft_lineair_op_vijandige_invoer():
    """Regressie op py/polynomial-redos (CodeQL, PR #44).

    Een onbegrensde `*` vóór een literal gaf kwadratisch terugkrabbelen: 4x de
    tijd bij 2x de invoer, en 16k tekens kostte ~1,7 s. Omdat er logregels zijn
    met door de gebruiker aangeleverde tekst was dat een DoS-route — de event
    loop stond stil zolang de logregel verwerkt werd.

    We meten de vórm van de groei, niet een absolute drempel: die zou op een
    trage of belaste machine vals alarm geven. Bij kwadratisch gedrag is de
    verhouding ~4; lineair is ~2. Alles onder 3 is ruim genoeg om het verschil
    te zien zonder gevoelig te zijn voor ruis.
    """
    vijandig = "a-"  # koppeltekens: woordgrenzen én binnen de tekenklasse

    def duur(n: int) -> float:
        tekst = vijandig * n
        start = time.perf_counter()
        for _ in range(3):
            redigeer(tekst)
        return (time.perf_counter() - start) / 3

    basis = duur(4000)
    dubbel = duur(8000)
    # Ondergrens tegen deling door bijna-nul op een erg snelle machine.
    verhouding = dubbel / max(basis, 1e-6)
    assert verhouding < 3, (
        f"redactie schaalt superlineair ({verhouding:.1f}x bij dubbele invoer); "
        "staat er weer een onbegrensde herhaling vóór een literal?"
    )


def _logger_met_buffer(naam: str):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(naam)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, handler, stream


def test_traceback_wordt_ook_geredigeerd():
    """De reden dat dit op de formatter hangt en niet op een logging.Filter.

    Een filter draait vóór het formatteren; `record.exc_text` is dan nog leeg,
    dus de traceback zou er ongefilterd doorheen glippen.
    """
    logger, handler, stream = _logger_met_buffer("test.redactie.traceback")
    handler.setFormatter(RedigerendeFormatter(handler.formatter))

    try:
        raise ValueError(f"Illegal header value b'{SLEUTEL}'")
    except ValueError:
        logger.error("Claude-call mislukt", exc_info=True)

    uitvoer = stream.getvalue()
    assert "Traceback" in uitvoer, "de traceback hoort wél zichtbaar te blijven"
    assert SLEUTEL not in uitvoer
    assert REDACTIE in uitvoer


def test_installeer_redactie_haakt_aan_en_is_idempotent():
    logger, handler, stream = _logger_met_buffer("test.redactie.installatie")
    origineel = handler.formatter

    installeer_redactie()
    assert isinstance(handler.formatter, RedigerendeFormatter)
    assert handler.formatter.binnenste is origineel

    # Tweede aanroep mag niet nóg een laag omhullen.
    installeer_redactie()
    assert handler.formatter.binnenste is origineel

    logger.info("sleutel %s in een logregel", SLEUTEL)
    assert SLEUTEL not in stream.getvalue()
    assert REDACTIE in stream.getvalue()

"""Het logging-vangnet redigeert sleutelvormen (MVP-02).

Tweede verdedigingslinie: de host hoort geen sleutels te loggen, maar een
onverwachte traceback of een bibliotheek die zijn eigen verzoek-headers logt,
mag geen sleutel op schijf zetten. Getest op wat het wél vangt én op wat het
bewust niet aanraakt (KvK-nummers, sessie-ID's, gewone tekst).
"""

import io
import logging

import pytest

from log_redaction import REDACTIE, RedigerendeFormatter, installeer_redactie, redigeer

SLEUTEL = "sk-ant-api03-ZEERGEHEIM1234567890abcdefg"


@pytest.mark.parametrize(
    "regel",
    [
        pytest.param(f"Claude-call mislukt: {SLEUTEL}", id="anthropic-sleutel"),
        pytest.param(f"Illegal header value b'{SLEUTEL}'", id="in-foutmelding"),
        pytest.param("token: sk-proj-abcdefghijklmnopqrstuvwxyz012345", id="openai-stijl"),
        pytest.param("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdef", id="bearer"),
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

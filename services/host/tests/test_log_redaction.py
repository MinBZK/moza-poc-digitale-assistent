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

import log_redaction
from log_redaction import (
    REDACTED,
    RedactingFormatter,
    install_redaction,
    redact,
    redact_always,
    redact_temporarily,
)

SLEUTEL = "sk-ant-api03-ZEERGEHEIM1234567890abcdefg"
# Een VLAM/UbiOps-achtig token: geen voorvoegsel, geen structuur. Precies wat
# patroonherkenning niet kan zien.
VORMLOOS = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


@pytest.mark.parametrize(
    "line",
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
def test_redigeert_sleutelvormen(line):
    result = redact(line)
    assert REDACTED in result
    assert "ZEERGEHEIM" not in result
    assert "abcdefghijklmnop" not in result
    assert "eyJhbGciOiJIUzI1NiJ9" not in result


@pytest.mark.parametrize(
    "line",
    [
        # Bewust geen entropie-heuristiek: dit zou anders vals-positief raken.
        "Tool-aanroep [claude]: kvk__mijn_bedrijf (velden: ['naam'])",
        "Server 'kvk' verbonden — 3 tools beschikbaar",
        "sessie 85234567|3f9a1c2e-0b44-4d1e-9f8a-2b6c7d8e9f01|vlam",
        "CORS allow_origins=['https://moza.overheid.nl']",
        "GET /health HTTP/1.1 200",
    ],
)
def test_laat_gewone_logregels_ongemoeid(line):
    assert redact(line) == line


# --- Sleutels die we bij naam kennen -----------------------------------------
#
# Patroonherkenning ziet alleen sleutels met een herkenbare vorm. De VLAM-backend
# gebruikt UbiOps-tokens zonder voorvoegsel; zonder deze registratie zou de helft
# van de backends buiten het vangnet vallen.


def test_vormloos_token_ontsnapt_zonder_registratie():
    """Vastleggen wat patroonherkenning niet kan: dit is de reden voor het register."""
    assert VORMLOOS in redact(f"call mislukt: {VORMLOOS}")


def test_geregistreerd_geheim_wordt_wel_geredigeerd():
    with redact_temporarily(VORMLOOS):
        result = redact(f"call mislukt: {VORMLOOS}")
    assert VORMLOOS not in result
    assert REDACTED in result


def test_registratie_stopt_na_het_verzoek():
    with redact_temporarily(VORMLOOS):
        pass
    assert VORMLOOS in redact(f"call mislukt: {VORMLOOS}")


def test_twee_verzoeken_met_dezelfde_sleutel_storen_elkaar_niet():
    """Het aflopen van het ene verzoek mag de registratie van het andere niet wissen."""
    with redact_temporarily(VORMLOOS):
        with redact_temporarily(VORMLOOS):
            pass
        # Het binnenste verzoek is klaar, het buitenste nog niet.
        assert VORMLOOS not in redact(f"fout: {VORMLOOS}")
    assert VORMLOOS in redact(f"fout: {VORMLOOS}")


def test_te_korte_waarde_wordt_niet_geregistreerd():
    """Anders zou een kort fragment gewone logtekst kunnen verminken."""
    with redact_temporarily("abc"):
        assert redact("abc is een gewoon woord") == "abc is een gewoon woord"


# Een sleutel uit een verzoek is door een aanvaller te kiezen. Zonder vormeis kan
# iemand gewone logtekst opgeven en die tijdens zijn eigen verzoek onzichtbaar
# maken — het vangnet tegen sleutellekken wordt dan een middel om sporen te
# wissen. Deze waarden moeten dus genegeerd worden.
@pytest.mark.parametrize(
    "malicious",
    [
        pytest.param("85234567", id="kvk-nummer"),
        pytest.param("Tool-aanroep", id="logfragment"),
        pytest.param("netbeheerder__verbruik", id="toolnaam-lang-genoeg"),
        pytest.param("geweigerd", id="woord"),
        pytest.param("abcdefghijklmnopqrstuvwxyz", id="lang-maar-zonder-cijfers"),
        pytest.param("12345678901234567890", id="lang-maar-zonder-letters"),
    ],
)
def test_logtekst_als_sleutel_wordt_niet_geregistreerd(malicious):
    line = "Tool-aanroep [claude]: netbeheerder__verbruik kvk 85234567 geweigerd"
    with redact_temporarily(malicious):
        assert redact(line) == line


def test_echte_sleutelvormen_worden_wel_geregistreerd():
    """De vormeis mag geen realistische sleutel buitensluiten."""
    for real_key in [
        "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",          # UbiOps-achtig, 32 hex
        "sk-ant-api03-AbCdEf1234567890xyz",           # Anthropic
        "ubiops-token-9f8e7d6c5b4a3210",              # met streepjes
    ]:
        with redact_temporarily(real_key):
            assert real_key not in redact(f"fout: {real_key}"), real_key


def test_registreer_geheim_is_blijvend():
    redact_always("SERVER-SLEUTEL-abcdefgh")
    assert "SERVER-SLEUTEL-abcdefgh" not in redact("fout: SERVER-SLEUTEL-abcdefgh")


# --- Terugkrabbelen begrensd houden ------------------------------------------


def _duur(text: str, herhalingen: int = 3) -> float:
    start = time.perf_counter()
    for _ in range(herhalingen):
        redact(text)
    return (time.perf_counter() - start) / herhalingen


# Elk van deze vormen raakt een ándere tak. `a-` haalt de sk-/label-patronen aan
# via woordgrenzen en de tekenklasse, maar níét het duurste patroon: dat heeft
# een letterlijke "api" nodig vóór de `[-_]?key`. Zonder die vormen bleef de tak
# met de langste prefix ongetoetst — en dat was precies de tak die de meeste tijd
# kostte.
VIJANDIG = [
    pytest.param("a-", id="koppeltekens"),
    pytest.param("api-", id="api-prefix"),
    pytest.param("apikey", id="apikey"),
    pytest.param("x-api-key:", id="api-key-label"),
    pytest.param("token=", id="token-label"),
    pytest.param("bearer ", id="bearer-label"),
    pytest.param("eyJ.", id="jwt-aanzet"),
    pytest.param("sk-", id="sk-prefix"),
]


@pytest.mark.parametrize("vorm", VIJANDIG)
def test_redactie_blijft_lineair_op_vijandige_invoer(vorm):
    """Regressie op kwadratisch terugkrabbelen (py/polynomial-redos).

    We meten de vórm van de groei, niet alleen een absolute drempel: die zou op
    een trage machine vals alarm geven. Kwadratisch is ~4x bij dubbele invoer,
    lineair ~2x.
    """
    basis = _duur(vorm * 4000)
    verdubbeld = _duur(vorm * 8000)
    # Ondergrens tegen deling door bijna-nul op een erg snelle machine.
    ratio = verdubbeld / max(basis, 1e-6)
    assert ratio < 3, (
        f"redactie schaalt superlineair ({ratio:.1f}x bij dubbele invoer) op "
        f"{vorm!r}; staat er weer een onbegrensde herhaling vóór een literal?"
    )


@pytest.mark.parametrize("vorm", VIJANDIG)
def test_vijandige_invoer_blijft_ruim_onder_een_seconde(vorm):
    """Een pure ratio-assertie slaagt ook als beide metingen 30 seconden zijn.

    Deze grens is bewust ruim: hij vangt een terugval naar kwadratisch gedrag
    (64 KB kostte toen tientallen seconden), niet een trage machine.
    """
    tekst = (vorm * 65536)[:65536]
    duur = _duur(tekst, herhalingen=1)
    assert duur < 1.0, f"64 KB {vorm!r} kostte {duur:.2f}s"


def test_voorfilter_verandert_de_dekking_niet():
    """De goedkope `in`-check vóór de regexen mag niets laten ontsnappen.

    Geen enkel patroon kan matchen zonder één van de triggers, dus de dekking is
    per constructie gelijk — deze test houdt die constructie eerlijk als er een
    patroon bij komt.
    """

    def zonder_voorfilter(text: str) -> str:
        for pattern, keep_label in log_redaction._PATTERNS:
            text = pattern.sub(
                (r"\1" + log_redaction.REDACTED) if keep_label else log_redaction.REDACTED,
                text,
            )
        return text

    monsters = [
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abcdefghijklmnop",
        "x-claude-api-key: sk-ant-abcdef1234567890",
        "API_KEY = 'geheim1234567890abcd'",
        "token: abcdef1234567890",
        "TOKENS [claude] input=1200 output=340",
        "Host gestart — 12 tools, backends: claude, vlam",
        "POST /chat/stream — mode='vlam'",
        "sk-proj-abcdefghijklmnopqrstuvwxyz",
        "",
        "geen enkel geheim hier",
    ]
    for monster in monsters:
        assert redact(monster) == zonder_voorfilter(monster), monster


def _logger_met_buffer(name: str):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger(name)
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
    handler.setFormatter(RedactingFormatter(handler.formatter))

    try:
        raise ValueError(f"Illegal header value b'{SLEUTEL}'")
    except ValueError:
        logger.error("Claude-call mislukt", exc_info=True)

    uitvoer = stream.getvalue()
    assert "Traceback" in uitvoer, "de traceback hoort wél zichtbaar te blijven"
    assert SLEUTEL not in uitvoer
    assert REDACTED in uitvoer


def test_installeer_redactie_haakt_aan_en_is_idempotent():
    logger, handler, stream = _logger_met_buffer("test.redactie.installatie")
    original = handler.formatter

    install_redaction()
    assert isinstance(handler.formatter, RedactingFormatter)
    assert handler.formatter.inner is original

    # Tweede aanroep mag niet nóg een laag omhullen.
    install_redaction()
    assert handler.formatter.inner is original

    logger.info("sleutel %s in een logregel", SLEUTEL)
    assert SLEUTEL not in stream.getvalue()
    assert REDACTED in stream.getvalue()

"""Een LLM-fout moet op zijn type worden herkend, niet op zijn tekst.

Vóór dit ticket gaven een time-out, een geweigerde sleutel en een overbelast
model alle drie dezelfde zin ("De assistent is op dit moment niet bereikbaar.
Controleer uw API-sleutel of probeer het later opnieuw"). De gebruiker kon
daaruit niet afleiden of wachten zin had, of dat hij zijn sleutel moest
nakijken. Deze test legt per exceptietype vast welke melding eruit komt, voor
beide SDK's.
"""

import anthropic
import httpx
import openai
import pytest

from errors import classificeer_llm_fout

VERZOEK = httpx.Request("POST", "https://example.invalid/v1/messages")


def _status_fout(module, klasse: str, status: int, boodschap: str = "fout"):
    """Bouw een SDK-statusfout zoals de echte client die opwerpt."""
    respons = httpx.Response(status, request=VERZOEK, json={"error": boodschap})
    return getattr(module, klasse)(boodschap, response=respons, body=None)


@pytest.mark.parametrize("module", [anthropic, openai], ids=["anthropic", "openai"])
@pytest.mark.parametrize(
    ("klasse", "status", "verwacht"),
    [
        ("AuthenticationError", 401, "LLM_SLEUTEL_ONGELDIG"),
        ("PermissionDeniedError", 403, "LLM_SLEUTEL_ONGELDIG"),
        ("NotFoundError", 404, "LLM_MODEL_ONBEKEND"),
        ("RateLimitError", 429, "LLM_TE_DRUK"),
        ("InternalServerError", 500, "LLM_OVERBELAST"),
        ("InternalServerError", 529, "LLM_OVERBELAST"),
    ],
)
def test_statusfouten_krijgen_een_eigen_code(module, klasse, status, verwacht):
    fout = classificeer_llm_fout(_status_fout(module, klasse, status), "claude", 60)
    assert fout.code == verwacht


@pytest.mark.parametrize("module", [anthropic, openai], ids=["anthropic", "openai"])
def test_timeout_noemt_hoelang_er_is_gewacht(module):
    fout = classificeer_llm_fout(module.APITimeoutError(VERZOEK), "claude", 60)
    assert fout.code == "LLM_TIMEOUT"
    assert "60 seconden" in fout.bericht


def test_asyncio_timeout_telt_ook_als_timeout():
    """`asyncio.wait_for` werpt de ingebouwde TimeoutError, niet die van de SDK."""
    fout = classificeer_llm_fout(TimeoutError(), "vlam", 30)
    assert fout.code == "LLM_TIMEOUT"
    assert "30 seconden" in fout.bericht


@pytest.mark.parametrize("module", [anthropic, openai], ids=["anthropic", "openai"])
def test_verbindingsfout_wijst_naar_het_netwerk(module):
    fout = classificeer_llm_fout(module.APIConnectionError(request=VERZOEK), "vlam", 30)
    assert fout.code == "LLM_ONBEREIKBAAR"


@pytest.mark.parametrize("module", [anthropic, openai], ids=["anthropic", "openai"])
def test_te_lange_context_krijgt_een_ander_advies_dan_een_gewone_400(module):
    te_lang = _status_fout(
        module, "BadRequestError", 400, "prompt is too long: 250000 tokens"
    )
    assert classificeer_llm_fout(te_lang, "claude", 60).code == "LLM_GESPREK_TE_LANG"

    anders = _status_fout(module, "BadRequestError", 400, "invalid parameter 'foo'")
    assert classificeer_llm_fout(anders, "claude", 60).code == "LLM_VERZOEK_ONGELDIG"


def test_onbekende_fout_levert_toch_een_actionabele_melding():
    fout = classificeer_llm_fout(RuntimeError("boem"), "claude", 60)
    assert fout.code == "LLM_ONBEKEND"
    assert fout.actie.strip()


def test_meldingen_verschillen_echt_van_elkaar():
    """De kern van het ticket: niet elke fout mag op dezelfde zin uitkomen."""
    gevallen = [
        anthropic.APITimeoutError(VERZOEK),
        _status_fout(anthropic, "AuthenticationError", 401),
        _status_fout(anthropic, "RateLimitError", 429),
        _status_fout(anthropic, "InternalServerError", 500),
        anthropic.APIConnectionError(request=VERZOEK),
    ]
    teksten = {classificeer_llm_fout(e, "claude", 60).tekst for e in gevallen}
    assert len(teksten) == len(gevallen)


# --- Budget: een geraakte spend limit is geen onbegrijpelijk verzoek ---------

# De echte tekst die Anthropic teruggaf toen het tegoed op was, gemeten op
# 17 augustus 2026. Voor het onderzoek telt dit dubbel: MVP-12 zet juist een
# spend limit op de gedeelde sleutel, dus dit is het scenario dat een sessiedag
# stil kan leggen.
BUDGET_TEKST = (
    "Your credit balance is too low to access the Anthropic API. "
    "Please go to Plans & Billing to upgrade or purchase credits."
)


@pytest.mark.parametrize(
    "boodschap",
    [
        BUDGET_TEKST,
        "You exceeded your current quota, please check your plan and billing details.",
        "insufficient_quota",
    ],
    ids=["anthropic-credit", "openai-quota", "openai-code"],
)
@pytest.mark.parametrize("module", [anthropic, openai], ids=["anthropic", "openai"])
def test_budget_op_krijgt_een_eigen_melding(module, boodschap):
    """Anders leest een opgeraakt tegoed als 'formuleer uw vraag anders'.

    Beide aanbieders sturen dit als een gewone 400, dus op type alleen is het
    niet te onderscheiden van een echt ongeldig verzoek. Dat is dezelfde reden
    waarom 'context te lang' hier al op tekst wordt herkend.
    """
    fout = classificeer_llm_fout(
        _status_fout(module, "BadRequestError", 400, boodschap), "claude", 60
    )
    assert fout.code == "LLM_BUDGET_OP"


def test_budget_melding_stuurt_niet_de_respondent_aan_het_werk():
    """De respondent kan hier niets aan doen; de begeleider wel.

    Een actie als 'formuleer uw vraag anders' is hier niet alleen nutteloos maar
    misleidend: hij laat de respondent denken dat het aan zijn vraag ligt, en
    hij verbergt voor de begeleider dat het budget op is.
    """
    fout = classificeer_llm_fout(
        _status_fout(anthropic, "BadRequestError", 400, BUDGET_TEKST), "claude", 60
    )
    assert "anders" not in fout.actie.lower()
    assert fout.actie.strip()


def test_een_echt_ongeldig_verzoek_blijft_ongeldig():
    """De tegenproef: niet elke 400 is een budgetprobleem."""
    fout = classificeer_llm_fout(
        _status_fout(anthropic, "BadRequestError", 400, "invalid parameter: temperature"),
        "claude",
        60,
    )
    assert fout.code == "LLM_VERZOEK_ONGELDIG"


def test_context_te_lang_gaat_voor_op_niets_van_dit_alles():
    """Regressie: de bestaande tak mag niet door de nieuwe worden ingepikt."""
    fout = classificeer_llm_fout(
        _status_fout(anthropic, "BadRequestError", 400, "prompt is too long"), "claude", 60
    )
    assert fout.code == "LLM_GESPREK_TE_LANG"

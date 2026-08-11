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

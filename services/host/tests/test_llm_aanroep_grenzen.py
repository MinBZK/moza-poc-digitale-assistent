"""De LLM-aanroep: grenzen op basis van meting, levensteken en één herkansing (PDR-013).

Tijdens het gebruikersonderzoek viel een beurt tweemaal weg op de harde grens
van 60 seconden, terwijl de late beurten in normale omstandigheden al 20
seconden kosten. De grens uit PDR-002 was een aanname bij een kleine prompt;
sindsdien is de prompt vijf keer zo groot geworden. Drie dingen borgen dat het
niet nog een keer gebeurt:

1. de grenzen zijn ruim boven de gemeten duur, en staan op één plek;
2. de host stuurt tijdens een lange aanroep een status-event, zodat de client
   weet dat er nog gewerkt wordt;
3. een 'te druk'-antwoord van het model krijgt één herkansing in de host, met
   een status-event ertussen, in plaats van stille retries in de SDK die de
   tijd opeten en daarna als time-out gemeld worden.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import asyncio  # noqa: E402
import types  # noqa: E402

import anthropic  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402

import config  # noqa: E402
import vlam_host  # noqa: E402

pytestmark = pytest.mark.asyncio


def _http_fout(klasse, status: int):
    verzoek = httpx.Request("POST", "https://api.test/v1/messages")
    return klasse("fout", response=httpx.Response(status, request=verzoek), body=None)


async def _verzamel(gen):
    events = []
    async for e in gen:
        events.append(e)
    return events


def _resultaat(events):
    return next((e["resultaat"] for e in events if e["type"] == "_resultaat"), None)


def _statussen(events):
    return [e["message"] for e in events if e["type"] == "status"]


def _fout(events):
    return next((e for e in events if e["type"] == "error"), None)


# --- grenzen ----------------------------------------------------------------


def test_grenzen_liggen_ruim_boven_de_gemeten_duur():
    """Gemeten: 20 s voor de zwaarste beurt (30k tokens in, 1.400 uit). De grens
    moet een staart van 3x én één herkansing dragen."""
    assert config.CLAUDE_TIMEOUT >= 180
    assert config.VLAM_TIMEOUT >= 120
    assert config.LLM_MAX_TOKENS == 2048
    assert 0 < config.LLM_HARTSLAG_INTERVAL <= 15


async def test_sdk_clients_doen_zelf_geen_retries(monkeypatch):
    """De SDK-retry gebeurt binnen de time-outgrens en is voor de gebruiker
    onzichtbaar; daarna wordt 'te druk' als time-out gemeld. De host doet de
    herkansing zelf, met een status-event."""
    gezien: list[dict] = []

    class _Vast:
        def __init__(self, **kwargs):
            gezien.append(kwargs)
            self.api_key = kwargs.get("api_key", "")
            self.messages = types.SimpleNamespace(create=None)
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=None)
            )

        async def close(self):
            pass

    monkeypatch.setattr(vlam_host.anthropic, "AsyncAnthropic", _Vast)
    monkeypatch.setattr(vlam_host.openai, "AsyncOpenAI", _Vast)
    monkeypatch.setattr(vlam_host, "VLAM_API_KEY", "server-vlam")
    monkeypatch.setattr(vlam_host, "VLAM_BASE_URL", "https://vlam.test/v1")
    vlam_host.VLAMHost()
    assert len(gezien) == 2, "server-clients voor claude en vlam"
    assert all(k.get("max_retries") == 0 for k in gezien)


async def test_override_clients_doen_zelf_geen_retries(monkeypatch):
    gezien: list[dict] = []

    class _Vast:
        def __init__(self, **kwargs):
            gezien.append(kwargs)
            self.api_key = kwargs.get("api_key", "")

        async def close(self):
            pass

    host = vlam_host.VLAMHost()
    monkeypatch.setattr(vlam_host.anthropic, "AsyncAnthropic", _Vast)
    monkeypatch.setattr(vlam_host.openai, "AsyncOpenAI", _Vast)
    monkeypatch.setattr(vlam_host, "VLAM_BASE_URL", "https://vlam.test/v1")
    async with host._request_clients(claude_api_key_override="sk-ant-x", mode="claude"):
        pass
    async with host._request_clients(vlam_api_key_override="vlam-x", mode="vlam"):
        pass
    assert len(gezien) == 2
    assert all(k.get("max_retries") == 0 for k in gezien)


# --- levensteken ------------------------------------------------------------


async def test_snelle_aanroep_geeft_alleen_het_resultaat():
    async def snel():
        return "antwoord"

    events = await _verzamel(
        vlam_host._llm_aanroep(snel, "claude", timeout=5, interval=0.05, wacht=0)
    )
    assert _resultaat(events) == "antwoord"
    assert _statussen(events) == []
    assert _fout(events) is None


async def test_lange_aanroep_stuurt_tussentijds_een_levensteken():
    async def traag():
        await asyncio.sleep(0.26)
        return "antwoord"

    events = await _verzamel(
        vlam_host._llm_aanroep(traag, "claude", timeout=5, interval=0.1, wacht=0)
    )
    assert _resultaat(events) == "antwoord"
    assert len(_statussen(events)) >= 2
    assert events[-1]["type"] == "_resultaat", "het resultaat sluit de reeks af"


async def test_grens_overschreden_meldt_hoelang_er_is_gewacht():
    gestart = asyncio.Event()
    afgebroken = asyncio.Event()

    async def hangt():
        gestart.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            afgebroken.set()
            raise

    events = await _verzamel(
        vlam_host._llm_aanroep(hangt, "claude", timeout=0.25, interval=0.1, wacht=0)
    )
    fout = _fout(events)
    assert fout is not None
    assert fout["code"] == "LLM_TIMEOUT"
    assert "0.25" in fout["message"] or "seconde" in fout["message"]
    assert _resultaat(events) is None
    await asyncio.wait_for(afgebroken.wait(), 1)


# --- herkansing -------------------------------------------------------------


@pytest.mark.parametrize(
    "fout",
    [
        _http_fout(anthropic.RateLimitError, 429),
        _http_fout(anthropic.InternalServerError, 529),
        anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.test")),
    ],
    ids=["te druk", "overbelast", "onbereikbaar"],
)
async def test_druk_model_krijgt_een_herkansing_met_een_status_ertussen(fout):
    pogingen = 0

    async def eerst_druk_dan_goed():
        nonlocal pogingen
        pogingen += 1
        if pogingen == 1:
            raise fout
        return "antwoord"

    events = await _verzamel(
        vlam_host._llm_aanroep(
            eerst_druk_dan_goed, "claude", timeout=5, interval=1, wacht=0
        )
    )
    assert pogingen == 2
    assert _resultaat(events) == "antwoord"
    assert _fout(events) is None
    statussen = _statussen(events)
    assert len(statussen) == 1 and "druk" in statussen[0].lower()


async def test_blijft_het_model_druk_dan_precies_een_herkansing():
    pogingen = 0

    async def altijd_druk():
        nonlocal pogingen
        pogingen += 1
        raise _http_fout(anthropic.RateLimitError, 429)

    events = await _verzamel(
        vlam_host._llm_aanroep(altijd_druk, "claude", timeout=5, interval=1, wacht=0)
    )
    assert pogingen == 2
    fout = _fout(events)
    assert fout is not None and fout["code"] == "LLM_TE_DRUK"


@pytest.mark.parametrize(
    "fout, code",
    [
        (_http_fout(anthropic.AuthenticationError, 401), "LLM_SLEUTEL_ONGELDIG"),
        (_http_fout(anthropic.BadRequestError, 400), "LLM_VERZOEK_ONGELDIG"),
    ],
    ids=["sleutel", "verzoek"],
)
async def test_een_fout_die_niet_overgaat_krijgt_geen_herkansing(fout, code):
    pogingen = 0

    async def kapot():
        nonlocal pogingen
        pogingen += 1
        raise fout

    events = await _verzamel(
        vlam_host._llm_aanroep(kapot, "claude", timeout=5, interval=1, wacht=0)
    )
    assert pogingen == 1
    assert _fout(events)["code"] == code


async def test_de_herkansing_telt_mee_in_de_grens():
    """Twee pogingen delen één grens: de gebruiker wacht nooit langer dan de
    grens, ook niet met herkansing."""
    pogingen = 0

    async def druk_en_dan_traag():
        nonlocal pogingen
        pogingen += 1
        if pogingen == 1:
            raise _http_fout(anthropic.RateLimitError, 429)
        await asyncio.sleep(60)

    events = await asyncio.wait_for(
        _verzamel(
            vlam_host._llm_aanroep(
                druk_en_dan_traag, "claude", timeout=0.3, interval=0.1, wacht=0
            )
        ),
        timeout=2,
    )
    assert _fout(events)["code"] == "LLM_TIMEOUT"

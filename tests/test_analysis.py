import json

import pytest

from notifier.analysis import PROVIDERS, AnalysisError, Analyzer, build_user_prompt, parse_analysis
from notifier.config import AiSettings
from notifier.market_data import Levels
from notifier.x_client import Tweet
from tests.conftest import FakeResponse, FakeSession, no_sleep

SYMBOLS = ("QQQ", "SPY")
TWEET = Tweet("1", "Fed cuts rates; Apple jumps", "alice", "2026-11-19T10:00:00Z")
QQQ = Levels(symbol="QQQ", last=512.3, change_pct=0.4, prev_high=514.2, prev_low=505.1, high_20d=520.0, low_20d=498.0, sma_50=505.0, sma_200=470.0)

GOOD_REPLY = {
    "summary": "The Fed cut rates and Apple rose.",
    "market_relevant": True,
    "market": [
        {"symbol": "SPY", "bias": "Bullish", "reason": "Lower rates help."},
        {"symbol": "QQQ", "bias": "bullish", "reason": "Tech benefits most."},
    ],
    "tickers": [{"symbol": "$aapl", "bias": "bullish", "note": "Leading gains."}],
}


def chat_response(content, status=200):
    return FakeResponse(status, {"choices": [{"message": {"content": content}}]})


def analyzer(*responses, provider="deepseek", model=None, base_url=None):
    session = FakeSession(*responses)
    settings = AiSettings(provider=provider, api_key="key", model=model, base_url=base_url)
    return Analyzer(settings, SYMBOLS, session=session, sleep=no_sleep), session


# ---- prompt


def test_prompt_contains_post_and_real_levels():
    prompt = build_user_prompt(TWEET, {"QQQ": QQQ}, SYMBOLS)
    assert "@alice" in prompt and "Fed cuts rates" in prompt
    assert "QQQ: last 512.30 (+0.40% today)" in prompt
    assert "20-day range 498.00-520.00" in prompt and "SMA200 470.00" in prompt
    assert "SPY: price data unavailable" in prompt


# ---- parsing


def test_parse_orders_market_by_configured_symbols_and_cleans_tickers():
    a = parse_analysis(json.dumps(GOOD_REPLY), SYMBOLS)
    assert [(m.symbol, m.bias) for m in a.market] == [("QQQ", "bullish"), ("SPY", "bullish")]
    assert [(t.symbol, t.bias) for t in a.tickers] == [("AAPL", "bullish")]


def test_parse_accepts_code_fences():
    a = parse_analysis("```json\n" + json.dumps(GOOD_REPLY) + "\n```", SYMBOLS)
    assert a.summary.startswith("The Fed")


def test_parse_fills_missing_symbols_and_unknown_bias_with_neutral():
    reply = {"summary": "s", "market": [{"symbol": "QQQ", "bias": "moon"}]}
    a = parse_analysis(json.dumps(reply), SYMBOLS)
    assert [(m.symbol, m.bias) for m in a.market] == [("QQQ", "neutral"), ("SPY", "neutral")]
    assert a.market_relevant is True and a.tickers == []


def test_parse_drops_bad_duplicate_and_index_tickers_and_caps_at_five():
    tickers = [{"symbol": s} for s in ["QQQ", "not valid", "NVDA", "nvda", "A", "B", "C", "D", "E"]]
    a = parse_analysis(json.dumps({"summary": "s", "tickers": tickers}), SYMBOLS)
    assert [t.symbol for t in a.tickers] == ["NVDA", "A", "B", "C", "D"]


@pytest.mark.parametrize("content", ["not json", "[]", '{"summary": ""}'])
def test_parse_rejects_unusable_replies(content):
    with pytest.raises(AnalysisError):
        parse_analysis(content, SYMBOLS)


# ---- client


@pytest.mark.parametrize("provider", ["deepseek", "gemini", "openai"])
def test_each_provider_uses_its_url_and_default_model(provider):
    a, session = analyzer(chat_response(json.dumps(GOOD_REPLY)), provider=provider)
    a.analyze(TWEET, {})
    call = session.calls[0]
    assert call["url"] == PROVIDERS[provider].base_url + "/chat/completions"
    assert call["json"]["model"] == PROVIDERS[provider].default_model
    assert call["json"]["response_format"] == {"type": "json_object"}
    assert session.headers["Authorization"] == "Bearer key"


def test_model_and_base_url_overrides():
    a, session = analyzer(chat_response(json.dumps(GOOD_REPLY)), model="m2", base_url="https://proxy.example/v1/")
    a.analyze(TWEET, {})
    assert session.calls[0]["url"] == "https://proxy.example/v1/chat/completions"
    assert session.calls[0]["json"]["model"] == "m2"


@pytest.mark.parametrize("status,hint", [(401, "AI_API_KEY"), (404, "AI_MODEL"), (400, "AI error 400")])
def test_errors_are_explained(status, hint):
    a, _ = analyzer(FakeResponse(status, text="bad"))
    with pytest.raises(AnalysisError, match=hint):
        a.analyze(TWEET, {})


def test_unexpected_reply_shape():
    a, _ = analyzer(FakeResponse(200, {"oops": True}))
    with pytest.raises(AnalysisError, match="unexpected format"):
        a.analyze(TWEET, {})


def test_disabled_provider_cannot_build_analyzer():
    with pytest.raises(ValueError):
        Analyzer(AiSettings("none", None, None, None), SYMBOLS)

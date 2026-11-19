"""AI summary and bull/bear analysis of a post.

All three supported providers (DeepSeek, Gemini, OpenAI/ChatGPT) speak
the same "OpenAI chat completions" format, so one small client covers
them all. Switching provider is just a setting (AI_PROVIDER).

The AI only *interprets*. Price levels come from IBKR and are given to
it as facts; it is told never to invent numbers.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable

import requests

from notifier.config import AiSettings
from notifier.http_retry import request_with_retry
from notifier.market_data import Levels
from notifier.x_client import Tweet

log = logging.getLogger(__name__)

BIASES = ("bullish", "bearish", "neutral")
TICKER_PATTERN = re.compile(r"^[A-Z][A-Z.]{0,5}$")
REQUEST_TIMEOUT_SECONDS = 90  # some models "think" before answering


@dataclass(frozen=True)
class ProviderPreset:
    base_url: str
    default_model: str


# Change a default model here, or override it with AI_MODEL in the env file.
PROVIDERS: dict[str, ProviderPreset] = {
    "deepseek": ProviderPreset("https://api.deepseek.com", "deepseek-v4-flash"),
    "gemini": ProviderPreset("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-latest"),
    "openai": ProviderPreset("https://api.openai.com/v1", "gpt-5-mini"),
}


class AnalysisError(Exception):
    """The AI call failed or returned something unusable."""


@dataclass(frozen=True)
class MarketView:
    symbol: str
    bias: str      # bullish / bearish / neutral
    reason: str


@dataclass(frozen=True)
class TickerView:
    symbol: str
    bias: str
    note: str


@dataclass(frozen=True)
class Analysis:
    summary: str
    market_relevant: bool
    market: list[MarketView] = field(default_factory=list)
    tickers: list[TickerView] = field(default_factory=list)


# ------------------------------------------------------------------ prompt

SYSTEM_PROMPT = """You are a concise market analyst for a US equity trader.
You get one post from X (Twitter) and current price levels for index ETFs.

Reply with JSON only, in exactly this shape:
{
  "summary": "1-2 sentences: what the post says, in plain words",
  "market_relevant": true or false,
  "market": [
    {"symbol": "QQQ", "bias": "bullish|bearish|neutral", "reason": "one short sentence"}
  ],
  "tickers": [
    {"symbol": "NVDA", "bias": "bullish|bearish|neutral", "note": "one short sentence"}
  ]
}

Rules:
- "market": one entry per index ETF listed under PRICE LEVELS, same order.
- Judge how the post could move each ETF in the next days.
- Use the price levels to give context (e.g. "near 20-day high, room to
  resistance at X"). Only use numbers that appear under PRICE LEVELS.
  Never invent prices.
- If the post has no market relevance, set market_relevant to false and
  every bias to "neutral".
- "tickers": US-listed stocks the post names or clearly refers to (a
  company name counts, e.g. "Apple" -> AAPL). Max 5. Empty list if none.
  Do not repeat the index ETFs here.
- Be specific and sober. No hype, no disclaimers."""


def _format_levels(levels: dict[str, Levels], symbols: tuple[str, ...]) -> str:
    lines = []
    for symbol in symbols:
        lv = levels.get(symbol)
        if lv is None:
            lines.append(f"{symbol}: price data unavailable")
            continue
        sma = ", ".join(
            f"{name} {value:.2f}"
            for name, value in (("SMA50", lv.sma_50), ("SMA200", lv.sma_200))
            if value is not None
        )
        lines.append(
            f"{symbol}: last {lv.last:.2f} ({lv.change_pct:+.2f}% today), "
            f"previous day range {lv.prev_low:.2f}-{lv.prev_high:.2f}, "
            f"20-day range {lv.low_20d:.2f}-{lv.high_20d:.2f}"
            + (f", {sma}" if sma else "")
        )
    return "\n".join(lines)


def build_user_prompt(tweet: Tweet, levels: dict[str, Levels], symbols: tuple[str, ...]) -> str:
    return (
        f"POST by @{tweet.username}"
        + (f" at {tweet.created_at}" if tweet.created_at else "")
        + f":\n{tweet.text}\n\nPRICE LEVELS:\n{_format_levels(levels, symbols)}"
    )


# ------------------------------------------------------------------ parsing


def _bias(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in BIASES else "neutral"


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return match.group(1) if match else text


def parse_analysis(content: str, symbols: tuple[str, ...]) -> Analysis:
    """Turn the model's reply into an Analysis, tolerating small mistakes."""
    try:
        data = json.loads(_strip_code_fence(content))
    except ValueError as error:
        raise AnalysisError(f"AI reply was not valid JSON: {content[:200]!r}") from error
    if not isinstance(data, dict) or not str(data.get("summary", "")).strip():
        raise AnalysisError("AI reply had no summary")

    by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in data.get("market") or []
        if isinstance(item, dict)
    }
    market = [
        MarketView(
            symbol=symbol,
            bias=_bias(by_symbol.get(symbol, {}).get("bias")),
            reason=str(by_symbol.get(symbol, {}).get("reason", "")).strip(),
        )
        for symbol in symbols
    ]

    tickers: list[TickerView] = []
    for item in data.get("tickers") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).upper().lstrip("$").strip()
        if TICKER_PATTERN.match(symbol) and symbol not in symbols and symbol not in {t.symbol for t in tickers}:
            tickers.append(TickerView(symbol, _bias(item.get("bias")), str(item.get("note", "")).strip()))

    return Analysis(
        summary=str(data["summary"]).strip(),
        market_relevant=bool(data.get("market_relevant", True)),
        market=market,
        tickers=tickers[:5],
    )


# ------------------------------------------------------------------ client


class Analyzer:
    def __init__(
        self,
        settings: AiSettings,
        symbols: tuple[str, ...],
        session: requests.Session | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        if not settings.enabled:
            raise ValueError("Analyzer needs an AI provider")
        preset = PROVIDERS[settings.provider]
        self._url = (settings.base_url or preset.base_url).rstrip("/") + "/chat/completions"
        self.model = settings.model or preset.default_model
        self._symbols = symbols
        self._session = session or requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {settings.api_key}"})
        self._retry_kwargs = {"sleep": sleep} if sleep else {}

    def analyze(self, tweet: Tweet, levels: dict[str, Levels]) -> Analysis:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(tweet, levels, self._symbols)},
            ],
            "response_format": {"type": "json_object"},
        }
        response = request_with_retry(
            self._session, "POST", self._url, json=body,
            timeout=REQUEST_TIMEOUT_SECONDS, **self._retry_kwargs,
        )
        if response.status_code in (401, 403):
            raise AnalysisError(f"AI provider rejected the key ({response.status_code}). Check AI_API_KEY.")
        if response.status_code == 404:
            raise AnalysisError(f"AI model {self.model!r} not found. Set AI_MODEL to a current model.")
        if response.status_code >= 400:
            raise AnalysisError(f"AI error {response.status_code}: {response.text[:300]}")
        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise AnalysisError("AI reply had an unexpected format") from error
        return parse_analysis(content or "", self._symbols)

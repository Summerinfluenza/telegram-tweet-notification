import pytest

from notifier.analysis import Analysis, MarketView, TickerView
from notifier.market_data import Levels
from notifier.messages import format_message
from notifier.telegram import TelegramError, TelegramNotifier
from notifier.x_client import Tweet
from tests.conftest import FakeResponse, FakeSession, no_sleep

TWEET = Tweet("5", "Rates <down> & stocks up", "alice")
QQQ = Levels(symbol="QQQ", last=512.3, change_pct=0.4, prev_high=514.2, prev_low=505.1, high_20d=520.0, low_20d=498.0, sma_50=505.0, sma_200=None)
ANALYSIS = Analysis(
    summary="Rates fall; stocks rise.",
    market_relevant=True,
    market=[MarketView("QQQ", "bullish", "Tech likes lower rates."), MarketView("SPY", "neutral", "")],
    tickers=[TickerView("AAPL", "bearish", "Lagging.")],
)


# ---- message formatting


def test_plain_message_escapes_html_and_links_to_post():
    message = format_message(TWEET)
    assert "Rates &lt;down&gt; &amp; stocks up" in message
    assert 'href="https://x.com/alice/status/5"' in message


def test_full_message_has_summary_bias_levels_and_tickers():
    message = format_message(TWEET, ANALYSIS, {"QQQ": QQQ})
    assert "📝 Rates fall; stocks rise." in message
    assert "🟢 <b>QQQ</b> 512.30 (+0.40%) · Bullish" in message
    assert "Prev day 505.10–514.20 · 20d 498.00–520.00 · 50d 505.00" in message
    assert "200d" not in message  # missing values are left out
    assert "⚪ <b>SPY</b> · Neutral" in message  # no levels for SPY: no price
    assert "🏷 <b>$AAPL</b> 🔴 Lagging." in message


def test_not_market_relevant_hides_market_details():
    analysis = Analysis("Just a joke.", market_relevant=False, market=ANALYSIS.market)
    message = format_message(TWEET, analysis, {"QQQ": QQQ})
    assert "No clear market impact" in message and "Bullish" not in message


def test_notes_are_shown():
    assert "⚠️ <i>AI analysis unavailable</i>" in format_message(TWEET, notes=["AI analysis unavailable"])


def test_plain_message_with_levels_shows_prices():
    assert "📊 <b>QQQ</b> 512.30 (+0.40%)" in format_message(TWEET, levels={"QQQ": QQQ})


def test_very_long_posts_stay_under_telegram_limit():
    long_tweet = Tweet("5", "x" * 10_000, "alice")
    assert len(format_message(long_tweet)) < 4096
    assert len(format_message(long_tweet, ANALYSIS, {"QQQ": QQQ})) < 4096


# ---- telegram client


def notifier(*responses):
    session = FakeSession(*responses)
    return TelegramNotifier("123:SECRET", "42", session=session, sleep=no_sleep), session


def test_send_posts_html_message_to_chat():
    tg, session = notifier(FakeResponse(200, {"ok": True}))
    tg.send("<b>hi</b>")
    call = session.calls[0]
    assert call["url"] == "https://api.telegram.org/bot123:SECRET/sendMessage"
    assert call["json"]["chat_id"] == "42" and call["json"]["parse_mode"] == "HTML"


def test_bot_username():
    tg, _ = notifier(FakeResponse(200, {"result": {"username": "mybot"}}))
    assert tg.bot_username() == "mybot"


@pytest.mark.parametrize("status,text,hint", [
    (401, "Unauthorized", "TELEGRAM_BOT_TOKEN"),
    (400, '{"description":"Bad Request: chat not found"}', "TELEGRAM_CHAT_ID"),
    (403, "Forbidden", "blocked"),
    (400, "something else", "Telegram error 400"),
])
def test_errors_are_explained_and_never_leak_token(status, text, hint):
    tg, _ = notifier(FakeResponse(status, text=text))
    with pytest.raises(TelegramError, match=hint) as info:
        tg.send("x")
    assert "SECRET" not in str(info.value)

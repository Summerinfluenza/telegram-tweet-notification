"""`python -m notifier.main --check`: tests every connection, one by one.

Prints ✅ / ❌ per step with a hint how to fix it, then sends a sample
message to Telegram so you can see exactly what alerts look like.
Run it after installing and after every settings change.
"""

from __future__ import annotations

from typing import Callable

from notifier.config import Config
from notifier.market_data import Levels
from notifier.messages import format_message
from notifier.x_client import Tweet

SAMPLE_TWEET = Tweet(
    id="20",
    text=(
        "Fed signals two more rate cuts this year as inflation cools faster than "
        "expected. Nvidia and Apple lead tech higher in premarket."
    ),
    username="setup_check",
)


def run_checks(config: Config, services, out: Callable[[str], None] = print) -> bool:
    ok = True

    def step(name: str, action: Callable[[], str]) -> object:
        nonlocal ok
        try:
            detail = action()
            out(f"✅ {name}: {detail}")
            return True
        except Exception as error:
            out(f"❌ {name}: {error}")
            ok = False
            return False

    out("✅ Settings file: loaded")

    step("Telegram bot", lambda: "@" + services.telegram.bot_username())

    def check_x() -> str:
        found = services.x.lookup_user_ids(config.accounts)
        missing = [a for a in config.accounts if a not in found]
        if missing:
            raise RuntimeError(f"not found on X: {', '.join(missing)}")
        return f"token works, found {', '.join('@' + a for a in config.accounts)}"

    step("X API", check_x)

    levels: dict[str, Levels] = {}
    if services.market is None:
        out("⏭️  IBKR prices: disabled (IBKR_ENABLED=false)")
    else:
        def check_ibkr() -> str:
            levels.update(services.market.fetch_levels(config.market_symbols))
            return ", ".join(f"{s} {lv.last:.2f}" for s, lv in levels.items())

        step("IBKR prices", check_ibkr)

    analysis = None
    if services.analyzer is None:
        out("⏭️  AI analysis: disabled (AI_PROVIDER=none)")
    else:
        def check_ai() -> str:
            nonlocal analysis
            analysis = services.analyzer.analyze(SAMPLE_TWEET, levels)
            biases = ", ".join(f"{m.symbol} {m.bias}" for m in analysis.market)
            return f"{config.ai.provider} / {services.analyzer.model} → {biases}"

        step("AI analysis", check_ai)

    def check_send() -> str:
        message = "🧪 <b>Setup check: sample alert</b>\n\n" + format_message(SAMPLE_TWEET, analysis, levels)
        services.telegram.send(message)
        return "sample message sent, check your Telegram"

    step("Telegram message", check_send)

    out("")
    out("All good! The timer will now send real alerts." if ok else "Fix the ❌ items above and run --check again.")
    return ok

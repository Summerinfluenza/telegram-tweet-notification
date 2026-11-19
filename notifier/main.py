"""Entry point.

    python -m notifier.main           check all accounts once (what the timer runs)
    python -m notifier.main --check   test every connection and send a sample message
    python -m notifier.main --notify TEXT   send TEXT to Telegram (used by auto-update)

One run:
  1. Ask X for posts newer than the last one seen, per account.
  2. If there are new posts: fetch QQQ/SPY levels from IBKR (once).
  3. For each post, oldest first: AI analysis -> Telegram message.
  4. Save which posts were sent.

If IBKR or the AI fails, the post is still sent, with a short note.
A post only counts as "seen" after Telegram accepted it, so nothing is
lost if Telegram is down - it's sent on the next run instead.
"""

from __future__ import annotations

import argparse
import html
import logging
import sys
from dataclasses import dataclass

from notifier.analysis import Analysis, Analyzer
from notifier.config import Config, ConfigError, load_config
from notifier.market_data import IbkrMarketData, Levels
from notifier.messages import format_message
from notifier.state import AccountState, State, load_state, prune_state, save_state
from notifier.telegram import TelegramNotifier
from notifier.x_client import Tweet, XClient

log = logging.getLogger("notifier")


@dataclass
class Services:
    """Everything that talks to the outside world (swapped for fakes in tests)."""
    x: XClient
    telegram: TelegramNotifier
    analyzer: Analyzer | None = None
    market: IbkrMarketData | None = None


def build_services(config: Config) -> Services:
    return Services(
        x=XClient(config.x_bearer_token),
        telegram=TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id),
        analyzer=Analyzer(config.ai, config.market_symbols) if config.ai.enabled else None,
        market=IbkrMarketData(config.ibkr) if config.ibkr.enabled else None,
    )


# ------------------------------------------------------------------ steps


def resolve_user_ids(config: Config, state: State, x: XClient) -> None:
    """Look up X user ids once per account and keep them in state."""
    missing = [u for u in config.accounts if not state.setdefault(u, AccountState()).user_id]
    if not missing:
        return
    found = x.lookup_user_ids(missing)
    for username in missing:
        if username in found:
            state[username].user_id = found[username]
        else:
            log.warning("X account @%s not found - check the spelling in X_ACCOUNTS", username)


def collect_new_tweets(config: Config, state: State, x: XClient) -> tuple[list[Tweet], bool]:
    """Fetch new posts from every account. Returns (posts oldest first, all_ok)."""
    pending: list[Tweet] = []
    ok = True
    for username in config.accounts:
        account = state[username]
        if not account.user_id:
            continue
        try:
            result = x.fetch_new_tweets(
                user_id=account.user_id,
                username=username,
                since_id=account.last_seen_id,
                include_replies=config.include_replies,
                include_reposts=config.include_reposts,
            )
        except Exception as error:  # keep checking the other accounts
            log.error("@%s: %s", username, error)
            ok = False
            continue

        if account.last_seen_id is None:
            account.last_seen_id = result.newest_id
            log.info("@%s: first run, will notify about posts from now on", username)
        elif result.tweets:
            log.info("@%s: %d new post(s)", username, len(result.tweets))
            pending.extend(result.tweets)
        elif result.newest_id:
            account.last_seen_id = result.newest_id

    pending.sort(key=lambda t: int(t.id))
    return pending, ok


def fetch_levels(config: Config, market: IbkrMarketData | None) -> tuple[dict[str, Levels], str | None]:
    if market is None:
        return {}, None
    try:
        return market.fetch_levels(config.market_symbols), None
    except Exception as error:
        log.error("IBKR: %s", error)
        return {}, "IBKR prices unavailable"


def analyze(analyzer: Analyzer | None, tweet: Tweet, levels: dict[str, Levels]) -> tuple[Analysis | None, str | None]:
    if analyzer is None:
        return None, None
    try:
        return analyzer.analyze(tweet, levels), None
    except Exception as error:
        log.error("AI analysis of %s failed: %s", tweet.url, error)
        return None, "AI analysis unavailable"


# ------------------------------------------------------------------ run


def run(config: Config, services: Services) -> bool:
    """Check all accounts once. Returns True if everything worked."""
    state = load_state(config.state_file)
    prune_state(state, config.accounts)
    ok = True
    try:
        resolve_user_ids(config, state, services.x)
        pending, ok = collect_new_tweets(config, state, services.x)
        if not pending:
            return ok

        levels, levels_note = fetch_levels(config, services.market)
        failed_accounts: set[str] = set()
        for tweet in pending:
            if tweet.username in failed_accounts:
                continue  # keep order: retry this account's posts next run
            analysis, ai_note = analyze(services.analyzer, tweet, levels)
            notes = [n for n in (levels_note, ai_note) if n]
            try:
                services.telegram.send(format_message(tweet, analysis, levels, notes))
            except Exception as error:
                log.error("Telegram: %s (will retry next run)", error)
                failed_accounts.add(tweet.username)
                ok = False
                continue
            state[tweet.username].last_seen_id = tweet.id  # only after a successful send
        return ok
    except Exception as error:
        log.error("%s", error)
        return False
    finally:
        save_state(config.state_file, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send new X posts with AI trading analysis to Telegram.")
    parser.add_argument("--check", action="store_true", help="test all connections and send a sample message")
    parser.add_argument("--notify", metavar="TEXT", help="just send TEXT to Telegram (used by auto-update)")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("ib_async").setLevel(logging.CRITICAL)  # we log our own clearer message

    try:
        config = load_config()
    except ConfigError as error:
        log.error("Setting problem: %s", error)
        return 2

    services = build_services(config)
    if args.notify:
        services.telegram.send(html.escape(args.notify, quote=False))
        return 0
    if args.check:
        from notifier.check import run_checks

        return 0 if run_checks(config, services) else 1
    return 0 if run(config, services) else 1


if __name__ == "__main__":
    sys.exit(main())

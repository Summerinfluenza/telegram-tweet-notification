"""Entry point: check every account once, notify about new posts, save state.

Run with:  python -m notifier.main
"""

from __future__ import annotations

import logging
import sys

from notifier.config import Config, ConfigError, load_config
from notifier.state import AccountState, State, load_state, save_state
from notifier.telegram import TelegramNotifier, format_tweet_message
from notifier.x_client import XClient

log = logging.getLogger("notifier")


def resolve_user_ids(config: Config, state: State, x_client: XClient) -> None:
    """Look up X user ids once per account and keep them in state."""
    missing = [u for u in config.accounts if not state.setdefault(u, AccountState()).user_id]
    if not missing:
        return
    found = x_client.lookup_user_ids(missing)
    for username in missing:
        if username in found:
            state[username].user_id = found[username]
        else:
            log.warning("X account not found: @%s", username)


def check_account(
    username: str, account: AccountState, config: Config,
    x_client: XClient, notifier: TelegramNotifier,
) -> int:
    """Notify about new posts from one account. Returns how many were sent."""
    result = x_client.fetch_new_tweets(
        user_id=account.user_id,
        username=username,
        since_id=account.last_seen_id,
        include_replies=config.include_replies,
        include_reposts=config.include_reposts,
    )

    if account.last_seen_id is None:
        account.last_seen_id = result.newest_id
        log.info("@%s: first run, starting from now", username)
        return 0

    sent = 0
    for tweet in result.tweets:
        notifier.send(format_tweet_message(tweet))
        account.last_seen_id = tweet.id  # advance only after a successful send
        sent += 1
    if result.newest_id and not result.tweets:
        account.last_seen_id = result.newest_id
    log.info("@%s: %d new post(s)", username, sent)
    return sent


def run(config: Config, x_client: XClient, notifier: TelegramNotifier) -> bool:
    """Check all accounts. Returns True if everything worked."""
    state = load_state(config.state_file)
    ok = True
    try:
        resolve_user_ids(config, state, x_client)
        for username in config.accounts:
            account = state[username]
            if not account.user_id:
                continue
            try:
                check_account(username, account, config, x_client, notifier)
            except Exception as error:  # keep checking the other accounts
                log.error("@%s: %s", username, error)
                ok = False
    finally:
        save_state(config.state_file, state)
    return ok


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        config = load_config()
    except ConfigError as error:
        log.error("%s (see README: 'Secrets')", error)
        return 2

    x_client = XClient(config.x_bearer_token)
    notifier = TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id)
    return 0 if run(config, x_client, notifier) else 1


if __name__ == "__main__":
    sys.exit(main())

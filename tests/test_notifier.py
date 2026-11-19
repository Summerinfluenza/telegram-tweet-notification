"""Tests run without network: X and Telegram are replaced by fakes."""

from pathlib import Path

import pytest

from notifier.config import ConfigError, load_config
from notifier.main import run
from notifier.state import AccountState, load_state, save_state
from notifier.telegram import format_tweet_message
from notifier.x_client import FetchResult, Tweet

BASE_ENV = {
    "X_BEARER_TOKEN": "x-token",
    "TELEGRAM_BOT_TOKEN": "tg-token",
    "TELEGRAM_CHAT_ID": "123",
    "X_ACCOUNTS": "@Alice, bob ,",
}


class FakeX:
    def __init__(self, tweets_by_user=None, newest_by_user=None):
        self.tweets_by_user = tweets_by_user or {}
        self.newest_by_user = newest_by_user or {}
        self.since_ids = {}

    def lookup_user_ids(self, usernames):
        return {u: f"id-{u}" for u in usernames}

    def fetch_new_tweets(self, user_id, username, since_id, **_):
        self.since_ids[username] = since_id
        if since_id is None:
            return FetchResult([], self.newest_by_user.get(username))
        tweets = self.tweets_by_user.get(username, [])
        return FetchResult(tweets, tweets[-1].id if tweets else None)


class FakeTelegram:
    def __init__(self, fail_after=None):
        self.sent = []
        self.fail_after = fail_after

    def send(self, text):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise RuntimeError("telegram down")
        self.sent.append(text)


def make_config(tmp_path: Path):
    return load_config({**BASE_ENV, "STATE_FILE": str(tmp_path / "state.json")})


def test_config_normalizes_accounts(tmp_path):
    assert make_config(tmp_path).accounts == ("alice", "bob")


def test_config_rejects_placeholder():
    with pytest.raises(ConfigError, match="X_BEARER_TOKEN"):
        load_config({**BASE_ENV, "X_BEARER_TOKEN": "REPLACE_ME"})


def test_state_round_trip(tmp_path):
    path = tmp_path / "state.json"
    save_state(path, {"alice": AccountState("1", "99")})
    assert load_state(path) == {"alice": AccountState("1", "99")}


def test_message_escapes_html():
    message = format_tweet_message(Tweet("5", "a < b & c", "alice"))
    assert "a &lt; b &amp; c" in message
    assert "https://x.com/alice/status/5" in message


def test_first_run_sets_baseline_without_notifying(tmp_path):
    config = make_config(tmp_path)
    telegram = FakeTelegram()
    assert run(config, FakeX(newest_by_user={"alice": "100"}), telegram)
    assert telegram.sent == []
    assert load_state(config.state_file)["alice"].last_seen_id == "100"


def test_new_posts_are_sent_in_order_and_state_advances(tmp_path):
    config = make_config(tmp_path)
    save_state(config.state_file, {
        "alice": AccountState("id-alice", "100"),
        "bob": AccountState("id-bob", "200"),
    })
    x = FakeX(tweets_by_user={"alice": [Tweet("101", "first", "alice"), Tweet("102", "second", "alice")]})
    telegram = FakeTelegram()

    assert run(config, x, telegram)
    assert x.since_ids == {"alice": "100", "bob": "200"}
    assert ["first" in telegram.sent[0], "second" in telegram.sent[1]] == [True, True]
    assert load_state(config.state_file)["alice"].last_seen_id == "102"


def test_failed_send_is_retried_next_run(tmp_path):
    config = make_config(tmp_path)
    save_state(config.state_file, {
        "alice": AccountState("id-alice", "100"),
        "bob": AccountState("id-bob", "200"),
    })
    x = FakeX(tweets_by_user={"alice": [Tweet("101", "one", "alice"), Tweet("102", "two", "alice")]})

    assert not run(config, x, FakeTelegram(fail_after=1))
    # Only the post that was actually delivered counts as seen.
    assert load_state(config.state_file)["alice"].last_seen_id == "101"

"""Sends messages through a Telegram bot."""

from __future__ import annotations

import html

import requests

from notifier.x_client import Tweet

TIMEOUT_SECONDS = 20
# Telegram's limit is 4096 characters; leave room for header and link.
MAX_TEXT_LENGTH = 3500


class TelegramError(Exception):
    """Raised when Telegram refuses a message."""


def format_tweet_message(tweet: Tweet) -> str:
    text = tweet.text
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH] + "…"
    return (
        f"🐦 <b>@{html.escape(tweet.username)}</b>\n\n"
        f"{html.escape(text)}\n\n"
        f'<a href="{tweet.url}">Open on X</a>'
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str, session: requests.Session | None = None):
        self._url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self._chat_id = chat_id
        self._session = session or requests.Session()

    def send(self, text: str) -> None:
        response = self._session.post(
            self._url,
            json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
            timeout=TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            # Don't include the URL: it contains the bot token.
            raise TelegramError(f"Telegram error {response.status_code}: {response.text[:300]}")

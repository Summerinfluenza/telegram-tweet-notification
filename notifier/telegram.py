"""Sends messages through a Telegram bot."""

from __future__ import annotations

from typing import Callable

import requests

from notifier.http_retry import request_with_retry

API_URL = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(Exception):
    """Telegram refused a request. The message explains what to do."""


class TelegramNotifier:
    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self._token = bot_token
        self._chat_id = chat_id
        self._session = session or requests.Session()
        self._retry_kwargs = {"sleep": sleep} if sleep else {}

    def _call(self, method: str, payload: dict | None = None) -> dict:
        response = request_with_retry(
            self._session, "POST", API_URL.format(token=self._token, method=method),
            json=payload or {}, **self._retry_kwargs,
        )
        if response.status_code == 401:
            raise TelegramError("Telegram rejected the bot token (401). Check TELEGRAM_BOT_TOKEN.")
        if response.status_code == 400 and "chat not found" in response.text.lower():
            raise TelegramError(
                "Telegram can't find the chat. Check TELEGRAM_CHAT_ID, and send your bot "
                "a message first (bots can't start conversations)."
            )
        if response.status_code == 403:
            raise TelegramError("The bot is blocked or not in the chat (403). Unblock it or add it again.")
        if response.status_code >= 400:
            # Never include the URL: it contains the bot token.
            raise TelegramError(f"Telegram error {response.status_code}: {response.text[:300]}")
        return response.json()

    def send(self, html_text: str) -> None:
        self._call("sendMessage", {
            "chat_id": self._chat_id,
            "text": html_text,
            "parse_mode": "HTML",
            "link_preview_options": {"is_disabled": True},
        })

    def bot_username(self) -> str:
        """Used by the setup check to confirm the token works."""
        return self._call("getMe")["result"]["username"]

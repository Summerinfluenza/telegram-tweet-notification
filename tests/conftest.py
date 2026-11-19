"""Shared test helpers. Nothing in the tests touches the network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from notifier.config import load_config


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=None, headers=None):
        self.status_code = status_code
        self._json = json_data
        self.text = text if text is not None else json.dumps(json_data or {})
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class FakeSession:
    """Returns queued responses in order and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict] = []
        self.headers: dict = {}

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def no_sleep(_seconds):
    pass


BASE_ENV = {
    "X_BEARER_TOKEN": "x-token",
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "TELEGRAM_CHAT_ID": "123456",
    "X_ACCOUNTS": "alice,bob",
    "AI_PROVIDER": "none",
    "IBKR_ENABLED": "false",
}


@pytest.fixture
def make_config(tmp_path: Path):
    def _make(**overrides):
        env = {**BASE_ENV, "STATE_FILE": str(tmp_path / "state.json"), **overrides}
        return load_config(env)

    return _make

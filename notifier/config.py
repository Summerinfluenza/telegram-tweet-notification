"""Reads all settings from environment variables.

In GitHub Actions these come from repository secrets (see README).
Locally you can put them in a `.env` file (see `.env.example`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PLACEHOLDER = "REPLACE_ME"


class ConfigError(Exception):
    """Raised when a required setting is missing or invalid."""


@dataclass(frozen=True)
class Config:
    x_bearer_token: str
    telegram_bot_token: str
    telegram_chat_id: str
    accounts: tuple[str, ...]
    state_file: Path
    include_replies: bool
    include_reposts: bool


def normalize_username(raw: str) -> str:
    """'@ElonMusk ' -> 'elonmusk'. X usernames are case-insensitive."""
    return raw.strip().lstrip("@").lower()


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value or value == PLACEHOLDER:
        raise ConfigError(f"Missing setting: {name}")
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name, "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    accounts = tuple(
        name
        for name in (normalize_username(a) for a in _required(env, "X_ACCOUNTS").split(","))
        if name
    )
    if not accounts:
        raise ConfigError("X_ACCOUNTS must list at least one username")

    return Config(
        x_bearer_token=_required(env, "X_BEARER_TOKEN"),
        telegram_bot_token=_required(env, "TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required(env, "TELEGRAM_CHAT_ID"),
        accounts=accounts,
        state_file=Path(env.get("STATE_FILE", "state.json")),
        include_replies=_flag(env, "INCLUDE_REPLIES", default=False),
        include_reposts=_flag(env, "INCLUDE_REPOSTS", default=False),
    )

"""Reads and validates all settings from environment variables.

On the server they come from /etc/telegram-tweet-notification.env.
Every error message says which setting is wrong and how to fix it,
so a typo never turns into a confusing crash later.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PLACEHOLDER = "REPLACE_ME"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{1,15}$")
CHAT_ID_PATTERN = re.compile(r"^(-?\d+|@[A-Za-z0-9_]{5,})$")
SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z.]{0,5}$")

AI_PROVIDERS = ("none", "deepseek", "gemini", "openai")


class ConfigError(Exception):
    """A setting is missing or invalid. The message explains the fix."""


@dataclass(frozen=True)
class AiSettings:
    provider: str              # one of AI_PROVIDERS
    api_key: str | None
    model: str | None          # None = provider default
    base_url: str | None       # None = provider default

    @property
    def enabled(self) -> bool:
        return self.provider != "none"


@dataclass(frozen=True)
class IbkrSettings:
    enabled: bool
    host: str
    port: int
    client_id: int


@dataclass(frozen=True)
class Config:
    x_bearer_token: str
    telegram_bot_token: str
    telegram_chat_id: str
    accounts: tuple[str, ...]
    market_symbols: tuple[str, ...]
    ai: AiSettings
    ibkr: IbkrSettings
    state_file: Path
    include_replies: bool
    include_reposts: bool


# ---------------------------------------------------------------- helpers


def _clean(value: str | None) -> str:
    """Trim whitespace and surrounding quotes people often paste in."""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1].strip()
    return value


def _get(env: Mapping[str, str], name: str) -> str:
    value = _clean(env.get(name))
    return "" if value == PLACEHOLDER else value


def _required(env: Mapping[str, str], name: str, hint: str) -> str:
    value = _get(env, name)
    if not value:
        raise ConfigError(f"{name} is not set. {hint}")
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = _get(env, name).lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false (got {value!r}).")


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    value = _get(env, name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise ConfigError(f"{name} must be a whole number (got {value!r}).") from None


def normalize_username(raw: str) -> str:
    """'@ElonMusk ' -> 'elonmusk'. X usernames are case-insensitive."""
    return raw.strip().lstrip("@").lower()


def _parse_accounts(raw: str) -> tuple[str, ...]:
    accounts: list[str] = []
    for name in (normalize_username(part) for part in raw.split(",")):
        if not name:
            continue
        if not USERNAME_PATTERN.match(name):
            raise ConfigError(
                f"X_ACCOUNTS contains an invalid username: {name!r}. "
                "Use plain usernames separated by commas, e.g. nasa,spacex"
            )
        if name not in accounts:
            accounts.append(name)
    if not accounts:
        raise ConfigError("X_ACCOUNTS must list at least one username, e.g. nasa,spacex")
    return tuple(accounts)


def _parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in raw.split(",") if s.strip()))
    bad = [s for s in symbols if not SYMBOL_PATTERN.match(s)]
    if bad or not symbols:
        raise ConfigError(f"MARKET_SYMBOLS must be tickers like QQQ,SPY (got {raw!r}).")
    return symbols


def _parse_ai(env: Mapping[str, str]) -> AiSettings:
    provider = (_get(env, "AI_PROVIDER") or "none").lower()
    if provider not in AI_PROVIDERS:
        raise ConfigError(f"AI_PROVIDER must be one of {', '.join(AI_PROVIDERS)} (got {provider!r}).")
    api_key = _get(env, "AI_API_KEY") or None
    if provider != "none" and not api_key:
        raise ConfigError(
            f"AI_API_KEY is not set, but AI_PROVIDER is {provider}. "
            "Add the key, or set AI_PROVIDER=none to send posts without analysis."
        )
    return AiSettings(
        provider=provider,
        api_key=api_key,
        model=_get(env, "AI_MODEL") or None,
        base_url=_get(env, "AI_BASE_URL") or None,
    )


def _parse_ibkr(env: Mapping[str, str]) -> IbkrSettings:
    port = _int(env, "IBKR_PORT", 4001)
    if not 1 <= port <= 65535:
        raise ConfigError(f"IBKR_PORT must be between 1 and 65535 (got {port}).")
    return IbkrSettings(
        enabled=_flag(env, "IBKR_ENABLED", default=True),
        host=_get(env, "IBKR_HOST") or "127.0.0.1",
        port=port,
        client_id=_int(env, "IBKR_CLIENT_ID", 77),
    )


# ---------------------------------------------------------------- main


def load_config(env: Mapping[str, str] = os.environ) -> Config:
    bearer = _required(env, "X_BEARER_TOKEN", "Get it at console.x.com (see docs/setup-x.md).")
    if bearer.lower().startswith("bearer "):
        bearer = bearer[7:].strip()  # people often paste the whole header

    chat_id = _required(env, "TELEGRAM_CHAT_ID", "See docs/setup-telegram.md.")
    if not CHAT_ID_PATTERN.match(chat_id):
        raise ConfigError(
            f"TELEGRAM_CHAT_ID looks wrong ({chat_id!r}). "
            "It should be a number like 123456789 (or -100... for groups)."
        )

    bot_token = _required(env, "TELEGRAM_BOT_TOKEN", "Get it from @BotFather (see docs/setup-telegram.md).")
    if ":" not in bot_token:
        raise ConfigError("TELEGRAM_BOT_TOKEN looks wrong. It should look like 123456:ABC-DEF...")

    return Config(
        x_bearer_token=bearer,
        telegram_bot_token=bot_token,
        telegram_chat_id=chat_id,
        accounts=_parse_accounts(_required(env, "X_ACCOUNTS", "List usernames, e.g. nasa,spacex")),
        market_symbols=_parse_symbols(_get(env, "MARKET_SYMBOLS") or "QQQ,SPY"),
        ai=_parse_ai(env),
        ibkr=_parse_ibkr(env),
        state_file=Path(_get(env, "STATE_FILE") or "state.json"),
        include_replies=_flag(env, "INCLUDE_REPLIES", default=False),
        include_reposts=_flag(env, "INCLUDE_REPOSTS", default=False),
    )

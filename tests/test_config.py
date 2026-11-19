import pytest

from notifier.config import ConfigError, load_config
from tests.conftest import BASE_ENV


def load(**overrides):
    return load_config({**BASE_ENV, **overrides})


def test_minimal_config_has_sensible_defaults():
    config = load_config({k: v for k, v in BASE_ENV.items() if k not in ("AI_PROVIDER", "IBKR_ENABLED")})
    assert config.accounts == ("alice", "bob")
    assert config.market_symbols == ("QQQ", "SPY")
    assert config.ai.provider == "none" and not config.ai.enabled
    assert config.ibkr.enabled and config.ibkr.port == 4001 and config.ibkr.host == "127.0.0.1"
    assert not config.include_replies and not config.include_reposts


def test_accounts_are_normalized_and_deduplicated():
    assert load(X_ACCOUNTS=" @Alice, BOB ,alice,, ").accounts == ("alice", "bob")


@pytest.mark.parametrize("bad", ["not a name", "way_too_long_username_here", "a-b"])
def test_invalid_usernames_are_rejected(bad):
    with pytest.raises(ConfigError, match="invalid username"):
        load(X_ACCOUNTS=bad)


@pytest.mark.parametrize("name", ["X_BEARER_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "X_ACCOUNTS"])
def test_placeholder_counts_as_missing(name):
    with pytest.raises(ConfigError, match=name):
        load(**{name: "REPLACE_ME"})


def test_quotes_and_bearer_prefix_are_stripped():
    config = load(X_BEARER_TOKEN='"Bearer abc123"', TELEGRAM_CHAT_ID="'987'")
    assert config.x_bearer_token == "abc123"
    assert config.telegram_chat_id == "987"


@pytest.mark.parametrize("chat_id", ["123", "-1001234567890", "@mychannel"])
def test_valid_chat_ids(chat_id):
    assert load(TELEGRAM_CHAT_ID=chat_id).telegram_chat_id == chat_id


@pytest.mark.parametrize("chat_id", ["abc", "12 34", "https://t.me/x"])
def test_invalid_chat_ids(chat_id):
    with pytest.raises(ConfigError, match="TELEGRAM_CHAT_ID"):
        load(TELEGRAM_CHAT_ID=chat_id)


def test_bot_token_must_look_like_a_token():
    with pytest.raises(ConfigError, match="TELEGRAM_BOT_TOKEN"):
        load(TELEGRAM_BOT_TOKEN="justtext")


def test_ai_provider_needs_a_key():
    with pytest.raises(ConfigError, match="AI_API_KEY"):
        load(AI_PROVIDER="deepseek")


def test_unknown_ai_provider_is_rejected():
    with pytest.raises(ConfigError, match="AI_PROVIDER"):
        load(AI_PROVIDER="claude-9000", AI_API_KEY="k")


def test_ai_settings_are_read():
    ai = load(AI_PROVIDER="Gemini", AI_API_KEY="k", AI_MODEL="m1").ai
    assert (ai.provider, ai.api_key, ai.model, ai.enabled) == ("gemini", "k", "m1", True)


def test_bad_flag_value_is_rejected():
    with pytest.raises(ConfigError, match="INCLUDE_REPLIES"):
        load(INCLUDE_REPLIES="maybe")


@pytest.mark.parametrize("port", ["abc", "0", "70000"])
def test_bad_ibkr_port_is_rejected(port):
    with pytest.raises(ConfigError, match="IBKR_PORT"):
        load(IBKR_PORT=port)


def test_market_symbols_can_be_changed():
    assert load(MARKET_SYMBOLS="qqq, iwm").market_symbols == ("QQQ", "IWM")


def test_bad_market_symbols_are_rejected():
    with pytest.raises(ConfigError, match="MARKET_SYMBOLS"):
        load(MARKET_SYMBOLS="QQQ,not a ticker")

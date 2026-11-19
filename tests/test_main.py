"""End-to-end behaviour of one run, with every outside service faked."""

from notifier.analysis import Analysis, MarketView
from notifier.check import run_checks
from notifier.main import Services, main, run
from notifier.market_data import Levels, MarketDataError
from notifier.state import AccountState, load_state, save_state
from notifier.x_client import FetchResult, Tweet

QQQ = Levels(symbol="QQQ", last=512.3, change_pct=0.4, prev_high=514.2, prev_low=505.1, high_20d=520.0, low_20d=498.0, sma_50=505.0, sma_200=470.0)


class FakeX:
    def __init__(self, tweets=None, newest=None, fail_for=()):
        self.tweets = tweets or {}
        self.newest = newest or {}
        self.fail_for = set(fail_for)
        self.since_ids = {}
        self.lookups = []

    def lookup_user_ids(self, usernames):
        self.lookups.append(list(usernames))
        return {u: f"id-{u}" for u in usernames if u != "ghost"}

    def fetch_new_tweets(self, user_id, username, since_id, **_):
        if username in self.fail_for:
            raise RuntimeError("X down")
        self.since_ids[username] = since_id
        if since_id is None:
            return FetchResult([], self.newest.get(username))
        tweets = self.tweets.get(username, [])
        return FetchResult(tweets, tweets[-1].id if tweets else None)


class FakeTelegram:
    def __init__(self, fail_on_text=None):
        self.sent = []
        self.fail_on_text = fail_on_text

    def send(self, text):
        if self.fail_on_text and self.fail_on_text in text:
            raise RuntimeError("telegram down")
        self.sent.append(text)

    def bot_username(self):
        return "mybot"


class FakeAnalyzer:
    model = "fake-model"

    def __init__(self, fail=False):
        self.fail = fail
        self.seen_levels = []

    def analyze(self, tweet, levels):
        self.seen_levels.append(levels)
        if self.fail:
            raise RuntimeError("AI down")
        return Analysis(f"Summary of {tweet.text}", True, [MarketView("QQQ", "bullish", "r"), MarketView("SPY", "bearish", "r")])


class FakeMarket:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def fetch_levels(self, symbols):
        self.calls += 1
        if self.fail:
            raise MarketDataError("gateway off")
        return {"QQQ": QQQ}


def seed(config, **accounts):
    save_state(config.state_file, {u: AccountState(f"id-{u}", last) for u, last in accounts.items()})


def t(id_, user, text=None):
    return Tweet(id_, text or f"post {id_}", user)


# ---------------------------------------------------------------- run


def test_first_run_sets_baseline_without_notifying(make_config):
    config = make_config()
    market = FakeMarket()
    services = Services(FakeX(newest={"alice": "100", "bob": "200"}), FakeTelegram(), market=market)
    assert run(config, services)
    assert services.telegram.sent == []
    assert market.calls == 0  # no new posts: IBKR is not even contacted
    state = load_state(config.state_file)
    assert (state["alice"].last_seen_id, state["bob"].last_seen_id) == ("100", "200")


def test_user_ids_are_looked_up_only_once(make_config):
    config = make_config()
    x = FakeX(newest={"alice": "1", "bob": "2"})
    run(config, Services(x, FakeTelegram()))
    run(config, Services(x, FakeTelegram()))
    assert x.lookups == [["alice", "bob"]]


def test_posts_from_all_accounts_are_sent_oldest_first(make_config):
    config = make_config()
    seed(config, alice="100", bob="100")
    x = FakeX({"alice": [t("103", "alice")], "bob": [t("101", "bob"), t("102", "bob")]})
    services = Services(x, FakeTelegram())
    assert run(config, services)
    assert ["101" in m for m in services.telegram.sent] == [True, False, False]
    assert "102" in services.telegram.sent[1] and "103" in services.telegram.sent[2]
    state = load_state(config.state_file)
    assert (state["alice"].last_seen_id, state["bob"].last_seen_id) == ("103", "102")


def test_full_pipeline_with_ai_and_ibkr(make_config):
    config = make_config()
    seed(config, alice="100", bob="100")
    market, analyzer = FakeMarket(), FakeAnalyzer()
    services = Services(FakeX({"alice": [t("101", "alice"), t("102", "alice")]}), FakeTelegram(), analyzer, market)
    assert run(config, services)
    assert market.calls == 1  # fetched once per run, not per post
    assert analyzer.seen_levels == [{"QQQ": QQQ}, {"QQQ": QQQ}]
    assert "📝 Summary of post 101" in services.telegram.sent[0]
    assert "512.30" in services.telegram.sent[0]


def test_ibkr_failure_still_sends_with_note(make_config):
    config = make_config()
    seed(config, alice="100", bob="100")
    services = Services(FakeX({"alice": [t("101", "alice")]}), FakeTelegram(), FakeAnalyzer(), FakeMarket(fail=True))
    assert run(config, services)
    assert "IBKR prices unavailable" in services.telegram.sent[0]
    assert "📝 Summary" in services.telegram.sent[0]


def test_ai_failure_still_sends_raw_post_with_note(make_config):
    config = make_config()
    seed(config, alice="100", bob="100")
    services = Services(FakeX({"alice": [t("101", "alice", "raw text")]}), FakeTelegram(), FakeAnalyzer(fail=True))
    assert run(config, services)
    assert "raw text" in services.telegram.sent[0]
    assert "AI analysis unavailable" in services.telegram.sent[0]


def test_telegram_failure_keeps_post_for_next_run_and_preserves_order(make_config):
    config = make_config()
    seed(config, alice="100", bob="100")
    x = FakeX({"alice": [t("101", "alice"), t("102", "alice", "FAIL"), t("103", "alice")],
               "bob": [t("104", "bob")]})
    telegram = FakeTelegram(fail_on_text="FAIL")
    assert not run(config, Services(x, telegram))
    state = load_state(config.state_file)
    assert state["alice"].last_seen_id == "101"   # 102 retried next run, 103 not skipped ahead
    assert state["bob"].last_seen_id == "104"     # other accounts unaffected
    assert len(telegram.sent) == 2


def test_x_failure_for_one_account_does_not_stop_others(make_config):
    config = make_config()
    seed(config, alice="100", bob="100")
    services = Services(FakeX({"bob": [t("101", "bob")]}, fail_for={"alice"}), FakeTelegram())
    assert not run(config, services)
    assert len(services.telegram.sent) == 1


def test_unknown_account_is_skipped(make_config):
    config = make_config(X_ACCOUNTS="alice,ghost")
    services = Services(FakeX(newest={"alice": "1"}), FakeTelegram())
    assert run(config, services)
    assert load_state(config.state_file)["ghost"].user_id is None


def test_removed_accounts_are_forgotten(make_config):
    config = make_config(X_ACCOUNTS="alice")
    seed(config, alice="100", old="5")
    run(config, Services(FakeX(), FakeTelegram()))
    assert list(load_state(config.state_file)) == ["alice"]


def test_main_returns_2_on_bad_settings(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    assert main([]) == 2


# ---------------------------------------------------------------- --check


def test_check_all_good_sends_sample(make_config):
    config = make_config()
    lines = []
    services = Services(FakeX(), FakeTelegram(), FakeAnalyzer(), FakeMarket())
    assert run_checks(config, services, out=lines.append)
    assert any(line.startswith("✅ IBKR prices: QQQ 512.30") for line in lines)
    assert any("fake-model → QQQ bullish, SPY bearish" in line for line in lines)
    assert "Setup check" in services.telegram.sent[0]


def test_check_reports_failures_and_continues(make_config):
    config = make_config(X_ACCOUNTS="alice,ghost")
    lines = []
    services = Services(FakeX(), FakeTelegram(), FakeAnalyzer(fail=True), FakeMarket(fail=True))
    assert not run_checks(config, services, out=lines.append)
    assert any(line.startswith("❌ X API: not found on X: ghost") for line in lines)
    assert any(line.startswith("❌ IBKR prices") for line in lines)
    assert any(line.startswith("❌ AI analysis") for line in lines)
    assert len(services.telegram.sent) == 1  # sample still sent, without analysis


def test_check_skips_disabled_parts(make_config):
    lines = []
    assert run_checks(make_config(), Services(FakeX(), FakeTelegram()), out=lines.append)
    assert any("disabled (IBKR_ENABLED=false)" in line for line in lines)
    assert any("disabled (AI_PROVIDER=none)" in line for line in lines)

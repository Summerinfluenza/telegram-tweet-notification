import pytest

from notifier.x_client import XApiError, XClient
from tests.conftest import FakeResponse, FakeSession, no_sleep


def client(*responses):
    session = FakeSession(*responses)
    return XClient("tok", session=session, sleep=no_sleep), session


def test_sends_bearer_token():
    _, session = client()
    assert session.headers["Authorization"] == "Bearer tok"


def test_lookup_user_ids_lowercases_and_skips_unknown():
    x, session = client(FakeResponse(200, {"data": [{"id": "1", "username": "Alice"}]}))
    assert x.lookup_user_ids(["alice", "ghost"]) == {"alice": "1"}
    assert session.calls[0]["params"] == {"usernames": "alice,ghost"}


def test_baseline_run_returns_no_tweets_but_newest_id():
    x, session = client(FakeResponse(200, {"data": [{"id": "9", "text": "old"}], "meta": {"newest_id": "9"}}))
    result = x.fetch_new_tweets("u1", "alice", since_id=None)
    assert result.tweets == [] and result.newest_id == "9"
    assert session.calls[0]["params"]["max_results"] == 5


def test_new_tweets_are_oldest_first_and_filters_are_sent():
    x, session = client(FakeResponse(200, {
        "data": [{"id": "12", "text": "b"}, {"id": "11", "text": "a"}],
        "meta": {"newest_id": "12"},
    }))
    result = x.fetch_new_tweets("u1", "alice", since_id="10")
    assert [t.id for t in result.tweets] == ["11", "12"]
    params = session.calls[0]["params"]
    assert params["since_id"] == "10"
    assert params["exclude"] == "replies,retweets"
    assert session.calls[0]["url"].endswith("/users/u1/tweets")


def test_include_flags_remove_exclude_param():
    x, session = client(FakeResponse(200, {"meta": {}}))
    x.fetch_new_tweets("u1", "alice", since_id="10", include_replies=True, include_reposts=True)
    assert "exclude" not in session.calls[0]["params"]


def test_long_posts_use_note_tweet_text():
    x, _ = client(FakeResponse(200, {
        "data": [{"id": "11", "text": "short…", "note_tweet": {"text": "the full long text"}}],
        "meta": {"newest_id": "11"},
    }))
    assert x.fetch_new_tweets("u1", "alice", "10").tweets[0].text == "the full long text"


def test_follows_pagination():
    x, session = client(
        FakeResponse(200, {"data": [{"id": "13", "text": "c"}], "meta": {"newest_id": "13", "next_token": "p2"}}),
        FakeResponse(200, {"data": [{"id": "11", "text": "a"}], "meta": {}}),
    )
    result = x.fetch_new_tweets("u1", "alice", "10")
    assert [t.id for t in result.tweets] == ["11", "13"]
    assert result.newest_id == "13"
    assert session.calls[1]["params"]["pagination_token"] == "p2"


def test_tweet_url():
    x, _ = client(FakeResponse(200, {"data": [{"id": "11", "text": "a"}], "meta": {}}))
    assert x.fetch_new_tweets("u1", "alice", "10").tweets[0].url == "https://x.com/alice/status/11"


@pytest.mark.parametrize("status,hint", [(401, "X_BEARER_TOKEN"), (402, "credits"), (403, "billing")])
def test_friendly_errors(status, hint):
    x, _ = client(FakeResponse(status, text="nope"))
    with pytest.raises(XApiError, match=hint):
        x.lookup_user_ids(["alice"])

"""Minimal client for the two X API v2 endpoints this bot needs.

Cost notes (pay-per-use): X bills per post/user *returned*. Asking for
posts with `since_id` returns nothing when there is nothing new, so
quiet periods cost (almost) nothing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Iterable

import requests

from notifier.http_retry import request_with_retry

log = logging.getLogger(__name__)

BASE_URL = "https://api.x.com/2"

# First run for an account: only record its newest post, so you are not
# flooded with old posts. 5 is the smallest number the API allows.
BASELINE_MAX_RESULTS = 5
# Later runs: up to PAGE_SIZE x MAX_PAGES new posts per account per run.
PAGE_SIZE = 100
MAX_PAGES = 3

FRIENDLY_ERRORS = {
    401: "X rejected the bearer token (401). Check X_BEARER_TOKEN.",
    402: "X API credits are used up (402). Top up at console.x.com > Billing.",
    403: "X refused access (403). Check that your app is in a project with billing enabled.",
    429: "X rate limit hit (429). The bot will try again next run.",
}


class XApiError(Exception):
    """The X API returned an error. The message explains what to do."""


@dataclass(frozen=True)
class Tweet:
    id: str
    text: str
    username: str
    created_at: str | None = None

    @property
    def url(self) -> str:
        return f"https://x.com/{self.username}/status/{self.id}"


@dataclass(frozen=True)
class FetchResult:
    tweets: list[Tweet]       # oldest first
    newest_id: str | None     # None when nothing new


class XClient:
    def __init__(
        self,
        bearer_token: str,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] | None = None,
    ):
        self._session = session or requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {bearer_token}"})
        self._retry_kwargs = {"sleep": sleep} if sleep else {}

    def _get(self, path: str, params: dict) -> dict:
        response = request_with_retry(
            self._session, "GET", f"{BASE_URL}{path}", params=params, **self._retry_kwargs
        )
        if response.status_code >= 400:
            message = FRIENDLY_ERRORS.get(response.status_code)
            raise XApiError(message or f"X API error {response.status_code}: {response.text[:300]}")
        return response.json()

    def lookup_user_ids(self, usernames: Iterable[str]) -> dict[str, str]:
        """Return {lowercase username: user id}. Unknown usernames are left out."""
        usernames = list(usernames)
        if not usernames:
            return {}
        body = self._get("/users/by", {"usernames": ",".join(usernames)})
        return {user["username"].lower(): user["id"] for user in body.get("data", [])}

    def fetch_new_tweets(
        self,
        user_id: str,
        username: str,
        since_id: str | None,
        include_replies: bool = False,
        include_reposts: bool = False,
    ) -> FetchResult:
        params: dict = {"tweet.fields": "created_at,note_tweet"}
        excluded = [
            name
            for name, include in (("replies", include_replies), ("retweets", include_reposts))
            if not include
        ]
        if excluded:
            params["exclude"] = ",".join(excluded)

        if since_id is None:
            # Baseline run: remember where we are, but notify about nothing.
            body = self._get(f"/users/{user_id}/tweets", {**params, "max_results": BASELINE_MAX_RESULTS})
            return FetchResult(tweets=[], newest_id=body.get("meta", {}).get("newest_id"))

        params.update({"since_id": since_id, "max_results": PAGE_SIZE})
        raw_tweets: list[dict] = []
        newest_id = None
        for _ in range(MAX_PAGES):
            body = self._get(f"/users/{user_id}/tweets", params)
            meta = body.get("meta", {})
            newest_id = newest_id or meta.get("newest_id")
            raw_tweets.extend(body.get("data", []))
            next_token = meta.get("next_token")
            if not next_token:
                break
            params["pagination_token"] = next_token
        else:
            log.warning("@%s posted more than %d times since last run; older ones skipped",
                        username, PAGE_SIZE * MAX_PAGES)

        tweets = [self._to_tweet(t, username) for t in raw_tweets]
        tweets.sort(key=lambda t: int(t.id))  # oldest first = posting order
        return FetchResult(tweets=tweets, newest_id=newest_id)

    @staticmethod
    def _to_tweet(raw: dict, username: str) -> Tweet:
        # Long posts (over 280 chars) keep their full text in note_tweet.
        full_text = (raw.get("note_tweet") or {}).get("text") or raw["text"]
        return Tweet(id=raw["id"], text=full_text, username=username, created_at=raw.get("created_at"))

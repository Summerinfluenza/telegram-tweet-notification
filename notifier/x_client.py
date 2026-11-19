"""Minimal client for the two X API v2 endpoints this bot needs.

Cost notes (pay-per-use): X bills per post/user *returned*. Asking for
posts with `since_id` returns nothing when there is nothing new, so
quiet periods cost (almost) nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import requests

BASE_URL = "https://api.x.com/2"
TIMEOUT_SECONDS = 20

# On the very first run for an account we only record its newest post,
# so you are not flooded with old posts. 5 is the API's minimum.
BASELINE_MAX_RESULTS = 5
# Max new posts fetched per account per run.
MAX_RESULTS = 20


class XApiError(Exception):
    """Raised when the X API returns an error."""


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
    tweets: list[Tweet]          # oldest first
    newest_id: str | None        # None when nothing new


class XClient:
    def __init__(self, bearer_token: str, session: requests.Session | None = None):
        self._session = session or requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {bearer_token}"})

    def _get(self, path: str, params: dict) -> dict:
        response = self._session.get(f"{BASE_URL}{path}", params=params, timeout=TIMEOUT_SECONDS)
        if response.status_code == 429:
            raise XApiError("Rate limited by X (HTTP 429). Will retry next run.")
        if response.status_code >= 400:
            raise XApiError(f"X API error {response.status_code}: {response.text[:300]}")
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
        params: dict = {
            "tweet.fields": "created_at",
            "max_results": MAX_RESULTS if since_id else BASELINE_MAX_RESULTS,
        }
        if since_id:
            params["since_id"] = since_id

        excluded = [
            name
            for name, include in (("replies", include_replies), ("retweets", include_reposts))
            if not include
        ]
        if excluded:
            params["exclude"] = ",".join(excluded)

        body = self._get(f"/users/{user_id}/tweets", params)
        newest_id = body.get("meta", {}).get("newest_id")

        if since_id is None:
            # Baseline run: remember where we are, but notify about nothing.
            return FetchResult(tweets=[], newest_id=newest_id)

        tweets = [
            Tweet(id=t["id"], text=t["text"], username=username, created_at=t.get("created_at"))
            for t in body.get("data", [])
        ]
        tweets.reverse()  # API returns newest first; send in posting order
        return FetchResult(tweets=tweets, newest_id=newest_id)

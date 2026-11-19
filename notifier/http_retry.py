"""One shared helper for HTTP calls with sensible retries.

Retries network hiccups, server errors (5xx) and rate limits (429) a
few times with growing pauses. Anything else is returned to the caller,
which turns it into a clear error message.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import requests

log = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = 3
DEFAULT_TIMEOUT = 30
MAX_WAIT_SECONDS = 30  # never sleep longer than this inside one run

RETRY_STATUSES = {429, 500, 502, 503, 504}


def _wait_seconds(response: requests.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(float(retry_after), MAX_WAIT_SECONDS)
    return min(2.0 ** attempt, MAX_WAIT_SECONDS)  # 2s, 4s, 8s ...


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    **kwargs,
) -> requests.Response:
    """Send a request, retrying temporary failures. Returns the last response."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = session.request(method, url, **kwargs)
            if response.status_code not in RETRY_STATUSES or attempt == attempts:
                return response
            log.warning("HTTP %s from %s, retrying", response.status_code, _host(url))
        except (requests.ConnectionError, requests.Timeout) as error:
            last_error = error
            if attempt == attempts:
                break
            log.warning("Network problem talking to %s, retrying", _host(url))
        sleep(_wait_seconds(response, attempt))

    # Only the error type: the full message can contain the URL (and tokens in it).
    reason = type(last_error).__name__ if last_error else "unknown error"
    raise ConnectionError(f"Could not reach {_host(url)} ({reason}). Check the server's internet connection.")


def _host(url: str) -> str:
    """Only the host name, so tokens inside URLs never reach the logs."""
    return url.split("/")[2] if "://" in url else url

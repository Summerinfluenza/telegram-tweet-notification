import pytest
import requests

from notifier.http_retry import request_with_retry
from tests.conftest import FakeResponse, FakeSession


def test_success_returns_immediately():
    session = FakeSession(FakeResponse(200))
    assert request_with_retry(session, "GET", "https://a.example/x").status_code == 200
    assert len(session.calls) == 1
    assert session.calls[0]["timeout"] == 30


def test_server_error_is_retried_then_succeeds():
    waits = []
    session = FakeSession(FakeResponse(503), FakeResponse(200))
    response = request_with_retry(session, "GET", "https://a.example/x", sleep=waits.append)
    assert response.status_code == 200
    assert waits == [2.0]


def test_retry_after_header_is_respected_but_capped():
    waits = []
    session = FakeSession(FakeResponse(429, headers={"Retry-After": "5"}),
                          FakeResponse(429, headers={"Retry-After": "999"}),
                          FakeResponse(200))
    request_with_retry(session, "GET", "https://a.example/x", sleep=waits.append)
    assert waits == [5.0, 30]


def test_gives_up_and_returns_last_error_response():
    session = FakeSession(FakeResponse(500), FakeResponse(500), FakeResponse(500))
    assert request_with_retry(session, "GET", "https://a.example/x", sleep=lambda s: None).status_code == 500


def test_client_errors_are_not_retried():
    session = FakeSession(FakeResponse(401))
    assert request_with_retry(session, "GET", "https://a.example/x").status_code == 401
    assert len(session.calls) == 1


def test_network_errors_are_retried_then_raised_without_secrets():
    url = "https://api.example/botSECRET/x"
    session = FakeSession(*(requests.ConnectionError(f"Max retries exceeded with url: {url}") for _ in range(3)))
    with pytest.raises(ConnectionError) as info:
        request_with_retry(session, "GET", url, sleep=lambda s: None)
    assert "api.example" in str(info.value)
    assert "SECRET" not in str(info.value)

from __future__ import annotations

import json
from collections import deque

import pytest
import requests

import bve.se.acquisition.http as http_module
from bve.se.acquisition.http import (
    AcquisitionHttpError,
    BoundedRetry,
    ResponseTooLargeError,
    UnexpectedContentTypeError,
    build_retrying_session,
    configured_user_agent,
    get_json,
    get_text,
    safe_get_public_page,
)

PUBLIC_IP = "93.184.216.34"


def public_resolver(hostname: str, port: int) -> tuple[str, ...]:
    assert hostname
    assert port == 443
    return (PUBLIC_IP,)


class FakeResponse:
    def __init__(
        self,
        body: bytes = b"",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
    ) -> None:
        self.body = body
        self.status_code = status_code
        self.headers = headers or {}
        self.chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int):
        del chunk_size
        return iter(self.chunks if self.chunks is not None else [self.body])

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.popleft()


def test_configured_user_agent_is_required(monkeypatch) -> None:
    monkeypatch.delenv("BVE_SE_USER_AGENT", raising=False)
    with pytest.raises(AcquisitionHttpError, match="BVE_SE_USER_AGENT"):
        configured_user_agent()

    monkeypatch.setenv("BVE_SE_USER_AGENT", "BVE Research without-contact")
    with pytest.raises(AcquisitionHttpError, match="contact email"):
        configured_user_agent()

    monkeypatch.setenv("BVE_SE_USER_AGENT", "BVE Research ops@example.com")
    assert configured_user_agent() == "BVE Research ops@example.com"


def test_retrying_session_is_bounded_and_honors_retry_after() -> None:
    session = build_retrying_session("BVE Research ops@example.com")
    retry = session.get_adapter("https://").max_retries

    assert isinstance(retry, BoundedRetry)
    assert retry.total == 3
    assert retry.backoff_max == 4.0
    assert retry.respect_retry_after_header is True
    assert 429 in retry.status_forcelist
    assert 500 in retry.status_forcelist and 599 in retry.status_forcelist
    assert session.headers["User-Agent"] == "BVE Research ops@example.com"
    retry_after_response = type("RetryResponse", (), {"headers": {"Retry-After": "120"}})()
    assert retry.get_retry_after(retry_after_response) == 30.0
    session.close()


def test_shared_live_request_pacer_enforces_conservative_start_interval() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    pacer = http_module._RequestPacer(0.34, clock=clock, sleeper=sleep)
    pacer.wait()
    pacer.wait()
    now[0] += 1.0
    pacer.wait()

    assert sleeps == [pytest.approx(0.34)]


def test_json_helper_uses_explicit_limits_and_closes_response() -> None:
    response = FakeResponse(
        json.dumps({"ok": True}).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    session = FakeSession([response])

    assert get_json(
        "https://api.example.com/data",
        params={"q": "term"},
        timeout=(1.0, 2.0),
        max_bytes=1024,
        resolver=public_resolver,
        session=session,  # type: ignore[arg-type]
    ) == {"ok": True}
    assert session.calls == [
        (
            "https://api.example.com/data",
            {
                "params": {"q": "term"},
                "timeout": (1.0, 2.0),
                "stream": True,
                "allow_redirects": False,
            },
        )
    ]
    assert response.closed


def test_json_helper_supports_openfda_not_found() -> None:
    response = FakeResponse(status_code=404)
    assert get_json(
        "https://api.fda.gov/drug/label.json",
        allow_not_found=True,
        resolver=public_resolver,
        session=FakeSession([response]),  # type: ignore[arg-type]
    ) is None
    assert response.closed


def test_helpers_reject_declared_or_streamed_oversize_responses() -> None:
    declared = FakeResponse(
        headers={"Content-Length": "101", "Content-Type": "text/plain"}
    )
    with pytest.raises(ResponseTooLargeError, match="Content-Length"):
        get_text(
            "https://example.com/large",
            max_bytes=100,
            resolver=public_resolver,
            session=FakeSession([declared]),  # type: ignore[arg-type]
        )
    assert declared.closed

    streamed = FakeResponse(
        chunks=[b"a" * 60, b"b" * 41],
        headers={"Content-Type": "text/plain"},
    )
    with pytest.raises(ResponseTooLargeError, match="body exceeds"):
        get_text(
            "https://example.com/large",
            max_bytes=100,
            resolver=public_resolver,
            session=FakeSession([streamed]),  # type: ignore[arg-type]
        )
    assert streamed.closed


def test_json_helper_rejects_invalid_payload() -> None:
    with pytest.raises(AcquisitionHttpError, match="invalid JSON"):
        get_json(
            "https://api.example.com/data",
            resolver=public_resolver,
            session=FakeSession(
                [FakeResponse(b"not-json", headers={"Content-Type": "application/json"})]
            ),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/page",
        "https://user:password@example.com/page",
        "https://localhost/page",
        "https://127.0.0.1/page",
        "https://10.0.0.1/page",
        "https://169.254.169.254/latest/meta-data",
        "https://[::1]/page",
    ],
)
def test_safe_page_rejects_unsafe_initial_url_before_request(url: str) -> None:
    session = FakeSession([])
    with pytest.raises(ValueError):
        safe_get_public_page(url, session=session)  # type: ignore[arg-type]
    assert session.calls == []


def test_safe_page_validates_every_redirect_before_next_request() -> None:
    redirect = FakeResponse(
        status_code=302,
        headers={"Location": "https://127.0.0.1/admin"},
    )
    session = FakeSession([redirect])

    with pytest.raises(ValueError, match="non-public IP literal"):
        safe_get_public_page(
            "https://example.com/start",
            resolver=public_resolver,
            session=session,  # type: ignore[arg-type]
        )
    assert [url for url, _ in session.calls] == ["https://example.com/start"]
    assert redirect.closed


def test_safe_page_follows_valid_relative_redirect_with_explicit_controls() -> None:
    redirect = FakeResponse(status_code=302, headers={"Location": "/final"})
    final = FakeResponse(b"public content", headers={"Content-Type": "text/html"})
    session = FakeSession([redirect, final])
    resolutions: list[tuple[str, int]] = []

    def resolver(hostname: str, port: int) -> tuple[str, ...]:
        resolutions.append((hostname, port))
        return (PUBLIC_IP,)

    assert safe_get_public_page(
        "https://example.com/start",
        timeout=(2.0, 4.0),
        max_bytes=100,
        resolver=resolver,
        session=session,  # type: ignore[arg-type]
    ) == "public content"
    assert [url for url, _ in session.calls] == [
        "https://example.com/start",
        "https://example.com/final",
    ]
    assert all(
        kwargs == {
            "params": None,
            "timeout": (2.0, 4.0),
            "stream": True,
            "allow_redirects": False,
        }
        for _, kwargs in session.calls
    )
    assert resolutions == [("example.com", 443), ("example.com", 443)]
    assert redirect.closed and final.closed


def test_safe_page_redirect_count_is_bounded() -> None:
    session = FakeSession(
        [
            FakeResponse(status_code=302, headers={"Location": "/two"}),
            FakeResponse(status_code=302, headers={"Location": "/three"}),
        ]
    )
    with pytest.raises(AcquisitionHttpError, match="exceeded 1 redirects"):
        safe_get_public_page(
            "https://example.com/one",
            max_redirects=1,
            resolver=public_resolver,
            session=session,  # type: ignore[arg-type]
        )


def test_dns_answer_rejects_any_non_public_address_before_request() -> None:
    session = FakeSession([])

    def mixed_resolver(hostname: str, port: int) -> tuple[str, ...]:
        del hostname, port
        return (PUBLIC_IP, "10.0.0.7")

    with pytest.raises(AcquisitionHttpError, match="included a non-public address"):
        get_json(
            "https://api.example.com/data",
            resolver=mixed_resolver,
            session=session,  # type: ignore[arg-type]
        )
    assert session.calls == []


def test_dns_failures_and_transport_failures_are_classified() -> None:
    def failed_resolver(hostname: str, port: int) -> tuple[str, ...]:
        del hostname, port
        raise OSError("resolver unavailable")

    with pytest.raises(AcquisitionHttpError, match="DNS resolution failed"):
        get_text(
            "https://example.com/data",
            resolver=failed_resolver,
            session=FakeSession([]),  # type: ignore[arg-type]
        )

    class FailedSession:
        def get(self, url: str, **kwargs):
            del url, kwargs
            raise requests.ConnectionError("connection refused")

    with pytest.raises(AcquisitionHttpError, match="HTTP transport failed"):
        get_text(
            "https://example.com/data",
            resolver=public_resolver,
            session=FailedSession(),  # type: ignore[arg-type]
        )


def test_api_helpers_validate_redirect_target_before_request() -> None:
    redirect = FakeResponse(
        status_code=307,
        headers={"Location": "https://169.254.169.254/latest/meta-data"},
    )
    session = FakeSession([redirect])

    with pytest.raises(ValueError, match="non-public IP literal"):
        get_json(
            "https://api.example.com/data",
            resolver=public_resolver,
            session=session,  # type: ignore[arg-type]
        )
    assert [url for url, _ in session.calls] == ["https://api.example.com/data"]
    assert redirect.closed


@pytest.mark.parametrize(
    ("helper", "content_type", "body"),
    [
        (get_json, "application/problem+json", b"{}"),
        (get_json, "text/json", b"{}"),
        (get_text, "application/xml", b"<article />"),
        (get_text, "application/ixbrl+xml", b"<html />"),
        (get_text, "text/plain", b"filing text"),
    ],
)
def test_api_helpers_accept_endpoint_appropriate_content_types(
    helper, content_type: str, body: bytes
) -> None:
    response = FakeResponse(body, headers={"Content-Type": content_type})
    result = helper(
        "https://api.example.com/data",
        resolver=public_resolver,
        session=FakeSession([response]),
    )
    assert result == ({} if helper is get_json else body.decode())
    assert response.closed


@pytest.mark.parametrize("content_type", ["", "text/html", "application/octet-stream"])
def test_json_helper_rejects_missing_or_wrong_content_type(content_type: str) -> None:
    headers = {"Content-Type": content_type} if content_type else {}
    response = FakeResponse(b"{}", headers=headers)

    with pytest.raises(UnexpectedContentTypeError, match="unexpected Content-Type"):
        get_json(
            "https://api.example.com/data",
            resolver=public_resolver,
            session=FakeSession([response]),  # type: ignore[arg-type]
        )
    assert response.closed


def test_public_page_requires_html_content_type() -> None:
    response = FakeResponse(b"not html", headers={"Content-Type": "text/plain"})
    with pytest.raises(UnexpectedContentTypeError, match="for html response"):
        safe_get_public_page(
            "https://example.com/page",
            resolver=public_resolver,
            session=FakeSession([response]),  # type: ignore[arg-type]
        )
    assert response.closed

"""Shared, bounded HTTP boundary for live public-source acquisition."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, cast
from urllib.parse import urljoin, urlsplit

import requests  # type: ignore[import-untyped]
from requests import Response, Session
from requests.adapters import HTTPAdapter  # type: ignore[import-untyped]
from urllib3.util.retry import Retry

from bve.se.acquisition.policy import validate_public_https_url


DEFAULT_TIMEOUT = (5.0, 30.0)
DEFAULT_MAX_RESPONSE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_PUBLIC_PAGE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_RETRY_TOTAL = 3
DEFAULT_RETRY_AFTER_SECONDS = 30.0
DEFAULT_MIN_REQUEST_INTERVAL_SECONDS = 0.34
_RETRY_STATUS_CODES = frozenset({429, *range(500, 600)})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_CONTACT_EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
ContentKind = Literal["json", "text", "html"]
AddressResolver = Callable[[str, int], Sequence[str]]


class AcquisitionHttpError(RuntimeError):
    """Base error for bounded acquisition HTTP failures."""


class ResponseTooLargeError(AcquisitionHttpError):
    """Raised before a response can exceed the configured byte ceiling."""


class UnexpectedContentTypeError(AcquisitionHttpError):
    """Raised when an endpoint returns content outside its declared media class."""


class BoundedRetry(Retry):
    """urllib3 retry policy that caps both backoff and Retry-After sleeps."""

    max_retry_after_seconds: float

    def __init__(
        self,
        *args: Any,
        max_retry_after_seconds: float = DEFAULT_RETRY_AFTER_SECONDS,
        **kwargs: Any,
    ) -> None:
        if max_retry_after_seconds < 0:
            raise ValueError("max_retry_after_seconds must not be negative")
        self.max_retry_after_seconds = max_retry_after_seconds
        super().__init__(*args, **kwargs)

    def new(self, **kwargs: Any) -> "BoundedRetry":
        retry = cast("BoundedRetry", super().new(**kwargs))
        retry.max_retry_after_seconds = self.max_retry_after_seconds
        return retry

    def get_retry_after(self, response) -> float | None:
        retry_after = super().get_retry_after(response)
        if retry_after is None:
            return None
        return max(0.0, min(retry_after, self.max_retry_after_seconds))


class _RequestPacer:
    """Serialize process-local request starts to comply with conservative public API rates."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds must not be negative")
        self.min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._last_started: float | None = None

    def wait(self) -> None:
        """Wait until this process may start its next shared live HTTP request."""

        with self._lock:
            now = self._clock()
            while self._last_started is not None:
                remaining = self.min_interval_seconds - (now - self._last_started)
                if remaining <= 0:
                    break
                self._sleeper(remaining)
                now = self._clock()
            self._last_started = now


def configured_user_agent() -> str:
    """Return the required operator-configured public-source user agent."""

    user_agent = os.environ.get("BVE_SE_USER_AGENT", "").strip()
    if not user_agent:
        raise AcquisitionHttpError(
            "BVE_SE_USER_AGENT must identify the live acquisition operator"
        )
    if "\r" in user_agent or "\n" in user_agent:
        raise AcquisitionHttpError("BVE_SE_USER_AGENT must not contain control characters")
    if not _CONTACT_EMAIL_RE.search(user_agent):
        raise AcquisitionHttpError(
            "BVE_SE_USER_AGENT must include an operator contact email"
        )
    return user_agent


def build_retrying_session(user_agent: str | None = None) -> Session:
    """Construct a requests Session with bounded GET retry semantics."""

    effective_user_agent = user_agent.strip() if user_agent else configured_user_agent()
    if not effective_user_agent or "\r" in effective_user_agent or "\n" in effective_user_agent:
        raise AcquisitionHttpError("a nonempty, single-line acquisition user agent is required")
    if not _CONTACT_EMAIL_RE.search(effective_user_agent):
        raise AcquisitionHttpError("acquisition user agent must include a contact email")
    retry = BoundedRetry(
        total=DEFAULT_RETRY_TOTAL,
        connect=DEFAULT_RETRY_TOTAL,
        read=DEFAULT_RETRY_TOTAL,
        status=DEFAULT_RETRY_TOTAL,
        other=0,
        redirect=0,
        allowed_methods=frozenset({"GET"}),
        status_forcelist=_RETRY_STATUS_CODES,
        backoff_factor=0.5,
        backoff_max=4.0,
        backoff_jitter=0.25,
        respect_retry_after_header=True,
        raise_on_status=False,
        max_retry_after_seconds=DEFAULT_RETRY_AFTER_SECONDS,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update({"User-Agent": effective_user_agent})
    session.mount("https://", adapter)
    return session


_SESSION_LOCK = threading.Lock()
_SHARED_SESSION: Session | None = None
_SHARED_USER_AGENT: str | None = None
_SHARED_REQUEST_PACER = _RequestPacer(DEFAULT_MIN_REQUEST_INTERVAL_SECONDS)


def shared_session() -> Session:
    """Return the process-wide retrying Session for the current configured identity."""

    global _SHARED_SESSION, _SHARED_USER_AGENT

    user_agent = configured_user_agent()
    with _SESSION_LOCK:
        if _SHARED_SESSION is None or _SHARED_USER_AGENT != user_agent:
            if _SHARED_SESSION is not None:
                _SHARED_SESSION.close()
            _SHARED_SESSION = build_retrying_session(user_agent)
            _SHARED_USER_AGENT = user_agent
        return _SHARED_SESSION


def _validate_limits(
    timeout: tuple[float, float],
    max_bytes: int,
) -> None:
    if len(timeout) != 2 or timeout[0] <= 0 or timeout[1] <= 0:
        raise ValueError("timeout must contain positive connect and read limits")
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")


def _system_resolver(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve all stream addresses so the complete answer can be policy checked."""

    records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return tuple(dict.fromkeys(str(record[4][0]) for record in records))


def _validate_resolved_url(
    url: str,
    *,
    resolver: AddressResolver,
) -> str:
    """Validate URL syntax and reject DNS answers containing any non-global address."""

    normalized = validate_public_https_url(url)
    parsed = urlsplit(normalized)
    assert parsed.hostname is not None  # guaranteed by validate_public_https_url
    hostname = parsed.hostname
    port = parsed.port or 443

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            resolved = tuple(resolver(hostname, port))
        except OSError as exc:
            raise AcquisitionHttpError(f"DNS resolution failed for {hostname}") from exc
        if not resolved:
            raise AcquisitionHttpError(f"DNS resolution returned no addresses for {hostname}")
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for value in resolved:
            try:
                addresses.append(ipaddress.ip_address(value))
            except ValueError as exc:
                raise AcquisitionHttpError(
                    f"DNS resolution returned an invalid address for {hostname}"
                ) from exc
    else:
        addresses = [literal]

    if any(
        not address.is_global
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
        for address in addresses
    ):
        raise AcquisitionHttpError(
            f"DNS resolution for {hostname} included a non-public address"
        )
    return normalized


def _validate_content_type(response: Response, *, expected: ContentKind, url: str) -> None:
    raw_content_type = response.headers.get("Content-Type", "")
    media_type = raw_content_type.partition(";")[0].strip().casefold()
    if expected == "json":
        accepted = media_type in {"application/json", "text/json"} or media_type.endswith(
            "+json"
        )
    elif expected == "text":
        accepted = (
            media_type.startswith("text/")
            or media_type in {"application/xml", "application/xhtml+xml"}
            or media_type.endswith("+xml")
        )
    else:
        accepted = media_type in {"text/html", "application/xhtml+xml"}
    if not accepted:
        rendered = raw_content_type or "<missing>"
        hostname = urlsplit(url).hostname or "unknown host"
        raise UnexpectedContentTypeError(
            f"unexpected Content-Type {rendered!r} for {expected} response from {hostname}"
        )


def _read_limited(response: Response, *, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > max_bytes:
            raise ResponseTooLargeError(
                f"response Content-Length {declared_size} exceeds limit {max_bytes}"
            )

    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > max_bytes:
            raise ResponseTooLargeError(
                f"response body exceeds configured limit {max_bytes}"
            )
    return bytes(body)


def _get_bytes(
    url: str,
    *,
    params: Mapping[str, object] | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allow_not_found: bool = False,
    expected_content: ContentKind,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    resolver: AddressResolver = _system_resolver,
    session: Session | None = None,
) -> bytes | None:
    _validate_limits(timeout, max_bytes)
    if max_redirects < 0:
        raise ValueError("max_redirects must not be negative")
    uses_shared_live_session = session is None
    client = session or shared_session()
    current_url = validate_public_https_url(url)
    current_params = params

    for redirect_count in range(max_redirects + 1):
        # Resolve immediately before every logical request, including each redirect target.
        current_url = _validate_resolved_url(current_url, resolver=resolver)
        if uses_shared_live_session:
            _SHARED_REQUEST_PACER.wait()
        try:
            response = client.get(
                current_url,
                params=current_params,
                timeout=timeout,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            hostname = urlsplit(current_url).hostname or "unknown host"
            raise AcquisitionHttpError(f"HTTP transport failed for {hostname}") from exc
        try:
            if response.status_code in _REDIRECT_STATUS_CODES:
                if redirect_count >= max_redirects:
                    raise AcquisitionHttpError(
                        f"HTTP response exceeded {max_redirects} redirects"
                    )
                location = response.headers.get("Location")
                if not location:
                    raise AcquisitionHttpError("redirect response omitted Location header")
                current_url = validate_public_https_url(urljoin(current_url, location))
                current_params = None
                continue
            if 300 <= response.status_code < 400:
                raise AcquisitionHttpError(
                    f"unsupported HTTP redirect status {response.status_code}"
                )
            if allow_not_found and response.status_code == 404:
                return None
            try:
                response.raise_for_status()
                _validate_content_type(
                    response,
                    expected=expected_content,
                    url=current_url,
                )
                return _read_limited(response, max_bytes=max_bytes)
            except requests.RequestException as exc:
                hostname = urlsplit(current_url).hostname or "unknown host"
                raise AcquisitionHttpError(f"HTTP response failed for {hostname}") from exc
        finally:
            response.close()

    raise AcquisitionHttpError("HTTP redirect handling failed")


def get_json(
    url: str,
    *,
    params: Mapping[str, object] | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allow_not_found: bool = False,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    resolver: AddressResolver = _system_resolver,
    session: Session | None = None,
) -> Any | None:
    """GET and decode bounded JSON through the shared retrying Session."""

    payload = _get_bytes(
        url,
        params=params,
        timeout=timeout,
        max_bytes=max_bytes,
        allow_not_found=allow_not_found,
        expected_content="json",
        max_redirects=max_redirects,
        resolver=resolver,
        session=session,
    )
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcquisitionHttpError(f"invalid JSON response from {url}") from exc


def get_text(
    url: str,
    *,
    params: Mapping[str, object] | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    resolver: AddressResolver = _system_resolver,
    session: Session | None = None,
) -> str:
    """GET and decode bounded text through the shared retrying Session."""

    payload = _get_bytes(
        url,
        params=params,
        timeout=timeout,
        max_bytes=max_bytes,
        expected_content="text",
        max_redirects=max_redirects,
        resolver=resolver,
        session=session,
    )
    assert payload is not None
    return payload.decode("utf-8", errors="replace")


def safe_get_public_page(
    url: str,
    *,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_PUBLIC_PAGE_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    resolver: AddressResolver = _system_resolver,
    session: Session | None = None,
) -> str:
    """GET a declared page while validating every redirect before following it."""

    payload = _get_bytes(
        url,
        timeout=timeout,
        max_bytes=max_bytes,
        expected_content="html",
        max_redirects=max_redirects,
        resolver=resolver,
        session=session,
    )
    assert payload is not None
    return payload.decode("utf-8", errors="replace")


__all__ = [
    "AcquisitionHttpError",
    "AddressResolver",
    "BoundedRetry",
    "DEFAULT_MAX_PUBLIC_PAGE_BYTES",
    "DEFAULT_MAX_RESPONSE_BYTES",
    "DEFAULT_MIN_REQUEST_INTERVAL_SECONDS",
    "DEFAULT_TIMEOUT",
    "ResponseTooLargeError",
    "UnexpectedContentTypeError",
    "build_retrying_session",
    "configured_user_agent",
    "get_json",
    "get_text",
    "safe_get_public_page",
    "shared_session",
]

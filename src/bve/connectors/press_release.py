"""
Company press release source connector.

Supports two usage patterns:

1. **Direct URL fetch** — ``fetch()`` with ``entity_hints`` triggers HTTP GET
   to a pre-known press release URL stored in ``entity_hints`` metadata.
   Pass the URL via ``extra_kwargs`` key ``"url"``.

2. **From text** — ``from_text()`` classmethod wraps pre-loaded plain text
   (e.g., copy-pasted from IR page, local file) in a ``RawDocument`` without
   any network call.  Used by the CLI's ``--text`` mode.

HTML stripping is handled by a simple regex approach to avoid requiring
``beautifulsoup4`` in the core dependency list.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Patterns for HTML stripping
_SCRIPT_RE  = re.compile(r"<script[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE   = re.compile(r"<style[^>]*>.*?</style>",  re.IGNORECASE | re.DOTALL)
_TAG_RE     = re.compile(r"<[^>]+>")
_ENTITY_RE  = re.compile(r"&(?:[a-z]+|#\d+);")
_WS_RE      = re.compile(r"\s+")
_TITLE_RE   = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_DATE_RE    = re.compile(
    r'(?:datePublished|article:published_time|publishedDate)["\s:=]+([0-9T\-:Z+]{10,25})',
    re.IGNORECASE,
)


def strip_html(html: str) -> tuple[str, str, Optional[datetime]]:
    """
    Strip HTML to plain text.  Also extracts title and publication date.

    Returns
    -------
    (text, title, published_at)
    """
    # Extract title before stripping
    title_match = _TITLE_RE.search(html)
    raw_title = title_match.group(1) if title_match else ""
    title = _WS_RE.sub(" ", _TAG_RE.sub("", raw_title)).strip()

    # Try to extract publication date from meta tags
    published_at: Optional[datetime] = None
    date_match = _DATE_RE.search(html)
    if date_match:
        date_str = date_match.group(1).replace("Z", "+00:00")
        try:
            published_at = datetime.fromisoformat(date_str[:25])
        except ValueError:
            pass

    # Strip tags
    text = _SCRIPT_RE.sub(" ", html)
    text = _STYLE_RE.sub(" ", text)
    text = _TAG_RE.sub(" ", text)
    text = _ENTITY_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()

    return text, title, published_at


class PressReleaseConnector:
    """
    Fetches press release content from a direct URL.

    ``fetch()`` requires the target URL to be passed as ``extra_kwargs["url"]``.

    For documents already loaded from local files or copy-pasted text, use
    the ``from_text()`` classmethod instead — no network call is made.

    Parameters
    ----------
    timeout:
        HTTP request timeout in seconds.  Default: 15.
    """

    def __init__(self, timeout: int = 15) -> None:
        self._timeout = timeout

    @property
    def source_type(self) -> str:
        return "press_release"

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
        *,
        url: Optional[str] = None,
        title_override: Optional[str] = None,
        published_at_override: Optional[datetime] = None,
    ) -> FetchResult:
        """
        Fetch a single press release by URL.

        Parameters
        ----------
        url:
            HTTP URL of the press release to fetch.  Required for network mode.
        title_override:
            Override the extracted title.
        published_at_override:
            Override the extracted publication date.
        """
        now = _utcnow()

        if not url:
            return FetchResult(
                source=self.source_type,
                fetch_errors=["url keyword argument is required for PressReleaseConnector.fetch()"],
            )

        try:
            html = self._get_url(url)
        except Exception as exc:
            return FetchResult(
                source=self.source_type,
                fetch_errors=[f"HTTP fetch failed for {url!r}: {exc}"],
            )

        text, extracted_title, extracted_date = strip_html(html)
        if not text.strip():
            return FetchResult(
                source=self.source_type,
                fetch_errors=[f"No text content extracted from {url!r}"],
            )

        title       = title_override or extracted_title or urlparse(url).path
        published_at = published_at_override or extracted_date

        if since and published_at and published_at < since:
            return FetchResult(source=self.source_type)

        doc = RawDocument.from_text(
            id=str(uuid.uuid4()),
            source=self.source_type,
            title=title,
            raw_text=text,
            entity_hints=entity_hints,
            retrieved_at=now,
            source_url=url,
            published_at=published_at,
        )
        return FetchResult(
            documents=[doc],
            source=self.source_type,
            fetched_at=now,
        )

    def _get_url(self, url: str) -> str:
        """Perform the HTTP GET, trying httpx first then urllib."""
        try:
            import httpx
            response = httpx.get(url, follow_redirects=True, timeout=self._timeout)
            response.raise_for_status()
            return response.text
        except ImportError:
            pass

        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "bve-intelligence/1.0"})
        with urllib.request.urlopen(req, timeout=self._timeout) as r:
            return r.read().decode("utf-8", errors="replace")

    @classmethod
    def from_text(
        cls,
        *,
        text: str,
        title: str,
        entity_hints: EntityHints,
        source_url: Optional[str] = None,
        published_at: Optional[datetime] = None,
    ) -> RawDocument:
        """
        Create a ``RawDocument`` from plain text without any network call.

        Useful for:
        - CLI ``--text FILE`` mode (local file → RawDocument)
        - Testing with fixture text files
        - Copy-pasted document content

        Parameters
        ----------
        text:
            Plain text (not HTML).  Must not be empty.
        title:
            Document headline.
        entity_hints:
            Asset / company identity context.
        source_url:
            Optional permalink (``None`` for local-only documents).
        published_at:
            Optional publication date.
        """
        return RawDocument.from_text(
            id=str(uuid.uuid4()),
            source="press_release",
            title=title,
            raw_text=text,
            entity_hints=entity_hints,
            retrieved_at=_utcnow(),
            source_url=source_url,
            published_at=published_at,
        )

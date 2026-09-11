"""Offline replay driven by the sealed query->record mapping.

The distinction that matters here is between replaying *a corpus* and replaying *an
acquisition*. B7's offline path did the former: it loaded every snapshot file in the
tree and handed the union to every query, so each query saw a universe no query had
actually seen. Membership was re-derived rather than reproduced, and the replay found
3,385 hits where the live run found 3,321.

This module does the latter. Each semantic query is served exactly the records the
sealed custody record says that query received, in the order it received them, attempt
by attempt — including attempts that failed after materializing bytes. Only acquisition
is swapped; every adapter's extraction, filtering and hit construction is the live code,
unmodified, so equality of output follows from equality of input rather than from
matching code that was written twice.

Nothing here consults the filesystem beyond the files the seal binds, and
:func:`block_network` makes a stray outbound call fatal rather than silently live.
"""

from __future__ import annotations

import hashlib
import json
import socket
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from bve.se.discovery.adapters import (
    ClinicalTrialsGovAdapter,
    PubMedDiscoveryAdapter,
    TrialAcquisitionFailure,
)
from bve.se.discovery.custody import (
    CustodyError,
    QueryAttemptRecord,
    SealedAcquisition,
    semantic_query_id,
    validate_seal,
)
from bve.se.schemas.contracts import SearchOutcome


class ReplayDivergence(CustodyError):
    """Replay asked for something the sealed acquisition never recorded.

    Always fatal. A replay that improvises an answer for an unrecorded query is a replay
    that cannot be used to prove anything about the run it claims to reproduce.
    """


class NetworkBlocked(RuntimeError):
    """An offline replay attempted to open a connection."""


@contextmanager
def block_network() -> Iterator[None]:
    """Make any outbound connection or name lookup fatal for the duration.

    The deny hooks go on the connect/resolve path rather than on ``socket.socket``
    itself: rebinding the class breaks ``class SSLSocket(socket)`` at stdlib import time,
    which turns a guard into an unrelated TypeError.
    """

    def deny(*_args: object, **_kwargs: object) -> None:
        raise NetworkBlocked("offline replay attempted a network call; this is fatal")

    saved = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
        "gethostbyname": socket.gethostbyname,
    }
    socket.socket.connect = deny  # type: ignore[method-assign]
    socket.socket.connect_ex = deny  # type: ignore[method-assign]
    socket.create_connection = deny  # type: ignore[assignment]
    socket.getaddrinfo = deny  # type: ignore[assignment]
    socket.gethostbyname = deny  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket.connect = saved["connect"]  # type: ignore[method-assign]
        socket.socket.connect_ex = saved["connect_ex"]  # type: ignore[method-assign]
        socket.create_connection = saved["create_connection"]  # type: ignore[assignment]
        socket.getaddrinfo = saved["getaddrinfo"]  # type: ignore[assignment]
        socket.gethostbyname = saved["gethostbyname"]  # type: ignore[assignment]


class SealedCorpusReplay:
    """Hand back each semantic query's recorded attempts, in recorded order."""

    def __init__(self, custody_root: Path) -> None:
        self.custody_root = Path(custody_root)
        #: Validation happens here, not at first use: a mutated corpus must fail before
        #: any stage has had the chance to consume part of it.
        self.sealed: SealedAcquisition = validate_seal(self.custody_root)
        self._pending: dict[tuple[str, str], deque[QueryAttemptRecord]] = {}
        for attempt in self.sealed.attempts:
            key = (attempt.source, attempt.semantic_query_id)
            self._pending.setdefault(key, deque()).append(attempt)

    def next_attempt(self, source: str, query_text: str) -> QueryAttemptRecord:
        """The next recorded attempt for this source and query, or a fatal divergence."""

        key = (source, semantic_query_id(source, query_text))
        pending = self._pending.get(key)
        if not pending:
            raise ReplayDivergence(
                f"{source}: sealed acquisition records no further attempt for query "
                f"{query_text!r}; live discovery and replay have diverged"
            )
        return pending.popleft()

    def payloads(self, attempt: QueryAttemptRecord) -> list[dict[str, Any]]:
        """The attempt's materialized records, hash-verified, in materialization order."""

        payloads: list[dict[str, Any]] = []
        for materialization in attempt.materializations:
            if materialization.snapshot_path is None:
                raise ReplayDivergence(
                    f"{attempt.source}: record {materialization.record_id} was sealed "
                    "without a snapshot path and cannot be replayed"
                )
            path = Path(materialization.snapshot_path)
            if not path.is_file():
                raise ReplayDivergence(f"sealed snapshot is missing: {path}")
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != materialization.content_hash:
                raise ReplayDivergence(
                    f"sealed snapshot {path} has been mutated: expected "
                    f"{materialization.content_hash}, found {digest}"
                )
            payloads.append(json.loads(content))
        return payloads

    def unconsumed(self) -> dict[tuple[str, str], int]:
        """Recorded attempts replay never asked for. Non-empty means divergence."""

        return {key: len(queue) for key, queue in self._pending.items() if queue}


class ReplayTrialsGovAdapter(ClinicalTrialsGovAdapter):
    """CT.gov discovery with acquisition replaced by the sealed record.

    Subclassing rather than reimplementing is the point: ``_acquire`` is the entire
    acquisition surface, so overriding it leaves materialization, filtering and hit
    construction as the same lines of code the live run executed.
    """

    def __init__(self, replay: SealedCorpusReplay, **kwargs: Any) -> None:
        super().__init__(search_fn=_offline_only, **kwargs)
        self._replay = replay

    def _acquire(self, vocabulary, query, as_of_date):  # type: ignore[no-untyped-def]
        attempt = self._replay.next_attempt(self.source_name, query.query)
        self.last_page_count = attempt.pages_fetched
        payloads = self._replay.payloads(attempt)
        if attempt.outcome is SearchOutcome.FAILED:
            # A failed attempt that had already written bytes must fail the same way and
            # still declare the same bytes, or replay would quietly heal B7's bug.
            raise TrialAcquisitionFailure(
                attempt.error or "sealed attempt failed", partial_payloads=payloads
            )
        return payloads


def replay_pubmed_adapter(
    replay: SealedCorpusReplay, **kwargs: Any
) -> PubMedDiscoveryAdapter:
    """PubMed discovery served from the sealed record.

    PubMed's acquisition seam is its ``search_fn``, which is keyed by the same query text
    the custody record is keyed by, so no subclass is needed.
    """

    source = PubMedDiscoveryAdapter.source_name

    def search_fn(query_text: str, _limit: int) -> list[dict[str, Any]]:
        attempt = replay.next_attempt(source, query_text)
        payloads = replay.payloads(attempt)
        if attempt.outcome is SearchOutcome.FAILED:
            raise RuntimeError(attempt.error or "sealed attempt failed")
        return payloads

    return PubMedDiscoveryAdapter(search_fn=search_fn, **kwargs)


def _offline_only(*_args: object, **_kwargs: object) -> list[dict[str, Any]]:
    raise ReplayDivergence("offline replay must not reach the live acquisition path")

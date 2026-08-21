"""Frozen trial provider for CI and replay.

Someone cloning the repo should be able to run the software without downloading gigabytes
of AACT or hitting a rate-limited API, so the test suite runs the *same* code path as
production with a fixture backend swapped in at the provider boundary.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from bve.se.schemas.contracts import SearchOutcome
from bve.se.universe.provider import (
    TrialQuery,
    TrialRecord,
    TrialUniverseResult,
)

BACKEND_NAME = "frozen"


def _matches(record: TrialRecord, query: TrialQuery) -> bool:
    if not query.terms and not query.conditions and not query.sponsors and not query.statuses:
        return True
    haystack = record.searchable_text().casefold()
    if query.terms and not any(term.casefold() in haystack for term in query.terms):
        return False
    if query.conditions and not any(
        condition.casefold() in haystack for condition in query.conditions
    ):
        return False
    if query.sponsors and not any(
        sponsor.casefold() in (record.lead_sponsor or "").casefold() for sponsor in query.sponsors
    ):
        return False
    if query.statuses and (record.overall_status or "") not in set(query.statuses):
        return False
    return True


class FrozenTrialProvider:
    """Serve a fixed set of records through the live provider contract."""

    backend_name = BACKEND_NAME

    def __init__(
        self, records: Iterable[TrialRecord], *, backend_version: str | None = None
    ) -> None:
        self.records = list(records)
        self.backend_version = backend_version

    @classmethod
    def from_jsonl(cls, path: Path, *, backend_version: str | None = None) -> "FrozenTrialProvider":
        records = [
            TrialRecord.model_validate(json.loads(line))
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        return cls(records, backend_version=backend_version or path.stem)

    def fetch(self, query: TrialQuery) -> TrialUniverseResult:
        matched = [
            record
            for record in self.records
            if _matches(record, query) and query.applies(record)
        ]
        truncated = False
        if query.max_records is not None:
            truncated = len(matched) > query.max_records
            matched = matched[: query.max_records]
        return TrialUniverseResult(
            records=matched,
            outcome=SearchOutcome.SUCCESS if matched else SearchOutcome.NO_EVIDENCE_FOUND,
            backend=self.backend_name,
            backend_version=self.backend_version,
            truncated=truncated,
        )

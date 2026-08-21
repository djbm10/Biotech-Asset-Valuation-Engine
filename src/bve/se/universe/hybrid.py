"""Hybrid backend: prefer a bulk mirror, fall back to the live API.

Bulk backends go stale between refreshes and local mirrors go missing; the live API is
always current but rate-limited. Running both and merging keeps the universe as broad as
the mirror allows without letting an unavailable mirror silently shrink it.
"""

from __future__ import annotations

from collections.abc import Sequence

from bve.se.schemas.contracts import SearchOutcome
from bve.se.universe.provider import (
    TrialQuery,
    TrialRecord,
    TrialUniverseProvider,
    TrialUniverseResult,
)

BACKEND_NAME = "hybrid"


class HybridTrialProvider:
    """Query providers in order and merge by ``trial_id``.

    The first provider to report a trial wins, so ordering expresses authority rather
    than recency. Every provider is queried even when the first succeeds: a mirror that
    is a week stale would otherwise hide trials registered since its refresh.
    """

    backend_name = BACKEND_NAME

    def __init__(self, providers: Sequence[TrialUniverseProvider]) -> None:
        if not providers:
            raise ValueError("HybridTrialProvider requires at least one provider")
        self.providers = list(providers)

    def fetch(self, query: TrialQuery) -> TrialUniverseResult:
        merged: dict[str, TrialRecord] = {}
        contributing: list[str] = []
        errors: list[str] = []
        truncated = False
        succeeded = False

        for provider in self.providers:
            result = provider.fetch(query)
            if result.outcome is SearchOutcome.FAILED:
                errors.append(f"{result.provenance()}: {result.error or 'failed'}")
                continue
            succeeded = True
            contributing.append(result.provenance())
            truncated = truncated or result.truncated
            for record in result.records:
                merged.setdefault(record.trial_id, record)

        if not succeeded:
            return TrialUniverseResult(
                outcome=SearchOutcome.FAILED,
                backend=self.backend_name,
                backend_version="+".join(
                    provider.backend_name for provider in self.providers
                ),
                error="; ".join(errors) or "all providers failed",
            )

        records = sorted(merged.values(), key=lambda record: record.trial_id)
        if query.max_records is not None:
            truncated = truncated or len(records) > query.max_records
            records = records[: query.max_records]

        if errors:
            # A partially available universe is reported as PARTIAL, never as a clean
            # SUCCESS: a downstream coverage claim has to know a backend was missing.
            outcome = SearchOutcome.PARTIAL
        elif records:
            outcome = SearchOutcome.SUCCESS
        else:
            outcome = SearchOutcome.NO_EVIDENCE_FOUND

        return TrialUniverseResult(
            records=records,
            outcome=outcome,
            backend=self.backend_name,
            backend_version="+".join(contributing) or None,
            error="; ".join(errors) or None,
            truncated=truncated,
        )

"""
SnapshotReplayEngine — frozen point-in-time decision view from CompanySnapshot history.

Phase 3B objective
------------------
Given a replay date and a list of company IDs, reconstruct the decision view
that would have been visible on that date using only data known by then.

No-lookahead guarantee
----------------------
``SnapshotReplayEngine.run()`` calls
``SnapshotStore.get_latest_snapshot(company_id, as_of=replay_date)``
for every company.  This retrieves the most recent snapshot whose
``as_of_date <= replay_date``, so future data never contaminates the view.

Decision outputs
----------------
``ReplayDecisionView`` is immutable.  Action rules are explicit and human-readable:

  APPROVED + sotp_discount > BUY_THRESHOLD    → "buy"
  APPROVED + sotp_discount > WATCH_THRESHOLD  → "watch"
  not APPROVED but sotp_discount > WATCH_THRESHOLD → "watch"
  everything else                              → "no_action"

Companies with no snapshot on or before the replay date are excluded from the
output (never produce a ``ReplayDecisionView``).

Usage
-----
    store = SnapshotStore("outputs/snapshots/company_snapshots.db")
    engine = SnapshotReplayEngine(store)

    decisions = engine.run(
        company_ids=["vktx", "alny", "srpt"],
        as_of_date=date(2025, 12, 31),
    )
    for d in decisions:
        print(d.ticker, d.action, f"{d.sotp_discount:+.1%}")
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from bve.entities.company_snapshot import ReviewerState

if TYPE_CHECKING:
    from bve.entities.company_snapshot import CompanySnapshot
    from bve.persistence.snapshot_store import SnapshotStore

# Action thresholds (explicit, no magic numbers hidden in logic)
BUY_THRESHOLD: float = 0.20    # SOTP discount > 20% + approved → buy
WATCH_THRESHOLD: float = 0.05  # SOTP discount > 5% → watch


class ReplayDecisionView(BaseModel, frozen=True):
    """
    Immutable decision record for one company at one replay date.

    All fields are derived from the snapshot visible on ``as_of_date``.
    No forward-looking data is used.

    Fields
    ------
    company_id             : Canonical company identifier.
    ticker                 : Exchange ticker.
    as_of_date             : The replay date this view was generated for.
    snapshot_id            : Which CompanySnapshot was used (audit trail).
    snapshot_as_of         : The snapshot's own ``as_of_date`` (≤ as_of_date).
    reviewer_state         : ReviewerState of the snapshot used.
    is_capital_candidate   : True when snapshot.is_capital_candidate_eligible.
    sotp_equity_value_millions : Snapshot SOTP equity value.
    market_cap_millions    : Snapshot market cap.
    sotp_discount          : (SOTP - market_cap) / market_cap. Positive = undervalued.
    rank                   : 1-indexed rank across all companies (1 = best SOTP discount).
    action                 : "buy" | "watch" | "no_action".
    """
    company_id: str
    ticker: str
    as_of_date: date
    snapshot_id: str
    snapshot_as_of: date
    reviewer_state: ReviewerState
    is_capital_candidate: bool
    sotp_equity_value_millions: float
    market_cap_millions: float
    sotp_discount: float
    rank: int = Field(ge=1)
    action: Literal["buy", "watch", "no_action"]

    @property
    def is_undervalued(self) -> bool:
        """True when SOTP > market cap."""
        return self.sotp_discount > 0.0

    @property
    def discount_pct_str(self) -> str:
        return f"{self.sotp_discount:+.1%}"


def _assign_action(
    is_capital_candidate: bool,
    sotp_discount: float,
) -> Literal["buy", "watch", "no_action"]:
    """
    Deterministic, threshold-based action assignment.

    Rules (evaluated in priority order):
    1. Capital-candidate eligible AND discount > BUY_THRESHOLD  → "buy"
    2. Discount > WATCH_THRESHOLD                               → "watch"
    3. Everything else                                          → "no_action"
    """
    if is_capital_candidate and sotp_discount > BUY_THRESHOLD:
        return "buy"
    if sotp_discount > WATCH_THRESHOLD:
        return "watch"
    return "no_action"


class SnapshotReplayEngine:
    """
    Reconstruct the decision view for a universe of companies at a historical date.

    Parameters
    ----------
    store : SnapshotStore
        The snapshot store to query.  Must support
        ``get_latest_snapshot(company_id, as_of=date)``.
    """

    def __init__(self, store: SnapshotStore) -> None:
        self._store = store

    def run(
        self,
        company_ids: list[str],
        as_of_date: date,
    ) -> list[ReplayDecisionView]:
        """
        Generate the decision view for each company as of ``as_of_date``.

        Steps
        -----
        1. For each company_id, load the latest snapshot with
           ``snapshot.as_of_date <= as_of_date``.
        2. Companies with no qualifying snapshot are silently skipped.
        3. Compute ``sotp_discount`` from the snapshot.
        4. Rank companies by ``sotp_discount`` descending (best opportunity first).
        5. Assign action using ``_assign_action()``.

        Returns a list of ``ReplayDecisionView`` sorted by rank (rank 1 first).
        """
        raw: list[tuple[float, CompanySnapshot]] = []

        for company_id in company_ids:
            snap = self._store.get_latest_snapshot(company_id, as_of=as_of_date)
            if snap is None:
                continue
            raw.append((snap.sotp_discount, snap))

        # Sort by sotp_discount descending (highest = best opportunity)
        raw.sort(key=lambda t: t[0], reverse=True)

        decisions: list[ReplayDecisionView] = []
        for rank, (discount, snap) in enumerate(raw, start=1):
            action = _assign_action(snap.is_capital_candidate_eligible, discount)
            decisions.append(
                ReplayDecisionView(
                    company_id=snap.company_id,
                    ticker=snap.ticker,
                    as_of_date=as_of_date,
                    snapshot_id=snap.snapshot_id,
                    snapshot_as_of=snap.as_of_date,
                    reviewer_state=snap.reviewer_state,
                    is_capital_candidate=snap.is_capital_candidate_eligible,
                    sotp_equity_value_millions=snap.sotp_equity_value_millions,
                    market_cap_millions=snap.market_cap_millions,
                    sotp_discount=discount,
                    rank=rank,
                    action=action,
                )
            )

        return decisions

    def run_range(
        self,
        company_ids: list[str],
        dates: list[date],
    ) -> dict[date, list[ReplayDecisionView]]:
        """
        Run the replay engine across multiple dates.

        Returns a dict mapping each date to its ranked decision list.
        Useful for building a time-series of decisions for backtesting.
        """
        return {d: self.run(company_ids, d) for d in sorted(dates)}

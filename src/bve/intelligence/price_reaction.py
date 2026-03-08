"""
Price reaction tracker — Wave 1B.

Creates event outcome records when valuation diffs are produced, then resolves
price return windows (T+1, T+5, T+30, T+90, T+180 trading days) incrementally
as market price data becomes available.

Design
------
- One ``EventOutcome`` row per valuation diff (event_id is the natural key).
- Resolution is incremental: each T-window is resolved independently once
  the target trading day has passed and price data exists in ``market_prices``.
- ``fully_resolved`` is set when all five windows are populated.
- Trading-day arithmetic uses ``bve.utils.trading_calendar`` (Mon–Fri, no holidays).
- Volume spike detection: volume > 2× 20-day average on signal_date is flagged.
  This is an early indicator that the market was aware of the event.

Event stratification fields (Wave 3)
-------------------------------------
``event_type`` is stored raw. Calibration queries should segment by:
    event_type + phase + endpoint_type
to avoid aggregating across heterogeneous event buckets (phase2_surrogate vs
phase3_os behave very differently). The stratification happens at query time,
not at write time, so all data is preserved.

Usage
-----
    tracker = PriceReactionTracker(knowledge)

    # After each valuation diff:
    tracker.record(diff, signal, ticker="RLAY")

    # At top of each run_once() cycle, after price refresh:
    n_resolved = tracker.resolve_pending()
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import KnowledgeStore, StoredValuationDiff
from bve.intelligence.schemas.signals import StructuredSignal
from bve.utils.trading_calendar import (
    WINDOWS_TD,
    is_trading_day_elapsed,
    resolution_targets,
    trading_days_after,
)

_LOG = logging.getLogger("bve.intelligence.price_reaction")

# Volume spike multiplier: flag if signal-day volume > N × 20-day avg.
_VOLUME_SPIKE_MULTIPLIER = 2.0


class EventOutcome(BaseModel):
    """In-memory representation of one event_outcomes row."""

    outcome_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_id: str
    asset_id: str
    ticker: Optional[str]
    signal_date: date
    event_type: Optional[str]
    model_delta_npv: Optional[float]
    model_delta_pct: Optional[float]
    volume_spike_at_signal: bool = False

    price_before: Optional[float] = None

    price_t1: Optional[float] = None
    market_return_t1: Optional[float] = None
    resolved_t1: bool = False

    price_t5: Optional[float] = None
    market_return_t5: Optional[float] = None
    resolved_t5: bool = False

    price_t30: Optional[float] = None
    market_return_t30: Optional[float] = None
    resolved_t30: bool = False

    price_t90: Optional[float] = None
    market_return_t90: Optional[float] = None
    resolved_t90: bool = False

    price_t180: Optional[float] = None
    market_return_t180: Optional[float] = None
    resolved_t180: bool = False

    fully_resolved: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PriceReactionTracker:
    """
    Records and resolves event outcome price windows.

    Parameters
    ----------
    knowledge:
        KnowledgeStore instance with market_prices + event_outcomes tables.
    logger:
        Optional logger override.
    """

    def __init__(
        self,
        knowledge: KnowledgeStore,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.knowledge = knowledge
        self.logger = logger or _LOG

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        diff: StoredValuationDiff,
        signal: StructuredSignal,
        ticker: Optional[str] = None,
    ) -> Optional[EventOutcome]:
        """
        Create an ``event_outcomes`` row for a valuation diff.

        Skips if an outcome for this ``event_id`` already exists (idempotent).

        Parameters
        ----------
        diff:
            The stored valuation diff that triggered the outcome record.
        signal:
            The associated structured signal (provides event_type + signal_date).
        ticker:
            Stock ticker for price lookup.  If None, the outcome row is created
            without price data (model delta still recorded).

        Returns
        -------
        EventOutcome or None
            The created outcome, or None if one already exists for this event_id.
        """
        if self._outcome_exists(diff.event_id):
            return None

        signal_date = signal.signal_date
        before_npv = float(diff.valuation_before.get("rnpv_millions") or 0.0)
        delta_pct: Optional[float] = None
        if before_npv != 0:
            delta_pct = round(diff.delta_npv / abs(before_npv) * 100.0, 4)

        # Price at signal date (T-0).
        price_before: Optional[float] = None
        volume_spike = False
        if ticker:
            price_row = self.knowledge.get_price_on_or_before(ticker, signal_date)
            if price_row:
                price_before = price_row.adj_close_usd
                avg_vol = self.knowledge.get_20day_avg_volume(ticker, signal_date)
                if avg_vol and avg_vol > 0:
                    volume_spike = price_row.volume > (_VOLUME_SPIKE_MULTIPLIER * avg_vol)

        outcome = EventOutcome(
            event_id=diff.event_id,
            asset_id=diff.asset_id,
            ticker=ticker,
            signal_date=signal_date,
            event_type=signal.event_type.value,
            model_delta_npv=diff.delta_npv,
            model_delta_pct=delta_pct,
            volume_spike_at_signal=volume_spike,
            price_before=price_before,
        )

        self._write_outcome(outcome)
        self.logger.info(
            "event_outcome_created event_id=%s asset=%s ticker=%s date=%s delta=%.1fM",
            diff.event_id,
            diff.asset_id,
            ticker or "none",
            signal_date,
            diff.delta_npv,
        )
        return outcome

    def resolve_pending(self, as_of: Optional[date] = None) -> int:
        """
        Resolve price windows for all unresolved outcomes where sufficient time
        has elapsed.

        Parameters
        ----------
        as_of:
            Reference date for elapsed-time checks.  Defaults to today (UTC).

        Returns
        -------
        int
            Number of window resolutions written (may span multiple outcomes).
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc).date()

        rows = self.knowledge._conn.execute(
            """
            SELECT outcome_id, asset_id, ticker, signal_date,
                   price_before,
                   resolved_t1, resolved_t5, resolved_t30, resolved_t90, resolved_t180
            FROM event_outcomes WHERE fully_resolved = 0
            """
        ).fetchall()

        total_resolved = 0
        for row in rows:
            outcome_id = row["outcome_id"]
            ticker = row["ticker"]
            signal_date = date.fromisoformat(row["signal_date"])
            price_before = row["price_before"]

            if not ticker or price_before is None:
                continue

            updates: dict[str, object] = {}
            all_done = True

            for w in WINDOWS_TD:
                col_resolved = f"resolved_t{w}"
                if row[col_resolved]:
                    continue  # already resolved
                all_done = False

                if not is_trading_day_elapsed(signal_date, w, as_of=as_of):
                    all_done = False
                    continue

                target_date = trading_days_after(signal_date, w)
                price_row = self.knowledge.get_price_on_or_before(ticker, target_date)
                if price_row is None:
                    all_done = False
                    continue

                ret = round((price_row.adj_close_usd - price_before) / price_before, 6)
                updates[f"price_t{w}"] = price_row.adj_close_usd
                updates[f"market_return_t{w}"] = ret
                updates[f"resolved_t{w}"] = 1
                total_resolved += 1

            if not updates:
                continue

            # Check if all windows are now resolved.
            currently_resolved = {
                f"resolved_t{w}": bool(row[f"resolved_t{w}"]) for w in WINDOWS_TD
            }
            currently_resolved.update({k: bool(v) for k, v in updates.items() if k.startswith("resolved")})
            fully = all(currently_resolved.get(f"resolved_t{w}", False) for w in WINDOWS_TD)
            updates["fully_resolved"] = 1 if fully else 0

            set_clause = ", ".join(f"{k} = ?" for k in updates)
            self.knowledge._conn.execute(
                f"UPDATE event_outcomes SET {set_clause} WHERE outcome_id = ?",
                [*updates.values(), outcome_id],
            )

        self.knowledge._conn.commit()
        if total_resolved:
            self.logger.info("event_outcomes_resolved count=%d as_of=%s", total_resolved, as_of)
        return total_resolved

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _outcome_exists(self, event_id: str) -> bool:
        row = self.knowledge._conn.execute(
            "SELECT 1 FROM event_outcomes WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None

    def _write_outcome(self, outcome: EventOutcome) -> None:
        self.knowledge._conn.execute(
            """
            INSERT INTO event_outcomes(
                outcome_id, event_id, asset_id, ticker, signal_date, event_type,
                model_delta_npv, model_delta_pct, volume_spike_at_signal, price_before,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                outcome.outcome_id,
                outcome.event_id,
                outcome.asset_id,
                outcome.ticker,
                outcome.signal_date.isoformat(),
                outcome.event_type,
                outcome.model_delta_npv,
                outcome.model_delta_pct,
                1 if outcome.volume_spike_at_signal else 0,
                outcome.price_before,
                outcome.created_at.isoformat(),
            ),
        )
        self.knowledge._conn.commit()

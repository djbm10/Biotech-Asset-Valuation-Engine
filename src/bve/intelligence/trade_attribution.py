"""
Wave P2 — Decision + Attribution Layer.

Records when a position is initiated or sized based on a signal, then
attributes realised market return back to the originating signal and analyst
decision.  Closes the loop between "signal fired → position taken → outcome."

Flow
----
1. ``record_decision(signal_id, asset_id, ...)`` — called when an analyst or
   automated rule acts on a ranked opportunity.  Creates a ``TradeDecision``.

2. ``record_outcome(decision_id, return_pct, ...)`` — called when the position
   is closed or the evaluation window expires.  Updates the ``TradeDecision``
   with realised P&L and sets ``attributed=True``.

3. ``AttributionReport.compute(store)`` — reads attributed decisions and
   produces per-signal, per-event-type, and overall attribution statistics.

Storage
-------
Two new KnowledgeStore tables (created lazily via _ensure_column pattern):
  - ``trade_decisions`` — one row per decision (entry intent)
  - Attribution is stored in-place on the same row (no second table)

Design invariants
-----------------
- One signal can produce at most one decision per asset (dedup on
  ``(signal_id, asset_id)``).
- ``return_pct`` is always the raw price return, not risk-adjusted.
  Risk-adjustment happens in ``AttributionReport``.
- Decisions can be ``pending`` (no outcome yet) or ``attributed``.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

DecisionStatus = Literal["pending", "attributed", "cancelled"]
SignalDirection = Literal["long", "short", "flat"]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TradeDecision(BaseModel):
    """
    One analyst/automated decision to enter or resize a position.

    Attributes
    ----------
    decision_id:
        UUID for this specific decision record.
    signal_id:
        The ``StructuredSignal.id`` that triggered this decision.
    asset_id:
        Intelligence-layer asset ID.
    event_type:
        String event type (e.g. ``"trial_readout"``).
    signal_date:
        Date of the triggering signal.
    decision_date:
        Date the position was initiated.
    direction:
        ``"long"`` | ``"short"`` | ``"flat"`` (exit).
    position_weight:
        Fraction of portfolio AUM allocated to this position (from
        PortfolioSizingEngine).  None when sizing was not computed.
    position_aum_millions:
        Dollar amount in $M if known.
    composite_score:
        Composite ranking score at decision time.
    mispricing_score:
        Model-implied mispricing fraction at decision time.
    sizing_method:
        Which sizing method was used (``"half_kelly"``, ``"proportional"``,
        ``"equal_weight"``).
    analyst_id:
        Identifier of the analyst or automation system that made the decision.
        Defaults to ``"system"``.
    rationale:
        Free-text rationale for the decision.
    status:
        ``"pending"`` until outcome is recorded.
    realised_return_pct:
        Filled by ``record_outcome()``.
    attribution_score:
        ``realised_return_pct × position_weight`` when both are available.
        Measures the contribution of this position to portfolio return.
    attributed_at:
        Timestamp when outcome was recorded.
    created_at:
        Timestamp when the decision was created.
    """

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    asset_id: str
    event_type: str
    signal_date: date
    decision_date: date = Field(default_factory=lambda: datetime.now(timezone.utc).date())
    direction: SignalDirection = "long"
    position_weight: Optional[float] = None
    position_aum_millions: Optional[float] = None
    composite_score: Optional[float] = None
    mispricing_score: Optional[float] = None
    sizing_method: Optional[str] = None
    analyst_id: str = "system"
    rationale: Optional[str] = None
    status: DecisionStatus = "pending"

    # Filled on attribution
    realised_return_pct: Optional[float] = None
    attribution_score: Optional[float] = None
    attributed_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Attribution output models
# ---------------------------------------------------------------------------

class PerSignalAttribution(BaseModel):
    """Attribution for one signal_id."""

    signal_id: str
    event_type: str
    n_decisions: int
    total_attribution_score: float
    avg_realised_return_pct: Optional[float]
    hit_rate: Optional[float]       # fraction of decisions with return > 0


class AttributionReport(BaseModel):
    """Portfolio-level attribution summary."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    n_total_decisions: int
    n_attributed: int
    n_pending: int
    coverage: Optional[float]       # n_attributed / n_total
    total_attribution_score: float  # Σ(return × weight)
    avg_realised_return_pct: Optional[float]
    hit_rate: Optional[float]       # fraction of attributed decisions with return > 0
    per_signal: list[PerSignalAttribution] = Field(default_factory=list)
    per_event_type: dict[str, float] = Field(default_factory=dict)  # event_type → avg return


# ---------------------------------------------------------------------------
# TradeAttributionTracker
# ---------------------------------------------------------------------------

class TradeAttributionTracker:
    """
    Records trade decisions and attributes outcomes back to signals.

    Parameters
    ----------
    store:
        A ``KnowledgeStore`` instance.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema setup
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        """Create trade_decisions table if it doesn't exist."""
        self.store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_decisions (
                decision_id          TEXT PRIMARY KEY,
                signal_id            TEXT NOT NULL,
                asset_id             TEXT NOT NULL,
                event_type           TEXT NOT NULL,
                signal_date          TEXT NOT NULL,
                decision_date        TEXT NOT NULL,
                direction            TEXT NOT NULL DEFAULT 'long',
                position_weight      REAL,
                position_aum_millions REAL,
                composite_score      REAL,
                mispricing_score     REAL,
                sizing_method        TEXT,
                analyst_id           TEXT NOT NULL DEFAULT 'system',
                rationale            TEXT,
                status               TEXT NOT NULL DEFAULT 'pending',
                realised_return_pct  REAL,
                attribution_score    REAL,
                attributed_at        TEXT,
                created_at           TEXT NOT NULL
            )
            """
        )
        self.store._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_decisions_signal_asset
                ON trade_decisions(signal_id, asset_id)
            """
        )
        self.store._conn.commit()

    # ------------------------------------------------------------------
    # Record decision
    # ------------------------------------------------------------------

    def record_decision(
        self,
        signal_id: str,
        asset_id: str,
        *,
        event_type: str,
        signal_date: date,
        direction: SignalDirection = "long",
        position_weight: Optional[float] = None,
        position_aum_millions: Optional[float] = None,
        composite_score: Optional[float] = None,
        mispricing_score: Optional[float] = None,
        sizing_method: Optional[str] = None,
        analyst_id: str = "system",
        rationale: Optional[str] = None,
    ) -> TradeDecision:
        """
        Record a new trade decision.  Idempotent: if a decision already exists
        for ``(signal_id, asset_id)``, returns the existing record.

        Returns
        -------
        TradeDecision
        """
        existing = self.store._conn.execute(
            "SELECT * FROM trade_decisions WHERE signal_id = ? AND asset_id = ?",
            (signal_id, asset_id),
        ).fetchone()
        if existing:
            return TradeDecision(**dict(existing))

        decision = TradeDecision(
            signal_id=signal_id,
            asset_id=asset_id,
            event_type=event_type,
            signal_date=signal_date,
            direction=direction,
            position_weight=position_weight,
            position_aum_millions=position_aum_millions,
            composite_score=composite_score,
            mispricing_score=mispricing_score,
            sizing_method=sizing_method,
            analyst_id=analyst_id,
            rationale=rationale,
        )
        self.store._conn.execute(
            """
            INSERT OR IGNORE INTO trade_decisions
                (decision_id, signal_id, asset_id, event_type, signal_date,
                 decision_date, direction, position_weight, position_aum_millions,
                 composite_score, mispricing_score, sizing_method, analyst_id,
                 rationale, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                decision.decision_id,
                decision.signal_id,
                decision.asset_id,
                decision.event_type,
                str(decision.signal_date),
                str(decision.decision_date),
                decision.direction,
                decision.position_weight,
                decision.position_aum_millions,
                decision.composite_score,
                decision.mispricing_score,
                decision.sizing_method,
                decision.analyst_id,
                decision.rationale,
                decision.created_at.isoformat(),
            ),
        )
        self.store._conn.commit()
        return decision

    # ------------------------------------------------------------------
    # Record outcome
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        decision_id: str,
        realised_return_pct: float,
        *,
        attributed_at: Optional[datetime] = None,
    ) -> Optional[TradeDecision]:
        """
        Attribute a realised return to a pending decision.

        Computes ``attribution_score = realised_return_pct × position_weight``
        when ``position_weight`` is set; otherwise stores ``realised_return_pct``
        directly as ``attribution_score``.

        Returns the updated ``TradeDecision``, or None if not found.
        """
        row = self.store._conn.execute(
            "SELECT * FROM trade_decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None

        row_dict = dict(row)
        weight = row_dict.get("position_weight")
        attr_score = (
            realised_return_pct * float(weight)
            if weight is not None
            else realised_return_pct
        )
        ts = (attributed_at or datetime.now(timezone.utc)).isoformat()

        self.store._conn.execute(
            """
            UPDATE trade_decisions
               SET realised_return_pct = ?,
                   attribution_score   = ?,
                   attributed_at       = ?,
                   status              = 'attributed'
             WHERE decision_id = ?
            """,
            (realised_return_pct, attr_score, ts, decision_id),
        )
        self.store._conn.commit()

        row_dict.update(
            realised_return_pct=realised_return_pct,
            attribution_score=attr_score,
            attributed_at=ts,
            status="attributed",
        )
        return TradeDecision(**row_dict)

    # ------------------------------------------------------------------
    # Attribution report
    # ------------------------------------------------------------------

    def report(self) -> AttributionReport:
        """
        Compute attribution statistics from all decisions in the store.

        Returns
        -------
        AttributionReport
        """
        rows = self.store._conn.execute(
            "SELECT * FROM trade_decisions ORDER BY created_at"
        ).fetchall()
        all_rows = [dict(r) for r in rows]
        attributed = [r for r in all_rows if r["status"] == "attributed"]

        n_total = len(all_rows)
        n_attributed = len(attributed)
        n_pending = len([r for r in all_rows if r["status"] == "pending"])
        coverage = n_attributed / n_total if n_total > 0 else None

        total_attr = sum(r["attribution_score"] or 0.0 for r in attributed)
        avg_return: Optional[float] = None
        hit_rate: Optional[float] = None

        if attributed:
            returns = [r["realised_return_pct"] for r in attributed if r["realised_return_pct"] is not None]
            if returns:
                avg_return = sum(returns) / len(returns)
                hit_rate = sum(1 for r in returns if r > 0) / len(returns)

        # Per-signal attribution
        from collections import defaultdict
        by_signal: dict[str, list[dict]] = defaultdict(list)
        for r in attributed:
            by_signal[r["signal_id"]].append(r)

        per_signal: list[PerSignalAttribution] = []
        for sig_id, sig_rows in by_signal.items():
            returns = [r["realised_return_pct"] for r in sig_rows if r["realised_return_pct"] is not None]
            per_signal.append(
                PerSignalAttribution(
                    signal_id=sig_id,
                    event_type=sig_rows[0]["event_type"],
                    n_decisions=len(sig_rows),
                    total_attribution_score=sum(r["attribution_score"] or 0.0 for r in sig_rows),
                    avg_realised_return_pct=sum(returns) / len(returns) if returns else None,
                    hit_rate=sum(1 for r in returns if r > 0) / len(returns) if returns else None,
                )
            )

        # Per-event-type average return
        by_event_type: dict[str, list[float]] = defaultdict(list)
        for r in attributed:
            if r["realised_return_pct"] is not None:
                by_event_type[r["event_type"]].append(r["realised_return_pct"])
        per_event_type = {
            et: sum(vals) / len(vals)
            for et, vals in by_event_type.items()
            if vals
        }

        return AttributionReport(
            n_total_decisions=n_total,
            n_attributed=n_attributed,
            n_pending=n_pending,
            coverage=coverage,
            total_attribution_score=total_attr,
            avg_realised_return_pct=avg_return,
            hit_rate=hit_rate,
            per_signal=per_signal,
            per_event_type=per_event_type,
        )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_decision(self, decision_id: str) -> Optional[TradeDecision]:
        """Return a specific decision by ID, or None if not found."""
        row = self.store._conn.execute(
            "SELECT * FROM trade_decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return TradeDecision(**dict(row)) if row else None

    def get_decisions(
        self,
        *,
        asset_id: Optional[str] = None,
        status: Optional[DecisionStatus] = None,
        limit: int = 200,
    ) -> list[TradeDecision]:
        """Return decisions, optionally filtered by asset_id and/or status."""
        conditions: list[str] = []
        params: list[object] = []
        if asset_id is not None:
            conditions.append("asset_id = ?")
            params.append(asset_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.store._conn.execute(
            f"SELECT * FROM trade_decisions {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [TradeDecision(**dict(r)) for r in rows]

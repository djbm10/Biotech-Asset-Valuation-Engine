"""
Wave J — Decision + Position Layer.

Records investment decisions with full portfolio context, tracks positions
from entry to exit, and stores outcome attributions for closed trades.

Design principles
-----------------
- Recommended vs executed are distinct fields.  The system always records
  what it recommended; the analyst records what was actually done.  The gap
  between them is the primary source of "execution drift" learning.
- Portfolio context is snapshotted at decision time (not recomputed live).
  ``portfolio_exposure_pct_at_decision``, ``catalyst_bucket_exposure_pct``,
  and ``indication_bucket_exposure_pct`` must be passed in by the caller —
  they are durable facts about the state of the portfolio at the moment the
  decision was made.
- ``holding_period_days`` is computed at close, never stored before then.
- All tables are created lazily on first ``DecisionLayer`` construction.
- No LLM calls, no external API calls.

Attribution taxonomy
--------------------
``pos_error``          — model predicted wrong direction on a trial/FDA event
``timing_error``       — directionally correct but signal was stale (>30d old)
``sizing_error``       — correct direction, but position was under/over-sized
``thesis_error``       — a key thesis claim was refuted for this asset
``market_drift``       — market moved for reasons unrelated to the catalyst
``confirmed_thesis``   — thesis played out (see WeeklyReviewEngine for strict criteria)
``unclassified``       — none of the above

Exit reasons
------------
``catalyst_resolved``  — the catalyst that drove entry resolved
``thesis_refuted``     — a key thesis claim was explicitly refuted
``stop_loss``          — hit predefined loss limit
``profit_target``      — hit predefined gain target
``rebalance``          — portfolio-level rebalance driven exit
``manual``             — analyst override
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

DecisionAction = Literal["buy", "size_up", "hold", "reduce", "pass", "exit"]
ConvictionTier = Literal["high", "medium", "low", "speculative"]
LiquidityBucket = Literal["liquid", "semi_liquid", "illiquid"]
AttributionType = Literal[
    "pos_error",
    "timing_error",
    "sizing_error",
    "thesis_error",
    "market_drift",
    "confirmed_thesis",
    "unclassified",
]
ExitReason = Literal[
    "catalyst_resolved",
    "thesis_refuted",
    "stop_loss",
    "profit_target",
    "rebalance",
    "manual",
]


# ---------------------------------------------------------------------------
# DecisionRecord
# ---------------------------------------------------------------------------

class DecisionRecord(BaseModel):
    """
    One investment decision recommendation, with optional execution record.

    ``recommended_*`` fields are always set at creation time.
    ``executed_*`` fields are set later via ``DecisionLayer.update_execution()``
    and may differ from recommended values.
    """

    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    signal_id: Optional[str] = None
    thesis_id: Optional[str] = None

    # Recommended (set by system)
    recommended_action: DecisionAction
    recommended_size_pct: Optional[float] = None

    # Executed (set by analyst after actual trade)
    executed_action: Optional[DecisionAction] = None
    executed_size_pct: Optional[float] = None

    # Signal quality at decision time
    signal_strength: Optional[float] = None

    # Portfolio context snapshot at decision time
    portfolio_exposure_pct_at_decision: Optional[float] = None
    catalyst_bucket_exposure_pct: Optional[float] = None
    indication_bucket_exposure_pct: Optional[float] = None
    liquidity_bucket: Optional[LiquidityBucket] = None
    conviction_tier: Optional[ConvictionTier] = None

    # Critic output at decision time
    critic_flags_count: int = 0

    # Human-readable rationale
    reasoning_text: str = ""

    decided_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# PositionSnapshot
# ---------------------------------------------------------------------------

class PositionSnapshot(BaseModel):
    """
    One position record.  Updated at close to add exit fields.

    ``holding_period_days`` is computed at close and is None for open positions.
    """

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    decision_id: Optional[str] = None
    entry_date: date
    entry_price_usd: Optional[float] = None
    current_size_pct: float
    linked_catalyst_id: Optional[str] = None
    thesis_strength_at_entry: Optional[float] = None
    is_active: bool = True

    # Set at close
    exit_date: Optional[date] = None
    exit_price_usd: Optional[float] = None
    exit_reason: Optional[ExitReason] = None
    holding_period_days: Optional[int] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# OutcomeAttribution
# ---------------------------------------------------------------------------

class OutcomeAttribution(BaseModel):
    """Classified outcome for a closed trade decision."""

    attribution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str
    asset_id: str
    return_pct: float
    attribution_type: AttributionType
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str = ""


# ---------------------------------------------------------------------------
# DecisionLayer
# ---------------------------------------------------------------------------

class DecisionLayer:
    """
    Manages decision records, position snapshots, and outcome attributions.

    Parameters
    ----------
    store:
        A ``KnowledgeStore`` instance.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self.store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_records (
                decision_id                      TEXT PRIMARY KEY,
                asset_id                         TEXT NOT NULL,
                signal_id                        TEXT,
                thesis_id                        TEXT,
                recommended_action               TEXT NOT NULL,
                recommended_size_pct             REAL,
                executed_action                  TEXT,
                executed_size_pct                REAL,
                signal_strength                  REAL,
                portfolio_exposure_pct_at_decision REAL,
                catalyst_bucket_exposure_pct     REAL,
                indication_bucket_exposure_pct   REAL,
                liquidity_bucket                 TEXT,
                conviction_tier                  TEXT,
                critic_flags_count               INTEGER NOT NULL DEFAULT 0,
                reasoning_text                   TEXT NOT NULL DEFAULT '',
                decided_at                       TEXT NOT NULL
            )
            """
        )
        self.store._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_decision_records_asset
                ON decision_records(asset_id, decided_at)
            """
        )
        self.store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS position_snapshots (
                snapshot_id               TEXT PRIMARY KEY,
                asset_id                  TEXT NOT NULL,
                decision_id               TEXT,
                entry_date                TEXT NOT NULL,
                entry_price_usd           REAL,
                current_size_pct          REAL NOT NULL,
                linked_catalyst_id        TEXT,
                thesis_strength_at_entry  REAL,
                is_active                 INTEGER NOT NULL DEFAULT 1,
                exit_date                 TEXT,
                exit_price_usd            REAL,
                exit_reason               TEXT,
                holding_period_days       INTEGER,
                created_at                TEXT NOT NULL
            )
            """
        )
        self.store._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_position_snapshots_asset
                ON position_snapshots(asset_id, is_active)
            """
        )
        self.store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS outcome_attributions (
                attribution_id   TEXT PRIMARY KEY,
                decision_id      TEXT NOT NULL,
                asset_id         TEXT NOT NULL,
                return_pct       REAL NOT NULL,
                attribution_type TEXT NOT NULL,
                resolved_at      TEXT NOT NULL,
                notes            TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self.store._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_outcome_attributions_decision
                ON outcome_attributions(decision_id)
            """
        )
        self.store._conn.commit()

    # ------------------------------------------------------------------
    # Decision management
    # ------------------------------------------------------------------

    def record_decision(
        self,
        asset_id: str,
        recommended_action: DecisionAction,
        *,
        signal_id: Optional[str] = None,
        thesis_id: Optional[str] = None,
        recommended_size_pct: Optional[float] = None,
        signal_strength: Optional[float] = None,
        portfolio_exposure_pct_at_decision: Optional[float] = None,
        catalyst_bucket_exposure_pct: Optional[float] = None,
        indication_bucket_exposure_pct: Optional[float] = None,
        liquidity_bucket: Optional[LiquidityBucket] = None,
        conviction_tier: Optional[ConvictionTier] = None,
        critic_flags_count: int = 0,
        reasoning_text: str = "",
        decided_at: Optional[datetime] = None,
    ) -> DecisionRecord:
        """
        Record a new investment decision recommendation.

        Parameters
        ----------
        decided_at:
            Explicit timestamp for the decision.  When provided, overrides the
            default ``datetime.now(timezone.utc)``.  Used by replay mode to
            place decisions at a specific historical datetime.
        """
        decision = DecisionRecord(
            asset_id=asset_id,
            signal_id=signal_id,
            thesis_id=thesis_id,
            recommended_action=recommended_action,
            recommended_size_pct=recommended_size_pct,
            signal_strength=signal_strength,
            portfolio_exposure_pct_at_decision=portfolio_exposure_pct_at_decision,
            catalyst_bucket_exposure_pct=catalyst_bucket_exposure_pct,
            indication_bucket_exposure_pct=indication_bucket_exposure_pct,
            liquidity_bucket=liquidity_bucket,
            conviction_tier=conviction_tier,
            critic_flags_count=critic_flags_count,
            reasoning_text=reasoning_text,
            decided_at=decided_at if decided_at is not None else datetime.now(timezone.utc),
        )
        self.store._conn.execute(
            """
            INSERT OR IGNORE INTO decision_records
                (decision_id, asset_id, signal_id, thesis_id,
                 recommended_action, recommended_size_pct,
                 signal_strength,
                 portfolio_exposure_pct_at_decision,
                 catalyst_bucket_exposure_pct,
                 indication_bucket_exposure_pct,
                 liquidity_bucket, conviction_tier,
                 critic_flags_count, reasoning_text, decided_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.asset_id,
                decision.signal_id,
                decision.thesis_id,
                decision.recommended_action,
                decision.recommended_size_pct,
                decision.signal_strength,
                decision.portfolio_exposure_pct_at_decision,
                decision.catalyst_bucket_exposure_pct,
                decision.indication_bucket_exposure_pct,
                decision.liquidity_bucket,
                decision.conviction_tier,
                decision.critic_flags_count,
                decision.reasoning_text,
                decision.decided_at.isoformat(),
            ),
        )
        self.store._conn.commit()
        return decision

    def update_execution(
        self,
        decision_id: str,
        executed_action: DecisionAction,
        executed_size_pct: Optional[float] = None,
    ) -> Optional[DecisionRecord]:
        """
        Record what was actually executed (may differ from recommendation).

        Returns the updated DecisionRecord, or None if not found.
        """
        row = self.store._conn.execute(
            "SELECT * FROM decision_records WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        self.store._conn.execute(
            """
            UPDATE decision_records
               SET executed_action   = ?,
                   executed_size_pct = ?
             WHERE decision_id = ?
            """,
            (executed_action, executed_size_pct, decision_id),
        )
        self.store._conn.commit()
        row_dict = dict(row)
        row_dict.update(
            executed_action=executed_action,
            executed_size_pct=executed_size_pct,
        )
        return self._row_to_decision(row_dict)

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        """Return a decision by ID."""
        row = self.store._conn.execute(
            "SELECT * FROM decision_records WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        return self._row_to_decision(dict(row)) if row else None

    def get_decision_history(
        self,
        asset_id: Optional[str] = None,
        *,
        limit: int = 100,
    ) -> list[DecisionRecord]:
        """Return decisions, optionally filtered to an asset."""
        if asset_id:
            rows = self.store._conn.execute(
                "SELECT * FROM decision_records WHERE asset_id = ? "
                "ORDER BY decided_at DESC LIMIT ?",
                (asset_id, limit),
            ).fetchall()
        else:
            rows = self.store._conn.execute(
                "SELECT * FROM decision_records ORDER BY decided_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_decision(dict(r)) for r in rows]

    def model_vs_execution_drift(self) -> dict:
        """
        Summary of cases where executed_action differs from recommended_action.

        Returns
        -------
        dict with keys: n_total, n_with_execution, n_diverged, pct_diverged
        """
        rows = self.store._conn.execute(
            "SELECT recommended_action, executed_action FROM decision_records"
        ).fetchall()
        n_total = len(rows)
        with_exec = [r for r in rows if r["executed_action"] is not None]
        diverged = [
            r for r in with_exec
            if r["executed_action"] != r["recommended_action"]
        ]
        pct = round(len(diverged) / len(with_exec), 4) if with_exec else None
        return {
            "n_total": n_total,
            "n_with_execution": len(with_exec),
            "n_diverged": len(diverged),
            "pct_diverged": pct,
        }

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def record_position(
        self,
        asset_id: str,
        current_size_pct: float,
        *,
        entry_date: Optional[date] = None,
        entry_price_usd: Optional[float] = None,
        decision_id: Optional[str] = None,
        linked_catalyst_id: Optional[str] = None,
        thesis_strength_at_entry: Optional[float] = None,
    ) -> PositionSnapshot:
        """Open a new position."""
        snap = PositionSnapshot(
            asset_id=asset_id,
            decision_id=decision_id,
            entry_date=entry_date or date.today(),
            entry_price_usd=entry_price_usd,
            current_size_pct=current_size_pct,
            linked_catalyst_id=linked_catalyst_id,
            thesis_strength_at_entry=thesis_strength_at_entry,
        )
        self.store._conn.execute(
            """
            INSERT OR IGNORE INTO position_snapshots
                (snapshot_id, asset_id, decision_id, entry_date, entry_price_usd,
                 current_size_pct, linked_catalyst_id, thesis_strength_at_entry,
                 is_active, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                snap.snapshot_id,
                snap.asset_id,
                snap.decision_id,
                snap.entry_date.isoformat(),
                snap.entry_price_usd,
                snap.current_size_pct,
                snap.linked_catalyst_id,
                snap.thesis_strength_at_entry,
                snap.created_at.isoformat(),
            ),
        )
        self.store._conn.commit()
        return snap

    def close_position(
        self,
        asset_id: str,
        exit_price_usd: Optional[float] = None,
        exit_reason: Optional[ExitReason] = None,
        *,
        exit_date: Optional[date] = None,
    ) -> Optional[PositionSnapshot]:
        """
        Close the most recent active position for *asset_id*.

        Sets ``is_active=0``, ``exit_date``, ``exit_price_usd``,
        ``exit_reason``, and computes ``holding_period_days``.

        Returns the updated PositionSnapshot, or None if no active position.
        """
        row = self.store._conn.execute(
            "SELECT * FROM position_snapshots "
            "WHERE asset_id = ? AND is_active = 1 "
            "ORDER BY created_at DESC LIMIT 1",
            (asset_id,),
        ).fetchone()
        if row is None:
            return None

        ed = exit_date or date.today()
        entry = date.fromisoformat(str(row["entry_date"]))
        holding_days = (ed - entry).days

        self.store._conn.execute(
            """
            UPDATE position_snapshots
               SET is_active          = 0,
                   exit_date          = ?,
                   exit_price_usd     = ?,
                   exit_reason        = ?,
                   holding_period_days = ?
             WHERE snapshot_id = ?
            """,
            (
                ed.isoformat(),
                exit_price_usd,
                exit_reason,
                holding_days,
                row["snapshot_id"],
            ),
        )
        self.store._conn.commit()
        row_dict = dict(row)
        row_dict.update(
            is_active=0,
            exit_date=ed.isoformat(),
            exit_price_usd=exit_price_usd,
            exit_reason=exit_reason,
            holding_period_days=holding_days,
        )
        return self._row_to_snapshot(row_dict)

    def get_active_positions(self) -> list[PositionSnapshot]:
        """Return all currently open positions."""
        rows = self.store._conn.execute(
            "SELECT * FROM position_snapshots WHERE is_active = 1 "
            "ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_snapshot(dict(r)) for r in rows]

    def get_positions(
        self,
        asset_id: Optional[str] = None,
        *,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[PositionSnapshot]:
        """Return positions with optional filters."""
        conditions = []
        params: list[object] = []
        if asset_id:
            conditions.append("asset_id = ?")
            params.append(asset_id)
        if active_only:
            conditions.append("is_active = 1")
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.store._conn.execute(
            f"SELECT * FROM position_snapshots {where} "
            f"ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row_to_snapshot(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Outcome attribution
    # ------------------------------------------------------------------

    def attribute_outcome(
        self,
        decision_id: str,
        return_pct: float,
        attribution_type: AttributionType,
        notes: str = "",
    ) -> OutcomeAttribution:
        """Record an outcome attribution for a decision."""
        # Look up asset_id from the decision
        row = self.store._conn.execute(
            "SELECT asset_id FROM decision_records WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        asset_id = str(row["asset_id"]) if row else ""

        attr = OutcomeAttribution(
            decision_id=decision_id,
            asset_id=asset_id,
            return_pct=return_pct,
            attribution_type=attribution_type,
            notes=notes,
        )
        self.store._conn.execute(
            """
            INSERT OR IGNORE INTO outcome_attributions
                (attribution_id, decision_id, asset_id, return_pct,
                 attribution_type, resolved_at, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attr.attribution_id,
                attr.decision_id,
                attr.asset_id,
                attr.return_pct,
                attr.attribution_type,
                attr.resolved_at.isoformat(),
                attr.notes,
            ),
        )
        self.store._conn.commit()
        return attr

    def get_attributions(
        self,
        asset_id: Optional[str] = None,
        *,
        attribution_type: Optional[AttributionType] = None,
        limit: int = 200,
    ) -> list[OutcomeAttribution]:
        """Return outcome attributions with optional filters."""
        conditions: list[str] = []
        params: list[object] = []
        if asset_id:
            conditions.append("asset_id = ?")
            params.append(asset_id)
        if attribution_type:
            conditions.append("attribution_type = ?")
            params.append(attribution_type)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.store._conn.execute(
            f"SELECT * FROM outcome_attributions {where} "
            f"ORDER BY resolved_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row_to_attribution(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_decision(row: dict) -> DecisionRecord:
        decided_at_str = row.get("decided_at", "")
        try:
            decided_at = datetime.fromisoformat(str(decided_at_str))
            if decided_at.tzinfo is None:
                decided_at = decided_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            decided_at = datetime.now(timezone.utc)

        return DecisionRecord(
            decision_id=str(row["decision_id"]),
            asset_id=str(row["asset_id"]),
            signal_id=row.get("signal_id"),
            thesis_id=row.get("thesis_id"),
            recommended_action=str(row.get("recommended_action") or "pass"),  # type: ignore[arg-type]
            recommended_size_pct=row.get("recommended_size_pct"),
            executed_action=row.get("executed_action"),  # type: ignore[arg-type]
            executed_size_pct=row.get("executed_size_pct"),
            signal_strength=row.get("signal_strength"),
            portfolio_exposure_pct_at_decision=row.get("portfolio_exposure_pct_at_decision"),
            catalyst_bucket_exposure_pct=row.get("catalyst_bucket_exposure_pct"),
            indication_bucket_exposure_pct=row.get("indication_bucket_exposure_pct"),
            liquidity_bucket=row.get("liquidity_bucket"),  # type: ignore[arg-type]
            conviction_tier=row.get("conviction_tier"),  # type: ignore[arg-type]
            critic_flags_count=int(row.get("critic_flags_count") or 0),
            reasoning_text=str(row.get("reasoning_text") or ""),
            decided_at=decided_at,
        )

    @staticmethod
    def _row_to_snapshot(row: dict) -> PositionSnapshot:
        created_at_str = row.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(str(created_at_str))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc)

        entry_date_str = row.get("entry_date", "")
        try:
            entry_date = date.fromisoformat(str(entry_date_str))
        except (ValueError, TypeError):
            entry_date = date.today()

        exit_date_val = row.get("exit_date")
        exit_date: Optional[date] = None
        if exit_date_val:
            try:
                exit_date = date.fromisoformat(str(exit_date_val))
            except (ValueError, TypeError):
                pass

        return PositionSnapshot(
            snapshot_id=str(row["snapshot_id"]),
            asset_id=str(row["asset_id"]),
            decision_id=row.get("decision_id"),
            entry_date=entry_date,
            entry_price_usd=row.get("entry_price_usd"),
            current_size_pct=float(row.get("current_size_pct") or 0.0),
            linked_catalyst_id=row.get("linked_catalyst_id"),
            thesis_strength_at_entry=row.get("thesis_strength_at_entry"),
            is_active=bool(int(row.get("is_active", 1))),
            exit_date=exit_date,
            exit_price_usd=row.get("exit_price_usd"),
            exit_reason=row.get("exit_reason"),  # type: ignore[arg-type]
            holding_period_days=row.get("holding_period_days"),
            created_at=created_at,
        )

    @staticmethod
    def _row_to_attribution(row: dict) -> OutcomeAttribution:
        resolved_at_str = row.get("resolved_at", "")
        try:
            resolved_at = datetime.fromisoformat(str(resolved_at_str))
            if resolved_at.tzinfo is None:
                resolved_at = resolved_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            resolved_at = datetime.now(timezone.utc)

        return OutcomeAttribution(
            attribution_id=str(row["attribution_id"]),
            decision_id=str(row["decision_id"]),
            asset_id=str(row["asset_id"]),
            return_pct=float(row.get("return_pct") or 0.0),
            attribution_type=str(row.get("attribution_type") or "unclassified"),  # type: ignore[arg-type]
            resolved_at=resolved_at,
            notes=str(row.get("notes") or ""),
        )

"""
Wave L — Weekly Review Engine.

Structures the weekly learning loop into four distinct accuracy dimensions.
Separating dimensions prevents conflation of different failure modes.

Design principles
-----------------
- Four independent sections, each measuring a different axis of accuracy.
- ``confirmed_thesis`` requires thesis claim evidence — not just "return > 0".
  A positive return caused by market drift does NOT confirm the thesis.
- Each section degrades gracefully when data is missing or sparse.
- Reports are stored in SQLite for longitudinal analysis (trend over weeks).
- No LLM calls. All classification is deterministic from structured data.

The four dimensions
-------------------
1. Fundamental accuracy
   Were our directional predictions correct on the clinical/regulatory event?
   Sources: ``forecast_records`` (resolved in lookback window).
   Error types: pos_error, timing_error, market_drift, unclassified.

2. Market timing accuracy
   How stale were our signals when forecasts were recorded?
   Sources: ``forecast_records.signal_date`` vs ``forecast_records.predicted_at``.

3. Thesis accuracy
   Were key thesis claims confirmed or refuted this week?
   Sources: ``thesis_claims`` (status changed within lookback window).
   Key claim types: ENDPOINT_MET, REGULATORY_PATHWAY, COMPETITOR_FAILURE.

4. Sizing quality
   How much did execution diverge from recommended sizing?
   Sources: ``decision_records`` (executed_action vs recommended_action).
   Only populated when DecisionLayer is provided.

Strict confirmed_thesis rule
-----------------------------
A forecast is ``confirmed_thesis`` only when ALL of:
  1. ``outcome_correct = 1`` OR ``actual_market_return_t30 > 0``
  2. AND at least one of:
     - A key thesis claim (ENDPOINT_MET, POS_ABOVE_THRESHOLD, REGULATORY_PATHWAY)
       was confirmed for this asset in the lookback window
     - OR event_type = trial_readout and predicted_direction aligns with resolution
  3. AND no ENDPOINT_MET or REGULATORY_PATHWAY claim was refuted in the same window

If rule 2 or 3 fails despite positive return → classified as ``market_drift``.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bve.intelligence.decision_layer import DecisionLayer
    from bve.intelligence.thesis_tracker import ThesisTracker


# ---------------------------------------------------------------------------
# Key claim types for thesis accuracy
# ---------------------------------------------------------------------------

_KEY_CLAIM_TYPES: frozenset[str] = frozenset({
    "endpoint_met",
    "regulatory_pathway",
    "competitor_failure",
})


# ---------------------------------------------------------------------------
# Section models
# ---------------------------------------------------------------------------

class FundamentalAccuracy(BaseModel):
    """Directional accuracy of clinical/regulatory predictions."""

    n_resolved: int = 0
    n_correct: int = 0
    hit_rate: Optional[float] = None          # n_correct / n_resolved
    n_pos_error: int = 0                      # predicted wrong direction on trial event
    n_timing_error: int = 0                   # correct direction, signal was stale
    n_market_drift: int = 0                   # positive return but thesis not confirmed
    n_confirmed_thesis: int = 0              # strict confirmed_thesis
    n_unclassified: int = 0


class MarketTimingAccuracy(BaseModel):
    """How fresh were the signals underlying our forecasts?"""

    n_forecasts_checked: int = 0
    n_stale_signals: int = 0                  # signal_date > stale_threshold days before predicted_at
    pct_stale: Optional[float] = None
    avg_signal_age_days: Optional[float] = None
    stale_threshold_days: int = 30


class ThesisAccuracy(BaseModel):
    """Key thesis claim confirmation vs refutation this week."""

    n_key_claims_confirmed: int = 0
    n_key_claims_refuted: int = 0
    n_all_claims_confirmed: int = 0
    n_all_claims_refuted: int = 0
    n_assets_with_refuted_key_claim: int = 0  # assets where ENDPOINT_MET / REGULATORY_PATHWAY refuted
    net_thesis_score: Optional[float] = None  # (confirmed - refuted) / total_key_resolved


class SizingQuality(BaseModel):
    """Divergence between recommended and executed position sizes."""

    n_decisions_checked: int = 0
    n_with_execution: int = 0                 # decisions where executed_action was recorded
    n_recommended_vs_executed_diverged: int = 0
    pct_diverged: Optional[float] = None
    avg_size_divergence_pct: Optional[float] = None   # mean |executed_pct - recommended_pct| in pp
    n_oversized: int = 0                      # executed_size > recommended_size + 2pp


class PolicyAudit(BaseModel):
    """Coverage and action mix for persisted Step 5 policy snapshots."""

    n_policy_snapshots: int = 0
    n_buy: int = 0
    n_add: int = 0
    n_monitor: int = 0
    n_avoid: int = 0
    avg_sizing_pct: Optional[float] = None
    n_blocked_by_company_gate: int = 0


# ---------------------------------------------------------------------------
# WeeklyReviewReport
# ---------------------------------------------------------------------------

class WeeklyReviewReport(BaseModel):
    """
    Structured weekly review across four accuracy dimensions.

    Each section is independent.  Missing data returns zero counts, not errors.

    Attributes
    ----------
    week_ending:
        End date of the review window (inclusive).
    fundamental:
        Directional prediction accuracy.
    market_timing:
        Signal freshness analysis.
    thesis:
        Thesis claim confirmation / refutation.
    sizing:
        Execution vs recommendation divergence.
    top_miss:
        asset_id with largest negative market return in the period (if any).
    top_win:
        asset_id with largest positive market return in the period (if any).
    calibration_drift_fired:
        Whether PoS drift alerts fired in the lookback window.
    generated_at:
        UTC timestamp.
    """

    review_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    week_ending: date = Field(default_factory=date.today)
    lookback_days: int = 7
    fundamental: FundamentalAccuracy = Field(default_factory=FundamentalAccuracy)
    market_timing: MarketTimingAccuracy = Field(default_factory=MarketTimingAccuracy)
    thesis: ThesisAccuracy = Field(default_factory=ThesisAccuracy)
    sizing: SizingQuality = Field(default_factory=SizingQuality)
    policy_audit: PolicyAudit = Field(default_factory=PolicyAudit)
    top_miss: Optional[str] = None
    top_win: Optional[str] = None
    calibration_drift_fired: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# WeeklyReviewEngine
# ---------------------------------------------------------------------------

class WeeklyReviewEngine:
    """
    Generates a :class:`WeeklyReviewReport` from KnowledgeStore data.

    Parameters
    ----------
    store:
        A ``KnowledgeStore`` instance.
    decision_layer:
        Optional ``DecisionLayer`` — required for ``SizingQuality`` section.
    thesis_tracker:
        Optional ``ThesisTracker`` — required for ``ThesisAccuracy`` section.
    stale_signal_threshold_days:
        Signals older than this at forecast time are considered stale.
    """

    def __init__(
        self,
        store: Any,
        *,
        decision_layer: Optional["DecisionLayer"] = None,
        thesis_tracker: Optional["ThesisTracker"] = None,
        stale_signal_threshold_days: int = 30,
    ) -> None:
        self.store = store
        self.decision_layer = decision_layer
        self.thesis_tracker = thesis_tracker
        self.stale_threshold_days = stale_signal_threshold_days
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self.store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_review_records (
                review_id    TEXT PRIMARY KEY,
                week_ending  TEXT NOT NULL UNIQUE,
                report_json  TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
            """
        )
        self.store._conn.commit()

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def run_review(
        self,
        *,
        week_ending: Optional[date] = None,
        lookback_days: int = 7,
    ) -> WeeklyReviewReport:
        """
        Generate a ``WeeklyReviewReport`` for the lookback window.

        Parameters
        ----------
        week_ending:
            End of review window (inclusive).  Defaults to today.
        lookback_days:
            Number of days to look back from ``week_ending``.

        Returns
        -------
        WeeklyReviewReport
        """
        end = week_ending or date.today()
        start = end - timedelta(days=lookback_days)

        fundamental = self._compute_fundamental(start, end)
        market_timing = self._compute_market_timing(start, end)
        thesis = self._compute_thesis_accuracy(start, end)
        sizing = self._compute_sizing_quality()
        policy_audit = self._compute_policy_audit(start, end)
        top_miss, top_win = self._compute_top_miss_win(start, end)
        drift = self._check_calibration_drift(start, end)

        report = WeeklyReviewReport(
            week_ending=end,
            lookback_days=lookback_days,
            fundamental=fundamental,
            market_timing=market_timing,
            thesis=thesis,
            sizing=sizing,
            policy_audit=policy_audit,
            top_miss=top_miss,
            top_win=top_win,
            calibration_drift_fired=drift,
        )
        self._store_report(report)
        return report

    def get_stored_report(self, week_ending: date) -> Optional[WeeklyReviewReport]:
        """Retrieve a previously stored report by week_ending date."""
        row = self.store._conn.execute(
            "SELECT report_json FROM weekly_review_records WHERE week_ending = ?",
            (week_ending.isoformat(),),
        ).fetchone()
        if row is None:
            return None
        data = json.loads(row["report_json"])
        return WeeklyReviewReport.model_validate(data)

    # ------------------------------------------------------------------
    # Section: Fundamental accuracy
    # ------------------------------------------------------------------

    def _compute_fundamental(self, start: date, end: date) -> FundamentalAccuracy:
        """Classify resolved forecasts in the window."""
        try:
            rows = self.store._conn.execute(
                """
                SELECT * FROM forecast_records
                 WHERE resolved = 1
                   AND date(predicted_at) BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return FundamentalAccuracy()

        n_resolved = len(rows)
        if n_resolved == 0:
            return FundamentalAccuracy(n_resolved=0)

        n_correct = 0
        n_pos_error = 0
        n_timing = 0
        n_market_drift = 0
        n_confirmed = 0
        n_unclassified = 0

        for row in rows:
            row_dict = dict(row)
            asset_id = str(row_dict.get("asset_id") or "")
            outcome_correct = int(row_dict.get("outcome_correct") or 0)
            actual_return = float(row_dict.get("actual_market_return_t30") or 0.0)
            event_type = str(row_dict.get("event_type") or "")
            signal_date_str = str(row_dict.get("signal_date") or "")
            predicted_at_str = str(row_dict.get("predicted_at") or "")

            if outcome_correct:
                n_correct += 1

            # Signal age at forecast time
            stale = self._is_stale_signal(signal_date_str, predicted_at_str)

            # Strict confirmed_thesis check
            is_confirmed = self._is_confirmed_thesis(
                asset_id, event_type, outcome_correct, actual_return, start, end
            )

            if outcome_correct and is_confirmed:
                n_confirmed += 1
            elif not outcome_correct and "trial_readout" in event_type:
                n_pos_error += 1
            elif outcome_correct and stale:
                n_timing += 1
            elif outcome_correct and not is_confirmed:
                # Return positive but thesis not confirmed → market drift
                n_market_drift += 1
            else:
                n_unclassified += 1

        hit_rate = round(n_correct / n_resolved, 4) if n_resolved > 0 else None
        return FundamentalAccuracy(
            n_resolved=n_resolved,
            n_correct=n_correct,
            hit_rate=hit_rate,
            n_pos_error=n_pos_error,
            n_timing_error=n_timing,
            n_market_drift=n_market_drift,
            n_confirmed_thesis=n_confirmed,
            n_unclassified=n_unclassified,
        )

    def _is_stale_signal(self, signal_date_str: str, predicted_at_str: str) -> bool:
        """Return True when signal was older than stale_threshold at forecast time."""
        try:
            sig_date = date.fromisoformat(signal_date_str[:10])
        except (ValueError, TypeError):
            return False
        try:
            pred_date = datetime.fromisoformat(predicted_at_str).date()
        except (ValueError, TypeError):
            return False
        return (pred_date - sig_date).days > self.stale_threshold_days

    def _is_confirmed_thesis(
        self,
        asset_id: str,
        event_type: str,
        outcome_correct: int,
        actual_return: float,
        start: date,
        end: date,
    ) -> bool:
        """
        Strict confirmed_thesis rule.

        Requires:
          1. Positive outcome (outcome_correct=1 OR actual_return > 0)
          2. Key thesis claim confirmed OR event_type aligns with trial_readout resolution
          3. No key claim refuted in the window
        """
        # Rule 1
        positive_outcome = outcome_correct == 1 or actual_return > 0
        if not positive_outcome:
            return False

        # Rules 2 + 3 require ThesisTracker
        if self.thesis_tracker is None:
            # Without thesis tracker, fall back to outcome_correct only
            # (cannot verify claim evidence)
            return False

        confirmed_key_claims, refuted_key_claims = self._get_claim_changes(
            asset_id, start, end
        )

        # Rule 3: any key claim refuted → not confirmed_thesis
        if refuted_key_claims > 0:
            return False

        # Rule 2: at least one key claim confirmed (thesis evidence required)
        return confirmed_key_claims > 0

    def _get_claim_changes(
        self, asset_id: str, start: date, end: date
    ) -> tuple[int, int]:
        """Return (n_confirmed_key, n_refuted_key) for asset in window."""
        if self.thesis_tracker is None:
            return 0, 0
        try:
            rows = self.store._conn.execute(
                """
                SELECT claim_type, status FROM thesis_claims
                 WHERE asset_id = ?
                   AND status IN ('confirmed', 'refuted')
                   AND date(resolved_at) BETWEEN ? AND ?
                """,
                (asset_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return 0, 0

        confirmed = sum(
            1 for r in rows
            if str(dict(r).get("status")) == "confirmed"
            and str(dict(r).get("claim_type")) in _KEY_CLAIM_TYPES
        )
        refuted = sum(
            1 for r in rows
            if str(dict(r).get("status")) == "refuted"
            and str(dict(r).get("claim_type")) in _KEY_CLAIM_TYPES
        )
        return confirmed, refuted

    # ------------------------------------------------------------------
    # Section: Market timing accuracy
    # ------------------------------------------------------------------

    def _compute_market_timing(self, start: date, end: date) -> MarketTimingAccuracy:
        """Measure signal freshness for forecasts in the window."""
        try:
            rows = self.store._conn.execute(
                """
                SELECT signal_date, predicted_at FROM forecast_records
                 WHERE date(predicted_at) BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return MarketTimingAccuracy(stale_threshold_days=self.stale_threshold_days)

        n_total = len(rows)
        if n_total == 0:
            return MarketTimingAccuracy(
                n_forecasts_checked=0,
                stale_threshold_days=self.stale_threshold_days,
            )

        ages: list[int] = []
        n_stale = 0
        for row in rows:
            r = dict(row)
            signal_date_str = str(r.get("signal_date") or "")
            predicted_at_str = str(r.get("predicted_at") or "")
            try:
                sig_date = date.fromisoformat(signal_date_str[:10])
                pred_date = datetime.fromisoformat(predicted_at_str).date()
                age = (pred_date - sig_date).days
                ages.append(age)
                if age > self.stale_threshold_days:
                    n_stale += 1
            except (ValueError, TypeError):
                continue

        avg_age = round(sum(ages) / len(ages), 1) if ages else None
        pct_stale = round(n_stale / n_total, 4) if n_total > 0 else None

        return MarketTimingAccuracy(
            n_forecasts_checked=n_total,
            n_stale_signals=n_stale,
            pct_stale=pct_stale,
            avg_signal_age_days=avg_age,
            stale_threshold_days=self.stale_threshold_days,
        )

    # ------------------------------------------------------------------
    # Section: Thesis accuracy
    # ------------------------------------------------------------------

    def _compute_thesis_accuracy(self, start: date, end: date) -> ThesisAccuracy:
        """Count key thesis claim confirmations and refutations in the window."""
        if self.thesis_tracker is None:
            return ThesisAccuracy()

        try:
            rows = self.store._conn.execute(
                """
                SELECT asset_id, claim_type, status FROM thesis_claims
                 WHERE status IN ('confirmed', 'refuted')
                   AND date(resolved_at) BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return ThesisAccuracy()

        n_key_confirmed = 0
        n_key_refuted = 0
        n_all_confirmed = 0
        n_all_refuted = 0
        assets_with_refuted_key: set[str] = set()

        for row in rows:
            r = dict(row)
            claim_type = str(r.get("claim_type") or "")
            status = str(r.get("status") or "")
            asset_id = str(r.get("asset_id") or "")

            if status == "confirmed":
                n_all_confirmed += 1
                if claim_type in _KEY_CLAIM_TYPES:
                    n_key_confirmed += 1
            elif status == "refuted":
                n_all_refuted += 1
                if claim_type in _KEY_CLAIM_TYPES:
                    n_key_refuted += 1
                    assets_with_refuted_key.add(asset_id)

        total_key = n_key_confirmed + n_key_refuted
        net = round((n_key_confirmed - n_key_refuted) / total_key, 4) if total_key > 0 else None

        return ThesisAccuracy(
            n_key_claims_confirmed=n_key_confirmed,
            n_key_claims_refuted=n_key_refuted,
            n_all_claims_confirmed=n_all_confirmed,
            n_all_claims_refuted=n_all_refuted,
            n_assets_with_refuted_key_claim=len(assets_with_refuted_key),
            net_thesis_score=net,
        )

    # ------------------------------------------------------------------
    # Section: Sizing quality
    # ------------------------------------------------------------------

    def _compute_sizing_quality(self) -> SizingQuality:
        """Measure divergence between recommended and executed sizes."""
        if self.decision_layer is None:
            return SizingQuality()

        drift = self.decision_layer.model_vs_execution_drift()
        n_total = drift.get("n_total", 0)
        n_with_exec = drift.get("n_with_execution", 0)
        n_diverged = drift.get("n_diverged", 0)
        pct = drift.get("pct_diverged")

        # Compute average size divergence
        avg_div: Optional[float] = None
        n_oversized = 0
        try:
            rows = self.store._conn.execute(
                """
                SELECT recommended_size_pct, executed_size_pct
                  FROM decision_records
                 WHERE executed_size_pct IS NOT NULL
                   AND recommended_size_pct IS NOT NULL
                """
            ).fetchall()
            if rows:
                diffs = [
                    abs(float(r["executed_size_pct"]) - float(r["recommended_size_pct"]))
                    for r in rows
                ]
                avg_div = round(sum(diffs) / len(diffs), 4) if diffs else None
                n_oversized = sum(
                    1 for r in rows
                    if float(r["executed_size_pct"]) > float(r["recommended_size_pct"]) + 0.02
                )
        except Exception:
            pass

        return SizingQuality(
            n_decisions_checked=n_total,
            n_with_execution=n_with_exec,
            n_recommended_vs_executed_diverged=n_diverged,
            pct_diverged=pct,
            avg_size_divergence_pct=avg_div,
            n_oversized=n_oversized,
        )

    # ------------------------------------------------------------------
    # Section: Policy audit
    # ------------------------------------------------------------------

    def _compute_policy_audit(self, start: date, end: date) -> PolicyAudit:
        """Summarize persisted Step 5 policy rows in the window."""
        try:
            rows = self.store._conn.execute(
                """
                SELECT action, sizing_pct, company_action_policy
                  FROM equity_policy_snapshots
                 WHERE as_of_date BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return PolicyAudit()

        n_rows = len(rows)
        if n_rows == 0:
            return PolicyAudit()

        actions = [str(row["action"] or "").lower() for row in rows]
        sizes = [
            float(row["sizing_pct"])
            for row in rows
            if row["sizing_pct"] is not None
        ]
        blocked = sum(
            1
            for row in rows
            if str(row["company_action_policy"] or "").lower()
            in {"avoid", "needs_manual_review"}
        )
        return PolicyAudit(
            n_policy_snapshots=n_rows,
            n_buy=sum(1 for action in actions if action == "buy"),
            n_add=sum(1 for action in actions if action == "add"),
            n_monitor=sum(1 for action in actions if action == "monitor"),
            n_avoid=sum(1 for action in actions if action == "avoid"),
            avg_sizing_pct=round(sum(sizes) / len(sizes), 4) if sizes else None,
            n_blocked_by_company_gate=blocked,
        )

    # ------------------------------------------------------------------
    # Top miss / win
    # ------------------------------------------------------------------

    def _compute_top_miss_win(
        self, start: date, end: date
    ) -> tuple[Optional[str], Optional[str]]:
        """Return (top_miss_asset_id, top_win_asset_id) by market return."""
        try:
            rows = self.store._conn.execute(
                """
                SELECT asset_id, actual_market_return_t30
                  FROM forecast_records
                 WHERE resolved = 1
                   AND actual_market_return_t30 IS NOT NULL
                   AND date(predicted_at) BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()
        except Exception:
            return None, None

        if not rows:
            return None, None

        by_asset: dict[str, float] = {}
        for row in rows:
            r = dict(row)
            aid = str(r.get("asset_id") or "")
            ret = float(r.get("actual_market_return_t30") or 0.0)
            if aid not in by_asset or ret < by_asset[aid]:  # keep worst per asset
                by_asset[aid] = ret

        top_miss = min(by_asset, key=lambda k: by_asset[k]) if by_asset else None
        top_win = max(by_asset, key=lambda k: by_asset[k]) if by_asset else None
        return top_miss, top_win

    # ------------------------------------------------------------------
    # Calibration drift check
    # ------------------------------------------------------------------

    def _check_calibration_drift(self, start: date, end: date) -> bool:
        """Return True if any PoS drift records exist in the window."""
        try:
            # Check if pos_calibration_reports table exists and has drift alerts
            row = self.store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='pos_calibration_reports'"
            ).fetchone()
            if row is None:
                return False
            result = self.store._conn.execute(
                """
                SELECT COUNT(*) as n FROM pos_calibration_reports
                 WHERE has_drift_alerts = 1
                   AND date(created_at) BETWEEN ? AND ?
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchone()
            return int(dict(result).get("n") or 0) > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _store_report(self, report: WeeklyReviewReport) -> None:
        """Persist report to weekly_review_records (upsert by week_ending)."""
        now = datetime.now(timezone.utc).isoformat()
        self.store._conn.execute(
            """
            INSERT OR REPLACE INTO weekly_review_records
                (review_id, week_ending, report_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                report.review_id,
                report.week_ending.isoformat(),
                report.model_dump_json(),
                now,
            ),
        )
        self.store._conn.commit()

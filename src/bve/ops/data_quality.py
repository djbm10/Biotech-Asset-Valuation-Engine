"""Data-quality monitoring for intelligence pipeline inputs and runtime health."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # pragma: no cover
    from bve.intelligence.knowledge_layer import KnowledgeStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DataQualityCheck(BaseModel):
    """One atomic data-quality check."""

    check_type: str
    asset_id: str
    value: float | int | str | None = None
    threshold: str
    passed: bool
    severity: str = "info"
    reason: str = "ok"
    details: str = ""


class DataQualityScore(BaseModel):
    """Aggregate quality score for one asset."""

    source: str = "knowledge_store"
    asset_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    checks: list[DataQualityCheck] = Field(default_factory=list)
    failing_checks: list[str] = Field(default_factory=list)
    gated: bool = False
    generated_at: datetime = Field(default_factory=_utcnow)


class DataQualityMonitor:
    """Runs deterministic quality checks against the knowledge store."""

    def __init__(self, store: "KnowledgeStore", gate_threshold: float = 0.50) -> None:
        self.store = store
        self.gate_threshold = gate_threshold

    def evaluate(self, asset_id: str) -> DataQualityScore:
        """Alias for compatibility with gate-style call sites."""
        return self.check_asset(asset_id)

    def check_all(self, asset_ids: list[str]) -> list[DataQualityScore]:
        return [self.check_asset(asset_id) for asset_id in asset_ids]

    def check_asset(self, asset_id: str) -> DataQualityScore:
        checks = [
            self._check_doc_freshness(asset_id),
            self._check_confidence_trend_30d(asset_id),
            self._check_clinical_metadata_completeness(asset_id),
            self._check_connector_error_rate(asset_id),
            self._check_market_data_freshness(asset_id),
            self._check_valuation_input_bounds(asset_id),
        ]
        passed = sum(1 for c in checks if c.passed)
        overall = passed / len(checks) if checks else 1.0
        failing = [c.check_type for c in checks if not c.passed]
        return DataQualityScore(
            asset_id=asset_id,
            overall_score=round(overall, 6),
            checks=checks,
            failing_checks=failing,
            gated=overall < self.gate_threshold,
        )

    @staticmethod
    def _severity_for_failure(check_type: str, value: float | int | str | None) -> str:
        if check_type == "connector_error_rate":
            rate = float(value or 0.0)
            return "critical" if rate >= 0.5 else "warning"
        if check_type == "market_data_freshness":
            if isinstance(value, (int, float)):
                return "critical" if float(value) > 7.0 else "warning"
            return "warning"
        if check_type == "valuation_input_bounds":
            return "critical"
        return "warning"

    def _check_doc_freshness(self, asset_id: str) -> DataQualityCheck:
        row = self.store._conn.execute(
            """
            SELECT MAX(created_at) AS latest_created_at
            FROM raw_documents
            WHERE json_extract(payload_json, '$.entity_hints.asset_id') = ?
            """,
            (asset_id,),
        ).fetchone()
        latest = row["latest_created_at"] if row is not None else None
        if latest is None:
            return DataQualityCheck(
                check_type="doc_freshness",
                asset_id=asset_id,
                value=None,
                threshold="<=3d",
                passed=True,
                severity="info",
                reason="no_source_documents",
                details="No raw documents available",
            )

        latest_dt = self.store._coerce_datetime(latest)
        age_days = (max(_utcnow(), latest_dt) - latest_dt).total_seconds() / 86400.0
        passed = age_days <= 3.0
        return DataQualityCheck(
            check_type="doc_freshness",
            asset_id=asset_id,
            value=round(age_days, 6),
            threshold="<=3d",
            passed=passed,
            severity="info" if passed else self._severity_for_failure("doc_freshness", age_days),
            reason="ok" if passed else "stale_source_documents",
            details=f"latest={latest_dt.isoformat()}",
        )

    def _check_confidence_trend_30d(self, asset_id: str) -> DataQualityCheck:
        cutoff = (_utcnow() - timedelta(days=30)).isoformat()
        row = self.store._conn.execute(
            """
            SELECT
                AVG(COALESCE(
                    CAST(json_extract(payload_json, '$.extraction_confidence') AS REAL),
                    0.0
                )) AS avg_confidence,
                COUNT(*) AS n_rows
            FROM structured_signals
            WHERE asset_id = ? AND created_at >= ?
            """,
            (asset_id, cutoff),
        ).fetchone()
        n_rows = int(row["n_rows"] or 0) if row is not None else 0
        if n_rows == 0:
            return DataQualityCheck(
                check_type="confidence_trend_30d",
                asset_id=asset_id,
                value=None,
                threshold=">=0.60",
                passed=True,
                severity="info",
                reason="no_recent_signals",
                details="No structured signals in last 30d",
            )

        avg_confidence = float(row["avg_confidence"] or 0.0)
        return DataQualityCheck(
            check_type="confidence_trend_30d",
            asset_id=asset_id,
            value=round(avg_confidence, 6),
            threshold=">=0.60",
            passed=avg_confidence >= 0.60,
            severity=(
                "info"
                if avg_confidence >= 0.60
                else self._severity_for_failure("confidence_trend_30d", avg_confidence)
            ),
            reason="ok" if avg_confidence >= 0.60 else "low_extraction_confidence_trend",
            details=f"n={n_rows}",
        )

    def _check_clinical_metadata_completeness(self, asset_id: str) -> DataQualityCheck:
        row = self.store._conn.execute(
            """
            SELECT
                SUM(
                    CASE
                        WHEN event_type IN ('trial_readout', 'interim_analysis', 'enrollment_update')
                        THEN 1 ELSE 0
                    END
                ) AS trial_like_rows,
                SUM(
                    CASE
                        WHEN event_type IN ('trial_readout', 'interim_analysis', 'enrollment_update')
                             AND (
                                 json_extract(payload_json, '$.trial_phase') IS NULL
                                 OR json_extract(payload_json, '$.primary_endpoint_met') IS NULL
                             )
                        THEN 1
                        ELSE 0
                    END
                ) AS null_rows
            FROM structured_signals
            WHERE asset_id = ?
            """,
            (asset_id,),
        ).fetchone()
        total_rows = int(row["trial_like_rows"] or 0) if row is not None else 0
        null_rows = int(row["null_rows"] or 0) if row is not None else 0
        if total_rows == 0:
            return DataQualityCheck(
                check_type="clinical_metadata_completeness",
                asset_id=asset_id,
                value=0.0,
                threshold="<=0.10",
                passed=True,
                severity="info",
                reason="no_trial_like_signals",
                details="No trial-like structured signals available",
            )

        rate = null_rows / total_rows
        return DataQualityCheck(
            check_type="clinical_metadata_completeness",
            asset_id=asset_id,
            value=round(rate, 6),
            threshold="<=0.10",
            passed=rate <= 0.10,
            severity=(
                "info"
                if rate <= 0.10
                else self._severity_for_failure("clinical_metadata_completeness", rate)
            ),
            reason="ok" if rate <= 0.10 else "missing_clinical_trial_metadata",
            details=f"null_rows={null_rows} trial_like_rows={total_rows}",
        )

    def _check_connector_error_rate(self, asset_id: str) -> DataQualityCheck:
        rows = self.store._conn.execute(
            """
            SELECT status
            FROM run_state
            WHERE asset_id = ? AND stage LIKE 'fetch:%'
            ORDER BY started_at DESC
            LIMIT 20
            """,
            (asset_id,),
        ).fetchall()
        total = len(rows)
        if total == 0:
            return DataQualityCheck(
                check_type="connector_error_rate",
                asset_id=asset_id,
                value=0.0,
                threshold="<=0.05",
                passed=True,
                severity="info",
                reason="no_connector_runs",
                details="No connector runs available",
            )

        failures = sum(1 for row in rows if str(row["status"]) == "failure")
        rate = failures / total
        return DataQualityCheck(
            check_type="connector_error_rate",
            asset_id=asset_id,
            value=round(rate, 6),
            threshold="<=0.05",
            passed=rate <= 0.05,
            severity="info"
            if rate <= 0.05
            else self._severity_for_failure("connector_error_rate", rate),
            reason="ok" if rate <= 0.05 else "connector_failure_rate_high",
            details=f"failures={failures} total={total}",
        )

    def _check_market_data_freshness(self, asset_id: str) -> DataQualityCheck:
        ticker_row = self.store._conn.execute(
            """
            SELECT ticker
            FROM asset_registry
            WHERE asset_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        ticker = str(ticker_row["ticker"] or "").upper() if ticker_row is not None else ""
        if not ticker:
            return DataQualityCheck(
                check_type="market_data_freshness",
                asset_id=asset_id,
                value=None,
                threshold="<=3d",
                passed=True,
                severity="info",
                reason="no_ticker_mapping_available",
                details="No ticker mapping found in asset_registry",
            )

        row = self.store._conn.execute(
            """
            SELECT
                MAX(price_date) AS latest_price_date
            FROM market_prices
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()
        latest_date_text = row["latest_price_date"] if row is not None else None
        if latest_date_text is None:
            # Ticker is registered but market prices have not been fetched yet.
            # This is expected for new assets or a freshly initialised pipeline.
            # Treat as a soft warning so the asset is not permanently gated
            # before the market-price connector has had a chance to run.
            return DataQualityCheck(
                check_type="market_data_freshness",
                asset_id=asset_id,
                value=None,
                threshold="<=3d",
                passed=True,
                severity="warning",
                reason="no_market_price_data_yet",
                details=f"ticker={ticker}",
            )

        latest_date = date.fromisoformat(str(latest_date_text))
        age_days = (date.today() - latest_date).days
        passed = age_days <= 3
        return DataQualityCheck(
            check_type="market_data_freshness",
            asset_id=asset_id,
            value=age_days,
            threshold="<=3d",
            passed=passed,
            severity="info"
            if passed
            else self._severity_for_failure("market_data_freshness", age_days),
            reason="ok" if passed else "stale_market_data",
            details=f"ticker={ticker} latest_price_date={latest_date.isoformat()}",
        )

    def _check_valuation_input_bounds(self, asset_id: str) -> DataQualityCheck:
        diffs = self.store.get_valuation_diffs(asset_id=asset_id, limit=1)
        if not diffs:
            return DataQualityCheck(
                check_type="valuation_input_bounds",
                asset_id=asset_id,
                value=None,
                threshold="bounded",
                passed=True,
                severity="info",
                reason="no_valuation_diff_data",
                details="No valuation diffs available",
            )

        latest = diffs[0]
        after = latest.valuation_after or {}
        issues: list[str] = []
        rnpv = after.get("rnpv_millions")
        nav_per_share = after.get("nav_per_share")
        approval_prob = after.get("approval_probability")

        try:
            if rnpv is not None and not (0.0 <= float(rnpv) <= 1_000_000.0):
                issues.append(f"rnpv_out_of_bounds:{rnpv}")
        except Exception:
            issues.append(f"rnpv_invalid:{rnpv}")

        try:
            if nav_per_share is not None and not (0.0 <= float(nav_per_share) <= 10_000.0):
                issues.append(f"nav_per_share_out_of_bounds:{nav_per_share}")
        except Exception:
            issues.append(f"nav_per_share_invalid:{nav_per_share}")

        try:
            if approval_prob is not None and not (0.0 <= float(approval_prob) <= 1.0):
                issues.append(f"approval_probability_out_of_bounds:{approval_prob}")
        except Exception:
            if approval_prob is not None:
                issues.append(f"approval_probability_invalid:{approval_prob}")

        passed = len(issues) == 0
        return DataQualityCheck(
            check_type="valuation_input_bounds",
            asset_id=asset_id,
            value=0 if passed else len(issues),
            threshold="bounded",
            passed=passed,
            severity="info"
            if passed
            else self._severity_for_failure("valuation_input_bounds", len(issues)),
            reason="ok" if passed else "valuation_inputs_out_of_bounds",
            details="; ".join(issues) if issues else "latest valuation diff is within bounds",
        )


def score_rows_to_json(scores: list[DataQualityScore]) -> list[dict[str, Any]]:
    """Small helper for CLI/reporting output."""
    return [score.model_dump(mode="json") for score in scores]

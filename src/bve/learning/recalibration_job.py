"""Produce calibration candidates from outcome records and summarise bias."""

from __future__ import annotations

import uuid

from bve.learning.bias_report import BiasReport, BiasReportEngine
from bve.learning.calibration import CalibrationEngine, CalibrationRecord, CalibrationSummary
from bve.persistence.gap_fill_store import OutcomeRecord

_MODULE_MAP: dict[str, str] = {
    "pos_error": "pos",
    "timing_error": "timeline",
    "thesis_error": "peak_sales",
    "market_drift": "peak_sales",
}
_DEFAULT_MODULE = "pos"
_ALL_MODULES = {"pos", "peak_sales", "timeline", "financing", "competition", "access"}


class RecalibrationJob:
    """
    Accept resolved outcomes, feed them into CalibrationEngine, produce
    calibration summaries and bias report.
    """

    def __init__(self) -> None:
        self._cal_engine = CalibrationEngine()
        self._bias_engine = BiasReportEngine()

    def ingest_outcomes(self, outcomes: list[OutcomeRecord]) -> None:
        """
        For each outcome, create a CalibrationRecord for the relevant module
        and resolve it.

        Module mapping:
        - attribution == "pos_error"    → module = "pos"
        - attribution == "timing_error" → module = "timeline"
        - attribution in {"thesis_error", "market_drift"} → module = "peak_sales"
        - default → module = "pos"

        predicted_value = 0.5 (default; outcome does not carry composite_score)
        realized_value  = 1.0 if return > 0 else 0.0
        """
        for outcome in outcomes:
            module = _MODULE_MAP.get(outcome.attribution, _DEFAULT_MODULE)
            predicted_value = 0.5
            realized_value = 1.0 if outcome.return_realized_pct > 0 else 0.0

            record = CalibrationRecord(
                record_id=str(uuid.uuid4()),
                asset_id=outcome.asset_id,
                module=module,
                prediction_date=outcome.decision_date,
                outcome_date=outcome.outcome_date,
                predicted_value=predicted_value,
                is_resolved=False,
            )
            self._cal_engine.add_record(record)
            self._cal_engine.resolve_record(record.record_id, realized_value)

    def summarize(self) -> list[CalibrationSummary]:
        """Return summaries for all modules that have resolved records."""
        summaries: list[CalibrationSummary] = []
        for module in _ALL_MODULES:
            summary = self._cal_engine.summarize(module)
            if summary.n_resolved > 0:
                summaries.append(summary)
        return summaries

    def generate_bias_report(self) -> BiasReport:
        summaries = self.summarize()
        return self._bias_engine.generate(summaries)

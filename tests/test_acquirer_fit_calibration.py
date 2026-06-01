"""Tests for Block 5C: acquirer-fit calibration report."""
from __future__ import annotations

import pytest

from bve.intelligence.acquirer_fit_calibration import (
    CalibrationReport,
    WeightSuggestion,
    build_calibration_report,
)
from bve.intelligence.acquirer_fit_log import (
    log_fit_predictions,
    resolve_fit_prediction,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeRow:
    def __init__(self, asset_id: str, rank: int, fit_score: float,
                 ticker: str | None = None, therapeutic_area: str | None = None,
                 stage: str | None = None):
        self.asset_id = asset_id
        self.rank = rank
        self.fit_score = fit_score
        self.ticker = ticker
        self.therapeutic_area = therapeutic_area
        self.stage = stage


@pytest.fixture
def store(tmp_path):
    return str(tmp_path / "calibration_test.sqlite")


def _seed_scenario(
    store: str,
    *,
    deal_rank: int,
    ta: str = "oncology",
    stage: str = "phase_3",
    screen_date: str = "2026-01-15",
    n_non_deal: int = 3,
) -> None:
    """Insert one deal asset at deal_rank plus n_non_deal non-deals."""
    rows: list[_FakeRow] = []
    # Insert deal at the specified rank
    for r in range(1, n_non_deal + 2):
        is_deal = r == deal_rank
        rows.append(_FakeRow(
            asset_id=f"asset_rank{r}",
            rank=r,
            fit_score=round(1.0 - r * 0.1, 2),
            therapeutic_area=ta,
            stage=stage,
        ))
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date=screen_date, rows=rows)
    for i, (rid, row) in enumerate(zip(ids, rows)):
        outcome = "acquisition" if row.rank == deal_rank else "none"
        resolve_fit_prediction(store, record_id=rid,
                               outcome=outcome, outcome_date="2026-07-01")


# ── Empty store ───────────────────────────────────────────────────────────────

def test_empty_store_returns_no_predictions_report(store) -> None:
    report = build_calibration_report(store)
    assert report.n_resolved == 0
    assert "No resolved predictions" in report.summary_text


# ── Report structure ──────────────────────────────────────────────────────────

def test_report_structure(store) -> None:
    _seed_scenario(store, deal_rank=1)
    report = build_calibration_report(store)
    assert isinstance(report, CalibrationReport)
    assert report.n_resolved >= 1
    assert isinstance(report.precision_at_1, float)
    assert isinstance(report.precision_at_3, float)
    assert isinstance(report.mean_reciprocal_rank, float)
    assert isinstance(report.weight_suggestions, list)
    assert isinstance(report.ta_error_rates, dict)
    assert isinstance(report.stage_error_rates, dict)
    assert isinstance(report.summary_text, str)


def test_weight_suggestion_structure(store) -> None:
    # Seed a scenario where oncology deals are systematically misranked
    for i, date in enumerate(["2026-01-15", "2026-02-01", "2026-03-01"]):
        _seed_scenario(store, deal_rank=4, ta="oncology", screen_date=date)
    report = build_calibration_report(store)
    for s in report.weight_suggestions:
        assert isinstance(s, WeightSuggestion)
        assert s.dimension in {
            "therapeutic_area", "modality", "stage",
            "strategic_priority", "valuation", "budget",
        }
        assert s.current_weight > 0
        assert s.suggested_weight >= 0.05
        assert s.suggested_weight <= 0.45


# ── Perfect precision → no suggestions ───────────────────────────────────────

def test_good_model_no_weight_suggestions(store) -> None:
    """When rank-1 always wins, no weight adjustments should be suggested."""
    for date in ["2026-01-15", "2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01"]:
        _seed_scenario(store, deal_rank=1, screen_date=date)
    report = build_calibration_report(store)
    assert report.precision_at_1 == 1.0
    # With perfect P@1, no weight changes should be needed
    assert len(report.weight_suggestions) == 0


# ── TA error detection ────────────────────────────────────────────────────────

def test_ta_error_rates_populated(store) -> None:
    """When oncology deals are misranked, ta_error_rates should flag oncology."""
    for date in ["2026-01-15", "2026-02-01"]:
        _seed_scenario(store, deal_rank=4, ta="oncology", screen_date=date)
    report = build_calibration_report(store)
    assert "oncology" in report.ta_error_rates
    assert report.ta_error_rates["oncology"] > 0.0


def test_ta_underweighted_flagged(store) -> None:
    """Consistent TA misranking should appear in underweighted_dimensions."""
    for date in ["2026-01-15", "2026-02-01", "2026-03-01"]:
        _seed_scenario(store, deal_rank=4, ta="oncology", screen_date=date)
    report = build_calibration_report(store)
    assert "therapeutic_area" in report.underweighted_dimensions


# ── Stage error detection ─────────────────────────────────────────────────────

def test_stage_error_rates_populated(store) -> None:
    for date in ["2026-01-15", "2026-02-01"]:
        _seed_scenario(store, deal_rank=4, stage="phase_3", screen_date=date)
    report = build_calibration_report(store)
    assert "phase_3" in report.stage_error_rates


# ── Weight constraints ────────────────────────────────────────────────────────

def test_suggested_weights_sum_to_1(store) -> None:
    _seed_scenario(store, deal_rank=4, ta="oncology")
    current = {
        "therapeutic_area": 0.25,
        "modality": 0.20,
        "stage": 0.15,
        "strategic_priority": 0.15,
        "valuation": 0.10,
        "budget": 0.15,
    }
    report = build_calibration_report(store, current_weights=current)
    # Build the final weights from suggestions
    final = dict(current)
    for s in report.weight_suggestions:
        final[s.dimension] = s.suggested_weight
    total = sum(final.values())
    assert abs(total - 1.0) < 0.02, f"Weights sum to {total:.4f}, expected ~1.0"


def test_suggested_weights_within_bounds(store) -> None:
    for date in ["2026-01-15", "2026-02-01", "2026-03-01"]:
        _seed_scenario(store, deal_rank=5, ta="rare_disease", screen_date=date)
    report = build_calibration_report(store)
    for s in report.weight_suggestions:
        assert 0.05 <= s.suggested_weight <= 0.45


# ── Summary text ──────────────────────────────────────────────────────────────

def test_summary_text_contains_metrics(store) -> None:
    _seed_scenario(store, deal_rank=1)
    report = build_calibration_report(store)
    assert "P@1" in report.summary_text
    assert "P@3" in report.summary_text
    assert "MRR" in report.summary_text


def test_summary_text_advisory_note(store) -> None:
    _seed_scenario(store, deal_rank=1)
    report = build_calibration_report(store)
    assert "advisory" in report.summary_text.lower()


# ── acquirer_id filter ────────────────────────────────────────────────────────

def test_calibration_report_respects_acquirer_filter(store) -> None:
    _seed_scenario(store, deal_rank=1, ta="oncology")
    # Also add pfizer data
    rows = [_FakeRow("pf_asset", rank=1, fit_score=0.9, therapeutic_area="immunology")]
    ids = log_fit_predictions(store, acquirer_id="pfizer",
                              screen_date="2026-01-15", rows=rows)
    resolve_fit_prediction(store, record_id=ids[0],
                           outcome="acquisition", outcome_date="2026-06-01")

    vx_report = build_calibration_report(store, acquirer_id="vertex")
    pf_report = build_calibration_report(store, acquirer_id="pfizer")
    # Vertex has oncology; pfizer has immunology — TA breakdown should differ
    if vx_report.ta_error_rates:
        assert "immunology" not in vx_report.ta_error_rates or \
               vx_report.n_resolved != pf_report.n_resolved

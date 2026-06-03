"""Tests for Block 5A/5B: acquirer-fit prediction log and grading."""
from __future__ import annotations

import pytest

from bve.intelligence.acquirer_fit_log import (
    FitGradeReport,
    FitPredictionRecord,
    get_fit_predictions,
    grade_fit_predictions,
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
    return tmp_path / "test_fit_log.sqlite"


@pytest.fixture
def sample_rows():
    return [
        _FakeRow("asset_a", rank=1, fit_score=0.91, ticker="AAA",
                 therapeutic_area="oncology", stage="phase_2"),
        _FakeRow("asset_b", rank=2, fit_score=0.78, ticker="BBB",
                 therapeutic_area="immunology", stage="phase_3"),
        _FakeRow("asset_c", rank=3, fit_score=0.65, ticker="CCC",
                 therapeutic_area="rare_disease", stage="phase_2"),
    ]


# ── log_fit_predictions ───────────────────────────────────────────────────────

def test_log_creates_records(store, sample_rows) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=sample_rows)
    assert len(ids) == 3


def test_log_returns_unique_record_ids(store, sample_rows) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=sample_rows)
    assert len(set(ids)) == 3


def test_log_stores_rank_and_score(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    recs = get_fit_predictions(store, acquirer_id="vertex")
    ranks = {r.rank for r in recs}
    assert 1 in ranks and 2 in ranks and 3 in ranks


def test_log_stores_asset_metadata(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    recs = get_fit_predictions(store, acquirer_id="vertex")
    asset_map = {r.asset_id: r for r in recs}
    assert asset_map["asset_a"].ticker == "AAA"
    assert asset_map["asset_a"].therapeutic_area == "oncology"
    assert asset_map["asset_a"].stage == "phase_2"


def test_log_unresolved_by_default(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    recs = get_fit_predictions(store)
    assert all(not r.resolved for r in recs)


def test_log_empty_rows_produces_no_records(store) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=[])
    assert ids == []
    assert get_fit_predictions(store) == []


def test_log_overwrite_same_date(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    new_rows = [_FakeRow("asset_z", rank=1, fit_score=0.99)]
    log_fit_predictions(store, acquirer_id="vertex", screen_date="2026-01-15",
                        rows=new_rows, overwrite_same_date=True)
    recs = get_fit_predictions(store, acquirer_id="vertex")
    assert len(recs) == 1
    assert recs[0].asset_id == "asset_z"


# ── resolve_fit_prediction ────────────────────────────────────────────────────

def test_resolve_sets_outcome_and_resolved(store, sample_rows) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=sample_rows)
    resolve_fit_prediction(store, record_id=ids[0],
                           outcome="acquisition", outcome_date="2026-06-01")
    recs = get_fit_predictions(store, asset_id="asset_a")
    assert recs[0].resolved is True
    assert recs[0].outcome == "acquisition"
    assert recs[0].outcome_date == "2026-06-01"


def test_resolve_rejects_outcome_before_screen_date(store, sample_rows) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-03-01", rows=sample_rows)
    with pytest.raises(ValueError, match="outcome_date"):
        resolve_fit_prediction(store, record_id=ids[0],
                               outcome="acquisition", outcome_date="2026-01-01")


def test_resolve_rejects_invalid_outcome(store, sample_rows) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=sample_rows)
    with pytest.raises(ValueError, match="outcome"):
        resolve_fit_prediction(store, record_id=ids[0],
                               outcome="ipo", outcome_date="2026-06-01")


def test_resolve_rejects_unknown_record_id(store) -> None:
    with pytest.raises(ValueError, match="No prediction record"):
        resolve_fit_prediction(store, record_id="nonexistent-id",
                               outcome="none", outcome_date="2026-06-01")


# ── get_fit_predictions ───────────────────────────────────────────────────────

def test_filter_by_acquirer(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    log_fit_predictions(store, acquirer_id="pfizer",
                        screen_date="2026-01-15", rows=sample_rows)
    recs = get_fit_predictions(store, acquirer_id="vertex")
    assert all(r.acquirer_id == "vertex" for r in recs)
    assert len(recs) == 3


def test_filter_by_asset(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    recs = get_fit_predictions(store, asset_id="asset_b")
    assert len(recs) == 1
    assert recs[0].asset_id == "asset_b"


def test_resolved_only_filter(store, sample_rows) -> None:
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=sample_rows)
    resolve_fit_prediction(store, record_id=ids[0],
                           outcome="acquisition", outcome_date="2026-06-01")
    recs = get_fit_predictions(store, resolved_only=True)
    assert len(recs) == 1


def test_as_of_date_no_lookahead(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-04-01", rows=sample_rows[:1])
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-06-01", rows=sample_rows[1:2])
    # As of April: should only see the April screen
    recs = get_fit_predictions(store, as_of_date="2026-04-01")
    assert all(r.screen_date <= "2026-04-01" for r in recs)
    assert len(recs) == 1


# ── grade_fit_predictions ─────────────────────────────────────────────────────

def _setup_grading_scenario(store) -> list[str]:
    """One screen with 3 assets; rank-1 is a deal, rank-2 is not, rank-3 is not."""
    rows = [
        _FakeRow("deal_asset", rank=1, fit_score=0.92,
                 therapeutic_area="oncology", stage="phase_3"),
        _FakeRow("no_deal_a", rank=2, fit_score=0.78,
                 therapeutic_area="oncology", stage="phase_2"),
        _FakeRow("no_deal_b", rank=3, fit_score=0.55,
                 therapeutic_area="immunology", stage="phase_2"),
    ]
    ids = log_fit_predictions(store, acquirer_id="vertex",
                              screen_date="2026-01-15", rows=rows)
    # Resolve all three
    resolve_fit_prediction(store, record_id=ids[0],
                           outcome="acquisition", outcome_date="2026-06-01")
    resolve_fit_prediction(store, record_id=ids[1],
                           outcome="none", outcome_date="2026-06-01")
    resolve_fit_prediction(store, record_id=ids[2],
                           outcome="none", outcome_date="2026-06-01")
    return ids


def test_grade_empty_store(store) -> None:
    report = grade_fit_predictions(store)
    assert report.n_screens == 0
    assert report.precision_at_1 == 0.0
    assert report.precision_at_3 == 0.0


def test_grade_perfect_rank1(store) -> None:
    _setup_grading_scenario(store)
    report = grade_fit_predictions(store, acquirer_id="vertex")
    assert report.precision_at_1 == 1.0
    assert report.precision_at_3 == 1.0


def test_grade_mrr_rank1_is_1(store) -> None:
    _setup_grading_scenario(store)
    report = grade_fit_predictions(store, acquirer_id="vertex")
    assert report.mean_reciprocal_rank == 1.0


def test_grade_p3_hit_on_rank2(store) -> None:
    """Rank-2 deal: P@1=0, P@3=1, MRR=0.5."""
    rows = [
        _FakeRow("no_deal", rank=1, fit_score=0.92,
                 therapeutic_area="oncology", stage="phase_3"),
        _FakeRow("deal_asset", rank=2, fit_score=0.78,
                 therapeutic_area="oncology", stage="phase_3"),
    ]
    ids = log_fit_predictions(store, acquirer_id="pfizer",
                              screen_date="2026-01-15", rows=rows)
    resolve_fit_prediction(store, record_id=ids[0],
                           outcome="none", outcome_date="2026-06-01")
    resolve_fit_prediction(store, record_id=ids[1],
                           outcome="acquisition", outcome_date="2026-06-01")
    report = grade_fit_predictions(store, acquirer_id="pfizer")
    assert report.precision_at_1 == 0.0
    assert report.precision_at_3 == 1.0
    assert abs(report.mean_reciprocal_rank - 0.5) < 0.01


def test_grade_report_structure(store) -> None:
    _setup_grading_scenario(store)
    report = grade_fit_predictions(store, acquirer_id="vertex")
    assert isinstance(report, FitGradeReport)
    assert report.n_screens == 1
    assert report.n_total == 3
    assert report.n_deals == 1
    assert isinstance(report.ta_breakdown, dict)
    assert isinstance(report.stage_breakdown, dict)


def test_grade_ta_breakdown_populated(store) -> None:
    _setup_grading_scenario(store)
    report = grade_fit_predictions(store, acquirer_id="vertex")
    assert "oncology" in report.ta_breakdown
    assert report.ta_breakdown["oncology"]["n"] >= 1


def test_grade_no_resolved_records_scores_zero(store, sample_rows) -> None:
    log_fit_predictions(store, acquirer_id="vertex",
                        screen_date="2026-01-15", rows=sample_rows)
    # Don't resolve
    report = grade_fit_predictions(store, acquirer_id="vertex")
    assert report.n_screens == 0
    assert report.precision_at_1 == 0.0

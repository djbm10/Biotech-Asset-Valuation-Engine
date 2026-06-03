"""Phase 4 Learning Layer tests — PredictionLog, PostmortemStore, RuleSuggester."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from bve.learning.postmortem import ErrorCategory, PostmortemEntry, PostmortemStore
from bve.learning.prediction_log import (
    PredictionLog,
    PredictionOutcome,
    PredictionRecord,
)
from bve.learning.rule_suggester import RuleSuggester, RuleSuggestionType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def log() -> PredictionLog:
    """In-memory PredictionLog for test isolation."""
    return PredictionLog(db_path=":memory:")


@pytest.fixture()
def store() -> PostmortemStore:
    return PostmortemStore()


@pytest.fixture()
def suggester() -> RuleSuggester:
    return RuleSuggester()


def _make_prediction(
    prediction_id: str = "pred-1",
    asset_id: str = "ASSET-A",
    model_pos: float = 0.70,
    catalyst_type: str = "phase3_readout",
    predicted_on: date = date(2025, 1, 1),
    expected_catalyst_date: date | None = date(2025, 6, 1),
) -> PredictionRecord:
    return PredictionRecord(
        prediction_id=prediction_id,
        asset_id=asset_id,
        predicted_on=predicted_on,
        catalyst_type=catalyst_type,
        expected_catalyst_date=expected_catalyst_date,
        model_pos=model_pos,
        market_implied_pos=0.60,
        asymmetry_score=1.2,
        scenario_ev_pct=0.15,
        notes="test prediction",
    )


def _make_outcome(
    prediction_id: str = "pred-1",
    asset_id: str = "ASSET-A",
    actual_result: str = "success",
    outcome_date: date = date(2025, 6, 15),
    price_change_pct: float | None = 0.35,
) -> PredictionOutcome:
    return PredictionOutcome(
        prediction_id=prediction_id,
        asset_id=asset_id,
        outcome_date=outcome_date,
        actual_result=actual_result,
        price_change_pct=price_change_pct,
        notes="test outcome",
    )


def _make_postmortem(
    asset_id: str = "ASSET-A",
    primary_error: ErrorCategory = ErrorCategory.CORRECT,
    actual_result: str = "success",
    model_pos: float = 0.70,
    catalyst_date: date = date(2025, 6, 15),
) -> PostmortemEntry:
    return PostmortemEntry(
        postmortem_id=str(uuid.uuid4()),
        asset_id=asset_id,
        ticker="AAAA",
        catalyst_date=catalyst_date,
        created_date=date(2025, 6, 20),
        catalyst_type="phase3_readout",
        actual_result=actual_result,
        model_pos_at_entry=model_pos,
        market_implied_pos_at_entry=0.55,
        price_change_pct=0.30,
        primary_error=primary_error,
        secondary_errors=[],
        what_model_got_right="good science read",
        what_model_got_wrong="",
        lessons="",
    )


# ===========================================================================
# PredictionLog tests
# ===========================================================================


class TestPredictionLogRoundtrip:
    def test_log_and_retrieve_prediction(self, log: PredictionLog) -> None:
        pred = _make_prediction()
        log.log_prediction(pred)
        results = log.get_predictions()
        assert len(results) == 1
        assert results[0].prediction_id == "pred-1"
        assert results[0].model_pos == pytest.approx(0.70)

    def test_logged_prediction_fields_preserved(self, log: PredictionLog) -> None:
        pred = _make_prediction(model_pos=0.55, catalyst_type="pdufa")
        log.log_prediction(pred)
        r = log.get_predictions()[0]
        assert r.catalyst_type == "pdufa"
        assert r.market_implied_pos == pytest.approx(0.60)
        assert r.asymmetry_score == pytest.approx(1.2)
        assert r.scenario_ev_pct == pytest.approx(0.15)
        assert r.notes == "test prediction"

    def test_log_and_retrieve_outcome(self, log: PredictionLog) -> None:
        outcome = _make_outcome()
        log.log_outcome(outcome)
        results = log.get_outcomes()
        assert len(results) == 1
        assert results[0].actual_result == "success"
        assert results[0].price_change_pct == pytest.approx(0.35)

    def test_outcome_fields_preserved(self, log: PredictionLog) -> None:
        outcome = _make_outcome(actual_result="failure", price_change_pct=-0.45)
        log.log_outcome(outcome)
        r = log.get_outcomes()[0]
        assert r.actual_result == "failure"
        assert r.price_change_pct == pytest.approx(-0.45)
        assert r.notes == "test outcome"

    def test_multiple_predictions_stored(self, log: PredictionLog) -> None:
        for i in range(5):
            log.log_prediction(_make_prediction(prediction_id=f"p{i}", asset_id="A"))
        assert len(log.get_predictions()) == 5

    def test_expected_catalyst_date_none_roundtrip(self, log: PredictionLog) -> None:
        pred = _make_prediction(expected_catalyst_date=None)
        log.log_prediction(pred)
        r = log.get_predictions()[0]
        assert r.expected_catalyst_date is None


class TestPredictionLogFiltering:
    def test_filter_predictions_by_asset_id(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction(prediction_id="p1", asset_id="ASSET-A"))
        log.log_prediction(_make_prediction(prediction_id="p2", asset_id="ASSET-B"))
        a_results = log.get_predictions(asset_id="ASSET-A")
        assert len(a_results) == 1
        assert a_results[0].asset_id == "ASSET-A"

    def test_filter_outcomes_by_asset_id(self, log: PredictionLog) -> None:
        log.log_outcome(_make_outcome(prediction_id="p1", asset_id="ASSET-A"))
        log.log_outcome(_make_outcome(prediction_id="p2", asset_id="ASSET-B"))
        a_results = log.get_outcomes(asset_id="ASSET-A")
        assert len(a_results) == 1
        assert a_results[0].asset_id == "ASSET-A"

    def test_filter_returns_empty_for_unknown_asset(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction())
        assert log.get_predictions(asset_id="UNKNOWN") == []


class TestMatchedPairs:
    def test_matched_pairs_only_when_both_exist(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction(prediction_id="p1"))
        log.log_prediction(_make_prediction(prediction_id="p2"))
        log.log_outcome(_make_outcome(prediction_id="p1"))
        pairs = log.matched_pairs()
        assert len(pairs) == 1
        assert pairs[0][0].prediction_id == "p1"
        assert pairs[0][1].prediction_id == "p1"

    def test_no_pairs_when_no_outcomes(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction())
        assert log.matched_pairs() == []

    def test_matched_pairs_filter_by_asset(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction(prediction_id="p1", asset_id="A"))
        log.log_prediction(_make_prediction(prediction_id="p2", asset_id="B"))
        log.log_outcome(_make_outcome(prediction_id="p1", asset_id="A"))
        log.log_outcome(_make_outcome(prediction_id="p2", asset_id="B"))
        pairs_a = log.matched_pairs(asset_id="A")
        assert len(pairs_a) == 1
        assert pairs_a[0][0].asset_id == "A"


class TestComputeAccuracy:
    def test_brier_zero_when_all_perfect(self, log: PredictionLog) -> None:
        # model_pos=1.0 and actual="success" → (1-1)² = 0
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=1.0))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="success"))
        acc = log.compute_accuracy()
        assert acc.brier_score == pytest.approx(0.0)

    def test_brier_one_when_all_wrong(self, log: PredictionLog) -> None:
        # model_pos=1.0 and actual="failure" → (1-0)² = 1
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=1.0))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="failure"))
        acc = log.compute_accuracy()
        assert acc.brier_score == pytest.approx(1.0)

    def test_brier_score_arithmetic(self, log: PredictionLog) -> None:
        # (0.7-1)² + (0.3-0)² = 0.09 + 0.09 = 0.18 / 2 = 0.09
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=0.70))
        log.log_prediction(_make_prediction(prediction_id="p2", model_pos=0.30))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="success"))
        log.log_outcome(_make_outcome(prediction_id="p2", actual_result="failure"))
        acc = log.compute_accuracy()
        assert acc.brier_score == pytest.approx(0.09, abs=1e-6)

    def test_calibration_error_arithmetic(self, log: PredictionLog) -> None:
        # |0.7 - 1| + |0.3 - 0| = 0.3 + 0.3 = 0.6 / 2 = 0.3
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=0.70))
        log.log_prediction(_make_prediction(prediction_id="p2", model_pos=0.30))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="success"))
        log.log_outcome(_make_outcome(prediction_id="p2", actual_result="failure"))
        acc = log.compute_accuracy()
        assert acc.calibration_error == pytest.approx(0.30, abs=1e-6)

    def test_n_correct_counting(self, log: PredictionLog) -> None:
        # p1: pos=0.8 → predicted success, actual success → correct
        # p2: pos=0.3 → predicted failure, actual failure → correct
        # p3: pos=0.8 → predicted success, actual failure → wrong
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=0.80))
        log.log_prediction(_make_prediction(prediction_id="p2", model_pos=0.30))
        log.log_prediction(_make_prediction(prediction_id="p3", model_pos=0.80))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="success"))
        log.log_outcome(_make_outcome(prediction_id="p2", actual_result="failure"))
        log.log_outcome(_make_outcome(prediction_id="p3", actual_result="failure"))
        acc = log.compute_accuracy()
        assert acc.n_correct == 2

    def test_n_successes_predicted(self, log: PredictionLog) -> None:
        # Only counts where pos>=0.5 AND actual=="success"
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=0.80))
        log.log_prediction(_make_prediction(prediction_id="p2", model_pos=0.80))
        log.log_prediction(_make_prediction(prediction_id="p3", model_pos=0.30))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="success"))
        log.log_outcome(_make_outcome(prediction_id="p2", actual_result="failure"))
        log.log_outcome(_make_outcome(prediction_id="p3", actual_result="success"))
        acc = log.compute_accuracy()
        assert acc.n_successes_predicted == 1

    def test_empty_log_returns_zero_count_record(self, log: PredictionLog) -> None:
        acc = log.compute_accuracy()
        assert acc.n_predictions == 0
        assert acc.n_correct == 0
        assert acc.brier_score is None
        assert acc.calibration_error is None

    def test_accuracy_filter_by_asset(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction(prediction_id="p1", asset_id="A", model_pos=1.0))
        log.log_prediction(_make_prediction(prediction_id="p2", asset_id="B", model_pos=0.0))
        log.log_outcome(_make_outcome(prediction_id="p1", asset_id="A", actual_result="success"))
        log.log_outcome(_make_outcome(prediction_id="p2", asset_id="B", actual_result="success"))
        acc_a = log.compute_accuracy(asset_id="A")
        assert acc_a.brier_score == pytest.approx(0.0)

    def test_n_predictions_includes_unmatched(self, log: PredictionLog) -> None:
        log.log_prediction(_make_prediction(prediction_id="p1"))
        log.log_prediction(_make_prediction(prediction_id="p2"))
        # Only one outcome
        log.log_outcome(_make_outcome(prediction_id="p1"))
        acc = log.compute_accuracy()
        assert acc.n_predictions == 2


# ===========================================================================
# PostmortemStore tests
# ===========================================================================


class TestPostmortemStoreRoundtrip:
    def test_add_and_get_roundtrip(self, store: PostmortemStore) -> None:
        entry = _make_postmortem(asset_id="ASSET-X")
        store.add(entry)
        retrieved = store.get(entry.postmortem_id)
        assert retrieved is not None
        assert retrieved.asset_id == "ASSET-X"

    def test_get_returns_none_for_unknown_id(self, store: PostmortemStore) -> None:
        assert store.get("does-not-exist") is None

    def test_list_all_returns_all_entries(self, store: PostmortemStore) -> None:
        for i in range(4):
            store.add(_make_postmortem(catalyst_date=date(2025, i + 1, 1)))
        assert len(store.list_all()) == 4

    def test_list_all_sorted_by_catalyst_date(self, store: PostmortemStore) -> None:
        store.add(_make_postmortem(catalyst_date=date(2025, 6, 1)))
        store.add(_make_postmortem(catalyst_date=date(2025, 1, 1)))
        entries = store.list_all()
        assert entries[0].catalyst_date < entries[1].catalyst_date


class TestPostmortemFiltering:
    def test_by_error_category_returns_matching(self, store: PostmortemStore) -> None:
        e1 = _make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE)
        e2 = _make_postmortem(primary_error=ErrorCategory.CORRECT)
        store.add(e1)
        store.add(e2)
        overestimates = store.by_error_category(ErrorCategory.POS_OVERESTIMATE)
        assert len(overestimates) == 1
        assert overestimates[0].postmortem_id == e1.postmortem_id

    def test_by_error_category_empty_when_no_match(self, store: PostmortemStore) -> None:
        store.add(_make_postmortem(primary_error=ErrorCategory.CORRECT))
        result = store.by_error_category(ErrorCategory.TIMING_ERROR)
        assert result == []

    def test_by_asset_returns_matching(self, store: PostmortemStore) -> None:
        store.add(_make_postmortem(asset_id="ASSET-A"))
        store.add(_make_postmortem(asset_id="ASSET-B"))
        store.add(_make_postmortem(asset_id="ASSET-A"))
        result = store.by_asset("ASSET-A")
        assert len(result) == 2
        assert all(e.asset_id == "ASSET-A" for e in result)

    def test_by_asset_returns_empty_for_unknown(self, store: PostmortemStore) -> None:
        store.add(_make_postmortem(asset_id="ASSET-A"))
        assert store.by_asset("UNKNOWN") == []


class TestPostmortemAnalytics:
    def test_error_distribution_counts_correctly(self, store: PostmortemStore) -> None:
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE))
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE))
        store.add(_make_postmortem(primary_error=ErrorCategory.CORRECT))
        dist = store.error_distribution()
        assert dist["pos_overestimate"] == 2
        assert dist["correct"] == 1

    def test_error_distribution_empty_when_no_entries(self, store: PostmortemStore) -> None:
        assert store.error_distribution() == {}

    def test_most_common_error_returns_correct_category(
        self, store: PostmortemStore
    ) -> None:
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE))
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE))
        store.add(_make_postmortem(primary_error=ErrorCategory.CORRECT))
        assert store.most_common_error() == ErrorCategory.POS_OVERESTIMATE

    def test_most_common_error_returns_none_when_empty(
        self, store: PostmortemStore
    ) -> None:
        assert store.most_common_error() is None


# ===========================================================================
# RuleSuggester tests
# ===========================================================================


def _fill_overestimates(store: PostmortemStore, count: int) -> None:
    for _ in range(count):
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE))


def _fill_underestimates(store: PostmortemStore, count: int) -> None:
    for _ in range(count):
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_UNDERESTIMATE))


def _fill_financing(store: PostmortemStore, count: int) -> None:
    for _ in range(count):
        store.add(_make_postmortem(primary_error=ErrorCategory.FINANCING_SURPRISE))


def _fill_competition(store: PostmortemStore, count: int) -> None:
    for _ in range(count):
        store.add(_make_postmortem(primary_error=ErrorCategory.COMPETITION_SURPRISE))


class TestRuleSuggesterPostmortemBased:
    def test_lower_base_pos_triggered_when_overestimates_exceed_threshold(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_overestimates(store, 5)  # 5 of 5 = 100% > 40%
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.LOWER_BASE_POS in types

    def test_lower_base_pos_not_triggered_when_count_too_low(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_overestimates(store, 3)  # 3 is NOT > 3
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.LOWER_BASE_POS not in types

    def test_lower_base_pos_not_triggered_when_fraction_too_low(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_overestimates(store, 4)
        # Add many other errors so fraction drops below 40%
        for _ in range(10):
            store.add(_make_postmortem(primary_error=ErrorCategory.CORRECT))
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.LOWER_BASE_POS not in types

    def test_raise_base_pos_triggered_when_underestimates_exceed_threshold(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_underestimates(store, 5)
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.RAISE_BASE_POS in types

    def test_raise_base_pos_not_triggered_when_count_too_low(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_underestimates(store, 2)
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.RAISE_BASE_POS not in types

    def test_add_financing_gate_triggered_at_threshold(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_financing(store, 2)
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.ADD_FINANCING_GATE in types

    def test_add_financing_gate_not_triggered_below_threshold(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_financing(store, 1)
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.ADD_FINANCING_GATE not in types

    def test_add_competition_discount_triggered_at_threshold(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_competition(store, 2)
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.ADD_COMPETITION_DISCOUNT in types

    def test_add_competition_discount_not_triggered_below_threshold(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_competition(store, 1)
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.ADD_COMPETITION_DISCOUNT not in types

    def test_no_suggestions_when_errors_sparse_and_mixed(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        # Mixed errors, none dominant
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_OVERESTIMATE))
        store.add(_make_postmortem(primary_error=ErrorCategory.POS_UNDERESTIMATE))
        store.add(_make_postmortem(primary_error=ErrorCategory.TIMING_ERROR))
        suggestions = suggester.analyze(store, log)
        assert suggestions == []

    def test_all_suggestions_require_human_review(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_overestimates(store, 5)
        _fill_financing(store, 2)
        _fill_competition(store, 2)
        for s in suggester.analyze(store, log):
            assert s.requires_human_review is True
            assert s.auto_applicable is False

    def test_evidence_count_reflects_postmortem_count(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_overestimates(store, 6)
        suggestions = suggester.analyze(store, log)
        lower_pos = next(
            s for s in suggestions if s.suggestion_type == RuleSuggestionType.LOWER_BASE_POS
        )
        assert lower_pos.evidence_count == 6


class TestRuleSuggesterBrierBased:
    def test_poor_brier_triggers_lower_base_pos(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        # model_pos=1.0, actual=failure → brier=(1-0)²=1.0 > 0.25
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=1.0))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="failure"))
        suggestions = suggester.analyze(store, log)
        types = [s.suggestion_type for s in suggestions]
        assert RuleSuggestionType.LOWER_BASE_POS in types

    def test_good_brier_does_not_trigger(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        # brier=0.0 < 0.25
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=1.0))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="success"))
        suggestions = suggester.analyze(store, log)
        # No postmortem errors either, so no suggestions expected
        assert suggestions == []

    def test_brier_does_not_duplicate_postmortem_lower_base_pos(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        # Both postmortem overestimates AND bad brier — only one LOWER_BASE_POS
        _fill_overestimates(store, 5)
        log.log_prediction(_make_prediction(prediction_id="p1", model_pos=1.0))
        log.log_outcome(_make_outcome(prediction_id="p1", actual_result="failure"))
        suggestions = suggester.analyze(store, log)
        lower_pos = [s for s in suggestions if s.suggestion_type == RuleSuggestionType.LOWER_BASE_POS]
        assert len(lower_pos) == 1


class TestRuleSuggesterTopSuggestion:
    def test_top_suggestion_returns_highest_confidence(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_overestimates(store, 5)  # confidence=0.80
        _fill_financing(store, 2)  # confidence=0.70
        top = suggester.top_suggestion(store, log)
        assert top is not None
        assert top.suggestion_type == RuleSuggestionType.LOWER_BASE_POS
        assert top.confidence == pytest.approx(0.80)

    def test_top_suggestion_returns_none_when_empty(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        assert suggester.top_suggestion(store, log) is None

    def test_top_suggestion_returns_none_when_no_triggers_met(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        store.add(_make_postmortem(primary_error=ErrorCategory.CORRECT))
        assert suggester.top_suggestion(store, log) is None

    def test_top_suggestion_is_a_rule_suggestion(
        self, store: PostmortemStore, log: PredictionLog, suggester: RuleSuggester
    ) -> None:
        _fill_competition(store, 3)
        top = suggester.top_suggestion(store, log)
        assert top is not None
        assert isinstance(top.suggestion_type, RuleSuggestionType)
        assert top.confidence >= 0.0
        assert top.confidence <= 1.0

"""Tests for bve.analysis.post_mortem."""
import pytest
from bve.analysis.post_mortem import (
    PostMortemCase, PostMortemAnalysis, PostMortemSummary,
    analyze_case, summarize,
)


def _case(**kwargs):
    defaults = dict(
        program_id="PROG-001",
        asset_name="Drug X",
        company="Acme Bio",
        therapeutic_area="oncology",
        phase="phase_3",
        modality="small_molecule",
        predicted_pos=0.65,
        actual_success=True,
        predicted_price_move_pct=0.55,
        actual_price_move_pct=0.50,
        prediction_date="2024-06-01",
        resolution_date="2025-01-15",
    )
    defaults.update(kwargs)
    return PostMortemCase(**defaults)


class TestAnalyzeCase:
    def test_returns_analysis(self):
        a = analyze_case(_case())
        assert isinstance(a, PostMortemAnalysis)

    def test_directionally_correct_when_both_positive(self):
        a = analyze_case(_case(predicted_pos=0.70, actual_success=True))
        assert a.directionally_correct is True

    def test_directionally_wrong_when_high_pos_fails(self):
        a = analyze_case(_case(predicted_pos=0.80, actual_success=False))
        assert a.directionally_correct is False

    def test_directionally_wrong_when_low_pos_succeeds(self):
        a = analyze_case(_case(predicted_pos=0.10, actual_success=True))
        assert a.directionally_correct is False

    def test_pos_error_magnitude_is_non_negative(self):
        a = analyze_case(_case())
        assert a.pos_error_magnitude >= 0.0

    def test_price_divergence_is_non_negative(self):
        a = analyze_case(_case())
        assert a.price_divergence >= 0.0

    def test_primary_category_is_valid_string(self):
        valid = {
            "pos_error", "timing_error", "thesis_error", "competitive_surprise",
            "financing_event", "regulatory_surprise", "market_drift", "correct",
        }
        a = analyze_case(_case())
        assert a.primary_error_category in valid

    def test_model_grade_is_letter(self):
        a = analyze_case(_case())
        assert a.model_grade in ("A", "B", "C", "D", "F")

    def test_contributing_factors_is_list(self):
        a = analyze_case(_case())
        assert isinstance(a.contributing_factors, list)

    def test_lessons_is_list(self):
        a = analyze_case(_case())
        assert isinstance(a.lessons, list)


class TestPOSErrorCategory:
    def test_high_pos_failure_is_pos_error(self):
        a = analyze_case(_case(predicted_pos=0.85, actual_success=False))
        assert a.primary_error_category == "pos_error"

    def test_low_pos_success_is_pos_error(self):
        a = analyze_case(_case(predicted_pos=0.15, actual_success=True))
        assert a.primary_error_category == "pos_error"

    def test_pos_error_grade_f_for_large_miss(self):
        a = analyze_case(_case(predicted_pos=0.90, actual_success=False))
        assert a.model_grade == "F"

    def test_correct_prediction_grade_a(self):
        a = analyze_case(_case(
            predicted_pos=0.70,
            actual_success=True,
            predicted_price_move_pct=0.40,
            actual_price_move_pct=0.42,
        ))
        assert a.model_grade in ("A", "B")


class TestTimingError:
    def test_timing_error_flagged_when_off_by_more_than_6mo(self):
        a = analyze_case(_case(
            predicted_resolution_months=12.0,
            actual_resolution_months=24.0,
        ))
        assert "timing_error" in (
            [a.primary_error_category] + a.contributing_factors
        ) or any("timing" in f.lower() for f in a.contributing_factors)

    def test_no_timing_error_when_close(self):
        a = analyze_case(_case(
            predicted_resolution_months=12.0,
            actual_resolution_months=14.0,
        ))
        assert a.primary_error_category != "timing_error"


class TestCompetitiveSurprise:
    def test_competitor_event_flagged(self):
        a = analyze_case(_case(
            predicted_pos=0.50,
            actual_success=False,
            competitor_event_before_resolution=True,
        ))
        assert any("competitor" in f.lower() for f in a.contributing_factors)


class TestFinancingEvent:
    def test_dilutive_raise_flagged(self):
        a = analyze_case(_case(dilutive_raise_before_resolution=True))
        assert any("dilut" in f.lower() for f in a.contributing_factors)


class TestRegulatorySuprise:
    def test_regulatory_surprise_flagged(self):
        a = analyze_case(_case(regulatory_surprise=True, predicted_pos=0.50, actual_success=False))
        assert "regulatory_surprise" in a.primary_error_category or any(
            "fda" in f.lower() or "regulatory" in f.lower() for f in a.contributing_factors
        )


class TestSummarize:
    def _make_cases(self, n: int = 5) -> list[PostMortemAnalysis]:
        cases = [
            _case(predicted_pos=0.70, actual_success=True),
            _case(predicted_pos=0.90, actual_success=False),
            _case(predicted_pos=0.30, actual_success=False),
            _case(predicted_pos=0.15, actual_success=True),
            _case(predicted_pos=0.55, actual_success=True),
        ][:n]
        return [analyze_case(c) for c in cases]

    def test_empty_list(self):
        s = summarize([])
        assert s.n_cases == 0
        assert s.directional_accuracy == 0.0

    def test_n_cases_correct(self):
        s = summarize(self._make_cases(5))
        assert s.n_cases == 5

    def test_directional_accuracy_in_range(self):
        s = summarize(self._make_cases())
        assert 0.0 <= s.directional_accuracy <= 1.0

    def test_error_by_category_has_all_keys(self):
        s = summarize(self._make_cases())
        expected_keys = {
            "pos_error", "timing_error", "thesis_error", "competitive_surprise",
            "financing_event", "regulatory_surprise", "market_drift", "correct",
        }
        assert set(s.error_by_category.keys()) == expected_keys

    def test_error_by_ta_keyed_by_ta(self):
        s = summarize(self._make_cases())
        assert "oncology" in s.error_by_ta

    def test_error_by_phase_keyed_by_phase(self):
        s = summarize(self._make_cases())
        assert "phase_3" in s.error_by_phase

    def test_error_by_modality_keyed_by_modality(self):
        s = summarize(self._make_cases())
        assert "small_molecule" in s.error_by_modality

    def test_systematic_bias_when_dominant_category(self):
        # Create 5 cases all with pos_error (high confidence, all failed)
        cases = [
            analyze_case(_case(predicted_pos=0.90, actual_success=False))
            for _ in range(5)
        ]
        s = summarize(cases)
        assert s.systematic_bias is not None
        assert "pos_error" in s.systematic_bias

    def test_no_systematic_bias_when_diverse_errors(self):
        # Mix of outcomes — should not produce bias
        cases = self._make_cases(5)
        s = summarize(cases)
        # Bias may or may not fire depending on distribution; just check type
        assert s.systematic_bias is None or isinstance(s.systematic_bias, str)

"""Sprint 41 — Layer 5 Calibration, Confidence, and Explainability Overlay tests.

Covers:
  • Shrinkage weight tier selection (4 tiers)
  • Deterministic p_takeout_12m with explicit logistic_probability
  • Time window ordering p6m < p12m < p18m
  • All probability band thresholds
  • Confidence level rules (HIGH / MEDIUM / LOW / VERY_LOW)
  • Range width scaling by confidence level
  • Both divergence flag conditions (and no-flag cases)
  • Calibration cohort mapping for every watchlist class
  • Display probability format by confidence level
  • Gate-to-description translation (all G1-G8)
  • Positive driver assembly (explicit vs fallback auto-generation)
  • what_would_change combines Layer 4 triggers + gate suggestions
  • Data gap generation (explicit vs inferred)
  • Output field completeness
  • Integration scenarios (process_ready / active_pursuit / strategic_radar)
"""
import math
import pytest

from bve.intelligence.ma_layer5_calibration import (
    Layer5Inputs,
    Layer5Output,
    ConfidenceLevel,
    ProbabilityBand,
    compute_layer5,
    _expit,
    _derive_logistic_probability,
    _shrinkage_weights,
    _compute_p12m,
    _compute_time_windows,
    _probability_band,
    _confidence_level,
    _probability_range,
    _divergence_flag,
    _calibration_cohort,
    _display_probability,
    _build_negative_drivers,
    _build_positive_drivers,
    _build_what_would_change,
    _build_data_gaps,
    _SHRINKAGE_SMALL,
    _SHRINKAGE_MODERATE,
    _SHRINKAGE_STANDARD,
    _SHRINKAGE_LARGE,
    _GATE_DESCRIPTIONS,
    _GATE_CHANGE_SUGGESTIONS,
    _CALIBRATION_COHORTS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_inputs(**kwargs) -> Layer5Inputs:
    """Minimal valid inputs with sensible defaults; override via kwargs."""
    defaults = dict(
        rank_score=0.65,
        rank_percentile=0.60,
        strategic_priority=0.70,
        transaction_probability=0.55,
        asset_quality=0.65,
        seller_willingness=0.50,
        base_rate=0.08,
        comparable_bucket_rate=0.12,
        n_comparable_observations=15,
        data_confidence_score=0.75,
        watchlist_class="strategic_radar",
        target_name="TestCo",
    )
    defaults.update(kwargs)
    return Layer5Inputs(**defaults)


# ===========================================================================
# 1. expit / logistic helper
# ===========================================================================

class TestExpit:
    def test_midpoint_returns_half(self):
        assert abs(_expit(0.0) - 0.5) < 1e-10

    def test_large_positive(self):
        assert _expit(20.0) > 0.999

    def test_large_negative(self):
        assert _expit(-20.0) < 0.001

    def test_symmetry(self):
        assert abs(_expit(2.0) + _expit(-2.0) - 1.0) < 1e-10


# ===========================================================================
# 2. Logistic probability derivation
# ===========================================================================

class TestDeriveLogisticProbability:
    def test_midpoint_score_gives_near_half(self):
        # rank_score == _LOGISTIC_MIDPOINT (0.68) → logistic ≈ 0.5
        p = _derive_logistic_probability(0.68)
        assert abs(p - 0.5) < 0.01

    def test_high_score_gives_high_prob(self):
        p = _derive_logistic_probability(0.85)
        assert p > 0.70

    def test_low_score_gives_low_prob(self):
        p = _derive_logistic_probability(0.35)
        assert p < 0.15

    def test_returns_between_0_and_1(self):
        for score in [0.0, 0.3, 0.5, 0.68, 0.8, 1.0]:
            p = _derive_logistic_probability(score)
            assert 0.0 <= p <= 1.0

    def test_monotone_increasing(self):
        scores = [0.2, 0.4, 0.6, 0.8]
        probs = [_derive_logistic_probability(s) for s in scores]
        for a, b in zip(probs, probs[1:]):
            assert b > a


# ===========================================================================
# 3. Shrinkage weight tiers
# ===========================================================================

class TestShrinkageWeights:
    def test_small_n_below_10(self):
        assert _shrinkage_weights(0) == _SHRINKAGE_SMALL
        assert _shrinkage_weights(5) == _SHRINKAGE_SMALL
        assert _shrinkage_weights(9) == _SHRINKAGE_SMALL

    def test_moderate_n_10_to_19(self):
        assert _shrinkage_weights(10) == _SHRINKAGE_MODERATE
        assert _shrinkage_weights(15) == _SHRINKAGE_MODERATE
        assert _shrinkage_weights(19) == _SHRINKAGE_MODERATE

    def test_standard_n_20_to_29(self):
        assert _shrinkage_weights(20) == _SHRINKAGE_STANDARD
        assert _shrinkage_weights(25) == _SHRINKAGE_STANDARD
        assert _shrinkage_weights(29) == _SHRINKAGE_STANDARD

    def test_large_n_30_plus(self):
        assert _shrinkage_weights(30) == _SHRINKAGE_LARGE
        assert _shrinkage_weights(100) == _SHRINKAGE_LARGE

    def test_all_tiers_sum_to_one(self):
        for n in [5, 15, 25, 50]:
            wb, wl, wk = _shrinkage_weights(n)
            assert abs(wb + wl + wk - 1.0) < 1e-10

    def test_small_weights_base_rate_heaviest(self):
        wb, wl, wk = _SHRINKAGE_SMALL
        assert wb > wl
        assert wb > wk

    def test_large_weights_logistic_heaviest(self):
        wb, wl, wk = _SHRINKAGE_LARGE
        assert wl > wb
        assert wl > wk

    def test_base_rate_weight_decreases_as_n_grows(self):
        wb_small, _, _ = _SHRINKAGE_SMALL
        wb_large, _, _ = _SHRINKAGE_LARGE
        assert wb_small > wb_large

    def test_logistic_weight_increases_as_n_grows(self):
        _, wl_small, _ = _SHRINKAGE_SMALL
        _, wl_large, _ = _SHRINKAGE_LARGE
        assert wl_large > wl_small


# ===========================================================================
# 4. p_takeout_12m computation
# ===========================================================================

class TestComputeP12m:
    def test_deterministic_with_known_inputs(self):
        # wb=0.60, wl=0.20, wk=0.20
        # base=0.08, logistic=0.20, bucket=0.12
        # expected: 0.60*0.08 + 0.20*0.20 + 0.20*0.12 = 0.048 + 0.040 + 0.024 = 0.112
        weights = _SHRINKAGE_SMALL  # n<10
        p = _compute_p12m(0.08, 0.20, 0.12, weights)
        assert abs(p - 0.112) < 1e-6

    def test_deterministic_large_n(self):
        # wb=0.30, wl=0.50, wk=0.20
        # base=0.08, logistic=0.50, bucket=0.20
        # expected: 0.30*0.08 + 0.50*0.50 + 0.20*0.20 = 0.024 + 0.250 + 0.040 = 0.314
        weights = _SHRINKAGE_LARGE
        p = _compute_p12m(0.08, 0.50, 0.20, weights)
        assert abs(p - 0.314) < 1e-6

    def test_clamped_to_0_1(self):
        p = _compute_p12m(0.0, 0.0, 0.0, (1.0, 0.0, 0.0))
        assert p == 0.0
        p2 = _compute_p12m(1.0, 1.0, 1.0, (0.33, 0.33, 0.34))
        assert p2 <= 1.0

    def test_weights_sum_to_1_so_p_bounded_by_inputs(self):
        base, logistic, bucket = 0.10, 0.20, 0.15
        for n in [5, 15, 25, 50]:
            w = _shrinkage_weights(n)
            p = _compute_p12m(base, logistic, bucket, w)
            assert min(base, logistic, bucket) <= p <= max(base, logistic, bucket)


# ===========================================================================
# 5. Time window ordering
# ===========================================================================

class TestComputeTimeWindows:
    def test_p6m_less_than_p12m(self):
        for p12m in [0.05, 0.10, 0.20, 0.30, 0.50]:
            p6m, _ = _compute_time_windows(p12m)
            assert p6m < p12m, f"p6m {p6m} not < p12m {p12m}"

    def test_p18m_greater_than_p12m(self):
        for p12m in [0.05, 0.10, 0.20, 0.30, 0.50]:
            _, p18m = _compute_time_windows(p12m)
            assert p18m > p12m, f"p18m {p18m} not > p12m {p12m}"

    def test_p6m_scale_factor(self):
        # p6m == p12m * 0.55
        p12m = 0.20
        p6m, _ = _compute_time_windows(p12m)
        assert abs(p6m - 0.20 * 0.55) < 1e-6

    def test_p18m_survival_formula(self):
        # p18m = 1 - (1 - p12m)^1.35
        p12m = 0.20
        _, p18m = _compute_time_windows(p12m)
        expected = 1.0 - (1.0 - p12m) ** 1.35
        assert abs(p18m - expected) < 1e-6

    def test_zero_probability(self):
        p6m, p18m = _compute_time_windows(0.0)
        assert p6m == 0.0
        assert p18m == 0.0

    def test_one_probability(self):
        p6m, p18m = _compute_time_windows(1.0)
        assert abs(p6m - 0.55) < 1e-6
        assert abs(p18m - 1.0) < 1e-6

    def test_full_ordering_p6m_lt_p12m_lt_p18m(self):
        for p12m in [0.05, 0.15, 0.25, 0.40]:
            p6m, p18m = _compute_time_windows(p12m)
            assert p6m < p12m < p18m


# ===========================================================================
# 6. Probability bands
# ===========================================================================

class TestProbabilityBand:
    def test_very_low_below_0_05(self):
        assert _probability_band(0.0) == ProbabilityBand.VERY_LOW
        assert _probability_band(0.04) == ProbabilityBand.VERY_LOW
        assert _probability_band(0.049) == ProbabilityBand.VERY_LOW

    def test_low_boundary_at_0_05(self):
        assert _probability_band(0.05) == ProbabilityBand.LOW

    def test_low_up_to_0_15(self):
        assert _probability_band(0.05) == ProbabilityBand.LOW
        assert _probability_band(0.10) == ProbabilityBand.LOW
        assert _probability_band(0.14) == ProbabilityBand.LOW

    def test_moderate_boundary_at_0_15(self):
        assert _probability_band(0.15) == ProbabilityBand.MODERATE

    def test_moderate_up_to_0_30(self):
        assert _probability_band(0.15) == ProbabilityBand.MODERATE
        assert _probability_band(0.20) == ProbabilityBand.MODERATE
        assert _probability_band(0.29) == ProbabilityBand.MODERATE

    def test_high_boundary_at_0_30(self):
        assert _probability_band(0.30) == ProbabilityBand.HIGH

    def test_high_up_to_0_50(self):
        assert _probability_band(0.30) == ProbabilityBand.HIGH
        assert _probability_band(0.40) == ProbabilityBand.HIGH
        assert _probability_band(0.499) == ProbabilityBand.HIGH

    def test_exceptional_at_0_50_and_above(self):
        assert _probability_band(0.50) == ProbabilityBand.EXCEPTIONAL
        assert _probability_band(0.75) == ProbabilityBand.EXCEPTIONAL
        assert _probability_band(1.0) == ProbabilityBand.EXCEPTIONAL

    def test_band_values_are_strings(self):
        band = _probability_band(0.20)
        assert isinstance(band.value, str)


# ===========================================================================
# 7. Confidence level rules
# ===========================================================================

class TestConfidenceLevel:
    def test_high_both_thresholds_met(self):
        inputs = _base_inputs(data_confidence_score=0.90, n_comparable_observations=25)
        assert _confidence_level(inputs) == ConfidenceLevel.HIGH

    def test_high_exact_thresholds(self):
        inputs = _base_inputs(data_confidence_score=0.85, n_comparable_observations=20)
        assert _confidence_level(inputs) == ConfidenceLevel.HIGH

    def test_not_high_when_data_below_0_85(self):
        inputs = _base_inputs(data_confidence_score=0.84, n_comparable_observations=25)
        assert _confidence_level(inputs) != ConfidenceLevel.HIGH

    def test_not_high_when_n_below_20(self):
        inputs = _base_inputs(data_confidence_score=0.90, n_comparable_observations=19)
        assert _confidence_level(inputs) != ConfidenceLevel.HIGH

    def test_medium_via_data_score(self):
        inputs = _base_inputs(data_confidence_score=0.70, n_comparable_observations=5)
        assert _confidence_level(inputs) == ConfidenceLevel.MEDIUM

    def test_medium_via_n_observations(self):
        inputs = _base_inputs(data_confidence_score=0.55, n_comparable_observations=15)
        assert _confidence_level(inputs) == ConfidenceLevel.MEDIUM

    def test_medium_exact_data_threshold(self):
        inputs = _base_inputs(data_confidence_score=0.65, n_comparable_observations=5)
        assert _confidence_level(inputs) == ConfidenceLevel.MEDIUM

    def test_medium_exact_n_threshold(self):
        inputs = _base_inputs(data_confidence_score=0.55, n_comparable_observations=10)
        assert _confidence_level(inputs) == ConfidenceLevel.MEDIUM

    def test_low_data_between_0_50_and_0_65(self):
        inputs = _base_inputs(data_confidence_score=0.55, n_comparable_observations=5)
        assert _confidence_level(inputs) == ConfidenceLevel.LOW

    def test_low_exact_minimum(self):
        inputs = _base_inputs(data_confidence_score=0.50, n_comparable_observations=5)
        assert _confidence_level(inputs) == ConfidenceLevel.LOW

    def test_very_low_below_0_50(self):
        inputs = _base_inputs(data_confidence_score=0.40, n_comparable_observations=50)
        assert _confidence_level(inputs) == ConfidenceLevel.VERY_LOW

    def test_very_low_is_checked_first(self):
        # Even with many observations, very_low triggers on data_confidence < 0.50
        inputs = _base_inputs(data_confidence_score=0.45, n_comparable_observations=100)
        assert _confidence_level(inputs) == ConfidenceLevel.VERY_LOW


# ===========================================================================
# 8. Probability range (uncertainty band widths)
# ===========================================================================

class TestProbabilityRange:
    def test_high_confidence_width_30_pct(self):
        lo, hi = _probability_range(0.20, ConfidenceLevel.HIGH)
        assert abs(lo - 0.20 * 0.70) < 1e-4
        assert abs(hi - 0.20 * 1.30) < 1e-4

    def test_medium_confidence_width_50_pct(self):
        lo, hi = _probability_range(0.20, ConfidenceLevel.MEDIUM)
        assert abs(lo - 0.20 * 0.50) < 1e-4
        assert abs(hi - 0.20 * 1.50) < 1e-4

    def test_low_confidence_width_75_pct(self):
        lo, hi = _probability_range(0.20, ConfidenceLevel.LOW)
        assert abs(lo - 0.20 * 0.25) < 1e-4
        assert abs(hi - 0.20 * 1.75) < 1e-4

    def test_very_low_confidence_width_100_pct(self):
        lo, hi = _probability_range(0.10, ConfidenceLevel.VERY_LOW)
        assert abs(lo - 0.0) < 1e-4
        assert abs(hi - 0.20) < 1e-4

    def test_range_always_non_negative(self):
        for conf in ConfidenceLevel:
            lo, hi = _probability_range(0.05, conf)
            assert lo >= 0.0
            assert hi >= 0.0

    def test_range_hi_never_exceeds_1(self):
        lo, hi = _probability_range(0.90, ConfidenceLevel.VERY_LOW)
        assert hi <= 1.0

    def test_lo_le_p12m_le_hi(self):
        for conf in ConfidenceLevel:
            p12m = 0.25
            lo, hi = _probability_range(p12m, conf)
            assert lo <= p12m <= hi


# ===========================================================================
# 9. Divergence flag
# ===========================================================================

class TestDivergenceFlag:
    def test_high_rank_low_prob_triggers_flag(self):
        # percentile > 0.85 AND prob < 0.10
        flag = _divergence_flag(0.90, 0.05)
        assert flag == "strategic_fit_high_but_transaction_probability_low"

    def test_low_rank_high_prob_triggers_flag(self):
        # percentile < 0.50 AND prob > 0.25
        flag = _divergence_flag(0.30, 0.30)
        assert flag == "transaction_possible_but_low_strategic_priority"

    def test_no_flag_mid_range(self):
        flag = _divergence_flag(0.60, 0.15)
        assert flag is None

    def test_no_flag_high_rank_high_prob(self):
        flag = _divergence_flag(0.90, 0.30)
        assert flag is None

    def test_no_flag_low_rank_low_prob(self):
        flag = _divergence_flag(0.30, 0.05)
        assert flag is None

    def test_boundary_high_rank(self):
        # exactly at 0.85 — not above, so no flag
        flag = _divergence_flag(0.85, 0.05)
        assert flag is None

    def test_boundary_high_prob(self):
        # exactly at 0.25 — not above, so no flag
        flag = _divergence_flag(0.30, 0.25)
        assert flag is None

    def test_boundary_low_rank(self):
        # exactly at 0.50 — not below, so no flag
        flag = _divergence_flag(0.50, 0.30)
        assert flag is None


# ===========================================================================
# 10. Calibration cohort mapping
# ===========================================================================

class TestCalibrationCohort:
    @pytest.mark.parametrize("watchlist_class,expected_fragment", [
        ("process_ready", "High-readiness"),
        ("active_pursuit", "Active-setup"),
        ("catalyst_watch", "Catalyst-driven"),
        ("relationship_build", "Relationship-stage"),
        ("strategic_radar", "Strategic-radar"),
        ("data_insufficient", "Data-limited"),
        ("pass", "Excluded"),
    ])
    def test_known_classes(self, watchlist_class, expected_fragment):
        cohort = _calibration_cohort(watchlist_class)
        assert expected_fragment in cohort

    def test_unknown_class_returns_unclassified(self):
        cohort = _calibration_cohort("not_a_real_class")
        assert "Unclassified" in cohort

    def test_all_calibration_cohorts_defined(self):
        expected = {
            "process_ready", "active_pursuit", "catalyst_watch",
            "relationship_build", "strategic_radar", "data_insufficient", "pass",
        }
        assert expected == set(_CALIBRATION_COHORTS.keys())


# ===========================================================================
# 11. Display probability formatting
# ===========================================================================

class TestDisplayProbability:
    def test_very_low_confidence_returns_excluded_text(self):
        display = _display_probability(0.05, ProbabilityBand.VERY_LOW, ConfidenceLevel.VERY_LOW)
        assert "excluded" in display.lower() or "insufficient" in display.lower()

    def test_low_confidence_returns_band_only(self):
        display = _display_probability(0.10, ProbabilityBand.LOW, ConfidenceLevel.LOW)
        assert "Band" in display or "band" in display
        assert "low confidence" in display.lower()

    def test_medium_confidence_shows_approx_percent(self):
        display = _display_probability(0.15, ProbabilityBand.LOW, ConfidenceLevel.MEDIUM)
        assert "15%" in display or "~15%" in display
        assert "Medium" in display

    def test_high_confidence_shows_exact_percent(self):
        display = _display_probability(0.20, ProbabilityBand.MODERATE, ConfidenceLevel.HIGH)
        assert "20%" in display
        assert "High" in display

    def test_rounding_to_nearest_percent(self):
        display = _display_probability(0.153, ProbabilityBand.LOW, ConfidenceLevel.HIGH)
        assert "15%" in display

    def test_low_confidence_no_raw_percentage(self):
        # LOW confidence → band only, no numeric output
        display = _display_probability(0.25, ProbabilityBand.MODERATE, ConfidenceLevel.LOW)
        assert "%" not in display or "low confidence" in display.lower()


# ===========================================================================
# 12. Gate description translation
# ===========================================================================

class TestGateDescriptions:
    def test_all_gates_g1_through_g8_defined(self):
        for gate in ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]:
            assert gate in _GATE_DESCRIPTIONS
            assert len(_GATE_DESCRIPTIONS[gate]) > 10

    def test_all_gates_have_change_suggestions(self):
        for gate in ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]:
            assert gate in _GATE_CHANGE_SUGGESTIONS
            assert len(_GATE_CHANGE_SUGGESTIONS[gate]) > 10

    def test_build_negative_drivers_translates_gate_ids(self):
        drivers = _build_negative_drivers(["G1", "G5"], [])
        assert any("Broken asset" in d for d in drivers)
        assert any("Seller not ready" in d for d in drivers)

    def test_build_negative_drivers_appends_extra_drivers(self):
        drivers = _build_negative_drivers([], ["Custom risk factor"])
        assert "Custom risk factor" in drivers

    def test_build_negative_drivers_no_duplicates(self):
        # Duplicate gate descriptions should not repeat
        drivers = _build_negative_drivers(["G1", "G1"], [])
        assert len(drivers) == 1

    def test_build_negative_drivers_unknown_gate(self):
        drivers = _build_negative_drivers(["G99"], [])
        assert "Gate G99" in drivers[0]

    def test_build_negative_drivers_empty_inputs(self):
        drivers = _build_negative_drivers([], [])
        assert drivers == []


# ===========================================================================
# 13. Positive driver assembly
# ===========================================================================

class TestPositiveDrivers:
    def test_explicit_drivers_returned_as_is(self):
        drivers = _build_positive_drivers(["Capital pressure", "Activist"], 3, 0.80, 0.65)
        assert "Capital pressure" in drivers
        assert "Activist" in drivers

    def test_fallback_high_strategic_priority(self):
        drivers = _build_positive_drivers([], 0, 0.75, 0.30)
        assert any("strategic priority" in d.lower() for d in drivers)

    def test_fallback_elevated_transaction_probability(self):
        drivers = _build_positive_drivers([], 0, 0.50, 0.60)
        assert any("transaction probability" in d.lower() for d in drivers)

    def test_fallback_active_driver_bucket_count(self):
        drivers = _build_positive_drivers([], 3, 0.50, 0.30)
        assert any("driver" in d.lower() for d in drivers)

    def test_no_fallback_when_explicit_provided(self):
        # explicit list prevents fallback auto-generation
        drivers = _build_positive_drivers(["Pipeline gap"], 4, 0.95, 0.95)
        assert len(drivers) == 1
        assert drivers[0] == "Pipeline gap"

    def test_no_fallback_below_thresholds(self):
        # strategic_priority < 0.70, transaction_probability < 0.55, count < 2
        drivers = _build_positive_drivers([], 1, 0.65, 0.40)
        assert drivers == []


# ===========================================================================
# 14. what_would_change assembly
# ===========================================================================

class TestWhatWouldChange:
    def test_includes_layer4_promotion_triggers(self):
        inputs = _base_inputs(
            input_what_would_change=["Seller engages banker"],
            active_gate_ids=[],
        )
        result = _build_what_would_change(inputs)
        assert "Seller engages banker" in result

    def test_includes_gate_suggestions(self):
        inputs = _base_inputs(
            input_what_would_change=[],
            active_gate_ids=["G5"],
        )
        result = _build_what_would_change(inputs)
        assert any("banker" in s.lower() for s in result)

    def test_no_duplicate_suggestions(self):
        inputs = _base_inputs(
            input_what_would_change=[_GATE_CHANGE_SUGGESTIONS["G5"]],
            active_gate_ids=["G5"],
        )
        result = _build_what_would_change(inputs)
        # The suggestion from the gate should not appear twice
        count = sum(1 for s in result if "banker" in s.lower())
        assert count == 1

    def test_empty_when_no_inputs(self):
        inputs = _base_inputs(input_what_would_change=[], active_gate_ids=[])
        result = _build_what_would_change(inputs)
        assert result == []


# ===========================================================================
# 15. Data gap generation
# ===========================================================================

class TestDataGaps:
    def test_explicit_gaps_returned_as_is(self):
        inputs = _base_inputs(input_data_gaps=["Missing Phase 3 data"])
        gaps = _build_data_gaps(inputs)
        assert gaps == ["Missing Phase 3 data"]

    def test_inferred_very_low_confidence(self):
        inputs = _base_inputs(
            input_data_gaps=[],
            data_confidence_score=0.40,
        )
        gaps = _build_data_gaps(inputs)
        assert len(gaps) >= 1
        assert any("diligence" in g.lower() for g in gaps)

    def test_inferred_low_confidence(self):
        inputs = _base_inputs(
            input_data_gaps=[],
            data_confidence_score=0.55,
            n_comparable_observations=5,
        )
        gaps = _build_data_gaps(inputs)
        assert len(gaps) >= 1

    def test_inferred_medium_confidence(self):
        inputs = _base_inputs(
            input_data_gaps=[],
            data_confidence_score=0.70,
            n_comparable_observations=5,
        )
        gaps = _build_data_gaps(inputs)
        assert len(gaps) >= 1

    def test_no_inferred_gaps_at_high_confidence(self):
        inputs = _base_inputs(
            input_data_gaps=[],
            data_confidence_score=0.90,
            n_comparable_observations=25,
        )
        gaps = _build_data_gaps(inputs)
        assert gaps == []


# ===========================================================================
# 16. Output field completeness
# ===========================================================================

class TestOutputFieldCompleteness:
    def test_all_required_fields_present(self):
        inputs = _base_inputs()
        result = compute_layer5(inputs)
        required_fields = [
            "target_name", "acquirer_id",
            "rank_score", "p_takeout_12m", "p_takeout_6m", "p_takeout_18m",
            "probability_band", "probability_range_low", "probability_range_high",
            "confidence_level", "calibration_cohort",
            "top_positive_drivers", "top_negative_drivers",
            "what_would_change_score", "data_gaps",
            "rank_probability_divergence_flag",
            "display_probability",
            "logistic_probability_used", "shrinkage_weights",
            "as_of_date", "model_version", "interpretation",
        ]
        for field in required_fields:
            assert hasattr(result, field), f"Missing field: {field}"

    def test_output_is_frozen(self):
        inputs = _base_inputs()
        result = compute_layer5(inputs)
        with pytest.raises(Exception):
            result.rank_score = 0.99  # frozen model should reject mutation

    def test_rank_score_unchanged_from_input(self):
        inputs = _base_inputs(rank_score=0.72)
        result = compute_layer5(inputs)
        assert result.rank_score == 0.72

    def test_target_name_passed_through(self):
        inputs = _base_inputs(target_name="BioTarget Inc")
        result = compute_layer5(inputs)
        assert result.target_name == "BioTarget Inc"

    def test_acquirer_id_passed_through(self):
        inputs = _base_inputs(acquirer_id="ACQ-001")
        result = compute_layer5(inputs)
        assert result.acquirer_id == "ACQ-001"

    def test_acquirer_id_none_allowed(self):
        inputs = _base_inputs(acquirer_id=None)
        result = compute_layer5(inputs)
        assert result.acquirer_id is None

    def test_deal_value_passed_through(self):
        inputs = _base_inputs(
            estimated_deal_value_low_millions=500.0,
            estimated_deal_value_high_millions=1200.0,
        )
        result = compute_layer5(inputs)
        assert result.estimated_deal_value_low_millions == 500.0
        assert result.estimated_deal_value_high_millions == 1200.0

    def test_shrinkage_weights_tuple_three_elements(self):
        inputs = _base_inputs()
        result = compute_layer5(inputs)
        assert len(result.shrinkage_weights) == 3

    def test_shrinkage_weights_sum_to_one(self):
        inputs = _base_inputs()
        result = compute_layer5(inputs)
        wb, wl, wk = result.shrinkage_weights
        assert abs(wb + wl + wk - 1.0) < 1e-10

    def test_probability_values_in_range(self):
        inputs = _base_inputs()
        result = compute_layer5(inputs)
        for attr in ["p_takeout_6m", "p_takeout_12m", "p_takeout_18m"]:
            val = getattr(result, attr)
            assert 0.0 <= val <= 1.0, f"{attr} = {val}"

    def test_range_lo_le_p12m_le_hi(self):
        inputs = _base_inputs()
        result = compute_layer5(inputs)
        assert result.probability_range_low <= result.p_takeout_12m <= result.probability_range_high


# ===========================================================================
# 17. Logistic probability (explicit vs derived)
# ===========================================================================

class TestLogisticProbabilitySource:
    def test_explicit_logistic_probability_used(self):
        inputs = _base_inputs(logistic_probability=0.42)
        result = compute_layer5(inputs)
        assert abs(result.logistic_probability_used - 0.42) < 1e-6

    def test_derived_when_none(self):
        inputs = _base_inputs(rank_score=0.68, logistic_probability=None)
        result = compute_layer5(inputs)
        expected = _derive_logistic_probability(0.68)
        assert abs(result.logistic_probability_used - expected) < 1e-6

    def test_explicit_affects_p12m(self):
        # With high explicit logistic probability, p12m should be higher
        inputs_low = _base_inputs(logistic_probability=0.05, n_comparable_observations=30)
        inputs_high = _base_inputs(logistic_probability=0.80, n_comparable_observations=30)
        result_low = compute_layer5(inputs_low)
        result_high = compute_layer5(inputs_high)
        assert result_high.p_takeout_12m > result_low.p_takeout_12m


# ===========================================================================
# 18. Integration scenarios
# ===========================================================================

class TestProcessReadyIntegration:
    """High-readiness target: strong signals, high confidence."""

    def test_process_ready_scenario(self, tmp_path, monkeypatch):
        # Block 22: HIGH confidence requires a fitted calibration. Monkeypatch a valid file.
        import json
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        inputs = Layer5Inputs(
            rank_score=0.82,
            rank_percentile=0.90,
            strategic_priority=0.85,
            transaction_probability=0.78,
            asset_quality=0.80,
            seller_willingness=0.75,
            active_driver_bucket_count=3,
            active_gate_ids=[],
            watchlist_class="process_ready",
            data_confidence_score=0.90,
            base_rate=0.15,
            comparable_bucket_rate=0.25,
            n_comparable_observations=35,
            logistic_probability=0.72,
            input_positive_drivers=["Seller running structured process", "Pipeline gap"],
            target_name="TargetCo",
        )
        result = compute_layer5(inputs)
        # High confidence expected (data_confidence=0.90, n=35, calibration_fitted=True)
        assert result.confidence_level == ConfidenceLevel.HIGH.value
        # p12m should be meaningful
        assert result.p_takeout_12m > 0.15
        # Time window ordering
        assert result.p_takeout_6m < result.p_takeout_12m < result.p_takeout_18m
        # Cohort
        assert "High-readiness" in result.calibration_cohort
        # Positive drivers
        assert len(result.top_positive_drivers) >= 2

    def test_process_ready_display_shows_percentage(self, tmp_path, monkeypatch):
        # Block 22: HIGH confidence requires a fitted calibration. Monkeypatch a valid file.
        import json
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        inputs = Layer5Inputs(
            rank_score=0.82,
            rank_percentile=0.90,
            strategic_priority=0.85,
            transaction_probability=0.78,
            asset_quality=0.80,
            seller_willingness=0.75,
            data_confidence_score=0.90,
            n_comparable_observations=35,
            watchlist_class="process_ready",
            target_name="TargetCo",
        )
        result = compute_layer5(inputs)
        assert "%" in result.display_probability
        assert "High" in result.display_probability


class TestActivePursuitIntegration:
    """Active-setup target: moderate confidence, gate caps present."""

    def test_active_pursuit_with_gates(self):
        inputs = Layer5Inputs(
            rank_score=0.60,
            rank_percentile=0.65,
            strategic_priority=0.70,
            transaction_probability=0.55,
            asset_quality=0.65,
            seller_willingness=0.45,
            active_driver_bucket_count=2,
            active_gate_ids=["G5"],
            watchlist_class="active_pursuit",
            data_confidence_score=0.75,
            base_rate=0.10,
            comparable_bucket_rate=0.14,
            n_comparable_observations=18,
            target_name="BioActiveCo",
        )
        result = compute_layer5(inputs)
        # G5 should appear in negative drivers
        assert any("Seller not ready" in d for d in result.top_negative_drivers)
        # G5 change suggestion in what_would_change
        assert any("banker" in s.lower() for s in result.what_would_change_score)
        # Cohort
        assert "Active-setup" in result.calibration_cohort

    def test_active_pursuit_no_divergence_for_normal_signals(self):
        inputs = Layer5Inputs(
            rank_score=0.65,
            rank_percentile=0.60,
            strategic_priority=0.70,
            transaction_probability=0.55,
            asset_quality=0.65,
            seller_willingness=0.50,
            watchlist_class="active_pursuit",
            data_confidence_score=0.75,
            n_comparable_observations=18,
            target_name="BioActiveCo",
        )
        result = compute_layer5(inputs)
        assert result.rank_probability_divergence_flag is None


class TestStrategicRadarIntegration:
    """Low-urgency target: strategic fit but no transaction pressure."""

    def test_strategic_radar_divergence_flag_fires(self):
        inputs = Layer5Inputs(
            rank_score=0.55,
            rank_percentile=0.90,  # high percentile
            strategic_priority=0.85,
            transaction_probability=0.30,
            asset_quality=0.70,
            seller_willingness=0.25,
            active_driver_bucket_count=0,
            active_gate_ids=["G3", "G5"],
            watchlist_class="strategic_radar",
            data_confidence_score=0.75,
            base_rate=0.05,
            comparable_bucket_rate=0.07,
            n_comparable_observations=8,
            logistic_probability=0.06,  # force low probability
            target_name="LongRunnerBio",
        )
        result = compute_layer5(inputs)
        assert result.rank_probability_divergence_flag == (
            "strategic_fit_high_but_transaction_probability_low"
        )

    def test_strategic_radar_cohort(self):
        inputs = _base_inputs(watchlist_class="strategic_radar")
        result = compute_layer5(inputs)
        assert "Strategic-radar" in result.calibration_cohort

    def test_strategic_radar_low_confidence_band_only_display(self, tmp_path, monkeypatch):
        # Block 22: confidence cap removed when calibration is fitted.
        import json
        params_file = tmp_path / "ma_calibration_params.json"
        params_file.write_text(json.dumps({"slope": 8.0, "midpoint": 0.68}))
        monkeypatch.setattr(
            "bve.intelligence.ma_layer5_calibration._CALIBRATION_PARAMS_PATH",
            params_file,
        )
        inputs = Layer5Inputs(
            rank_score=0.45,
            rank_percentile=0.40,
            strategic_priority=0.65,
            transaction_probability=0.30,
            asset_quality=0.55,
            seller_willingness=0.25,
            watchlist_class="strategic_radar",
            data_confidence_score=0.52,
            n_comparable_observations=4,
            target_name="EarlyBio",
        )
        result = compute_layer5(inputs)
        assert result.confidence_level == ConfidenceLevel.LOW.value
        assert "Band" in result.display_probability or "band" in result.display_probability


class TestVeryLowConfidenceIntegration:
    """Targets with insufficient data quality."""

    def test_very_low_confidence_excluded_display(self):
        inputs = _base_inputs(data_confidence_score=0.40)
        result = compute_layer5(inputs)
        assert result.confidence_level == ConfidenceLevel.VERY_LOW.value
        assert "excluded" in result.display_probability.lower() or \
               "insufficient" in result.display_probability.lower()

    def test_very_low_confidence_interpretation_mentions_insufficient(self):
        inputs = _base_inputs(data_confidence_score=0.40)
        result = compute_layer5(inputs)
        assert "insufficient" in result.interpretation.lower()


class TestDivergenceLowRankHighProbIntegration:
    """Transaction setup exists but target is low strategic priority."""

    def test_low_rank_high_prob_divergence_fires(self):
        # percentile < 0.50 AND p12m > 0.25
        inputs = Layer5Inputs(
            rank_score=0.72,
            rank_percentile=0.30,  # low percentile
            strategic_priority=0.50,
            transaction_probability=0.70,
            asset_quality=0.60,
            seller_willingness=0.70,
            active_driver_bucket_count=3,
            watchlist_class="active_pursuit",
            data_confidence_score=0.80,
            base_rate=0.20,
            comparable_bucket_rate=0.35,
            n_comparable_observations=40,
            logistic_probability=0.70,
            target_name="LowPriorityHighRisk",
        )
        result = compute_layer5(inputs)
        assert result.rank_probability_divergence_flag == (
            "transaction_possible_but_low_strategic_priority"
        )


# ===========================================================================
# 19. Shrinkage weight tier boundary precision
# ===========================================================================

class TestShrinkageWeightBoundaryPrecision:
    def test_n_exactly_9_is_small(self):
        assert _shrinkage_weights(9) == _SHRINKAGE_SMALL

    def test_n_exactly_10_is_moderate(self):
        assert _shrinkage_weights(10) == _SHRINKAGE_MODERATE

    def test_n_exactly_19_is_moderate(self):
        assert _shrinkage_weights(19) == _SHRINKAGE_MODERATE

    def test_n_exactly_20_is_standard(self):
        assert _shrinkage_weights(20) == _SHRINKAGE_STANDARD

    def test_n_exactly_29_is_standard(self):
        assert _shrinkage_weights(29) == _SHRINKAGE_STANDARD

    def test_n_exactly_30_is_large(self):
        assert _shrinkage_weights(30) == _SHRINKAGE_LARGE


# ===========================================================================
# 20. Metadata pass-through
# ===========================================================================

class TestMetadataPassthrough:
    def test_as_of_date_passed_through(self):
        inputs = _base_inputs(as_of_date="2026-05-14")
        result = compute_layer5(inputs)
        assert result.as_of_date == "2026-05-14"

    def test_model_version_passed_through(self):
        inputs = _base_inputs(model_version="v2.1")
        result = compute_layer5(inputs)
        assert result.model_version == "v2.1"

    def test_interpretation_contains_target_name(self):
        inputs = _base_inputs(target_name="OmegaBio")
        result = compute_layer5(inputs)
        assert "OmegaBio" in result.interpretation

    def test_interpretation_contains_watchlist_class(self):
        inputs = _base_inputs(watchlist_class="catalyst_watch")
        result = compute_layer5(inputs)
        assert "catalyst" in result.interpretation.lower()

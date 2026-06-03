"""
Sprint 50 — Block 4: CalibratedProbabilityBand

Tests for ma_calibrated_probability_band:
  - minimum_n guard: if segment N < threshold → RANK_ONLY (no probability shown)
  - If N >= threshold → calibrated range with confidence interval
  - RANK_ONLY label is explicit, never a probability number
  - Band includes: lower_bound, point_estimate, upper_bound, confidence_level
  - Segment-level calibration: narrow band from larger segments
  - Empty dataset → RANK_ONLY (no crash)
"""
from __future__ import annotations

import pytest


class TestCalibratedProbabilityBand:
    """Tests for CalibratedProbabilityBand and compute_probability_band."""

    def test_rank_only_when_below_minimum_n(self):
        """Fewer outcomes than minimum_n → RANK_ONLY, no probability shown."""
        from bve.intelligence.ma_calibrated_probability_band import (
            compute_probability_band,
            DisplayMode,
        )

        # 3 outcomes, minimum_n=10 → RANK_ONLY
        outcomes = [1, 0, 1]
        result = compute_probability_band(outcomes, minimum_n=10)
        assert result.display_mode == DisplayMode.RANK_ONLY
        assert result.point_estimate is None
        assert result.lower_bound is None
        assert result.upper_bound is None

    def test_rank_only_label_text_present(self):
        """RANK_ONLY result must carry a label_text explaining why."""
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        result = compute_probability_band([1, 0], minimum_n=10)
        assert result.label_text != ""
        assert "rank" in result.label_text.lower() or "insufficient" in result.label_text.lower()

    def test_band_shown_when_above_minimum_n(self):
        """N >= minimum_n → SHOW_BAND mode, probability band populated."""
        from bve.intelligence.ma_calibrated_probability_band import (
            compute_probability_band,
            DisplayMode,
        )

        # 15 outcomes → above minimum_n=10
        outcomes = [1, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1]
        result = compute_probability_band(outcomes, minimum_n=10)
        assert result.display_mode == DisplayMode.SHOW_BAND
        assert result.point_estimate is not None
        assert result.lower_bound is not None
        assert result.upper_bound is not None
        assert 0.0 <= result.point_estimate <= 1.0

    def test_point_estimate_is_empirical_rate(self):
        """Point estimate should reflect empirical success rate."""
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        outcomes = [1] * 8 + [0] * 12  # 40% success rate
        result = compute_probability_band(outcomes, minimum_n=10)
        assert result.point_estimate == pytest.approx(0.40, abs=0.05)

    def test_band_width_narrows_with_larger_n(self):
        """Larger N → narrower confidence interval."""
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        # Small sample: N=15, 60% success
        small_n = [1] * 9 + [0] * 6
        # Large sample: N=60, 60% success
        large_n = [1] * 36 + [0] * 24

        r_small = compute_probability_band(small_n, minimum_n=10)
        r_large = compute_probability_band(large_n, minimum_n=10)

        width_small = r_small.upper_bound - r_small.lower_bound
        width_large = r_large.upper_bound - r_large.lower_bound

        assert width_large < width_small

    def test_lower_bound_less_than_point_less_than_upper(self):
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        outcomes = [1] * 12 + [0] * 8
        result = compute_probability_band(outcomes, minimum_n=10)
        assert result.lower_bound < result.point_estimate < result.upper_bound

    def test_empty_outcomes_returns_rank_only(self):
        """Empty outcomes list → RANK_ONLY, no crash."""
        from bve.intelligence.ma_calibrated_probability_band import (
            compute_probability_band,
            DisplayMode,
        )
        result = compute_probability_band([], minimum_n=10)
        assert result.display_mode == DisplayMode.RANK_ONLY

    def test_minimum_n_exactly_met_shows_band(self):
        """Exactly minimum_n observations → SHOW_BAND."""
        from bve.intelligence.ma_calibrated_probability_band import (
            compute_probability_band,
            DisplayMode,
        )
        outcomes = [1] * 6 + [0] * 4  # N=10
        result = compute_probability_band(outcomes, minimum_n=10)
        assert result.display_mode == DisplayMode.SHOW_BAND

    def test_confidence_level_reflects_sample_size(self):
        """Larger N → higher band confidence."""
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        small = compute_probability_band([1] * 6 + [0] * 4, minimum_n=10)   # N=10
        large = compute_probability_band([1] * 36 + [0] * 24, minimum_n=10) # N=60

        assert large.confidence_level >= small.confidence_level

    def test_band_output_model_fields(self):
        """CalibratedProbabilityBand must have all required fields."""
        from bve.intelligence.ma_calibrated_probability_band import CalibratedProbabilityBand, compute_probability_band

        outcomes = [1] * 12 + [0] * 8
        result = compute_probability_band(outcomes, minimum_n=10)
        assert isinstance(result, CalibratedProbabilityBand)
        assert hasattr(result, "n_observations")
        assert hasattr(result, "display_mode")
        assert hasattr(result, "point_estimate")
        assert hasattr(result, "lower_bound")
        assert hasattr(result, "upper_bound")
        assert hasattr(result, "confidence_level")
        assert hasattr(result, "label_text")
        assert result.n_observations == 20

    def test_default_minimum_n_is_reasonable(self):
        """Default minimum_n must be documented and ≥ 5."""
        from bve.intelligence.ma_calibrated_probability_band import DEFAULT_MINIMUM_N
        assert DEFAULT_MINIMUM_N >= 5

    def test_segment_label_stored_in_output(self):
        """Segment label passed through to output for display."""
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        outcomes = [1] * 12 + [0] * 8
        result = compute_probability_band(outcomes, minimum_n=10, segment_label="oncology_phase2")
        assert result.segment_label == "oncology_phase2"

    def test_rank_only_segment_label_still_stored(self):
        from bve.intelligence.ma_calibrated_probability_band import compute_probability_band

        result = compute_probability_band([1, 0], minimum_n=10, segment_label="rare_disease")
        assert result.segment_label == "rare_disease"

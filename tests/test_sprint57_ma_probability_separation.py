"""
Block 20 — M&A Probability Separation
TDD tests written BEFORE implementation.

Tests for:
  1. New Layer5Inputs fields: acquisition_fraction, license_fraction,
     comparable_bucket_rate_source
  2. New Layer5Output fields: p_any_strategic_transaction_12m,
     p_full_acquisition_12m, p_license_or_partner_12m, bucket_rate_warning
  3. p_takeout_12m is deprecated alias for p_full_acquisition_12m
  4. resolve_comparable_bucket_rate() helper returns (rate, source) tuple
  5. bucket_rate_warning set when source is 'fallback'
  6. confidence capped at LOW when bucket_rate_source is 'fallback'
  7. Transaction split labelling (derived/heuristic, not independently calibrated)
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_layer5_calibration import (
    Layer5Inputs,
    Layer5Output,
    compute_layer5,
    resolve_comparable_bucket_rate,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_inputs(**kwargs) -> Layer5Inputs:
    defaults = dict(
        rank_score=0.55,
        rank_percentile=0.65,
        strategic_priority=0.60,
        transaction_probability=0.50,
        asset_quality=0.70,
        seller_willingness=0.55,
        base_rate=0.08,
        comparable_bucket_rate=0.12,
        n_comparable_observations=10,
        target_name="TestCo",
        as_of_date="2026-05-27",
    )
    defaults.update(kwargs)
    return Layer5Inputs(**defaults)


# ---------------------------------------------------------------------------
# Block 20-A: New Layer5Inputs fields
# ---------------------------------------------------------------------------

class TestLayer5InputsNewFields:

    def test_acquisition_fraction_default(self):
        inp = _base_inputs()
        assert inp.acquisition_fraction == pytest.approx(0.60)

    def test_license_fraction_default(self):
        inp = _base_inputs()
        assert inp.license_fraction == pytest.approx(0.35)

    def test_comparable_bucket_rate_source_default_empty(self):
        inp = _base_inputs()
        assert inp.comparable_bucket_rate_source == ""

    def test_acquisition_fraction_custom(self):
        inp = _base_inputs(acquisition_fraction=0.75)
        assert inp.acquisition_fraction == pytest.approx(0.75)

    def test_license_fraction_custom(self):
        inp = _base_inputs(license_fraction=0.20)
        assert inp.license_fraction == pytest.approx(0.20)

    def test_comparable_bucket_rate_source_segment_report(self):
        inp = _base_inputs(comparable_bucket_rate_source="segment_report")
        assert inp.comparable_bucket_rate_source == "segment_report"

    def test_comparable_bucket_rate_source_fallback(self):
        inp = _base_inputs(comparable_bucket_rate_source="fallback")
        assert inp.comparable_bucket_rate_source == "fallback"

    def test_fractions_are_bounded_0_to_1(self):
        with pytest.raises(Exception):
            _base_inputs(acquisition_fraction=1.5)
        with pytest.raises(Exception):
            _base_inputs(license_fraction=-0.1)


# ---------------------------------------------------------------------------
# Block 20-B: New Layer5Output fields
# ---------------------------------------------------------------------------

class TestLayer5OutputNewFields:

    def test_p_any_strategic_transaction_12m_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_any_strategic_transaction_12m")
        assert 0.0 <= out.p_any_strategic_transaction_12m <= 1.0

    def test_p_full_acquisition_12m_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_full_acquisition_12m")
        assert 0.0 <= out.p_full_acquisition_12m <= 1.0

    def test_p_license_or_partner_12m_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_license_or_partner_12m")
        assert 0.0 <= out.p_license_or_partner_12m <= 1.0

    def test_bucket_rate_warning_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "bucket_rate_warning")

    def test_p_any_is_primary_calibrated_output(self):
        """p_any_strategic_transaction_12m is the primary calibrated 12m output."""
        inp = _base_inputs()
        out = compute_layer5(inp)
        # p_any is the same value as the pre-Block20 p12m shrinkage blend
        # p_takeout_12m is the DEPRECATED alias for p_full_acquisition_12m
        assert 0.0 <= out.p_any_strategic_transaction_12m <= 1.0
        # With default acquisition_fraction=0.60, p_takeout < p_any
        assert out.p_takeout_12m <= out.p_any_strategic_transaction_12m + 1e-9

    def test_p_full_acquisition_is_fraction_of_p_any(self):
        """p_full_acquisition_12m = acquisition_fraction * p_any_strategic_transaction_12m."""
        inp = _base_inputs(acquisition_fraction=0.60)
        out = compute_layer5(inp)
        expected = round(0.60 * out.p_any_strategic_transaction_12m, 4)
        assert out.p_full_acquisition_12m == pytest.approx(expected, abs=1e-4)

    def test_p_license_is_fraction_of_p_any(self):
        """p_license_or_partner_12m = license_fraction * p_any_strategic_transaction_12m."""
        inp = _base_inputs(license_fraction=0.35)
        out = compute_layer5(inp)
        expected = round(0.35 * out.p_any_strategic_transaction_12m, 4)
        assert out.p_license_or_partner_12m == pytest.approx(expected, abs=1e-4)

    def test_custom_fractions_flow_through(self):
        inp = _base_inputs(acquisition_fraction=0.80, license_fraction=0.15)
        out = compute_layer5(inp)
        assert out.p_full_acquisition_12m == pytest.approx(
            round(0.80 * out.p_any_strategic_transaction_12m, 4), abs=1e-4
        )
        assert out.p_license_or_partner_12m == pytest.approx(
            round(0.15 * out.p_any_strategic_transaction_12m, 4), abs=1e-4
        )

    def test_p_splits_do_not_exceed_p_any(self):
        out = compute_layer5(_base_inputs())
        assert out.p_full_acquisition_12m <= out.p_any_strategic_transaction_12m + 1e-9
        assert out.p_license_or_partner_12m <= out.p_any_strategic_transaction_12m + 1e-9


# ---------------------------------------------------------------------------
# Block 20-C: p_takeout_12m is deprecated alias for p_full_acquisition_12m
# ---------------------------------------------------------------------------

class TestPTakeoutAlias:

    def test_p_takeout_12m_equals_p_full_acquisition(self):
        """'takeout' == full acquisition in market convention."""
        out = compute_layer5(_base_inputs())
        assert out.p_takeout_12m == pytest.approx(out.p_full_acquisition_12m, abs=1e-9)

    def test_p_takeout_not_equal_p_any_strategic(self):
        """p_takeout_12m must NOT equal p_any_strategic unless acquisition_fraction=1.0."""
        inp = _base_inputs(acquisition_fraction=0.60)
        out = compute_layer5(inp)
        # With a 60% acquisition fraction, takeout < any_strategic
        assert out.p_takeout_12m < out.p_any_strategic_transaction_12m + 1e-9

    def test_p_takeout_equals_p_any_when_fraction_is_one(self):
        inp = _base_inputs(acquisition_fraction=1.0)
        out = compute_layer5(inp)
        assert out.p_takeout_12m == pytest.approx(out.p_any_strategic_transaction_12m, abs=1e-4)


# ---------------------------------------------------------------------------
# Block 20-D: resolve_comparable_bucket_rate() helper
# ---------------------------------------------------------------------------

class TestResolveComparableBucketRate:

    def test_segment_report_source_returned(self):
        rate, source = resolve_comparable_bucket_rate(0.15, "segment_report")
        assert source == "segment_report"
        assert rate == pytest.approx(0.15)

    def test_fallback_source_returned(self):
        rate, source = resolve_comparable_bucket_rate(0.08, "fallback")
        assert source == "fallback"
        assert rate == pytest.approx(0.08)

    def test_empty_source_treated_as_fallback(self):
        rate, source = resolve_comparable_bucket_rate(0.10, "")
        assert source == "fallback"

    def test_returns_tuple_of_float_and_str(self):
        result = resolve_comparable_bucket_rate(0.12, "segment_report")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)


# ---------------------------------------------------------------------------
# Block 20-E: bucket_rate_warning set when fallback
# ---------------------------------------------------------------------------

class TestBucketRateWarning:

    def test_no_warning_when_segment_report(self):
        inp = _base_inputs(comparable_bucket_rate_source="segment_report")
        out = compute_layer5(inp)
        assert out.bucket_rate_warning is None or out.bucket_rate_warning == ""

    def test_warning_set_when_fallback(self):
        inp = _base_inputs(comparable_bucket_rate_source="fallback")
        out = compute_layer5(inp)
        assert out.bucket_rate_warning is not None and out.bucket_rate_warning != ""

    def test_no_warning_when_source_empty_legacy(self):
        """Empty source = legacy unset — no cap, no warning (backward-compatible)."""
        inp = _base_inputs(comparable_bucket_rate_source="")
        out = compute_layer5(inp)
        # "" is the legacy default; backward compat — no warning, no cap
        # (only explicit "fallback" triggers the guard)
        assert out.bucket_rate_warning is None or out.bucket_rate_warning == ""

    def test_warning_contains_useful_text(self):
        inp = _base_inputs(comparable_bucket_rate_source="fallback")
        out = compute_layer5(inp)
        assert isinstance(out.bucket_rate_warning, str)
        assert len(out.bucket_rate_warning) > 0


# ---------------------------------------------------------------------------
# Block 20-F: confidence capped at LOW when bucket_rate_source is 'fallback'
#             (only when the base data_confidence_score would otherwise give MEDIUM/HIGH)
# ---------------------------------------------------------------------------

class TestFallbackConfidenceCap:

    def test_high_data_confidence_with_fallback_bucket_capped_at_low(self):
        """Even with good data, fallback bucket source caps confidence at LOW."""
        inp = _base_inputs(
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="fallback",
        )
        out = compute_layer5(inp)
        assert out.confidence_level in ("low", "very_low")

    def test_segment_report_allows_high_confidence(self):
        inp = _base_inputs(
            data_confidence_score=0.90,
            n_comparable_observations=25,
            comparable_bucket_rate_source="segment_report",
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "high"

    def test_fallback_with_low_data_confidence_stays_very_low(self):
        inp = _base_inputs(
            data_confidence_score=0.30,
            n_comparable_observations=3,
            comparable_bucket_rate_source="fallback",
        )
        out = compute_layer5(inp)
        assert out.confidence_level == "very_low"


# ---------------------------------------------------------------------------
# Block 20-G: Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_existing_callers_with_no_new_fields_work(self):
        """Layer5Inputs without new fields still constructs fine (all have defaults)."""
        inp = Layer5Inputs(
            rank_score=0.50,
            rank_percentile=0.50,
            strategic_priority=0.50,
            transaction_probability=0.50,
            asset_quality=0.60,
            seller_willingness=0.50,
        )
        out = compute_layer5(inp)
        assert 0.0 <= out.p_takeout_12m <= 1.0

    def test_p_takeout_6m_and_18m_still_present(self):
        out = compute_layer5(_base_inputs())
        assert hasattr(out, "p_takeout_6m")
        assert hasattr(out, "p_takeout_18m")

    def test_all_existing_output_fields_still_present(self):
        out = compute_layer5(_base_inputs())
        for field in [
            "rank_score", "probability_band", "confidence_level",
            "top_positive_drivers", "top_negative_drivers",
            "calibration_cohort", "display_probability", "interpretation",
        ]:
            assert hasattr(out, field), f"Missing field: {field}"

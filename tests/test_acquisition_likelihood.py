from __future__ import annotations

import math

import pytest

from bve.intelligence.acquisition_likelihood import (
    AcquisitionLikelihoodFeatures,
    STAGE_A_FEATURE_WEIGHTS,
    _affordability_score,
    _catalyst_proximity_score,
    compute_acquisition_likelihood,
    features_from_calibration_row,
)


# ---------------------------------------------------------------------------
# Feature weight sanity
# ---------------------------------------------------------------------------


def test_stage_a_feature_weights_sum_to_one():
    total = sum(STAGE_A_FEATURE_WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_stage_a_feature_weights_are_positive():
    assert all(v > 0 for v in STAGE_A_FEATURE_WEIGHTS.values())


# ---------------------------------------------------------------------------
# _catalyst_proximity_score
# ---------------------------------------------------------------------------


def test_catalyst_proximity_none_returns_zero():
    assert _catalyst_proximity_score(None) == 0.0


def test_catalyst_proximity_zero_or_negative_returns_zero():
    assert _catalyst_proximity_score(0) == 0.0
    assert _catalyst_proximity_score(-10) == 0.0


def test_catalyst_proximity_beyond_730_days_returns_zero():
    assert _catalyst_proximity_score(731) == 0.0
    assert _catalyst_proximity_score(1000) == 0.0


def test_catalyst_proximity_peaks_near_60_days():
    score_60 = _catalyst_proximity_score(60)
    score_30 = _catalyst_proximity_score(30)
    score_180 = _catalyst_proximity_score(180)

    # Peak is at 60 days
    assert score_60 == pytest.approx(1.0, abs=1e-6)
    assert score_30 < score_60
    assert score_180 < score_60


def test_catalyst_proximity_is_symmetric_around_peak():
    # The Gaussian is centred at 60, so distance of 30 on each side should give same score
    score_below = _catalyst_proximity_score(60 - 30)
    score_above = _catalyst_proximity_score(60 + 30)
    assert abs(score_below - score_above) < 1e-6


# ---------------------------------------------------------------------------
# _affordability_score
# ---------------------------------------------------------------------------


def test_affordability_none_returns_neutral():
    assert _affordability_score(None) == 0.5


def test_affordability_sweet_spot_returns_one():
    assert _affordability_score(500.0) == 1.0
    assert _affordability_score(4999.0) == 1.0


def test_affordability_tiny_company_returns_low_neutral():
    # Below sweet-spot floor — possible but not ideal
    assert _affordability_score(100.0) == 0.5


def test_affordability_mega_cap_returns_zero():
    assert _affordability_score(15_000.0) == 0.0
    assert _affordability_score(20_000.0) == 0.0


def test_affordability_tapers_linearly_between_sweet_spot_and_mega_cap():
    # At midpoint between 5000 and 15000 (i.e., 10000), score should be 0.5
    score = _affordability_score(10_000.0)
    assert abs(score - 0.5) < 0.01


# ---------------------------------------------------------------------------
# compute_acquisition_likelihood
# ---------------------------------------------------------------------------


def test_compute_acquisition_likelihood_all_zeros_returns_zero():
    features = AcquisitionLikelihoodFeatures()
    score = compute_acquisition_likelihood(features)
    assert score == 0.0


def test_compute_acquisition_likelihood_all_ones_with_sweet_spot_ev_returns_near_one():
    features = AcquisitionLikelihoodFeatures(
        de_risking_stage_score=1.0,
        scarcity_score=1.0,
        capital_vulnerability_score=1.0,
        ta_heat_score=1.0,
        valuation_discount_score=1.0,
        days_to_catalyst=60,          # peak proximity score
        enterprise_value_millions=1000.0,  # sweet-spot → affordability=1.0
    )
    score = compute_acquisition_likelihood(features)
    # All features = 1.0 × weights summing to 1.0 × affordability 1.0 → 1.0
    assert score == pytest.approx(1.0, abs=1e-6)


def test_compute_acquisition_likelihood_mega_cap_zeroes_out_score():
    features = AcquisitionLikelihoodFeatures(
        de_risking_stage_score=1.0,
        scarcity_score=1.0,
        capital_vulnerability_score=1.0,
        ta_heat_score=1.0,
        valuation_discount_score=1.0,
        days_to_catalyst=60,
        enterprise_value_millions=15_000.0,  # mega-cap → affordability=0.0
    )
    score = compute_acquisition_likelihood(features)
    assert score == 0.0


def test_compute_acquisition_likelihood_is_bounded_between_0_and_1():
    for ev in [None, 50.0, 1000.0, 10_000.0, 20_000.0]:
        for days in [None, 10, 60, 200, 800]:
            features = AcquisitionLikelihoodFeatures(
                de_risking_stage_score=0.8,
                scarcity_score=0.7,
                capital_vulnerability_score=0.6,
                ta_heat_score=0.5,
                valuation_discount_score=0.4,
                days_to_catalyst=days,
                enterprise_value_millions=ev,
            )
            score = compute_acquisition_likelihood(features)
            assert 0.0 <= score <= 1.0, f"Out of range for ev={ev}, days={days}: {score}"


def test_compute_acquisition_likelihood_higher_de_risking_increases_score():
    base = AcquisitionLikelihoodFeatures(
        de_risking_stage_score=0.3,
        enterprise_value_millions=1000.0,
    )
    high = AcquisitionLikelihoodFeatures(
        de_risking_stage_score=0.9,
        enterprise_value_millions=1000.0,
    )
    assert compute_acquisition_likelihood(high) > compute_acquisition_likelihood(base)


# ---------------------------------------------------------------------------
# features_from_calibration_row
# ---------------------------------------------------------------------------


def test_features_from_calibration_row_extracts_known_fields():
    class FakeRow:
        de_risking_stage_score = 0.75
        scarcity_score = 0.60
        capital_vulnerability_score = 0.50
        ta_heat_score = 0.40
        valuation_discount_score = 0.30
        days_to_catalyst = 45
        enterprise_value_millions = 2000.0
        ev_millions = None  # secondary EV field (not used when primary is set)

    features = features_from_calibration_row(FakeRow())

    assert features.de_risking_stage_score == pytest.approx(0.75)
    assert features.scarcity_score == pytest.approx(0.60)
    assert features.capital_vulnerability_score == pytest.approx(0.50)
    assert features.ta_heat_score == pytest.approx(0.40)
    assert features.valuation_discount_score == pytest.approx(0.30)
    assert features.days_to_catalyst == 45
    assert features.enterprise_value_millions == pytest.approx(2000.0)


def test_features_from_calibration_row_defaults_missing_fields():
    class EmptyRow:
        pass

    features = features_from_calibration_row(EmptyRow())

    assert features.de_risking_stage_score == 0.0
    assert features.scarcity_score == 0.0
    assert features.capital_vulnerability_score == 0.0
    assert features.ta_heat_score == 0.0
    assert features.valuation_discount_score == 0.0
    assert features.days_to_catalyst is None
    assert features.enterprise_value_millions is None


def test_features_from_calibration_row_falls_back_to_ev_millions():
    class RowWithEvMillions:
        ev_millions = 3000.0
        enterprise_value_millions = None

    features = features_from_calibration_row(RowWithEvMillions())
    assert features.enterprise_value_millions == pytest.approx(3000.0)

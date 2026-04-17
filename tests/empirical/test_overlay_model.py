"""
Tests for bve.empirical.overlay_model — OverlayArtifact, fit_overlay,
fit_overlay_time_split, and the internal logistic fitter.
"""
import json
import math
import pytest

from bve.empirical.overlay_model import (
    OverlayArtifact,
    fit_overlay,
    fit_overlay_time_split,
    _fit_logistic_l2,
    _build_arrays,
)
from bve.empirical.features import FEATURE_NAMES, N_FEATURES, MIN_OVERLAY_RECORDS
from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.pos_outcome import POSOutcomeRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(
    phase="phase_2",
    success=True,
    moa="novel",
    bio=False,
    endpoint="surrogate_validated",
    safety="minor",
    competition="moderate",
    outcome_date=None,
    sponsor="AcmeBio",
    idx=0,
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{idx}-{phase}-{moa}-{bio}",
        sponsor=sponsor,
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        moa_precedent=moa,
        biomarker_selected=bio,
        endpoint_type=endpoint,
        safety_profile=safety,
        competitive_pressure=competition,
        success=success,
        outcome_raw="advanced" if success else "failed",
        outcome_date=outcome_date,
    )


def _make_records(n: int = 30, alternating_success: bool = True) -> list[POSOutcomeRecord]:
    """Generate n synthetic records with alternating success."""
    recs = []
    phases = ["phase_1", "phase_2", "phase_3", "nda_bla"]
    for i in range(n):
        recs.append(_rec(
            phase=phases[i % len(phases)],
            success=(i % 2 == 0) if alternating_success else True,
            idx=i,
        ))
    return recs


def _make_base_table(records: list[POSOutcomeRecord]) -> BaseRateTable:
    return BaseRateTable(records, smoothing_alpha=1.0)


def _make_artifact(n: int = 30) -> tuple[OverlayArtifact, BaseRateTable, list[POSOutcomeRecord]]:
    recs = _make_records(n)
    table = _make_base_table(recs)
    artifact = fit_overlay(recs, table, alpha=1.0)
    return artifact, table, recs


# ---------------------------------------------------------------------------
# _fit_logistic_l2 — internal optimizer
# ---------------------------------------------------------------------------

class TestFitLogisticL2:
    def test_returns_correct_shapes(self):
        import numpy as np
        X = np.zeros((20, N_FEATURES))
        y = np.array([1.0, 0.0] * 10)
        offsets = np.zeros(20)
        coeffs, intercept, converged = _fit_logistic_l2(X, y, offsets, alpha=1.0)
        assert len(coeffs) == N_FEATURES
        assert isinstance(intercept, float)
        assert isinstance(converged, bool)

    def test_all_finite_coefficients(self):
        import numpy as np
        recs = _make_records(20)
        table = _make_base_table(recs)
        X, y, offsets, _ = _build_arrays(recs, table)
        coeffs, intercept, converged = _fit_logistic_l2(X, y, offsets, alpha=1.0)
        assert all(math.isfinite(c) for c in coeffs)
        assert math.isfinite(intercept)

    def test_all_success_pushes_intercept_positive(self):
        """When all outcomes are success, intercept should be pushed positive."""
        import numpy as np
        X = np.zeros((20, N_FEATURES))
        y = np.ones(20)
        offsets = np.zeros(20)  # base rate = 0.5
        coeffs, intercept, converged = _fit_logistic_l2(X, y, offsets, alpha=1.0)
        assert intercept > 0.0

    def test_all_failure_pushes_intercept_negative(self):
        import numpy as np
        X = np.zeros((20, N_FEATURES))
        y = np.zeros(20)
        offsets = np.zeros(20)
        coeffs, intercept, converged = _fit_logistic_l2(X, y, offsets, alpha=1.0)
        assert intercept < 0.0

    def test_higher_alpha_shrinks_coefficients(self):
        """Higher L2 regularization → smaller L1 norm on beta (excl. intercept)."""
        import numpy as np
        # Use records with varied features so the feature matrix has signal
        recs = []
        for i in range(30):
            recs.append(_rec(
                phase=["phase_1", "phase_2", "phase_3", "nda_bla"][i % 4],
                success=(i % 2 == 0),
                moa="validated" if i % 3 == 0 else ("novel" if i % 3 == 1 else "partial"),
                bio=(i % 2 == 0),
                safety="clean" if i % 4 == 0 else ("concerning" if i % 4 == 2 else "minor"),
                competition="low" if i % 3 == 0 else ("high" if i % 3 == 1 else "moderate"),
                idx=i,
            ))
        table = _make_base_table(recs)
        X, y, offsets, _ = _build_arrays(recs, table)
        coeffs_low, _, _ = _fit_logistic_l2(X, y, offsets, alpha=0.001)
        coeffs_high, _, _ = _fit_logistic_l2(X, y, offsets, alpha=1000.0)
        norm_low = sum(abs(c) for c in coeffs_low)
        norm_high = sum(abs(c) for c in coeffs_high)
        # High regularization should shrink coefficients significantly
        assert norm_high <= norm_low

    def test_converged_flag_is_bool(self):
        import numpy as np
        X = np.zeros((15, N_FEATURES))
        y = np.array([1.0, 0.0] * 7 + [1.0])
        offsets = np.full(15, 0.5)
        _, _, converged = _fit_logistic_l2(X, y, offsets, alpha=1.0)
        assert isinstance(converged, bool)


# ---------------------------------------------------------------------------
# fit_overlay — basic contract
# ---------------------------------------------------------------------------

class TestFitOverlay:
    def test_returns_overlay_artifact(self):
        artifact, _, _ = _make_artifact(30)
        assert isinstance(artifact, OverlayArtifact)

    def test_feature_names_match(self):
        artifact, _, _ = _make_artifact(30)
        assert artifact.feature_names == FEATURE_NAMES

    def test_n_coefficients_matches_n_features(self):
        artifact, _, _ = _make_artifact(30)
        assert len(artifact.coefficients) == N_FEATURES

    def test_n_train_recorded(self):
        recs = _make_records(25)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table, alpha=1.0)
        assert artifact.n_train == 25

    def test_regularization_alpha_stored(self):
        recs = _make_records(20)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table, alpha=2.5)
        assert artifact.regularization_alpha == 2.5

    def test_train_brier_is_finite(self):
        artifact, _, _ = _make_artifact(30)
        assert math.isfinite(artifact.train_brier_base)
        assert math.isfinite(artifact.train_brier_overlay)

    def test_train_brier_in_valid_range(self):
        artifact, _, _ = _make_artifact(30)
        assert 0.0 <= artifact.train_brier_base <= 1.0
        assert 0.0 <= artifact.train_brier_overlay <= 1.0

    def test_train_ece_in_valid_range(self):
        artifact, _, _ = _make_artifact(30)
        assert 0.0 <= artifact.train_ece_base <= 1.0
        assert 0.0 <= artifact.train_ece_overlay <= 1.0

    def test_n_feature_nonzero_keys(self):
        artifact, _, _ = _make_artifact(30)
        assert set(artifact.n_feature_nonzero.keys()) == set(FEATURE_NAMES)

    def test_n_feature_nonzero_values_are_non_negative_ints(self):
        artifact, _, _ = _make_artifact(30)
        for name, count in artifact.n_feature_nonzero.items():
            assert isinstance(count, int)
            assert count >= 0

    def test_raises_when_fewer_than_min_records(self):
        recs = _make_records(MIN_OVERLAY_RECORDS - 1)
        table = _make_base_table(recs)
        with pytest.raises(ValueError, match=str(MIN_OVERLAY_RECORDS)):
            fit_overlay(recs, table)

    def test_exactly_min_records_does_not_raise(self):
        recs = _make_records(MIN_OVERLAY_RECORDS)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table)
        assert artifact.n_train == MIN_OVERLAY_RECORDS

    def test_cutoff_year_stored(self):
        recs = _make_records(20)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table, cutoff_year=2020)
        assert artifact.cutoff_year == 2020

    def test_no_cutoff_year_defaults_to_none(self):
        recs = _make_records(20)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table)
        assert artifact.cutoff_year is None

    def test_test_metrics_none_when_no_test_records(self):
        artifact, _, _ = _make_artifact(30)
        assert artifact.n_test is None
        assert artifact.test_brier_base is None
        assert artifact.test_brier_overlay is None

    def test_test_metrics_populated_when_test_records_provided(self):
        train = _make_records(20)
        test = _make_records(10)
        table = _make_base_table(train)
        artifact = fit_overlay(train, table, test_records=test)
        assert artifact.n_test == 10
        assert artifact.test_brier_base is not None
        assert artifact.test_brier_overlay is not None
        assert artifact.test_ece_base is not None
        assert artifact.test_ece_overlay is not None

    def test_test_brier_in_valid_range_when_populated(self):
        train = _make_records(20)
        test = _make_records(10)
        table = _make_base_table(train)
        artifact = fit_overlay(train, table, test_records=test)
        assert 0.0 <= artifact.test_brier_base <= 1.0
        assert 0.0 <= artifact.test_brier_overlay <= 1.0

    def test_all_success_records_produces_finite_artifact(self):
        """Edge case: all outcomes are success."""
        recs = _make_records(20, alternating_success=False)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table)
        assert all(math.isfinite(c) for c in artifact.coefficients)

    def test_varied_features_populate_nonzero_counts(self):
        recs = []
        for i in range(15):
            recs.append(_rec(
                phase="phase_2",
                success=(i % 2 == 0),
                moa="validated" if i % 3 == 0 else "novel",
                bio=True if i % 2 == 0 else False,
                idx=i,
            ))
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table)
        # At least moa_validated and biomarker_selected should have nonzero counts
        assert artifact.n_feature_nonzero["moa_validated"] > 0
        assert artifact.n_feature_nonzero["biomarker_selected"] > 0


# ---------------------------------------------------------------------------
# OverlayArtifact.apply
# ---------------------------------------------------------------------------

class TestOverlayArtifactApply:
    def test_returns_float_in_unit_interval(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        p = artifact.apply(fv, base_log_odds=0.0)
        assert 0.0 < p < 1.0

    def test_higher_base_log_odds_gives_higher_prob(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        p_low = artifact.apply(fv, base_log_odds=-2.0)
        p_high = artifact.apply(fv, base_log_odds=2.0)
        assert p_high > p_low

    def test_all_zeros_feature_vector_uses_only_base_and_intercept(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        # Result should be sigmoid(base_lo + intercept)
        from scipy.special import expit
        expected = round(float(expit(1.0 + artifact.intercept)), 4)
        actual = artifact.apply(fv, base_log_odds=1.0)
        assert abs(actual - expected) < 1e-4

    def test_mismatched_feature_vector_raises(self):
        artifact, _, _ = _make_artifact(30)
        with pytest.raises(ValueError, match="length"):
            artifact.apply([0.0, 1.0], base_log_odds=0.0)

    def test_result_is_rounded_to_4_places(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        p = artifact.apply(fv, base_log_odds=0.0)
        # 4 decimal places: str representation should have at most 4 decimal digits
        assert round(p, 4) == p

    def test_extreme_positive_base_log_odds_returns_close_to_one(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        p = artifact.apply(fv, base_log_odds=20.0)
        assert p > 0.99

    def test_extreme_negative_base_log_odds_returns_close_to_zero(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        p = artifact.apply(fv, base_log_odds=-20.0)
        assert p < 0.01

    def test_positive_coefficient_increases_probability(self):
        """A positive coefficient for an active feature should increase prob."""
        artifact, _, _ = _make_artifact(30)
        fv_off = [0.0] * N_FEATURES
        fv_on = [0.0] * N_FEATURES
        # Find a feature with a positive coefficient
        pos_idx = next(
            (i for i, c in enumerate(artifact.coefficients) if c > 0), None
        )
        if pos_idx is not None:
            fv_on[pos_idx] = 1.0
            p_off = artifact.apply(fv_off, base_log_odds=0.0)
            p_on = artifact.apply(fv_on, base_log_odds=0.0)
            assert p_on >= p_off


# ---------------------------------------------------------------------------
# OverlayArtifact.feature_contributions + net_log_odds_delta
# ---------------------------------------------------------------------------

class TestOverlayArtifactContributions:
    def test_feature_contributions_keys(self):
        artifact, _, _ = _make_artifact(30)
        fv = [1.0] * N_FEATURES
        contribs = artifact.feature_contributions(fv)
        assert set(contribs.keys()) == set(FEATURE_NAMES)

    def test_feature_contributions_zero_when_feature_off(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        contribs = artifact.feature_contributions(fv)
        assert all(v == 0.0 for v in contribs.values())

    def test_feature_contributions_equals_fv_times_coeff(self):
        artifact, _, _ = _make_artifact(30)
        fv = [1.0 if i % 2 == 0 else 0.0 for i in range(N_FEATURES)]
        contribs = artifact.feature_contributions(fv)
        for i, name in enumerate(FEATURE_NAMES):
            expected = round(fv[i] * artifact.coefficients[i], 6)
            assert contribs[name] == expected

    def test_net_log_odds_delta_is_intercept_plus_sum_of_contributions(self):
        artifact, _, _ = _make_artifact(30)
        fv = [1.0, 0.0] * (N_FEATURES // 2) + [0.0] * (N_FEATURES % 2)
        delta = artifact.net_log_odds_delta(fv)
        contribs = artifact.feature_contributions(fv)
        expected = round(artifact.intercept + sum(contribs.values()), 6)
        assert abs(delta - expected) < 1e-5

    def test_net_log_odds_delta_all_zeros_returns_intercept(self):
        artifact, _, _ = _make_artifact(30)
        fv = [0.0] * N_FEATURES
        delta = artifact.net_log_odds_delta(fv)
        assert abs(delta - round(artifact.intercept, 6)) < 1e-5


# ---------------------------------------------------------------------------
# OverlayArtifact.to_dict / from_dict — JSON roundtrip
# ---------------------------------------------------------------------------

class TestOverlayArtifactRoundtrip:
    def test_to_dict_is_json_serializable(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        # Should not raise
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

    def test_from_dict_restores_feature_names(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.feature_names == artifact.feature_names

    def test_from_dict_restores_coefficients(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.coefficients == artifact.coefficients

    def test_from_dict_restores_intercept(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.intercept == artifact.intercept

    def test_from_dict_restores_train_brier(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.train_brier_base == artifact.train_brier_base
        assert restored.train_brier_overlay == artifact.train_brier_overlay

    def test_from_dict_restores_n_train(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.n_train == artifact.n_train

    def test_from_dict_apply_matches_original(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        fv = [0.0] * N_FEATURES
        assert artifact.apply(fv, 0.0) == restored.apply(fv, 0.0)

    def test_from_dict_handles_optional_none_test_metrics(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        assert d["n_test"] is None
        restored = OverlayArtifact.from_dict(d)
        assert restored.n_test is None
        assert restored.test_brier_base is None

    def test_from_dict_restores_test_metrics_when_present(self):
        train = _make_records(20)
        test = _make_records(10)
        table = _make_base_table(train)
        artifact = fit_overlay(train, table, test_records=test)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.n_test == artifact.n_test
        assert restored.test_brier_base == artifact.test_brier_base
        assert restored.test_brier_overlay == artifact.test_brier_overlay

    def test_roundtrip_preserves_converged_flag(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.converged == artifact.converged

    def test_roundtrip_preserves_n_feature_nonzero(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.n_feature_nonzero == artifact.n_feature_nonzero

    def test_roundtrip_preserves_cutoff_year_none(self):
        artifact, _, _ = _make_artifact(30)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.cutoff_year is None

    def test_roundtrip_preserves_cutoff_year_int(self):
        recs = _make_records(20)
        table = _make_base_table(recs)
        artifact = fit_overlay(recs, table, cutoff_year=2019)
        d = artifact.to_dict()
        restored = OverlayArtifact.from_dict(d)
        assert restored.cutoff_year == 2019


# ---------------------------------------------------------------------------
# OverlayArtifact.coefficient_summary
# ---------------------------------------------------------------------------

class TestCoefficientSummary:
    def test_returns_string(self):
        artifact, _, _ = _make_artifact(30)
        s = artifact.coefficient_summary()
        assert isinstance(s, str)

    def test_contains_feature_names(self):
        artifact, _, _ = _make_artifact(30)
        s = artifact.coefficient_summary()
        for name in FEATURE_NAMES:
            assert name in s

    def test_contains_intercept(self):
        artifact, _, _ = _make_artifact(30)
        s = artifact.coefficient_summary()
        assert "intercept" in s.lower()

    def test_contains_alpha_and_n_train(self):
        artifact, _, _ = _make_artifact(30)
        s = artifact.coefficient_summary()
        assert "alpha=" in s or "alpha" in s
        assert "n_train=" in s or "n_train" in s

    def test_contains_train_brier(self):
        artifact, _, _ = _make_artifact(30)
        s = artifact.coefficient_summary()
        assert "Brier" in s

    def test_test_brier_appears_when_test_metrics_populated(self):
        train = _make_records(20)
        test = _make_records(10)
        table = _make_base_table(train)
        artifact = fit_overlay(train, table, test_records=test)
        s = artifact.coefficient_summary()
        # Should show both train and test brier
        assert s.count("Brier") >= 2

    def test_is_multiline(self):
        artifact, _, _ = _make_artifact(30)
        s = artifact.coefficient_summary()
        assert "\n" in s


# ---------------------------------------------------------------------------
# fit_overlay_time_split
# ---------------------------------------------------------------------------

class TestFitOverlayTimeSplit:
    def _make_temporal_records(self) -> list[POSOutcomeRecord]:
        recs = []
        for i in range(30):
            year = 2015 + (i % 10)
            recs.append(_rec(
                phase=["phase_1", "phase_2", "phase_3", "nda_bla"][i % 4],
                success=(i % 2 == 0),
                outcome_date=str(year),
                idx=i,
            ))
        return recs

    def test_returns_overlay_artifact(self):
        recs = self._make_temporal_records()
        table = _make_base_table(recs)
        artifact = fit_overlay_time_split(recs, table, cutoff_year=2019)
        assert isinstance(artifact, OverlayArtifact)

    def test_cutoff_year_stored(self):
        recs = self._make_temporal_records()
        table = _make_base_table(recs)
        artifact = fit_overlay_time_split(recs, table, cutoff_year=2019)
        assert artifact.cutoff_year == 2019

    def test_test_metrics_populated_when_test_fold_exists(self):
        recs = self._make_temporal_records()
        table = _make_base_table(recs)
        artifact = fit_overlay_time_split(recs, table, cutoff_year=2019)
        # Records from 2020-2024 should be in test
        if artifact.n_test and artifact.n_test > 0:
            assert artifact.test_brier_base is not None
            assert artifact.test_brier_overlay is not None

    def test_raises_when_not_enough_train_records(self):
        """Only records with year <= 2000, giving 0 train records."""
        recs = self._make_temporal_records()  # years 2015-2024
        table = _make_base_table(recs)
        # cutoff_year=2010 → all records are in test (yr > 2010), no train
        with pytest.raises(ValueError, match="training records"):
            fit_overlay_time_split(recs, table, cutoff_year=2010)

    def test_records_with_no_date_go_to_train(self):
        """Records with outcome_date=None should be assigned to train."""
        recs_no_date = [_rec(phase="phase_2", success=(i % 2 == 0), idx=i)
                        for i in range(15)]
        recs_future = [_rec(phase="phase_3", success=(i % 2 == 0),
                           outcome_date="2025", idx=100+i)
                       for i in range(5)]
        all_recs = recs_no_date + recs_future
        table = _make_base_table(all_recs)
        # None-dated records go to train; 2025 > 2020 goes to test
        artifact = fit_overlay_time_split(all_recs, table, cutoff_year=2020)
        assert artifact.n_train == 15

    def test_alpha_stored_in_artifact(self):
        recs = self._make_temporal_records()
        table = _make_base_table(recs)
        artifact = fit_overlay_time_split(recs, table, cutoff_year=2019, alpha=2.0)
        assert artifact.regularization_alpha == 2.0

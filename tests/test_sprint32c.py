"""
Sprint 32C — Enhanced Gaussian copula correlation rules tests.

Covers:
- ENHANCED_CORRELATION: all expected variables present
- Positive pairs: sampled rank correlation in expected direction (> 0)
- Negative pairs: sampled rank correlation in expected direction (< 0)
- Independent variables (discount_rate, rd_cost_mult) have near-zero sample r
- ENHANCED_CORRELATION matrix is positive definite (Cholesky succeeds)
- validate_correlation_consistency(): warns when driver-based + peak_sales in spec
- validate_correlation_consistency(): no warning in SIMPLE mode
- validate_correlation_consistency(): no warning when peak_sales not in spec
- DEFAULT_CORRELATION backward compatibility preserved
"""
import warnings
import numpy as np
import pytest
from scipy.stats import spearmanr

from bve.models.correlations import (
    ENHANCED_CORRELATION,
    DEFAULT_CORRELATION,
    CorrelationSpec,
    correlated_uniform_samples,
    validate_correlation_consistency,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sample_rank_corr(spec: CorrelationSpec, var_a: str, var_b: str,
                      n: int = 5000, seed: int = 0) -> float:
    """Return Spearman rank correlation between var_a and var_b."""
    rng = np.random.default_rng(seed)
    samples = correlated_uniform_samples(spec, n, rng)
    r, _ = spearmanr(samples[var_a], samples[var_b])
    return float(r)


# ---------------------------------------------------------------------------
# ENHANCED_CORRELATION structure
# ---------------------------------------------------------------------------

class TestEnhancedCorrelationStructure:
    def test_all_expected_variables_present(self):
        expected = {
            "phase_3_success_prob", "label_breadth_mult",
            "eligible_patients_mult", "peak_penetration_mult",
            "payer_access_fraction", "competitor_share_mult",
            "prior_auth_burden_delta", "discount_rate", "rd_cost_mult",
        }
        assert expected == set(ENHANCED_CORRELATION.variables)

    def test_matrix_is_positive_definite(self):
        """Cholesky must succeed — all correlations are internally consistent."""
        L = ENHANCED_CORRELATION.cholesky()
        assert L.shape == (9, 9)

    def test_diagonal_is_one(self):
        mat = ENHANCED_CORRELATION.build_matrix()
        assert np.allclose(np.diag(mat), 1.0)

    def test_matrix_is_symmetric(self):
        mat = ENHANCED_CORRELATION.build_matrix()
        assert np.allclose(mat, mat.T)

    def test_all_correlations_in_minus_one_to_one(self):
        mat = ENHANCED_CORRELATION.build_matrix()
        assert np.all(mat >= -1.0) and np.all(mat <= 1.0)


# ---------------------------------------------------------------------------
# Positive correlations (clinical data → commercial chain)
# ---------------------------------------------------------------------------

class TestPositiveCorrelations:
    def test_phase3_success_label_breadth_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "phase_3_success_prob", "label_breadth_mult")
        assert r > 0.10, f"Expected positive r, got {r:.3f}"

    def test_phase3_success_penetration_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "phase_3_success_prob", "peak_penetration_mult")
        assert r > 0.10, f"Expected positive r, got {r:.3f}"

    def test_phase3_success_payer_access_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "phase_3_success_prob", "payer_access_fraction")
        assert r > 0.05, f"Expected positive r, got {r:.3f}"

    def test_label_breadth_eligible_patients_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "label_breadth_mult", "eligible_patients_mult")
        assert r > 0.20, f"Expected positive r, got {r:.3f}"

    def test_label_breadth_penetration_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "label_breadth_mult", "peak_penetration_mult")
        assert r > 0.10, f"Expected positive r, got {r:.3f}"

    def test_eligible_patients_penetration_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "eligible_patients_mult", "peak_penetration_mult")
        assert r > 0.05, f"Expected positive r, got {r:.3f}"

    def test_penetration_payer_access_positive(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "peak_penetration_mult", "payer_access_fraction")
        assert r > 0.10, f"Expected positive r, got {r:.3f}"


# ---------------------------------------------------------------------------
# Negative correlations (competition and payer friction)
# ---------------------------------------------------------------------------

class TestNegativeCorrelations:
    def test_competitor_share_penetration_negative(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "competitor_share_mult", "peak_penetration_mult")
        assert r < -0.10, f"Expected negative r, got {r:.3f}"

    def test_competitor_share_payer_access_negative(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "competitor_share_mult", "payer_access_fraction")
        assert r < -0.05, f"Expected negative r, got {r:.3f}"

    def test_prior_auth_burden_penetration_negative(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "prior_auth_burden_delta", "peak_penetration_mult")
        assert r < -0.10, f"Expected negative r, got {r:.3f}"

    def test_prior_auth_burden_payer_access_negative(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "prior_auth_burden_delta", "payer_access_fraction")
        assert r < -0.20, f"Expected negative r, got {r:.3f}"


# ---------------------------------------------------------------------------
# Independent variables (near-zero correlation)
# ---------------------------------------------------------------------------

class TestIndependentVariables:
    def test_discount_rate_vs_phase3_near_zero(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "discount_rate", "phase_3_success_prob")
        assert abs(r) < 0.15, f"discount_rate vs phase_3 should be ~0, got {r:.3f}"

    def test_discount_rate_vs_penetration_near_zero(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "discount_rate", "peak_penetration_mult")
        assert abs(r) < 0.15, f"discount_rate vs penetration should be ~0, got {r:.3f}"

    def test_rd_cost_vs_phase3_near_zero(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "rd_cost_mult", "phase_3_success_prob")
        assert abs(r) < 0.15, f"rd_cost vs phase_3 should be ~0, got {r:.3f}"

    def test_rd_cost_vs_payer_access_near_zero(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "rd_cost_mult", "payer_access_fraction")
        assert abs(r) < 0.15, f"rd_cost vs payer_access should be ~0, got {r:.3f}"

    def test_discount_rate_vs_rd_cost_near_zero(self):
        r = _sample_rank_corr(ENHANCED_CORRELATION, "discount_rate", "rd_cost_mult")
        assert abs(r) < 0.15, f"discount_rate vs rd_cost should be ~0, got {r:.3f}"


# ---------------------------------------------------------------------------
# validate_correlation_consistency
# ---------------------------------------------------------------------------

class TestValidateCorrelationConsistency:
    def _spec_with_peak_sales(self) -> CorrelationSpec:
        return CorrelationSpec(
            variables=["peak_sales", "penetration"],
            pairs=[("peak_sales", "penetration", -0.20)],
        )

    def _spec_without_peak_sales(self) -> CorrelationSpec:
        return CorrelationSpec(
            variables=["phase_3_success_prob", "label_breadth_mult"],
            pairs=[("phase_3_success_prob", "label_breadth_mult", 0.40)],
        )

    def test_driver_based_plus_peak_sales_warns(self):
        spec = self._spec_with_peak_sales()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            validate_correlation_consistency(spec, driver_based=True)
            assert len(w) == 1
            assert "peak_sales" in str(w[0].message).lower()
            assert issubclass(w[0].category, UserWarning)

    def test_simple_mode_no_warning(self):
        spec = self._spec_with_peak_sales()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            validate_correlation_consistency(spec, driver_based=False)
            assert len(w) == 0

    def test_driver_based_no_peak_sales_no_warning(self):
        spec = self._spec_without_peak_sales()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            validate_correlation_consistency(spec, driver_based=True)
            assert len(w) == 0

    def test_warning_mentions_driver_based(self):
        spec = self._spec_with_peak_sales()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            validate_correlation_consistency(spec, driver_based=True)
            msg = str(w[0].message).lower()
            assert "driver" in msg or "double" in msg


# ---------------------------------------------------------------------------
# DEFAULT_CORRELATION backward compatibility
# ---------------------------------------------------------------------------

class TestDefaultCorrelationBackwardCompat:
    def test_default_has_original_four_variables(self):
        expected = {"peak_sales", "penetration", "discount_rate", "years_to_peak"}
        assert expected == set(DEFAULT_CORRELATION.variables)

    def test_default_peak_sales_penetration_negative(self):
        r = _sample_rank_corr(DEFAULT_CORRELATION, "peak_sales", "penetration")
        assert r < 0

    def test_default_cholesky_succeeds(self):
        L = DEFAULT_CORRELATION.cholesky()
        assert L.shape == (4, 4)

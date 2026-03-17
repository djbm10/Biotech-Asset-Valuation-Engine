"""
Wave 6 — Endpoint Benchmarking: 10 required tests.

1.  ORR evaluation: high ORR → z_score > 0, category EXCELLENT or ABOVE_THRESHOLD
2.  ORR evaluation: low ORR → z_score < 0, category BELOW_SOC
3.  HR evaluation: HR=0.50 (good) → positive z_score after -log normalization
4.  HR evaluation: HR=0.95 (poor) → negative z_score
5.  Shrinkage: small reference class (n=2) → std_adj >> std_sample
6.  Shrinkage: large reference class (n=10) → std_adj ≈ std_sample
7.  Unknown indication → returns None gracefully
8.  pos_modifier bounded within [-0.20, 0.20]
9.  normalize_endpoint: HR inversion works correctly
10. normalize_endpoint: ORR passes through unchanged
"""
from __future__ import annotations

import math
import statistics
from pathlib import Path

import pytest

from bve.intelligence.endpoint_benchmarking import (
    EndpointBenchmarkEvaluator,
    EndpointEvaluation,
    _PRIOR_STD_DEFAULTS,
    _categorize,
    _pos_modifier,
    normalize_endpoint,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BENCHMARKS_PATH = str(
    Path(__file__).resolve().parent.parent.parent
    / "src" / "bve" / "config" / "endpoint_benchmarks.yaml"
)


@pytest.fixture(scope="module")
def evaluator() -> EndpointBenchmarkEvaluator:
    return EndpointBenchmarkEvaluator(benchmarks_path=BENCHMARKS_PATH)


# ---------------------------------------------------------------------------
# Test 1: High ORR → z_score > 0, category EXCELLENT or ABOVE_THRESHOLD
# ---------------------------------------------------------------------------

class TestORREvaluationHigh:
    def test_high_orr_positive_zscore(self, evaluator):
        # NSCLC 1L ORR approved range ~0.20–0.45; pembrolizumab ≈ 0.45
        # Observe 0.55 (above the approval distribution mean) → z > 0
        result = evaluator.evaluate(0.55, "orr", "nsclc", "first_line")
        assert result is not None
        assert result.z_score > 0.0, f"Expected z > 0, got {result.z_score}"

    def test_high_orr_category(self, evaluator):
        result = evaluator.evaluate(0.65, "orr", "nsclc", "first_line")
        assert result is not None
        assert result.category in ("EXCELLENT", "ABOVE_THRESHOLD"), (
            f"Expected EXCELLENT or ABOVE_THRESHOLD, got {result.category}"
        )

    def test_high_orr_returns_evaluation_model(self, evaluator):
        result = evaluator.evaluate(0.60, "orr", "nsclc", "first_line")
        assert isinstance(result, EndpointEvaluation)


# ---------------------------------------------------------------------------
# Test 2: Low ORR → z_score < 0, category BELOW_SOC
# ---------------------------------------------------------------------------

class TestORREvaluationLow:
    def test_low_orr_negative_zscore(self, evaluator):
        # ORR of 0.05 is below the NSCLC 1L approval distribution
        result = evaluator.evaluate(0.05, "orr", "nsclc", "first_line")
        assert result is not None
        assert result.z_score < 0.0, f"Expected z < 0, got {result.z_score}"

    def test_low_orr_category_below_soc(self, evaluator):
        result = evaluator.evaluate(0.05, "orr", "nsclc", "first_line")
        assert result is not None
        assert result.category == "BELOW_SOC", (
            f"Expected BELOW_SOC, got {result.category}"
        )


# ---------------------------------------------------------------------------
# Test 3: HR=0.50 (good) → positive z_score
# ---------------------------------------------------------------------------

class TestHREvaluationGood:
    def test_hr_050_positive_zscore(self, evaluator):
        # HR=0.50 in NSCLC 1L; -log(0.50) ≈ 0.693
        # Approved HRs ~0.56–0.73 → normalized mean ~0.4–0.58
        # 0.693 should be above mean → z > 0
        result = evaluator.evaluate(0.50, "pfs_hr", "nsclc", "first_line")
        assert result is not None
        assert result.z_score > 0.0, (
            f"HR=0.50 should yield positive z_score; got {result.z_score}"
        )

    def test_hr_050_normalized_is_positive(self):
        norm = normalize_endpoint(0.50, "pfs_hr")
        assert norm > 0.0


# ---------------------------------------------------------------------------
# Test 4: HR=0.95 (poor) → negative z_score
# ---------------------------------------------------------------------------

class TestHREvaluationPoor:
    def test_hr_095_negative_zscore(self, evaluator):
        result = evaluator.evaluate(0.95, "pfs_hr", "nsclc", "first_line")
        assert result is not None
        assert result.z_score < 0.0, (
            f"HR=0.95 should yield negative z_score; got {result.z_score}"
        )

    def test_hr_095_category_not_excellent(self, evaluator):
        result = evaluator.evaluate(0.95, "pfs_hr", "nsclc", "first_line")
        assert result is not None
        assert result.category in ("ABOVE_SOC", "BELOW_SOC")


# ---------------------------------------------------------------------------
# Test 5: Small reference class (n=2) → std_adj >> std_sample
# ---------------------------------------------------------------------------

class TestShrinkageSmallClass:
    def test_small_class_std_adj_inflated(self):
        """Build a synthetic evaluator with a 2-drug reference class."""
        evaluator = EndpointBenchmarkEvaluator.__new__(EndpointBenchmarkEvaluator)
        evaluator._path = Path(BENCHMARKS_PATH)
        evaluator._data = None
        evaluator._prior_std = dict(_PRIOR_STD_DEFAULTS)

        # Inject a synthetic benchmark with n=2 approved drugs
        evaluator._data = {
            "test_area": {
                "test_indication": {
                    "first_line": {
                        "orr": {
                            "soc_baseline": 0.10,
                            "approved_drugs": [
                                {"name": "drug_a", "value": 0.30, "year": 2020},
                                {"name": "drug_b", "value": 0.40, "year": 2021},
                            ],
                        }
                    }
                }
            }
        }

        result = evaluator.evaluate(0.35, "orr", "test_indication", "first_line")
        assert result is not None
        assert result.n_reference_drugs == 2
        assert result.shrinkage_applied is True
        assert result.std_adjusted > result.std_sample, (
            f"std_adj={result.std_adjusted} should exceed std_sample={result.std_sample}"
        )

    def test_small_class_shrinkage_magnitude(self):
        """With n=2, prior contributes meaningfully to std_adj."""
        vals = [0.30, 0.40]
        std_sample = statistics.stdev(vals)
        prior = _PRIOR_STD_DEFAULTS["orr"]
        std_adj = math.sqrt(std_sample ** 2 + prior ** 2)
        # Prior should contribute at least 30% of quadrature sum when n=2
        assert std_adj / std_sample > 1.10, (
            f"Expected shrinkage > 10% over sample std; ratio={std_adj/std_sample:.3f}"
        )


# ---------------------------------------------------------------------------
# Test 6: Large reference class (n=10) → std_adj ≈ std_sample
# ---------------------------------------------------------------------------

class TestShrinkageLargeClass:
    def test_large_class_std_adj_close_to_sample(self):
        """n=10 shrinkage ratio must be substantially smaller than n=2 ratio."""
        import statistics as _stats

        # n=10 distribution
        vals_n10 = [0.10, 0.20, 0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.90]
        std_n10 = _stats.stdev(vals_n10)

        # n=2 distribution (same endpoint)
        vals_n2 = [0.30, 0.40]
        std_n2 = _stats.stdev(vals_n2)

        prior = _PRIOR_STD_DEFAULTS["orr"]
        ratio_n10 = math.sqrt(std_n10 ** 2 + prior ** 2) / std_n10
        ratio_n2  = math.sqrt(std_n2  ** 2 + prior ** 2) / std_n2

        # n=10 should have less shrinkage inflation than n=2
        assert ratio_n10 < ratio_n2, (
            f"n=10 ratio {ratio_n10:.3f} should be < n=2 ratio {ratio_n2:.3f}"
        )
        # n=10 inflation should still be moderate (std_sample not wildly >> prior)
        assert ratio_n10 < 1.20, (
            f"n=10 shrinkage ratio should be < 1.20; got {ratio_n10:.3f}"
        )

    def test_large_class_shrinkage_applied_flag(self):
        """shrinkage_applied is True whenever std_adj > std_sample (always)."""
        # Even with large n, std_adj = sqrt(std² + prior²) > std whenever prior > 0
        evaluator = EndpointBenchmarkEvaluator.__new__(EndpointBenchmarkEvaluator)
        evaluator._path = Path(BENCHMARKS_PATH)
        evaluator._data = None
        evaluator._prior_std = dict(_PRIOR_STD_DEFAULTS)

        drugs = [{"name": f"drug_{i}", "value": 0.10 + i * 0.08, "year": 2010 + i}
                 for i in range(10)]
        evaluator._data = {
            "test_area": {
                "large_indication": {
                    "first_line": {
                        "orr": {"soc_baseline": 0.10, "approved_drugs": drugs}
                    }
                }
            }
        }

        result = evaluator.evaluate(0.45, "orr", "large_indication", "first_line")
        assert result is not None
        assert result.n_reference_drugs == 10
        # std_adj always > std_sample (prior > 0)
        assert result.shrinkage_applied is True


# ---------------------------------------------------------------------------
# Test 7: Unknown indication → returns None gracefully
# ---------------------------------------------------------------------------

class TestUnknownIndication:
    def test_unknown_indication_returns_none(self, evaluator):
        result = evaluator.evaluate(0.40, "orr", "unknown_xyzzy_indication", "first_line")
        assert result is None

    def test_unknown_endpoint_returns_none(self, evaluator):
        result = evaluator.evaluate(0.40, "completely_unknown_ep", "nsclc", "first_line")
        assert result is None

    def test_unknown_lot_returns_none(self, evaluator):
        result = evaluator.evaluate(0.40, "orr", "nsclc", "fourth_line")
        assert result is None


# ---------------------------------------------------------------------------
# Test 8: pos_modifier bounded within [-0.20, 0.20]
# ---------------------------------------------------------------------------

class TestPosModifierBounds:
    def test_large_positive_z_capped_at_020(self):
        # z = 5.0 → 0.10 * 5 = 0.50 → capped at 0.20
        mod = _pos_modifier(5.0)
        assert mod == pytest.approx(0.20)

    def test_large_negative_z_capped_at_minus_020(self):
        mod = _pos_modifier(-5.0)
        assert mod == pytest.approx(-0.20)

    def test_moderate_z_not_capped(self):
        # z = 1.0 → 0.10 * 1.0 = 0.10 (within bounds)
        mod = _pos_modifier(1.0)
        assert mod == pytest.approx(0.10)

    def test_pos_modifier_from_full_evaluation_is_bounded(self, evaluator):
        # Evaluate an extreme case; modifier must stay within [-0.20, 0.20]
        result = evaluator.evaluate(0.99, "orr", "nsclc", "first_line")
        assert result is not None
        assert -0.20 <= result.pos_modifier <= 0.20

    def test_pos_modifier_from_low_evaluation_is_bounded(self, evaluator):
        result = evaluator.evaluate(0.001, "orr", "nsclc", "first_line")
        assert result is not None
        assert -0.20 <= result.pos_modifier <= 0.20


# ---------------------------------------------------------------------------
# Test 9: normalize_endpoint — HR inversion
# ---------------------------------------------------------------------------

class TestNormalizeEndpointHR:
    def test_hr_inversion_direction(self):
        # HR=0.50 (good) → normalized value > HR=0.80 (worse)
        norm_good = normalize_endpoint(0.50, "pfs_hr")
        norm_poor = normalize_endpoint(0.80, "pfs_hr")
        assert norm_good > norm_poor, (
            f"HR 0.50 should normalize higher than 0.80; "
            f"got {norm_good:.4f} vs {norm_poor:.4f}"
        )

    def test_hr_equals_negative_log(self):
        for hr in (0.40, 0.60, 0.75, 0.90):
            expected = -math.log(hr)
            assert normalize_endpoint(hr, "pfs_hr") == pytest.approx(expected)

    def test_all_hr_endpoint_types_inverted(self):
        for ep in ("pfs_hr", "os_hr", "ttp_hr", "dfs_hr", "efs_hr"):
            assert normalize_endpoint(0.60, ep) == pytest.approx(-math.log(0.60))

    def test_hr_near_zero_guarded(self):
        # value capped at 1e-6 to avoid log(0)
        result = normalize_endpoint(0.0, "pfs_hr")
        assert math.isfinite(result)
        assert result > 0


# ---------------------------------------------------------------------------
# Test 10: normalize_endpoint — ORR passes through unchanged
# ---------------------------------------------------------------------------

class TestNormalizeEndpointORR:
    def test_orr_passthrough(self):
        for val in (0.0, 0.25, 0.50, 0.75, 1.0):
            assert normalize_endpoint(val, "orr") == pytest.approx(val)

    def test_cr_rate_passthrough(self):
        assert normalize_endpoint(0.37, "cr_rate") == pytest.approx(0.37)

    def test_pasi90_passthrough(self):
        assert normalize_endpoint(0.73, "pasi90") == pytest.approx(0.73)

    def test_acr50_passthrough(self):
        assert normalize_endpoint(0.56, "acr50") == pytest.approx(0.56)

    def test_unknown_endpoint_passthrough(self):
        # Non-HR endpoint keys pass through by default
        assert normalize_endpoint(0.42, "some_custom_ep") == pytest.approx(0.42)

"""
Tests for Sprint 9 overlay hardening:
    - EXPECTED_SIGNS contract (features.py)
    - Sparse clamp guard (overlay_model.py)
    - Sign gate guard (overlay_model.py)
    - sweep_alpha (overlay_model.py)
    - PromotionGateResult (overlay_gates.py)
    - check_promotion_gates (overlay_gates.py)
    - promotion_summary (overlay_gates.py)
"""
import math
import pytest

from bve.empirical.features import (
    EXPECTED_SIGNS,
    FEATURE_NAMES,
    N_FEATURES,
)
from bve.empirical.overlay_model import (
    OverlayArtifact,
    AlphaSweepEntry,
    fit_overlay,
    fit_overlay_time_split,
    sweep_alpha,
)
from bve.empirical.overlay_gates import (
    PromotionGateResult,
    check_promotion_gates,
    promotion_summary,
)
from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.pos_outcome import POSOutcomeRecord
from bve.empirical.comparison import POSModeComparison, ModeEvalResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _rec(
    phase="phase_2",
    success=True,
    moa="partial",
    bio=False,
    endpoint="surrogate_validated",
    safety="minor",
    competition="moderate",
    outcome_date=None,
    idx=0,
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{idx}",
        sponsor="AcmeBio",
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


def _varied_records(n: int = 30) -> list[POSOutcomeRecord]:
    """Records with diverse feature states — ensures non-zero feature matrix."""
    recs = []
    phases = ["phase_1", "phase_2", "phase_3"]
    moavals = ["validated", "novel", "partial"]
    safeties = ["clean", "concerning", "minor", "serious"]
    comps = ["low", "high", "moderate"]
    for i in range(n):
        recs.append(_rec(
            phase=phases[i % len(phases)],
            success=(i % 2 == 0),
            moa=moavals[i % len(moavals)],
            bio=(i % 3 == 0),
            safety=safeties[i % len(safeties)],
            competition=comps[i % len(comps)],
            idx=i,
        ))
    return recs


def _make_table(recs: list[POSOutcomeRecord]) -> BaseRateTable:
    return BaseRateTable(recs, smoothing_alpha=1.0)


def _make_comparison(
    fitted_brier: float = 0.18,
    fitted_auc: float = 0.75,
    fitted_ece: float = 0.12,
    emp_h_brier: float = 0.20,
    emp_h_auc: float = 0.70,
    emp_h_ece: float = 0.10,
) -> POSModeComparison:
    """Build a minimal POSModeComparison for gate testing."""
    return POSModeComparison(
        modes=[
            ModeEvalResult(
                mode="empirical_fitted",
                brier=fitted_brier,
                auc=fitted_auc,
                ece=fitted_ece,
                n_samples=50,
                mean_pred=0.55,
                mean_outcome=0.60,
            ),
            ModeEvalResult(
                mode="empirical_heuristic",
                brier=emp_h_brier,
                auc=emp_h_auc,
                ece=emp_h_ece,
                n_samples=50,
                mean_pred=0.52,
                mean_outcome=0.60,
            ),
        ],
        cutoff_year=2019,
        n_train=59,
        n_test=50,
        best_mode_by_brier="empirical_fitted",
        best_mode_by_auc="empirical_fitted",
        empirical_success_rate=0.60,
    )


def _clean_artifact(**overrides) -> OverlayArtifact:
    """Minimal OverlayArtifact that passes all gates by default."""
    defaults = dict(
        feature_names=list(FEATURE_NAMES),
        coefficients=[0.0] * N_FEATURES,
        intercept=0.0,
        regularization_alpha=1.0,
        n_train=50,
        cutoff_year=2019,
        n_feature_nonzero={name: 10 for name in FEATURE_NAMES},
        converged=True,
        train_brier_base=0.25,
        train_brier_overlay=0.18,
        train_auc_base=0.60,
        train_auc_overlay=0.72,
        train_ece_base=0.12,
        train_ece_overlay=0.09,
        sparse_clamped={},
        sign_violated={},
        min_feature_obs=5,
    )
    defaults.update(overrides)
    return OverlayArtifact(**defaults)


# ---------------------------------------------------------------------------
# EXPECTED_SIGNS contract tests
# ---------------------------------------------------------------------------

class TestExpectedSigns:
    def test_all_features_covered(self):
        """Every feature in FEATURE_NAMES has an entry in EXPECTED_SIGNS."""
        for name in FEATURE_NAMES:
            assert name in EXPECTED_SIGNS, f"'{name}' missing from EXPECTED_SIGNS"

    def test_no_extra_features(self):
        """EXPECTED_SIGNS contains no names outside FEATURE_NAMES."""
        for name in EXPECTED_SIGNS:
            assert name in FEATURE_NAMES, f"'{name}' in EXPECTED_SIGNS but not FEATURE_NAMES"

    def test_values_are_valid(self):
        """Every sign value must be +1, -1, or 0."""
        for name, sign in EXPECTED_SIGNS.items():
            assert sign in (-1, 0, 1), f"EXPECTED_SIGNS['{name}'] = {sign!r}, expected -1/0/+1"

    def test_safety_serious_must_be_negative(self):
        """CRITICAL: safety_serious must always have expected sign -1."""
        assert EXPECTED_SIGNS["safety_serious"] == -1

    def test_safety_clean_positive(self):
        assert EXPECTED_SIGNS["safety_clean"] == +1

    def test_safety_concerning_negative(self):
        assert EXPECTED_SIGNS["safety_concerning"] == -1

    def test_moa_validated_positive(self):
        assert EXPECTED_SIGNS["moa_validated"] == +1

    def test_moa_novel_negative(self):
        assert EXPECTED_SIGNS["moa_novel"] == -1

    def test_biomarker_selected_positive(self):
        assert EXPECTED_SIGNS["biomarker_selected"] == +1

    def test_endpoint_biomarker_only_negative(self):
        assert EXPECTED_SIGNS["endpoint_biomarker_only"] == -1

    def test_endpoint_surrogate_novel_negative(self):
        assert EXPECTED_SIGNS["endpoint_surrogate_novel"] == -1

    def test_competition_low_positive(self):
        assert EXPECTED_SIGNS["competition_low"] == +1

    def test_competition_high_negative(self):
        assert EXPECTED_SIGNS["competition_high"] == -1

    def test_endpoint_hard_clinical_unconstrained(self):
        """endpoint_hard_clinical is deliberately 0 (data-determined direction)."""
        assert EXPECTED_SIGNS["endpoint_hard_clinical"] == 0


# ---------------------------------------------------------------------------
# Sparse clamp guard
# ---------------------------------------------------------------------------

class TestSparseClampGuard:
    def _make_sparse_records(self, n: int = 20) -> tuple[list, BaseRateTable]:
        """Records that are all baseline — every feature has n_nonzero=0."""
        recs = []
        for i in range(n):
            recs.append(_rec(
                phase="phase_2",
                success=(i % 2 == 0),
                moa="partial",       # baseline — produces 0 for moa indicators
                bio=False,
                endpoint="surrogate_validated",  # baseline
                safety="minor",      # baseline
                competition="moderate",  # baseline
                idx=i,
            ))
        table = _make_table(recs)
        return recs, table

    def test_sparse_features_are_zeroed(self):
        """Features with zero training observations get coefficient 0.0."""
        recs, table = self._make_sparse_records(20)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=1)
        # All-baseline records: every non-baseline feature has n_nonzero=0
        # With min_feature_obs=1, features with n=0 are clamped
        for name, n_obs in art.sparse_clamped.items():
            idx = art.feature_names.index(name)
            assert art.coefficients[idx] == 0.0, (
                f"'{name}' was sparse-clamped but coefficient is {art.coefficients[idx]}"
            )

    def test_sparse_clamped_records_n_nonzero(self):
        """sparse_clamped maps feature_name → n_nonzero at clamp time."""
        recs, table = self._make_sparse_records(20)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=5)
        for name, n_obs in art.sparse_clamped.items():
            assert isinstance(n_obs, int)
            assert n_obs >= 0
            assert n_obs < art.min_feature_obs

    def test_min_feature_obs_stored_in_artifact(self):
        recs, table = self._make_sparse_records(20)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=7)
        assert art.min_feature_obs == 7

    def test_sparse_clamp_threshold_respected(self):
        """Feature with exactly min_feature_obs examples is NOT clamped."""
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=1)
        # With min_feature_obs=1: any feature that appears at least once is not clamped
        for name in art.sparse_clamped:
            assert art.n_feature_nonzero[name] < 1

    def test_sparse_clamp_zero_threshold_clamps_nothing(self):
        """min_feature_obs=0 disables the sparse clamp (nothing has n_nonzero < 0)."""
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=0)
        assert art.sparse_clamped == {}

    def test_roundtrip_preserves_sparse_clamped(self):
        recs, table = self._make_sparse_records(20)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=5)
        d = art.to_dict()
        art2 = OverlayArtifact.from_dict(d)
        assert art2.sparse_clamped == art.sparse_clamped
        assert art2.min_feature_obs == art.min_feature_obs

    def test_from_dict_defaults_sparse_clamped_empty(self):
        """Legacy artifacts without sparse_clamped key deserialize cleanly."""
        recs, table = self._make_sparse_records(20)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=5)
        d = art.to_dict()
        del d["sparse_clamped"]
        del d["min_feature_obs"]
        art2 = OverlayArtifact.from_dict(d)
        assert art2.sparse_clamped == {}
        assert art2.min_feature_obs == 5  # default

    def test_sparse_clamp_applied_before_sign_gate(self):
        """A sparse-clamped feature must not appear in sign_violated."""
        recs, table = self._make_sparse_records(20)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=5, enforce_sign_gate=True)
        overlap = set(art.sparse_clamped) & set(art.sign_violated)
        assert overlap == set(), f"Features in both sparse_clamped and sign_violated: {overlap}"


# ---------------------------------------------------------------------------
# Sign gate guard
# ---------------------------------------------------------------------------

class TestSignGateGuard:
    def test_sign_violated_empty_for_all_baseline_records(self):
        """All-baseline records → all coefficients near 0 → no sign violations."""
        recs = []
        for i in range(20):
            recs.append(_rec(phase="phase_2", success=(i % 2 == 0), idx=i))
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=0, enforce_sign_gate=True)
        assert art.sign_violated == {}

    def test_sign_gate_disabled_when_enforce_false(self):
        """With enforce_sign_gate=False, sign_violated must be empty."""
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=1.0, min_feature_obs=0, enforce_sign_gate=False)
        assert art.sign_violated == {}

    def test_sign_violated_coefficient_forced_to_zero(self):
        """Any feature in sign_violated must have coefficient == 0.0."""
        recs = _varied_records(30)
        table = _make_table(recs)
        # Very low alpha → large coefficients → more likely sign violations
        art = fit_overlay(recs, table, alpha=0.001, min_feature_obs=0, enforce_sign_gate=True)
        for name in art.sign_violated:
            idx = art.feature_names.index(name)
            assert art.coefficients[idx] == 0.0, (
                f"'{name}' in sign_violated but coefficient is {art.coefficients[idx]}"
            )

    def test_sign_violated_stores_raw_coefficient(self):
        """Values in sign_violated are the raw (pre-zeroing) coefficients."""
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=0.001, min_feature_obs=0, enforce_sign_gate=True)
        for name, raw in art.sign_violated.items():
            assert isinstance(raw, float)
            # Raw coefficient should violate the expected sign
            expected = EXPECTED_SIGNS[name]
            if expected == +1:
                assert raw < 0.0, f"'{name}': expected raw<0 for +1 violation, got {raw}"
            elif expected == -1:
                assert raw > 0.0, f"'{name}': expected raw>0 for -1 violation, got {raw}"

    def test_roundtrip_preserves_sign_violated(self):
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=0.001, min_feature_obs=0, enforce_sign_gate=True)
        d = art.to_dict()
        art2 = OverlayArtifact.from_dict(d)
        assert art2.sign_violated == art.sign_violated

    def test_from_dict_defaults_sign_violated_empty(self):
        """Legacy artifacts without sign_violated key deserialize cleanly."""
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=1.0)
        d = art.to_dict()
        del d["sign_violated"]
        art2 = OverlayArtifact.from_dict(d)
        assert art2.sign_violated == {}

    def test_unconstrained_feature_never_in_sign_violated(self):
        """Features with EXPECTED_SIGNS=0 are never added to sign_violated."""
        recs = _varied_records(30)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=0.001, min_feature_obs=0, enforce_sign_gate=True)
        unconstrained = {name for name, s in EXPECTED_SIGNS.items() if s == 0}
        in_violation = unconstrained & set(art.sign_violated)
        assert in_violation == set(), (
            f"Unconstrained features must not appear in sign_violated: {in_violation}"
        )

    def test_safety_serious_must_never_be_positive_after_gate(self):
        """The safety_serious coefficient must never be positive when the gate is on."""
        recs = _varied_records(40)
        table = _make_table(recs)
        art = fit_overlay(recs, table, alpha=0.001, min_feature_obs=0, enforce_sign_gate=True)
        idx = art.feature_names.index("safety_serious")
        assert art.coefficients[idx] <= 0.0, (
            f"safety_serious coefficient is {art.coefficients[idx]} — gate should prevent positive values"
        )


# ---------------------------------------------------------------------------
# sweep_alpha
# ---------------------------------------------------------------------------

class TestSweepAlpha:
    def test_returns_one_entry_per_alpha(self):
        recs = _varied_records(30)
        table = _make_table(recs)
        alphas = [0.5, 1.0, 5.0]
        results = sweep_alpha(recs, table, alphas=alphas)
        assert len(results) == 3
        assert [e.alpha for e in results] == alphas

    def test_entry_fields_present(self):
        recs = _varied_records(30)
        table = _make_table(recs)
        results = sweep_alpha(recs, table, alphas=[1.0])
        e = results[0]
        assert e.alpha == 1.0
        assert isinstance(e.train_brier, float)
        assert isinstance(e.n_sparse_clamped, int)
        assert isinstance(e.n_sign_violated, int)
        assert isinstance(e.converged, bool)

    def test_default_alphas_used_when_none(self):
        recs = _varied_records(30)
        table = _make_table(recs)
        results = sweep_alpha(recs, table, alphas=None)
        assert len(results) == 4  # default is [1.0, 3.0, 5.0, 10.0]

    def test_higher_alpha_increases_train_brier(self):
        """Higher regularization should push train Brier toward the base rate Brier."""
        recs = _varied_records(40)
        table = _make_table(recs)
        results = sweep_alpha(recs, table, alphas=[0.01, 100.0])
        low_alpha_brier = results[0].train_brier
        high_alpha_brier = results[1].train_brier
        # Very high alpha collapses to intercept-only → higher train Brier
        assert high_alpha_brier >= low_alpha_brier

    def test_temporal_split_when_cutoff_year_provided(self):
        """When cutoff_year is given and no test_records, uses time split."""
        recs = []
        for i in range(40):
            recs.append(_rec(
                phase="phase_2",
                success=(i % 2 == 0),
                outcome_date=f"201{i % 9}-01-01",  # dates 2010–2018
                idx=i,
            ))
        # Add some post-cutoff records
        for i in range(20):
            recs.append(_rec(
                phase="phase_2",
                success=(i % 2 == 0),
                outcome_date=f"202{i % 5}-01-01",  # dates 2020–2024
                idx=40 + i,
            ))
        table = _make_table(recs)
        results = sweep_alpha(recs, table, alphas=[1.0], cutoff_year=2019)
        e = results[0]
        # Test metrics should be populated
        assert e.test_brier is not None
        assert e.test_auc is not None
        assert e.test_ece is not None

    def test_no_test_metrics_when_no_split(self):
        """Without cutoff_year or test_records, test metrics are None."""
        recs = _varied_records(30)
        table = _make_table(recs)
        results = sweep_alpha(recs, table, alphas=[1.0], cutoff_year=None, test_records=None)
        e = results[0]
        assert e.test_brier is None
        assert e.test_auc is None
        assert e.test_ece is None

    def test_n_sparse_and_sign_violated_are_non_negative(self):
        recs = _varied_records(30)
        table = _make_table(recs)
        results = sweep_alpha(recs, table, alphas=[0.5, 1.0, 5.0])
        for e in results:
            assert e.n_sparse_clamped >= 0
            assert e.n_sign_violated >= 0

    def test_alpha_sweep_entry_dataclass_fields(self):
        e = AlphaSweepEntry(
            alpha=2.0,
            train_brier=0.20,
            test_brier=0.22,
            test_auc=0.71,
            test_ece=0.14,
            n_sparse_clamped=2,
            n_sign_violated=0,
            converged=True,
        )
        assert e.alpha == 2.0
        assert e.n_sparse_clamped == 2
        assert e.converged is True


# ---------------------------------------------------------------------------
# PromotionGateResult
# ---------------------------------------------------------------------------

class TestPromotionGateResult:
    def test_pass_str_format(self):
        g = PromotionGateResult(
            gate="fitted_brier_vs_empirical_heuristic",
            passed=True,
            value=0.18,
            threshold=0.20,
            detail="fitted_brier=0.1800 < empirical_heuristic_brier=0.2000",
        )
        s = str(g)
        assert "[PASS]" in s
        assert "fitted_brier_vs_empirical_heuristic" in s

    def test_fail_str_format(self):
        g = PromotionGateResult(
            gate="ece_regression",
            passed=False,
            value=0.07,
            threshold=0.05,
            detail="|fitted_ece(0.17) - emp_heuristic_ece(0.10)| = 0.07 > 0.0500",
        )
        s = str(g)
        assert "[FAIL]" in s
        assert "ece_regression" in s

    def test_is_frozen_dataclass(self):
        g = PromotionGateResult(gate="g", passed=True, value=0.1, threshold=0.2, detail="ok")
        with pytest.raises((AttributeError, TypeError)):
            g.passed = False  # type: ignore[misc]

    def test_fields_preserved(self):
        g = PromotionGateResult(gate="g", passed=False, value=1.5, threshold=1.0, detail="d")
        assert g.gate == "g"
        assert g.passed is False
        assert g.value == 1.5
        assert g.threshold == 1.0
        assert g.detail == "d"


# ---------------------------------------------------------------------------
# check_promotion_gates
# ---------------------------------------------------------------------------

class TestCheckPromotionGates:
    def test_returns_four_results(self):
        comp = _make_comparison(
            fitted_brier=0.18, emp_h_brier=0.20,
            fitted_ece=0.12, emp_h_ece=0.10,
        )
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert len(gates) == 4

    def test_gate_order(self):
        """Gates must be returned in the documented order."""
        comp = _make_comparison()
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert gates[0].gate == "fitted_brier_vs_empirical_heuristic"
        assert gates[1].gate == "safety_serious_sign"
        assert gates[2].gate == "ece_regression"
        assert gates[3].gate == "sparse_feature_count"

    def test_all_pass_when_overlay_is_clean(self):
        """Clean overlay + good comparison → all four gates pass."""
        comp = _make_comparison(
            fitted_brier=0.18, emp_h_brier=0.20,
            fitted_ece=0.12, emp_h_ece=0.10,
        )
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert all(g.passed for g in gates), [g for g in gates if not g.passed]

    def test_gate1_fails_when_brier_not_better(self):
        """Brier gate fails when fitted Brier >= empirical_heuristic Brier."""
        comp = _make_comparison(fitted_brier=0.22, emp_h_brier=0.20)
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert not gates[0].passed
        assert gates[0].value == pytest.approx(0.22)
        assert gates[0].threshold == pytest.approx(0.20)

    def test_gate1_passes_when_brier_strictly_better(self):
        comp = _make_comparison(fitted_brier=0.199, emp_h_brier=0.20)
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert gates[0].passed

    def test_gate2_fails_when_safety_serious_sign_violated(self):
        """safety_serious in sign_violated → gate 2 fails."""
        overlay = _clean_artifact(sign_violated={"safety_serious": +0.717})
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert not gates[1].passed
        assert gates[1].value == 0.0  # failed → value=0.0

    def test_gate2_fails_when_safety_serious_sparse_clamped(self):
        """safety_serious sparse-clamped → gate 2 fails (can't verify sign)."""
        overlay = _clean_artifact(sparse_clamped={"safety_serious": 3})
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert not gates[1].passed

    def test_gate2_passes_when_safety_serious_clean(self):
        """No sign violation or sparse clamp for safety_serious → gate 2 passes."""
        overlay = _clean_artifact(sparse_clamped={}, sign_violated={})
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert gates[1].passed
        assert gates[1].value == 1.0

    def test_gate2_detail_contains_coefficient_info_when_passing(self):
        """When gate 2 passes, detail should mention the coefficient value."""
        overlay = _clean_artifact()
        # Put a valid (negative) coefficient for safety_serious
        coeffs = list(overlay.coefficients)
        idx = overlay.feature_names.index("safety_serious")
        coeffs[idx] = -0.337
        overlay = _clean_artifact(coefficients=coeffs)
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert gates[1].passed
        assert "coefficient" in gates[1].detail

    def test_gate3_fails_when_ece_regression_exceeds_threshold(self):
        """ECE regression gate fails when |fitted_ece - emp_h_ece| > max_ece_regression."""
        comp = _make_comparison(fitted_ece=0.17, emp_h_ece=0.10)
        overlay = _clean_artifact()
        gates = check_promotion_gates(
            comp, overlay, empirical_heuristic_brier=0.20, max_ece_regression=0.05
        )
        assert not gates[2].passed
        assert gates[2].value == pytest.approx(0.07, abs=0.001)

    def test_gate3_passes_when_ece_within_threshold(self):
        comp = _make_comparison(fitted_ece=0.14, emp_h_ece=0.10)
        overlay = _clean_artifact()
        gates = check_promotion_gates(
            comp, overlay, empirical_heuristic_brier=0.20, max_ece_regression=0.05
        )
        assert gates[2].passed

    def test_gate3_custom_threshold_applied(self):
        """max_ece_regression parameter overrides the default 0.05."""
        comp = _make_comparison(fitted_ece=0.17, emp_h_ece=0.10)  # delta=0.07
        overlay = _clean_artifact()
        # With threshold=0.10, delta=0.07 should pass
        gates = check_promotion_gates(
            comp, overlay, empirical_heuristic_brier=0.20, max_ece_regression=0.10
        )
        assert gates[2].passed

    def test_gate4_fails_when_too_many_sparse_features(self):
        """Sparse feature count gate fails when n_sparse > max_sparse_features."""
        overlay = _clean_artifact(sparse_clamped={
            "moa_validated": 2,
            "endpoint_surrogate_novel": 1,
            "endpoint_biomarker_only": 3,
            "moa_novel": 0,  # 4th sparse — exceeds default max of 3
        })
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert not gates[3].passed
        assert gates[3].value == pytest.approx(4.0)

    def test_gate4_passes_when_sparse_at_threshold(self):
        """Exactly max_sparse_features → gate passes (≤ not <)."""
        overlay = _clean_artifact(sparse_clamped={
            "moa_validated": 2,
            "endpoint_surrogate_novel": 1,
            "endpoint_biomarker_only": 3,
        })
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20, max_sparse_features=3)
        assert gates[3].passed

    def test_gate4_custom_max_applied(self):
        overlay = _clean_artifact(sparse_clamped={"moa_validated": 2, "moa_novel": 1})
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20)
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20, max_sparse_features=1)
        assert not gates[3].passed

    def test_missing_fitted_mode_in_comparison(self):
        """If 'empirical_fitted' is absent from comparison, Brier defaults to inf → gate fails."""
        comp = POSModeComparison(
            modes=[
                ModeEvalResult(
                    mode="empirical_heuristic",
                    brier=0.20,
                    auc=0.70,
                    ece=0.10,
                    n_samples=50,
                    mean_pred=0.52,
                    mean_outcome=0.60,
                ),
            ],
            cutoff_year=2019,
            n_train=50,
            n_test=50,
            best_mode_by_brier="empirical_heuristic",
            best_mode_by_auc="empirical_heuristic",
            empirical_success_rate=0.60,
        )
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        assert not gates[0].passed  # inf >= 0.20

    def test_gate_value_and_threshold_types(self):
        """All gate values and thresholds must be numeric floats."""
        comp = _make_comparison()
        overlay = _clean_artifact()
        gates = check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)
        for g in gates:
            assert isinstance(g.value, float), f"{g.gate}.value is not float"
            assert isinstance(g.threshold, float), f"{g.gate}.threshold is not float"


# ---------------------------------------------------------------------------
# promotion_summary
# ---------------------------------------------------------------------------

class TestPromotionSummary:
    def _all_pass_gates(self) -> list[PromotionGateResult]:
        comp = _make_comparison(fitted_brier=0.18, emp_h_brier=0.20,
                                fitted_ece=0.12, emp_h_ece=0.10)
        overlay = _clean_artifact()
        return check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)

    def _one_fail_gates(self) -> list[PromotionGateResult]:
        comp = _make_comparison(fitted_brier=0.22, emp_h_brier=0.20)  # gate 1 fails
        overlay = _clean_artifact()
        return check_promotion_gates(comp, overlay, empirical_heuristic_brier=0.20)

    def test_returns_string(self):
        gates = self._all_pass_gates()
        result = promotion_summary(gates)
        assert isinstance(result, str)

    def test_promotable_verdict_when_all_pass(self):
        gates = self._all_pass_gates()
        summary = promotion_summary(gates)
        assert "PROMOTABLE" in summary
        assert "NOT PROMOTABLE" not in summary

    def test_not_promotable_verdict_when_any_fail(self):
        gates = self._one_fail_gates()
        summary = promotion_summary(gates)
        assert "NOT PROMOTABLE" in summary

    def test_summary_contains_all_gate_names(self):
        gates = self._all_pass_gates()
        summary = promotion_summary(gates)
        assert "fitted_brier_vs_empirical_heuristic" in summary
        assert "safety_serious_sign" in summary
        assert "ece_regression" in summary
        assert "sparse_feature_count" in summary

    def test_summary_contains_pass_and_fail_indicators(self):
        gates = self._one_fail_gates()
        summary = promotion_summary(gates)
        assert "PASS" in summary
        assert "FAIL" in summary

    def test_failed_gate_detail_in_summary(self):
        """Failed gate details are included in the summary output."""
        gates = self._one_fail_gates()
        summary = promotion_summary(gates)
        # The failed gate's detail should appear in the summary
        failed = [g for g in gates if not g.passed]
        for g in failed:
            assert g.detail in summary

    def test_empty_gates_list(self):
        """promotion_summary handles empty list gracefully."""
        summary = promotion_summary([])
        assert isinstance(summary, str)
        assert "PROMOTABLE" in summary  # all gates pass vacuously


# ---------------------------------------------------------------------------
# Integration: guards + gates on fit_overlay_time_split output
# ---------------------------------------------------------------------------

class TestHardeningIntegration:
    def _make_time_split_records(self) -> list[POSOutcomeRecord]:
        """40 train records (≤2019) + 20 test records (>2019) with varied features."""
        recs = []
        for i in range(40):
            recs.append(_rec(
                phase=["phase_2", "phase_3"][i % 2],
                success=(i % 2 == 0),
                moa=["novel", "partial", "validated"][i % 3],
                bio=(i % 3 == 0),
                safety=["clean", "minor", "concerning", "serious"][i % 4],
                competition=["low", "moderate", "high"][i % 3],
                outcome_date="2018-01-01",
                idx=i,
            ))
        for i in range(20):
            recs.append(_rec(
                phase="phase_2",
                success=(i % 2 == 0),
                moa="novel",
                outcome_date="2022-01-01",
                idx=40 + i,
            ))
        return recs

    def test_no_sign_violations_with_default_guards(self):
        """Default guards should prevent sign violations in typical settings."""
        recs = self._make_time_split_records()
        table = _make_table(recs)
        art = fit_overlay_time_split(recs, table, cutoff_year=2019, alpha=1.0,
                                     min_feature_obs=5, enforce_sign_gate=True)
        # safety_serious must never be positive
        idx = art.feature_names.index("safety_serious")
        assert art.coefficients[idx] <= 0.0

    def test_sparse_clamped_and_sign_violated_disjoint(self):
        recs = self._make_time_split_records()
        table = _make_table(recs)
        art = fit_overlay_time_split(recs, table, cutoff_year=2019, alpha=1.0,
                                     min_feature_obs=5, enforce_sign_gate=True)
        overlap = set(art.sparse_clamped) & set(art.sign_violated)
        assert overlap == set()

    def test_gates_reflect_actual_artifact(self):
        """Gate results should be consistent with the artifact's own fields."""
        recs = self._make_time_split_records()
        table = _make_table(recs)
        art = fit_overlay_time_split(recs, table, cutoff_year=2019, alpha=1.0,
                                     min_feature_obs=5, enforce_sign_gate=True)
        # Build a minimal comparison using the artifact's own test metrics
        emp_h_brier = 0.22  # simulated empirical_heuristic baseline
        emp_h_ece = 0.11
        fitted_brier = art.test_brier_overlay or 0.25
        fitted_ece = art.test_ece_overlay or 0.15
        fitted_auc = art.test_auc_overlay or 0.65
        comp = _make_comparison(
            fitted_brier=fitted_brier,
            fitted_ece=fitted_ece,
            fitted_auc=fitted_auc,
            emp_h_brier=emp_h_brier,
            emp_h_ece=emp_h_ece,
        )
        gates = check_promotion_gates(comp, art, empirical_heuristic_brier=emp_h_brier)
        assert len(gates) == 4
        # Gate 4 (sparse_feature_count) should agree with artifact
        assert gates[3].value == float(len(art.sparse_clamped))

    def test_sweep_with_all_guards(self):
        """sweep_alpha should run cleanly with guards enabled."""
        recs = self._make_time_split_records()
        table = _make_table(recs)
        results = sweep_alpha(
            recs, table,
            alphas=[1.0, 5.0],
            cutoff_year=2019,
            min_feature_obs=5,
            enforce_sign_gate=True,
        )
        assert len(results) == 2
        for e in results:
            assert math.isfinite(e.train_brier)
            assert e.n_sparse_clamped >= 0
            assert e.n_sign_violated >= 0

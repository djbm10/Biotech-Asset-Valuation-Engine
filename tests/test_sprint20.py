"""
Sprint 20 tests — CalibratedPOS bridge.

Tests the resolve_base_rate() and compute_phase_pos_calibrated() bridge
between CalibratedPOSModel (Sprint 17) and the industry-prior POS model.

All tests use synthetic CalibratedPOSModel data — no live DB calls.
"""
from __future__ import annotations

import math
import pytest

from bve.analysis.calibration_metrics import OutcomeRecord, PredictionRecord
from bve.analysis.pos_bridge import (
    BaseRateSource,
    BaseRateSourceType,
    _DEFAULT_BLEND_THRESHOLD,
    compute_phase_pos_calibrated,
    pos_delta,
    resolve_base_rate,
)
from bve.models.pos_calibrated import (
    N_FULL_POSTERIOR,
    N_PRIOR_ONLY,
    CalibratedPOSModel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pred(program_id, ta="oncology", phase="phase_2", model_pos=0.50):
    return PredictionRecord(
        program_id=program_id, ticker="X", ta=ta, phase=phase, model_pos=model_pos
    )


def _make_outcome(program_id, outcome_type="approval"):
    return OutcomeRecord(program_id=program_id, outcome_type=outcome_type)


def _build_model(ta="oncology", phase="phase_2", n_success=30, n_fail=20):
    """Build a CalibratedPOSModel with N_FULL_POSTERIOR outcomes → blend_weight=1."""
    preds, outcomes = [], []
    for i in range(n_success):
        pid = f"{ta}_{phase}_S{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "approval"))
    for i in range(n_fail):
        pid = f"{ta}_{phase}_F{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "failure_efficacy"))
    return CalibratedPOSModel.from_records(preds, outcomes)


def _build_full_model(ta="oncology", phase="phase_2", n_success=40, n_fail=10):
    """Build a model with N >= N_FULL_POSTERIOR to get blend_weight=1.0."""
    preds, outcomes = [], []
    for i in range(n_success):
        pid = f"{ta}_{phase}_S{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "approval"))
    for i in range(n_fail):
        pid = f"{ta}_{phase}_F{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "failure_efficacy"))
    return CalibratedPOSModel.from_records(preds, outcomes)


# ===========================================================================
# TestBaseRateSource
# ===========================================================================

class TestBaseRateSource:
    def test_dataclass_fields(self):
        src = BaseRateSource(rate=0.42, source="industry_prior")
        assert src.rate == 0.42
        assert src.source == "industry_prior"
        assert src.blend_weight is None
        assert src.n_outcomes is None

    def test_calibrated_fields_populated(self):
        src = BaseRateSource(rate=0.55, source="calibrated", blend_weight=0.80, n_outcomes=45)
        assert src.blend_weight == 0.80
        assert src.n_outcomes == 45


# ===========================================================================
# TestResolveBaseRate — no cal_model
# ===========================================================================

class TestResolveBaseRateNoCal:
    def test_returns_industry_prior_for_known_ta(self):
        result = resolve_base_rate("oncology", "phase_2", None)
        assert result.source == "industry_prior"
        assert 0.0 < result.rate < 1.0

    def test_returns_fallback_for_unknown_ta(self):
        result = resolve_base_rate("xyzzy_unknown", "phase_99", None)
        # Falls through to industry "all" bucket or fallback
        assert result.source in ("industry_prior", "fallback")
        assert 0.0 < result.rate < 1.0

    def test_case_insensitive_ta(self):
        r1 = resolve_base_rate("oncology", "phase_2", None)
        r2 = resolve_base_rate("ONCOLOGY", "PHASE_2", None)
        assert r1.rate == pytest.approx(r2.rate)

    def test_blend_weight_none_for_industry_prior(self):
        result = resolve_base_rate("oncology", "phase_2", None)
        assert result.blend_weight is None

    def test_n_outcomes_none_for_industry_prior(self):
        result = resolve_base_rate("oncology", "phase_2", None)
        assert result.n_outcomes is None


# ===========================================================================
# TestResolveBaseRate — with cal_model
# ===========================================================================

class TestResolveBaseRateWithCal:
    def test_uses_calibrated_when_blend_above_threshold(self):
        # N=50 → blend_weight=1.0 → above threshold
        model = _build_full_model(n_success=40, n_fail=10)
        result = resolve_base_rate("oncology", "phase_2", model)
        assert result.source == "calibrated"

    def test_falls_back_to_prior_when_blend_below_threshold(self):
        # N=5 → blend_weight=0.0 → below any threshold
        preds = [_make_pred(f"P{i}", ta="oncology", phase="phase_2") for i in range(5)]
        outcomes = [_make_outcome(f"P{i}", "approval") for i in range(5)]
        model = CalibratedPOSModel.from_records(preds, outcomes)
        result = resolve_base_rate("oncology", "phase_2", model, blend_threshold=0.10)
        # blend_weight=0.0 < 0.10 → should fall through to industry prior
        assert result.source == "industry_prior"

    def test_blend_weight_reported_when_calibrated(self):
        model = _build_full_model(n_success=40, n_fail=10)
        result = resolve_base_rate("oncology", "phase_2", model)
        assert result.blend_weight is not None
        assert result.blend_weight > 0

    def test_n_outcomes_reported_when_calibrated(self):
        model = _build_full_model(n_success=40, n_fail=10)
        result = resolve_base_rate("oncology", "phase_2", model)
        assert result.n_outcomes == 50

    def test_calibrated_unknown_bin_falls_back_to_prior(self):
        model = _build_full_model(ta="oncology", phase="phase_2")
        # Ask for immunology/phase_3 — not in calibrated bins
        result = resolve_base_rate("immunology", "phase_3", model)
        assert result.source in ("industry_prior", "fallback")

    def test_calibration_rate_differs_from_prior(self):
        # 80% success rate → posterior much higher than typical ~40% industry prior
        model = _build_full_model(n_success=40, n_fail=10)
        cal_result = resolve_base_rate("oncology", "phase_2", model)
        prior_result = resolve_base_rate("oncology", "phase_2", None)
        assert cal_result.rate != pytest.approx(prior_result.rate, abs=0.05)

    def test_threshold_controls_calibration_acceptance(self):
        # Mid-range N — blend_weight ~0.5
        n_mid = (N_PRIOR_ONLY + N_FULL_POSTERIOR) // 2
        preds = [_make_pred(f"P{i}", ta="oncology", phase="phase_2") for i in range(n_mid)]
        outcomes_s = [_make_outcome(f"P{i}", "approval") for i in range(n_mid // 2)]
        outcomes_f = [_make_outcome(f"P{i}", "failure_efficacy") for i in range(n_mid // 2, n_mid)]
        model = CalibratedPOSModel.from_records(preds, outcomes_s + outcomes_f)

        # Low threshold → calibration accepted
        r_low = resolve_base_rate("oncology", "phase_2", model, blend_threshold=0.01)
        # High threshold → industry prior used
        r_high = resolve_base_rate("oncology", "phase_2", model, blend_threshold=0.99)
        assert r_low.source == "calibrated"
        assert r_high.source == "industry_prior"


# ===========================================================================
# TestComputePhasePosCal
# ===========================================================================

class TestComputePhasePosCal:
    def test_returns_float_in_01(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        pos = compute_phase_pos_calibrated(
            TrialPhase.PHASE_2,
            TherapeuticArea.ONCOLOGY,
            cal_model=None,
        )
        assert 0.0 < pos < 1.0

    def test_matches_compute_phase_pos_without_cal_model(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase
        from bve.models.pos_model import compute_pos as compute_phase_pos

        ta = TherapeuticArea.ONCOLOGY
        phase = TrialPhase.PHASE_2

        pos_standard = compute_phase_pos(phase, ta)
        pos_bridge = compute_phase_pos_calibrated(phase, ta, cal_model=None)
        assert pos_standard == pytest.approx(pos_bridge, abs=0.001)

    def test_calibrated_model_changes_result(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase
        from bve.models.pos_model import compute_pos as compute_phase_pos

        ta = TherapeuticArea.ONCOLOGY
        phase = TrialPhase.PHASE_2

        # 80% success rate → calibrated posterior much higher than industry prior
        model = _build_full_model(n_success=40, n_fail=10)
        pos_cal = compute_phase_pos_calibrated(phase, ta, cal_model=model)
        pos_std = compute_phase_pos(phase, ta)

        # Calibrated model should give higher PoS (posterior 80% vs ~40% prior)
        assert pos_cal > pos_std

    def test_low_n_calibrated_model_does_not_change_result(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase
        from bve.models.pos_model import compute_pos as compute_phase_pos

        ta = TherapeuticArea.ONCOLOGY
        phase = TrialPhase.PHASE_2

        # N=5 → blend_weight=0.0 → below threshold → falls back to prior
        preds = [_make_pred(f"P{i}", ta="oncology", phase="phase_2") for i in range(5)]
        outcomes = [_make_outcome(f"P{i}", "approval") for i in range(5)]
        model = CalibratedPOSModel.from_records(preds, outcomes)

        pos_cal = compute_phase_pos_calibrated(phase, ta, cal_model=model)
        pos_std = compute_phase_pos(phase, ta)
        assert pos_cal == pytest.approx(pos_std, abs=0.001)

    def test_result_monotone_with_calibrated_rate(self):
        """Higher posterior success rate → higher calibrated PoS (all else equal)."""
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        ta = TherapeuticArea.ONCOLOGY
        phase = TrialPhase.PHASE_2

        model_high = _build_full_model(n_success=45, n_fail=5)   # 90%
        model_low = _build_full_model(n_success=5, n_fail=45)    # 10%

        pos_high = compute_phase_pos_calibrated(phase, ta, cal_model=model_high)
        pos_low = compute_phase_pos_calibrated(phase, ta, cal_model=model_low)
        assert pos_high > pos_low


# ===========================================================================
# TestPOSDelta
# ===========================================================================

class TestPOSDelta:
    def test_returns_none_for_insufficient_data(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        preds = [_make_pred(f"P{i}", ta="oncology", phase="phase_2") for i in range(5)]
        outcomes = [_make_outcome(f"P{i}", "approval") for i in range(5)]
        model = CalibratedPOSModel.from_records(preds, outcomes)

        delta = pos_delta(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, model)
        assert delta is None

    def test_returns_float_for_full_calibration(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        model = _build_full_model(n_success=40, n_fail=10)
        delta = pos_delta(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, model)
        assert isinstance(delta, float)

    def test_positive_delta_when_posterior_above_prior(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        # 80% posterior >> typical ~40% Phase 2 oncology prior
        model = _build_full_model(n_success=40, n_fail=10)
        delta = pos_delta(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, model)
        assert delta is not None and delta > 0

    def test_negative_delta_when_posterior_below_prior(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        # 10% posterior << typical ~40% Phase 2 prior
        model = _build_full_model(n_success=5, n_fail=45)
        delta = pos_delta(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, model)
        assert delta is not None and delta < 0

    def test_unknown_bin_returns_none(self):
        from bve.entities.asset import TherapeuticArea
        from bve.entities.trial import TrialPhase

        model = _build_full_model(ta="oncology", phase="phase_2")
        # Immunology is not in the calibrated bins
        delta = pos_delta(TrialPhase.PHASE_3, TherapeuticArea.IMMUNOLOGY, model)
        assert delta is None

"""
Tests for PhaseCorrelationUpdater — Bayesian Phase 2→3 PoS update.

Required scenarios:
1. Strong Phase 2 RCT result → posterior increases within cap
2. Weak Phase 2 result → posterior decreases within cap
3. Single-arm Phase 2 → z-score shrunk by 0.60
4. Posterior cap enforced (raw posterior exceeds ±25pp)
5. Phase 1 only → smaller update applied
6. No prior phase data → posterior unchanged, update_applied=False
7. All proposals use ChangeMode.BOUNDED
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

import pytest
from scipy.stats import norm

from bve.intelligence.phase_correlation_updater import (
    PhaseCorrelationUpdater,
    PhaseCorrelationResult,
    _sigmoid,
    _bayesian_update,
    _z_from_signal,
    _safety_z_from_grade,
    _parse_structured_signal,
)
from bve.intelligence.taxonomy import ChangeMode


# ---------------------------------------------------------------------------
# Test config (injected, no YAML dependency)
# ---------------------------------------------------------------------------

_TEST_CONFIG = {
    "alpha":                      0.0,
    "beta":                       0.50,
    "max_update_pp":              0.25,
    "single_arm_z_shrinkage":     0.60,
    "phase1_beta":                0.25,
    "phase1_max_update_fraction": 0.33,
    "proposal_bound_pct":         80.0,
}


@pytest.fixture
def updater() -> PhaseCorrelationUpdater:
    return PhaseCorrelationUpdater(config=_TEST_CONFIG)


# ---------------------------------------------------------------------------
# Minimal fake StructuredSignalRecord (only payload_json and id needed)
# ---------------------------------------------------------------------------

@dataclass
class _FakeRecord:
    id: str
    payload_json: dict
    extraction_result_id: str = "ext-test"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _make_payload(
    trial_phase: str = "phase_2",
    p_value: Optional[float] = None,
    primary_endpoint_met: Optional[bool] = None,
    randomization: Optional[str] = "randomized",
    hazard_ratio: Optional[float] = None,
    estimated_effect_size: Optional[float] = None,
    safety_grade: Optional[int] = None,
    **extra,
) -> dict:
    """Build a minimal StructuredSignal-compatible payload dict."""
    return {
        "id":                    "sig-test-001",
        "event_id":              "evt-test-001",
        "asset_id":              "asset-test-001",
        "company_id":            "co-test-001",
        "event_type":            "trial_readout",
        "signal_date":           "2025-01-15",
        "created_at":            "2025-01-15T12:00:00Z",
        "extraction_confidence": 0.85,
        # Clinical facts
        "trial_phase":           trial_phase,
        "p_value":               p_value,
        "primary_endpoint_met":  primary_endpoint_met,
        "randomization":         randomization,
        "hazard_ratio":          hazard_ratio,
        "estimated_effect_size": estimated_effect_size,
        "safety_grade":          safety_grade,
        **extra,
    }


def _record(payload: dict, rec_id: str = "rec-001") -> _FakeRecord:
    return _FakeRecord(id=rec_id, payload_json=payload)


# ---------------------------------------------------------------------------
# Scenario 1: Strong Phase 2 RCT result → posterior increases within cap
# ---------------------------------------------------------------------------

class TestStrongPhase2RCT:
    """p_value=0.01, met=True, randomized → positive update, within ±25pp."""

    def test_posterior_increases(self, updater):
        signal = _record(_make_payload(
            trial_phase="phase_2",
            p_value=0.01,
            primary_endpoint_met=True,
            randomization="randomized",
        ))
        result = updater.update("asset-A", "engine-A", 0.40, [signal])
        assert result.update_applied
        assert result.posterior_pos > result.prior_pos, (
            f"Expected posterior > prior. prior={result.prior_pos}, "
            f"posterior={result.posterior_pos}"
        )

    def test_phase_data_source_is_phase2(self, updater):
        signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True))
        result = updater.update("asset-A", "engine-A", 0.40, [signal])
        assert result.phase_data_source == "phase_2"

    def test_delta_within_max_update_pp(self, updater):
        signal = _record(_make_payload(p_value=0.001, primary_endpoint_met=True))
        result = updater.update("asset-A", "engine-A", 0.40, [signal])
        delta = abs(result.posterior_pos - result.prior_pos)
        assert delta <= _TEST_CONFIG["max_update_pp"] + 1e-6

    def test_no_single_arm_penalty(self, updater):
        signal = _record(_make_payload(p_value=0.01, randomization="randomized"))
        result = updater.update("asset-A", "engine-A", 0.40, [signal])
        assert not result.single_arm_penalty_applied

    def test_z_raw_positive_for_significant_result(self, updater):
        signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True))
        result = updater.update("asset-A", "engine-A", 0.40, [signal])
        assert result.z_raw is not None and result.z_raw > 0

    def test_likelihood_above_half(self, updater):
        """Positive z → likelihood > 0.5."""
        signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True))
        result = updater.update("asset-A", "engine-A", 0.40, [signal])
        assert result.likelihood is not None and result.likelihood > 0.5


# ---------------------------------------------------------------------------
# Scenario 2: Weak Phase 2 result → posterior decreases within cap
# ---------------------------------------------------------------------------

class TestWeakPhase2Result:
    """p_value=0.80, met=False, randomized → posterior decreases."""

    def test_posterior_decreases(self, updater):
        signal = _record(_make_payload(
            p_value=0.80,
            primary_endpoint_met=False,
            randomization="randomized",
        ))
        result = updater.update("asset-B", "engine-B", 0.40, [signal])
        assert result.update_applied
        assert result.posterior_pos < result.prior_pos, (
            f"Expected posterior < prior. prior={result.prior_pos}, "
            f"posterior={result.posterior_pos}"
        )

    def test_z_raw_negative(self, updater):
        """met=False → z should be negative."""
        signal = _record(_make_payload(p_value=0.80, primary_endpoint_met=False))
        result = updater.update("asset-B", "engine-B", 0.40, [signal])
        assert result.z_raw is not None and result.z_raw < 0

    def test_likelihood_below_half(self, updater):
        """Negative z → likelihood < 0.5."""
        signal = _record(_make_payload(p_value=0.80, primary_endpoint_met=False))
        result = updater.update("asset-B", "engine-B", 0.40, [signal])
        assert result.likelihood is not None and result.likelihood < 0.5

    def test_delta_within_max_update_pp(self, updater):
        signal = _record(_make_payload(p_value=0.80, primary_endpoint_met=False))
        result = updater.update("asset-B", "engine-B", 0.40, [signal])
        delta = abs(result.posterior_pos - result.prior_pos)
        assert delta <= _TEST_CONFIG["max_update_pp"] + 1e-6

    def test_hazard_ratio_greater_than_one_decreases_posterior(self, updater):
        """HR > 1 → treatment harm → z = -log(HR) < 0 → decreased posterior."""
        signal = _record(_make_payload(
            p_value=None, hazard_ratio=1.30, randomization="randomized"
        ))
        result = updater.update("asset-B", "engine-B", 0.40, [signal])
        assert result.posterior_pos < result.prior_pos


# ---------------------------------------------------------------------------
# Scenario 3: Single-arm Phase 2 → z shrunk by 0.60
# ---------------------------------------------------------------------------

class TestSingleArmShrinkage:
    """Single-arm trial: z_adjusted = z_raw × 0.60."""

    def test_single_arm_penalty_applied(self, updater):
        signal = _record(_make_payload(
            p_value=0.01, primary_endpoint_met=True, randomization="single_arm"
        ))
        result = updater.update("asset-C", "engine-C", 0.40, [signal])
        assert result.single_arm_penalty_applied

    def test_non_randomized_penalty_applied(self, updater):
        signal = _record(_make_payload(
            p_value=0.01, primary_endpoint_met=True, randomization="non_randomized"
        ))
        result = updater.update("asset-C", "engine-C", 0.40, [signal])
        assert result.single_arm_penalty_applied

    def test_z_adjusted_is_z_raw_times_shrinkage(self, updater):
        shrinkage = _TEST_CONFIG["single_arm_z_shrinkage"]  # 0.60
        signal = _record(_make_payload(
            p_value=0.01, primary_endpoint_met=True, randomization="single_arm"
        ))
        result = updater.update("asset-C", "engine-C", 0.40, [signal])
        assert result.z_raw is not None
        assert result.z_adjusted == pytest.approx(result.z_raw * shrinkage, rel=1e-5)

    def test_single_arm_posterior_less_than_rct_posterior(self, updater):
        """Same p-value: single-arm update is smaller than RCT update (same direction)."""
        rct_signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True, randomization="randomized"))
        sa_signal  = _record(_make_payload(p_value=0.01, primary_endpoint_met=True, randomization="single_arm"))

        rct_result = updater.update("asset-C", "engine-C", 0.40, [rct_signal])
        sa_result  = updater.update("asset-C", "engine-C", 0.40, [sa_signal])

        # Both increase, but single-arm less so
        assert sa_result.posterior_pos < rct_result.posterior_pos, (
            f"Single-arm posterior ({sa_result.posterior_pos:.4f}) should be "
            f"< RCT posterior ({rct_result.posterior_pos:.4f})"
        )

    def test_randomized_trial_no_penalty(self, updater):
        signal = _record(_make_payload(p_value=0.01, randomization="randomized"))
        result = updater.update("asset-C", "engine-C", 0.40, [signal])
        assert not result.single_arm_penalty_applied
        assert result.z_adjusted == pytest.approx(result.z_raw, rel=1e-9)


# ---------------------------------------------------------------------------
# Scenario 4: Posterior cap enforced
# ---------------------------------------------------------------------------

class TestPosteriorCapEnforced:
    """Very strong Phase 2 result: raw posterior > prior + 0.25 → capped."""

    def test_cap_applied_for_very_strong_result(self, updater):
        # p=0.001 → z ≈ 3.29 → raw_posterior well above prior+0.25
        signal = _record(_make_payload(
            p_value=0.001, primary_endpoint_met=True, randomization="randomized"
        ))
        result = updater.update("asset-D", "engine-D", 0.40, [signal])
        assert result.cap_applied, (
            f"Expected cap_applied=True. raw={result.raw_posterior:.4f}, "
            f"prior={result.prior_pos}, posterior={result.posterior_pos:.4f}"
        )

    def test_posterior_not_above_prior_plus_max(self, updater):
        signal = _record(_make_payload(p_value=0.001, primary_endpoint_met=True))
        result = updater.update("asset-D", "engine-D", 0.40, [signal])
        max_allowed = result.prior_pos + _TEST_CONFIG["max_update_pp"]
        assert result.posterior_pos <= max_allowed + 1e-6

    def test_cap_applied_for_very_negative_result(self, updater):
        """Very negative Phase 2 (p=0.001, met=False) → lower bound cap."""
        signal = _record(_make_payload(
            p_value=0.001, primary_endpoint_met=False, randomization="randomized"
        ))
        result = updater.update("asset-D", "engine-D", 0.40, [signal])
        assert result.cap_applied

    def test_posterior_not_below_prior_minus_max(self, updater):
        signal = _record(_make_payload(p_value=0.001, primary_endpoint_met=False))
        result = updater.update("asset-D", "engine-D", 0.40, [signal])
        min_allowed = result.prior_pos - _TEST_CONFIG["max_update_pp"]
        assert result.posterior_pos >= min_allowed - 1e-6

    def test_raw_posterior_exceeds_cap(self, updater):
        """raw_posterior should be outside the capped range to confirm cap is doing work."""
        signal = _record(_make_payload(p_value=0.001, primary_endpoint_met=True))
        result = updater.update("asset-D", "engine-D", 0.40, [signal])
        assert result.raw_posterior is not None
        assert result.raw_posterior > result.prior_pos + _TEST_CONFIG["max_update_pp"] - 1e-6


# ---------------------------------------------------------------------------
# Scenario 5: Phase 1 only → smaller update applied
# ---------------------------------------------------------------------------

class TestPhase1OnlyPath:
    """No Phase 2 signal, clean Phase 1 safety → small positive update."""

    def _ph1_record(self, safety_grade: int) -> _FakeRecord:
        return _record(_make_payload(
            trial_phase="phase_1",
            safety_grade=safety_grade,
            p_value=None,
            randomization=None,
        ))

    def test_update_applied(self, updater):
        result = updater.update("asset-E", "engine-E", 0.30, [self._ph1_record(1)])
        assert result.update_applied
        assert result.phase_data_source == "phase_1"

    def test_clean_safety_increases_posterior(self, updater):
        """Grade 1 safety → positive safety_z → likelihood > 0.5 → posterior > prior."""
        result = updater.update("asset-E", "engine-E", 0.30, [self._ph1_record(1)])
        assert result.posterior_pos > result.prior_pos

    def test_serious_safety_decreases_posterior(self, updater):
        """Grade 4 safety → negative safety_z → posterior < prior."""
        result = updater.update("asset-E", "engine-E", 0.30, [self._ph1_record(4)])
        assert result.posterior_pos < result.prior_pos

    def test_phase1_update_smaller_than_phase2(self, updater):
        """Phase 1 update (capped at ~8pp) is smaller than Phase 2 update (capped at 25pp)."""
        ph1_record = self._ph1_record(1)
        ph2_record = _record(_make_payload(
            trial_phase="phase_2", p_value=0.01, primary_endpoint_met=True
        ))

        ph1_result = updater.update("asset-E", "engine-E", 0.30, [ph1_record])
        ph2_result = updater.update("asset-E", "engine-E", 0.30, [ph2_record])

        ph1_delta = abs(ph1_result.posterior_pos - ph1_result.prior_pos)
        ph2_delta = abs(ph2_result.posterior_pos - ph2_result.prior_pos)

        assert ph1_delta < ph2_delta, (
            f"Phase 1 delta ({ph1_delta:.4f}) should be < Phase 2 delta ({ph2_delta:.4f})"
        )

    def test_phase1_absolute_cap_is_smaller(self, updater):
        """Phase 1 max update = max_update_pp × fraction ≈ 0.083."""
        ph1_max = _TEST_CONFIG["max_update_pp"] * _TEST_CONFIG["phase1_max_update_fraction"]
        result = updater.update("asset-E", "engine-E", 0.30, [self._ph1_record(1)])
        delta = abs(result.posterior_pos - result.prior_pos)
        assert delta <= ph1_max + 1e-6

    def test_phase2_preferred_over_phase1(self, updater):
        """When both Phase 1 and Phase 2 records exist, Phase 2 is used."""
        ph1 = self._ph1_record(1)
        ph2 = _record(_make_payload(
            trial_phase="phase_2", p_value=0.01, primary_endpoint_met=True
        ))
        result = updater.update("asset-E", "engine-E", 0.30, [ph1, ph2])
        assert result.phase_data_source == "phase_2"


# ---------------------------------------------------------------------------
# Scenario 6: No prior phase data → posterior unchanged
# ---------------------------------------------------------------------------

class TestNoPriorData:
    def test_no_signals_returns_prior(self, updater):
        result = updater.update("asset-F", "engine-F", 0.45, [])
        assert not result.update_applied
        assert result.posterior_pos == pytest.approx(result.prior_pos)

    def test_skip_reason_set(self, updater):
        result = updater.update("asset-F", "engine-F", 0.45, [])
        assert result.skip_reason is not None
        assert len(result.skip_reason) > 0

    def test_proposal_is_none(self, updater):
        result = updater.update("asset-F", "engine-F", 0.45, [])
        assert result.proposal is None

    def test_phase_data_source_is_none(self, updater):
        result = updater.update("asset-F", "engine-F", 0.45, [])
        assert result.phase_data_source is None

    def test_nda_bla_signals_not_used(self, updater):
        """Signals with trial_phase=nda_bla do not trigger an update."""
        nda_signal = _record(_make_payload(trial_phase="nda_bla", p_value=0.01))
        result = updater.update("asset-F", "engine-F", 0.45, [nda_signal])
        assert not result.update_applied

    def test_phase1_no_safety_grade_skips(self, updater):
        """Phase 1 signal without safety_grade → no update."""
        ph1 = _record(_make_payload(
            trial_phase="phase_1", safety_grade=None, p_value=None
        ))
        result = updater.update("asset-F", "engine-F", 0.45, [ph1])
        assert not result.update_applied

    def test_phase2_no_quantitative_data_skips(self, updater):
        """Phase 2 signal with only enrollment_status (no p/HR/effect) → no update."""
        ph2 = _record(_make_payload(
            trial_phase="phase_2",
            p_value=None, hazard_ratio=None,
            estimated_effect_size=None, primary_endpoint_met=None,
        ))
        result = updater.update("asset-F", "engine-F", 0.45, [ph2])
        assert not result.update_applied


# ---------------------------------------------------------------------------
# Scenario 7: All proposals use ChangeMode.BOUNDED
# ---------------------------------------------------------------------------

class TestProposalMode:
    def test_phase2_proposal_is_bounded(self, updater):
        signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True))
        result = updater.update("asset-G", "engine-G", 0.40, [signal])
        assert result.proposal is not None
        assert result.proposal.change_mode == ChangeMode.BOUNDED

    def test_phase1_proposal_is_bounded(self, updater):
        ph1 = _record(_make_payload(trial_phase="phase_1", safety_grade=1, p_value=None))
        result = updater.update("asset-G", "engine-G", 0.40, [ph1])
        assert result.proposal is not None
        assert result.proposal.change_mode == ChangeMode.BOUNDED

    def test_proposal_bound_pct_set(self, updater):
        signal = _record(_make_payload(p_value=0.05, primary_endpoint_met=True))
        result = updater.update("asset-G", "engine-G", 0.40, [signal])
        assert result.proposal is not None
        assert result.proposal.bound_pct == _TEST_CONFIG["proposal_bound_pct"]

    def test_proposal_parameter_path(self, updater):
        signal = _record(_make_payload(p_value=0.05))
        result = updater.update("asset-G", "engine-G", 0.40, [signal])
        assert result.proposal is not None
        assert result.proposal.parameter_path == "trials[*].success_probability"

    def test_proposal_within_bound_pct(self, updater):
        signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True))
        result = updater.update("asset-G", "engine-G", 0.40, [signal])
        assert result.proposal is not None
        assert abs(result.proposal.proposed_delta_pct) <= result.proposal.bound_pct + 1e-6

    def test_rationale_format(self, updater):
        signal = _record(_make_payload(p_value=0.01, primary_endpoint_met=True))
        result = updater.update("asset-G", "engine-G", 0.40, [signal])
        assert result.proposal is not None
        rationale = result.proposal.rationale
        assert "z=" in rationale
        assert "likelihood=" in rationale
        assert "posterior" in rationale
        assert "prior" in rationale


# ---------------------------------------------------------------------------
# Math helper unit tests
# ---------------------------------------------------------------------------

class TestMathHelpers:
    def test_sigmoid_zero(self):
        assert _sigmoid(0.0) == pytest.approx(0.5)

    def test_sigmoid_positive(self):
        assert _sigmoid(2.0) > 0.5

    def test_sigmoid_negative(self):
        assert _sigmoid(-2.0) < 0.5

    def test_bayesian_update_neutral(self):
        """L=0.5 (z=0) → posterior = prior."""
        assert _bayesian_update(0.40, 0.5) == pytest.approx(0.40)

    def test_bayesian_update_increases(self):
        assert _bayesian_update(0.40, 0.70) > 0.40

    def test_bayesian_update_decreases(self):
        assert _bayesian_update(0.40, 0.30) < 0.40

    def test_z_from_signal_p_value_positive(self):
        """p=0.01, met=True → positive z ≈ 2.576."""
        from bve.intelligence.schemas.signals import StructuredSignal
        sig = StructuredSignal(
            id="s1", event_id="e1", asset_id="a1", company_id="c1",
            event_type="trial_readout",
            signal_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            p_value=0.01, primary_endpoint_met=True,
        )
        z = _z_from_signal(sig)
        assert z is not None
        assert z == pytest.approx(float(norm.ppf(0.995)), rel=1e-4)

    def test_z_from_signal_p_value_negative(self):
        """p=0.01, met=False → negative z."""
        from bve.intelligence.schemas.signals import StructuredSignal
        sig = StructuredSignal(
            id="s1", event_id="e1", asset_id="a1", company_id="c1",
            event_type="trial_readout",
            signal_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            p_value=0.01, primary_endpoint_met=False,
        )
        z = _z_from_signal(sig)
        assert z is not None
        assert z < 0

    def test_z_from_signal_hazard_ratio(self):
        """HR=0.70 → z = -log(0.70) ≈ +0.357 (positive = benefit)."""
        from bve.intelligence.schemas.signals import StructuredSignal
        sig = StructuredSignal(
            id="s1", event_id="e1", asset_id="a1", company_id="c1",
            event_type="trial_readout",
            signal_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            hazard_ratio=0.70,
        )
        z = _z_from_signal(sig)
        assert z is not None
        assert z == pytest.approx(-math.log(0.70), rel=1e-5)
        assert z > 0

    def test_z_from_signal_binary_met(self):
        from bve.intelligence.schemas.signals import StructuredSignal
        sig = StructuredSignal(
            id="s1", event_id="e1", asset_id="a1", company_id="c1",
            event_type="trial_readout",
            signal_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            primary_endpoint_met=True,
        )
        assert _z_from_signal(sig) == pytest.approx(1.96)

    def test_z_from_signal_no_data(self):
        from bve.intelligence.schemas.signals import StructuredSignal
        sig = StructuredSignal(
            id="s1", event_id="e1", asset_id="a1", company_id="c1",
            event_type="trial_readout",
            signal_date=date(2025, 1, 1),
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        assert _z_from_signal(sig) is None

    def test_safety_z_grades(self):
        assert _safety_z_from_grade(1) == pytest.approx(1.0)
        assert _safety_z_from_grade(3) == pytest.approx(0.0)
        assert _safety_z_from_grade(4) == pytest.approx(-1.0)
        assert _safety_z_from_grade(None) is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_posterior_in_01(self, updater):
        """Posterior always stays in (0, 1)."""
        for p_val in [1e-10, 0.001, 0.5, 0.999]:
            signal = _record(_make_payload(p_value=p_val, primary_endpoint_met=True))
            result = updater.update("asset-X", "engine-X", 0.30, [signal])
            assert 0.0 < result.posterior_pos < 1.0

    def test_most_recent_phase2_used(self, updater):
        """When two Phase 2 records exist, first one (most recent) is used."""
        rec1 = _FakeRecord(id="rec-recent", payload_json=_make_payload(
            p_value=0.01, primary_endpoint_met=True
        ))
        rec2 = _FakeRecord(id="rec-old", payload_json=_make_payload(
            p_value=0.90, primary_endpoint_met=False
        ))
        result = updater.update("asset-X", "engine-X", 0.40, [rec1, rec2])
        assert result.signal_id == "rec-recent"
        assert result.posterior_pos > result.prior_pos  # positive from rec1

    def test_parse_structured_signal_returns_none_on_bad_json(self):
        assert _parse_structured_signal({"bad": "data"}) is None

    def test_parse_structured_signal_succeeds_on_valid_payload(self):
        payload = _make_payload(p_value=0.05, primary_endpoint_met=True)
        sig = _parse_structured_signal(payload)
        assert sig is not None
        assert sig.p_value == pytest.approx(0.05)

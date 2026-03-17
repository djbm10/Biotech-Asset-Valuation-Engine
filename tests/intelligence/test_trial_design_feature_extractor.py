"""
Tests for TrialDesignFeatureExtractor — pre-readout trial design scoring.

Four required scenarios:
1. Randomized double-blind OS endpoint trial  → RCT_COMPARATIVE + HARD_CLINICAL → positive PoS adj
2. Single-arm surrogate endpoint trial        → SINGLE_ARM + SURROGATE_VALIDATED → negative PoS adj
3. Underpowered Phase 3 (n=50)                → low_power_flag=True, adjusted_pos < base_pos
4. Breakthrough-effect relaxation             → relaxation_applied=True, low_power_flag=False
"""
from __future__ import annotations

import pytest

from bve.intelligence.trial_design_feature_extractor import (
    PreReadoutAssessment,
    TrialDesignFeatureExtractor,
    _power_from_params,
    _clamp_proposed_pos,
)
from bve.models.trial_design_features import (
    EndpointBasis,
    EvidenceDesign,
    ApprovalPathway,
)


# ---------------------------------------------------------------------------
# Minimal CT record builders
# ---------------------------------------------------------------------------

def _build_ct_record(
    nct_id: str = "NCT12345678",
    phases: list | None = None,
    allocation: str = "RANDOMIZED",
    masking: str = "DOUBLE",
    primary_outcome_measure: str = "Overall Survival",
    enrollment_count: int | None = 400,
    title: str = "A Phase 3 Trial",
) -> dict:
    """Build a minimal CT v2 protocolSection-style record."""
    record: dict = {
        "protocolSection": {
            "identificationModule": {
                "nctId":      nct_id,
                "briefTitle": title,
            },
            "designModule": {
                "phases": phases if phases is not None else ["PHASE3"],
                "designInfo": {
                    "allocation":  allocation,
                    "maskingInfo": {"masking": masking},
                },
            },
            "outcomesModule": {
                "primaryOutcomes": [
                    {"measure": primary_outcome_measure},
                ],
            },
        }
    }
    if enrollment_count is not None:
        record["protocolSection"]["designModule"]["enrollmentInfo"] = {
            "count": enrollment_count
        }
    return record


# ---------------------------------------------------------------------------
# Extractor fixture with config injected (avoids YAML file dependency)
# ---------------------------------------------------------------------------

_TEST_CONFIG = {
    "design_scoring_max_update_pp": 0.15,
    "low_power_threshold": 0.70,
    "low_power_logodds_penalty_scale": 0.20,
    "breakthrough_effect_multiplier": 1.5,
    "proposal_bound_pct": 50.0,
    "historical_median_n": {
        "default": {"phase_2": 150, "phase_3": 380},
    },
    "historical_effect_size_default": 0.15,
}


@pytest.fixture
def extractor() -> TrialDesignFeatureExtractor:
    return TrialDesignFeatureExtractor(config=_TEST_CONFIG)


# ---------------------------------------------------------------------------
# Scenario 1: Randomized double-blind OS endpoint trial
# ---------------------------------------------------------------------------

class TestRCTHardClinical:
    """Randomized, double-blind, OS-endpoint Phase 3 → positive PoS adjustment."""

    def test_evidence_design_is_rct_comparative(self, extractor):
        record = _build_ct_record(
            allocation="RANDOMIZED",
            masking="DOUBLE",
            primary_outcome_measure="Overall Survival",
        )
        result = extractor.assess(record, "asset-001", "engine-001", base_pos=0.45)
        assert not result.assessment_skipped
        assert result.features.evidence_design == EvidenceDesign.RCT_COMPARATIVE

    def test_endpoint_basis_is_hard_clinical(self, extractor):
        record = _build_ct_record(
            primary_outcome_measure="Overall Survival (OS)",
        )
        result = extractor.assess(record, "asset-001", "engine-001", base_pos=0.45)
        assert result.features.endpoint_basis == EndpointBasis.HARD_CLINICAL

    def test_adjusted_pos_exceeds_base_pos(self, extractor):
        """Hard clinical + RCT_COMPARATIVE → positive design log-odds → adjusted > base."""
        record = _build_ct_record(
            allocation="RANDOMIZED",
            masking="DOUBLE",
            primary_outcome_measure="Overall Survival",
            enrollment_count=400,
        )
        result = extractor.assess(record, "asset-001", "engine-001", base_pos=0.45)
        assert result.adjusted_pos > result.base_pos, (
            f"Expected positive adjustment: base={result.base_pos}, adj={result.adjusted_pos}"
        )

    def test_proposal_is_bounded(self, extractor):
        record = _build_ct_record()
        result = extractor.assess(record, "asset-001", "engine-001", base_pos=0.45)
        from bve.intelligence.taxonomy import ChangeMode
        assert result.proposal is not None
        assert result.proposal.change_mode == ChangeMode.BOUNDED

    def test_proposal_within_bound_pct(self, extractor):
        record = _build_ct_record()
        result = extractor.assess(record, "asset-001", "engine-001", base_pos=0.45)
        assert result.proposal is not None
        assert abs(result.proposal.proposed_delta_pct) <= result.proposal.bound_pct + 1e-6

    def test_nct_id_in_signal_id(self, extractor):
        record = _build_ct_record(nct_id="NCT99887766")
        result = extractor.assess(record, "asset-001", "engine-001", base_pos=0.45)
        assert result.proposal is not None
        assert "NCT99887766" in result.proposal.signal_id


# ---------------------------------------------------------------------------
# Scenario 2: Single-arm surrogate endpoint Phase 3 trial
# ---------------------------------------------------------------------------

class TestSingleArmSurrogate:
    """Single-arm, PFS endpoint Phase 3 → negative PoS adjustment vs baseline."""

    def test_evidence_design_is_single_arm(self, extractor):
        record = _build_ct_record(
            allocation="",        # not randomized
            masking="NONE",
            primary_outcome_measure="Progression-Free Survival",
        )
        result = extractor.assess(record, "asset-002", "engine-002", base_pos=0.45)
        assert result.features.evidence_design == EvidenceDesign.SINGLE_ARM

    def test_endpoint_basis_is_surrogate_validated(self, extractor):
        record = _build_ct_record(
            primary_outcome_measure="Progression-Free Survival",
        )
        result = extractor.assess(record, "asset-002", "engine-002", base_pos=0.45)
        assert result.features.endpoint_basis == EndpointBasis.SURROGATE_VALIDATED

    def test_adjusted_pos_below_rct_adjusted_pos(self, extractor):
        """Single-arm has lower PoS than RCT at Phase 3 due to evidence_design penalty."""
        base = 0.45

        rct_record = _build_ct_record(
            allocation="RANDOMIZED", masking="DOUBLE",
            primary_outcome_measure="Progression-Free Survival",
            enrollment_count=400,
        )
        sa_record = _build_ct_record(
            allocation="", masking="NONE",
            primary_outcome_measure="Progression-Free Survival",
            enrollment_count=400,
        )

        rct_result = extractor.assess(rct_record, "asset-002", "engine-002", base_pos=base)
        sa_result  = extractor.assess(sa_record,  "asset-002", "engine-002", base_pos=base)

        assert sa_result.adjusted_pos < rct_result.adjusted_pos, (
            f"Single-arm ({sa_result.adjusted_pos:.4f}) should be < RCT ({rct_result.adjusted_pos:.4f})"
        )

    def test_phase_is_phase3(self, extractor):
        record = _build_ct_record(phases=["PHASE3"])
        result = extractor.assess(record, "asset-002", "engine-002", base_pos=0.45)
        assert result.phase == "phase_3"


# ---------------------------------------------------------------------------
# Scenario 3: Underpowered Phase 3 (n=50)
# ---------------------------------------------------------------------------

class TestUnderpoweredPhase3:
    """Small Phase 3 enrollment → low_power_flag=True, adjusted_pos < base_pos."""

    def test_low_power_flag_is_set(self, extractor):
        record = _build_ct_record(
            phases=["PHASE3"],
            allocation="RANDOMIZED",
            masking="DOUBLE",
            primary_outcome_measure="Overall Survival",
            enrollment_count=50,
        )
        result = extractor.assess(record, "asset-003", "engine-003", base_pos=0.50)
        assert result.low_power_flag, (
            f"Expected low_power_flag=True for n=50. power={result.power:.3f}"
        )

    def test_adjusted_pos_penalised(self, extractor):
        """With low power and good design, power penalty should offset or exceed design bonus."""
        record = _build_ct_record(
            phases=["PHASE3"],
            allocation="",        # single arm — design penalty guaranteed
            masking="NONE",
            primary_outcome_measure="Overall Survival",
            enrollment_count=50,
        )
        result = extractor.assess(record, "asset-003", "engine-003", base_pos=0.50)
        assert result.adjusted_pos < result.base_pos, (
            f"Expected adjusted_pos < base for underpowered single-arm. "
            f"base={result.base_pos}, adj={result.adjusted_pos}"
        )

    def test_power_below_threshold(self, extractor):
        record = _build_ct_record(enrollment_count=50, phases=["PHASE3"])
        result = extractor.assess(record, "asset-003", "engine-003", base_pos=0.50)
        assert result.power is not None
        assert result.power < _TEST_CONFIG["low_power_threshold"]

    def test_breakthrough_relaxation_not_applied(self, extractor):
        record = _build_ct_record(enrollment_count=50, phases=["PHASE3"])
        result = extractor.assess(record, "asset-003", "engine-003", base_pos=0.50)
        assert not result.breakthrough_relaxation_applied


# ---------------------------------------------------------------------------
# Scenario 4: Breakthrough-effect relaxation
# ---------------------------------------------------------------------------

class TestBreakthroughEffectRelaxation:
    """prior_phase_effect=0.30 > 1.5×0.15=0.225 → relaxation applied, no power penalty."""

    def test_relaxation_applied(self, extractor):
        record = _build_ct_record(
            phases=["PHASE3"],
            enrollment_count=60,   # small — would normally be underpowered
        )
        result = extractor.assess(
            record, "asset-004", "engine-004",
            base_pos=0.40,
            prior_phase_effect=0.30,   # > 1.5 × 0.15 = 0.225
        )
        assert result.breakthrough_relaxation_applied

    def test_low_power_flag_suppressed(self, extractor):
        record = _build_ct_record(
            phases=["PHASE3"],
            enrollment_count=60,
        )
        result = extractor.assess(
            record, "asset-004", "engine-004",
            base_pos=0.40,
            prior_phase_effect=0.30,
        )
        assert not result.low_power_flag, (
            "Power penalty should be suppressed when breakthrough relaxation is active"
        )

    def test_effect_size_used_is_prior(self, extractor):
        record = _build_ct_record(phases=["PHASE3"], enrollment_count=60)
        result = extractor.assess(
            record, "asset-004", "engine-004",
            base_pos=0.40,
            prior_phase_effect=0.30,
        )
        assert result.effect_size_used == pytest.approx(0.30)

    def test_no_relaxation_when_prior_effect_small(self, extractor):
        """prior_phase_effect=0.10 < 1.5×0.15 → no relaxation."""
        record = _build_ct_record(phases=["PHASE3"], enrollment_count=60)
        result = extractor.assess(
            record, "asset-004", "engine-004",
            base_pos=0.40,
            prior_phase_effect=0.10,
        )
        assert not result.breakthrough_relaxation_applied

    def test_relaxation_not_applied_when_just_below_threshold(self, extractor):
        """prior_phase_effect=0.20 < 1.5×0.15=0.225 → no relaxation."""
        record = _build_ct_record(phases=["PHASE3"], enrollment_count=60)
        result = extractor.assess(
            record, "asset-004", "engine-004",
            base_pos=0.40,
            prior_phase_effect=0.20,  # clearly below 0.225
        )
        assert not result.breakthrough_relaxation_applied


# ---------------------------------------------------------------------------
# Skip cases
# ---------------------------------------------------------------------------

class TestSkipCases:
    def test_unknown_phase_skips(self, extractor):
        record = _build_ct_record(phases=["NA"])
        result = extractor.assess(record, "asset-x", "engine-x", base_pos=0.40)
        assert result.assessment_skipped
        assert result.proposal is None

    def test_empty_phases_skips(self, extractor):
        record = _build_ct_record(phases=[])
        result = extractor.assess(record, "asset-x", "engine-x", base_pos=0.40)
        assert result.assessment_skipped

    def test_skipped_result_has_skip_reason(self, extractor):
        record = _build_ct_record(phases=[])
        result = extractor.assess(record, "asset-x", "engine-x", base_pos=0.40)
        assert result.skip_reason is not None
        assert len(result.skip_reason) > 0


# ---------------------------------------------------------------------------
# Approval pathway detection
# ---------------------------------------------------------------------------

class TestApprovalPathwayDetection:
    def test_breakthrough_keyword_in_title(self, extractor):
        record = _build_ct_record(
            title="Breakthrough Therapy Designation Phase 3 Study of Drug X"
        )
        result = extractor.assess(record, "asset-p", "engine-p", base_pos=0.40)
        assert result.features.approval_pathway == ApprovalPathway.BREAKTHROUGH_DESIGNATION

    def test_orphan_keyword(self, extractor):
        record = _build_ct_record(title="Phase 3 Orphan Drug Study in Rare Condition")
        result = extractor.assess(record, "asset-p", "engine-p", base_pos=0.40)
        assert result.features.approval_pathway == ApprovalPathway.ORPHAN_DRUG

    def test_standard_when_no_keyword(self, extractor):
        record = _build_ct_record(title="A Phase 3 Randomized Trial")
        result = extractor.assess(record, "asset-p", "engine-p", base_pos=0.40)
        assert result.features.approval_pathway == ApprovalPathway.STANDARD


# ---------------------------------------------------------------------------
# Clamping invariants
# ---------------------------------------------------------------------------

class TestClampingInvariants:
    def test_adjusted_pos_within_01(self, extractor):
        record = _build_ct_record(enrollment_count=10, phases=["PHASE3"])
        result = extractor.assess(record, "asset-c", "engine-c", base_pos=0.50)
        assert 0.0 < result.adjusted_pos < 1.0

    def test_max_delta_pp_not_exceeded(self, extractor):
        """Change should never exceed design_scoring_max_update_pp."""
        record = _build_ct_record(
            allocation="RANDOMIZED", masking="QUADRUPLE",
            primary_outcome_measure="Overall Survival",
            enrollment_count=1000,
        )
        result = extractor.assess(record, "asset-c", "engine-c", base_pos=0.45)
        delta = abs(result.adjusted_pos - result.base_pos)
        assert delta <= _TEST_CONFIG["design_scoring_max_update_pp"] + 1e-6

    def test_clamp_proposed_pos_absolute_cap(self):
        result = _clamp_proposed_pos(
            base_pos=0.50, raw_proposed=0.80, max_update_pp=0.15, bound_pct=50.0
        )
        assert abs(result - 0.50) <= 0.15 + 1e-6

    def test_clamp_proposed_pos_relative_cap(self):
        # base=0.10, bound=50% → max delta=0.05
        result = _clamp_proposed_pos(
            base_pos=0.10, raw_proposed=0.20, max_update_pp=0.15, bound_pct=50.0
        )
        assert abs(result - 0.10) <= 0.05 + 1e-6


# ---------------------------------------------------------------------------
# Power helper
# ---------------------------------------------------------------------------

class TestPowerHelper:
    def test_power_increases_with_n(self):
        p_small = _power_from_params(n=50,   effect=0.15)
        p_large = _power_from_params(n=500,  effect=0.15)
        assert p_large > p_small

    def test_well_powered_trial(self):
        """Standard Phase 3 (n=400, effect=0.20) should have power > 0.80."""
        power = _power_from_params(n=400, effect=0.20)
        assert power > 0.80

    def test_underpowered_small_n(self):
        power = _power_from_params(n=30, effect=0.15)
        assert power < 0.70

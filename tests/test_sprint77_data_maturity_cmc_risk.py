"""
Block 36 — Data Maturity + CMC Risk
TDD tests written BEFORE implementation.

Tests for:
  A: DataMaturityLevel enum + log-odds values
  B: CMCRiskLevel enum + log-odds values
  C: DataMaturityLevel phase gate (Phase 2/3 only)
  D: CMCRiskLevel penalty gate (Phase 3/NDA_BLA only)
  E: CMC early warning at Phase 1/2 for complex modalities
  F: POSAdjusters fields (data_maturity, cmc_risk defaults)
  G: Combined stacking with existing adjusters
"""
from __future__ import annotations

import warnings

import pytest

from bve.entities.trial import GeneTherapyModality, TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    TherapeuticArea,
    compute_pos,
    compute_pos_detailed,
)


# ---------------------------------------------------------------------------
# Block 36-A: DataMaturityLevel enum
# ---------------------------------------------------------------------------

class TestDataMaturityLevelEnum:

    def test_data_maturity_level_importable(self):
        from bve.models.pos_model import DataMaturityLevel
        assert DataMaturityLevel is not None

    def test_mature_final_exists(self):
        from bve.models.pos_model import DataMaturityLevel
        assert hasattr(DataMaturityLevel, "MATURE_FINAL")

    def test_interim_pre_planned_exists(self):
        from bve.models.pos_model import DataMaturityLevel
        assert hasattr(DataMaturityLevel, "INTERIM_PRE_PLANNED")

    def test_early_interim_unplanned_exists(self):
        from bve.models.pos_model import DataMaturityLevel
        assert hasattr(DataMaturityLevel, "EARLY_INTERIM_UNPLANNED")

    def test_immature_ongoing_exists(self):
        from bve.models.pos_model import DataMaturityLevel
        assert hasattr(DataMaturityLevel, "IMMATURE_ONGOING")

    def test_unknown_exists(self):
        from bve.models.pos_model import DataMaturityLevel
        assert hasattr(DataMaturityLevel, "UNKNOWN")

    def test_mature_final_logodds_zero(self):
        """MATURE_FINAL = 0.00 (reference — no adjustment)."""
        from bve.models.pos_model import DataMaturityLevel, _DATA_MATURITY_LOGODDS
        assert _DATA_MATURITY_LOGODDS[DataMaturityLevel.MATURE_FINAL] == pytest.approx(0.00, abs=1e-6)

    def test_interim_pre_planned_logodds(self):
        """INTERIM_PRE_PLANNED = -0.10."""
        from bve.models.pos_model import DataMaturityLevel, _DATA_MATURITY_LOGODDS
        assert _DATA_MATURITY_LOGODDS[DataMaturityLevel.INTERIM_PRE_PLANNED] == pytest.approx(-0.10, abs=1e-4)

    def test_early_interim_unplanned_logodds(self):
        """EARLY_INTERIM_UNPLANNED = -0.35."""
        from bve.models.pos_model import DataMaturityLevel, _DATA_MATURITY_LOGODDS
        assert _DATA_MATURITY_LOGODDS[DataMaturityLevel.EARLY_INTERIM_UNPLANNED] == pytest.approx(-0.35, abs=1e-4)

    def test_immature_ongoing_logodds(self):
        """IMMATURE_ONGOING = -0.20."""
        from bve.models.pos_model import DataMaturityLevel, _DATA_MATURITY_LOGODDS
        assert _DATA_MATURITY_LOGODDS[DataMaturityLevel.IMMATURE_ONGOING] == pytest.approx(-0.20, abs=1e-4)

    def test_unknown_logodds_zero(self):
        """UNKNOWN = 0.00 (adds flag, no point-estimate change)."""
        from bve.models.pos_model import DataMaturityLevel, _DATA_MATURITY_LOGODDS
        assert _DATA_MATURITY_LOGODDS[DataMaturityLevel.UNKNOWN] == pytest.approx(0.00, abs=1e-6)


# ---------------------------------------------------------------------------
# Block 36-B: CMCRiskLevel enum
# ---------------------------------------------------------------------------

class TestCMCRiskLevelEnum:

    def test_cmc_risk_level_importable(self):
        from bve.models.pos_model import CMCRiskLevel
        assert CMCRiskLevel is not None

    def test_proven_scalable_exists(self):
        from bve.models.pos_model import CMCRiskLevel
        assert hasattr(CMCRiskLevel, "PROVEN_SCALABLE")

    def test_late_stage_dev_exists(self):
        from bve.models.pos_model import CMCRiskLevel
        assert hasattr(CMCRiskLevel, "LATE_STAGE_DEV")

    def test_development_stage_exists(self):
        from bve.models.pos_model import CMCRiskLevel
        assert hasattr(CMCRiskLevel, "DEVELOPMENT_STAGE")

    def test_known_issues_exists(self):
        from bve.models.pos_model import CMCRiskLevel
        assert hasattr(CMCRiskLevel, "KNOWN_ISSUES")

    def test_unknown_exists(self):
        from bve.models.pos_model import CMCRiskLevel
        assert hasattr(CMCRiskLevel, "UNKNOWN")

    def test_proven_scalable_logodds_zero(self):
        """PROVEN_SCALABLE = 0.00 (reference)."""
        from bve.models.pos_model import CMCRiskLevel, _CMC_RISK_LOGODDS
        assert _CMC_RISK_LOGODDS[CMCRiskLevel.PROVEN_SCALABLE] == pytest.approx(0.00, abs=1e-6)

    def test_late_stage_dev_logodds(self):
        """LATE_STAGE_DEV = -0.10."""
        from bve.models.pos_model import CMCRiskLevel, _CMC_RISK_LOGODDS
        assert _CMC_RISK_LOGODDS[CMCRiskLevel.LATE_STAGE_DEV] == pytest.approx(-0.10, abs=1e-4)

    def test_development_stage_logodds(self):
        """DEVELOPMENT_STAGE = -0.20."""
        from bve.models.pos_model import CMCRiskLevel, _CMC_RISK_LOGODDS
        assert _CMC_RISK_LOGODDS[CMCRiskLevel.DEVELOPMENT_STAGE] == pytest.approx(-0.20, abs=1e-4)

    def test_known_issues_logodds(self):
        """KNOWN_ISSUES = -0.40."""
        from bve.models.pos_model import CMCRiskLevel, _CMC_RISK_LOGODDS
        assert _CMC_RISK_LOGODDS[CMCRiskLevel.KNOWN_ISSUES] == pytest.approx(-0.40, abs=1e-4)

    def test_unknown_logodds_zero(self):
        """UNKNOWN = 0.00 (adds flag, no point-estimate change)."""
        from bve.models.pos_model import CMCRiskLevel, _CMC_RISK_LOGODDS
        assert _CMC_RISK_LOGODDS[CMCRiskLevel.UNKNOWN] == pytest.approx(0.00, abs=1e-6)


# ---------------------------------------------------------------------------
# Block 36-C: DataMaturityLevel phase gate
# ---------------------------------------------------------------------------

class TestDataMaturityPhaseGate:

    def test_data_maturity_applies_at_phase_2(self):
        """EARLY_INTERIM_UNPLANNED at Phase 2 should reduce POS."""
        from bve.models.pos_model import DataMaturityLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_early_interim = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.EARLY_INTERIM_UNPLANNED),
        )
        assert pos_early_interim < pos_default

    def test_data_maturity_applies_at_phase_3(self):
        """EARLY_INTERIM_UNPLANNED at Phase 3 should reduce POS."""
        from bve.models.pos_model import DataMaturityLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_early_interim = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.EARLY_INTERIM_UNPLANNED),
        )
        assert pos_early_interim < pos_default

    def test_data_maturity_silent_at_phase_1(self):
        """DataMaturityLevel has no effect at Phase 1 — phase gate."""
        from bve.models.pos_model import DataMaturityLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_early_interim = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.EARLY_INTERIM_UNPLANNED),
        )
        assert pos_early_interim == pytest.approx(pos_default, abs=1e-6)

    def test_data_maturity_silent_at_nda_bla(self):
        """DataMaturityLevel has no effect at NDA/BLA — phase gate."""
        from bve.models.pos_model import DataMaturityLevel
        pos_default = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_early_interim = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.EARLY_INTERIM_UNPLANNED),
        )
        assert pos_early_interim == pytest.approx(pos_default, abs=1e-6)

    def test_data_maturity_unknown_no_pos_change_phase_2(self):
        """UNKNOWN data maturity: no point-estimate change at Phase 2."""
        from bve.models.pos_model import DataMaturityLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_unknown = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.UNKNOWN),
        )
        assert pos_unknown == pytest.approx(pos_default, abs=1e-6)

    def test_data_maturity_unknown_emits_flag_phase_2(self):
        """UNKNOWN data maturity at Phase 2 emits 'data_maturity_unknown' flag."""
        from bve.models.pos_model import DataMaturityLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.UNKNOWN),
        )
        assert "data_maturity_unknown" in result.confidence_flags

    def test_data_maturity_no_flag_phase_1(self):
        """No data_maturity_unknown flag at Phase 1 (phase gate)."""
        from bve.models.pos_model import DataMaturityLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.UNKNOWN),
        )
        assert "data_maturity_unknown" not in result.confidence_flags

    def test_mature_final_no_change_phase_2(self):
        """MATURE_FINAL (0.00) produces same result as default (UNKNOWN)."""
        from bve.models.pos_model import DataMaturityLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_mature = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.MATURE_FINAL),
        )
        assert pos_mature == pytest.approx(pos_default, abs=1e-6)


# ---------------------------------------------------------------------------
# Block 36-D: CMCRiskLevel penalty gate
# ---------------------------------------------------------------------------

class TestCMCRiskPhaseGate:

    def test_cmc_risk_applies_at_phase_3(self):
        """KNOWN_ISSUES at Phase 3 should reduce POS."""
        from bve.models.pos_model import CMCRiskLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_known_issues = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(cmc_risk=CMCRiskLevel.KNOWN_ISSUES),
        )
        assert pos_known_issues < pos_default

    def test_cmc_risk_applies_at_nda_bla(self):
        """KNOWN_ISSUES at NDA/BLA should reduce POS.
        Use ACCELERATED pathway to lower effective base rate so ceiling doesn't mask penalty.
        (NDA/BLA base rates are 0.82–0.94 → all hit 0.75 ceiling; AA discount reveals the delta.)
        """
        from bve.entities.asset import ApprovalPathwayType
        from bve.models.pos_model import CMCRiskLevel
        pos_proven = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.CARDIOVASCULAR,
            POSAdjusters(cmc_risk=CMCRiskLevel.PROVEN_SCALABLE),
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        pos_known_issues = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.CARDIOVASCULAR,
            POSAdjusters(cmc_risk=CMCRiskLevel.KNOWN_ISSUES),
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        assert pos_known_issues < pos_proven

    def test_cmc_risk_no_penalty_at_phase_1(self):
        """CMC risk has no NUMERICAL penalty at Phase 1."""
        from bve.models.pos_model import CMCRiskLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_known_issues = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(cmc_risk=CMCRiskLevel.KNOWN_ISSUES),
        )
        # Phase 1: no penalty (only early warning for complex modalities)
        assert pos_known_issues == pytest.approx(pos_default, abs=1e-6)

    def test_cmc_risk_no_penalty_at_phase_2(self):
        """CMC risk has no NUMERICAL penalty at Phase 2 (early warning only)."""
        from bve.models.pos_model import CMCRiskLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_known_issues = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(cmc_risk=CMCRiskLevel.KNOWN_ISSUES),
        )
        assert pos_known_issues == pytest.approx(pos_default, abs=1e-6)

    def test_cmc_risk_unknown_no_pos_change_phase_3(self):
        """UNKNOWN CMC at Phase 3: no point-estimate change."""
        from bve.models.pos_model import CMCRiskLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_unknown = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(cmc_risk=CMCRiskLevel.UNKNOWN),
        )
        assert pos_unknown == pytest.approx(pos_default, abs=1e-6)

    def test_cmc_risk_unknown_emits_flag_phase_3(self):
        """UNKNOWN CMC at Phase 3 emits 'cmc_risk_unknown' flag."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(cmc_risk=CMCRiskLevel.UNKNOWN),
        )
        assert "cmc_risk_unknown" in result.confidence_flags

    def test_cmc_risk_unknown_emits_flag_nda_bla(self):
        """UNKNOWN CMC at NDA/BLA emits 'cmc_risk_unknown' flag."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.NDA_BLA, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(cmc_risk=CMCRiskLevel.UNKNOWN),
        )
        assert "cmc_risk_unknown" in result.confidence_flags

    def test_cmc_risk_no_flag_phase_1_simple_modality(self):
        """UNKNOWN CMC at Phase 1 with UNKNOWN modality: no flag (non-complex modality)."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.UNKNOWN,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        assert "cmc_risk_unknown" not in result.confidence_flags
        assert "cmc_risk_unassessed_complex_modality" not in result.confidence_flags


# ---------------------------------------------------------------------------
# Block 36-E: CMC early warning for complex modalities at Phase 1/2
# ---------------------------------------------------------------------------

class TestCMCRiskEarlyWarning:

    def test_cmc_early_warning_phase_1_aav(self):
        """AAV at Phase 1 + cmc_risk=UNKNOWN → 'cmc_risk_unassessed_complex_modality' flag."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_1, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        assert "cmc_risk_unassessed_complex_modality" in result.confidence_flags

    def test_cmc_early_warning_phase_2_car_t(self):
        """CAR-T autologous at Phase 2 + cmc_risk=UNKNOWN → early warning flag."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.HEMATOLOGY,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.CAR_T_AUTOLOGOUS,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        assert "cmc_risk_unassessed_complex_modality" in result.confidence_flags

    def test_cmc_early_warning_no_pos_change(self):
        """Early warning does not change POS — only a flag."""
        from bve.models.pos_model import CMCRiskLevel
        pos_no_modality = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_aav_unknown_cmc = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        # AAV modality changes base rate, but cmc_risk=UNKNOWN should not add penalty
        # Verify: pos with cmc_risk=UNKNOWN == pos with cmc_risk=PROVEN_SCALABLE
        pos_aav_proven = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                cmc_risk=CMCRiskLevel.PROVEN_SCALABLE,
            ),
        )
        assert pos_aav_unknown_cmc == pytest.approx(pos_aav_proven, abs=1e-6)

    def test_no_early_warning_when_cmc_set_phase_1(self):
        """When cmc_risk is explicitly set (not UNKNOWN) at Phase 1, no early warning flag."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_1, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                cmc_risk=CMCRiskLevel.LATE_STAGE_DEV,
            ),
        )
        assert "cmc_risk_unassessed_complex_modality" not in result.confidence_flags

    def test_no_early_warning_at_phase_3(self):
        """At Phase 3, the flag is 'cmc_risk_unknown', not the early warning variant."""
        from bve.models.pos_model import CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_3, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        assert "cmc_risk_unknown" in result.confidence_flags
        assert "cmc_risk_unassessed_complex_modality" not in result.confidence_flags


# ---------------------------------------------------------------------------
# Block 36-F: POSAdjusters fields
# ---------------------------------------------------------------------------

class TestPOSAdjustersFields:

    def test_data_maturity_field_exists(self):
        from bve.models.pos_model import DataMaturityLevel
        adj = POSAdjusters()
        assert hasattr(adj, "data_maturity")

    def test_data_maturity_default_unknown(self):
        from bve.models.pos_model import DataMaturityLevel
        adj = POSAdjusters()
        assert adj.data_maturity == DataMaturityLevel.UNKNOWN

    def test_cmc_risk_field_exists(self):
        from bve.models.pos_model import CMCRiskLevel
        adj = POSAdjusters()
        assert hasattr(adj, "cmc_risk")

    def test_cmc_risk_default_unknown(self):
        from bve.models.pos_model import CMCRiskLevel
        adj = POSAdjusters()
        assert adj.cmc_risk == CMCRiskLevel.UNKNOWN

    def test_data_maturity_accepts_all_values(self):
        from bve.models.pos_model import DataMaturityLevel
        for val in DataMaturityLevel:
            adj = POSAdjusters(data_maturity=val)
            assert adj.data_maturity == val

    def test_cmc_risk_accepts_all_values(self):
        from bve.models.pos_model import CMCRiskLevel
        for val in CMCRiskLevel:
            adj = POSAdjusters(cmc_risk=val)
            assert adj.cmc_risk == val


# ---------------------------------------------------------------------------
# Block 36-G: Combined stacking with existing adjusters
# ---------------------------------------------------------------------------

class TestCombinedAdjusters:

    def test_stacking_data_maturity_and_cmc_risk_at_phase_3(self):
        """Both data_maturity and cmc_risk penalties apply at Phase 3."""
        from bve.models.pos_model import DataMaturityLevel, CMCRiskLevel
        pos_default = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_both = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                data_maturity=DataMaturityLevel.EARLY_INTERIM_UNPLANNED,
                cmc_risk=CMCRiskLevel.KNOWN_ISSUES,
            ),
        )
        pos_data_only = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(data_maturity=DataMaturityLevel.EARLY_INTERIM_UNPLANNED),
        )
        pos_cmc_only = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(cmc_risk=CMCRiskLevel.KNOWN_ISSUES),
        )
        # Both lower POS individually
        assert pos_data_only < pos_default
        assert pos_cmc_only < pos_default
        # Combined is lower than either alone
        assert pos_both <= pos_data_only
        assert pos_both <= pos_cmc_only

    def test_backward_compat_no_new_fields_no_change(self):
        """Existing calls without data_maturity or cmc_risk are bit-for-bit unchanged."""
        pos_old = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                moa_precedent=__import__("bve.models.pos_model", fromlist=["MoAPrecedent"]).MoAPrecedent.VALIDATED,
            ),
        )
        from bve.models.pos_model import DataMaturityLevel, CMCRiskLevel
        pos_new = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                moa_precedent=__import__("bve.models.pos_model", fromlist=["MoAPrecedent"]).MoAPrecedent.VALIDATED,
                data_maturity=DataMaturityLevel.UNKNOWN,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        assert pos_old == pytest.approx(pos_new, abs=1e-6)

    def test_multiple_flags_emitted_at_phase_3(self):
        """Both 'data_maturity_unknown' and 'cmc_risk_unknown' flags emitted when both UNKNOWN at Phase 3."""
        from bve.models.pos_model import DataMaturityLevel, CMCRiskLevel
        result = compute_pos_detailed(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                data_maturity=DataMaturityLevel.UNKNOWN,
                cmc_risk=CMCRiskLevel.UNKNOWN,
            ),
        )
        assert "data_maturity_unknown" in result.confidence_flags
        assert "cmc_risk_unknown" in result.confidence_flags

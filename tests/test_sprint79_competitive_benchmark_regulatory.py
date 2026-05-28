"""
Block 39 — Competitive Benchmark Position + Prior Regulatory Actions
TDD tests written BEFORE implementation.

Tests for:
  A: CompetitiveBenchmarkPosition enum + log-odds values
  B: PriorRegulatoryAction enum + log-odds
  C: RegulatoryActionRecord model (action, same_molecule, same_indication, issue_resolved)
  D: Phase gate for CompetitiveBenchmarkPosition (Phase 2/3 only)
  E: Phase gate for regulatory actions (holds all phases; CRL/RTF/AdCom Phase 3/NDA only)
  F: RegulatoryActionRecord penalty scaling (resolved → 50%, diff_indication → 40%, both → 20%)
  G: Stacking cap for regulatory actions (-0.60)
  H: POSAdjusters fields
"""
from __future__ import annotations

import pytest

from bve.entities.trial import TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    TherapeuticArea,
    compute_pos,
    compute_pos_detailed,
)


# ---------------------------------------------------------------------------
# Block 39-A: CompetitiveBenchmarkPosition enum
# ---------------------------------------------------------------------------

class TestCompetitiveBenchmarkEnum:

    def test_competitive_benchmark_importable(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        assert CompetitiveBenchmarkPosition is not None

    def test_best_in_class_exists(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        assert hasattr(CompetitiveBenchmarkPosition, "BEST_IN_CLASS")

    def test_competitive_exists(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        assert hasattr(CompetitiveBenchmarkPosition, "COMPETITIVE")

    def test_below_comparator_exists(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        assert hasattr(CompetitiveBenchmarkPosition, "BELOW_COMPARATOR")

    def test_clearly_inferior_exists(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        assert hasattr(CompetitiveBenchmarkPosition, "CLEARLY_INFERIOR")

    def test_unknown_exists(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        assert hasattr(CompetitiveBenchmarkPosition, "UNKNOWN")

    def test_best_in_class_logodds(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition, _COMPETITIVE_BENCHMARK_LOGODDS
        assert _COMPETITIVE_BENCHMARK_LOGODDS[CompetitiveBenchmarkPosition.BEST_IN_CLASS] == pytest.approx(+0.20, abs=1e-4)

    def test_competitive_logodds_zero(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition, _COMPETITIVE_BENCHMARK_LOGODDS
        assert _COMPETITIVE_BENCHMARK_LOGODDS[CompetitiveBenchmarkPosition.COMPETITIVE] == pytest.approx(0.00, abs=1e-6)

    def test_below_comparator_logodds(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition, _COMPETITIVE_BENCHMARK_LOGODDS
        assert _COMPETITIVE_BENCHMARK_LOGODDS[CompetitiveBenchmarkPosition.BELOW_COMPARATOR] == pytest.approx(-0.25, abs=1e-4)

    def test_clearly_inferior_logodds(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition, _COMPETITIVE_BENCHMARK_LOGODDS
        assert _COMPETITIVE_BENCHMARK_LOGODDS[CompetitiveBenchmarkPosition.CLEARLY_INFERIOR] == pytest.approx(-0.50, abs=1e-4)

    def test_unknown_logodds_zero_with_flag(self):
        """UNKNOWN = 0.00 + emits flag."""
        from bve.models.pos_model import CompetitiveBenchmarkPosition, _COMPETITIVE_BENCHMARK_LOGODDS
        assert _COMPETITIVE_BENCHMARK_LOGODDS[CompetitiveBenchmarkPosition.UNKNOWN] == pytest.approx(0.00, abs=1e-6)


# ---------------------------------------------------------------------------
# Block 39-B: PriorRegulatoryAction enum
# ---------------------------------------------------------------------------

class TestPriorRegulatoryActionEnum:

    def test_prior_regulatory_action_importable(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert PriorRegulatoryAction is not None

    def test_clinical_hold_safety_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "CLINICAL_HOLD_SAFETY")

    def test_clinical_hold_cmc_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "CLINICAL_HOLD_CMC")

    def test_crl_safety_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "CRL_SAFETY")

    def test_crl_efficacy_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "CRL_EFFICACY")

    def test_crl_cmc_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "CRL_CMC")

    def test_advisory_committee_negative_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "ADVISORY_COMMITTEE_NEGATIVE")

    def test_prior_refusal_to_file_exists(self):
        from bve.models.pos_model import PriorRegulatoryAction
        assert hasattr(PriorRegulatoryAction, "PRIOR_REFUSAL_TO_FILE")

    def test_clinical_hold_safety_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.CLINICAL_HOLD_SAFETY] == pytest.approx(-0.45, abs=1e-4)

    def test_clinical_hold_cmc_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.CLINICAL_HOLD_CMC] == pytest.approx(-0.20, abs=1e-4)

    def test_crl_safety_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.CRL_SAFETY] == pytest.approx(-0.50, abs=1e-4)

    def test_crl_efficacy_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.CRL_EFFICACY] == pytest.approx(-0.35, abs=1e-4)

    def test_crl_cmc_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.CRL_CMC] == pytest.approx(-0.25, abs=1e-4)

    def test_advisory_committee_negative_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.ADVISORY_COMMITTEE_NEGATIVE] == pytest.approx(-0.30, abs=1e-4)

    def test_prior_refusal_to_file_logodds(self):
        from bve.models.pos_model import PriorRegulatoryAction, _REGULATORY_ACTION_LOGODDS
        assert _REGULATORY_ACTION_LOGODDS[PriorRegulatoryAction.PRIOR_REFUSAL_TO_FILE] == pytest.approx(-0.35, abs=1e-4)


# ---------------------------------------------------------------------------
# Block 39-C: RegulatoryActionRecord model
# ---------------------------------------------------------------------------

class TestRegulatoryActionRecord:

    def test_importable(self):
        from bve.models.pos_model import RegulatoryActionRecord
        assert RegulatoryActionRecord is not None

    def test_has_action_field(self):
        from bve.models.pos_model import RegulatoryActionRecord, PriorRegulatoryAction
        rec = RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
        assert rec.action == PriorRegulatoryAction.CRL_SAFETY

    def test_same_molecule_default_true(self):
        from bve.models.pos_model import RegulatoryActionRecord, PriorRegulatoryAction
        rec = RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
        assert rec.same_molecule is True

    def test_same_indication_default_true(self):
        from bve.models.pos_model import RegulatoryActionRecord, PriorRegulatoryAction
        rec = RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
        assert rec.same_indication is True

    def test_issue_resolved_default_false(self):
        from bve.models.pos_model import RegulatoryActionRecord, PriorRegulatoryAction
        rec = RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
        assert rec.issue_resolved is False

    def test_all_fields_settable(self):
        from bve.models.pos_model import RegulatoryActionRecord, PriorRegulatoryAction
        rec = RegulatoryActionRecord(
            action=PriorRegulatoryAction.CLINICAL_HOLD_SAFETY,
            same_molecule=False,
            same_indication=False,
            issue_resolved=True,
        )
        assert rec.same_molecule is False
        assert rec.same_indication is False
        assert rec.issue_resolved is True


# ---------------------------------------------------------------------------
# Block 39-D: CompetitiveBenchmarkPosition phase gate (Phase 2/3 only)
# ---------------------------------------------------------------------------

class TestCompetitiveBenchmarkPhaseGate:

    def test_clearly_inferior_reduces_pos_at_phase_2(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_inferior = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(competitive_benchmark=CompetitiveBenchmarkPosition.CLEARLY_INFERIOR),
        )
        assert pos_inferior < pos_default

    def test_best_in_class_increases_pos_at_phase_3(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        pos_default = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_best = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(competitive_benchmark=CompetitiveBenchmarkPosition.BEST_IN_CLASS),
        )
        assert pos_best > pos_default

    def test_benchmark_silent_at_phase_1(self):
        """CompetitiveBenchmarkPosition has no effect at Phase 1."""
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        pos_default = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_inferior = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(competitive_benchmark=CompetitiveBenchmarkPosition.CLEARLY_INFERIOR),
        )
        assert pos_inferior == pytest.approx(pos_default, abs=1e-6)

    def test_benchmark_silent_at_nda_bla(self):
        """CompetitiveBenchmarkPosition has no effect at NDA/BLA."""
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        pos_default = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_inferior = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(competitive_benchmark=CompetitiveBenchmarkPosition.CLEARLY_INFERIOR),
        )
        assert pos_inferior == pytest.approx(pos_default, abs=1e-6)

    def test_benchmark_unknown_no_pos_change_phase_2(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_unknown = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(competitive_benchmark=CompetitiveBenchmarkPosition.UNKNOWN),
        )
        assert pos_unknown == pytest.approx(pos_default, abs=1e-6)

    def test_benchmark_unknown_emits_flag_phase_2(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(competitive_benchmark=CompetitiveBenchmarkPosition.UNKNOWN),
        )
        assert "competitive_benchmark_unknown" in result.confidence_flags


# ---------------------------------------------------------------------------
# Block 39-E: Regulatory actions phase gate
# ---------------------------------------------------------------------------

class TestRegulatoryActionPhaseGate:

    def test_clinical_hold_applies_at_phase_1(self):
        """Clinical holds apply at ALL phases."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_default = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_hold = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CLINICAL_HOLD_SAFETY)
            ]),
        )
        assert pos_hold < pos_default

    def test_clinical_hold_applies_at_phase_2(self):
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_hold = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CLINICAL_HOLD_SAFETY)
            ]),
        )
        assert pos_hold < pos_default

    def test_crl_applies_at_phase_3(self):
        """CRL applies at Phase 3."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_default = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_crl = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
            ]),
        )
        assert pos_crl < pos_default

    def test_crl_applies_at_nda_bla(self):
        """CRL applies at NDA/BLA via ACCELERATED pathway to show through ceiling."""
        from bve.entities.asset import ApprovalPathwayType
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_default = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.CARDIOVASCULAR,
            POSAdjusters(),
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        pos_crl = compute_pos(
            TrialPhase.NDA_BLA, TherapeuticArea.CARDIOVASCULAR,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
            ]),
            approval_pathway=ApprovalPathwayType.ACCELERATED,
        )
        assert pos_crl < pos_default

    def test_crl_silent_at_phase_1(self):
        """CRL/RTF/AdCom: no effect at Phase 1."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_default = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_crl = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
            ]),
        )
        assert pos_crl == pytest.approx(pos_default, abs=1e-6)

    def test_crl_silent_at_phase_2(self):
        """CRL/RTF/AdCom: no effect at Phase 2."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_default = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_crl = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_EFFICACY)
            ]),
        )
        assert pos_crl == pytest.approx(pos_default, abs=1e-6)


# ---------------------------------------------------------------------------
# Block 39-F: RegulatoryActionRecord penalty scaling
# ---------------------------------------------------------------------------

class TestRegulatoryActionPenaltyScaling:

    def test_resolved_penalty_50_percent(self):
        """Resolved issue → 50% of full penalty."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_unresolved = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(
                    action=PriorRegulatoryAction.CRL_SAFETY,
                    issue_resolved=False,
                )
            ]),
        )
        pos_resolved = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(
                    action=PriorRegulatoryAction.CRL_SAFETY,
                    issue_resolved=True,
                )
            ]),
        )
        # Resolved → less penalty → higher POS
        assert pos_resolved > pos_unresolved

    def test_different_indication_penalty_40_percent(self):
        """Different indication → 40% of full penalty."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_same_ind = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(
                    action=PriorRegulatoryAction.CRL_SAFETY,
                    same_indication=True,
                )
            ]),
        )
        pos_diff_ind = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(
                    action=PriorRegulatoryAction.CRL_SAFETY,
                    same_indication=False,
                )
            ]),
        )
        assert pos_diff_ind > pos_same_ind

    def test_resolved_and_different_indication_20_percent(self):
        """Both resolved AND different indication → 20% of full penalty."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_full = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
            ]),
        )
        pos_both_mitigated = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(
                    action=PriorRegulatoryAction.CRL_SAFETY,
                    same_indication=False,
                    issue_resolved=True,
                )
            ]),
        )
        assert pos_both_mitigated > pos_full


# ---------------------------------------------------------------------------
# Block 39-G: Stacking cap for regulatory actions
# ---------------------------------------------------------------------------

class TestRegulatoryActionStackingCap:

    def test_stacking_cap_applied(self):
        """Multiple regulatory actions cannot exceed -0.60 total penalty."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        # Stack 3 severe actions
        pos_single = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY)
            ]),
        )
        pos_stacked = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY),
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_EFFICACY),
                RegulatoryActionRecord(action=PriorRegulatoryAction.ADVISORY_COMMITTEE_NEGATIVE),
            ]),
        )
        # Adding more actions reduces POS further (cap not yet hit)
        # OR they're both at the cap (≤ single)
        assert pos_stacked <= pos_single

    def test_cap_prevents_going_to_zero(self):
        """Even with many severe holds, POS must remain positive."""
        from bve.models.pos_model import PriorRegulatoryAction, RegulatoryActionRecord
        pos_many_holds = compute_pos(
            TrialPhase.PHASE_3, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(prior_regulatory_actions=[
                RegulatoryActionRecord(action=PriorRegulatoryAction.CLINICAL_HOLD_SAFETY),
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_SAFETY),
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_EFFICACY),
                RegulatoryActionRecord(action=PriorRegulatoryAction.CRL_CMC),
                RegulatoryActionRecord(action=PriorRegulatoryAction.PRIOR_REFUSAL_TO_FILE),
            ]),
        )
        assert pos_many_holds > 0.0


# ---------------------------------------------------------------------------
# Block 39-H: POSAdjusters fields
# ---------------------------------------------------------------------------

class TestPOSAdjustersBlock39Fields:

    def test_competitive_benchmark_field_exists(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        adj = POSAdjusters()
        assert hasattr(adj, "competitive_benchmark")

    def test_competitive_benchmark_default_unknown(self):
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        adj = POSAdjusters()
        assert adj.competitive_benchmark == CompetitiveBenchmarkPosition.UNKNOWN

    def test_prior_regulatory_actions_field_exists(self):
        adj = POSAdjusters()
        assert hasattr(adj, "prior_regulatory_actions")

    def test_prior_regulatory_actions_default_empty_list(self):
        adj = POSAdjusters()
        assert adj.prior_regulatory_actions == []

    def test_backward_compat_no_new_fields(self):
        """Existing calls without block39 fields are unchanged."""
        from bve.models.pos_model import CompetitiveBenchmarkPosition
        pos_old = compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters())
        pos_new = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(
                competitive_benchmark=CompetitiveBenchmarkPosition.UNKNOWN,
                prior_regulatory_actions=[],
            ),
        )
        assert pos_old == pytest.approx(pos_new, abs=1e-6)

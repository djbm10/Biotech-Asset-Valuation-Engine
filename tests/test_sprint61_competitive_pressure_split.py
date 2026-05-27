"""
Block 25 — Rename/Split CompetitivePressure
TDD tests written BEFORE implementation.

Tests for:
  1. RegulatoryApprovalBar enum — new primary enum for POS adjustment
  2. CommercialCrowding enum — revenue-layer concept, NOT a POS adjuster
  3. competitive_pressure deprecated in favour of regulatory_approval_bar
  4. Backward compat: existing code using competitive_pressure still works
"""
from __future__ import annotations

import warnings

import pytest

from bve.models.pos_model import (
    POSAdjusters,
    CompetitivePressure,
    RegulatoryApprovalBar,
    CommercialCrowding,
)
from bve.entities.asset import TherapeuticArea
from bve.entities.trial import TrialPhase

_TA = TherapeuticArea.ONCOLOGY
_PHASE = TrialPhase.PHASE_2


# ---------------------------------------------------------------------------
# Block 25-A: RegulatoryApprovalBar enum
# ---------------------------------------------------------------------------

class TestRegulatoryApprovalBarEnum:

    def test_enum_values_exist(self):
        assert RegulatoryApprovalBar.UNCROWDED.value == "uncrowded"
        assert RegulatoryApprovalBar.MODERATE.value == "moderate"
        assert RegulatoryApprovalBar.CROWDED.value == "crowded"
        assert RegulatoryApprovalBar.HIGHLY_CROWDED.value == "highly_crowded"
        assert RegulatoryApprovalBar.UNKNOWN.value == "unknown"

    def test_five_primary_values(self):
        primary = {"uncrowded", "moderate", "crowded", "highly_crowded", "unknown"}
        values = {v.value for v in RegulatoryApprovalBar}
        assert primary.issubset(values)

    def test_uncrowded_gives_positive_logodds(self):
        """UNCROWDED (+0.10) should yield higher POS than MODERATE (0.00)."""
        from bve.models.pos_model import compute_pos
        adj_crowded  = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.UNCROWDED)
        adj_moderate = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.MODERATE)
        pos_uncrowded = compute_pos(_PHASE, _TA, adj_crowded)
        pos_moderate  = compute_pos(_PHASE, _TA, adj_moderate)
        assert pos_uncrowded > pos_moderate

    def test_highly_crowded_gives_negative_logodds(self):
        """HIGHLY_CROWDED should yield lower POS than MODERATE."""
        from bve.models.pos_model import compute_pos
        adj_highly   = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.HIGHLY_CROWDED)
        adj_moderate = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.MODERATE)
        pos_highly   = compute_pos(_PHASE, _TA, adj_highly)
        pos_moderate = compute_pos(_PHASE, _TA, adj_moderate)
        assert pos_highly < pos_moderate

    def test_moderate_is_reference_zero(self):
        """MODERATE produces the same POS as having no competitive adjustment."""
        from bve.models.pos_model import compute_pos
        adj_moderate = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.MODERATE)
        adj_default  = POSAdjusters()
        assert compute_pos(_PHASE, _TA, adj_moderate) == pytest.approx(
            compute_pos(_PHASE, _TA, adj_default), abs=1e-9
        )

    def test_unknown_zero_adjustment(self):
        """UNKNOWN produces the same adjustment as MODERATE (both 0.00)."""
        from bve.models.pos_model import compute_pos
        adj_unknown  = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.UNKNOWN)
        adj_moderate = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.MODERATE)
        assert compute_pos(_PHASE, _TA, adj_unknown) == pytest.approx(
            compute_pos(_PHASE, _TA, adj_moderate), abs=1e-9
        )

    def test_default_is_moderate(self):
        adj = POSAdjusters()
        assert adj.regulatory_approval_bar == RegulatoryApprovalBar.MODERATE


# ---------------------------------------------------------------------------
# Block 25-B: CompetitivePressure deprecated alias
# ---------------------------------------------------------------------------

class TestCompetitivePressureDeprecatedAlias:

    def test_competitive_pressure_field_still_accepted(self):
        """Old callers passing competitive_pressure still construct POSAdjusters."""
        adj = POSAdjusters(competitive_pressure=CompetitivePressure.NORMAL_BAR)
        assert adj is not None

    def test_competitive_pressure_accepted_with_deprecation_warning(self):
        """Setting competitive_pressure emits a DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            POSAdjusters(competitive_pressure=CompetitivePressure.ELEVATED_BAR)
        assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_competitive_pressure_maps_to_regulatory_approval_bar(self):
        """When competitive_pressure is set, regulatory_approval_bar is populated accordingly."""
        adj = POSAdjusters(competitive_pressure=CompetitivePressure.LOW_BAR)
        assert adj.regulatory_approval_bar == RegulatoryApprovalBar.UNCROWDED

    def test_competitive_pressure_moderate_maps_to_moderate(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            adj = POSAdjusters(competitive_pressure=CompetitivePressure.MODERATE)
        assert adj.regulatory_approval_bar == RegulatoryApprovalBar.MODERATE

    def test_competitive_pressure_high_maps_to_crowded(self):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            adj = POSAdjusters(competitive_pressure=CompetitivePressure.HIGH)
        assert adj.regulatory_approval_bar == RegulatoryApprovalBar.CROWDED

    def test_both_fields_set_uses_regulatory_approval_bar(self):
        """When both fields are set, regulatory_approval_bar takes precedence."""
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            adj = POSAdjusters(
                regulatory_approval_bar=RegulatoryApprovalBar.CROWDED,
                competitive_pressure=CompetitivePressure.LOW_BAR,  # would normally map to UNCROWDED
            )
        assert adj.regulatory_approval_bar == RegulatoryApprovalBar.CROWDED


# ---------------------------------------------------------------------------
# Block 25-C: CommercialCrowding enum — NOT a POS adjuster
# ---------------------------------------------------------------------------

class TestCommercialCrowdingEnum:

    def test_enum_values_exist(self):
        assert CommercialCrowding.MONOPOLY.value == "monopoly"
        assert CommercialCrowding.LOW.value == "low"
        assert CommercialCrowding.MODERATE.value == "moderate"
        assert CommercialCrowding.HIGH.value == "high"
        assert CommercialCrowding.DOMINANT_PLAYER.value == "dominant_player"

    def test_not_a_pos_adjuster_field(self):
        """CommercialCrowding must NOT appear as a field on POSAdjusters."""
        adj = POSAdjusters()
        assert not hasattr(adj, "commercial_crowding")

    def test_is_importable(self):
        assert CommercialCrowding is not None

    def test_has_five_tiers(self):
        assert len(CommercialCrowding) == 5


# ---------------------------------------------------------------------------
# Block 25-D: Backward compatibility
# ---------------------------------------------------------------------------

class TestSplitBackwardCompat:

    def test_existing_pos_adjusters_without_any_competitive_field_work(self):
        """POSAdjusters with no competitive fields still constructs fine."""
        adj = POSAdjusters(
            moa_precedent=POSAdjusters.model_fields["moa_precedent"].default,
        )
        assert adj.regulatory_approval_bar == RegulatoryApprovalBar.MODERATE

    def test_pos_score_unchanged_when_using_default_moderate(self):
        """Default (MODERATE) produces same result before and after Block 25."""
        from bve.models.pos_model import compute_pos
        adj_new = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.MODERATE)
        adj_old = POSAdjusters()  # default moderate
        assert compute_pos(_PHASE, _TA, adj_new) == pytest.approx(
            compute_pos(_PHASE, _TA, adj_old), abs=1e-9
        )

    def test_competitive_pressure_alias_keeps_working_for_normal_bar(self):
        """NORMAL_BAR legacy value still maps to MODERATE and produces correct POS."""
        from bve.models.pos_model import compute_pos
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            adj_legacy = POSAdjusters(competitive_pressure=CompetitivePressure.NORMAL_BAR)
        adj_new = POSAdjusters(regulatory_approval_bar=RegulatoryApprovalBar.MODERATE)
        assert compute_pos(_PHASE, _TA, adj_legacy) == pytest.approx(
            compute_pos(_PHASE, _TA, adj_new), abs=1e-9
        )

    def test_all_existing_pos_adjuster_fields_still_present(self):
        """Block 25 must not remove any existing fields from POSAdjusters."""
        adj = POSAdjusters()
        for field in [
            "endpoint_type", "moa_precedent", "sample_size_adequacy",
            "safety_profile", "biomarker_selection", "prior_phase_data",
            "has_breakthrough_designation",
        ]:
            assert hasattr(adj, field), f"Missing field: {field}"

    def test_competitive_pressure_class_still_importable(self):
        """CompetitivePressure class/alias is still importable and usable."""
        assert CompetitivePressure is not None
        assert CompetitivePressure.LOW_BAR is not None

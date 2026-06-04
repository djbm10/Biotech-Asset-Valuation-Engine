"""
DealType / CompanyProfile Literal drift validator.

Prevents future drift between:
  1. The canonical DealType enum (deal_type_classification.py)
  2. The CompanyProfile.deal_type_classification Literal (exclusions/models.py)
  3. Gate 10 normalization (_LEGACY_GATE10_MAP in rules.py)

Architecture note (2026-06-04 refactor):
  Gate 10 no longer routes companies to specialist models based on deal type.
  Model routing for licensing / platform / commercial / distress types is now
  owned by Layer 0B (classify_deal_structure_route in deal_type_classification.py).
  Gate 10 only handles the "historical_training" sentinel → HISTORICAL_ONLY.
  _CANONICAL_ROUTING_MAP is intentionally empty after the refactor.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bve.intelligence.deal_type_classification import DealType
from bve.intelligence.exclusions.models import CompanyProfile
from bve.intelligence.exclusions.rules import (
    _CANONICAL_ROUTING_MAP,
    _LEGACY_GATE10_MAP,
    gate_10_model_routing,
    RoutingModel,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _profile(**kwargs) -> CompanyProfile:
    """Minimal valid CompanyProfile."""
    defaults = dict(
        company_id="TST-001",
        name="TestCo",
        ticker="TST",
    )
    defaults.update(kwargs)
    return CompanyProfile(**defaults)


# ---------------------------------------------------------------------------
# 1. Every DealType value is accepted by CompanyProfile.deal_type_classification
# ---------------------------------------------------------------------------

class TestDealTypeLiteralCoverage:
    """All canonical DealType values must be valid for CompanyProfile."""

    @pytest.mark.parametrize("dt", list(DealType))
    def test_canonical_dealtype_accepted_by_company_profile(self, dt: DealType):
        """CompanyProfile.deal_type_classification accepts every DealType enum value."""
        try:
            p = _profile(deal_type_classification=dt.value)
            assert p.deal_type_classification == dt.value
        except ValidationError as exc:
            pytest.fail(
                f"DealType.{dt.name} (value={dt.value!r}) is NOT accepted by "
                f"CompanyProfile.deal_type_classification. "
                f"Add {dt.value!r} to the Literal in exclusions/models.py. "
                f"Pydantic error: {exc}"
            )

    def test_none_is_accepted(self):
        """None (default) is always valid."""
        p = _profile(deal_type_classification=None)
        assert p.deal_type_classification is None

    def test_unknown_value_rejected(self):
        """Values outside the Literal are rejected."""
        with pytest.raises(ValidationError):
            _profile(deal_type_classification="made_up_bucket")


# ---------------------------------------------------------------------------
# 2. Legacy Gate 10 literals still normalise correctly
# ---------------------------------------------------------------------------

class TestLegacyGate10NormalizationStable:
    """All five legacy literals must remain in _LEGACY_GATE10_MAP and normalise
    to the expected canonical value (or None for PASS)."""

    EXPECTED: dict[str, str | None] = {
        "standard_pipeline":  None,
        "licensing_only":     "asset_license_partnership",
        "distress_only":      "distressed_optionality",
        "commercial_only":    "commercial_franchise_acquisition",
        "platform_only":      "platform_acquisition",
    }

    def test_all_legacy_literals_present_in_map(self):
        for legacy in self.EXPECTED:
            assert legacy in _LEGACY_GATE10_MAP, (
                f"{legacy!r} missing from _LEGACY_GATE10_MAP"
            )

    @pytest.mark.parametrize("legacy,expected_canonical", list(EXPECTED.items()))
    def test_legacy_literal_normalizes_to_canonical(self, legacy, expected_canonical):
        assert _LEGACY_GATE10_MAP[legacy] == expected_canonical

    @pytest.mark.parametrize("legacy,expected_canonical", list(EXPECTED.items()))
    def test_legacy_literals_accepted_by_company_profile(self, legacy, expected_canonical):
        """CompanyProfile accepts all five legacy literals."""
        p = _profile(deal_type_classification=legacy)
        assert p.deal_type_classification == legacy

    def test_standard_pipeline_passes_gate10(self):
        """standard_pipeline → normalises to None → Gate 10 PASS."""
        p = _profile(deal_type_classification="standard_pipeline")
        result = gate_10_model_routing(p)
        assert result.status.name in ("PASS", "ELIGIBLE"), (
            f"standard_pipeline should PASS Gate 10, got {result.status}"
        )

    def test_licensing_only_passes_gate10(self):
        """licensing_only → Gate 10 PASS (routing now owned by Layer 0B)."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        p = _profile(deal_type_classification="licensing_only")
        result = gate_10_model_routing(p)
        assert result.status == ExclusionStatus.PASS, (
            f"licensing_only should PASS Gate 10 after 0A/0B refactor, got {result.status}. "
            "Model routing for deal types is now owned by Layer 0B."
        )
        assert result.route_to_model is None

    def test_distress_only_passes_gate10(self):
        """distress_only → Gate 10 PASS (routing now owned by Layer 0B)."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        p = _profile(deal_type_classification="distress_only")
        result = gate_10_model_routing(p)
        assert result.status == ExclusionStatus.PASS, (
            f"distress_only should PASS Gate 10 after refactor, got {result.status}."
        )
        assert result.route_to_model is None

    def test_commercial_only_passes_gate10(self):
        """commercial_only → Gate 10 PASS (routing now owned by Layer 0B)."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        p = _profile(deal_type_classification="commercial_only")
        result = gate_10_model_routing(p)
        assert result.status == ExclusionStatus.PASS, (
            f"commercial_only should PASS Gate 10 after refactor, got {result.status}."
        )

    def test_platform_only_passes_gate10(self):
        """platform_only → Gate 10 PASS (routing now owned by Layer 0B)."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        p = _profile(deal_type_classification="platform_only")
        result = gate_10_model_routing(p)
        assert result.status == ExclusionStatus.PASS, (
            f"platform_only should PASS Gate 10 after refactor, got {result.status}."
        )


# ---------------------------------------------------------------------------
# 3. historical_training sentinel is handled correctly
# ---------------------------------------------------------------------------

class TestHistoricalTrainingSentinel:
    """historical_training is a special sentinel — not a DealType value."""

    def test_historical_training_accepted_by_company_profile(self):
        """CompanyProfile accepts the historical_training sentinel."""
        p = _profile(deal_type_classification="historical_training")
        assert p.deal_type_classification == "historical_training"

    def test_historical_training_not_a_dealtype_value(self):
        """historical_training is NOT a member of the DealType enum."""
        dealtype_values = {dt.value for dt in DealType}
        assert "historical_training" not in dealtype_values, (
            "historical_training was added to DealType — this is wrong. "
            "It must remain a special sentinel only."
        )

    def test_historical_training_routes_to_historical_only(self):
        """Gate 10 produces HISTORICAL_ONLY status for historical_training."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        p = _profile(deal_type_classification="historical_training")
        result = gate_10_model_routing(p)
        assert result.status == ExclusionStatus.HISTORICAL_ONLY

    def test_historical_training_not_in_legacy_map(self):
        """historical_training sentinel must NOT appear in _LEGACY_GATE10_MAP."""
        assert "historical_training" not in _LEGACY_GATE10_MAP, (
            "historical_training must be handled by its own branch in "
            "gate_10_model_routing(), not via _LEGACY_GATE10_MAP."
        )


# ---------------------------------------------------------------------------
# 4. Canonical routing map — empty after 0A/0B refactor
# ---------------------------------------------------------------------------

class TestCanonicalRoutingMapRefactored:
    """After the 0A/0B refactor, _CANONICAL_ROUTING_MAP is intentionally empty.

    Model routing for deal types (licensing/platform/commercial/distress) is
    now owned by Layer 0B via classify_deal_structure_route().
    Gate 10 is a pass-through for all canonical DealType values.
    """

    ALL_DEAL_TYPES = {dt.value for dt in DealType}
    # These two pass-through types existed before the refactor
    LEGACY_PASS_THROUGH = {"single_asset_takeout", "pipeline_portfolio_takeout"}

    def test_canonical_routing_map_is_empty(self):
        """_CANONICAL_ROUTING_MAP must be empty after the 0A/0B refactor."""
        assert _CANONICAL_ROUTING_MAP == {}, (
            "_CANONICAL_ROUTING_MAP should be empty. "
            "Model routing for deal types now lives in Layer 0B "
            "(classify_deal_structure_route in deal_type_classification.py)."
        )

    def test_all_canonical_deal_types_pass_gate10(self):
        """All six canonical DealType values now PASS Gate 10."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        for dt_value in self.ALL_DEAL_TYPES:
            p = _profile(deal_type_classification=dt_value)
            result = gate_10_model_routing(p)
            assert result.status == ExclusionStatus.PASS, (
                f"{dt_value!r} should PASS Gate 10 after refactor, got {result.status}."
            )
            assert result.route_to_model is None, (
                f"{dt_value!r} should not produce a route_to_model in Gate 10."
            )

    def test_legacy_and_canonical_both_pass_gate10(self):
        """Legacy literal and its canonical equivalent both PASS Gate 10."""
        from bve.intelligence.exclusions.enums import ExclusionStatus
        pairs = [
            ("licensing_only",  "asset_license_partnership"),
            ("distress_only",   "distressed_optionality"),
            ("commercial_only", "commercial_franchise_acquisition"),
            ("platform_only",   "platform_acquisition"),
        ]
        for legacy, canonical in pairs:
            r_legacy = gate_10_model_routing(_profile(deal_type_classification=legacy))
            r_canonical = gate_10_model_routing(_profile(deal_type_classification=canonical))
            assert r_legacy.status == ExclusionStatus.PASS, (
                f"Legacy {legacy!r} should PASS Gate 10 after refactor."
            )
            assert r_canonical.status == ExclusionStatus.PASS, (
                f"Canonical {canonical!r} should PASS Gate 10 after refactor."
            )

    def test_layer0b_owns_licensing_model_routing(self):
        """Layer 0B (classify_deal_structure_route) produces the licensing route."""
        from bve.intelligence.deal_type_classification import (
            classify_deal_structure_route,
            DealStructureRoute,
        )
        from bve.intelligence.ma_eligibility import TargetEligibilityInput
        target = TargetEligibilityInput(
            ticker="LIC001",
            has_existing_partnership=True,
            asset_rights_scope="licensed_in",
            royalty_stack_rate=0.18,
        )
        result = classify_deal_structure_route(target)
        # Should be a licensing sub-route — not full_company_takeout
        licensing_routes = {
            DealStructureRoute.GLOBAL_LICENSE,
            DealStructureRoute.REGIONAL_LICENSE,
            DealStructureRoute.OPTION_TO_LICENSE_OR_ACQUIRE,
            DealStructureRoute.CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION,
            DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
        }
        assert result.primary_route in licensing_routes, (
            f"Expected licensing route from 0B, got {result.primary_route}."
        )

    def test_layer0b_owns_distress_model_routing(self):
        """Layer 0B assigns DISTRESSED_OPTIONALITY route for distressed targets."""
        from bve.intelligence.deal_type_classification import (
            classify_deal_structure_route,
            DealStructureRoute,
        )
        from bve.intelligence.ma_eligibility import TargetEligibilityInput
        target = TargetEligibilityInput(
            ticker="DIST001",
            financing_pressure_high=True,
            lead_asset_quality_low=True,
        )
        result = classify_deal_structure_route(target)
        assert result.primary_route == DealStructureRoute.DISTRESSED_OPTIONALITY, (
            f"Expected DISTRESSED_OPTIONALITY from 0B, got {result.primary_route}."
        )

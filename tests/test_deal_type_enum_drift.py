"""
DealType / CompanyProfile Literal drift validator.

Prevents future drift between:
  1. The canonical DealType enum (deal_type_classification.py)
  2. The CompanyProfile.deal_type_classification Literal (exclusions/models.py)
  3. Gate 10 routing (_LEGACY_GATE10_MAP / _CANONICAL_ROUTING_MAP in rules.py)

If a new DealType enum member is added without updating the Literal and the
routing maps, these tests will fail immediately — the developer will know
exactly where to add the new value.
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

    def test_licensing_only_routes_to_licensing_model(self):
        p = _profile(deal_type_classification="licensing_only")
        result = gate_10_model_routing(p)
        assert result.route_to_model == RoutingModel.LICENSING_MODEL

    def test_distress_only_routes_to_distressed_model(self):
        p = _profile(deal_type_classification="distress_only")
        result = gate_10_model_routing(p)
        assert result.route_to_model == RoutingModel.DISTRESSED_OPTIONALITY_MODEL

    def test_commercial_only_routes_to_commercial_model(self):
        p = _profile(deal_type_classification="commercial_only")
        result = gate_10_model_routing(p)
        assert result.route_to_model == RoutingModel.COMMERCIAL_FRANCHISE_MODEL

    def test_platform_only_routes_to_platform_model(self):
        p = _profile(deal_type_classification="platform_only")
        result = gate_10_model_routing(p)
        assert result.route_to_model == RoutingModel.PLATFORM_ACQUISITION_MODEL


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
# 4. Canonical routing map covers non-passthrough DealType values
# ---------------------------------------------------------------------------

class TestCanonicalRoutingMapCompleteness:
    """_CANONICAL_ROUTING_MAP must contain exactly the DealType values that
    require specialist routing (not single_asset_takeout / pipeline_portfolio_takeout
    which pass through Gate 10)."""

    # DealType values that are expected to PASS through Gate 10 (no specialist routing)
    PASS_THROUGH = {"single_asset_takeout", "pipeline_portfolio_takeout"}

    def test_routed_types_have_route_to_model(self):
        """Every canonical value in _CANONICAL_ROUTING_MAP maps to a RoutingModel."""
        for k, (reason, model) in _CANONICAL_ROUTING_MAP.items():
            assert isinstance(model, RoutingModel), (
                f"{k!r} does not map to a RoutingModel in _CANONICAL_ROUTING_MAP"
            )
            assert isinstance(reason, str) and reason, (
                f"{k!r} has empty reason in _CANONICAL_ROUTING_MAP"
            )

    def test_passthrough_types_not_in_routing_map(self):
        """Pass-through types must NOT be in _CANONICAL_ROUTING_MAP."""
        for pt in self.PASS_THROUGH:
            assert pt not in _CANONICAL_ROUTING_MAP, (
                f"{pt!r} must not be in _CANONICAL_ROUTING_MAP — it should PASS Gate 10"
            )

    def test_passthrough_types_pass_gate10(self):
        """single_asset_takeout and pipeline_portfolio_takeout PASS Gate 10."""
        for pt in self.PASS_THROUGH:
            p = _profile(deal_type_classification=pt)
            result = gate_10_model_routing(p)
            assert result.status.name in ("PASS", "ELIGIBLE"), (
                f"{pt!r} should PASS Gate 10, got status={result.status}"
            )

    def test_legacy_and_canonical_produce_same_routing(self):
        """Legacy literal and its canonical equivalent yield identical Gate 10 results."""
        pairs = [
            ("licensing_only",  "asset_license_partnership"),
            ("distress_only",   "distressed_optionality"),
            ("commercial_only", "commercial_franchise_acquisition"),
            ("platform_only",   "platform_acquisition"),
        ]
        for legacy, canonical in pairs:
            r_legacy = gate_10_model_routing(_profile(deal_type_classification=legacy))
            r_canonical = gate_10_model_routing(_profile(deal_type_classification=canonical))
            assert r_legacy.route_to_model == r_canonical.route_to_model, (
                f"Legacy {legacy!r} and canonical {canonical!r} produce different "
                f"routing models: {r_legacy.route_to_model} vs {r_canonical.route_to_model}"
            )

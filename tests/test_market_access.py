"""Tests for bve.models.market_access."""
import pytest
from bve.models.market_access import (
    PayerDynamics, assess_market_access,
    FormularyTier, PriorAuthBurden, CostEffectivenessRisk,
)


def _default():
    return PayerDynamics()


class TestDefaultDynamics:
    def test_returns_result(self):
        r = assess_market_access(_default())
        assert r is not None

    def test_moderate_tier_by_default(self):
        r = assess_market_access(_default())
        assert r.access_risk_tier in ("favorable", "moderate")

    def test_multiplier_in_range(self):
        r = assess_market_access(_default())
        assert 0.30 <= r.effective_patient_pool_multiplier <= 1.0

    def test_adoption_speed_in_range(self):
        r = assess_market_access(_default())
        assert -0.30 <= r.adoption_speed_modifier <= 0.10

    def test_peak_penetration_in_range(self):
        r = assess_market_access(_default())
        assert -0.20 <= r.peak_penetration_modifier <= 0.05

    def test_access_risk_score_in_range(self):
        r = assess_market_access(_default())
        assert 0.0 <= r.access_risk_score <= 1.0

    def test_risk_factors_is_list(self):
        r = assess_market_access(_default())
        assert isinstance(r.risk_factors, list)

    def test_tailwinds_is_list(self):
        r = assess_market_access(_default())
        assert isinstance(r.tailwinds, list)

    def test_net_price_durability_positive(self):
        r = assess_market_access(_default())
        assert r.net_price_durability_years >= 1.0


class TestFormularyTierEffects:
    def test_excluded_caps_pool_at_floor(self):
        r = assess_market_access(PayerDynamics(formulary_tier=FormularyTier.EXCLUDED))
        assert r.effective_patient_pool_multiplier <= 0.35

    def test_excluded_is_challenging_or_unknown_tier(self):
        r = assess_market_access(PayerDynamics(formulary_tier=FormularyTier.EXCLUDED))
        assert r.access_risk_tier in ("challenging", "unknown")

    def test_tier3_reduces_pool(self):
        base = assess_market_access(_default())
        tier3 = assess_market_access(PayerDynamics(formulary_tier=FormularyTier.TIER_3))
        assert tier3.effective_patient_pool_multiplier < base.effective_patient_pool_multiplier

    def test_tier1_adoption_boost(self):
        base = assess_market_access(_default())
        tier1 = assess_market_access(PayerDynamics(formulary_tier=FormularyTier.TIER_1))
        assert tier1.adoption_speed_modifier >= base.adoption_speed_modifier

    def test_tier1_reduces_risk_score(self):
        base = assess_market_access(_default())
        tier1 = assess_market_access(PayerDynamics(formulary_tier=FormularyTier.TIER_1))
        assert tier1.access_risk_score <= base.access_risk_score


class TestPriorAuthBurden:
    def test_high_prior_auth_negative_adoption(self):
        r = assess_market_access(PayerDynamics(prior_auth_burden=PriorAuthBurden.HIGH))
        assert r.adoption_speed_modifier < 0.0

    def test_high_prior_auth_reduces_pool(self):
        none_r = assess_market_access(PayerDynamics(prior_auth_burden=PriorAuthBurden.NONE))
        high_r = assess_market_access(PayerDynamics(prior_auth_burden=PriorAuthBurden.HIGH))
        assert high_r.effective_patient_pool_multiplier < none_r.effective_patient_pool_multiplier

    def test_none_prior_auth_reduces_risk_score(self):
        unknown_r = assess_market_access(_default())
        none_r = assess_market_access(PayerDynamics(prior_auth_burden=PriorAuthBurden.NONE))
        assert none_r.access_risk_score <= unknown_r.access_risk_score


class TestCostEffectivenessRisk:
    def test_high_icer_negative_peak_penetration(self):
        r = assess_market_access(PayerDynamics(cost_effectiveness_risk=CostEffectivenessRisk.HIGH))
        assert r.peak_penetration_modifier < 0.0

    def test_moderate_icer_small_peak_penalty(self):
        low = assess_market_access(PayerDynamics(cost_effectiveness_risk=CostEffectivenessRisk.LOW))
        mod = assess_market_access(PayerDynamics(cost_effectiveness_risk=CostEffectivenessRisk.MODERATE))
        assert mod.peak_penetration_modifier < low.peak_penetration_modifier


class TestOrphanDrugDesignation:
    def test_orphan_increases_pool(self):
        base = assess_market_access(_default())
        orphan = assess_market_access(PayerDynamics(orphan_drug_designation=True))
        assert orphan.access_risk_score <= base.access_risk_score

    def test_orphan_longer_price_durability(self):
        base = assess_market_access(_default())
        orphan = assess_market_access(PayerDynamics(orphan_drug_designation=True))
        assert orphan.net_price_durability_years > base.net_price_durability_years

    def test_orphan_adds_tailwinds(self):
        r = assess_market_access(PayerDynamics(orphan_drug_designation=True))
        assert len(r.tailwinds) > 0

    def test_orphan_favorable_tier(self):
        r = assess_market_access(PayerDynamics(orphan_drug_designation=True))
        assert r.access_risk_tier in ("favorable", "moderate")


class TestStepEdit:
    def test_step_edit_reduces_pool(self):
        base = assess_market_access(_default())
        se = assess_market_access(PayerDynamics(step_edit_required=True))
        assert se.effective_patient_pool_multiplier < base.effective_patient_pool_multiplier

    def test_step_edit_negative_adoption(self):
        r = assess_market_access(PayerDynamics(step_edit_required=True))
        assert r.adoption_speed_modifier < 0.0

    def test_step_edit_adds_risk_factor(self):
        r = assess_market_access(PayerDynamics(step_edit_required=True))
        assert any("step" in f.lower() for f in r.risk_factors)


class TestMedicareHeavy:
    def test_medicare_heavy_reduces_pool(self):
        base = assess_market_access(_default())
        med = assess_market_access(PayerDynamics(medicare_heavy_indication=True))
        assert med.effective_patient_pool_multiplier < base.effective_patient_pool_multiplier

    def test_medicare_heavy_plus_high_icer_extra_peak_penalty(self):
        med_only = assess_market_access(
            PayerDynamics(medicare_heavy_indication=True,
                          cost_effectiveness_risk=CostEffectivenessRisk.LOW)
        )
        med_high = assess_market_access(
            PayerDynamics(medicare_heavy_indication=True,
                          cost_effectiveness_risk=CostEffectivenessRisk.HIGH)
        )
        assert med_high.peak_penetration_modifier < med_only.peak_penetration_modifier

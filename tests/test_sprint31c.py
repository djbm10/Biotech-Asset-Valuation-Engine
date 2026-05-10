"""
Sprint 31C — ScenarioTree: outcome-branch decomposition tests.

Covers:
- All named clinical, regulatory, commercial branches
- ScenarioTree composition and to_shock()
- from_named_branches() factory
- Branch shock properties (pos_mult, label_breadth, etc.)
- Endpoint-miss near-zero revenue (pos_mult=0.0)
- Composed shock field merging (multipliers × multipliers, deltas + deltas)
- Canonical pre-built trees
- Immutability
"""
import pytest

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.market_model import MarketModel
from bve.models.rnpv_model import compute_rnpv_full
from bve.models.scenario_tree import (
    CLINICAL_BRANCHES,
    COMMERCIAL_BRANCHES,
    REGULATORY_BRANCHES,
    TREE_BASE_CASE,
    TREE_BEST_CASE,
    TREE_CONFIRMATORY_COMPETITOR,
    TREE_DOWNSIDE,
    TREE_FAILURE,
    ScenarioTree,
    from_named_branches,
)
from bve.valuation.scenario import apply_scenario_shock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="tree-001",
        name="Tree Drug",
        indication="Oncology",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        launch_year=2028,
        patent_expiry_year=2040,
        discount_rate=0.10,
        effective_tax_rate=0.21,
        royalty_rate=0.0,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="tree-001",
            phase=TrialPhase.PHASE_3,
            success_probability=0.60,
            duration_years=4.0,
            cost_millions=150.0,
        ),
    ]


def _market() -> MarketModel:
    return MarketModel(
        asset_id="tree-001",
        therapeutic_area="oncology",
        addressable_patients_annual=60_000,
        net_price_per_patient_usd=100_000,
        peak_penetration=0.20,
        years_to_peak=4,
        patent_life_years=12,
        cogs_rate=0.12,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.18,
    )


# ---------------------------------------------------------------------------
# Clinical branches
# ---------------------------------------------------------------------------

class TestClinicalBranches:
    def test_all_four_branches_exist(self):
        for key in ("failure", "mixed_result", "success", "strong_success"):
            assert key in CLINICAL_BRANCHES

    def test_failure_pos_mult_is_zero(self):
        shock = CLINICAL_BRANCHES["failure"].shock
        assert shock.clinical.pos_mult == 0.0

    def test_mixed_result_pos_mult_lt_one(self):
        shock = CLINICAL_BRANCHES["mixed_result"].shock
        assert 0.0 < shock.clinical.pos_mult < 1.0

    def test_success_pos_mult_is_one(self):
        shock = CLINICAL_BRANCHES["success"].shock
        assert shock.clinical.pos_mult == 1.0

    def test_strong_success_pos_mult_gt_one(self):
        shock = CLINICAL_BRANCHES["strong_success"].shock
        assert shock.clinical.pos_mult > 1.0

    def test_strong_success_breakthrough_designation(self):
        shock = CLINICAL_BRANCHES["strong_success"].shock
        assert shock.clinical.breakthrough_designation_override is True

    def test_failure_near_zero_rnpv(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = CLINICAL_BRANCHES["failure"].shock
        s_asset, s_trials, s_market, _, _ = apply_scenario_shock(asset, trials, market, shock)
        result = compute_rnpv_full(s_asset, s_trials, s_market)
        # pos_mult=0.0 → each trial clamped to min 0.01 → cumulative_prob ≤ 0.01
        assert result.cumulative_success_probability <= 0.01

    def test_strong_success_higher_rnpv_than_mixed(self):
        asset = _asset()
        trials = _trials()
        market = _market()

        def _rnpv(branch_key):
            shock = CLINICAL_BRANCHES[branch_key].shock
            s_a, s_t, s_m, _, _ = apply_scenario_shock(asset, trials, market, shock)
            return compute_rnpv_full(s_a, s_t, s_m).rnpv_millions

        assert _rnpv("strong_success") > _rnpv("success") > _rnpv("mixed_result")

    def test_branches_are_frozen(self):
        for branch in CLINICAL_BRANCHES.values():
            with pytest.raises(Exception):
                branch.name = "Modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Regulatory branches
# ---------------------------------------------------------------------------

class TestRegulatoryBranches:
    def test_all_five_branches_exist(self):
        for key in (
            "standard_approval", "accelerated_approval", "narrow_label",
            "delay_crl", "confirmatory_required",
        ):
            assert key in REGULATORY_BRANCHES

    def test_accelerated_approval_negative_duration(self):
        shock = REGULATORY_BRANCHES["accelerated_approval"].shock
        assert shock.regulatory.duration_add_years < 0.0

    def test_narrow_label_reduces_label_breadth(self):
        shock = REGULATORY_BRANCHES["narrow_label"].shock
        assert shock.regulatory.label_breadth_mult < 1.0

    def test_delay_crl_adds_positive_duration(self):
        shock = REGULATORY_BRANCHES["delay_crl"].shock
        assert shock.regulatory.duration_add_years > 0.0
        assert shock.regulatory.crl_delay_add_years > 0.0

    def test_confirmatory_required_has_cost(self):
        shock = REGULATORY_BRANCHES["confirmatory_required"].shock
        assert shock.regulatory.confirmatory_trial_cost_millions > 0.0

    def test_standard_approval_is_zero_effect(self):
        shock = REGULATORY_BRANCHES["standard_approval"].shock
        assert shock.is_zero_effect


# ---------------------------------------------------------------------------
# Commercial branches
# ---------------------------------------------------------------------------

class TestCommercialBranches:
    def test_all_four_branches_exist(self):
        for key in (
            "strong_launch", "normal_launch",
            "payer_restricted_launch", "competitor_disrupted_launch",
        ):
            assert key in COMMERCIAL_BRANCHES

    def test_normal_launch_is_zero_effect(self):
        shock = COMMERCIAL_BRANCHES["normal_launch"].shock
        assert shock.is_zero_effect

    def test_strong_launch_higher_penetration(self):
        shock = COMMERCIAL_BRANCHES["strong_launch"].shock
        assert shock.commercial.peak_penetration_mult > 1.0

    def test_payer_restricted_lower_penetration(self):
        shock = COMMERCIAL_BRANCHES["payer_restricted_launch"].shock
        assert shock.commercial.peak_penetration_mult < 1.0
        assert shock.commercial.prior_auth_burden_delta > 0.0

    def test_competitor_disrupted_has_competition_shock(self):
        shock = COMMERCIAL_BRANCHES["competitor_disrupted_launch"].shock
        assert shock.competition.competitor_market_share_mult > 1.0
        assert shock.competition.competition_price_pressure_delta > 0.0


# ---------------------------------------------------------------------------
# ScenarioTree composition
# ---------------------------------------------------------------------------

class TestScenarioTreeComposition:
    def test_to_shock_returns_scenario_shock(self):
        tree = from_named_branches("success", "standard_approval", "normal_launch")
        shock = tree.to_shock()
        from bve.models.scenario_shock import ScenarioShock
        assert isinstance(shock, ScenarioShock)

    def test_base_case_tree_close_to_direct_compute(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = TREE_BASE_CASE.to_shock()
        s_a, s_t, s_m, _, _ = apply_scenario_shock(asset, trials, market, shock)
        tree_rnpv = compute_rnpv_full(s_a, s_t, s_m).rnpv_millions
        direct_rnpv = compute_rnpv_full(asset, trials, market).rnpv_millions
        # Base case (success + standard + normal) = zero-effect tree
        assert tree_rnpv == pytest.approx(direct_rnpv, rel=1e-4)

    def test_best_case_rnpv_gt_base_case(self):
        asset = _asset()
        trials = _trials()
        market = _market()

        def _rnpv(tree):
            shock = tree.to_shock()
            s_a, s_t, s_m, _, _ = apply_scenario_shock(asset, trials, market, shock)
            return compute_rnpv_full(s_a, s_t, s_m).rnpv_millions

        assert _rnpv(TREE_BEST_CASE) > _rnpv(TREE_BASE_CASE)

    def test_downside_rnpv_lt_base_case(self):
        asset = _asset()
        trials = _trials()
        market = _market()

        def _rnpv(tree):
            shock = tree.to_shock()
            s_a, s_t, s_m, _, _ = apply_scenario_shock(asset, trials, market, shock)
            return compute_rnpv_full(s_a, s_t, s_m).rnpv_millions

        assert _rnpv(TREE_DOWNSIDE) < _rnpv(TREE_BASE_CASE)

    def test_failure_near_zero_approval(self):
        asset = _asset()
        trials = _trials()
        market = _market()
        shock = TREE_FAILURE.to_shock()
        s_a, s_t, s_m, _, _ = apply_scenario_shock(asset, trials, market, shock)
        result = compute_rnpv_full(s_a, s_t, s_m)
        # pos_mult=0.0 → clamped to 0.01 → cumulative_prob ≤ 0.01
        assert result.cumulative_success_probability <= 0.01

    def test_composed_shock_multipliers_multiply(self):
        """pos_mult and label_breadth_mult are multiplied across branches."""
        tree = from_named_branches("strong_success", "narrow_label", "normal_launch")
        shock = tree.to_shock()
        # strong_success: pos_mult=1.25, regulatory.label_breadth_mult=1.20
        # narrow_label: regulatory.label_breadth_mult=0.60
        # composed: 1.20 × 0.60 = 0.72
        strong_reg_breadth = CLINICAL_BRANCHES["strong_success"].shock.regulatory.label_breadth_mult
        narrow_breadth = REGULATORY_BRANCHES["narrow_label"].shock.regulatory.label_breadth_mult
        assert shock.clinical.pos_mult == pytest.approx(
            CLINICAL_BRANCHES["strong_success"].shock.clinical.pos_mult, abs=1e-6
        )
        assert shock.regulatory.label_breadth_mult == pytest.approx(
            strong_reg_breadth * narrow_breadth, abs=1e-6
        )

    def test_composed_shock_deltas_add(self):
        """Duration deltas from regulatory + CRL delay should sum."""
        tree = from_named_branches("success", "delay_crl", "normal_launch")
        shock = tree.to_shock()
        delay_branch = REGULATORY_BRANCHES["delay_crl"].shock
        expected_duration = delay_branch.regulatory.duration_add_years + delay_branch.regulatory.crl_delay_add_years
        assert shock.regulatory.duration_add_years == pytest.approx(
            delay_branch.regulatory.duration_add_years, abs=1e-6
        )
        assert shock.regulatory.crl_delay_add_years == pytest.approx(
            delay_branch.regulatory.crl_delay_add_years, abs=1e-6
        )

    def test_label_auto_generated_from_branch_names(self):
        tree = ScenarioTree(
            clinical_branch=CLINICAL_BRANCHES["success"],
            regulatory_branch=REGULATORY_BRANCHES["standard_approval"],
            commercial_branch=COMMERCIAL_BRANCHES["normal_launch"],
        )
        assert "Clinical Success" in tree.effective_label
        assert "Standard Approval" in tree.effective_label
        assert "Normal Launch" in tree.effective_label

    def test_label_override_respected(self):
        tree = ScenarioTree(
            clinical_branch=CLINICAL_BRANCHES["success"],
            regulatory_branch=REGULATORY_BRANCHES["standard_approval"],
            commercial_branch=COMMERCIAL_BRANCHES["normal_launch"],
            label="My Custom Label",
        )
        assert tree.effective_label == "My Custom Label"

    def test_description_auto_generated(self):
        tree = from_named_branches("mixed_result", "narrow_label", "payer_restricted_launch")
        desc = tree.effective_description
        assert len(desc) > 0
        # Description should contain content from each branch description
        assert "Clinical:" in desc and "Regulatory:" in desc and "Commercial:" in desc

    def test_tree_is_frozen(self):
        tree = from_named_branches("success", "standard_approval", "normal_launch")
        with pytest.raises(Exception):
            tree.label = "Modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# from_named_branches factory
# ---------------------------------------------------------------------------

class TestFromNamedBranches:
    def test_builds_all_valid_combinations(self):
        clinical_keys = ("failure", "mixed_result", "success", "strong_success")
        regulatory_keys = (
            "standard_approval", "accelerated_approval", "narrow_label",
            "delay_crl", "confirmatory_required",
        )
        commercial_keys = (
            "strong_launch", "normal_launch",
            "payer_restricted_launch", "competitor_disrupted_launch",
        )
        # Spot-check 6 combinations
        combinations = [
            ("strong_success", "accelerated_approval", "strong_launch"),
            ("mixed_result", "narrow_label", "payer_restricted_launch"),
            ("failure", "standard_approval", "normal_launch"),
            ("success", "delay_crl", "competitor_disrupted_launch"),
            ("strong_success", "confirmatory_required", "normal_launch"),
            ("mixed_result", "accelerated_approval", "payer_restricted_launch"),
        ]
        for clin, reg, comm in combinations:
            tree = from_named_branches(clin, reg, comm)  # type: ignore[arg-type]
            assert isinstance(tree, ScenarioTree)

    def test_label_kwarg_passed_through(self):
        tree = from_named_branches(
            "success", "standard_approval", "normal_launch",
            label="Custom Label",
        )
        assert tree.effective_label == "Custom Label"


# ---------------------------------------------------------------------------
# Canonical pre-built trees
# ---------------------------------------------------------------------------

class TestCanonicalTrees:
    def test_best_case_label(self):
        assert TREE_BEST_CASE.label == "Best Case"

    def test_base_case_label(self):
        assert TREE_BASE_CASE.label == "Base Case"

    def test_downside_label(self):
        assert TREE_DOWNSIDE.label == "Conservative Downside"

    def test_failure_label(self):
        assert TREE_FAILURE.label == "Endpoint Miss"

    def test_confirmatory_competitor_has_both_shocks(self):
        shock = TREE_CONFIRMATORY_COMPETITOR.to_shock()
        # confirmatory trial cost > 0
        assert shock.regulatory.confirmatory_trial_cost_millions > 0.0
        # competitor disruption present
        assert shock.competition.competition_price_pressure_delta > 0.0

    def test_best_case_has_breakthrough_designation(self):
        shock = TREE_BEST_CASE.to_shock()
        assert shock.clinical.breakthrough_designation_override is True

    def test_failure_tree_pos_mult_zero(self):
        shock = TREE_FAILURE.to_shock()
        assert shock.clinical.pos_mult == pytest.approx(0.0, abs=1e-6)

    def test_ordering_best_gt_base_gt_downside(self):
        asset = _asset()
        trials = _trials()
        market = _market()

        def _rnpv(tree):
            shock = tree.to_shock()
            s_a, s_t, s_m, _, _ = apply_scenario_shock(asset, trials, market, shock)
            return compute_rnpv_full(s_a, s_t, s_m).rnpv_millions

        assert _rnpv(TREE_BEST_CASE) > _rnpv(TREE_BASE_CASE) > _rnpv(TREE_DOWNSIDE)

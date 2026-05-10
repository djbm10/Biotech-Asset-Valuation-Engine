"""
Sprint 32B — Full MC variable table (23 variables, named distributions) tests.

Covers:
- MCVariableSpec fields and immutability
- DistributionType enum values
- Exactly 23 variables in MC_VARIABLE_TABLE
- All 5 distribution types present
- Beta variables: alpha > 0, beta > 0; sampled values in (0, 1)
- LogNormal variables: mu and sigma present; sampled values > 0
- Normal variables: mean and std present
- Triangular variables: low <= mode <= high
- Bernoulli variables: p in (0, 1); sampled values only 0 or 1
- Confirmatory trial cost has bernoulli_trigger="confirmatory_trial_required"
- Tax variable present (effective_tax_rate, Beta distribution)
- All 7 categories populated
- sample_params_valid() returns True for all 23
- ACTIVE_MC_VARIABLES is a subset of all variables
- MC_VARIABLES_BY_CATEGORY groups correctly
"""
import math
import pytest
import numpy as np

from bve.models.mc_variable_table import (
    DistributionType,
    MCVariableSpec,
    MC_VARIABLE_TABLE,
    MC_VARIABLES_BY_CATEGORY,
    ACTIVE_MC_VARIABLES,
)


# ---------------------------------------------------------------------------
# DistributionType enum
# ---------------------------------------------------------------------------

class TestDistributionType:
    def test_all_five_types(self):
        types = {dt.value for dt in DistributionType}
        assert types == {"beta", "lognormal", "normal", "triangular", "bernoulli"}

    def test_string_access(self):
        assert DistributionType("beta") is DistributionType.BETA
        assert DistributionType("lognormal") is DistributionType.LOGNORMAL
        assert DistributionType("bernoulli") is DistributionType.BERNOULLI


# ---------------------------------------------------------------------------
# MCVariableSpec structure
# ---------------------------------------------------------------------------

class TestMCVariableSpec:
    def test_frozen(self):
        spec = MC_VARIABLE_TABLE["discount_rate"]
        with pytest.raises(Exception):
            spec.active = False  # type: ignore[misc]

    def test_has_name(self):
        for spec in MC_VARIABLE_TABLE.values():
            assert spec.name and isinstance(spec.name, str)

    def test_has_description(self):
        for spec in MC_VARIABLE_TABLE.values():
            assert spec.description and isinstance(spec.description, str)

    def test_has_category(self):
        for spec in MC_VARIABLE_TABLE.values():
            assert spec.category in {
                "clinical", "regulatory", "commercial",
                "payer", "competition", "costs", "tax",
            }

    def test_sample_params_valid_all(self):
        for spec in MC_VARIABLE_TABLE.values():
            assert spec.sample_params_valid(), (
                f"{spec.name} has invalid params for {spec.distribution_type}"
            )

    def test_active_is_bool(self):
        for spec in MC_VARIABLE_TABLE.values():
            assert isinstance(spec.active, bool)


# ---------------------------------------------------------------------------
# 23-variable table completeness
# ---------------------------------------------------------------------------

class TestVariableTableCompleteness:
    def test_exactly_23_variables(self):
        assert len(MC_VARIABLE_TABLE) == 23

    def test_all_five_distribution_types_present(self):
        types_used = {s.distribution_type for s in MC_VARIABLE_TABLE.values()}
        assert DistributionType.BETA in types_used
        assert DistributionType.LOGNORMAL in types_used
        assert DistributionType.NORMAL in types_used
        assert DistributionType.TRIANGULAR in types_used
        assert DistributionType.BERNOULLI in types_used

    def test_all_seven_categories_present(self):
        categories = set(MC_VARIABLES_BY_CATEGORY.keys())
        assert categories == {"clinical", "regulatory", "commercial", "payer", "competition", "costs", "tax"}

    def test_clinical_has_4_variables(self):
        assert len(MC_VARIABLES_BY_CATEGORY["clinical"]) == 4

    def test_regulatory_has_5_variables(self):
        assert len(MC_VARIABLES_BY_CATEGORY["regulatory"]) == 5

    def test_commercial_has_5_variables(self):
        assert len(MC_VARIABLES_BY_CATEGORY["commercial"]) == 5

    def test_payer_has_2_variables(self):
        assert len(MC_VARIABLES_BY_CATEGORY["payer"]) == 2

    def test_competition_has_2_variables(self):
        assert len(MC_VARIABLES_BY_CATEGORY["competition"]) == 2

    def test_costs_has_4_variables(self):
        assert len(MC_VARIABLES_BY_CATEGORY["costs"]) == 4

    def test_tax_has_1_variable(self):
        assert len(MC_VARIABLES_BY_CATEGORY["tax"]) == 1


# ---------------------------------------------------------------------------
# Beta distribution properties
# ---------------------------------------------------------------------------

class TestBetaVariables:
    @pytest.fixture
    def beta_specs(self):
        return [s for s in MC_VARIABLE_TABLE.values() if s.distribution_type == DistributionType.BETA]

    def test_alpha_positive(self, beta_specs):
        for spec in beta_specs:
            assert spec.params["alpha"] > 0, f"{spec.name}: alpha must be positive"

    def test_beta_positive(self, beta_specs):
        for spec in beta_specs:
            assert spec.params["beta"] > 0, f"{spec.name}: beta must be positive"

    def test_samples_in_unit_interval(self, beta_specs):
        rng = np.random.default_rng(42)
        for spec in beta_specs:
            samples = rng.beta(spec.params["alpha"], spec.params["beta"], 500)
            assert np.all(samples > 0) and np.all(samples < 1), (
                f"{spec.name}: Beta samples outside (0,1)"
            )

    def test_effective_tax_rate_is_beta(self):
        spec = MC_VARIABLE_TABLE["effective_tax_rate"]
        assert spec.distribution_type == DistributionType.BETA
        assert spec.category == "tax"

    def test_phase_success_probs_are_beta(self):
        for name in ["phase_1_success_prob", "phase_2_success_prob", "phase_3_success_prob"]:
            assert MC_VARIABLE_TABLE[name].distribution_type == DistributionType.BETA

    def test_beta_mean_in_range(self, beta_specs):
        for spec in beta_specs:
            a = spec.params["alpha"]
            b = spec.params["beta"]
            mean = a / (a + b)
            assert 0 < mean < 1, f"{spec.name}: derived mean {mean} out of (0,1)"


# ---------------------------------------------------------------------------
# LogNormal distribution properties
# ---------------------------------------------------------------------------

class TestLogNormalVariables:
    @pytest.fixture
    def lognormal_specs(self):
        return [s for s in MC_VARIABLE_TABLE.values() if s.distribution_type == DistributionType.LOGNORMAL]

    def test_sigma_positive(self, lognormal_specs):
        for spec in lognormal_specs:
            assert spec.params["sigma"] > 0, f"{spec.name}: sigma must be positive"

    def test_samples_always_positive(self, lognormal_specs):
        rng = np.random.default_rng(0)
        for spec in lognormal_specs:
            mu = spec.params["mu"]
            sigma = spec.params["sigma"]
            samples = rng.lognormal(mu, sigma, 500)
            assert np.all(samples > 0), f"{spec.name}: LogNormal samples not all positive"

    def test_multiplier_specs_centred_near_one(self):
        """Multiplier specs (mu = -0.5*sigma^2) should have E[X] ≈ 1."""
        for name in ["eligible_patients_mult", "net_price_mult", "peak_penetration_mult",
                     "label_breadth_mult", "rd_cost_mult", "competitor_share_mult"]:
            spec = MC_VARIABLE_TABLE[name]
            mu = spec.params["mu"]
            sigma = spec.params["sigma"]
            # E[X] = exp(mu + 0.5*sigma^2)
            expected_mean = math.exp(mu + 0.5 * sigma ** 2)
            assert abs(expected_mean - 1.0) < 0.01, (
                f"{name}: multiplier mean {expected_mean:.4f} not close to 1.0"
            )

    def test_confirmatory_cost_has_bernoulli_trigger(self):
        spec = MC_VARIABLE_TABLE["confirmatory_trial_cost_millions"]
        assert spec.bernoulli_trigger == "confirmatory_trial_required"
        assert spec.distribution_type == DistributionType.LOGNORMAL


# ---------------------------------------------------------------------------
# Normal distribution properties
# ---------------------------------------------------------------------------

class TestNormalVariables:
    @pytest.fixture
    def normal_specs(self):
        return [s for s in MC_VARIABLE_TABLE.values() if s.distribution_type == DistributionType.NORMAL]

    def test_std_positive(self, normal_specs):
        for spec in normal_specs:
            assert spec.params["std"] > 0, f"{spec.name}: std must be positive"

    def test_discount_rate_is_normal(self):
        spec = MC_VARIABLE_TABLE["discount_rate"]
        assert spec.distribution_type == DistributionType.NORMAL
        assert spec.params["mean"] == pytest.approx(0.10, abs=1e-6)

    def test_regulatory_duration_delta_is_normal(self):
        spec = MC_VARIABLE_TABLE["regulatory_duration_delta_years"]
        assert spec.distribution_type == DistributionType.NORMAL
        assert spec.params["mean"] == pytest.approx(0.0, abs=1e-6)


# ---------------------------------------------------------------------------
# Triangular distribution properties
# ---------------------------------------------------------------------------

class TestTriangularVariables:
    @pytest.fixture
    def triangular_specs(self):
        return [s for s in MC_VARIABLE_TABLE.values() if s.distribution_type == DistributionType.TRIANGULAR]

    def test_low_le_mode_le_high(self, triangular_specs):
        for spec in triangular_specs:
            low = spec.params["low"]
            mode = spec.params["mode"]
            high = spec.params["high"]
            assert low <= mode <= high, (
                f"{spec.name}: triangular params violate low <= mode <= high"
            )

    def test_years_to_peak_is_triangular(self):
        spec = MC_VARIABLE_TABLE["years_to_peak"]
        assert spec.distribution_type == DistributionType.TRIANGULAR

    def test_patent_life_is_triangular(self):
        spec = MC_VARIABLE_TABLE["patent_life_years"]
        assert spec.distribution_type == DistributionType.TRIANGULAR

    def test_samples_in_range(self, triangular_specs):
        rng = np.random.default_rng(1)
        for spec in triangular_specs:
            low = spec.params["low"]
            mode = spec.params["mode"]
            high = spec.params["high"]
            # scipy triangular: c = (mode-low)/(high-low), loc=low, scale=high-low
            from scipy.stats import triang
            c = (mode - low) / (high - low) if high > low else 0.5
            samples = triang(c=c, loc=low, scale=high - low).rvs(200, random_state=rng)
            assert np.all(samples >= low) and np.all(samples <= high), (
                f"{spec.name}: Triangular samples outside [low, high]"
            )


# ---------------------------------------------------------------------------
# Bernoulli distribution properties
# ---------------------------------------------------------------------------

class TestBernoulliVariables:
    @pytest.fixture
    def bernoulli_specs(self):
        return [s for s in MC_VARIABLE_TABLE.values() if s.distribution_type == DistributionType.BERNOULLI]

    def test_p_in_unit_interval(self, bernoulli_specs):
        for spec in bernoulli_specs:
            assert 0 < spec.params["p"] < 1, f"{spec.name}: p must be in (0,1)"

    def test_samples_only_zero_or_one(self, bernoulli_specs):
        rng = np.random.default_rng(77)
        for spec in bernoulli_specs:
            samples = (rng.uniform(0, 1, 1000) < spec.params["p"]).astype(int)
            assert set(np.unique(samples)).issubset({0, 1}), (
                f"{spec.name}: Bernoulli samples not in {{0,1}}"
            )

    def test_breakthrough_designation_is_bernoulli(self):
        spec = MC_VARIABLE_TABLE["breakthrough_designation"]
        assert spec.distribution_type == DistributionType.BERNOULLI

    def test_confirmatory_trial_required_is_bernoulli(self):
        spec = MC_VARIABLE_TABLE["confirmatory_trial_required"]
        assert spec.distribution_type == DistributionType.BERNOULLI

    def test_accelerated_approval_is_bernoulli(self):
        spec = MC_VARIABLE_TABLE["accelerated_approval"]
        assert spec.distribution_type == DistributionType.BERNOULLI


# ---------------------------------------------------------------------------
# Active / opt-in structure
# ---------------------------------------------------------------------------

class TestActiveFlags:
    def test_active_variables_is_subset_of_all(self):
        active_names = {s.name for s in ACTIVE_MC_VARIABLES}
        all_names = set(MC_VARIABLE_TABLE.keys())
        assert active_names.issubset(all_names)

    def test_at_least_one_active(self):
        assert len(ACTIVE_MC_VARIABLES) >= 1

    def test_at_least_one_inactive(self):
        inactive = [s for s in MC_VARIABLE_TABLE.values() if not s.active]
        assert len(inactive) >= 1

    def test_driver_based_vars_inactive_by_default(self):
        for name in ["eligible_patients_mult", "net_price_mult", "peak_penetration_mult"]:
            assert not MC_VARIABLE_TABLE[name].active


# ---------------------------------------------------------------------------
# Conditional (Bernoulli-triggered) variable
# ---------------------------------------------------------------------------

class TestConditionalVariables:
    def test_bernoulli_trigger_points_to_existing_variable(self):
        for spec in MC_VARIABLE_TABLE.values():
            if spec.bernoulli_trigger is not None:
                assert spec.bernoulli_trigger in MC_VARIABLE_TABLE, (
                    f"{spec.name}: bernoulli_trigger '{spec.bernoulli_trigger}' not in table"
                )

    def test_trigger_variable_is_bernoulli(self):
        for spec in MC_VARIABLE_TABLE.values():
            if spec.bernoulli_trigger is not None:
                trigger = MC_VARIABLE_TABLE[spec.bernoulli_trigger]
                assert trigger.distribution_type == DistributionType.BERNOULLI

"""Tests for scenario library and stress runner."""

import pytest

from bve.scenarios.stress_runner import ScenarioLibrary, StressRunner, StressResult


BASE_PARAMS = {
    "years_to_approval": 7.0,
    "trial_cost": 200.0,
    "pos_phase3": 0.60,
    "pos_nda_bla": 0.85,
    "peak_penetration": 0.25,
    "net_price": 150_000.0,
    "discount_rate": 0.10,
    "dilution_probability": 0.30,
    "mna_probability": 0.40,
    "mna_timing_months": 18.0,
    "addressable_patients": 50_000.0,
    "years_to_peak": 5.0,
}


@pytest.fixture
def library():
    return ScenarioLibrary()


@pytest.fixture
def runner(library):
    return StressRunner(library=library)


class TestScenarioLibrary:
    def test_loads_scenarios(self, library):
        assert len(library.all()) > 0

    def test_known_scenario_accessible(self, library):
        s = library.get("trial_delayed_18_months")
        assert s is not None
        assert s.name == "Trial delayed 18 months"

    def test_unknown_scenario_returns_none(self, library):
        assert library.get("nonexistent_scenario") is None

    def test_scenario_has_required_fields(self, library):
        for s in library.all():
            assert s.scenario_id
            assert s.name
            assert s.category
            assert s.description
            assert s.rationale
            assert len(s.shocks) > 0

    def test_by_category_returns_subset(self, library):
        regulatory = library.by_category("regulatory")
        assert len(regulatory) >= 1
        assert all(s.category == "regulatory" for s in regulatory)

    def test_scenario_ids_list(self, library):
        ids = library.scenario_ids()
        assert "trial_delayed_18_months" in ids
        assert "fda_raises_endpoint_bar" in ids

    def test_has_all_required_categories(self, library):
        categories = {s.category for s in library.all()}
        required = {"regulatory", "competitive", "financing", "clinical", "commercial", "mna"}
        assert required.issubset(categories)


class TestStressRunner:
    def test_run_trial_delay_increases_years(self, runner):
        result = runner.run("trial_delayed_18_months", BASE_PARAMS)
        assert result.stressed_values["years_to_approval"] > BASE_PARAMS["years_to_approval"]

    def test_run_trial_delay_increases_trial_cost(self, runner):
        result = runner.run("trial_delayed_18_months", BASE_PARAMS)
        # Shock is +0.20 (20% increase)
        assert result.stressed_values["trial_cost"] > BASE_PARAMS["trial_cost"]

    def test_run_competitor_reduces_penetration(self, runner):
        result = runner.run("competitor_beats_to_market", BASE_PARAMS)
        assert result.stressed_values["peak_penetration"] < BASE_PARAMS["peak_penetration"]

    def test_run_unknown_scenario_raises(self, runner):
        with pytest.raises(KeyError):
            runner.run("nonexistent_scenario", BASE_PARAMS)

    def test_base_values_unchanged(self, runner):
        original = dict(BASE_PARAMS)
        runner.run("trial_delayed_18_months", BASE_PARAMS)
        assert BASE_PARAMS == original

    def test_describe_contains_scenario_name(self, runner):
        result = runner.run("trial_delayed_18_months", BASE_PARAMS)
        desc = result.describe()
        assert "Trial delayed" in desc

    def test_run_top_n_returns_at_most_n(self, runner):
        ids = ["trial_delayed_18_months", "fda_raises_endpoint_bar", "competitor_beats_to_market", "fda_crl"]
        results = runner.run_top_n(ids, BASE_PARAMS, n=3)
        assert len(results) == 3

    def test_run_all_returns_all_scenarios(self, runner, library):
        results = runner.run_all(BASE_PARAMS)
        # Only scenarios whose params overlap with BASE_PARAMS will have shocked_params
        assert len(results) == len(library.all())

    def test_fda_crl_increases_years_to_approval(self, runner):
        result = runner.run("fda_crl", BASE_PARAMS)
        assert result.stressed_values["years_to_approval"] > BASE_PARAMS["years_to_approval"]

    def test_loe_urgency_increases_mna_probability(self, runner):
        result = runner.run("loe_urgency_accelerates", BASE_PARAMS)
        assert result.stressed_values["mna_probability"] > BASE_PARAMS["mna_probability"]

    def test_biotech_risk_off_increases_discount_rate(self, runner):
        result = runner.run("biotech_risk_off_drawdown", BASE_PARAMS)
        assert result.stressed_values["discount_rate"] > BASE_PARAMS["discount_rate"]

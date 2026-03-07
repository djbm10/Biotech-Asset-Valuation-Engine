"""
Tests for AssumptionsLoader (Step 1).

Covers:
  - Singleton behaviour and reset()
  - Required sections present
  - Validation rejects bad values
  - All backward-compat names in constants.py sourced correctly
  - New sections (loe_erosion_profiles, competition, trial_design) accessible
  - prob_approval_from_phase is correctly derived
  - Fallback accessors (phase_success_rates_for, gross_to_net, cogs_rate, loe_erosion_profile)
"""
from __future__ import annotations

import math
import textwrap
from pathlib import Path

import pytest
import yaml

from bve.config.assumptions_loader import AssumptionsLoader, AssumptionsValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_minimal_yaml(tmp_path: Path, overrides: dict | None = None) -> Path:
    """Write a minimal valid YAML to tmp_path/assumptions.yaml and return path."""
    base = yaml.safe_load(
        (Path(__file__).parent.parent / "src/bve/config/industry_assumptions.yaml")
        .read_text()
    )
    if overrides:
        def _deep_merge(d, u):
            for k, v in u.items():
                if isinstance(v, dict) and k in d:
                    _deep_merge(d[k], v)
                else:
                    d[k] = v
        _deep_merge(base, overrides)
    p = tmp_path / "assumptions.yaml"
    p.write_text(yaml.dump(base))
    return p


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_get_returns_same_instance(self):
        a1 = AssumptionsLoader.get()
        a2 = AssumptionsLoader.get()
        assert a1 is a2

    def test_reset_returns_new_instance(self, tmp_path):
        original = AssumptionsLoader.get()
        p = _write_minimal_yaml(tmp_path)
        new = AssumptionsLoader.reset(path=p)
        assert new is not original
        # restore default
        AssumptionsLoader.reset()

    def test_reset_none_reloads_default(self):
        a = AssumptionsLoader.reset()
        assert a is AssumptionsLoader.get()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_valid_file_loads_without_error(self):
        a = AssumptionsLoader.get()
        assert a.version is not None

    def test_missing_section_raises(self, tmp_path):
        base = yaml.safe_load(
            (Path(__file__).parent.parent / "src/bve/config/industry_assumptions.yaml")
            .read_text()
        )
        del base["phase_success_rates"]
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump(base))
        with pytest.raises(AssumptionsValidationError, match="phase_success_rates"):
            AssumptionsLoader(p)

    def test_phase_success_rate_out_of_range_raises(self, tmp_path):
        p = _write_minimal_yaml(tmp_path, {"phase_success_rates": {"all": {"phase_1": 1.5, "phase_2": 0.37, "phase_3": 0.60, "nda_bla": 0.87}}})
        with pytest.raises(AssumptionsValidationError, match="must be in"):
            AssumptionsLoader(p)

    def test_cap_positive_zero_raises(self, tmp_path):
        p = _write_minimal_yaml(tmp_path, {"trial_design": {"cap_logodds_positive": 0.0}})
        with pytest.raises(AssumptionsValidationError, match="must be > 0"):
            AssumptionsLoader(p)

    def test_cap_negative_positive_raises(self, tmp_path):
        p = _write_minimal_yaml(tmp_path, {"trial_design": {"cap_logodds_negative": 0.1}})
        with pytest.raises(AssumptionsValidationError, match="must be < 0"):
            AssumptionsLoader(p)

    def test_loe_loss_out_of_range_raises(self, tmp_path):
        p = _write_minimal_yaml(tmp_path, {
            "loe_erosion_profiles": {"small_molecule": {
                "year_1_loss": 1.5, "year_2_loss": 0.65, "year_3_loss": 0.80, "terminal_loss": 0.85
            }}
        })
        with pytest.raises(AssumptionsValidationError, match="must be in"):
            AssumptionsLoader(p)


# ---------------------------------------------------------------------------
# Phase success rates
# ---------------------------------------------------------------------------

class TestPhaseSuccessRates:
    def test_all_tas_present(self):
        a = AssumptionsLoader.get()
        expected_tas = {
            "all", "oncology", "rare_disease", "cns", "cardiovascular",
            "immunology", "infectious_disease", "ophthalmology", "other"
        }
        assert expected_tas.issubset(set(a.phase_success_rates.keys()))

    def test_all_phases_present_per_ta(self):
        a = AssumptionsLoader.get()
        for ta, phases in a.phase_success_rates.items():
            for ph in ("phase_1", "phase_2", "phase_3", "nda_bla"):
                assert ph in phases, f"{ta} missing {ph}"

    def test_values_in_unit_interval(self):
        a = AssumptionsLoader.get()
        for ta, phases in a.phase_success_rates.items():
            for ph, v in phases.items():
                assert 0 < v < 1, f"{ta}.{ph} = {v}"

    def test_fallback_returns_other(self):
        a = AssumptionsLoader.get()
        result = a.phase_success_rates_for("unknown_ta")
        assert result == a.phase_success_rates["other"]

    def test_oncology_lower_phase2_than_rare_disease(self):
        a = AssumptionsLoader.get()
        assert (
            a.phase_success_rates["oncology"]["phase_2"]
            < a.phase_success_rates["rare_disease"]["phase_2"]
        )


# ---------------------------------------------------------------------------
# Derived: prob_approval_from_phase
# ---------------------------------------------------------------------------

class TestProbApprovalFromPhase:
    def test_phase1_equals_product_of_all_phases(self):
        a = AssumptionsLoader.get()
        for ta, rates in a.phase_success_rates.items():
            expected = rates["phase_1"] * rates["phase_2"] * rates["phase_3"] * rates["nda_bla"]
            actual = a.prob_approval_from_phase[ta]["phase_1"]
            assert actual == pytest.approx(expected, rel=1e-6), f"Failed for {ta}"

    def test_nda_bla_equals_phase_success_nda(self):
        a = AssumptionsLoader.get()
        for ta, rates in a.phase_success_rates.items():
            assert a.prob_approval_from_phase[ta]["nda_bla"] == pytest.approx(
                rates["nda_bla"], rel=1e-6
            )

    def test_approval_prob_decreases_with_earlier_phase(self):
        """Earlier phase start = lower cumulative P(approval)."""
        a = AssumptionsLoader.get()
        p = a.prob_approval_from_phase["oncology"]
        assert p["phase_1"] < p["phase_2"] < p["phase_3"] < p["nda_bla"]


# ---------------------------------------------------------------------------
# Commercial defaults
# ---------------------------------------------------------------------------

class TestCommercialDefaults:
    def test_gross_to_net_modalities_present(self):
        a = AssumptionsLoader.get()
        for mod in ("small_molecule", "biologic", "gene_therapy", "other"):
            assert mod in a.gross_to_net_by_modality

    def test_gross_to_net_fallback(self):
        a = AssumptionsLoader.get()
        assert a.gross_to_net("unknown") == a.gross_to_net_by_modality["other"]

    def test_sgna_keys_present(self):
        a = AssumptionsLoader.get()
        for key in ("rate_launch", "rate_mature", "ramp_years"):
            assert key in a.sgna

    def test_sgna_launch_gt_mature(self):
        a = AssumptionsLoader.get()
        assert a.sgna["rate_launch"] > a.sgna["rate_mature"]


# ---------------------------------------------------------------------------
# LOE erosion profiles
# ---------------------------------------------------------------------------

class TestLOEErosionProfiles:
    def test_small_molecule_profile_present(self):
        a = AssumptionsLoader.get()
        p = a.loe_erosion_profile("small_molecule")
        assert "year_1_loss" in p

    def test_biologic_erodes_slower_than_small_molecule(self):
        a = AssumptionsLoader.get()
        sm = a.loe_erosion_profile("small_molecule")
        bio = a.loe_erosion_profile("biologic")
        assert bio["year_1_loss"] < sm["year_1_loss"]

    def test_erosion_increases_over_time(self):
        """Year 3 loss must be >= year 1 loss for all profiles."""
        a = AssumptionsLoader.get()
        for name, p in a.loe_erosion_profiles.items():
            assert p["year_3_loss"] >= p["year_1_loss"], (
                f"{name}: year_3_loss ({p['year_3_loss']}) < year_1_loss ({p['year_1_loss']})"
            )

    def test_terminal_loss_gte_year3(self):
        a = AssumptionsLoader.get()
        for name, p in a.loe_erosion_profiles.items():
            assert p["terminal_loss"] >= p["year_3_loss"], name

    def test_fallback_for_unknown_modality(self):
        a = AssumptionsLoader.get()
        result = a.loe_erosion_profile("unknown_modality")
        assert "year_1_loss" in result


# ---------------------------------------------------------------------------
# Trial design
# ---------------------------------------------------------------------------

class TestTrialDesign:
    def test_logodds_dimensions_present(self):
        a = AssumptionsLoader.get()
        for dim in ("endpoint_basis", "evidence_design", "approval_pathway"):
            assert dim in a.trial_design_logodds

    def test_surrogate_validated_is_reference_zero(self):
        a = AssumptionsLoader.get()
        assert a.trial_design_logodds["endpoint_basis"]["surrogate_validated"] == 0.0
        assert a.trial_design_logodds["evidence_design"]["rct_comparative"] == 0.0
        assert a.trial_design_logodds["approval_pathway"]["standard"] == 0.0

    def test_caps_have_correct_signs(self):
        a = AssumptionsLoader.get()
        assert a.trial_design_cap_positive > 0
        assert a.trial_design_cap_negative < 0

    def test_phase3_scaling_is_one(self):
        a = AssumptionsLoader.get()
        s = a.trial_design_phase_scaling["phase_3"]
        for dim in ("endpoint_basis", "evidence_design"):
            assert s[dim] == pytest.approx(1.0)

    def test_phase1_scaling_lower_than_phase3(self):
        a = AssumptionsLoader.get()
        p1 = a.trial_design_phase_scaling["phase_1"]
        p3 = a.trial_design_phase_scaling["phase_3"]
        for dim in ("endpoint_basis", "evidence_design"):
            assert p1[dim] < p3[dim]


# ---------------------------------------------------------------------------
# Backward compatibility: constants.py names unchanged
# ---------------------------------------------------------------------------

class TestBackwardCompatConstants:
    """
    Verify constants.py exports the same names with the same values.
    These tests protect all existing code that imports from constants.py.
    """

    def test_phase_success_rates_identical(self):
        from bve.config.constants import PHASE_SUCCESS_RATES
        from bve.config.assumptions_loader import AssumptionsLoader
        assert PHASE_SUCCESS_RATES == AssumptionsLoader.get().phase_success_rates

    def test_trial_design_logodds_identical(self):
        from bve.config.constants import TRIAL_DESIGN_LOGODDS
        from bve.config.assumptions_loader import AssumptionsLoader
        assert TRIAL_DESIGN_LOGODDS == AssumptionsLoader.get().trial_design_logodds

    def test_trial_design_caps_match(self):
        from bve.config.constants import TRIAL_DESIGN_CAP_POSITIVE, TRIAL_DESIGN_CAP_NEGATIVE
        from bve.config.assumptions_loader import AssumptionsLoader
        a = AssumptionsLoader.get()
        assert TRIAL_DESIGN_CAP_POSITIVE == pytest.approx(a.trial_design_cap_positive)
        assert TRIAL_DESIGN_CAP_NEGATIVE == pytest.approx(a.trial_design_cap_negative)

    def test_sgna_rates_match(self):
        from bve.config.constants import SGNA_RATE_LAUNCH, SGNA_RATE_MATURE, SGNA_RAMP_YEARS
        from bve.config.assumptions_loader import AssumptionsLoader
        sgna = AssumptionsLoader.get().sgna
        assert SGNA_RATE_LAUNCH == pytest.approx(sgna["rate_launch"])
        assert SGNA_RATE_MATURE == pytest.approx(sgna["rate_mature"])
        assert SGNA_RAMP_YEARS == int(sgna["ramp_years"])

    def test_phase_neutral_sentinel_unchanged(self):
        from bve.config.constants import TRIAL_DESIGN_PHASE_NEUTRAL
        assert TRIAL_DESIGN_PHASE_NEUTRAL == "neutral"

    def test_phase_order_unchanged(self):
        from bve.config.constants import PHASE_ORDER
        assert PHASE_ORDER == {"phase_1": 1, "phase_2": 2, "phase_3": 3, "nda_bla": 4}

    def test_mc_defaults_accessible(self):
        from bve.config.constants import MC_PEAK_SALES_CV, MC_DISCOUNT_RATE_STD, MC_PHASE_ESS
        assert 0 < MC_PEAK_SALES_CV < 1
        assert 0 < MC_DISCOUNT_RATE_STD < 0.20
        assert set(MC_PHASE_ESS.keys()) == {"phase_1", "phase_2", "phase_3", "nda_bla"}

    def test_mc_years_to_peak_std_and_patent_life_std_exported(self):
        from bve.config.constants import MC_YEARS_TO_PEAK_STD, MC_PATENT_LIFE_STD
        assert MC_YEARS_TO_PEAK_STD > 0
        assert MC_PATENT_LIFE_STD > 0


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_phase_success_rates_is_immutable(self):
        a = AssumptionsLoader.get()
        with pytest.raises(TypeError):
            a.phase_success_rates["new_ta"] = {}  # type: ignore[index]

    def test_nested_phase_rates_immutable(self):
        a = AssumptionsLoader.get()
        with pytest.raises(TypeError):
            a.phase_success_rates["oncology"]["phase_1"] = 0.99  # type: ignore[index]

    def test_loe_profiles_immutable(self):
        a = AssumptionsLoader.get()
        with pytest.raises(TypeError):
            a.loe_erosion_profiles["small_molecule"]["year_1_loss"] = 0.99  # type: ignore[index]

    def test_sgna_immutable(self):
        a = AssumptionsLoader.get()
        with pytest.raises(TypeError):
            a.sgna["rate_launch"] = 0.99  # type: ignore[index]


# ---------------------------------------------------------------------------
# Fallback warnings
# ---------------------------------------------------------------------------

class TestFallbackWarnings:
    def test_unknown_ta_emits_user_warning(self):
        a = AssumptionsLoader.get()
        with pytest.warns(UserWarning, match="not found in industry_assumptions"):
            a.phase_success_rates_for("unknown_ta")

    def test_unknown_modality_gross_to_net_warns(self):
        a = AssumptionsLoader.get()
        with pytest.warns(UserWarning, match="not found in gross_to_net"):
            a.gross_to_net("unknown_modality")

    def test_unknown_modality_cogs_rate_warns(self):
        a = AssumptionsLoader.get()
        with pytest.warns(UserWarning, match="not found in cogs_rate"):
            a.cogs_rate("unknown_modality")

    def test_unknown_modality_loe_profile_warns(self):
        a = AssumptionsLoader.get()
        with pytest.warns(UserWarning, match="not found in loe_erosion_profiles"):
            a.loe_erosion_profile("unknown_modality")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_provenance_has_required_keys(self):
        a = AssumptionsLoader.get()
        prov = a.provenance()
        assert set(prov.keys()) >= {"version", "path", "loaded_at", "sources"}

    def test_version_is_string(self):
        a = AssumptionsLoader.get()
        assert isinstance(a.provenance()["version"], str)

    def test_loaded_at_ends_with_z(self):
        a = AssumptionsLoader.get()
        assert a.provenance()["loaded_at"].endswith("Z")

    def test_sources_is_list(self):
        a = AssumptionsLoader.get()
        assert isinstance(a.provenance()["sources"], list)
        assert len(a.provenance()["sources"]) > 0

    def test_path_points_to_yaml(self):
        a = AssumptionsLoader.get()
        assert a.provenance()["path"].endswith(".yaml")


# ---------------------------------------------------------------------------
# commercial_defaults accessor
# ---------------------------------------------------------------------------

class TestCommercialDefaultsAccessor:
    def test_commercial_defaults_keys_present(self):
        a = AssumptionsLoader.get()
        defaults = a.commercial_defaults
        for key in ("discount_rate", "peak_penetration", "cogs_rate"):
            assert key in defaults, f"Missing key: {key}"

    def test_discount_rate_is_positive(self):
        a = AssumptionsLoader.get()
        assert float(a.commercial_defaults["discount_rate"]) > 0

    def test_peak_penetration_in_unit_interval(self):
        a = AssumptionsLoader.get()
        pp = float(a.commercial_defaults["peak_penetration"])
        assert 0 < pp <= 1

    def test_cogs_rate_in_unit_interval(self):
        a = AssumptionsLoader.get()
        cr = float(a.commercial_defaults["cogs_rate"])
        assert 0 < cr < 1

    def test_cli_fallbacks_match_loader_defaults(self):
        """run_asset.py fallback values must equal what AssumptionsLoader provides."""
        a = AssumptionsLoader.get()
        from bve.config.constants import MC_PEAK_SALES_CV, MC_DISCOUNT_RATE_STD, MC_YEARS_TO_PEAK_STD
        assert MC_PEAK_SALES_CV == pytest.approx(a.mc_peak_sales_cv)
        assert MC_DISCOUNT_RATE_STD == pytest.approx(a.mc_discount_rate_std)
        assert MC_YEARS_TO_PEAK_STD == pytest.approx(a.mc_years_to_peak_std)

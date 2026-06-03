"""
Block 37A — Stage-Specific M&A Transaction Priors
TDD tests written BEFORE implementation.

Tests for:
  A: transaction_mix_by_stage in industry_assumptions.yaml
  B: AssumptionsLoader.transaction_mix_by_stage property
  C: target_stage field on Layer5Inputs
  D: Stage-adjusted fractions used in compute_layer5()
  E: DERIVED_STAGE_ADJUSTED source tag
  F: Fallback to flat defaults when target_stage not set
"""
from __future__ import annotations

import pytest

from bve.config.assumptions_loader import AssumptionsLoader


# ---------------------------------------------------------------------------
# Block 37A-A: YAML structure
# ---------------------------------------------------------------------------

class TestTransactionMixYAML:

    def test_transaction_mix_by_stage_loaded(self):
        """transaction_mix_by_stage must be present in YAML."""
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        assert tmbs is not None
        assert len(tmbs) >= 6

    def test_all_expected_stages_present(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        for stage in ["preclinical", "phase_1", "phase_2", "phase_3", "nda_bla", "approved", "fallback"]:
            assert stage in tmbs, f"Stage {stage!r} missing from transaction_mix_by_stage"

    def test_preclinical_acquisition_fraction(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        assert tmbs["preclinical"]["acquisition"] == pytest.approx(0.15, abs=1e-3)

    def test_phase_3_acquisition_fraction(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        assert tmbs["phase_3"]["acquisition"] == pytest.approx(0.65, abs=1e-3)

    def test_approved_acquisition_fraction(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        assert tmbs["approved"]["acquisition"] == pytest.approx(0.80, abs=1e-3)

    def test_phase_1_license_fraction(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        assert tmbs["phase_1"]["license_or_partnership"] == pytest.approx(0.65, abs=1e-3)

    def test_fallback_fractions_present(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        fallback = tmbs["fallback"]
        assert "acquisition" in fallback
        assert "license_or_partnership" in fallback

    def test_fractions_dont_sum_to_one(self):
        """
        Acquisition + license fractions should NOT sum to 1.0 intentionally.
        Remainder = other deal structures (spin-offs, JVs, asset swaps, etc.).
        """
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        for stage, data in tmbs.items():
            total = data.get("acquisition", 0) + data.get("license_or_partnership", 0)
            assert total < 1.0, (
                f"Stage {stage!r}: acquisition+license = {total:.3f} should be < 1.0 "
                "(remainder = other deal structures)"
            )

    def test_fractions_individually_in_range(self):
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        for stage, data in tmbs.items():
            for key in ["acquisition", "license_or_partnership"]:
                val = data.get(key, 0)
                assert 0.0 <= val <= 1.0, f"Stage {stage!r} {key}={val} out of [0,1]"

    def test_acquisition_increases_with_stage(self):
        """Acquisition fraction must increase from preclinical → approved."""
        loader = AssumptionsLoader.get()
        tmbs = loader.transaction_mix_by_stage
        assert tmbs["preclinical"]["acquisition"] < tmbs["phase_2"]["acquisition"]
        assert tmbs["phase_2"]["acquisition"] < tmbs["phase_3"]["acquisition"]
        assert tmbs["phase_3"]["acquisition"] < tmbs["approved"]["acquisition"]


# ---------------------------------------------------------------------------
# Block 37A-B: AssumptionsLoader accessors
# ---------------------------------------------------------------------------

class TestAssumptionsLoaderAccessors:

    def test_get_transaction_mix_known_stage(self):
        """get_transaction_mix(stage) returns a dict with acquisition and license keys."""
        loader = AssumptionsLoader.get()
        mix = loader.get_transaction_mix("phase_2")
        assert isinstance(mix, dict)
        assert "acquisition" in mix
        assert "license_or_partnership" in mix

    def test_get_transaction_mix_phase_3(self):
        loader = AssumptionsLoader.get()
        mix = loader.get_transaction_mix("phase_3")
        assert mix["acquisition"] == pytest.approx(0.65, abs=1e-3)

    def test_get_transaction_mix_unknown_stage_falls_back_to_fallback(self):
        """Unknown stage falls back to 'fallback' entry with UserWarning."""
        import warnings
        loader = AssumptionsLoader.get()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mix = loader.get_transaction_mix("totally_unknown_stage_xyz")
        assert mix is not None
        assert "acquisition" in mix
        assert any("totally_unknown_stage_xyz" in str(warning.message) for warning in w)

    def test_get_transaction_mix_unknown_returns_fallback_values(self):
        """Unknown stage fallback values match the 'fallback' entry."""
        import warnings
        loader = AssumptionsLoader.get()
        fallback = loader.transaction_mix_by_stage["fallback"]
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            mix = loader.get_transaction_mix("unknown_stage")
        assert mix["acquisition"] == pytest.approx(fallback["acquisition"], abs=1e-6)
        assert mix["license_or_partnership"] == pytest.approx(fallback["license_or_partnership"], abs=1e-6)


# ---------------------------------------------------------------------------
# Block 37A-C: Layer5Inputs target_stage field
# ---------------------------------------------------------------------------

class TestLayer5InputsTargetStage:

    def test_target_stage_field_exists(self):
        from bve.intelligence.ma_layer5_calibration import Layer5Inputs
        inp = Layer5Inputs(
            rank_score=0.5, rank_percentile=0.5, strategic_priority=0.5,
            transaction_probability=0.5, asset_quality=0.5, seller_willingness=0.5,
        )
        assert hasattr(inp, "target_stage")

    def test_target_stage_default_none(self):
        from bve.intelligence.ma_layer5_calibration import Layer5Inputs
        inp = Layer5Inputs(
            rank_score=0.5, rank_percentile=0.5, strategic_priority=0.5,
            transaction_probability=0.5, asset_quality=0.5, seller_willingness=0.5,
        )
        assert inp.target_stage is None

    def test_target_stage_accepts_string(self):
        from bve.intelligence.ma_layer5_calibration import Layer5Inputs
        inp = Layer5Inputs(
            rank_score=0.5, rank_percentile=0.5, strategic_priority=0.5,
            transaction_probability=0.5, asset_quality=0.5, seller_willingness=0.5,
            target_stage="phase_2",
        )
        assert inp.target_stage == "phase_2"


# ---------------------------------------------------------------------------
# Block 37A-D: Stage-adjusted fractions in compute_layer5()
# ---------------------------------------------------------------------------

def _make_inputs(**kwargs):
    from bve.intelligence.ma_layer5_calibration import Layer5Inputs
    defaults = dict(
        rank_score=0.6, rank_percentile=0.6, strategic_priority=0.6,
        transaction_probability=0.6, asset_quality=0.6, seller_willingness=0.6,
    )
    defaults.update(kwargs)
    return Layer5Inputs(**defaults)


class TestStageAdjustedFractions:

    def test_phase_3_higher_acquisition_than_phase_1(self):
        """Phase 3 has higher acquisition fraction → higher p_full_acquisition."""
        from bve.intelligence.ma_layer5_calibration import compute_layer5
        out_ph3 = compute_layer5(_make_inputs(target_stage="phase_3"))
        out_ph1 = compute_layer5(_make_inputs(target_stage="phase_1"))
        # Same p_any but different acquisition fractions
        # p_full_acq = acq_fraction * p_any, so phase_3 > phase_1
        assert out_ph3.p_full_acquisition_12m >= out_ph1.p_full_acquisition_12m

    def test_preclinical_lower_acquisition_than_approved(self):
        """Preclinical acquisition fraction 0.15 < approved 0.80."""
        from bve.intelligence.ma_layer5_calibration import compute_layer5
        out_pre = compute_layer5(_make_inputs(target_stage="preclinical"))
        out_app = compute_layer5(_make_inputs(target_stage="approved"))
        assert out_pre.p_full_acquisition_12m <= out_app.p_full_acquisition_12m

    def test_no_target_stage_uses_flat_defaults(self):
        """Without target_stage, fractions from Layer5Inputs.acquisition_fraction used."""
        from bve.intelligence.ma_layer5_calibration import compute_layer5
        out_no_stage = compute_layer5(_make_inputs())
        out_explicit_fallback = compute_layer5(_make_inputs(
            acquisition_fraction=0.60,  # flat default from Layer5Inputs
            license_fraction=0.35,
        ))
        # Both should produce the same result
        assert out_no_stage.p_full_acquisition_12m == pytest.approx(
            out_explicit_fallback.p_full_acquisition_12m, abs=1e-4
        )

    def test_unknown_stage_falls_back_to_fallback_fractions(self):
        """Unknown target_stage should use fallback fractions without error."""
        import warnings
        from bve.intelligence.ma_layer5_calibration import compute_layer5
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            out = compute_layer5(_make_inputs(target_stage="totally_invalid_stage_xyz"))
        assert out is not None
        assert out.p_full_acquisition_12m >= 0.0


# ---------------------------------------------------------------------------
# Block 37A-E: DERIVED_STAGE_ADJUSTED source tag
# ---------------------------------------------------------------------------

class TestDerivedStageAdjustedTag:

    def test_derived_stage_adjusted_enum_exists(self):
        """ProbabilitySource.DERIVED_STAGE_ADJUSTED must exist."""
        from bve.intelligence.ma_layer5_calibration import ProbabilitySource
        assert hasattr(ProbabilitySource, "DERIVED_STAGE_ADJUSTED")

    def test_source_tag_is_derived_stage_adjusted_when_stage_set(self):
        """When target_stage is set, p_full_acquisition_source = DERIVED_STAGE_ADJUSTED."""
        from bve.intelligence.ma_layer5_calibration import compute_layer5, ProbabilitySource
        out = compute_layer5(_make_inputs(target_stage="phase_2"))
        assert out.p_full_acquisition_source == ProbabilitySource.DERIVED_STAGE_ADJUSTED

    def test_source_tag_is_derived_when_no_stage(self):
        """Without target_stage, p_full_acquisition_source = DERIVED (flat prior)."""
        from bve.intelligence.ma_layer5_calibration import compute_layer5, ProbabilitySource
        out = compute_layer5(_make_inputs())
        assert out.p_full_acquisition_source == ProbabilitySource.DERIVED

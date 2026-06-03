"""
Block 21 — M&A Score Decomposition (Attribution Layer)
TDD tests written BEFORE implementation.

Tests for:
  1. DriverComponent dataclass fields and validation
  2. GateSummary dataclass fields
  3. ScoreComposition dataclass fields and invariants
  4. compute_score_decomposition() function
  5. _EXPLANATORY_DRIVER_WEIGHTS sums to 1.0 and has all 8 buckets
  6. Layer5Inputs.include_decomposition opt-in field
  7. Layer5Output.score_composition Optional[ScoreComposition]
  8. Integration: compute_layer5(include_decomposition=True) attaches decomposition
  9. Attribution labelling — contributions are clearly "approximate"
  10. Decomposition does not change rank_score or any probability output
"""
from __future__ import annotations

import pytest

from bve.intelligence.ma_score_decomposition import (
    DriverComponent,
    GateSummary,
    ScoreComposition,
    _EXPLANATORY_DRIVER_WEIGHTS,
    compute_score_decomposition,
)
from bve.intelligence.ma_layer5_calibration import (
    Layer5Inputs,
    Layer5Output,
    compute_layer5,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _base_layer5_inputs(**kwargs) -> Layer5Inputs:
    defaults = dict(
        rank_score=0.55,
        rank_percentile=0.65,
        strategic_priority=0.60,
        transaction_probability=0.50,
        asset_quality=0.70,
        seller_willingness=0.55,
        base_rate=0.08,
        comparable_bucket_rate=0.12,
        n_comparable_observations=10,
        target_name="TestCo",
        as_of_date="2026-05-27",
    )
    defaults.update(kwargs)
    return Layer5Inputs(**defaults)


def _make_decomp_inputs(**kwargs) -> dict:
    """Minimal input dict for compute_score_decomposition."""
    defaults = dict(
        target_name="TestCo",
        acquirer_id=None,
        final_score=0.55,
        rank_score=0.55,
        asset_quality=0.70,
        seller_willingness=0.55,
        strategic_priority=0.60,
        transaction_probability=0.50,
        active_driver_bucket_count=3,
        active_gate_ids=["G1"],
        watchlist_class="strategic_radar",
        data_confidence_score=0.75,
        base_rate=0.08,
        comparable_bucket_rate=0.12,
        comparable_bucket_rate_source="segment_report",
        n_comparable_observations=10,
        shrinkage_weights=(0.4, 0.4, 0.2),
        calibration_base_rate=0.08,
        calibration_comparable_rate=0.12,
    )
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Block 21-A: _EXPLANATORY_DRIVER_WEIGHTS schema
# ---------------------------------------------------------------------------

class TestExplanatoryDriverWeights:

    def test_weights_sum_to_one(self):
        total = sum(_EXPLANATORY_DRIVER_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_eight_buckets(self):
        assert len(_EXPLANATORY_DRIVER_WEIGHTS) == 8

    def test_required_buckets_present(self):
        required = {
            "target_quality", "buyer_mandate", "strategic_fit",
            "strategic_urgency", "deal_momentum", "seller_readiness",
            "transaction_realism", "information_readiness",
        }
        assert required == set(_EXPLANATORY_DRIVER_WEIGHTS.keys())

    def test_all_weights_positive(self):
        for k, v in _EXPLANATORY_DRIVER_WEIGHTS.items():
            assert v > 0.0, f"Weight for {k!r} must be > 0"


# ---------------------------------------------------------------------------
# Block 21-B: DriverComponent dataclass
# ---------------------------------------------------------------------------

class TestDriverComponent:

    def test_fields_present(self):
        dc = DriverComponent(
            driver="target_quality",
            label="Target Quality",
            raw_score=0.70,
            weight=0.25,
            contribution=0.175,
            data_available=True,
            source_layer="Layer 1",
            notes="Approximate attribution",
        )
        assert dc.driver == "target_quality"
        assert dc.label == "Target Quality"
        assert dc.raw_score == pytest.approx(0.70)
        assert dc.weight == pytest.approx(0.25)
        assert dc.contribution == pytest.approx(0.175)
        assert dc.data_available is True
        assert dc.source_layer == "Layer 1"
        assert dc.notes == "Approximate attribution"

    def test_contribution_is_weight_times_raw_score(self):
        dc = DriverComponent(
            driver="buyer_mandate",
            label="Buyer Mandate",
            raw_score=0.60,
            weight=0.15,
            contribution=round(0.60 * 0.15, 4),
            data_available=True,
            source_layer="Layer 2",
            notes="",
        )
        assert dc.contribution == pytest.approx(dc.raw_score * dc.weight, abs=1e-4)


# ---------------------------------------------------------------------------
# Block 21-C: GateSummary dataclass
# ---------------------------------------------------------------------------

class TestGateSummary:

    def test_fields_present(self):
        gs = GateSummary(
            gate_id="G1",
            description="Minimum threshold gate",
            triggered=True,
            effect="score_cap:0.5",
        )
        assert gs.gate_id == "G1"
        assert gs.description == "Minimum threshold gate"
        assert gs.triggered is True
        assert gs.effect == "score_cap:0.5"

    def test_effect_values(self):
        for effect in ("pass", "score_cap:0.5", "hard_fail", "no_effect"):
            gs = GateSummary(gate_id="G0", description="x", triggered=False, effect=effect)
            assert gs.effect == effect


# ---------------------------------------------------------------------------
# Block 21-D: ScoreComposition dataclass
# ---------------------------------------------------------------------------

class TestScoreComposition:

    def _make_simple_composition(self) -> ScoreComposition:
        components = [
            DriverComponent(
                driver=k,
                label=k.replace("_", " ").title(),
                raw_score=0.5,
                weight=w,
                contribution=round(0.5 * w, 4),
                data_available=True,
                source_layer="Layer 1",
                notes="approximate attribution",
            )
            for k, w in _EXPLANATORY_DRIVER_WEIGHTS.items()
        ]
        return ScoreComposition(
            target_name="TestCo",
            acquirer_id=None,
            final_score=0.55,
            weighted_sum=round(sum(c.contribution for c in components), 4),
            components=components,
            gate_summary=[GateSummary("G1", "desc", False, "no_effect")],
            calibration_shrinkage_weights=(0.4, 0.4, 0.2),
            calibration_base_rate=0.08,
            calibration_comparable_rate=0.12,
            calibration_comparable_rate_source="segment_report",
            n_comparable_observations=10,
            score_floor_applied=False,
            score_cap_applied=False,
            cap_value=None,
        )

    def test_construction_succeeds(self):
        sc = self._make_simple_composition()
        assert sc.target_name == "TestCo"
        assert sc.final_score == pytest.approx(0.55)

    def test_components_cover_all_eight_drivers(self):
        sc = self._make_simple_composition()
        driver_names = {c.driver for c in sc.components}
        assert driver_names == set(_EXPLANATORY_DRIVER_WEIGHTS.keys())

    def test_weighted_sum_field_present(self):
        sc = self._make_simple_composition()
        assert hasattr(sc, "weighted_sum")
        assert sc.weighted_sum > 0.0

    def test_gate_summary_list_present(self):
        sc = self._make_simple_composition()
        assert isinstance(sc.gate_summary, list)

    def test_calibration_fields_present(self):
        sc = self._make_simple_composition()
        assert sc.calibration_base_rate == pytest.approx(0.08)
        assert sc.calibration_comparable_rate == pytest.approx(0.12)
        assert sc.calibration_comparable_rate_source == "segment_report"
        assert sc.n_comparable_observations == 10

    def test_score_floor_and_cap_flags(self):
        sc = self._make_simple_composition()
        assert sc.score_floor_applied is False
        assert sc.score_cap_applied is False
        assert sc.cap_value is None


# ---------------------------------------------------------------------------
# Block 21-E: compute_score_decomposition()
# ---------------------------------------------------------------------------

class TestComputeScoreDecomposition:

    def test_returns_score_composition(self):
        inp = _make_decomp_inputs()
        result = compute_score_decomposition(**inp)
        assert isinstance(result, ScoreComposition)

    def test_all_eight_components_present(self):
        inp = _make_decomp_inputs()
        result = compute_score_decomposition(**inp)
        driver_names = {c.driver for c in result.components}
        assert driver_names == set(_EXPLANATORY_DRIVER_WEIGHTS.keys())

    def test_contributions_sum_near_weighted_sum(self):
        inp = _make_decomp_inputs()
        result = compute_score_decomposition(**inp)
        manual_sum = sum(c.contribution for c in result.components)
        assert abs(manual_sum - result.weighted_sum) < 1e-4

    def test_approximate_attribution_label_in_notes(self):
        """Every component notes field must mention 'approximate'."""
        inp = _make_decomp_inputs()
        result = compute_score_decomposition(**inp)
        for c in result.components:
            assert "approximate" in c.notes.lower(), (
                f"Component {c.driver!r} notes do not mention 'approximate': {c.notes!r}"
            )

    def test_does_not_modify_final_score(self):
        """Decomposition is attribution only — final_score equals input."""
        inp = _make_decomp_inputs(final_score=0.62)
        result = compute_score_decomposition(**inp)
        assert result.final_score == pytest.approx(0.62)

    def test_gate_summary_reflects_active_gates(self):
        inp = _make_decomp_inputs(active_gate_ids=["G1", "G3"])
        result = compute_score_decomposition(**inp)
        gate_ids = {g.gate_id for g in result.gate_summary}
        assert "G1" in gate_ids
        assert "G3" in gate_ids

    def test_no_gates_gives_empty_or_no_effect_gate_summary(self):
        inp = _make_decomp_inputs(active_gate_ids=[])
        result = compute_score_decomposition(**inp)
        # Either empty or all gates show no_effect
        for g in result.gate_summary:
            assert g.triggered is False or g.effect in ("no_effect", "pass")


# ---------------------------------------------------------------------------
# Block 21-F: Layer5Inputs opt-in field
# ---------------------------------------------------------------------------

class TestLayer5InputsDecompositionField:

    def test_include_decomposition_defaults_false(self):
        inp = _base_layer5_inputs()
        assert inp.include_decomposition is False

    def test_include_decomposition_can_be_set_true(self):
        inp = _base_layer5_inputs(include_decomposition=True)
        assert inp.include_decomposition is True


# ---------------------------------------------------------------------------
# Block 21-G: Layer5Output.score_composition field
# ---------------------------------------------------------------------------

class TestLayer5OutputDecompositionField:

    def test_score_composition_default_none(self):
        out = compute_layer5(_base_layer5_inputs())
        assert out.score_composition is None

    def test_score_composition_attached_when_opted_in(self):
        inp = _base_layer5_inputs(include_decomposition=True)
        out = compute_layer5(inp)
        assert out.score_composition is not None
        assert isinstance(out.score_composition, ScoreComposition)

    def test_decomposition_does_not_change_rank_score(self):
        """Attribution layer must not alter any probability or rank output."""
        inp_base = _base_layer5_inputs()
        inp_decomp = _base_layer5_inputs(include_decomposition=True)
        out_base = compute_layer5(inp_base)
        out_decomp = compute_layer5(inp_decomp)
        assert out_base.rank_score == pytest.approx(out_decomp.rank_score)
        assert out_base.p_any_strategic_transaction_12m == pytest.approx(
            out_decomp.p_any_strategic_transaction_12m
        )
        assert out_base.p_takeout_12m == pytest.approx(out_decomp.p_takeout_12m)
        assert out_base.confidence_level == out_decomp.confidence_level

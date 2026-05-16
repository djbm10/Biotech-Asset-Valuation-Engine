"""
Tests for P3.2 — Acquirer urgency map: buyer-target matrix.

Verifies:
- build_acquirer_matrix returns AcquirerMatrix with correct dimensions
- cells[i][j] matches acquirer i and target j
- composite_score in [0, 1]
- ta_match reflects whether TA is in acquirer.strategic_areas
- budget_ok reflects affordability gate
- stage_match is 0.0/0.5/1.0
- top_pairs() returns correct number sorted descending
- scores_for_target() returns all acquirers for a target, sorted
- scores_for_acquirer() returns all targets for an acquirer, sorted
- get_cell() finds the correct cell by id+name
- heat_map_dict() structure and values
- as_csv_rows() header and dimensions
- as_heat_map_text() returns non-empty string
- empty targets raises ValueError
- weights not summing to 1 raises ValueError
- heat_level values are valid
- TargetSpec.short_label() uses ticker when available
- loe_urgency in [0, 1] for all cells
- custom universe works
"""
from __future__ import annotations

import pytest

from bve.analysis.acquirer_matrix import (
    AcquirerMatrix,
    MatrixCell,
    TargetSpec,
    build_acquirer_matrix,
)
from bve.entities.acquirer import AcquirerProfile, ACQUIRER_UNIVERSE


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ONCO_TARGET = TargetSpec(
    name="OncoCo",
    ticker="ONCO",
    therapeutic_area="oncology",
    modality="biologic",
    deal_size_millions=2000.0,
    stage="Phase 3",
)

IMMUNO_TARGET = TargetSpec(
    name="ImmunoCo",
    ticker="IMCO",
    therapeutic_area="immunology",
    modality="small_molecule",
    deal_size_millions=500.0,
    stage="Phase 2",
)

LARGE_TARGET = TargetSpec(
    name="BigTarget",
    therapeutic_area="oncology",
    modality="biologic",
    deal_size_millions=50_000.0,  # unaffordable for most
    stage="Phase 3",
)


def _tiny_universe() -> list[AcquirerProfile]:
    """Two-acquirer universe for fast tests."""
    from bve.entities.acquirer import ACQUIRER_BY_ID
    return [ACQUIRER_BY_ID["pfizer"], ACQUIRER_BY_ID["merck"]]


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestMatrixStructure:
    def test_matrix_returns_acquirer_matrix(self):
        m = build_acquirer_matrix([ONCO_TARGET], universe=_tiny_universe())
        assert isinstance(m, AcquirerMatrix)

    def test_matrix_dimensions(self):
        universe = _tiny_universe()
        m = build_acquirer_matrix([ONCO_TARGET, IMMUNO_TARGET], universe=universe)
        assert len(m.cells) == len(universe)           # rows = acquirers
        assert all(len(row) == 2 for row in m.cells)   # cols = targets

    def test_cell_is_matrix_cell(self):
        m = build_acquirer_matrix([ONCO_TARGET], universe=_tiny_universe())
        assert isinstance(m.cells[0][0], MatrixCell)

    def test_cell_acquirer_name_matches_row(self):
        universe = _tiny_universe()
        m = build_acquirer_matrix([ONCO_TARGET], universe=universe)
        for acq, row in zip(universe, m.cells):
            assert row[0].acquirer_id == acq.company_id

    def test_cell_target_name_matches_col(self):
        universe = _tiny_universe()
        targets = [ONCO_TARGET, IMMUNO_TARGET]
        m = build_acquirer_matrix(targets, universe=universe)
        for row in m.cells:
            for cell, target in zip(row, targets):
                assert cell.target_name == target.name

    def test_composite_score_in_unit_interval(self):
        m = build_acquirer_matrix([ONCO_TARGET, IMMUNO_TARGET], universe=_tiny_universe())
        for row in m.cells:
            for cell in row:
                assert 0.0 <= cell.composite_score <= 1.0

    def test_weights_stored(self):
        m = build_acquirer_matrix([ONCO_TARGET], universe=_tiny_universe())
        assert "ta" in m.weights
        assert abs(sum(m.weights.values()) - 1.0) < 0.01


# ---------------------------------------------------------------------------
# Scoring correctness
# ---------------------------------------------------------------------------

class TestScoring:
    def test_ta_match_true_for_oncology(self):
        """Pfizer covers oncology — ta_match should be True for oncology target."""
        m = build_acquirer_matrix([ONCO_TARGET], universe=_tiny_universe())
        pfizer_cell = m.get_cell("pfizer", "OncoCo")
        assert pfizer_cell is not None
        assert pfizer_cell.ta_match is True

    def test_ta_match_false_for_mismatch(self):
        """Gilead focuses on hiv/liver/oncology; test a TA not in its areas."""
        from bve.entities.acquirer import ACQUIRER_BY_ID
        gilead = ACQUIRER_BY_ID["gilead"]
        neuro_target = TargetSpec(
            name="NeuroCo",
            therapeutic_area="neuroscience_rare",  # not in Gilead's areas
            modality="small_molecule",
            deal_size_millions=500.0,
            stage="Phase 2",
        )
        m = build_acquirer_matrix([neuro_target], universe=[gilead])
        cell = m.get_cell("gilead", "NeuroCo")
        assert cell.ta_match is False

    def test_budget_ok_true_for_affordable(self):
        """$500M target should be affordable for most large pharma."""
        m = build_acquirer_matrix([IMMUNO_TARGET], universe=_tiny_universe())
        for row in m.cells:
            # $500M is well within 25% of multi-billion firepower
            assert row[0].budget_ok is True

    def test_budget_ok_false_for_unaffordable(self):
        """$50B target is unaffordable even for the biggest buyers."""
        m = build_acquirer_matrix([LARGE_TARGET], universe=_tiny_universe())
        for row in m.cells:
            assert row[0].budget_ok is False

    def test_stage_match_1_for_phase3_match(self):
        """Pfizer prefers Phase 3; target is Phase 3 → stage_match=1.0."""
        m = build_acquirer_matrix([ONCO_TARGET], universe=_tiny_universe())
        pfizer_cell = m.get_cell("pfizer", "OncoCo")
        assert pfizer_cell.stage_match == pytest.approx(1.0)

    def test_stage_match_0_for_mismatch(self):
        """Phase 1 target vs Phase 3-preferred acquirer → stage_match=0.0."""
        phase1_target = TargetSpec(
            name="EarlyCo",
            therapeutic_area="oncology",
            modality="biologic",
            deal_size_millions=200.0,
            stage="Phase 1",
        )
        from bve.entities.acquirer import ACQUIRER_BY_ID
        pfizer = ACQUIRER_BY_ID["pfizer"]
        m = build_acquirer_matrix([phase1_target], universe=[pfizer])
        cell = m.get_cell("pfizer", "EarlyCo")
        assert cell.stage_match == pytest.approx(0.0)

    def test_loe_urgency_in_unit_interval(self):
        m = build_acquirer_matrix([ONCO_TARGET], universe=ACQUIRER_UNIVERSE)
        for row in m.cells:
            assert 0.0 <= row[0].loe_urgency <= 1.0

    def test_higher_loe_lifts_composite(self):
        """Acquirer with higher LOE urgency should score ≥ acquirer with zero LOE."""
        from bve.entities.acquirer import LOECliff
        no_loe = AcquirerProfile(
            company_id="no_loe",
            name="NoLOE Pharma",
            cash_millions=10_000,
            annual_fcf_millions=5_000,
            strategic_areas=["oncology"],
            preferred_modalities=["biologic"],
            preferred_phase="Phase 3",
        )
        high_loe = AcquirerProfile(
            company_id="high_loe",
            name="HighLOE Pharma",
            cash_millions=10_000,
            annual_fcf_millions=5_000,
            strategic_areas=["oncology"],
            preferred_modalities=["biologic"],
            preferred_phase="Phase 3",
            loe_cliffs=[
                LOECliff(
                    product_name="BlockbusterA",
                    indication="cancer",
                    peak_sales_millions=10_000,
                    loe_year=2027,
                    revenue_at_risk_millions=8_000,
                )
            ],
        )
        m = build_acquirer_matrix([ONCO_TARGET], universe=[no_loe, high_loe])
        cell_no_loe = m.get_cell("no_loe", "OncoCo")
        cell_high_loe = m.get_cell("high_loe", "OncoCo")
        assert cell_high_loe.composite_score > cell_no_loe.composite_score


# ---------------------------------------------------------------------------
# Ranked accessors
# ---------------------------------------------------------------------------

class TestRankedAccessors:
    def setup_method(self):
        self.m = build_acquirer_matrix(
            [ONCO_TARGET, IMMUNO_TARGET], universe=ACQUIRER_UNIVERSE
        )

    def test_top_pairs_returns_correct_count(self):
        top = self.m.top_pairs(5)
        assert len(top) == 5

    def test_top_pairs_sorted_descending(self):
        top = self.m.top_pairs(5)
        scores = [c.composite_score for c in top]
        assert scores == sorted(scores, reverse=True)

    def test_top_pairs_more_than_available(self):
        top = self.m.top_pairs(n=1000)
        expected = len(ACQUIRER_UNIVERSE) * 2  # all (acquirer, target) pairs
        assert len(top) == expected

    def test_scores_for_target_has_all_acquirers(self):
        cells = self.m.scores_for_target("OncoCo")
        assert len(cells) == len(ACQUIRER_UNIVERSE)

    def test_scores_for_target_sorted(self):
        cells = self.m.scores_for_target("OncoCo")
        scores = [c.composite_score for c in cells]
        assert scores == sorted(scores, reverse=True)

    def test_scores_for_target_all_same_target(self):
        cells = self.m.scores_for_target("OncoCo")
        assert all(c.target_name == "OncoCo" for c in cells)

    def test_scores_for_acquirer_has_all_targets(self):
        cells = self.m.scores_for_acquirer("pfizer")
        assert len(cells) == 2  # two targets in the matrix

    def test_scores_for_acquirer_sorted(self):
        cells = self.m.scores_for_acquirer("pfizer")
        scores = [c.composite_score for c in cells]
        assert scores == sorted(scores, reverse=True)

    def test_get_cell_found(self):
        cell = self.m.get_cell("pfizer", "OncoCo")
        assert cell is not None
        assert cell.acquirer_id == "pfizer"
        assert cell.target_name == "OncoCo"

    def test_get_cell_not_found(self):
        cell = self.m.get_cell("nonexistent", "OncoCo")
        assert cell is None


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

class TestExportHelpers:
    def setup_method(self):
        self.m = build_acquirer_matrix(
            [ONCO_TARGET, IMMUNO_TARGET], universe=_tiny_universe()
        )

    def test_heat_map_dict_structure(self):
        hm = self.m.heat_map_dict()
        assert isinstance(hm, dict)
        for acq_name, targets in hm.items():
            assert isinstance(acq_name, str)
            assert isinstance(targets, dict)
            for t_name, score in targets.items():
                assert isinstance(score, float)
                assert 0.0 <= score <= 1.0

    def test_heat_map_dict_has_all_acquirers(self):
        hm = self.m.heat_map_dict()
        assert len(hm) == len(_tiny_universe())

    def test_heat_map_dict_has_all_targets(self):
        hm = self.m.heat_map_dict()
        for targets in hm.values():
            assert "OncoCo" in targets
            assert "ImmunoCo" in targets

    def test_as_csv_rows_header(self):
        rows = self.m.as_csv_rows()
        header = rows[0]
        assert header[0] == "Acquirer"
        assert "OncoCo" in header
        assert "ImmunoCo" in header

    def test_as_csv_rows_dimensions(self):
        rows = self.m.as_csv_rows()
        assert len(rows) == len(_tiny_universe()) + 1  # +1 for header
        for row in rows[1:]:
            assert len(row) == 3  # acquirer + 2 targets

    def test_as_heat_map_text_is_string(self):
        text = self.m.as_heat_map_text()
        assert isinstance(text, str)
        assert len(text) > 0
        assert "Pfizer" in text


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_empty_targets_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_acquirer_matrix([])

    def test_bad_weights_raises(self):
        with pytest.raises(ValueError, match="sum"):
            build_acquirer_matrix(
                [ONCO_TARGET],
                ta_weight=0.5, loe_weight=0.5, budget_weight=0.5, stage_weight=0.5,
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestTargetSpec:
    def test_short_label_uses_ticker(self):
        spec = TargetSpec("LongCompanyName Inc", "oncology", "biologic", 1000.0, ticker="LCNI")
        assert spec.short_label() == "LCNI"

    def test_short_label_truncates_name_when_no_ticker(self):
        spec = TargetSpec("LongCompanyName Inc", "oncology", "biologic", 1000.0)
        assert len(spec.short_label()) <= 12


class TestHeatLevel:
    def test_hot_above_0_7(self):
        cell = MatrixCell("x", "X", "T", True, True, 1.0, True, 1.0, 0.80)
        assert cell.heat_level == "hot"

    def test_warm_0_5_to_0_7(self):
        cell = MatrixCell("x", "X", "T", True, True, 0.3, True, 0.5, 0.55)
        assert cell.heat_level == "warm"

    def test_cool_0_3_to_0_5(self):
        cell = MatrixCell("x", "X", "T", False, False, 0.1, True, 0.5, 0.35)
        assert cell.heat_level == "cool"

    def test_cold_below_0_3(self):
        cell = MatrixCell("x", "X", "T", False, False, 0.0, False, 0.0, 0.10)
        assert cell.heat_level == "cold"

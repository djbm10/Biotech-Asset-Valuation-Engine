"""Tests for the S&E shortlist driver (Idea 13).

The driver is a pure join: ScienceThesisBuilder -> Layer15BuyerMatcher ->
build_buyer_problem_shortlist. These anchors prove it ranks the eligible set,
records gate-failers (with their gate, via Idea 14), respects ``limit``, and that
the memo template renders for both empty and populated shortlists.
"""
from __future__ import annotations

from bve.cli.se_shortlist import _render_memo, _render_table
from bve.intelligence.science_thesis import BuyerProblem, EvidenceGrade
from bve.intelligence.se_shortlist import ShortlistAssetInput, build_se_shortlist


def _problem(**overrides) -> BuyerProblem:
    base = dict(buyer_id="vertex", buyer_name="Vertex", required_ta=["hematology"])
    base.update(overrides)
    return BuyerProblem(**base)


def _asset(asset_id: str, **overrides) -> ShortlistAssetInput:
    base = dict(
        asset_id=asset_id,
        asset_name=asset_id.title(),
        therapeutic_area="hematology",
        modality="small molecule",
        target="HBF",
        evidence_grade=EvidenceGrade.DILIGENCE_CONFIRMED,
    )
    base.update(overrides)
    return ShortlistAssetInput(**base)


def test_driver_ranks_eligible_and_records_gate_failure() -> None:
    assets = [
        _asset("low", problem_solution_fit=0.2),
        _asset("high", problem_solution_fit=0.95, has_human_poc=True),
        # Fails the only-hematology gate -> excluded, never scored.
        _asset("blocked", therapeutic_area="oncology"),
    ]
    shortlist = build_se_shortlist(_problem(), assets)

    assert [e.asset_id for e in shortlist.ranked] == ["high", "low"]
    assert shortlist.ranked[0].bd_actionability >= shortlist.ranked[1].bd_actionability
    assert [x.asset_id for x in shortlist.excluded] == ["blocked"]
    assert "ta_outside_buyer_strategy" in shortlist.excluded[0].failed_gates


def test_does_not_solve_problem_is_a_gate() -> None:
    shortlist = build_se_shortlist(
        _problem(),
        [_asset("nope", solves_buyer_problem=False)],
    )
    assert not shortlist.ranked
    assert shortlist.excluded[0].failed_gates == ["does_not_solve_buyer_problem"]


def test_limit_truncates_ranked_only() -> None:
    assets = [_asset(f"a{i}", problem_solution_fit=0.1 * i) for i in range(1, 6)]
    shortlist = build_se_shortlist(_problem(), assets, limit=2)
    assert len(shortlist.ranked) == 2
    # Highest problem_solution_fit first.
    assert shortlist.ranked[0].asset_id == "a5"


def test_buyer_problem_id_defaults_to_buyer_id() -> None:
    shortlist = build_se_shortlist(_problem(), [_asset("x")])
    assert shortlist.buyer_problem_id == "vertex"
    override = build_se_shortlist(_problem(), [_asset("x")], buyer_problem_id="custom")
    assert override.buyer_problem_id == "custom"


def test_renderers_handle_empty_and_populated() -> None:
    problem = _problem()
    populated = build_se_shortlist(problem, [_asset("high", problem_solution_fit=0.9)])
    empty = build_se_shortlist(problem, [_asset("blocked", therapeutic_area="oncology")])

    # Table + memo must render without error for both shapes.
    assert "Ranked" in _render_table(populated)
    assert "Excluded" in _render_table(empty)
    assert "Search & Evaluation Shortlist" in _render_memo(populated, problem)
    assert "No assets passed the hard gates" in _render_memo(empty, problem)

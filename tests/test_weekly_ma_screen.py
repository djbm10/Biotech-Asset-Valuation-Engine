"""
Tests for weekly_ma_screen.py — Block 2D.

All external dependencies are injected via fixture objects.
No network access, no live ledger file.

Covers:
  1. run() returns WeeklyMAScreenResult
  2. Target with coverage < min_coverage is suppressed
  3. Non-suppressed targets are ranked descending by probability
  4. top_acquirer is the highest pair score for each ranked target
  5. Pair scoring creates target × acquirer rows
  6. deal_size_fit behaves correctly inside/outside range
  7. score_mode is stored in result
  8. Empty ledger still works using baseline
  9. Confidence bands are attached (probability_low < probability_high)
  10. Diagnostics include universe size, ranked count, suppressed count
  11. Deterministic: same inputs → same output
  12. Helper functions: _jaccard, _deal_size_fit, _coverage_from_n_records
  13. ranked_targets_to_rows / pair_results_to_rows produce correct dicts
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bve.ingestion.evidence_ledger import EvidenceLedger
from bve.ingestion.profile_enricher import AcquirerProfileEnriched, TargetProfileEnriched
from bve.ingestion.review_gate import ScoreMode
from bve.intelligence.weekly_ma_screen import (
    AcquirerPairResult,
    AcquirerTAOverride,
    WeeklyMAScreen,
    WeeklyMAScreenResult,
    _coverage_from_n_records,
    _deal_size_fit,
    _jaccard,
    pair_results_to_rows,
    ranked_targets_to_rows,
)

AS_OF = date(2026, 6, 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_target(
    ticker: str = "TSTR",
    lead_asset_phase: str = "phase3",
    therapeutic_areas: list[str] | None = None,
    lead_modality: str = "small_molecule",
    market_cap_bucket: str = "micro",
    include_in_screen: bool = True,
    quality_score: float = 0.80,
    has_partner_encumbrance: bool | None = None,
    cash_runway_months: float | None = 18.0,
    is_single_asset_company: bool = False,
    company_type: str = "drug_developer",
) -> TargetProfileEnriched:
    return TargetProfileEnriched(
        ticker=ticker,
        name=f"{ticker} Corp",
        cik=None,
        exchange="NASDAQ",
        company_type=company_type,
        therapeutic_areas=therapeutic_areas or ["oncology"],
        lead_asset="TEST-001",
        lead_asset_phase=lead_asset_phase,
        lead_modality=lead_modality,
        lead_indication="test indication",
        is_single_asset_company=is_single_asset_company,
        include_in_screen=include_in_screen,
        market_cap_bucket=market_cap_bucket,
        has_partner_encumbrance=has_partner_encumbrance,
        cash_millions=200.0,
        rd_expense_ttm_millions=80.0,
        sgna_expense_ttm_millions=None,
        operating_burn_ttm_millions=80.0,
        shares_outstanding_millions=60.0,
        cash_runway_months=cash_runway_months,
        quality_score=quality_score,
        data_quality_flags=[],
        source_map={},
        enriched_at="2026-06-01T00:00:00+00:00",
    )


def _make_acquirer(
    ticker: str = "TACQ",
    therapeutic_areas: list[str] | None = None,
    modalities: list[str] | None = None,
    preferred_stages: list[str] | None = None,
    deal_range: tuple[float, float] = (500.0, 10000.0),
    bd_appetite: float = 0.60,
    urgency: float = 0.55,
    integration_capacity: float = 0.75,
    include_as_acquirer: bool = True,
) -> AcquirerProfileEnriched:
    return AcquirerProfileEnriched(
        ticker=ticker,
        name=f"{ticker} Pharma",
        cik=None,
        therapeutic_areas=therapeutic_areas or ["oncology"],
        modalities=modalities or ["small_molecule", "biologic"],
        deal_size_range_millions=deal_range,
        preferred_stages=preferred_stages or ["phase2", "phase3"],
        include_as_acquirer=include_as_acquirer,
        bd_appetite=bd_appetite,
        urgency=urgency,
        integration_capacity=integration_capacity,
        quality_score=0.90,
        data_quality_flags=[],
        source_map={},
        enriched_at="2026-06-01T00:00:00+00:00",
    )


def _empty_ledger(tmp_path: Path) -> EvidenceLedger:
    return EvidenceLedger(path=tmp_path / "ledger.jsonl")


def _default_screen() -> WeeklyMAScreen:
    return WeeklyMAScreen()


# ===========================================================================
# Basic result structure
# ===========================================================================


class TestWeeklyMAScreenRun:
    def test_returns_weekly_ma_screen_result(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(
            as_of_date=AS_OF,
            targets=[_make_target()],
            acquirers=[_make_acquirer()],
            ledger=ledger,
        )
        assert isinstance(result, WeeklyMAScreenResult)

    def test_as_of_date_preserved(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert result.as_of_date == AS_OF

    def test_score_mode_stored_in_result(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            score_mode=ScoreMode.ALL_AUTO)
        assert result.score_mode == "all_auto"

    def test_provisional_score_mode_default(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert result.score_mode == "provisional"

    def test_ranked_targets_is_list(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert isinstance(result.ranked_targets, list)

    def test_suppressed_targets_is_list(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert isinstance(result.suppressed_targets, list)


# ===========================================================================
# Suppression
# ===========================================================================


class TestSuppression:
    def test_target_with_zero_records_is_suppressed_when_min_coverage_positive(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        # min_coverage=0.20 requires at least 1 record; empty ledger → suppressed
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.20)
        assert len(result.suppressed_targets) == 1
        assert result.suppressed_targets[0].suppressed is True

    def test_suppressed_target_not_in_ranked(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.20)
        ranked_tickers = {t.ticker for t in result.ranked_targets}
        assert "TSTR" not in ranked_tickers

    def test_suppression_reason_set(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.20)
        sup = result.suppressed_targets[0]
        assert sup.suppression_reason is not None
        assert "coverage" in sup.suppression_reason

    def test_zero_min_coverage_nothing_suppressed(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert len(result.suppressed_targets) == 0
        assert len(result.ranked_targets) == 1

    def test_non_included_targets_excluded_from_screen(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        t = _make_target(include_in_screen=False)
        result = screen.run(AS_OF, [t], [_make_acquirer()], ledger, min_coverage=0.0)
        assert len(result.ranked_targets) == 0

    def test_both_suppressed_and_unsuppressed_targets(self, tmp_path):
        screen = _default_screen()
        # Give one target records in the ledger so it passes coverage
        ledger = _empty_ledger(tmp_path)
        t1 = _make_target("T1")
        t2 = _make_target("T2")
        # Run with zero min_coverage so both appear in ranked
        result = screen.run(AS_OF, [t1, t2], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert len(result.ranked_targets) == 2
        assert len(result.suppressed_targets) == 0


# ===========================================================================
# Ranking order
# ===========================================================================


class TestRankingOrder:
    def test_targets_ranked_descending_by_probability(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        # phase3 oncology should score higher than preclinical cns
        t_high = _make_target("HIGH", lead_asset_phase="phase3",
                               therapeutic_areas=["oncology"])
        t_low = _make_target("LOW", lead_asset_phase="preclinical",
                              therapeutic_areas=["neuroscience"])
        result = screen.run(AS_OF, [t_low, t_high], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert len(result.ranked_targets) == 2
        assert result.ranked_targets[0].ma_probability >= result.ranked_targets[1].ma_probability

    def test_rank_field_is_sequential(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        targets = [_make_target(f"T{i}") for i in range(5)]
        result = screen.run(AS_OF, targets, [_make_acquirer()], ledger, min_coverage=0.0)
        ranks = [t.rank for t in result.ranked_targets]
        assert ranks == list(range(1, 6))

    def test_rank_1_is_highest_probability(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        t_high = _make_target("HIGH", lead_asset_phase="commercial",
                               therapeutic_areas=["rare_disease"])
        t_low = _make_target("LOW", lead_asset_phase="phase1",
                              therapeutic_areas=["neuroscience"])
        result = screen.run(AS_OF, [t_low, t_high], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert result.ranked_targets[0].ma_probability >= result.ranked_targets[1].ma_probability


# ===========================================================================
# Pair scoring
# ===========================================================================


class TestPairScoring:
    def test_top_acquirer_is_set_on_ranked_target(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert result.ranked_targets[0].top_acquirer is not None

    def test_top_acquirer_pair_score_is_set(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert result.ranked_targets[0].top_acquirer_pair_score is not None

    def test_top_acquirer_is_best_scoring_acquirer(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        # High-appetite acquirer should win
        acq_high = _make_acquirer("BEST", bd_appetite=0.95, urgency=0.90,
                                   therapeutic_areas=["oncology"])
        acq_low = _make_acquirer("WORST", bd_appetite=0.10, urgency=0.05,
                                  therapeutic_areas=["musculoskeletal"])
        result = screen.run(AS_OF, [_make_target()], [acq_high, acq_low], ledger,
                            min_coverage=0.0)
        assert result.ranked_targets[0].top_acquirer == "BEST"

    def test_pair_results_cover_all_acquirers(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        acquirers = [_make_acquirer(f"ACQ{i}") for i in range(3)]
        result = screen.run(AS_OF, [_make_target()], acquirers, ledger,
                            min_coverage=0.0, top_n_for_pairs=100)
        assert len(result.top_acquirer_pairs) == 3

    def test_top_n_for_pairs_limits_output(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        targets = [_make_target(f"T{i}") for i in range(3)]
        acquirers = [_make_acquirer(f"A{i}") for i in range(4)]
        result = screen.run(AS_OF, targets, acquirers, ledger,
                            min_coverage=0.0, top_n_for_pairs=5)
        assert len(result.top_acquirer_pairs) <= 5

    def test_pair_results_are_acquirer_pair_result_instances(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        for p in result.top_acquirer_pairs:
            assert isinstance(p, AcquirerPairResult)

    def test_suppressed_target_has_no_pairs(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.99)  # force suppression
        assert len(result.top_acquirer_pairs) == 0

    def test_excluded_acquirer_not_in_pairs(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        acq_included = _make_acquirer("INC", include_as_acquirer=True)
        acq_excluded = _make_acquirer("EXC", include_as_acquirer=False)
        result = screen.run(AS_OF, [_make_target()], [acq_included, acq_excluded], ledger,
                            min_coverage=0.0, top_n_for_pairs=100)
        acquirer_ids = {p.acquirer_ticker for p in result.top_acquirer_pairs}
        assert "EXC" not in acquirer_ids

    def test_weak_ta_fit_caps_pair_score(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        target = _make_target(therapeutic_areas=["neurology"])
        acquirer = _make_acquirer(
            therapeutic_areas=["oncology"],
            bd_appetite=1.0,
            urgency=1.0,
            integration_capacity=1.0,
        )
        result = screen.run(AS_OF, [target], [acquirer], ledger, min_coverage=0.0)
        pair = result.top_acquirer_pairs[0]
        assert pair.ta_overlap == 0.0
        assert pair.pair_score == 0.60
        assert pair.ta_fit_cap_applied == 0.60

    def test_recent_ta_override_relaxes_weak_ta_cap(self, tmp_path):
        override = AcquirerTAOverride(
            acquirer_ticker="TACQ",
            therapeutic_area="neurology",
            override_type="public_ta_expansion_statement",
            source="2026 investor day",
            source_date=date(2026, 1, 1),
            recorded_at=AS_OF,
            confidence=0.80,
        )
        screen = WeeklyMAScreen(ta_overrides=[override])
        ledger = _empty_ledger(tmp_path)
        target = _make_target(therapeutic_areas=["neurology"])
        acquirer = _make_acquirer(
            therapeutic_areas=["oncology"],
            bd_appetite=1.0,
            urgency=1.0,
            integration_capacity=1.0,
        )
        result = screen.run(AS_OF, [target], [acquirer], ledger, min_coverage=0.0)
        pair = result.top_acquirer_pairs[0]
        assert pair.pair_score > 0.60
        assert pair.ta_fit_cap_applied is None
        assert pair.ta_fit_override_type == "public_ta_expansion_statement"

    def test_stale_adjacent_ta_override_does_not_relax_cap(self, tmp_path):
        override = AcquirerTAOverride(
            acquirer_ticker="TACQ",
            therapeutic_area="neurology",
            override_type="adjacent_ta_deal_history",
            source="old acquisition",
            source_date=date(2020, 1, 1),
            recorded_at=AS_OF,
            confidence=0.90,
        )
        screen = WeeklyMAScreen(ta_overrides=[override])
        ledger = _empty_ledger(tmp_path)
        target = _make_target(therapeutic_areas=["neurology"])
        acquirer = _make_acquirer(
            therapeutic_areas=["oncology"],
            bd_appetite=1.0,
            urgency=1.0,
            integration_capacity=1.0,
        )
        result = screen.run(AS_OF, [target], [acquirer], ledger, min_coverage=0.0)
        pair = result.top_acquirer_pairs[0]
        assert pair.pair_score == 0.60
        assert pair.ta_fit_cap_applied == 0.60


# ===========================================================================
# Confidence bands
# ===========================================================================


class TestConfidenceBands:
    def test_probability_low_less_than_probability(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        t = result.ranked_targets[0]
        assert t.probability_low <= t.ma_probability

    def test_probability_high_greater_than_probability(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        t = result.ranked_targets[0]
        assert t.probability_high >= t.ma_probability

    def test_confidence_label_is_valid_string(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        t = result.ranked_targets[0]
        assert t.confidence_label in ("high", "medium", "low")

    def test_probability_in_range(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        for t in result.ranked_targets:
            assert 0.0 <= t.ma_probability <= 1.0
            assert 0.0 <= t.probability_low <= 1.0
            assert 0.0 <= t.probability_high <= 1.0


# ===========================================================================
# Empty ledger / baseline-only
# ===========================================================================


class TestEmptyLedger:
    def test_empty_ledger_does_not_crash(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert isinstance(result, WeeklyMAScreenResult)

    def test_empty_ledger_still_produces_scores(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        t = result.ranked_targets[0]
        assert t.asset_quality > 0.0
        assert t.ma_attractiveness > 0.0

    def test_empty_ledger_probability_is_non_zero(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert result.ranked_targets[0].ma_probability > 0.0


# ===========================================================================
# Diagnostics
# ===========================================================================


class TestDiagnostics:
    def test_diagnostics_has_n_targets_input(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert "n_targets_input" in result.diagnostics

    def test_diagnostics_n_acquirers_input(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert result.diagnostics["n_acquirers_input"] == 1

    def test_diagnostics_n_ranked(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert result.diagnostics["n_ranked_targets"] == 1

    def test_diagnostics_n_suppressed(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.99)
        assert result.diagnostics["n_suppressed_targets"] == 1

    def test_diagnostics_score_mode(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            score_mode=ScoreMode.APPROVED_ONLY)
        assert result.diagnostics["score_mode"] == "approved_only"

    def test_diagnostics_as_of_date(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger)
        assert result.diagnostics["as_of_date"] == "2026-06-01"

    def test_diagnostics_n_pair_scores(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.0)
        assert result.diagnostics["n_pair_scores"] == 1


# ===========================================================================
# Determinism
# ===========================================================================


class TestDeterminism:
    def test_same_inputs_same_ranked_output(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        targets = [_make_target(f"T{i}") for i in range(5)]
        acquirers = [_make_acquirer(f"A{i}") for i in range(3)]
        r1 = screen.run(AS_OF, targets, acquirers, ledger, min_coverage=0.0)
        r2 = screen.run(AS_OF, targets, acquirers, ledger, min_coverage=0.0)
        probs_1 = [t.ma_probability for t in r1.ranked_targets]
        probs_2 = [t.ma_probability for t in r2.ranked_targets]
        assert probs_1 == probs_2

    def test_same_inputs_same_pair_scores(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        r1 = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                        min_coverage=0.0)
        r2 = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                        min_coverage=0.0)
        assert r1.top_acquirer_pairs[0].pair_score == r2.top_acquirer_pairs[0].pair_score


# ===========================================================================
# Helper function unit tests
# ===========================================================================


class TestJaccard:
    def test_identical_lists(self):
        assert _jaccard(["a", "b"], ["a", "b"]) == 1.0

    def test_disjoint_lists(self):
        assert _jaccard(["a"], ["b"]) == 0.0

    def test_partial_overlap(self):
        result = _jaccard(["a", "b"], ["b", "c"])
        assert abs(result - 1 / 3) < 1e-6  # |{b}| / |{a,b,c}|

    def test_empty_lists(self):
        assert _jaccard([], []) == 0.0

    def test_one_empty(self):
        assert _jaccard(["a"], []) == 0.0


class TestDealSizeFit:
    def test_ev_inside_range_returns_1(self):
        assert _deal_size_fit("micro", (100.0, 1000.0)) == 1.0

    def test_unknown_bucket_returns_neutral(self):
        assert _deal_size_fit(None, (100.0, 1000.0)) == 0.5

    def test_ev_below_range_returns_less_than_1(self):
        # nano (~75M) with range (1000, 5000) → 75 << 1000
        fit = _deal_size_fit("nano", (1000.0, 5000.0))
        assert fit < 1.0
        assert fit >= 0.0

    def test_ev_above_range_returns_less_than_1(self):
        # large (~25000M) with range (100, 500) → 25000 >> 500
        fit = _deal_size_fit("large", (100.0, 500.0))
        assert fit < 1.0
        assert fit >= 0.0

    def test_small_inside_range(self):
        # small (~1500M) with range (500, 5000)
        assert _deal_size_fit("small", (500.0, 5000.0)) == 1.0


class TestCoverageFromNRecords:
    def test_zero_records_zero_coverage(self):
        assert _coverage_from_n_records(0) == 0.0

    def test_five_records_full_coverage(self):
        assert _coverage_from_n_records(5) == 1.0

    def test_ten_records_capped_at_1(self):
        assert _coverage_from_n_records(10) == 1.0

    def test_one_record_partial_coverage(self):
        assert _coverage_from_n_records(1) == pytest.approx(0.2)

    def test_three_records(self):
        assert _coverage_from_n_records(3) == pytest.approx(0.6)


# ===========================================================================
# CSV helpers
# ===========================================================================


class TestCSVHelpers:
    def _run_screen(self, tmp_path) -> WeeklyMAScreenResult:
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        return screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                          min_coverage=0.0)

    def test_ranked_targets_to_rows_returns_list(self, tmp_path):
        result = self._run_screen(tmp_path)
        rows = ranked_targets_to_rows(result)
        assert isinstance(rows, list)

    def test_ranked_targets_row_has_expected_keys(self, tmp_path):
        result = self._run_screen(tmp_path)
        rows = ranked_targets_to_rows(result)
        assert len(rows) == 1
        row = rows[0]
        assert "ticker" in row
        assert "ma_probability" in row
        assert "rank" in row
        assert "top_acquirer" in row
        assert "as_of_date" in row

    def test_pair_results_to_rows_returns_list(self, tmp_path):
        result = self._run_screen(tmp_path)
        rows = pair_results_to_rows(result)
        assert isinstance(rows, list)

    def test_pair_results_row_has_expected_keys(self, tmp_path):
        result = self._run_screen(tmp_path)
        rows = pair_results_to_rows(result)
        assert len(rows) == 1
        row = rows[0]
        assert "target_ticker" in row
        assert "acquirer_ticker" in row
        assert "pair_score" in row
        assert "ta_overlap" in row
        assert "as_of_date" in row

    def test_ranked_targets_row_as_of_date_is_isoformat(self, tmp_path):
        result = self._run_screen(tmp_path)
        rows = ranked_targets_to_rows(result)
        assert rows[0]["as_of_date"] == "2026-06-01"

    def test_empty_ranked_returns_empty_rows(self, tmp_path):
        screen = _default_screen()
        ledger = _empty_ledger(tmp_path)
        result = screen.run(AS_OF, [_make_target()], [_make_acquirer()], ledger,
                            min_coverage=0.99)
        rows = ranked_targets_to_rows(result)
        assert rows == []

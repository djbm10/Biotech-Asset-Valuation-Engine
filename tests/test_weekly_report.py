"""
Tests for weekly_report.py — Block 2E.

Uses fixture WeeklyMAScreenResult objects. No network, no scoring.

Covers:
  1. write_outputs creates all six expected files
  2. ranked_targets.csv has required columns
  3. top_acquirer_pairs.csv sorted by pair_score descending
  4. suppressed_targets.csv includes suppressed names
  5. score_changes.csv has headers when prev_result is None
  6. score_changes computes rank/probability changes correctly
  7. audit_report.md contains all required sections
  8. validation_snapshot.json contains diagnostics and schema_version
  9. list fields serialize as semicolon-separated strings
  10. output is deterministic for same result
  11. generate_markdown returns a string with all section headers
  12. edge cases: empty ranked, no acquirer pairs, no suppressed
"""
from __future__ import annotations

import csv
import json
from datetime import date
from io import StringIO
from pathlib import Path

import pytest

from bve.intelligence.weekly_ma_screen import (
    AcquirerPairResult,
    TargetScreenResult,
    WeeklyMAScreenResult,
)
from bve.reporting.weekly_report import (
    REPORT_VERSION,
    WeeklyReportGenerator,
    _join,
    _format_probability,
    _result_by_ticker,
    compute_score_changes,
)

AS_OF = date(2026, 6, 1)
PREV_AS_OF = date(2026, 5, 25)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_target_result(
    ticker: str = "TSTR",
    rank: int = 1,
    ma_probability: float = 0.35,
    prob_low: float = 0.20,
    prob_high: float = 0.50,
    confidence_label: str = "medium",
    top_acquirer: str | None = "PFE",
    top_acquirer_pair_score: float | None = 0.62,
    main_drivers: list[str] | None = None,
    key_risks: list[str] | None = None,
    suppressed: bool = False,
    suppression_reason: str | None = None,
    evidence_coverage_overall: float = 0.80,
    profile_quality_score: float = 0.75,
) -> TargetScreenResult:
    return TargetScreenResult(
        rank=rank,
        ticker=ticker,
        name=f"{ticker} Bio",
        ma_probability=ma_probability,
        probability_low=prob_low,
        probability_high=prob_high,
        confidence_label=confidence_label,
        asset_quality=0.60,
        seller_willingness=0.45,
        financing_risk=0.10,
        catalyst_timing=0.35,
        ma_attractiveness=0.55,
        evidence_coverage_overall=evidence_coverage_overall,
        profile_quality_score=profile_quality_score,
        top_acquirer=top_acquirer,
        top_acquirer_pair_score=top_acquirer_pair_score,
        main_drivers=main_drivers or ["phase3 asset", "rare disease TA"],
        key_risks=key_risks or ["low evidence coverage (1 records)"],
        suppressed=suppressed,
        suppression_reason=suppression_reason,
    )


def _make_suppressed(ticker: str = "SUPP") -> TargetScreenResult:
    return _make_target_result(
        ticker=ticker,
        rank=0,
        suppressed=True,
        suppression_reason="coverage 0.00 < 0.20",
        evidence_coverage_overall=0.0,
    )


def _make_pair(
    target: str = "TSTR",
    acquirer: str = "PFE",
    pair_score: float = 0.65,
) -> AcquirerPairResult:
    return AcquirerPairResult(
        target_ticker=target,
        acquirer_ticker=acquirer,
        pair_score=pair_score,
        ta_overlap=0.50,
        modality_fit=1.0,
        stage_fit=1.0,
        deal_size_fit=0.80,
        pipeline_gap_fill=0.40,
        integration_complexity=0.20,
    )


def _make_result(
    ranked: list[TargetScreenResult] | None = None,
    suppressed: list[TargetScreenResult] | None = None,
    pairs: list[AcquirerPairResult] | None = None,
    as_of: date = AS_OF,
    score_mode: str = "provisional",
) -> WeeklyMAScreenResult:
    ranked = [_make_target_result()] if ranked is None else ranked
    suppressed = [] if suppressed is None else suppressed
    pairs = [_make_pair()] if pairs is None else pairs
    return WeeklyMAScreenResult(
        as_of_date=as_of,
        score_mode=score_mode,
        ranked_targets=ranked,
        suppressed_targets=suppressed,
        top_acquirer_pairs=pairs,
        diagnostics={
            "n_targets_input": len(ranked) + len(suppressed),
            "n_acquirers_input": 23,
            "n_ranked_targets": len(ranked),
            "n_suppressed_targets": len(suppressed),
            "n_pair_scores": len(pairs),
            "score_mode": score_mode,
            "as_of_date": as_of.isoformat(),
        },
    )


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    """Return (fieldnames, rows) from a CSV file."""
    with path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    return list(fieldnames), rows


# ===========================================================================
# write_outputs — file creation
# ===========================================================================


class TestWriteOutputsFileCreation:
    def test_all_six_files_created(self, tmp_path):
        gen = WeeklyReportGenerator()
        result = _make_result()
        paths = gen.write_outputs(result, tmp_path / "out")
        names = {p.name for p in paths}
        assert "ranked_targets.csv" in names
        assert "top_acquirer_pairs.csv" in names
        assert "suppressed_targets.csv" in names
        assert "score_changes.csv" in names
        assert "audit_report.md" in names
        assert "validation_snapshot.json" in names

    def test_returns_list_of_six_paths(self, tmp_path):
        gen = WeeklyReportGenerator()
        paths = gen.write_outputs(_make_result(), tmp_path / "out")
        assert len(paths) == 6

    def test_all_paths_exist_on_disk(self, tmp_path):
        gen = WeeklyReportGenerator()
        paths = gen.write_outputs(_make_result(), tmp_path / "out")
        for p in paths:
            assert p.exists(), f"Missing: {p.name}"

    def test_output_dir_created_if_missing(self, tmp_path):
        gen = WeeklyReportGenerator()
        deep = tmp_path / "a" / "b" / "c"
        gen.write_outputs(_make_result(), deep)
        assert deep.exists()


# ===========================================================================
# ranked_targets.csv
# ===========================================================================


class TestRankedTargetsCSV:
    def test_has_required_columns(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(), tmp_path)
        fields, _ = _read_csv(tmp_path / "ranked_targets.csv")
        for col in ["rank", "ticker", "name", "ma_score", "score_low",
                    "score_high", "confidence_label", "asset_quality",
                    "seller_willingness", "ma_attractiveness", "catalyst_timing",
                    "evidence_coverage_overall", "profile_quality_score",
                    "top_acquirer", "top_acquirer_pair_score",
                    "main_drivers", "key_risks"]:
            assert col in fields, f"Missing column: {col}"

    def test_has_one_row_per_ranked_target(self, tmp_path):
        gen = WeeklyReportGenerator()
        targets = [_make_target_result(f"T{i}", rank=i+1) for i in range(5)]
        gen.write_outputs(_make_result(ranked=targets), tmp_path)
        _, rows = _read_csv(tmp_path / "ranked_targets.csv")
        assert len(rows) == 5

    def test_list_fields_semicolon_separated(self, tmp_path):
        gen = WeeklyReportGenerator()
        t = _make_target_result(main_drivers=["phase3 asset", "rare disease TA"])
        gen.write_outputs(_make_result(ranked=[t]), tmp_path)
        _, rows = _read_csv(tmp_path / "ranked_targets.csv")
        assert "phase3 asset" in rows[0]["main_drivers"]
        assert "rare disease TA" in rows[0]["main_drivers"]
        assert ";" in rows[0]["main_drivers"]

    def test_empty_ranked_writes_headers_only(self, tmp_path):
        gen = WeeklyReportGenerator()
        # Provide a suppressed target to avoid an all-empty result
        gen.write_outputs(_make_result(ranked=[], suppressed=[_make_suppressed()]), tmp_path)
        fields, rows = _read_csv(tmp_path / "ranked_targets.csv")
        assert len(rows) == 0
        assert "ticker" in fields


# ===========================================================================
# top_acquirer_pairs.csv
# ===========================================================================


class TestTopAcquirerPairsCSV:
    def test_has_required_columns(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(), tmp_path)
        fields, _ = _read_csv(tmp_path / "top_acquirer_pairs.csv")
        for col in ["target_ticker", "acquirer_ticker", "pair_score",
                    "ta_overlap", "modality_fit", "stage_fit",
                    "deal_size_fit", "pipeline_gap_fill", "integration_complexity"]:
            assert col in fields

    def test_sorted_by_pair_score_descending(self, tmp_path):
        gen = WeeklyReportGenerator()
        pairs = [
            _make_pair("T1", "A1", 0.30),
            _make_pair("T2", "A2", 0.80),
            _make_pair("T3", "A3", 0.55),
        ]
        gen.write_outputs(_make_result(pairs=pairs), tmp_path)
        _, rows = _read_csv(tmp_path / "top_acquirer_pairs.csv")
        scores = [float(r["pair_score"]) for r in rows]
        assert scores == sorted(scores, reverse=True)

    def test_top_100_limit(self, tmp_path):
        gen = WeeklyReportGenerator()
        pairs = [_make_pair(f"T{i}", f"A{i}", round(0.5 + i * 0.001, 4)) for i in range(150)]
        gen.write_outputs(_make_result(pairs=pairs), tmp_path)
        _, rows = _read_csv(tmp_path / "top_acquirer_pairs.csv")
        assert len(rows) <= 100

    def test_empty_pairs_writes_headers_only(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(pairs=[]), tmp_path)
        fields, rows = _read_csv(tmp_path / "top_acquirer_pairs.csv")
        assert len(rows) == 0
        assert "target_ticker" in fields


# ===========================================================================
# suppressed_targets.csv
# ===========================================================================


class TestSuppressedTargetsCSV:
    def test_has_required_columns(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(suppressed=[_make_suppressed()]), tmp_path)
        fields, _ = _read_csv(tmp_path / "suppressed_targets.csv")
        for col in ["ticker", "name", "suppression_reason",
                    "evidence_coverage_overall", "profile_quality_score",
                    "asset_quality", "seller_willingness", "ma_attractiveness", "catalyst_timing"]:
            assert col in fields

    def test_suppressed_ticker_in_rows(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(suppressed=[_make_suppressed("SUPP")]), tmp_path)
        _, rows = _read_csv(tmp_path / "suppressed_targets.csv")
        tickers = {r["ticker"] for r in rows}
        assert "SUPP" in tickers

    def test_suppression_reason_written(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(suppressed=[_make_suppressed()]), tmp_path)
        _, rows = _read_csv(tmp_path / "suppressed_targets.csv")
        assert rows[0]["suppression_reason"] != ""

    def test_empty_suppressed_writes_headers_only(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(suppressed=[]), tmp_path)
        fields, rows = _read_csv(tmp_path / "suppressed_targets.csv")
        assert len(rows) == 0
        assert "ticker" in fields


# ===========================================================================
# score_changes.csv
# ===========================================================================


class TestScoreChangesCSV:
    def test_has_headers_when_no_prev_result(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(), tmp_path, prev_result=None)
        fields, rows = _read_csv(tmp_path / "score_changes.csv")
        assert "ticker" in fields
        assert "rank_change" in fields
        assert len(rows) == 0  # no data, headers only

    def test_rank_change_positive_when_moved_up(self):
        prev_t = _make_target_result("TSTR", rank=10, ma_probability=0.30)
        curr_t = _make_target_result("TSTR", rank=3, ma_probability=0.42)
        prev = _make_result(ranked=[prev_t])
        curr = _make_result(ranked=[curr_t])
        changes = compute_score_changes(curr, prev)
        row = next(c for c in changes if c["ticker"] == "TSTR")
        assert row["rank_change"] == 7  # 10 - 3

    def test_rank_change_negative_when_moved_down(self):
        prev_t = _make_target_result("TSTR", rank=2, ma_probability=0.50)
        curr_t = _make_target_result("TSTR", rank=8, ma_probability=0.35)
        prev = _make_result(ranked=[prev_t])
        curr = _make_result(ranked=[curr_t])
        changes = compute_score_changes(curr, prev)
        row = next(c for c in changes if c["ticker"] == "TSTR")
        assert row["rank_change"] == -6

    def test_probability_change_computed(self):
        prev_t = _make_target_result("TSTR", rank=5, ma_probability=0.30)
        curr_t = _make_target_result("TSTR", rank=5, ma_probability=0.42)
        prev = _make_result(ranked=[prev_t])
        curr = _make_result(ranked=[curr_t])
        changes = compute_score_changes(curr, prev)
        row = next(c for c in changes if c["ticker"] == "TSTR")
        assert abs(row["ma_score_change"] - 0.12) < 0.001

    def test_score_changes_written_to_csv_when_prev_exists(self, tmp_path):
        prev_t = _make_target_result("TSTR", rank=10)
        curr_t = _make_target_result("TSTR", rank=3)
        prev = _make_result(ranked=[prev_t])
        curr = _make_result(ranked=[curr_t])
        gen = WeeklyReportGenerator()
        gen.write_outputs(curr, tmp_path, prev_result=prev)
        fields, rows = _read_csv(tmp_path / "score_changes.csv")
        assert len(rows) >= 1

    def test_empty_when_no_prev(self):
        result = _make_result()
        changes = compute_score_changes(result, None)
        assert changes == []

    def test_new_ticker_in_current_not_in_prev(self):
        prev_t = _make_target_result("OLD", rank=1)
        curr_t = _make_target_result("NEW", rank=1)
        prev = _make_result(ranked=[prev_t])
        curr = _make_result(ranked=[curr_t])
        changes = compute_score_changes(curr, prev)
        tickers = {c["ticker"] for c in changes}
        assert "NEW" in tickers
        assert "OLD" in tickers


# ===========================================================================
# audit_report.md
# ===========================================================================


class TestAuditReportMarkdown:
    def _gen_md(self, result=None, prev=None) -> str:
        gen = WeeklyReportGenerator()
        return gen.generate_markdown(result or _make_result(), prev)

    def test_returns_string(self):
        assert isinstance(self._gen_md(), str)

    def test_contains_date_header(self):
        md = self._gen_md()
        assert "2026-06-01" in md

    def test_contains_run_summary_section(self):
        md = self._gen_md()
        assert "## Run Summary" in md

    def test_contains_top_targets_section(self):
        md = self._gen_md()
        assert "## Top 25 Targets" in md

    def test_contains_top_pairs_section(self):
        md = self._gen_md()
        assert "## Top 20 Acquirer Pairs" in md

    def test_contains_score_changes_section(self):
        md = self._gen_md()
        assert "## Biggest Score Changes" in md

    def test_contains_suppressed_section(self):
        md = self._gen_md()
        assert "## Suppressed Targets" in md

    def test_contains_pending_review_section(self):
        md = self._gen_md()
        assert "## Pending Review" in md

    def test_contains_model_diagnostics_section(self):
        md = self._gen_md()
        assert "## Model Diagnostics" in md

    def test_contains_notes_section(self):
        md = self._gen_md()
        assert "## Notes" in md

    def test_contains_research_output_disclaimer(self):
        md = self._gen_md()
        assert "research output" in md.lower()

    def test_ticker_appears_in_top_targets_table(self):
        t = _make_target_result("RVMD", rank=1, ma_probability=0.45)
        md = self._gen_md(_make_result(ranked=[t]))
        assert "RVMD" in md

    def test_no_prev_shows_no_comparison_message(self):
        md = self._gen_md(prev=None)
        assert "No previous result" in md or "no previous result" in md.lower() or "previous" in md.lower()

    def test_suppressed_ticker_in_suppressed_section(self):
        result = _make_result(suppressed=[_make_suppressed("SUPP_X")])
        md = self._gen_md(result)
        assert "SUPP_X" in md

    def test_written_to_disk_is_valid_utf8(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(), tmp_path)
        content = (tmp_path / "audit_report.md").read_text(encoding="utf-8")
        assert len(content) > 0


# ===========================================================================
# validation_snapshot.json
# ===========================================================================


class TestValidationSnapshot:
    def _load_snapshot(self, tmp_path) -> dict:
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(), tmp_path)
        return json.loads((tmp_path / "validation_snapshot.json").read_text())

    def test_as_of_date_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert snap["as_of_date"] == "2026-06-01"

    def test_score_mode_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert snap["score_mode"] == "provisional"

    def test_n_ranked_targets_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "n_ranked_targets" in snap
        assert snap["n_ranked_targets"] == 1

    def test_n_suppressed_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "n_suppressed_targets" in snap

    def test_top_target_is_ticker(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert snap["top_target"] == "TSTR"

    def test_top_ma_score_is_float(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert isinstance(snap["top_ma_score"], float)

    def test_calibration_status_is_uncalibrated(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert snap["calibration_status"] == "uncalibrated"
        assert "output_interpretation" in snap

    def test_schema_version_is_report_version(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert snap["schema_version"] == REPORT_VERSION

    def test_generated_at_is_iso_timestamp(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "T" in snap["generated_at"]
        assert "generated_at" in snap

    def test_classifier_version_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "classifier_version" in snap

    def test_baseline_model_version_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "baseline_model_version" in snap

    def test_pair_scorer_version_present(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "pair_scorer_version" in snap

    def test_diagnostics_embedded(self, tmp_path):
        snap = self._load_snapshot(tmp_path)
        assert "diagnostics" in snap
        assert isinstance(snap["diagnostics"], dict)

    def test_valid_json(self, tmp_path):
        gen = WeeklyReportGenerator()
        gen.write_outputs(_make_result(), tmp_path)
        content = (tmp_path / "validation_snapshot.json").read_text()
        parsed = json.loads(content)
        assert isinstance(parsed, dict)


# ===========================================================================
# Determinism
# ===========================================================================


class TestDeterminism:
    def test_same_result_produces_same_csv(self, tmp_path):
        result = _make_result()
        gen = WeeklyReportGenerator()
        p1 = tmp_path / "run1"
        p2 = tmp_path / "run2"
        gen.write_outputs(result, p1)
        gen.write_outputs(result, p2)
        c1 = (p1 / "ranked_targets.csv").read_text()
        c2 = (p2 / "ranked_targets.csv").read_text()
        assert c1 == c2

    def test_same_result_produces_same_pairs_csv(self, tmp_path):
        result = _make_result()
        gen = WeeklyReportGenerator()
        p1 = tmp_path / "run1"
        p2 = tmp_path / "run2"
        gen.write_outputs(result, p1)
        gen.write_outputs(result, p2)
        assert (p1 / "top_acquirer_pairs.csv").read_text() == (p2 / "top_acquirer_pairs.csv").read_text()


# ===========================================================================
# Helper functions
# ===========================================================================


class TestHelpers:
    def test_format_probability(self):
        assert _format_probability(0.35) == "35.0%"
        assert _format_probability(0.0) == "0.0%"
        assert _format_probability(1.0) == "100.0%"

    def test_join_semicolons(self):
        assert _join(["a", "b", "c"]) == "a; b; c"

    def test_join_empty(self):
        assert _join([]) == ""

    def test_join_single(self):
        assert _join(["x"]) == "x"

    def test_result_by_ticker_includes_ranked(self):
        t = _make_target_result("AAAA")
        result = _make_result(ranked=[t])
        by_ticker = _result_by_ticker(result)
        assert "AAAA" in by_ticker

    def test_result_by_ticker_includes_suppressed(self):
        s = _make_suppressed("SSSS")
        result = _make_result(suppressed=[s])
        by_ticker = _result_by_ticker(result)
        assert "SSSS" in by_ticker

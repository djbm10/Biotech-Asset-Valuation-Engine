"""Block 17 — M&A Base Rate / Negative Set Expansion.

Tests for:
  - NegativeType enum completeness
  - TypedNegativeCase dataset coverage and quality
  - MA_EXPANDED_DATASET composition
  - run_ma_backtest() expanded-dataset output
  - wilson_ci() helper
  - compute_base_rate_report() correctness
  - render_markdown() format
  - CLI output (--json, --dataset)

Fixes B5 / V5: base rate computed from typed, auditable dataset;
bankruptcies separated from healthy independents.
"""
from __future__ import annotations

import json
from io import StringIO

import pytest


# ---------------------------------------------------------------------------
# TestNegativeType
# ---------------------------------------------------------------------------

class TestNegativeType:
    def test_five_values_exist(self):
        from bve.intelligence.ma_negative_set import NegativeType
        assert len(NegativeType) == 5

    def test_value_strings(self):
        from bve.intelligence.ma_negative_set import NegativeType
        assert NegativeType.NORMAL_INDEPENDENT.value == "normal_independent"
        assert NegativeType.STRATEGIC_REVIEW_NO_DEAL.value == "strategic_review_no_deal"
        assert NegativeType.DISTRESS_NO_DEAL.value == "distress_no_deal"
        assert NegativeType.FAILED_PROCESS.value == "failed_process"
        assert NegativeType.BANKRUPTCY_OR_LIQUIDATION.value == "bankruptcy_or_liquidation"

    def test_no_duplicate_values(self):
        from bve.intelligence.ma_negative_set import NegativeType
        vals = [nt.value for nt in NegativeType]
        assert len(vals) == len(set(vals))


# ---------------------------------------------------------------------------
# TestTypedNegativeCatalog
# ---------------------------------------------------------------------------

class TestTypedNegativeCatalog:
    def test_minimum_100_records(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET
        assert len(TYPED_NEGATIVE_DATASET) >= 100

    def test_all_five_types_present(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET, NegativeType
        present = {c.negative_type for c in TYPED_NEGATIVE_DATASET}
        assert present == set(NegativeType)

    def test_minimum_10_per_type(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET, NegativeType
        for nt in NegativeType:
            count = sum(1 for c in TYPED_NEGATIVE_DATASET if c.negative_type == nt)
            assert count >= 10, f"{nt.value} has only {count} cases (min 10)"

    def test_no_blank_company_names(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET
        for c in TYPED_NEGATIVE_DATASET:
            assert c.company.strip(), f"Blank company name in {c}"

    def test_cap_bucket_values(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET
        valid = {"small", "mid", "large"}
        for c in TYPED_NEGATIVE_DATASET:
            assert c.cap_bucket in valid, f"{c.company} has cap_bucket={c.cap_bucket!r}"

    def test_phase_score_values(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET
        valid = {0.5, 1.0, 2.0, 3.0}
        for c in TYPED_NEGATIVE_DATASET:
            assert c.phase_score in valid, f"{c.company} has phase_score={c.phase_score}"

    def test_therapeutic_area_not_blank(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET
        for c in TYPED_NEGATIVE_DATASET:
            assert c.therapeutic_area.strip(), f"Blank TA in {c.company}"

    def test_bankruptcy_cases_have_calibration_exclude_true(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET, NegativeType
        for c in TYPED_NEGATIVE_DATASET:
            if c.negative_type == NegativeType.BANKRUPTCY_OR_LIQUIDATION:
                assert c.calibration_exclude is True, (
                    f"{c.company} is bankruptcy but calibration_exclude=False"
                )

    def test_non_bankruptcy_cases_have_calibration_exclude_false(self):
        from bve.intelligence.ma_negative_set import TYPED_NEGATIVE_DATASET, NegativeType
        for c in TYPED_NEGATIVE_DATASET:
            if c.negative_type != NegativeType.BANKRUPTCY_OR_LIQUIDATION:
                assert c.calibration_exclude is False, (
                    f"{c.company} ({c.negative_type.value}) has calibration_exclude=True"
                )

    def test_get_typed_negatives_returns_all(self):
        from bve.intelligence.ma_negative_set import (
            TYPED_NEGATIVE_DATASET, get_typed_negatives,
        )
        result = get_typed_negatives()
        assert len(result) == len(TYPED_NEGATIVE_DATASET)

    def test_typed_negatives_by_type(self):
        from bve.intelligence.ma_negative_set import (
            NegativeType, typed_negatives_by_type,
        )
        bn = typed_negatives_by_type(NegativeType.BANKRUPTCY_OR_LIQUIDATION)
        for c in bn:
            assert c.negative_type == NegativeType.BANKRUPTCY_OR_LIQUIDATION

    def test_calibration_negatives_excludes_bankruptcy(self):
        from bve.intelligence.ma_negative_set import calibration_negatives, NegativeType
        result = calibration_negatives()
        for c in result:
            assert c.negative_type != NegativeType.BANKRUPTCY_OR_LIQUIDATION

    def test_negative_type_counts_keys(self):
        from bve.intelligence.ma_negative_set import negative_type_counts, NegativeType
        counts = negative_type_counts()
        for nt in NegativeType:
            assert nt.value in counts
            assert counts[nt.value] > 0


# ---------------------------------------------------------------------------
# TestMABacktestExpanded
# ---------------------------------------------------------------------------

class TestMABacktestExpanded:
    def test_expanded_dataset_size_gte_120(self):
        from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
        assert len(MA_EXPANDED_DATASET) >= 120

    def test_positives_still_20(self):
        from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
        positives = [r for r in MA_EXPANDED_DATASET if r.label == 1]
        assert len(positives) == 20

    def test_all_five_negative_types_in_expanded(self):
        from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
        from bve.intelligence.ma_negative_set import NegativeType
        neg_types = {r.negative_type for r in MA_EXPANDED_DATASET if r.label == 0 and r.negative_type}
        for nt in NegativeType:
            assert nt.value in neg_types, f"{nt.value} missing from expanded dataset"

    def test_n_by_negative_type_sums_to_n_negative(self):
        from bve.analysis.ma_backtest import run_ma_backtest, MA_EXPANDED_DATASET
        result = run_ma_backtest(MA_EXPANDED_DATASET)
        total_typed = sum(result.n_by_negative_type.values())
        assert total_typed == result.n_negative

    def test_bankruptcy_tagged_correctly(self):
        from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
        bk = [r for r in MA_EXPANDED_DATASET if r.negative_type == "bankruptcy_or_liquidation"]
        for r in bk:
            assert r.calibration_exclude is True

    def test_core_dataset_unchanged(self):
        from bve.analysis.ma_backtest import MA_BACKTEST_DATASET
        assert len(MA_BACKTEST_DATASET) == 40
        positives = [r for r in MA_BACKTEST_DATASET if r.label == 1]
        assert len(positives) == 20

    def test_run_ma_backtest_expanded_base_rate_realistic(self):
        from bve.analysis.ma_backtest import run_ma_backtest, MA_EXPANDED_DATASET
        result = run_ma_backtest(MA_EXPANDED_DATASET)
        # Biotech M&A base rate is typically 10-30% for a tracked universe
        assert 0.05 < result.baseline_rate < 0.40

    def test_calibration_base_rate_higher_than_baseline(self):
        """Excluding bankruptcies from denom raises calibration base rate."""
        from bve.analysis.ma_backtest import run_ma_backtest, MA_EXPANDED_DATASET
        result = run_ma_backtest(MA_EXPANDED_DATASET)
        assert result.calibration_base_rate >= result.baseline_rate

    def test_run_ma_backtest_core_still_works(self):
        from bve.analysis.ma_backtest import run_ma_backtest, MA_BACKTEST_DATASET
        result = run_ma_backtest(MA_BACKTEST_DATASET)
        assert result.n_positive == 20
        assert result.n_negative == 20
        assert 0.0 < result.auc <= 1.0

    def test_expanded_auc_reasonable(self):
        from bve.analysis.ma_backtest import run_ma_backtest, MA_EXPANDED_DATASET
        result = run_ma_backtest(MA_EXPANDED_DATASET)
        # AUC should be above 0.5 (better than random)
        assert result.auc > 0.5


# ---------------------------------------------------------------------------
# TestWilsonCI
# ---------------------------------------------------------------------------

class TestWilsonCI:
    def test_known_values(self):
        """N=100, k=10 → base_rate=0.10; CI should be roughly [0.06, 0.15]."""
        from bve.analysis.ma_base_rate_report import wilson_ci
        lo, hi = wilson_ci(100, 10)
        assert lo < 0.10 < hi
        assert 0.0 <= lo
        assert hi <= 1.0

    def test_zero_n_returns_full_interval(self):
        from bve.analysis.ma_base_rate_report import wilson_ci
        lo, hi = wilson_ci(0, 0)
        assert lo == 0.0
        assert hi == 1.0

    def test_zero_positives_ci_lower_is_zero(self):
        from bve.analysis.ma_base_rate_report import wilson_ci
        lo, hi = wilson_ci(50, 0)
        assert lo == pytest.approx(0.0, abs=1e-6)
        assert hi > 0.0

    def test_all_positive_ci_upper_is_one(self):
        from bve.analysis.ma_base_rate_report import wilson_ci
        lo, hi = wilson_ci(50, 50)
        assert lo < 1.0
        assert hi == pytest.approx(1.0, abs=1e-6)

    def test_larger_n_narrower_ci(self):
        from bve.analysis.ma_base_rate_report import wilson_ci
        lo_small, hi_small = wilson_ci(20, 4)   # 20%, N=20
        lo_large, hi_large = wilson_ci(200, 40)  # 20%, N=200
        assert (hi_small - lo_small) > (hi_large - lo_large)

    def test_bounds_ordered(self):
        from bve.analysis.ma_base_rate_report import wilson_ci
        for n, k in [(10, 3), (50, 25), (100, 70), (30, 0)]:
            lo, hi = wilson_ci(n, k)
            assert lo <= hi


# ---------------------------------------------------------------------------
# TestBaseRateReport
# ---------------------------------------------------------------------------

class TestBaseRateReport:
    @pytest.fixture
    def report(self):
        from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
        from bve.analysis.ma_base_rate_report import compute_base_rate_report
        return compute_base_rate_report(MA_EXPANDED_DATASET)

    def test_n_positives(self, report):
        assert report.n_positives == 20

    def test_n_negatives_total_gte_90(self, report):
        assert report.n_negatives_total >= 90

    def test_overall_base_rate_excludes_bankruptcy(self, report):
        # base_rate should be higher than base_rate_strict (bk excluded)
        assert report.overall.base_rate >= report.overall.base_rate_strict

    def test_overall_base_rate_realistic(self, report):
        assert 0.10 < report.overall.base_rate < 0.40

    def test_base_rate_strict_includes_all(self, report):
        # strict = n_pos / (n_pos + n_neg_all)
        n_total = report.n_positives + report.n_negatives_total
        expected = report.n_positives / n_total
        assert report.overall.base_rate_strict == pytest.approx(expected, abs=1e-4)

    def test_ci_bounds_straddle_base_rate(self, report):
        seg = report.overall
        assert seg.ci_lower <= seg.base_rate <= seg.ci_upper

    def test_by_therapeutic_area_keys(self, report):
        assert "oncology_rare" in report.by_therapeutic_area
        assert "other" in report.by_therapeutic_area

    def test_by_stage_keys(self, report):
        assert "phase_1" in report.by_stage
        assert "phase_2_3" in report.by_stage
        assert "approved" in report.by_stage

    def test_by_cap_bucket_keys(self, report):
        assert "small" in report.by_cap_bucket
        assert "mid" in report.by_cap_bucket
        assert "large" in report.by_cap_bucket

    def test_n_by_negative_type_has_all_five(self, report):
        from bve.intelligence.ma_negative_set import NegativeType
        for nt in NegativeType:
            assert nt.value in report.n_by_negative_type

    def test_bankruptcy_exclusion_note_non_empty(self, report):
        assert len(report.bankruptcy_exclusion_note) > 50

    def test_bankruptcy_exclusion_note_mentions_bankruptcy(self, report):
        assert "bankruptcy" in report.bankruptcy_exclusion_note.lower() or \
               "liquidation" in report.bankruptcy_exclusion_note.lower()

    def test_calibration_warning_fires_for_low_base_rate_segment(self):
        """Synthetic dataset with 1 positive in 30 should trigger warning."""
        from bve.analysis.ma_backtest import MABacktestRecord
        from bve.analysis.ma_base_rate_report import compute_base_rate_report
        records = [
            MABacktestRecord("Pos", 2022, 1, 1.0, 1, 1, 0, 0, 0),
        ] + [
            MABacktestRecord(f"Neg{i}", 2022, 0, 1.0, 0, 1, 0, 0, 0,
                             negative_type="normal_independent")
            for i in range(29)
        ]
        r = compute_base_rate_report(records)
        # base_rate = 1/30 < 10%, should trigger warning
        assert r.overall.calibration_warning is not None

    def test_small_segment_triggers_warning(self):
        """A segment with fewer than 10 records triggers a small-sample warning."""
        from bve.analysis.ma_backtest import MABacktestRecord
        from bve.analysis.ma_base_rate_report import compute_base_rate_report
        records = [
            MABacktestRecord("Pos1", 2022, 1, 2.0, 1, 1, 0, 0, 0),
            MABacktestRecord("Neg1", 2022, 0, 2.0, 1, 1, 0, 0, 0,
                             negative_type="normal_independent"),
        ]
        r = compute_base_rate_report(records)
        assert r.overall.calibration_warning is not None

    def test_dataset_version_stamped(self, report):
        assert report.dataset_version == "expanded_v1"

    def test_segment_n_total_is_positive_plus_all_negatives(self, report):
        seg = report.overall
        expected_total = seg.n_positive + sum(seg.n_by_negative_type.values())
        assert seg.n_total == expected_total

    def test_segment_calibration_negatives_plus_bk_equals_all_neg(self, report):
        seg = report.overall
        bk_count = seg.n_by_negative_type.get("bankruptcy_or_liquidation", 0)
        assert seg.n_calibration_negatives == (seg.n_total - seg.n_positive - bk_count)


# ---------------------------------------------------------------------------
# TestRenderMarkdown
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    @pytest.fixture
    def md(self):
        from bve.analysis.ma_backtest import MA_EXPANDED_DATASET
        from bve.analysis.ma_base_rate_report import compute_base_rate_report, render_markdown
        r = compute_base_rate_report(MA_EXPANDED_DATASET)
        return render_markdown(r)

    def test_contains_base_rate_header(self, md):
        assert "Base Rate" in md

    def test_contains_negative_type_breakdown(self, md):
        assert "Negative Type Breakdown" in md

    def test_bankruptcy_mentioned(self, md):
        assert "bankruptcy" in md.lower()

    def test_markdown_table_pipes(self, md):
        # At least one pipe character present in each table row
        table_rows = [l for l in md.splitlines() if l.startswith("|")]
        assert len(table_rows) > 5

    def test_contains_ci_column(self, md):
        assert "80% CI" in md

    def test_contains_overall_segment(self, md):
        assert "overall" in md

    def test_exclusion_note_present(self, md):
        assert "Bankruptcy Exclusion Note" in md

    def test_ends_with_newline(self, md):
        assert md.endswith("\n")


# ---------------------------------------------------------------------------
# TestCLI
# ---------------------------------------------------------------------------

class TestCLI:
    def test_json_output_has_required_keys(self, capsys):
        from bve.cli.ma_base_rate_report import main
        main(["--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for key in (
            "dataset_version", "n_positives", "n_negatives_total",
            "n_by_negative_type", "overall", "by_therapeutic_area",
            "by_stage", "by_cap_bucket", "bankruptcy_exclusion_note",
        ):
            assert key in data, f"Missing key: {key}"

    def test_core_dataset_uses_40_records(self, capsys):
        from bve.cli.ma_base_rate_report import main
        main(["--dataset", "core", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        total = data["n_positives"] + data["n_negatives_total"]
        assert total == 40

    def test_expanded_dataset_uses_gte_120_records(self, capsys):
        from bve.cli.ma_base_rate_report import main
        main(["--dataset", "expanded", "--json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        total = data["n_positives"] + data["n_negatives_total"]
        assert total >= 120

    def test_markdown_output_no_crash(self, capsys):
        from bve.cli.ma_base_rate_report import main
        rc = main([])
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out) > 100

    def test_file_output(self, tmp_path):
        from bve.cli.ma_base_rate_report import main
        out_path = tmp_path / "report.md"
        rc = main(["--output", str(out_path)])
        assert rc == 0
        assert out_path.exists()
        content = out_path.read_text()
        assert "Base Rate" in content

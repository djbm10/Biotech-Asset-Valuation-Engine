"""
Tests for bve.empirical.coverage — CoverageReport + build_coverage_report.
"""
import pytest

from bve.empirical.base_rate_table import BaseRateTable
from bve.empirical.coverage import CellCoverage, CoverageReport, build_coverage_report
from bve.empirical.pos_outcome import POSOutcomeRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(
    phase="phase_2",
    success=True,
    moa="novel",
    bio=False,
    ta="oncology",
    sponsor="AcmeBio",
    year="2020",
    modality="small_molecule",
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{phase}-{success}-{sponsor}",
        sponsor=sponsor,
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        therapeutic_area=ta,
        modality=modality,
        moa_precedent=moa,
        biomarker_selected=bio,
        success=success,
        outcome_raw="advanced" if success else "failed",
        outcome_date=year,
    )


def _make_records() -> list[POSOutcomeRecord]:
    """10 records across phases with known composition."""
    recs = []
    # 4 phase_2 (3 success, 1 failure)
    for i in range(3):
        recs.append(_rec("phase_2", True, sponsor=f"Sponsor{i}"))
    recs.append(_rec("phase_2", False, sponsor="Sponsor3"))
    # 4 phase_3 (2 success, 2 failure)
    for i in range(2):
        recs.append(_rec("phase_3", True, sponsor=f"SponsorX{i}"))
    for i in range(2):
        recs.append(_rec("phase_3", False, sponsor=f"SponsorY{i}"))
    # 2 phase_1 (1 success, 1 failure)
    recs.append(_rec("phase_1", True, sponsor="Alpha"))
    recs.append(_rec("phase_1", False, sponsor="Beta"))
    return recs


# ---------------------------------------------------------------------------
# Empty dataset
# ---------------------------------------------------------------------------

class TestBuildCoverageReportEmpty:
    def test_empty_records_returns_zero_report(self):
        table = BaseRateTable([])
        report = build_coverage_report([], table)
        assert report.total_records == 0
        assert report.total_success == 0
        assert report.total_failure == 0
        assert report.overall_success_rate == 0.0
        assert report.cells == []
        assert report.sparse_cells == []

    def test_empty_report_summary_contains_header(self):
        table = BaseRateTable([])
        report = build_coverage_report([], table)
        assert "Coverage Report" in report.summary()


# ---------------------------------------------------------------------------
# Non-empty dataset
# ---------------------------------------------------------------------------

class TestBuildCoverageReportBasic:
    def setup_method(self):
        self.records = _make_records()
        self.table = BaseRateTable(self.records, smoothing_alpha=1.0)
        self.report = build_coverage_report(self.records, self.table, sparse_threshold=3)

    def test_total_records(self):
        assert self.report.total_records == 10

    def test_success_and_failure_counts(self):
        assert self.report.total_success == 6
        assert self.report.total_failure == 4

    def test_overall_success_rate(self):
        assert abs(self.report.overall_success_rate - 0.6) < 0.01

    def test_by_phase_keys_present(self):
        assert "phase_1" in self.report.by_phase
        assert "phase_2" in self.report.by_phase
        assert "phase_3" in self.report.by_phase

    def test_by_phase_counts(self):
        assert self.report.by_phase["phase_2"] == 4
        assert self.report.by_phase["phase_3"] == 4
        assert self.report.by_phase["phase_1"] == 2

    def test_by_therapeutic_area(self):
        assert self.report.by_therapeutic_area.get("oncology") == 10

    def test_by_modality(self):
        assert "small_molecule" in self.report.by_modality

    def test_by_sponsor_is_non_empty(self):
        assert len(self.report.by_sponsor) > 0

    def test_phase_smoothed_rates_present(self):
        rates = self.report.phase_smoothed_rates
        assert "phase_2" in rates
        assert 0.0 < rates["phase_2"] < 1.0

    def test_total_cells_positive(self):
        # Table creates multiple key levels per record
        assert self.report.total_cells > 0

    def test_cells_list_matches_total(self):
        assert len(self.report.cells) == self.report.total_cells


# ---------------------------------------------------------------------------
# Sparse cell detection
# ---------------------------------------------------------------------------

class TestSparseCellDetection:
    def test_all_sparse_when_threshold_high(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table, sparse_threshold=1000)
        assert len(report.sparse_cells) == report.total_cells

    def test_no_sparse_when_threshold_zero(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table, sparse_threshold=0)
        assert len(report.sparse_cells) == 0

    def test_sparse_cells_flagged_in_cell_objects(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table, sparse_threshold=3)
        for c in report.sparse_cells:
            assert c.is_sparse is True
            assert c.n < 3

    def test_sparse_warnings_returns_strings(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table, sparse_threshold=1000)
        warnings = report.sparse_warnings()
        assert len(warnings) == report.total_cells
        assert all(isinstance(w, str) for w in warnings)

    def test_no_sparse_warnings_when_no_sparse(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table, sparse_threshold=0)
        assert report.sparse_warnings() == []


# ---------------------------------------------------------------------------
# CellCoverage contents
# ---------------------------------------------------------------------------

class TestCellCoverageContents:
    def test_cell_coverage_n_equals_success_plus_failure(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table)
        for cell in report.cells:
            assert cell.n == cell.n_success + cell.n_failure

    def test_cell_coverage_raw_rate_between_0_and_1(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table)
        for cell in report.cells:
            assert 0.0 <= cell.raw_rate <= 1.0

    def test_cell_coverage_smoothed_rate_between_0_and_1(self):
        records = _make_records()
        table = BaseRateTable(records, smoothing_alpha=1.0)
        report = build_coverage_report(records, table)
        for cell in report.cells:
            assert 0.0 < cell.smoothed_rate < 1.0


# ---------------------------------------------------------------------------
# Summary output
# ---------------------------------------------------------------------------

class TestCoverageReportSummary:
    def test_summary_contains_record_count(self):
        records = _make_records()
        table = BaseRateTable(records)
        report = build_coverage_report(records, table)
        assert "10" in report.summary()

    def test_summary_contains_phase_keys(self):
        records = _make_records()
        table = BaseRateTable(records)
        report = build_coverage_report(records, table)
        summary = report.summary()
        assert "phase_2" in summary

    def test_summary_contains_sparse_warning_when_applicable(self):
        records = _make_records()
        table = BaseRateTable(records)
        report = build_coverage_report(records, table, sparse_threshold=1000)
        assert "Sparse" in report.summary() or "sparse" in report.summary()


# ---------------------------------------------------------------------------
# Top-N sponsors
# ---------------------------------------------------------------------------

class TestTopNSponsors:
    def test_top_n_sponsors_respected(self):
        records = _make_records()
        table = BaseRateTable(records)
        report = build_coverage_report(records, table, top_n_sponsors=3)
        assert len(report.by_sponsor) <= 3

    def test_all_sponsors_when_top_n_large(self):
        records = _make_records()
        table = BaseRateTable(records)
        report = build_coverage_report(records, table, top_n_sponsors=1000)
        # 10 records, each with unique sponsor name
        assert len(report.by_sponsor) == 10

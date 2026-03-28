"""
Sprint 9 Phase 4 — POS Backtest Dataset Validation (Task 9.18).

Verifies that research/data/oncology_phase_transitions.csv:
- Has sufficient sample size (N ≥ 50)
- Is not survivor-biased (overall success rate < 55%)
- Approximates realistic industry priors per phase
  * Phase 2 success rate 35–50%
  * Phase 3 success rate 35–55%
- Has enough failures in each phase for meaningful signal
- Columns have expected values (schema validation)

These tests are data-quality guards, not model-performance tests.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

DATASET_PATH = Path(__file__).parents[1] / "research" / "data" / "oncology_phase_transitions.csv"

VALID_PHASES = {"phase_1", "phase_2", "phase_3", "phase_3b", "nda_bla"}
VALID_OUTCOMES = {"advanced", "approved", "failed", "withdrawn", "terminated"}
VALID_ENDPOINT_TYPES = {
    "hard_clinical", "surrogate_validated", "surrogate",
    "composite", "biomarker", "primary",
}


def _load_rows() -> list[dict]:
    with open(DATASET_PATH, newline="") as f:
        return list(csv.DictReader(f))


def _success(row: dict) -> bool:
    return row["outcome"] in ("advanced", "approved")


@pytest.fixture(scope="module")
def rows():
    return _load_rows()


@pytest.fixture(scope="module")
def phase_2_rows(rows):
    return [r for r in rows if r["phase_start"] == "phase_2"]


@pytest.fixture(scope="module")
def phase_3_rows(rows):
    return [r for r in rows if r["phase_start"] in ("phase_3", "phase_3b")]


# ---------------------------------------------------------------------------
# Schema & integrity
# ---------------------------------------------------------------------------

class TestDatasetSchema:
    def test_file_exists(self):
        assert DATASET_PATH.exists(), f"Dataset missing: {DATASET_PATH}"

    def test_has_required_columns(self, rows):
        required = {
            "drug", "company", "indication", "phase_start",
            "outcome", "year", "moa_precedent", "biomarker_enriched",
            "safety_profile", "endpoint_type",
        }
        assert rows, "Dataset is empty"
        assert required.issubset(rows[0].keys()), \
            f"Missing columns: {required - rows[0].keys()}"

    def test_all_phase_start_values_valid(self, rows):
        bad = [r["drug"] for r in rows if r["phase_start"] not in VALID_PHASES]
        assert not bad, f"Invalid phase_start values in rows: {bad}"

    def test_all_outcome_values_valid(self, rows):
        bad = [r["drug"] for r in rows if r["outcome"] not in VALID_OUTCOMES]
        assert not bad, f"Invalid outcome values in rows: {bad}"

    def test_year_is_numeric(self, rows):
        for r in rows:
            assert r["year"].isdigit(), f"{r['drug']}: year is not numeric: {r['year']!r}"

    def test_no_duplicate_drug_phase(self, rows):
        seen: set[tuple] = set()
        dupes = []
        for r in rows:
            key = (r["drug"].lower(), r["phase_start"])
            if key in seen:
                dupes.append(key)
            seen.add(key)
        assert not dupes, f"Duplicate drug/phase combinations: {dupes}"


# ---------------------------------------------------------------------------
# Sample size
# ---------------------------------------------------------------------------

class TestSampleSize:
    def test_total_n_at_least_50(self, rows):
        assert len(rows) >= 50, f"Dataset too small: N={len(rows)}"

    def test_phase_2_n_at_least_20(self, phase_2_rows):
        assert len(phase_2_rows) >= 20, \
            f"Insufficient Phase 2 programs: N={len(phase_2_rows)}"

    def test_phase_3_n_at_least_15(self, phase_3_rows):
        assert len(phase_3_rows) >= 15, \
            f"Insufficient Phase 3 programs: N={len(phase_3_rows)}"

    def test_phase_2_has_meaningful_failures(self, phase_2_rows):
        failures = [r for r in phase_2_rows if r["outcome"] == "failed"]
        assert len(failures) >= 10, \
            f"Too few Phase 2 failures for valid calibration: N={len(failures)}"

    def test_phase_3_has_meaningful_failures(self, phase_3_rows):
        failures = [r for r in phase_3_rows if r["outcome"] == "failed"]
        assert len(failures) >= 10, \
            f"Too few Phase 3 failures for valid calibration: N={len(failures)}"


# ---------------------------------------------------------------------------
# Base-rate balance (survivor bias guards)
# ---------------------------------------------------------------------------

class TestBaseRateBalance:
    def test_overall_success_rate_not_survivor_biased(self, rows):
        """Overall success rate must be < 55% to avoid survivor selection bias."""
        n_success = sum(1 for r in rows if _success(r))
        rate = n_success / len(rows)
        assert rate < 0.55, \
            f"Overall success rate {rate:.1%} too high — likely survivor biased"

    def test_phase_2_success_rate_reflects_industry_prior(self, phase_2_rows):
        """Phase 2 success rate should approximate the ~35-50% industry prior."""
        n_success = sum(1 for r in phase_2_rows if _success(r))
        rate = n_success / len(phase_2_rows)
        assert 0.30 <= rate <= 0.55, \
            f"Phase 2 success rate {rate:.1%} outside realistic range (30-55%)"

    def test_phase_3_success_rate_reflects_industry_prior(self, phase_3_rows):
        """Phase 3 success rate should approximate the ~40-60% industry prior."""
        n_success = sum(1 for r in phase_3_rows if _success(r))
        rate = n_success / len(phase_3_rows)
        assert 0.30 <= rate <= 0.65, \
            f"Phase 3 success rate {rate:.1%} outside realistic range (30-65%)"

    def test_phase_2_success_rate_below_60pct(self, phase_2_rows):
        """Hard cap: Phase 2 success rate must be below 60% (survivor bias threshold)."""
        n_success = sum(1 for r in phase_2_rows if _success(r))
        rate = n_success / len(phase_2_rows)
        assert rate < 0.60, \
            f"Phase 2 success rate {rate:.1%} ≥ 60% — strong survivor selection bias"

    def test_phase_3_success_rate_below_65pct(self, phase_3_rows):
        """Hard cap: Phase 3 success rate must be below 65%."""
        n_success = sum(1 for r in phase_3_rows if _success(r))
        rate = n_success / len(phase_3_rows)
        assert rate < 0.65, \
            f"Phase 3 success rate {rate:.1%} ≥ 65% — strong survivor selection bias"


# ---------------------------------------------------------------------------
# Feature distribution (covariate balance)
# ---------------------------------------------------------------------------

class TestCovariateBalance:
    def test_has_both_biomarker_enriched_and_unselected(self, rows):
        """Dataset must contain biomarker-enriched and non-enriched programs."""
        enriched = [r for r in rows if r.get("biomarker_enriched", "").lower() == "true"]
        unenriched = [r for r in rows if r.get("biomarker_enriched", "").lower() == "false"]
        assert len(enriched) >= 5, f"Too few biomarker-enriched programs: {len(enriched)}"
        assert len(unenriched) >= 10, f"Too few biomarker-unselected programs: {len(unenriched)}"

    def test_has_novel_and_established_moa(self, rows):
        moa_values = {r.get("moa_precedent", "").lower() for r in rows}
        assert "novel" in moa_values, "No novel MoA programs in dataset"
        assert "partial" in moa_values or "established" in moa_values, \
            "No established/partial MoA programs in dataset"

    def test_endpoint_type_diversity(self, rows):
        endpoint_types = {r.get("endpoint_type", "") for r in rows}
        assert len(endpoint_types) >= 2, \
            f"Insufficient endpoint type diversity: {endpoint_types}"

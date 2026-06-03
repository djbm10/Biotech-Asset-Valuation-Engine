"""
Tests for universe_schema.py (Phase 2M).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from bve.ingestion.universe_schema import (
    ACQUIRER_REQUIRED_FIELDS,
    MAX_STALE_DAYS,
    TARGET_REQUIRED_FIELDS,
    VALID_LEAD_ASSET_STAGES,
    VALID_MODALITIES,
    VALID_THERAPEUTIC_AREAS,
    UniverseIssue,
    UniverseValidationResult,
    load_and_validate,
    profile_quality_score,
    validate_universe_schema,
)

_TODAY = date.today().isoformat()
_RECENT = (date.today() - timedelta(days=30)).isoformat()
_STALE = (date.today() - timedelta(days=MAX_STALE_DAYS + 10)).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _target(
    ticker: str = "RVMD",
    name: str = "Revolution Medicines",
    cik: str = "0001628171",
    aliases: list | None = None,
    therapeutic_areas: list | None = None,
    lead_asset: str = "daraxonrasib",
    lead_asset_stage: str = "phase3",
    modality: str = "small_molecule",
    company_type: str = "drug_developer",
    market_cap_bucket: str = "mid",
    cash_position_source: str = "sec_10q_2025q4",
    rd_expense_source: str = "sec_10k_2025",
    last_verified_date: str | None = None,
    notes: str = "Test target with sufficient notes text.",
    **kwargs,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "cik": cik,
        "aliases": aliases if aliases is not None else ["RevMed"],
        "therapeutic_areas": therapeutic_areas if therapeutic_areas is not None else ["oncology"],
        "lead_asset": lead_asset,
        "lead_asset_stage": lead_asset_stage,
        "modality": modality,
        "company_type": company_type,
        "market_cap_bucket": market_cap_bucket,
        "cash_position_source": cash_position_source,
        "rd_expense_source": rd_expense_source,
        "last_verified_date": last_verified_date or _RECENT,
        "notes": notes,
        **kwargs,
    }


def _acquirer(
    ticker: str = "PFE",
    name: str = "Pfizer",
    cik: str = "0000078003",
    therapeutic_areas: list | None = None,
    modalities: list | None = None,
    deal_size_range_millions: list | None = None,
    strategic_priorities: list | None = None,
    patent_cliff_exposure: str = "Eliquis loses exclusivity 2026–2028.",
    last_verified_date: str | None = None,
    **kwargs,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "cik": cik,
        "therapeutic_areas": therapeutic_areas if therapeutic_areas is not None else ["oncology"],
        "modalities": modalities if modalities is not None else ["small_molecule", "biologic"],
        "deal_size_range_millions": deal_size_range_millions if deal_size_range_millions is not None else [1000, 60000],
        "strategic_priorities": strategic_priorities if strategic_priorities is not None else ["oncology_adcs", "rare_disease"],
        "patent_cliff_exposure": patent_cliff_exposure,
        "last_verified_date": last_verified_date or _RECENT,
        **kwargs,
    }


def _run(targets: dict, acquirers: dict, as_of: str | None = None) -> UniverseValidationResult:
    return validate_universe_schema(targets, acquirers, as_of)


# ---------------------------------------------------------------------------
# 1. Vocabularies
# ---------------------------------------------------------------------------


class TestVocabularies:
    def test_valid_therapeutic_areas_nonempty(self):
        assert len(VALID_THERAPEUTIC_AREAS) >= 10

    def test_valid_modalities_nonempty(self):
        assert len(VALID_MODALITIES) >= 8

    def test_valid_lead_asset_stages_contains_expected(self):
        for s in ("preclinical", "phase1", "phase2", "phase3", "commercial", "unknown"):
            assert s in VALID_LEAD_ASSET_STAGES

    def test_oncology_in_valid_tas(self):
        assert "oncology" in VALID_THERAPEUTIC_AREAS

    def test_small_molecule_in_valid_modalities(self):
        assert "small_molecule" in VALID_MODALITIES


# ---------------------------------------------------------------------------
# 2. profile_quality_score
# ---------------------------------------------------------------------------


class TestProfileQualityScore:
    def test_perfect_score_all_fields(self):
        entry = _target(notes="Sufficient notes for quality check here")
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score == 1.0

    def test_missing_cik_reduces_score(self):
        entry = _target(cik=None)
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0
        assert abs(score - 0.9) < 0.01

    def test_missing_aliases_reduces_score(self):
        entry = _target(aliases=[])
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0

    def test_invalid_modality_reduces_score(self):
        entry = _target(modality="unknown_bad_modality")
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0

    def test_stale_date_reduces_score(self):
        entry = _target(last_verified_date=_STALE)
        score = profile_quality_score(entry, date.fromisoformat(_TODAY))
        assert score < 1.0

    def test_empty_notes_reduces_score(self):
        entry = _target(notes="")
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0

    def test_short_notes_reduces_score(self):
        entry = _target(notes="short")
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0

    def test_score_in_range(self):
        entry = _target()
        score = profile_quality_score(entry)
        assert 0.0 <= score <= 1.0

    def test_invalid_stage_reduces_score(self):
        entry = _target(lead_asset_stage="Phase 3")  # wrong format
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0

    def test_missing_cash_source_reduces_score(self):
        entry = _target(cash_position_source="")
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0

    def test_missing_rd_source_reduces_score(self):
        entry = _target(rd_expense_source="")
        score = profile_quality_score(entry, date.fromisoformat(_RECENT))
        assert score < 1.0


# ---------------------------------------------------------------------------
# 3. Target validation rules
# ---------------------------------------------------------------------------


class TestTargetRules:
    def test_valid_target_no_errors(self):
        result = _run({"RVMD": _target()}, {})
        assert result.error_count == 0

    def test_t01_invalid_ticker_format(self):
        entry = _target(ticker="rv-md")
        result = _run({"rv-md": entry}, {})
        errors = [e for e in result.errors if e.rule == "T01"]
        assert len(errors) >= 1

    def test_t01_lowercase_ticker(self):
        entry = _target(ticker="rvmd")
        result = _run({"rvmd": entry}, {})
        errors = [e for e in result.errors if e.rule == "T01"]
        assert len(errors) >= 1

    def test_t02_duplicate_ticker(self):
        entry1 = _target(ticker="RVMD")
        entry2 = _target(ticker="RVMD", name="Other Co")
        result = _run({"RVMD": entry1, "RVMD2": entry2}, {})
        # Second entry with same ticker is the duplicate
        errors = [e for e in result.errors if e.rule == "T02"]
        assert len(errors) >= 1

    def test_t03_missing_cik_is_warning(self):
        entry = _target(cik=None)
        result = _run({"RVMD": entry}, {})
        warns = [w for w in result.warnings if w.rule == "T03"]
        assert len(warns) == 1
        assert result.error_count == 0  # CIK is warning, not error

    def test_t04_empty_aliases_warning(self):
        entry = _target(aliases=[])
        result = _run({"RVMD": entry}, {})
        warns = [w for w in result.warnings if w.rule == "T04"]
        assert len(warns) == 1

    def test_t05_invalid_ta_error(self):
        entry = _target(therapeutic_areas=["not_a_real_ta"])
        result = _run({"RVMD": entry}, {})
        errors = [e for e in result.errors if e.rule == "T05"]
        assert len(errors) >= 1

    def test_t05_valid_tas_no_error(self):
        entry = _target(therapeutic_areas=["oncology", "rare_disease"])
        result = _run({"RVMD": entry}, {})
        t05_errors = [e for e in result.errors if e.rule == "T05"]
        assert len(t05_errors) == 0

    def test_t06_invalid_modality_error(self):
        entry = _target(modality="nanoparticle_magic")
        result = _run({"RVMD": entry}, {})
        errors = [e for e in result.errors if e.rule == "T06"]
        assert len(errors) >= 1

    def test_t07_empty_lead_asset_error(self):
        entry = _target(lead_asset="")
        result = _run({"RVMD": entry}, {})
        errors = [e for e in result.errors if e.rule in ("T07", "T12")]
        assert len(errors) >= 1

    def test_t08_invalid_stage_error(self):
        entry = _target(lead_asset_stage="Phase Three")
        result = _run({"RVMD": entry}, {})
        errors = [e for e in result.errors if e.rule == "T08"]
        assert len(errors) >= 1

    def test_t09_stale_date_warning(self):
        entry = _target(last_verified_date=_STALE)
        result = _run({"RVMD": entry}, {}, as_of=_TODAY)
        warns = [w for w in result.warnings if w.rule == "T09"]
        assert len(warns) == 1

    def test_t10_missing_cash_source_warning(self):
        entry = _target(cash_position_source="")
        result = _run({"RVMD": entry}, {})
        warns = [w for w in result.warnings if w.rule == "T10"]
        assert len(warns) == 1

    def test_t11_missing_rd_source_warning(self):
        entry = _target(rd_expense_source="")
        result = _run({"RVMD": entry}, {})
        warns = [w for w in result.warnings if w.rule == "T11"]
        assert len(warns) == 1

    def test_t12_missing_required_field_error(self):
        entry = _target()
        del entry["lead_asset_stage"]
        result = _run({"RVMD": entry}, {})
        errors = [e for e in result.errors if e.rule == "T12"]
        assert len(errors) >= 1

    def test_target_count_incremented(self):
        targets = {f"T{i:03d}": _target(ticker=f"T{i:03d}") for i in range(5)}
        result = _run(targets, {})
        assert result.target_count == 5


# ---------------------------------------------------------------------------
# 4. Acquirer validation rules
# ---------------------------------------------------------------------------


class TestAcquirerRules:
    def test_valid_acquirer_no_errors(self):
        result = _run({}, {"PFE": _acquirer()})
        assert result.error_count == 0

    def test_a01_invalid_ticker_error(self):
        entry = _acquirer(ticker="pfe-inc")
        result = _run({}, {"pfe-inc": entry})
        errors = [e for e in result.errors if e.rule == "A01"]
        assert len(errors) >= 1

    def test_a02_duplicate_acquirer_error(self):
        entry1 = _acquirer(ticker="PFE")
        entry2 = _acquirer(ticker="PFE", name="Pfizer Other")
        result = _run({}, {"PFE": entry1, "PFE2": entry2})
        errors = [e for e in result.errors if e.rule == "A02"]
        assert len(errors) >= 1

    def test_a03_missing_cik_is_warning(self):
        entry = _acquirer(cik=None)
        result = _run({}, {"PFE": entry})
        warns = [w for w in result.warnings if w.rule == "A03"]
        assert len(warns) == 1

    def test_a04_invalid_ta_error(self):
        entry = _acquirer(therapeutic_areas=["not_real"])
        result = _run({}, {"PFE": entry})
        errors = [e for e in result.errors if e.rule == "A04"]
        assert len(errors) >= 1

    def test_a05_invalid_modality_error(self):
        entry = _acquirer(modalities=["made_up"])
        result = _run({}, {"PFE": entry})
        errors = [e for e in result.errors if e.rule == "A05"]
        assert len(errors) >= 1

    def test_a06_invalid_deal_range_error(self):
        entry = _acquirer(deal_size_range_millions=[5000, 1000])  # min > max
        result = _run({}, {"PFE": entry})
        errors = [e for e in result.errors if e.rule == "A06"]
        assert len(errors) >= 1

    def test_a06_valid_deal_range_no_error(self):
        entry = _acquirer(deal_size_range_millions=[500, 50000])
        result = _run({}, {"PFE": entry})
        a06 = [e for e in result.errors if e.rule == "A06"]
        assert len(a06) == 0

    def test_a07_stale_acquirer_warning(self):
        entry = _acquirer(last_verified_date=_STALE)
        result = _run({}, {"PFE": entry}, as_of=_TODAY)
        warns = [w for w in result.warnings if w.rule == "A07"]
        assert len(warns) == 1

    def test_a08_missing_strategic_priorities_warning(self):
        entry = _acquirer(strategic_priorities=[])
        result = _run({}, {"PFE": entry})
        warns = [w for w in result.warnings if w.rule == "A08"]
        assert len(warns) == 1

    def test_a09_missing_patent_cliff_warning(self):
        entry = _acquirer(patent_cliff_exposure="")
        result = _run({}, {"PFE": entry})
        warns = [w for w in result.warnings if w.rule == "A09"]
        assert len(warns) == 1

    def test_a10_missing_required_field_error(self):
        entry = _acquirer()
        del entry["deal_size_range_millions"]
        result = _run({}, {"PFE": entry})
        errors = [e for e in result.errors if e.rule == "A10"]
        assert len(errors) >= 1

    def test_acquirer_count_incremented(self):
        acquirers = {f"A{i:03d}": _acquirer(ticker=f"A{i:03d}") for i in range(3)}
        result = _run({}, acquirers)
        assert result.acquirer_count == 3


# ---------------------------------------------------------------------------
# 5. UniverseValidationResult properties
# ---------------------------------------------------------------------------


class TestUniverseValidationResult:
    def test_is_valid_true_when_no_errors(self):
        result = UniverseValidationResult()
        assert result.is_valid is True

    def test_is_valid_false_when_errors(self):
        result = UniverseValidationResult()
        result.issues.append(UniverseIssue(rule="T01", ticker="X", severity="error", message="test"))
        assert result.is_valid is False

    def test_warnings_dont_fail_is_valid(self):
        result = UniverseValidationResult()
        result.issues.append(UniverseIssue(rule="T03", ticker="X", severity="warning", message="test"))
        assert result.is_valid is True

    def test_quality_score_median_none_when_empty(self):
        result = UniverseValidationResult()
        assert result.quality_score_median is None

    def test_quality_score_median_single(self):
        result = UniverseValidationResult(target_quality_scores={"RVMD": 0.8})
        assert result.quality_score_median == 0.8

    def test_quality_score_median_even(self):
        result = UniverseValidationResult(target_quality_scores={"A": 0.6, "B": 0.8})
        assert result.quality_score_median == 0.7

    def test_quality_score_median_odd(self):
        result = UniverseValidationResult(target_quality_scores={"A": 0.6, "B": 0.8, "C": 0.7})
        assert result.quality_score_median == 0.7

    def test_missing_cik_count(self):
        result = UniverseValidationResult()
        result.issues.append(UniverseIssue(rule="T03", ticker="X", severity="warning", message="cik missing"))
        result.issues.append(UniverseIssue(rule="A03", ticker="Y", severity="warning", message="cik missing"))
        assert result.missing_cik_count == 2

    def test_suppression_reason_distribution(self):
        result = UniverseValidationResult()
        result.issues.append(UniverseIssue(rule="T03", ticker="X", severity="warning", message="a"))
        result.issues.append(UniverseIssue(rule="T03", ticker="Y", severity="warning", message="b"))
        result.issues.append(UniverseIssue(rule="T05", ticker="Z", severity="error", message="c"))
        dist = result.suppression_reason_distribution
        assert dist["T03"] == 2
        assert dist["T05"] == 1

    def test_issue_str_representation(self):
        issue = UniverseIssue(rule="T01", ticker="RVMD", severity="error", message="bad ticker", field="ticker")
        s = str(issue)
        assert "T01" in s
        assert "RVMD" in s
        assert "ticker" in s


# ---------------------------------------------------------------------------
# 6. load_and_validate
# ---------------------------------------------------------------------------


class TestLoadAndValidate:
    def test_loads_real_targets_file(self):
        targets_path = Path("research/universe/targets.yaml")
        acquirers_path = Path("research/universe/acquirers.yaml")
        if not targets_path.exists() or not acquirers_path.exists():
            pytest.skip("YAML files not present")
        result = load_and_validate(targets_path, acquirers_path)
        assert result.target_count > 0
        assert result.acquirer_count > 0

    def test_missing_targets_file_returns_empty(self, tmp_path):
        acquirers_path = tmp_path / "acquirers.yaml"
        acquirers_path.write_text("PFE:\n  ticker: PFE\n", encoding="utf-8")
        result = load_and_validate(tmp_path / "nonexistent_targets.yaml", acquirers_path)
        assert result.target_count == 0

    def test_writes_correct_target_count(self, tmp_path):
        targets = {
            "RVMD": _target(ticker="RVMD"),
            "BEAM": _target(ticker="BEAM", aliases=["Beam"], notes="Another test company with sufficient notes"),
        }
        acquirers = {"PFE": _acquirer()}
        t_path = tmp_path / "targets.yaml"
        a_path = tmp_path / "acquirers.yaml"
        t_path.write_text(yaml.dump(targets), encoding="utf-8")
        a_path.write_text(yaml.dump(acquirers), encoding="utf-8")
        result = load_and_validate(t_path, a_path)
        assert result.target_count == 2
        assert result.acquirer_count == 1

    def test_quality_scores_computed_for_all_targets(self, tmp_path):
        targets = {
            f"T{i:03d}": _target(ticker=f"T{i:03d}") for i in range(5)
        }
        acquirers = {}
        t_path = tmp_path / "targets.yaml"
        a_path = tmp_path / "acquirers.yaml"
        t_path.write_text(yaml.dump(targets), encoding="utf-8")
        a_path.write_text(yaml.dump(acquirers), encoding="utf-8")
        result = load_and_validate(t_path, a_path)
        assert len(result.target_quality_scores) == 5

    def test_empty_yaml_files_no_crash(self, tmp_path):
        t_path = tmp_path / "targets.yaml"
        a_path = tmp_path / "acquirers.yaml"
        t_path.write_text("{}", encoding="utf-8")
        a_path.write_text("{}", encoding="utf-8")
        result = load_and_validate(t_path, a_path)
        assert result.target_count == 0
        assert result.acquirer_count == 0


# ---------------------------------------------------------------------------
# 7. Integration: real YAML files pass acceptance criteria (Phase 2M)
# ---------------------------------------------------------------------------


class TestPhase2MAcceptanceCriteria:
    """
    These tests enforce the acceptance criteria from the Phase 2M spec.
    They will SKIP if the YAML files don't yet have the required counts.
    """

    @pytest.fixture(autouse=True)
    def _check_files(self):
        targets_path = Path("research/universe/targets.yaml")
        acquirers_path = Path("research/universe/acquirers.yaml")
        if not targets_path.exists() or not acquirers_path.exists():
            pytest.skip("YAML files not present")
        self.result = load_and_validate(targets_path, acquirers_path)

    def test_100_targets_present(self):
        assert self.result.target_count >= 100, (
            f"Expected ≥100 targets, got {self.result.target_count}"
        )

    def test_20_acquirers_present(self):
        assert self.result.acquirer_count >= 20, (
            f"Expected ≥20 acquirers, got {self.result.acquirer_count}"
        )

    def test_no_validation_errors(self):
        errors = self.result.errors
        msg = "\n".join(str(e) for e in errors[:10])
        assert len(errors) == 0, f"Expected no errors:\n{msg}"

    def test_quality_score_median_above_threshold(self):
        med = self.result.quality_score_median
        assert med is not None
        assert med > 0.75, f"Quality median {med:.2f} is not > 0.75"

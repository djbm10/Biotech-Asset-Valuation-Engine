"""
Tests for profile_enricher.py — Block 2B.

All external calls (SEC EDGAR, evidence ledger) are mocked.
No network access is required.

Covers:
  - TargetProfileEnriched construction and field values
  - AcquirerProfileEnriched construction and field values
  - Manual override priority (overrides > yaml > sec > null)
  - Financial enrichment (cash, R&D, runway)
  - Evidence ledger dynamic signals
  - Profile quality scoring and flags
  - Output writer (target_profiles.json, acquirer_profiles.json, profile_quality_report.json)
  - Graceful handling of SEC fetch failures
  - Edge cases: missing cash, missing R&D, empty ledger
"""
from __future__ import annotations

import json

import pytest

from bve.ingestion.profile_enricher import (
    AcquirerProfileEnriched,
    ProfileEnricher,
    TargetProfileEnriched,
    write_profiles,
)
from bve.ingestion.universe_loader import AcquirerEntry, TargetEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_target(ticker: str = "TSTR", **overrides) -> TargetEntry:
    base = dict(
        ticker=ticker,
        name="Test Biotech",
        exchange="NASDAQ",
        company_type="drug_developer",
        therapeutic_areas=["oncology"],
        lead_asset="TEST-001",
        lead_asset_phase="phase2",
        lead_modality="small_molecule",
        lead_indication="solid tumors",
        is_single_asset_company=False,
        include_in_screen=True,
        cik="0001234567",
        market_cap_bucket="micro",
        platform_type=None,
        has_partner_encumbrance=None,
        notes=None,
    )
    base.update(overrides)
    return TargetEntry(**base)


def _make_acquirer(ticker: str = "TACQ", **overrides) -> AcquirerEntry:
    base = dict(
        ticker=ticker,
        name="Big Pharma",
        therapeutic_areas=["oncology"],
        modalities=["biologic"],
        deal_size_range_millions=(1000.0, 10000.0),
        preferred_stages=["phase3"],
        include_as_acquirer=True,
        cik="0009876543",
        notes=None,
    )
    base.update(overrides)
    return AcquirerEntry(**base)


def _sec_full(ticker: str) -> dict:
    return {
        "cash_millions": 250.0,
        "rd_expense_millions": 120.0,
        "sgna_expense_millions": None,
        "shares_outstanding_millions": 80.0,
    }


def _sec_cash_only(ticker: str) -> dict:
    return {"cash_millions": 300.0, "rd_expense_millions": None, "shares_outstanding_millions": None}


def _sec_empty(ticker: str) -> dict:
    return {}


def _ledger_full(ticker: str) -> dict:
    return {"acquirer_appetite": 0.72, "acquirer_urgency": 0.65, "integration_capacity": 0.80}


def _ledger_empty(ticker: str) -> dict:
    return {}


def _make_enricher(
    targets=None,
    acquirers=None,
    overrides=None,
    sec_fetcher=None,
    ledger_fetcher=None,
) -> ProfileEnricher:
    targets = targets or {"TSTR": _make_target()}
    acquirers = acquirers or {"TACQ": _make_acquirer()}
    overrides = overrides or {}
    return ProfileEnricher(
        targets,
        acquirers,
        overrides,
        sec_fetcher=sec_fetcher or _sec_full,
        ledger_score_fetcher=ledger_fetcher or _ledger_full,
    )


# ===========================================================================
# TargetProfileEnriched — structure
# ===========================================================================


class TestTargetProfileEnriched:
    def test_returns_target_profile_instance(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert isinstance(p, TargetProfileEnriched)

    def test_ticker_preserved(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.ticker == "TSTR"

    def test_name_preserved(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.name == "Test Biotech"

    def test_lead_asset_populated(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.lead_asset == "TEST-001"

    def test_lead_asset_phase_populated(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.lead_asset_phase == "phase2"

    def test_therapeutic_areas_populated(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert "oncology" in p.therapeutic_areas

    def test_cash_millions_from_sec(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.cash_millions == 250.0

    def test_rd_expense_from_sec(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.rd_expense_ttm_millions == 120.0

    def test_shares_from_sec(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.shares_outstanding_millions == 80.0

    def test_sgna_from_sec_when_available(self):
        def sec_with_sgna(ticker: str) -> dict:
            return {
                "cash_millions": 250.0,
                "rd_expense_millions": 120.0,
                "sgna_expense_millions": 60.0,
                "shares_outstanding_millions": 80.0,
            }

        e = _make_enricher(sec_fetcher=sec_with_sgna)
        p = e.enrich_target("TSTR")
        assert p.sgna_expense_ttm_millions == 60.0
        assert p.operating_burn_ttm_millions == 180.0

    def test_cash_runway_computed(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        # 250 / (120/12) = 250/10 = 25.0 months
        assert p.cash_runway_months == pytest.approx(25.0, abs=0.1)

    def test_cash_runway_uses_rd_plus_sgna_when_available(self):
        def sec_with_sgna(ticker: str) -> dict:
            return {
                "cash_millions": 180.0,
                "rd_expense_millions": 120.0,
                "sgna_expense_millions": 60.0,
                "shares_outstanding_millions": None,
            }

        e = _make_enricher(sec_fetcher=sec_with_sgna)
        p = e.enrich_target("TSTR")
        # 180 / ((120 + 60) / 12) = 12 months
        assert p.cash_runway_months == pytest.approx(12.0, abs=0.1)
        assert "runway_estimated_from_rd_only" not in p.data_quality_flags

    def test_enriched_at_is_string(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert isinstance(p.enriched_at, str)
        assert "T" in p.enriched_at  # ISO format

    def test_include_in_screen_preserved(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.include_in_screen is True

    def test_cik_preserved(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.cik == "0001234567"


# ===========================================================================
# Manual override priority
# ===========================================================================


class TestManualOverridePriority:
    def test_override_wins_over_yaml_for_lead_asset(self):
        overrides = {"TSTR": {"lead_asset": "TEST-999"}}
        e = _make_enricher(overrides=overrides)
        p = e.enrich_target("TSTR")
        assert p.lead_asset == "TEST-999"

    def test_override_wins_over_yaml_for_phase(self):
        overrides = {"TSTR": {"lead_asset_phase": "phase3"}}
        e = _make_enricher(overrides=overrides)
        p = e.enrich_target("TSTR")
        assert p.lead_asset_phase == "phase3"

    def test_override_wins_for_therapeutic_areas(self):
        overrides = {"TSTR": {"therapeutic_areas": ["rare_disease"]}}
        e = _make_enricher(overrides=overrides)
        p = e.enrich_target("TSTR")
        assert p.therapeutic_areas == ["rare_disease"]

    def test_source_map_shows_manual_override(self):
        overrides = {"TSTR": {"lead_asset": "TEST-999"}}
        e = _make_enricher(overrides=overrides)
        p = e.enrich_target("TSTR")
        assert p.source_map["lead_asset"] == "manual_override"

    def test_yaml_wins_when_no_override(self):
        e = _make_enricher(overrides={})
        p = e.enrich_target("TSTR")
        assert p.source_map["lead_asset"] == "yaml"
        assert p.lead_asset == "TEST-001"

    def test_source_map_shows_sec_for_financial_fields(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.source_map["cash_millions"] == "sec"
        assert p.source_map["rd_expense_ttm_millions"] == "sec"

    def test_acquirer_override_applies_to_therapeutic_areas(self):
        overrides = {"TACQ": {"therapeutic_areas": ["metabolic", "oncology"]}}
        e = _make_enricher(overrides=overrides)
        p = e.enrich_acquirer("TACQ")
        assert "metabolic" in p.therapeutic_areas


# ===========================================================================
# Financial enrichment edge cases
# ===========================================================================


class TestFinancialEnrichment:
    def test_missing_cash_sets_cash_missing_flag(self):
        e = _make_enricher(sec_fetcher=_sec_empty)
        p = e.enrich_target("TSTR")
        assert "cash_missing" in p.data_quality_flags

    def test_missing_rd_sets_rd_expense_missing_flag(self):
        e = _make_enricher(sec_fetcher=_sec_empty)
        p = e.enrich_target("TSTR")
        assert "rd_expense_missing" in p.data_quality_flags

    def test_cash_only_no_runway(self):
        e = _make_enricher(sec_fetcher=_sec_cash_only)
        p = e.enrich_target("TSTR")
        assert p.cash_millions == 300.0
        assert p.cash_runway_months is None

    def test_runway_flag_set_when_computed(self):
        e = _make_enricher(sec_fetcher=_sec_full)
        p = e.enrich_target("TSTR")
        assert "runway_estimated_from_rd_only" in p.data_quality_flags

    def test_missing_sgna_sets_flag_when_rd_available(self):
        e = _make_enricher(sec_fetcher=_sec_full)
        p = e.enrich_target("TSTR")
        assert "sgna_expense_missing" in p.data_quality_flags

    def test_sec_source_null_when_no_data(self):
        e = _make_enricher(sec_fetcher=_sec_empty)
        p = e.enrich_target("TSTR")
        assert p.source_map["cash_millions"] == "null"
        assert p.source_map["cash_runway_months"] == "null"

    def test_sec_fetch_exception_does_not_crash(self):
        def failing_sec(ticker: str) -> dict:
            raise ConnectionError("network down")

        e = _make_enricher(sec_fetcher=failing_sec)
        p = e.enrich_target("TSTR")
        assert p.cash_millions is None
        assert "cash_missing" in p.data_quality_flags

    def test_runway_formula_correct(self):
        def sec_custom(ticker: str) -> dict:
            return {"cash_millions": 60.0, "rd_expense_millions": 24.0, "shares_outstanding_millions": None}

        e = _make_enricher(sec_fetcher=sec_custom)
        p = e.enrich_target("TSTR")
        # 60 / (24/12) = 60/2 = 30 months
        assert p.cash_runway_months == pytest.approx(30.0, abs=0.1)


# ===========================================================================
# Quality scoring — targets
# ===========================================================================


class TestTargetQualityScore:
    def test_full_data_high_quality_score(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert p.quality_score >= 0.70

    def test_missing_cash_reduces_score(self):
        e_full = _make_enricher(sec_fetcher=_sec_full)
        e_empty = _make_enricher(sec_fetcher=_sec_empty)
        p_full = e_full.enrich_target("TSTR")
        p_empty = e_empty.enrich_target("TSTR")
        assert p_full.quality_score > p_empty.quality_score

    def test_missing_lead_asset_reduces_score(self):
        t = _make_target(lead_asset="")
        e_empty_lead = _make_enricher(targets={"TSTR": t})
        e_normal = _make_enricher()
        p_empty = e_empty_lead.enrich_target("TSTR")
        p_normal = e_normal.enrich_target("TSTR")
        assert p_normal.quality_score > p_empty.quality_score

    def test_quality_score_in_range(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert 0.0 <= p.quality_score <= 1.0

    def test_quality_score_is_float(self):
        e = _make_enricher()
        p = e.enrich_target("TSTR")
        assert isinstance(p.quality_score, float)

    def test_phase_unknown_sets_flag(self):
        t = _make_target(lead_asset_phase="unknown")
        e = _make_enricher(targets={"TSTR": t})
        p = e.enrich_target("TSTR")
        assert "phase_missing_or_unknown" in p.data_quality_flags

    def test_manual_override_flag_informational(self):
        overrides = {"TSTR": {"lead_asset": "OVERRIDE"}}
        e = _make_enricher(overrides=overrides)
        p = e.enrich_target("TSTR")
        assert "manual_override_used" in p.data_quality_flags
        # Does not reduce quality score
        e_no_override = _make_enricher(overrides={})
        p_no_override = e_no_override.enrich_target("TSTR")
        assert p.quality_score == p_no_override.quality_score


# ===========================================================================
# AcquirerProfileEnriched
# ===========================================================================


class TestAcquirerProfileEnriched:
    def test_returns_acquirer_profile_instance(self):
        e = _make_enricher()
        p = e.enrich_acquirer("TACQ")
        assert isinstance(p, AcquirerProfileEnriched)

    def test_ticker_preserved(self):
        e = _make_enricher()
        p = e.enrich_acquirer("TACQ")
        assert p.ticker == "TACQ"

    def test_bd_appetite_from_ledger(self):
        e = _make_enricher(ledger_fetcher=_ledger_full)
        p = e.enrich_acquirer("TACQ")
        assert p.bd_appetite == pytest.approx(0.72)

    def test_urgency_from_ledger(self):
        e = _make_enricher(ledger_fetcher=_ledger_full)
        p = e.enrich_acquirer("TACQ")
        assert p.urgency == pytest.approx(0.65)

    def test_integration_capacity_from_ledger(self):
        e = _make_enricher(ledger_fetcher=_ledger_full)
        p = e.enrich_acquirer("TACQ")
        assert p.integration_capacity == pytest.approx(0.80)

    def test_empty_ledger_uses_prior_defaults(self):
        e = _make_enricher(ledger_fetcher=_ledger_empty)
        p = e.enrich_acquirer("TACQ")
        assert p.bd_appetite == pytest.approx(0.50)   # DEFAULT_SEED_SCORES["acquirer_appetite"]
        assert p.urgency == pytest.approx(0.30)        # DEFAULT_SEED_SCORES["acquirer_urgency"]
        assert p.integration_capacity == pytest.approx(0.70)

    def test_empty_ledger_sets_no_evidence_flag(self):
        e = _make_enricher(ledger_fetcher=_ledger_empty)
        p = e.enrich_acquirer("TACQ")
        assert "no_evidence_coverage" in p.data_quality_flags

    def test_ledger_source_shown_when_data_present(self):
        e = _make_enricher(ledger_fetcher=_ledger_full)
        p = e.enrich_acquirer("TACQ")
        assert p.source_map["bd_appetite"] == "ledger"
        assert p.source_map["urgency"] == "ledger"

    def test_prior_source_shown_when_empty_ledger(self):
        e = _make_enricher(ledger_fetcher=_ledger_empty)
        p = e.enrich_acquirer("TACQ")
        assert p.source_map["bd_appetite"] == "prior"

    def test_deal_size_range_preserved(self):
        e = _make_enricher()
        p = e.enrich_acquirer("TACQ")
        lo, hi = p.deal_size_range_millions
        assert lo == 1000.0
        assert hi == 10000.0

    def test_modalities_preserved(self):
        e = _make_enricher()
        p = e.enrich_acquirer("TACQ")
        assert "biologic" in p.modalities

    def test_ledger_exception_does_not_crash(self):
        def failing_ledger(ticker: str) -> dict:
            raise RuntimeError("ledger unavailable")

        e = _make_enricher(ledger_fetcher=failing_ledger)
        p = e.enrich_acquirer("TACQ")
        assert p.bd_appetite == pytest.approx(0.50)
        assert "no_evidence_coverage" in p.data_quality_flags


# ===========================================================================
# enrich_targets() / enrich_acquirers() batch methods
# ===========================================================================


class TestBatchEnrichment:
    def test_enrich_targets_returns_dict(self):
        e = _make_enricher()
        result = e.enrich_targets()
        assert isinstance(result, dict)
        assert "TSTR" in result

    def test_enrich_acquirers_returns_dict(self):
        e = _make_enricher()
        result = e.enrich_acquirers()
        assert isinstance(result, dict)
        assert "TACQ" in result

    def test_all_targets_enriched(self):
        targets = {
            "AAA": _make_target("AAA"),
            "BBB": _make_target("BBB"),
            "CCC": _make_target("CCC"),
        }
        e = _make_enricher(targets=targets)
        result = e.enrich_targets()
        assert set(result.keys()) == {"AAA", "BBB", "CCC"}

    def test_all_acquirers_enriched(self):
        acquirers = {
            "ACQ1": _make_acquirer("ACQ1"),
            "ACQ2": _make_acquirer("ACQ2"),
        }
        e = _make_enricher(acquirers=acquirers)
        result = e.enrich_acquirers()
        assert set(result.keys()) == {"ACQ1", "ACQ2"}


# ===========================================================================
# Output writer
# ===========================================================================


class TestWriteProfiles:
    def _make_profiles(self):
        e = _make_enricher()
        return e.enrich_targets(), e.enrich_acquirers()

    def test_target_profiles_json_created(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        assert (tmp_path / "profiles" / "target_profiles.json").exists()

    def test_acquirer_profiles_json_created(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        assert (tmp_path / "profiles" / "acquirer_profiles.json").exists()

    def test_quality_report_created(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        assert (tmp_path / "profiles" / "profile_quality_report.json").exists()

    def test_target_profiles_json_is_valid_json(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        content = (tmp_path / "profiles" / "target_profiles.json").read_text()
        parsed = json.loads(content)
        assert "TSTR" in parsed

    def test_acquirer_profiles_json_is_valid_json(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        content = (tmp_path / "profiles" / "acquirer_profiles.json").read_text()
        parsed = json.loads(content)
        assert "TACQ" in parsed

    def test_quality_report_has_summary(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        content = json.loads(
            (tmp_path / "profiles" / "profile_quality_report.json").read_text()
        )
        assert "summary" in content
        assert content["summary"]["target_count"] == 1
        assert content["summary"]["acquirer_count"] == 1

    def test_quality_report_targets_section(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        content = json.loads(
            (tmp_path / "profiles" / "profile_quality_report.json").read_text()
        )
        assert "TSTR" in content["targets"]
        assert "quality_score" in content["targets"]["TSTR"]

    def test_deal_size_range_serialised_as_list(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        content = json.loads(
            (tmp_path / "profiles" / "acquirer_profiles.json").read_text()
        )
        dr = content["TACQ"]["deal_size_range_millions"]
        assert isinstance(dr, list)
        assert len(dr) == 2

    def test_output_dir_created_if_missing(self, tmp_path):
        t, a = self._make_profiles()
        deep = tmp_path / "a" / "b" / "c"
        write_profiles(t, a, deep)
        assert (deep / "target_profiles.json").exists()

    def test_high_quality_pct_computed(self, tmp_path):
        t, a = self._make_profiles()
        write_profiles(t, a, tmp_path / "profiles")
        content = json.loads(
            (tmp_path / "profiles" / "profile_quality_report.json").read_text()
        )
        assert "targets_high_quality_pct" in content["summary"]
        pct = content["summary"]["targets_high_quality_pct"]
        assert 0.0 <= pct <= 1.0

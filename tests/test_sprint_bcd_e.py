"""
Tests for Sprints B, C, D, E:
  B — EV-based deal_size_fit
  C — Structured suppression reason codes + Coverage Recovery Queue
  D — 5-section diligence shortlists in weekly report
  E — Historical calibration runner
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

from bve.ingestion.profile_enricher import ProfileEnricher, TargetProfileEnriched
from bve.ingestion.sec_edgar import extract_long_term_debt
from bve.intelligence.weekly_ma_screen import (
    WeeklyMAScreen,
    _deal_size_fit,
)
from bve.reporting.weekly_report import WeeklyReportGenerator


# ---------------------------------------------------------------------------
# Helpers — reusable fixture builders
# ---------------------------------------------------------------------------

def _make_target(
    ticker: str = "TEST",
    lead_asset_phase: str = "phase_2",
    therapeutic_areas: Optional[list[str]] = None,
    cash_runway_months: Optional[float] = 18.0,
    market_cap_bucket: str = "micro",
    enterprise_value_millions: Optional[float] = None,
    data_quality_flags: Optional[list[str]] = None,
    include_in_screen: bool = True,
) -> TargetProfileEnriched:
    return TargetProfileEnriched(
        ticker=ticker,
        name=f"{ticker} Corp",
        cik=None,
        exchange="NASDAQ",
        company_type="drug_developer",
        therapeutic_areas=therapeutic_areas or ["oncology"],
        lead_asset="TEST-001",
        lead_asset_phase=lead_asset_phase,
        lead_modality="small_molecule",
        lead_indication="test indication",
        is_single_asset_company=False,
        include_in_screen=include_in_screen,
        market_cap_bucket=market_cap_bucket,
        has_partner_encumbrance=None,
        cash_millions=200.0,
        rd_expense_ttm_millions=80.0,
        sgna_expense_ttm_millions=None,
        operating_burn_ttm_millions=80.0,
        shares_outstanding_millions=60.0,
        cash_runway_months=cash_runway_months,
        quality_score=0.80,
        data_quality_flags=data_quality_flags or [],
        source_map={},
        enriched_at="2026-06-01T00:00:00+00:00",
        enterprise_value_millions=enterprise_value_millions,
    )


# ---------------------------------------------------------------------------
# Sprint B — EV-based deal_size_fit
# ---------------------------------------------------------------------------

class TestDealSizeFitWithEV:
    def test_live_ev_inside_range_returns_1(self):
        # EV = 800M, range 500–2000 → perfect fit
        assert _deal_size_fit("micro", (500.0, 2000.0), enterprise_value_millions=800.0) == 1.0

    def test_live_ev_below_range(self):
        # EV = 50M, range 500–2000 → below
        score = _deal_size_fit("nano", (500.0, 2000.0), enterprise_value_millions=50.0)
        assert 0.0 <= score < 1.0

    def test_live_ev_above_range(self):
        # EV = 50_000M, range 500–10_000 → above
        score = _deal_size_fit("large", (500.0, 10000.0), enterprise_value_millions=50_000.0)
        assert 0.0 <= score < 1.0

    def test_live_ev_prefers_ev_over_bucket(self):
        # Bucket "nano" would give EV=75M → below range; live EV=1000M → inside range
        score_bucket = _deal_size_fit("nano", (500.0, 2000.0))
        score_ev = _deal_size_fit("nano", (500.0, 2000.0), enterprise_value_millions=1000.0)
        assert score_ev > score_bucket

    def test_none_ev_falls_back_to_bucket(self):
        # None EV → should use bucket "micro" = 350M
        score_bucket = _deal_size_fit("micro", (500.0, 2000.0))
        score_none = _deal_size_fit("micro", (500.0, 2000.0), enterprise_value_millions=None)
        assert score_bucket == score_none

    def test_target_with_ev_used_in_pair_scoring(self):
        """When target has enterprise_value_millions, it reaches _deal_size_fit correctly."""
        from bve.ingestion.profile_enricher import AcquirerProfileEnriched
        from bve.ingestion.evidence_ledger import EvidenceLedger

        target = _make_target(enterprise_value_millions=1200.0)
        acquirer = AcquirerProfileEnriched(
            ticker="TACQ", name="Big Pharma", cik=None,
            therapeutic_areas=["oncology"], modalities=["small_molecule"],
            deal_size_range_millions=(500.0, 5000.0), preferred_stages=["phase_2"],
            include_as_acquirer=True,
            bd_appetite=0.60, urgency=0.55, integration_capacity=0.75,
            quality_score=0.80, data_quality_flags=[], source_map={},
            enriched_at="2026-06-01T00:00:00+00:00",
        )
        screen = WeeklyMAScreen()
        result = screen.run(
            as_of_date=date(2026, 6, 1),
            targets=[target],
            acquirers=[acquirer],
            ledger=EvidenceLedger(),
            min_coverage=0.0,  # disable suppression — testing EV logic, not coverage
        )
        # Should have pair scores since EV=1200M is in range 500–5000
        assert len(result.top_acquirer_pairs) > 0
        assert result.top_acquirer_pairs[0].deal_size_fit == pytest.approx(1.0)


class TestLongTermDebtExtraction:
    def test_extract_no_debt_returns_none(self):
        assert extract_long_term_debt({}) is None

    def test_extract_from_long_term_debt_noncurrent(self):
        facts = {
            "us-gaap": {
                "LongTermDebtNoncurrent": {
                    "units": {"USD": [
                        {"form": "10-K", "val": 500_000_000, "end": "2025-12-31"},
                    ]}
                }
            }
        }
        result = extract_long_term_debt(facts)
        assert result == pytest.approx(500.0)

    def test_extract_picks_latest_filing(self):
        facts = {
            "us-gaap": {
                "LongTermDebtNoncurrent": {
                    "units": {"USD": [
                        {"form": "10-K", "val": 100_000_000, "end": "2024-12-31"},
                        {"form": "10-K", "val": 200_000_000, "end": "2025-12-31"},
                    ]}
                }
            }
        }
        result = extract_long_term_debt(facts)
        assert result == pytest.approx(200.0)


class TestProfileEnricherEV:
    def test_ev_computed_when_market_cap_fetcher_provided(self):
        """EV = market_cap + debt - cash."""
        from bve.ingestion.universe_loader import TargetEntry
        target_entry = TargetEntry(
            ticker="TEST", name="Test Corp", cik=None, exchange="NASDAQ",
            company_type="drug_developer", therapeutic_areas=["oncology"],
            lead_asset="TEST-001", lead_asset_phase="phase_2",
            lead_modality="small_molecule", lead_indication="test",
            is_single_asset_company=False, include_in_screen=True,
            market_cap_bucket="micro",
        )
        enricher = ProfileEnricher(
            targets={"TEST": target_entry},
            acquirers={},
            manual_overrides={},
            sec_fetcher=lambda ticker: {
                "cash_millions": 100.0,
                "rd_expense_millions": 50.0,
                "sgna_expense_millions": None,
                "shares_outstanding_millions": 50.0,
                "long_term_debt_millions": 200.0,
            },
            market_cap_fetcher=lambda ticker: 500.0,
        )
        profile = enricher.enrich_target("TEST")
        assert profile.market_cap_millions == pytest.approx(500.0)
        assert profile.long_term_debt_millions == pytest.approx(200.0)
        # EV = 500 + 200 - 100 = 600
        assert profile.enterprise_value_millions == pytest.approx(600.0)

    def test_ev_is_none_when_no_market_cap_fetcher(self):
        from bve.ingestion.universe_loader import TargetEntry
        target_entry = TargetEntry(
            ticker="TEST", name="Test Corp", cik=None, exchange="NASDAQ",
            company_type="drug_developer", therapeutic_areas=["oncology"],
            lead_asset="TEST-001", lead_asset_phase="phase_2",
            lead_modality="small_molecule", lead_indication="test",
            is_single_asset_company=False, include_in_screen=True,
            market_cap_bucket="micro",
        )
        enricher = ProfileEnricher(
            targets={"TEST": target_entry},
            acquirers={},
            manual_overrides={},
            sec_fetcher=lambda ticker: {
                "cash_millions": 100.0,
                "rd_expense_millions": 50.0,
                "sgna_expense_millions": None,
                "shares_outstanding_millions": 50.0,
                "long_term_debt_millions": 200.0,
            },
        )
        profile = enricher.enrich_target("TEST")
        assert profile.enterprise_value_millions is None
        assert profile.market_cap_millions is None


# ---------------------------------------------------------------------------
# Sprint C — Structured suppression reason codes
# ---------------------------------------------------------------------------

class TestSuppressionReasonCodes:
    def _run_with_zero_records(self) -> str:
        """Run screen for a target with no evidence records; return suppression_reason."""
        from bve.ingestion.evidence_ledger import EvidenceLedger

        target = _make_target(
            ticker="NOSIG",
            data_quality_flags=["cash_missing"],
        )
        screen = WeeklyMAScreen()
        result = screen.run(
            as_of_date=date(2026, 6, 1),
            targets=[target],
            acquirers=[],
            ledger=EvidenceLedger(),
            min_coverage=0.20,
        )
        assert result.suppressed_targets, "Expected target to be suppressed"
        return result.suppressed_targets[0].suppression_reason or ""

    def test_suppression_reason_contains_no_evidence_records(self):
        reason = self._run_with_zero_records()
        assert "no_evidence_records" in reason

    def test_suppression_reason_contains_cash_missing(self):
        reason = self._run_with_zero_records()
        assert "cash_missing" in reason

    def test_suppression_reason_format_parseable(self):
        reason = self._run_with_zero_records()
        # Format: "coverage:0.00<0.20 [code1,code2]"
        assert "coverage:" in reason
        assert "[" in reason and "]" in reason


# ---------------------------------------------------------------------------
# Sprint D — 5-section diligence shortlists
# ---------------------------------------------------------------------------

class TestDiligenceShortlists:
    def _make_result_with_ranked_and_suppressed(self):
        """Build a minimal WeeklyMAScreenResult with both ranked and suppressed targets."""
        from bve.intelligence.weekly_ma_screen import (
            WeeklyMAScreenResult,
            TargetScreenResult,
        )
        from datetime import date

        def _tsr(ticker, rank, ma_prob, conf, q_score, asset_q, suppressed=False):
            return TargetScreenResult(
                rank=rank, ticker=ticker, name=f"{ticker} Corp",
                ma_probability=ma_prob,
                probability_low=ma_prob - 0.05, probability_high=ma_prob + 0.05,
                confidence_label=conf,
                asset_quality=asset_q, seller_willingness=0.50,
                financing_risk=0.10, catalyst_timing=0.50, ma_attractiveness=0.50,
                evidence_coverage_overall=0.80 if not suppressed else 0.10,
                profile_quality_score=q_score,
                top_acquirer="TACQ" if not suppressed else None,
                top_acquirer_pair_score=0.75 if not suppressed else None,
                main_drivers=["asset_quality"], key_risks=[],
                suppressed=suppressed,
                suppression_reason=(
                    "coverage:0.10<0.20 [no_evidence_records]" if suppressed else None
                ),
            )

        ranked = [
            _tsr("AA", 1, 0.80, "high", 0.90, 0.85),
            _tsr("BB", 2, 0.72, "high", 0.88, 0.75),
            _tsr("CC", 3, 0.65, "medium", 0.60, 0.70),
            _tsr("DD", 4, 0.55, "low", 0.40, 0.65),
            _tsr("EE", 5, 0.48, "low", 0.35, 0.60),
        ]
        suppressed = [
            _tsr("FF", 0, 0.40, "low", 0.80, 0.78, suppressed=True),
        ]
        return WeeklyMAScreenResult(
            as_of_date=date(2026, 6, 7),
            score_mode="provisional",
            ranked_targets=ranked,
            suppressed_targets=suppressed,
            top_acquirer_pairs=[],
            diagnostics={"n_pair_scores": 0, "n_targets_input": 6},
        )

    def test_diligence_shortlists_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "## Diligence Shortlists" in md

    def test_highest_ma_score_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "### Highest ma_score" in md

    def test_highest_confidence_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "### Highest Confidence" in md

    def test_best_buyer_fit_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "### Best Buyer Fit" in md

    def test_biggest_data_gaps_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "### Biggest Data Gaps" in md

    def test_suppressed_but_strategic_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "### Suppressed But Strategic" in md

    def test_suppressed_ticker_appears_in_strategic_shortlist(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        # FF has highest asset_quality among suppressed → should appear
        assert "FF" in md.split("### Suppressed But Strategic")[1].split("##")[0]

    def test_coverage_recovery_queue_section_present(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        assert "## Coverage Recovery Queue" in md

    def test_coverage_recovery_queue_contains_action(self):
        result = self._make_result_with_ranked_and_suppressed()
        gen = WeeklyReportGenerator()
        md = gen.generate_markdown(result)
        crq_section = md.split("## Coverage Recovery Queue")[1].split("##")[0]
        assert "Seed with CT.gov" in crq_section or "evidence" in crq_section.lower()


# ---------------------------------------------------------------------------
# Sprint E — Historical calibration runner
# ---------------------------------------------------------------------------

class TestCalibrationRunner:
    def test_load_cases_returns_list(self):
        from bve.intelligence.calibration_runner import load_cases
        cases = load_cases()
        assert isinstance(cases, list)
        assert len(cases) > 0

    def test_cases_have_layer1_score(self):
        from bve.intelligence.calibration_runner import load_cases
        cases = load_cases()
        scored = [c for c in cases if c.layer1_snapshot.get("layer1_score") is not None]
        assert len(scored) > 50  # well above N=30 threshold

    def test_layer1_score_in_valid_range(self):
        from bve.intelligence.calibration_runner import load_cases
        cases = load_cases()
        for c in cases[:20]:
            score = c.layer1_snapshot.get("layer1_score")
            if score is not None:
                assert 0.0 <= score <= 1.0

    def test_run_calibration_returns_artifact_and_report(self):
        from bve.intelligence.calibration_runner import run_historical_calibration
        artifact, report = run_historical_calibration()
        assert artifact is not None
        assert report is not None

    def test_calibration_status_not_insufficient_data(self):
        """N=325 >> 30 minimum; should not be insufficient_data."""
        from bve.intelligence.calibration_runner import run_historical_calibration
        _, report = run_historical_calibration()
        assert report.calibration_status != "insufficient_data"

    def test_report_has_positive_and_negative_cases(self):
        from bve.intelligence.calibration_runner import run_historical_calibration
        _, report = run_historical_calibration()
        assert report.n_positive > 0
        assert report.n_negative > 0

    def test_report_summary_is_string(self):
        from bve.intelligence.calibration_runner import run_historical_calibration
        _, report = run_historical_calibration()
        summary = report.summary()
        assert isinstance(summary, str)
        assert "Calibration Run" in summary

    def test_artifact_has_platt_params(self):
        from bve.intelligence.calibration_runner import run_historical_calibration
        artifact, _ = run_historical_calibration()
        # Should have fitted Platt params when N > 30
        assert artifact.platt_intercept is not None
        assert artifact.platt_slope is not None

    def test_base_rate_reasonable(self):
        """Historical M&A base rate should be between 5% and 70%."""
        from bve.intelligence.calibration_runner import run_historical_calibration
        _, report = run_historical_calibration()
        if report.base_rate is not None:
            assert 0.05 <= report.base_rate <= 0.70

    def test_catalyst_timing_score_neutral_when_none(self):
        from bve.intelligence.calibration_runner import _catalyst_timing_score
        assert _catalyst_timing_score(None) == 0.50

    def test_catalyst_timing_score_high_when_imminent(self):
        from bve.intelligence.calibration_runner import _catalyst_timing_score
        assert _catalyst_timing_score(0) == pytest.approx(1.0)

    def test_catalyst_timing_score_low_when_far(self):
        from bve.intelligence.calibration_runner import _catalyst_timing_score
        assert _catalyst_timing_score(365) == pytest.approx(0.0)

    def test_compute_raw_score_midpoint_for_neutral_inputs(self):
        from bve.intelligence.calibration_runner import _compute_raw_ma_score, _sigmoid
        # All neutral inputs (0.50) → ma_score should be close to sigmoid(-2 + 4*0.5*0.65 + ...)
        score = _compute_raw_ma_score(0.50, 0.50, 0.50, None)
        assert 0.0 < score < 1.0

    def test_higher_quality_gives_higher_raw_score(self):
        from bve.intelligence.calibration_runner import _compute_raw_ma_score
        low = _compute_raw_ma_score(0.20, 0.30, 0.30, None)
        high = _compute_raw_ma_score(0.90, 0.80, 0.85, 30)
        assert high > low

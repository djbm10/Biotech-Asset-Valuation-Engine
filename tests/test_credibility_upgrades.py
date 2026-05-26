"""
Tests for credibility upgrades:
  1. XBI-adjusted alpha in ReplaySummary
  2. model_pos + pos_comparison_text in ValuationOutput
  3. Staleness warnings
  4. Prediction log
  5. Score drivers / suppressors on MAProbabilityRow
"""
from __future__ import annotations

import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. XBI-adjusted alpha — ReplaySummary
# ---------------------------------------------------------------------------

class TestReplaySummaryAlpha:
    def _make_summary(self, **kwargs):
        from bve.intelligence.replay_summary import ReplaySummary
        defaults = dict(
            run_id="test-run",
            start_date=date(2021, 1, 1),
            end_date=date(2022, 1, 1),
            strategy_version="top2_add",
            score_version="v1.5",
        )
        defaults.update(kwargs)
        return ReplaySummary(**defaults)

    def test_alpha_fields_exist(self):
        """ReplaySummary must have the three new alpha fields."""
        from bve.intelligence.replay_summary import ReplaySummary
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(ReplaySummary)}
        assert "mean_xbi_return_pct" in field_names
        assert "mean_alpha_pct" in field_names
        assert "alpha_hit_rate" in field_names
        assert "n_with_xbi_data" in field_names

    def test_alpha_fields_default_none(self):
        s = self._make_summary()
        assert s.mean_xbi_return_pct is None
        assert s.mean_alpha_pct is None
        assert s.alpha_hit_rate is None
        assert s.n_with_xbi_data == 0

    def test_alpha_computed_correctly(self):
        """mean_alpha = mean_return - mean_xbi_return."""
        s = self._make_summary(
            mean_return_pct=5.0,
            mean_xbi_return_pct=2.0,
            mean_alpha_pct=3.0,
        )
        assert s.mean_alpha_pct == pytest.approx(3.0)

    def test_alpha_hit_rate_stored(self):
        s = self._make_summary(alpha_hit_rate=0.6, n_with_xbi_data=10)
        assert s.alpha_hit_rate == pytest.approx(0.6)
        assert s.n_with_xbi_data == 10

    def test_to_dict_includes_alpha_fields(self):
        s = self._make_summary(
            mean_xbi_return_pct=1.5,
            mean_alpha_pct=3.5,
            alpha_hit_rate=0.55,
            n_with_xbi_data=20,
        )
        d = s.to_dict()
        assert d["mean_xbi_return_pct"] == pytest.approx(1.5)
        assert d["mean_alpha_pct"] == pytest.approx(3.5)
        assert d["alpha_hit_rate"] == pytest.approx(0.55)
        assert d["n_with_xbi_data"] == 20

    def test_to_dict_alpha_none_when_not_computed(self):
        s = self._make_summary()
        d = s.to_dict()
        assert d["mean_xbi_return_pct"] is None
        assert d["mean_alpha_pct"] is None
        assert d["alpha_hit_rate"] is None

    def test_summarize_computes_alpha_from_decisions(self, tmp_path):
        """HistoricalReplay.summarize() populates alpha fields from xbi_return_during_hold."""
        from bve.ops.historical_replay import ReplayStore
        from bve.intelligence.replay_policy import ReplayDecision
        db = str(tmp_path / "test.sqlite")
        rs = ReplayStore(db)
        run_id = rs.create_run(
            start_date=date(2021, 1, 1),
            end_date=date(2022, 1, 1),
            cadence="weekly",
            decision_policy="top2_add",
            score_version="v1.5",
            strategy_version="top2_add",
        )
        # Insert 3 closed decisions with xbi data:
        # decision 1: return=+10%, xbi=+3%  → alpha=+7% (alpha hit)
        # decision 2: return=+2%,  xbi=+5%  → alpha=-3% (no alpha hit)
        # decision 3: return=-4%,  xbi=-8%  → alpha=+4% (alpha hit)
        decisions = [
            ("a-asset1", "T1", date(2021, 2, 1), "add", 0.65, 100.0, 10.0, +3.0),
            ("a-asset2", "T2", date(2021, 3, 1), "add", 0.60, 50.0,  2.0, +5.0),
            ("a-asset3", "T3", date(2021, 4, 1), "add", 0.55, 80.0, -4.0, -8.0),
        ]
        for asset_id, ticker, decided_at, action, score, ep, ret, xbi in decisions:
            rd = ReplayDecision(
                asset_id=asset_id, ticker=ticker,
                recommended_action=action, recommended_size_pct=0.5,
                composite_score=score, decided_at=decided_at,
            )
            rs.insert_decision(run_id=run_id, decision=rd, entry_price=ep)
        # Close them with return data
        open_decisions = rs.get_open_decisions(run_id)
        for idx, d in enumerate(open_decisions):
            rs.close_decision(
                decision_id=d["decision_id"],
                exit_date=date(2021, 6, 1),
                exit_price=100.0,
                return_pct=decisions[idx][6],
                attribution_type="market_drift",
                xbi_return_during_hold=decisions[idx][7],
            )

        from bve.ops.historical_replay import HistoricalReplay
        from bve.ops.universe_data import UNIVERSE

        runner = HistoricalReplay(
            replay_store=rs,
            knowledge_store_path=":memory:",
            universe=UNIVERSE[:5],
        )
        summary = runner.summarize(run_id)

        # mean_xbi = (3 + 5 - 8) / 3 = 0.0
        assert summary.n_with_xbi_data == 3
        assert summary.mean_xbi_return_pct == pytest.approx(0.0, abs=0.01)
        # mean_return = (10 + 2 - 4) / 3 = 2.667
        # mean_alpha = mean_return - mean_xbi = 2.667 - 0.0 = 2.667
        assert summary.mean_alpha_pct == pytest.approx(2.667, abs=0.01)
        # alpha_hit_rate: decisions 1 and 3 have positive alpha → 2/3
        assert summary.alpha_hit_rate == pytest.approx(2 / 3, abs=0.01)

    def test_summarize_alpha_none_when_no_xbi_data(self, tmp_path):
        """If no decisions have xbi data, alpha fields are None."""
        from bve.ops.historical_replay import ReplayStore, HistoricalReplay
        from bve.intelligence.replay_policy import ReplayDecision
        from bve.ops.universe_data import UNIVERSE
        db = str(tmp_path / "test2.sqlite")
        rs = ReplayStore(db)
        run_id = rs.create_run(
            start_date=date(2021, 1, 1),
            end_date=date(2022, 1, 1),
            cadence="weekly",
            decision_policy="top2_add",
            score_version="v1.5",
            strategy_version="top2_add",
        )
        rd = ReplayDecision(
            asset_id="a-x", ticker="XX",
            recommended_action="add", recommended_size_pct=0.5,
            composite_score=0.6, decided_at=date(2021, 2, 1),
        )
        rs.insert_decision(run_id=run_id, decision=rd, entry_price=100.0)
        open_d = rs.get_open_decisions(run_id)
        rs.close_decision(
            decision_id=open_d[0]["decision_id"],
            exit_date=date(2021, 6, 1),
            exit_price=105.0,
            return_pct=5.0,
            attribution_type="market_drift",
            xbi_return_during_hold=None,  # no xbi data
        )
        runner = HistoricalReplay(replay_store=rs, knowledge_store_path=":memory:", universe=UNIVERSE[:5])
        summary = runner.summarize(run_id)
        assert summary.mean_xbi_return_pct is None
        assert summary.mean_alpha_pct is None
        assert summary.alpha_hit_rate is None
        assert summary.n_with_xbi_data == 0


# ---------------------------------------------------------------------------
# 2. model_pos + pos_comparison_text in ValuationOutput
# ---------------------------------------------------------------------------

class TestValuationOutputPOSSurface:
    def _make_output(self, *, current_price=None, implied_pos=None, pos_gap=None,
                     mispricing_direction="aligned", mispricing_magnitude="none",
                     model_pos=0.65):
        """Build a minimal ValuationOutput-like mock to test summary_dict and property."""
        from bve.valuation.outputs import ValuationOutput, SensitivityPoint
        from bve.entities.asset import Asset, Modality, DevelopmentStage as Stage, TherapeuticArea
        from bve.entities.company import Company
        from bve.entities.trial import ClinicalTrial, TrialPhase
        from bve.models.market_model import MarketModel
        from bve.models.rnpv_model import RNPVResult
        from bve.models.monte_carlo import MonteCarloResult
        from bve.valuation.scenario import ScenarioSet, ScenarioResult
        from bve.expectations.market_implied_pos import ImpliedPoSResult

        asset = Asset(
            id="a-test", name="TestDrug", indication="TestInd",
            therapeutic_area=TherapeuticArea.ONCOLOGY, stage=Stage.PHASE_3,
            modality=Modality.SMALL_MOLECULE, mechanism_of_action="test",
        )
        company = Company(
            id="co-test", name="TestCo", ticker="TST",
            cash_millions=200.0, debt_millions=0.0,
            shares_outstanding_millions=50.0,
            current_price=current_price,
        )
        trial = ClinicalTrial(
            asset_id="a-test", phase=TrialPhase.PHASE_3,
            success_probability=model_pos, duration_years=2.0, cost_millions=50.0,
        )
        mm = MarketModel(
            asset_id="a-test", addressable_patients_annual=100_000,
            net_price_per_patient_usd=20_000, peak_penetration=0.10,
            patent_life_years=10, years_to_peak=5,
        )
        rnpv = RNPVResult(
            asset_id="a-test", asset_name="TestDrug",
            rnpv_millions=200.0, peak_sales_millions=500.0,
            cumulative_success_probability=model_pos,
            probability_adjusted_revenue_pv_millions=model_pos * 1000.0,
            years_to_launch=3.0, discount_rate=0.10, net_ownership=1.0,
            gross_revenue_pv_millions=1000.0, trial_costs_pv_millions=50.0,
        )
        mc = MonteCarloResult(
            asset_id="a-test",
            mean_millions=200.0, std_millions=100.0,
            median_millions=190.0,
            percentile_5_millions=50.0, percentile_10_millions=75.0,
            percentile_25_millions=125.0, percentile_50_millions=190.0,
            percentile_75_millions=275.0, percentile_90_millions=350.0,
            percentile_95_millions=420.0,
            probability_positive=0.70, probability_above_500m=0.15,
            probability_above_1b=0.05,
            n_simulations=1000,
            simulated_values_millions=[200.0] * 1000,
        )
        scenario_r = ScenarioResult(
            label="base", description="Base scenario",
            rnpv_millions=200.0, peak_sales_millions=500.0,
            years_to_launch=3.0,
            nav_millions=400.0, nav_per_share=8.0,
            cumulative_success_probability=model_pos,
        )
        scenarios = ScenarioSet(bull=scenario_r, base=scenario_r, bear=scenario_r)

        market_exp = None
        if current_price is not None and implied_pos is not None:
            market_exp = ImpliedPoSResult(
                asset_id="a-test", ticker="TST", as_of_date=date.today(),
                current_ev_millions=current_price * 50.0,
                net_cash_millions=200.0,
                pipeline_ev_millions=(current_price * 50.0) - 200.0,
                model_peak_sales_millions=500.0,
                model_pos=model_pos,
                gross_revenue_pv_millions=1000.0,
                trial_costs_pv_millions=50.0,
                implied_pos=implied_pos,
                implied_peak_sales_millions=500.0 * implied_pos / model_pos,
                pos_gap=pos_gap if pos_gap is not None else (model_pos - implied_pos),
                peak_sales_gap_millions=0.0,
                mispricing_direction=mispricing_direction,
                mispricing_magnitude=mispricing_magnitude,
            )

        return ValuationOutput(
            asset=asset, company=company, trials=[trial], market_model=mm,
            rnpv=rnpv, scenarios=scenarios, monte_carlo=mc,
            nav_millions=400.0, nav_per_share=8.0,
            market_expectation=market_exp,
        )

    def test_summary_dict_has_model_pos(self):
        out = self._make_output(model_pos=0.65)
        d = out.summary_dict
        assert "model_pos" in d
        assert d["model_pos"] == pytest.approx(0.65)

    def test_summary_dict_model_pos_matches_rnpv(self):
        out = self._make_output(model_pos=0.42)
        assert out.summary_dict["model_pos"] == pytest.approx(0.42)

    def test_pos_comparison_text_none_without_price(self):
        out = self._make_output(current_price=None)
        assert out.pos_comparison_text is None

    def test_pos_comparison_text_none_without_market_expectation(self):
        out = self._make_output(current_price=None, implied_pos=None)
        assert out.pos_comparison_text is None

    def test_pos_comparison_text_present_with_price(self):
        out = self._make_output(
            current_price=10.0, model_pos=0.65, implied_pos=0.42,
            mispricing_direction="underpriced", mispricing_magnitude="moderate",
        )
        text = out.pos_comparison_text
        assert text is not None
        assert "65%" in text
        assert "42%" in text
        assert "underpriced" in text.lower()

    def test_pos_comparison_text_shows_gap(self):
        out = self._make_output(
            current_price=10.0, model_pos=0.65, implied_pos=0.42,
            pos_gap=0.23,
            mispricing_direction="underpriced", mispricing_magnitude="moderate",
        )
        text = out.pos_comparison_text
        # Gap should be +23pp
        assert "+23" in text or "+23.0" in text

    def test_pos_comparison_text_overpriced(self):
        out = self._make_output(
            current_price=20.0, model_pos=0.40, implied_pos=0.65,
            pos_gap=-0.25,
            mispricing_direction="overpriced", mispricing_magnitude="large",
        )
        text = out.pos_comparison_text
        assert text is not None
        assert "overpriced" in text.lower()

    def test_pos_comparison_text_in_summary_dict(self):
        out = self._make_output(
            current_price=10.0, model_pos=0.65, implied_pos=0.42,
            mispricing_direction="underpriced", mispricing_magnitude="moderate",
        )
        d = out.summary_dict
        assert "pos_comparison_text" in d
        assert d["pos_comparison_text"] is not None

    def test_summary_dict_pos_comparison_none_without_price(self):
        out = self._make_output(current_price=None)
        assert out.summary_dict.get("pos_comparison_text") is None


# ---------------------------------------------------------------------------
# 3. Staleness warnings
# ---------------------------------------------------------------------------

class TestStalenessWarnings:
    def test_no_warning_when_fresh(self):
        from bve.utils.staleness import check_financial_staleness
        fresh = date.today() - timedelta(days=10)
        result = check_financial_staleness(fresh)
        assert result is None

    def test_warning_after_60_days_financial(self):
        from bve.utils.staleness import check_financial_staleness, StalenessWarning
        stale = date.today() - timedelta(days=65)
        result = check_financial_staleness(stale)
        assert result is not None
        assert isinstance(result, StalenessWarning)
        assert result.age_days == 65
        assert result.threshold_days == 60
        assert result.field == "financial_data"

    def test_no_warning_acquirer_profile_within_90(self):
        from bve.utils.staleness import check_profile_staleness
        fresh = date.today() - timedelta(days=45)
        assert check_profile_staleness(fresh) is None

    def test_warning_acquirer_profile_after_90_days(self):
        from bve.utils.staleness import check_profile_staleness, StalenessWarning
        stale = date.today() - timedelta(days=95)
        result = check_profile_staleness(stale)
        assert result is not None
        assert result.threshold_days == 90
        assert result.field == "acquirer_profile"

    def test_severity_warning_just_over_threshold(self):
        from bve.utils.staleness import check_financial_staleness
        stale = date.today() - timedelta(days=70)
        result = check_financial_staleness(stale)
        assert result is not None
        assert result.severity == "warning"

    def test_severity_critical_double_threshold(self):
        from bve.utils.staleness import check_financial_staleness
        stale = date.today() - timedelta(days=130)  # > 2 × 60
        result = check_financial_staleness(stale)
        assert result is not None
        assert result.severity == "critical"

    def test_check_staleness_generic(self):
        from bve.utils.staleness import check_staleness
        stale = date.today() - timedelta(days=40)
        result = check_staleness(stale, field="custom_field", threshold_days=30)
        assert result is not None
        assert result.field == "custom_field"
        assert result.age_days == 40
        assert result.threshold_days == 30

    def test_staleness_message_is_human_readable(self):
        from bve.utils.staleness import check_financial_staleness
        stale = date.today() - timedelta(days=90)
        result = check_financial_staleness(stale)
        assert result is not None
        assert "financial_data" in result.message
        assert "90" in result.message

    def test_staleness_warning_at_exactly_threshold(self):
        """At exactly the threshold, no warning should be raised."""
        from bve.utils.staleness import check_financial_staleness
        exactly = date.today() - timedelta(days=60)
        result = check_financial_staleness(exactly)
        assert result is None

    def test_staleness_warning_one_past_threshold(self):
        from bve.utils.staleness import check_financial_staleness
        one_past = date.today() - timedelta(days=61)
        result = check_financial_staleness(one_past)
        assert result is not None

    def test_check_staleness_returns_none_for_today(self):
        from bve.utils.staleness import check_staleness
        result = check_staleness(date.today(), field="test", threshold_days=30)
        assert result is None


# ---------------------------------------------------------------------------
# 4. Prediction log
# ---------------------------------------------------------------------------

class TestPredictionLog:
    def _make_log(self, tmp_path) -> "PredictionLog":
        from bve.ops.prediction_log import PredictionLog
        return PredictionLog(str(tmp_path / "pred.db"))

    def test_create_and_read_entry(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, PredictionLogEntry
        log = self._make_log(tmp_path)
        entry = PredictionLogEntry(
            logged_at="2025-01-01T10:00:00",
            log_type="ma_score",
            asset_id="a-test",
            ticker="TST",
            score=0.75,
            confidence=0.60,
            notes="best acquirer: roche",
        )
        entry_id = log.log(entry)
        assert entry_id > 0

    def test_unresolved_returns_entry(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, PredictionLogEntry
        log = self._make_log(tmp_path)
        log.log(PredictionLogEntry(
            logged_at="2025-01-01T10:00:00",
            log_type="ma_score",
            asset_id="a-x",
            ticker="XX",
            score=0.72,
            confidence=0.55,
            notes="test",
        ))
        unresolved = log.unresolved()
        assert len(unresolved) == 1
        assert unresolved[0]["asset_id"] == "a-x"
        assert unresolved[0]["outcome"] is None

    def test_resolve_entry(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, PredictionLogEntry
        log = self._make_log(tmp_path)
        entry_id = log.log(PredictionLogEntry(
            logged_at="2025-01-01T10:00:00",
            log_type="ma_score",
            asset_id="a-y",
            ticker="YY",
            score=0.80,
            confidence=0.70,
            notes="",
        ))
        log.resolve(entry_id, outcome="correct", outcome_notes="acquired by Roche at $2B")
        unresolved = log.unresolved()
        assert len(unresolved) == 0

    def test_summary_stats(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, PredictionLogEntry
        log = self._make_log(tmp_path)
        for i, outcome in enumerate([None, "correct", "wrong", "correct"]):
            eid = log.log(PredictionLogEntry(
                logged_at=f"2025-0{i+1}-01T10:00:00",
                log_type="ma_score",
                asset_id=f"a-{i}",
                ticker=f"T{i}",
                score=0.70,
                confidence=None,
                notes="",
            ))
            if outcome is not None:
                log.resolve(eid, outcome=outcome)
        stats = log.summary()
        assert stats["total"] == 4
        assert stats["resolved"] == 3
        assert stats["unresolved"] == 1
        assert stats["correct"] == 2
        assert stats["accuracy"] == pytest.approx(2 / 3)

    def test_log_ma_score_factory(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, log_ma_score
        log = self._make_log(tmp_path)
        eid = log_ma_score(
            log, asset_id="a-z", ticker="ZZ",
            score=0.77, p_takeout=0.35, acquirer="merck",
        )
        assert eid > 0
        rows = log.unresolved(log_type="ma_score")
        assert len(rows) == 1
        assert "merck" in rows[0]["notes"]

    def test_log_mispricing_factory(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, log_mispricing
        log = self._make_log(tmp_path)
        eid = log_mispricing(
            log, asset_id="a-w", ticker="WW",
            model_pos=0.68, implied_pos=0.42, pos_gap=0.26,
            direction="underpriced",
        )
        assert eid > 0
        rows = log.unresolved(log_type="mispricing")
        assert len(rows) == 1
        assert "0.68" in rows[0]["notes"]
        assert "underpriced" in rows[0]["notes"]

    def test_filter_unresolved_by_type(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, PredictionLogEntry
        log = self._make_log(tmp_path)
        log.log(PredictionLogEntry(
            logged_at="2025-01-01T10:00:00", log_type="ma_score",
            asset_id="a-1", ticker="T1", score=0.70, confidence=None, notes="",
        ))
        log.log(PredictionLogEntry(
            logged_at="2025-01-02T10:00:00", log_type="mispricing",
            asset_id="a-2", ticker="T2", score=0.25, confidence=None, notes="",
        ))
        ma_only = log.unresolved(log_type="ma_score")
        assert len(ma_only) == 1
        assert ma_only[0]["log_type"] == "ma_score"

    def test_by_type_in_summary(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog, PredictionLogEntry
        log = self._make_log(tmp_path)
        for t in ["ma_score", "ma_score", "mispricing"]:
            log.log(PredictionLogEntry(
                logged_at="2025-01-01T10:00:00", log_type=t,
                asset_id="a-x", ticker="X", score=0.5, confidence=None, notes="",
            ))
        stats = log.summary()
        assert stats["by_type"]["ma_score"] == 2
        assert stats["by_type"]["mispricing"] == 1

    def test_empty_log_summary(self, tmp_path):
        from bve.ops.prediction_log import PredictionLog
        log = self._make_log(tmp_path)
        stats = log.summary()
        assert stats["total"] == 0
        assert stats["accuracy"] is None

    def test_idempotent_schema_creation(self, tmp_path):
        """Creating PredictionLog twice on same DB should not error."""
        from bve.ops.prediction_log import PredictionLog
        db = str(tmp_path / "idempotent.db")
        PredictionLog(db)
        PredictionLog(db)  # should not raise


# ---------------------------------------------------------------------------
# 5. Score drivers and suppressors on MAProbabilityRow
# ---------------------------------------------------------------------------

class TestScoreDriversSuppressors:
    def _make_row(self, **kwargs) -> "MAProbabilityRow":
        from bve.intelligence.ma_probability import MAProbabilityRow
        defaults = dict(
            asset_id="a-test",
            company_id="co-test",
            ticker="TST",
            mna_probability_score=0.65,
            p_acquisition=0.65,
            raw_probability=0.65,
            above_alert_threshold=True,
            score_version="v1.5",
            best_acquirer_id="roche",
            best_acquirer_name="Roche",
            best_acquirer_fit_score=0.70,
            valuation_discount_score=0.50,
            strategic_fit_score=0.50,
            de_risking_stage_score=0.50,
            capital_vulnerability_score=0.50,
            scarcity_score=0.50,
            scarcity_peer_count=3,
            scarcity_bucket="moderate",
            vulnerability_score=0.40,
            target_signal_score=0.0,
            external_deal_pressure_score=0.0,
            explanation="test",
        )
        defaults.update(kwargs)
        return MAProbabilityRow(**defaults)

    def test_fields_exist(self):
        from bve.intelligence.ma_probability import MAProbabilityRow
        row = self._make_row()
        assert hasattr(row, "score_drivers")
        assert hasattr(row, "score_suppressors")
        assert isinstance(row.score_drivers, list)
        assert isinstance(row.score_suppressors, list)

    def test_high_strategic_fit_is_driver(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(strategic_fit_score=0.82)
        row = compute_score_drivers_suppressors(row)
        assert any("strategic" in d.lower() for d in row.score_drivers)

    def test_high_capital_vulnerability_is_driver(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(capital_vulnerability_score=0.80)
        row = compute_score_drivers_suppressors(row)
        assert any("capital" in d.lower() for d in row.score_drivers)

    def test_high_scarcity_is_driver(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(scarcity_score=0.78)
        row = compute_score_drivers_suppressors(row)
        assert any("scarcit" in d.lower() for d in row.score_drivers)

    def test_low_strategic_fit_is_suppressor(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(strategic_fit_score=0.22)
        row = compute_score_drivers_suppressors(row)
        assert any("strategic" in s.lower() for s in row.score_suppressors)

    def test_low_derisking_is_suppressor(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(de_risking_stage_score=0.18)
        row = compute_score_drivers_suppressors(row)
        assert any("derisking" in s.lower() or "de-risk" in s.lower() or "stage" in s.lower()
                   for s in row.score_suppressors)

    def test_max_3_drivers(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(
            strategic_fit_score=0.90,
            capital_vulnerability_score=0.85,
            de_risking_stage_score=0.80,
            valuation_discount_score=0.75,
            scarcity_score=0.70,
        )
        row = compute_score_drivers_suppressors(row)
        assert len(row.score_drivers) <= 3

    def test_max_2_suppressors(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(
            strategic_fit_score=0.10,
            capital_vulnerability_score=0.15,
            de_risking_stage_score=0.20,
            valuation_discount_score=0.25,
        )
        row = compute_score_drivers_suppressors(row)
        assert len(row.score_suppressors) <= 2

    def test_no_drivers_when_all_moderate(self):
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(
            strategic_fit_score=0.50,
            capital_vulnerability_score=0.50,
            de_risking_stage_score=0.50,
            valuation_discount_score=0.50,
            scarcity_score=0.50,
        )
        row = compute_score_drivers_suppressors(row)
        assert len(row.score_drivers) == 0

    def test_compute_returns_new_row_immutable(self):
        """compute_score_drivers_suppressors must return a new row, not mutate."""
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(strategic_fit_score=0.85)
        row2 = compute_score_drivers_suppressors(row)
        assert row is not row2
        # Original unchanged
        assert row.score_drivers == []

    def test_drivers_suppressors_serialise(self):
        """Fields survive model_dump round-trip."""
        from bve.intelligence.ma_probability import compute_score_drivers_suppressors
        row = self._make_row(strategic_fit_score=0.85, de_risking_stage_score=0.20)
        row = compute_score_drivers_suppressors(row)
        d = row.model_dump()
        assert isinstance(d["score_drivers"], list)
        assert isinstance(d["score_suppressors"], list)

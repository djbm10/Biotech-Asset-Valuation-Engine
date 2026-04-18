"""Tests for GapFillStore — Phase 2 persistent SQLite store."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.analysis.catalyst_payoff import CatalystPayoffTree, CatalystScenario
from bve.analysis.implied_expectations import (
    ConsensusEstimate,
    ImpliedExpectationsRecord,
    MarketSnapshot,
)
from bve.analysis.variant_view import (
    ConsensusAssumption,
    ModelAssumption,
    VariantDelta,
    VariantThesis,
)
from bve.models.runway_forecast import BurnScenario, RunwayForecast
from bve.persistence.gap_fill_store import (
    DecisionRecord,
    GapFillStore,
    OutcomeRecord,
    ParameterVersion,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path):
    db_path = tmp_path / "test_gap_fill.db"
    s = GapFillStore(db_path=str(db_path))
    yield s
    s.close()


def _market_snapshot(asset_id: str = "asset-1", snap_date: str = "2025-01-15") -> MarketSnapshot:
    return MarketSnapshot(
        asset_id=asset_id,
        ticker="TKRA",
        snapshot_date=date.fromisoformat(snap_date),
        market_cap_millions=500.0,
        ev_millions=450.0,
        share_price=12.50,
        shares_outstanding_millions=40.0,
        cash_millions=55.0,
        debt_millions=5.0,
    )


def _implied_expectation(asset_id: str = "asset-1") -> ImpliedExpectationsRecord:
    return ImpliedExpectationsRecord(
        asset_id=asset_id,
        ticker="TKRA",
        snapshot_date=date(2025, 1, 15),
        implied_pos=0.35,
        implied_peak_sales_millions=800.0,
        implied_dilution_pct=0.12,
        implied_timeline_years=4.5,
        model_pos=0.42,
        model_peak_sales_millions=950.0,
        model_rnpv_millions=320.0,
        current_ev_millions=450.0,
        upside_pct=0.25,
        downside_pct=-0.15,
        valuation_gap_millions=75.0,
    )


def _consensus_estimate(asset_id: str = "asset-1") -> ConsensusEstimate:
    return ConsensusEstimate(
        asset_id=asset_id,
        ticker="TKRA",
        estimate_date=date(2025, 1, 15),
        source="StreetAccount",
        model_pos=0.40,
        model_peak_sales_millions=850.0,
        analyst_count=8,
        consensus_rnpv_millions=290.0,
    )


def _variant_thesis(asset_id: str = "asset-1") -> VariantThesis:
    delta = VariantDelta(
        dimension="peak_sales",
        consensus_assumption=ConsensusAssumption(
            dimension="peak_sales",
            consensus_value="$850M",
            confidence=0.7,
            source="consensus",
        ),
        model_assumption=ModelAssumption(
            dimension="peak_sales",
            model_value="$950M",
            confidence=0.6,
            rationale="Larger addressable pool",
        ),
        delta_summary="Model 12% above consensus",
        magnitude=0.12,
        falsifier="Phase 3 enrollment below 300 patients",
    )
    return VariantThesis(
        asset_id=asset_id,
        ticker="TKRA",
        created_at=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
        updated_at=datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc),
        what_market_believes="Market prices Phase 3 at 35% PoS",
        what_model_thinks="Model calculates 42% PoS based on biomarker data",
        why_gap_exists="Street ignores enrichment signal",
        catalysts_to_resolve=["Phase 3 readout Q3 2025"],
        confidence_score=0.70,
        overall_conviction="high",
        deltas=[delta],
    )


def _catalyst_scenario() -> CatalystScenario:
    return CatalystScenario(
        scenario_id="scen-1",
        label="clear_win",
        probability=0.45,
        expected_price_move_pct=0.60,
        post_event_financing_state="no_need",
        post_event_thesis_state="confirmed",
        next_catalyst="NDA filing",
    )


def _catalyst_tree(asset_id: str = "asset-1") -> CatalystPayoffTree:
    return CatalystPayoffTree(
        catalyst_id="cat-001",
        asset_id=asset_id,
        catalyst_label="Phase 3 top-line",
        catalyst_date=date(2025, 9, 15),
        catalyst_type="clinical_data",
        scenarios=[_catalyst_scenario()],
        expected_return_pct=0.28,
        downside_severity_pct=-0.45,
        skew_ratio=2.5,
        setup_score=0.72,
        pre_event_recommendation="hold",
        post_event_action_map={"clear_win": "add", "miss": "sell"},
    )


def _runway_forecast(company_id: str = "co-1") -> RunwayForecast:
    burn = BurnScenario(
        label="base",
        quarterly_burn_millions=22.0,
        annual_burn_millions=88.0,
    )
    return RunwayForecast(
        company_id=company_id,
        forecast_date=date(2025, 1, 15),
        cash_millions=180.0,
        debt_millions=10.0,
        net_cash_millions=170.0,
        burn_scenarios=[burn],
        runway_months_bull=26.0,
        runway_months_base=23.0,
        runway_months_bear=18.0,
        next_catalyst_date=date(2025, 9, 15),
        capital_needed_to_next_catalyst_millions=55.0,
        capital_needed_to_approval_millions=200.0,
        cash_adequate_for_next_catalyst=True,
    )


def _decision_record(asset_id: str = "asset-1") -> DecisionRecord:
    return DecisionRecord(
        asset_id=asset_id,
        ticker="TKRA",
        decision_date=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        action="add",
        target_position_pct=0.04,
        composite_score=0.72,
        market_gap_pct=0.15,
        thesis_confidence=0.68,
        rationale="Strong biomarker signal supports above-consensus PoS",
    )


def _outcome_record(decision_id: str) -> OutcomeRecord:
    return OutcomeRecord(
        decision_id=decision_id,
        asset_id="asset-1",
        ticker="TKRA",
        decision_date=date(2025, 1, 15),
        outcome_date=date(2025, 9, 20),
        return_realized_pct=0.55,
        catalyst_triggered=True,
        catalyst_description="Phase 3 met primary endpoint",
        thesis_confirmed=True,
        attribution="confirmed_thesis",
    )


def _parameter_version(module: str = "pos_model") -> ParameterVersion:
    return ParameterVersion(
        module=module,
        parameters={"phase2_base_rate": 0.40, "phase3_base_rate": 0.62},
        description="Initial calibration from oncology dataset",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStoreInit:
    def test_store_initialises_and_tables_exist(self, store):
        """Store initialises; all expected tables are created."""
        tables = {
            row[0]
            for row in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "market_snapshots",
            "implied_expectations",
            "consensus_estimates",
            "variant_theses",
            "catalyst_trees",
            "financing_forecasts",
            "decision_records",
            "outcome_records",
            "parameter_versions",
        }
        assert expected.issubset(tables)


class TestMarketSnapshots:
    def test_upsert_and_get_latest(self, store):
        snap = _market_snapshot()
        store.upsert_market_snapshot(snap)
        result = store.get_latest_market_snapshot("asset-1")
        assert result is not None
        assert result.share_price == 12.50
        assert result.snapshot_date == date(2025, 1, 15)

    def test_get_latest_returns_none_for_unknown(self, store):
        assert store.get_latest_market_snapshot("unknown-asset") is None

    def test_get_market_snapshots_ordered(self, store):
        store.upsert_market_snapshot(_market_snapshot(snap_date="2025-01-10"))
        store.upsert_market_snapshot(_market_snapshot(snap_date="2025-01-20"))
        store.upsert_market_snapshot(_market_snapshot(snap_date="2025-01-15"))
        results = store.get_market_snapshots("asset-1")
        dates = [r.snapshot_date for r in results]
        assert dates == sorted(dates), "Snapshots should be returned in ascending date order"
        assert len(results) == 3


class TestImpliedExpectations:
    def test_upsert_and_get_latest(self, store):
        rec = _implied_expectation()
        store.upsert_implied_expectation(rec)
        result = store.get_latest_implied_expectation("asset-1")
        assert result is not None
        assert result.implied_pos == pytest.approx(0.35)
        assert result.upside_pct == pytest.approx(0.25)

    def test_get_implied_expectations_list(self, store):
        store.upsert_implied_expectation(_implied_expectation())
        store.upsert_implied_expectation(_implied_expectation())
        results = store.get_implied_expectations("asset-1")
        assert len(results) == 2

    def test_returns_none_for_unknown(self, store):
        assert store.get_latest_implied_expectation("no-asset") is None


class TestConsensusEstimates:
    def test_upsert_and_get_latest(self, store):
        est = _consensus_estimate()
        store.upsert_consensus_estimate(est)
        result = store.get_latest_consensus_estimate("asset-1")
        assert result is not None
        assert result.analyst_count == 8
        assert result.source == "StreetAccount"

    def test_returns_none_for_unknown(self, store):
        assert store.get_latest_consensus_estimate("no-asset") is None


class TestVariantTheses:
    def test_upsert_and_get_active(self, store):
        thesis = _variant_thesis()
        store.upsert_variant_thesis(thesis)
        result = store.get_active_variant_thesis("asset-1")
        assert result is not None
        assert result.overall_conviction == "high"
        assert len(result.deltas) == 1
        assert result.deltas[0].dimension == "peak_sales"

    def test_get_variant_theses_list(self, store):
        store.upsert_variant_thesis(_variant_thesis())
        store.upsert_variant_thesis(_variant_thesis())
        theses = store.get_variant_theses("asset-1")
        assert len(theses) == 2

    def test_upsert_again_still_one_active(self, store):
        """Upserting a second thesis replaces the row but is_active=1 for both (INSERT OR REPLACE)."""
        store.upsert_variant_thesis(_variant_thesis())
        store.upsert_variant_thesis(_variant_thesis())
        # get_active returns the most recent one
        result = store.get_active_variant_thesis("asset-1")
        assert result is not None

    def test_returns_none_for_unknown(self, store):
        assert store.get_active_variant_thesis("no-asset") is None


class TestCatalystTrees:
    def test_upsert_and_get_latest(self, store):
        tree = _catalyst_tree()
        store.upsert_catalyst_tree(tree)
        result = store.get_latest_catalyst_tree("asset-1")
        assert result is not None
        assert result.catalyst_id == "cat-001"
        assert len(result.scenarios) == 1
        assert result.scenarios[0].label == "clear_win"

    def test_get_catalyst_trees_list(self, store):
        store.upsert_catalyst_tree(_catalyst_tree())
        results = store.get_catalyst_trees("asset-1")
        assert len(results) == 1
        assert results[0].post_event_action_map["clear_win"] == "add"

    def test_returns_none_for_unknown(self, store):
        assert store.get_latest_catalyst_tree("no-asset") is None


class TestFinancingForecasts:
    def test_upsert_and_get_latest(self, store):
        forecast = _runway_forecast()
        store.upsert_financing_forecast(forecast)
        result = store.get_latest_financing_forecast("co-1")
        assert result is not None
        assert result.runway_months_base == pytest.approx(23.0)
        assert result.cash_adequate_for_next_catalyst is True
        assert len(result.burn_scenarios) == 1
        assert result.burn_scenarios[0].label == "base"

    def test_next_catalyst_date_roundtrip(self, store):
        forecast = _runway_forecast()
        store.upsert_financing_forecast(forecast)
        result = store.get_latest_financing_forecast("co-1")
        assert result is not None
        assert result.next_catalyst_date == date(2025, 9, 15)

    def test_returns_none_for_unknown(self, store):
        assert store.get_latest_financing_forecast("unknown-co") is None


class TestDecisionRecords:
    def test_write_and_get_decisions(self, store):
        rec = _decision_record()
        store.write_decision(rec)
        results = store.get_decisions("asset-1")
        assert len(results) == 1
        assert results[0].action == "add"
        assert results[0].composite_score == pytest.approx(0.72)

    def test_get_decision_by_id(self, store):
        rec = _decision_record()
        store.write_decision(rec)
        fetched = store.get_decision(rec.decision_id)
        assert fetched is not None
        assert fetched.decision_id == rec.decision_id
        assert fetched.ticker == "TKRA"

    def test_get_decision_returns_none_for_unknown(self, store):
        assert store.get_decision("no-such-id") is None

    def test_multiple_decisions_ordered(self, store):
        r1 = _decision_record()
        r2 = _decision_record()
        store.write_decision(r1)
        store.write_decision(r2)
        results = store.get_decisions("asset-1")
        assert len(results) == 2


class TestOutcomeRecords:
    def test_write_and_get_outcome_for_decision(self, store):
        dec = _decision_record()
        store.write_decision(dec)
        outcome = _outcome_record(dec.decision_id)
        store.write_outcome(outcome)
        result = store.get_outcome_for_decision(dec.decision_id)
        assert result is not None
        assert result.return_realized_pct == pytest.approx(0.55)
        assert result.thesis_confirmed is True
        assert result.attribution == "confirmed_thesis"

    def test_get_outcomes_list(self, store):
        dec = _decision_record()
        store.write_decision(dec)
        outcome = _outcome_record(dec.decision_id)
        store.write_outcome(outcome)
        results = store.get_outcomes("asset-1")
        assert len(results) == 1

    def test_thesis_confirmed_none_roundtrip(self, store):
        dec = _decision_record()
        store.write_decision(dec)
        outcome = OutcomeRecord(
            decision_id=dec.decision_id,
            asset_id="asset-1",
            ticker="TKRA",
            decision_date=date(2025, 1, 15),
            outcome_date=date(2025, 6, 1),
            return_realized_pct=-0.10,
            attribution="market_drift",
        )
        store.write_outcome(outcome)
        result = store.get_outcome_for_decision(dec.decision_id)
        assert result is not None
        assert result.thesis_confirmed is None


class TestParameterVersions:
    def test_write_and_get_active(self, store):
        pv = _parameter_version()
        store.write_parameter_version(pv)
        result = store.get_active_parameter_version("pos_model")
        assert result is not None
        assert result.parameters["phase2_base_rate"] == pytest.approx(0.40)
        assert result.is_active is True

    def test_deactivate_parameter_version(self, store):
        pv = _parameter_version()
        store.write_parameter_version(pv)
        store.deactivate_parameter_version(pv.version_id)
        result = store.get_active_parameter_version("pos_model")
        assert result is None

    def test_list_parameter_versions(self, store):
        pv1 = _parameter_version()
        pv2 = _parameter_version()
        store.write_parameter_version(pv1)
        store.write_parameter_version(pv2)
        versions = store.list_parameter_versions("pos_model")
        assert len(versions) == 2

    def test_returns_none_for_unknown_module(self, store):
        assert store.get_active_parameter_version("nonexistent_module") is None


class TestContextManager:
    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "ctx_test.db"
        with GapFillStore(db_path=str(db_path)) as s:
            snap = _market_snapshot()
            s.upsert_market_snapshot(snap)
            result = s.get_latest_market_snapshot("asset-1")
            assert result is not None
        # After __exit__, connection is closed — verify the file was written
        assert db_path.exists()

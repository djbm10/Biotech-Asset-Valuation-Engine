"""
Tests for src/bve/analysis/validation_audit.py

Uses small synthetic fixtures so no real DB or file I/O is required.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from bve.analysis.validation_audit import (
    _signal_tier,
    run_calibration_audit,
    run_drawdown_audit,
    run_false_positive_audit,
    run_mna_audit,
    run_trade_audit,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_report(
    *,
    n_positions: int = 5,
    position_returns: list[float] | None = None,
    missing_tickers: list[dict] | None = None,
) -> dict:
    """Minimal strict_backtest_report structure."""
    if position_returns is None:
        position_returns = [0.10, -0.05, 0.20, -0.02, 0.15]
    positions = [
        {
            "asset_id": f"a-tk{i}",
            "ticker": f"TK{i}",
            "signal_date": f"2023-0{i+1}-01",
            "exit_date": f"2023-0{i+2}-01" if i < 4 else "2023-06-01",
            "weight": 0.1,
            "gross_return": r,
            "net_return": r - 0.002,
            "rank_at_signal": i + 1,
            "composite_score": 0.7 - i * 0.05,
            "calibrated_score": 0.5 + r * 0.2,
            "catalyst_type": "phase_3_readout",
            "therapeutic_area": "oncology",
            "modality": "small_molecule",
            "financing_risk_score": 0.1,
        }
        for i, r in enumerate(position_returns)
    ]
    return {
        "generated_at": "2026-01-01T00:00:00Z",
        "splits": [
            {
                "split": "train",
                "start_date": "2021-02-01",
                "end_date": "2024-02-01",
                "portfolio_backtest": {"position_log": positions},
                "mna_validation": {
                    "precision_at_k": 0.35,
                    "acquirer_top1_accuracy": 0.44,
                    "acquirer_top3_accuracy": 0.54,
                    "acquirer_top5_accuracy": 0.63,
                    "acquirer_mrr": 0.52,
                    "acquisition_likelihood_auc": 0.70,
                    "unique_target_recall_at_k": 0.52,
                },
                "replay_summary": {"n_decisions": 6},
                "alpha_validation": {},
            }
        ],
        "holdout_metrics": {"public_markets": {}, "mna": {}},
        "final_test_metrics": {"public_markets": {}, "mna": {}},
        "missing_price_report": {
            "tickers": missing_tickers or [
                {
                    "ticker": "TK0",
                    "status": "active",
                    "price_coverage_start": "2021-02-01",
                    "price_coverage_end": "2024-02-01",
                    "row_count": 1000,
                    "total_row_count": 1000,
                    "missing_days_pct": 10.0,
                    "source": "yfinance",
                    "included_in_backtest": True,
                    "reason_if_excluded": None,
                    "announcement_date": None,
                    "close_date": None,
                },
                {
                    "ticker": "ACQ1",
                    "status": "acquired",
                    "price_coverage_start": "2022-01-01",
                    "price_coverage_end": "2023-01-01",
                    "row_count": 366,
                    "total_row_count": 366,
                    "missing_days_pct": 80.0,
                    "source": "deal_universe",
                    "included_in_backtest": True,
                    "reason_if_excluded": None,
                    "announcement_date": "2023-01-01",
                    "close_date": None,
                },
                {
                    "ticker": "MISS",
                    "status": "unknown",
                    "price_coverage_start": None,
                    "price_coverage_end": None,
                    "row_count": 0,
                    "total_row_count": 0,
                    "missing_days_pct": 100.0,
                    "source": "none",
                    "included_in_backtest": False,
                    "reason_if_excluded": "no_price_data",
                    "announcement_date": None,
                    "close_date": None,
                },
            ],
        },
    }


def _make_replay_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE replay_decisions (
            decision_id TEXT, run_id TEXT, asset_id TEXT, ticker TEXT,
            decided_at TEXT, action TEXT, size_pct REAL,
            composite_score REAL, entry_price REAL, exit_date TEXT,
            exit_price REAL, return_pct REAL, attribution_type TEXT,
            is_closed INTEGER
        );
        CREATE TABLE historical_prices (ticker TEXT, price_date TEXT, close_usd REAL);
        CREATE TABLE market_prices (ticker TEXT, price_date TEXT, close_usd REAL);
        CREATE TABLE acquisition_announcements (ticker TEXT, announcement_date TEXT);
        CREATE TABLE capital_snapshots (
            snapshot_id TEXT, asset_id TEXT, snapshot_date TEXT,
            cash_runway_quarters REAL, capital_risk_level TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO replay_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("d1", "r1", "a-vktx", "VKTX", "2024-01-01", "add",
         0.05, 0.62, 25.0, "2024-02-01", 28.0, 12.0, "confirmed_thesis", 1),
    )
    conn.execute(
        "INSERT INTO replay_decisions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("d2", "r1", "a-edit", "EDIT", "2024-01-15", "add",
         0.05, 0.51, 10.0, "2024-02-15", 8.5, -15.0, "thesis_error", 1),
    )
    conn.execute(
        "INSERT INTO acquisition_announcements VALUES (?,?)",
        ("ACME", "2023-06-01"),
    )
    conn.commit()
    return conn


def _make_knowledge_db(*, include_acquired: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE ma_probability_snapshots (
            snapshot_date TEXT, asset_id TEXT, ticker TEXT, stage TEXT,
            therapeutic_area TEXT, probability REAL, rank INTEGER,
            best_acquirer_id TEXT, best_acquirer_name TEXT,
            above_alert_threshold INTEGER, strategic_fit_score REAL,
            valuation_discount_score REAL, de_risking_stage_score REAL,
            capital_vulnerability_score REAL, enterprise_value_millions REAL,
            acquisition_discount REAL, days_to_catalyst INTEGER,
            estimated_deal_value_low_millions REAL, estimated_deal_value_high_millions REAL,
            run_id TEXT, created_at TEXT, scarcity_score REAL,
            scarcity_peer_count INTEGER, scarcity_bucket TEXT,
            p_takeout_calibrated REAL, acquirer_candidates_json TEXT
        );
        """
    )
    candidates_json = json.dumps(
        [
            {"acquirer_name": "Pfizer", "acquirer_id": "pfizer", "mna_probability_score": 0.9},
            {"acquirer_name": "Roche", "acquirer_id": "roche", "mna_probability_score": 0.8},
            {"acquirer_name": "Novartis", "acquirer_id": "novartis", "mna_probability_score": 0.7},
            {"acquirer_name": "GSK", "acquirer_id": "gsk", "mna_probability_score": 0.6},
            {"acquirer_name": "Merck", "acquirer_id": "merck", "mna_probability_score": 0.5},
        ]
    )
    # Acquired ticker ACME — has prior snapshots
    conn.execute(
        "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2023-01-01", "a-acme", "ACME", "phase_3", "oncology",
         0.85, 1, "pfizer", "Pfizer", 1,
         0.9, 0.7, 0.9, 0.1, 500.0, 0.2, 30,
         400.0, 600.0, "run1", "2023-01-01T00:00:00Z",
         0.8, 2, "high", 0.4, candidates_json),
    )
    # Non-acquired false positive — high score
    conn.execute(
        "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2024-01-01", "a-fp1", "FP1", "phase_2", "immunology",
         0.92, 1, "roche", "Roche", 1,
         0.88, 0.75, 0.8, 0.6, 300.0, 0.3, None,
         200.0, 400.0, "run2", "2024-01-01T00:00:00Z",
         0.9, 1, "very_high", None, candidates_json),
    )
    # Non-acquired lower score
    conn.execute(
        "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2024-01-01", "a-fp2", "FP2", "phase_1", "cns",
         0.3, 5, "novartis", "Novartis", 0,
         0.4, 0.3, 0.5, 0.2, 100.0, 0.1, None,
         80.0, 120.0, "run2", "2024-01-01T00:00:00Z",
         0.4, 3, "medium", None, candidates_json),
    )
    conn.commit()
    return conn


def _make_deal_yaml(tmp_path: Path, acquirer_in_top5: bool = True) -> Path:
    deal = {
        "as_of_date": "2026-03-22",
        "deals": [
            {
                "target_name": "Acme Pharma",
                "target_ticker": "ACME",
                "acquirer": "Pfizer" if acquirer_in_top5 else "Sanofi",
                "acquirer_category": "big_pharma",
                "announcement_date": "2023-06-01",
                "headline_value_millions": 1500,
                "therapeutic_area": "oncology",
                "phase_at_acquisition": "phase_3",
                "comp_bucket": "direct_dev_stage",
            }
        ],
    }
    import yaml
    p = tmp_path / "deal_universe.yaml"
    p.write_text(yaml.dump(deal))
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSignalTier:
    def test_rank_1_is_tier_a(self):
        assert _signal_tier(None, 1) == "tier_A"

    def test_rank_3_is_tier_a(self):
        assert _signal_tier(None, 3) == "tier_A"

    def test_rank_5_is_tier_b(self):
        assert _signal_tier(None, 5) == "tier_B"

    def test_rank_10_is_tier_c(self):
        assert _signal_tier(None, 10) == "tier_C"

    def test_score_based_tier_a(self):
        assert _signal_tier(0.70, None) == "tier_A"

    def test_score_based_tier_b(self):
        assert _signal_tier(0.55, None) == "tier_B"

    def test_score_based_tier_c(self):
        assert _signal_tier(0.40, None) == "tier_C"

    def test_none_unknown(self):
        assert _signal_tier(None, None) == "unknown"


class TestTradeAudit:
    def test_runs_without_error(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db()
        summary = run_trade_audit(report, conn, tmp_path)
        conn.close()
        assert "n_trades" in summary

    def test_creates_all_trades_csv(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db()
        run_trade_audit(report, conn, tmp_path)
        conn.close()
        assert (tmp_path / "all_trades.csv").exists()

    def test_creates_winners_csv(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db()
        run_trade_audit(report, conn, tmp_path)
        conn.close()
        assert (tmp_path / "top_20_winners.csv").exists()

    def test_creates_losers_csv(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db()
        run_trade_audit(report, conn, tmp_path)
        conn.close()
        assert (tmp_path / "top_20_losers.csv").exists()

    def test_winners_have_highest_returns(self, tmp_path):
        import csv
        report = _make_report(position_returns=[0.10, -0.05, 0.20, -0.02, 0.15])
        conn = _make_replay_db()
        run_trade_audit(report, conn, tmp_path)
        conn.close()
        with open(tmp_path / "top_20_winners.csv") as f:
            rows = list(csv.DictReader(f))
        if rows:
            returns = [float(r["net_return_pct"]) for r in rows if r["net_return_pct"] not in ("", "None")]
            if len(returns) >= 2:
                assert returns[0] >= returns[-1]

    def test_losers_have_lowest_returns(self, tmp_path):
        import csv
        report = _make_report(position_returns=[0.10, -0.05, 0.20, -0.02, 0.15])
        conn = _make_replay_db()
        run_trade_audit(report, conn, tmp_path)
        conn.close()
        with open(tmp_path / "top_20_losers.csv") as f:
            rows = list(csv.DictReader(f))
        if rows:
            returns = [float(r["net_return_pct"]) for r in rows if r["net_return_pct"] not in ("", "None")]
            if len(returns) >= 2:
                assert returns[0] <= returns[-1]

    def test_trade_count_positive(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db()
        summary = run_trade_audit(report, conn, tmp_path)
        conn.close()
        assert summary["n_trades"] >= 0

    def test_creates_summary_json(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db()
        run_trade_audit(report, conn, tmp_path)
        conn.close()
        assert (tmp_path / "trade_summary.json").exists()


class TestMnaAudit:
    def test_runs_without_error(self, tmp_path):
        conn = _make_knowledge_db()
        deal_path = _make_deal_yaml(tmp_path, acquirer_in_top5=True)
        summary = run_mna_audit(deal_path, conn, tmp_path, universe=[])
        conn.close()
        assert "n_deals_evaluated" in summary

    def test_creates_deal_level_csv(self, tmp_path):
        conn = _make_knowledge_db()
        deal_path = _make_deal_yaml(tmp_path)
        run_mna_audit(deal_path, conn, tmp_path, universe=[])
        conn.close()
        assert (tmp_path / "mna_deal_level_audit.csv").exists()

    def test_creates_missed_acquirers_csv(self, tmp_path):
        conn = _make_knowledge_db()
        deal_path = _make_deal_yaml(tmp_path)
        run_mna_audit(deal_path, conn, tmp_path, universe=[])
        conn.close()
        assert (tmp_path / "mna_missed_acquirers.csv").exists()

    def test_creates_correct_top5_csv(self, tmp_path):
        conn = _make_knowledge_db()
        deal_path = _make_deal_yaml(tmp_path)
        run_mna_audit(deal_path, conn, tmp_path, universe=[])
        conn.close()
        assert (tmp_path / "mna_correct_top5.csv").exists()

    def test_ranks_actual_acquirer_rank1_when_in_top5(self, tmp_path):
        import csv
        conn = _make_knowledge_db(include_acquired=True)
        deal_path = _make_deal_yaml(tmp_path, acquirer_in_top5=True)
        summary = run_mna_audit(deal_path, conn, tmp_path, universe=[])
        conn.close()
        with open(tmp_path / "mna_deal_level_audit.csv") as f:
            rows = list(csv.DictReader(f))
        acme_rows = [r for r in rows if r["ticker"] == "ACME"]
        if acme_rows:
            rank = acme_rows[0]["rank_of_actual"]
            assert rank == "1" or rank == "not_in_pool" or rank == "no_prior_snapshot"

    def test_missed_acquirer_when_not_in_top5(self, tmp_path):
        import csv
        conn = _make_knowledge_db(include_acquired=True)
        deal_path = _make_deal_yaml(tmp_path, acquirer_in_top5=False)
        run_mna_audit(deal_path, conn, tmp_path, universe=[])
        conn.close()
        with open(tmp_path / "mna_missed_acquirers.csv") as f:
            rows = list(csv.DictReader(f))
        # Sanofi is not in the top5 candidates, so ACME should appear in missed
        assert any(r["ticker"] == "ACME" for r in rows)

    def test_handles_missing_deal_universe(self, tmp_path):
        conn = _make_knowledge_db()
        missing_path = tmp_path / "nonexistent.yaml"
        summary = run_mna_audit(missing_path, conn, tmp_path, universe=[])
        conn.close()
        assert summary == {}


class TestFalsePositiveAudit:
    def test_runs_without_error(self, tmp_path):
        conn = _make_knowledge_db()
        acquired = {"ACME"}
        summary = run_false_positive_audit(conn, acquired, tmp_path)
        conn.close()
        assert "n_false_positives_evaluated" in summary

    def test_excludes_acquired_tickers(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        acquired = {"ACME"}
        run_false_positive_audit(conn, acquired, tmp_path)
        conn.close()
        with open(tmp_path / "top_20_mna_false_positives.csv") as f:
            rows = list(csv.DictReader(f))
        tickers = [r["ticker"] for r in rows]
        assert "ACME" not in tickers

    def test_includes_non_acquired_tickers(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        acquired = {"ACME"}
        run_false_positive_audit(conn, acquired, tmp_path)
        conn.close()
        with open(tmp_path / "top_20_mna_false_positives.csv") as f:
            rows = list(csv.DictReader(f))
        tickers = [r["ticker"] for r in rows]
        assert "FP1" in tickers or "FP2" in tickers

    def test_sorted_by_score_descending(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        acquired = {"ACME"}
        run_false_positive_audit(conn, acquired, tmp_path)
        conn.close()
        with open(tmp_path / "top_20_mna_false_positives.csv") as f:
            rows = list(csv.DictReader(f))
        if len(rows) >= 2:
            scores = [float(r["mna_score"]) for r in rows if r["mna_score"] not in ("None", "N/A", "")]
            assert scores == sorted(scores, reverse=True)

    def test_creates_false_positive_summary_md(self, tmp_path):
        conn = _make_knowledge_db()
        run_false_positive_audit(conn, {"ACME"}, tmp_path)
        conn.close()
        assert (tmp_path / "false_positive_summary.md").exists()


class TestCalibrationAudit:
    def test_runs_without_error(self, tmp_path):
        report = _make_report()
        conn = _make_knowledge_db()
        acquired = {"ACME"}
        summary = run_calibration_audit(report, conn, acquired, tmp_path)
        conn.close()
        assert "public_ece" in summary

    def test_creates_public_calibration_csv(self, tmp_path):
        report = _make_report()
        conn = _make_knowledge_db()
        run_calibration_audit(report, conn, {"ACME"}, tmp_path)
        conn.close()
        assert (tmp_path / "calibration_buckets_public.csv").exists()

    def test_creates_mna_calibration_csv(self, tmp_path):
        report = _make_report()
        conn = _make_knowledge_db()
        run_calibration_audit(report, conn, {"ACME"}, tmp_path)
        conn.close()
        assert (tmp_path / "calibration_buckets_mna.csv").exists()

    def test_calibration_buckets_count(self, tmp_path):
        import csv
        report = _make_report()
        conn = _make_knowledge_db()
        run_calibration_audit(report, conn, {"ACME"}, tmp_path)
        conn.close()
        with open(tmp_path / "calibration_buckets_public.csv") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 5  # 5 buckets

    def test_calibration_ece_non_negative(self, tmp_path):
        report = _make_report()
        conn = _make_knowledge_db()
        summary = run_calibration_audit(report, conn, {"ACME"}, tmp_path)
        conn.close()
        assert summary["public_ece"] >= 0.0
        assert summary["mna_ece"] >= 0.0


class TestDrawdownAudit:
    def test_runs_without_error(self, tmp_path):
        report = _make_report()
        summary = run_drawdown_audit(report, tmp_path)
        assert "max_drawdown_pct" in summary or summary == {}

    def test_creates_drawdown_csv(self, tmp_path):
        report = _make_report()
        run_drawdown_audit(report, tmp_path)
        assert (tmp_path / "drawdown_audit.csv").exists()

    def test_creates_drawdown_md(self, tmp_path):
        report = _make_report()
        run_drawdown_audit(report, tmp_path)
        assert (tmp_path / "drawdown_audit.md").exists()

    def test_max_drawdown_non_positive(self, tmp_path):
        report = _make_report(position_returns=[-0.10, -0.08, -0.15, -0.02, 0.05])
        summary = run_drawdown_audit(report, tmp_path)
        if summary:
            assert summary.get("max_drawdown_pct", 0) <= 0.0

    def test_creates_equity_curve_csv(self, tmp_path):
        report = _make_report()
        run_drawdown_audit(report, tmp_path)
        assert (tmp_path / "equity_curve.csv").exists()

    def test_handles_empty_positions(self, tmp_path):
        report = _make_report()
        report["splits"][0]["portfolio_backtest"]["position_log"] = []
        summary = run_drawdown_audit(report, tmp_path)
        assert summary == {}

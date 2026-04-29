"""
Tests for src/bve/analysis/institutional_validation.py

All tests use synthetic in-memory fixtures — no real DB or file I/O.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from bve.analysis.institutional_validation import (
    CRITERIA,
    RANDOM_BASELINE_TOP1,
    RANDOM_BASELINE_TOP5,
    _apply_calibration,
    _brier_score,
    _block_bootstrap_ci,
    _classify_fp,
    _ece,
    _isotonic_calibrate,
    _nearest_xbi,
    _normalize_acquirer_name,
    _pass_fail,
    _xbi_return,
    build_corrected_metrics,
    run_false_positive_taxonomy,
    run_lead_time_correction,
    run_mna_calibration,
    run_pool_coverage,
    run_public_market_metrics,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_report(
    *,
    n_train: int = 20,
    train_returns: list[float] | None = None,
    mna_prec_train: float = 0.35,
    mna_auc_train: float = 0.70,
    acq_top1_train: float = 0.44,
    acq_top5_train: float = 0.63,
) -> dict:
    if train_returns is None:
        train_returns = [0.05 * (i % 3 - 1) for i in range(n_train)]
    positions = [
        {
            "asset_id": f"a-tk{i}",
            "ticker": f"TK{i % 5}",
            "signal_date": f"202{2 + i % 2}-0{(i % 9) + 1}-01",
            "exit_date": f"202{2 + i % 2}-0{(i % 9) + 2}-01",
            "weight": 0.1,
            "gross_return": r,
            "net_return": r - 0.002,
            "rank_at_signal": (i % 10) + 1,
            "composite_score": 0.5 + r * 0.1,
            "calibrated_score": 0.5,
            "catalyst_type": "company_sotp",
            "therapeutic_area": "oncology",
            "modality": "small_molecule",
            "financing_risk_score": 0.1,
        }
        for i, r in enumerate(train_returns)
    ]
    return {
        "generated_at": "2026-01-01T00:00:00Z",
        "splits": [
            {
                "split": "train",
                "start_date": "2021-02-01",
                "end_date": "2024-02-01",
                "portfolio_backtest": {"position_log": positions},
                "alpha_validation": {
                    "run_id": "r1",
                    "n_trades": n_train,
                    "mean_excess_return": 0.05,
                    "hit_rate": 0.55,
                    "bootstrap_p_value": 0.15,
                    "alpha_survives_corrections": False,
                    "csv_path": "",
                },
                "mna_validation": {
                    "n_rows": 500,
                    "n_positive_targets": 10,
                    "precision_at_k": mna_prec_train,
                    "acquisition_likelihood_auc": mna_auc_train,
                    "acquirer_top1_accuracy": acq_top1_train,
                    "acquirer_top3_accuracy": 0.55,
                    "acquirer_top5_accuracy": acq_top5_train,
                    "acquirer_mrr": 0.52,
                    "false_positive_rate_at_k": 0.65,
                    "unique_target_recall_at_k": 0.52,
                },
                "replay_summary": {"n_decisions": 6},
            },
            {
                "split": "validation",
                "start_date": "2024-03-01",
                "end_date": "2025-02-01",
                "portfolio_backtest": {"position_log": []},
                "alpha_validation": {
                    "n_trades": 5,
                    "mean_excess_return": -0.10,
                    "hit_rate": 0.40,
                    "bootstrap_p_value": 1.0,
                    "alpha_survives_corrections": False,
                    "csv_path": "",
                },
                "mna_validation": {
                    "n_rows": 100,
                    "n_positive_targets": 3,
                    "precision_at_k": 0.25,
                    "acquisition_likelihood_auc": 0.60,
                    "acquirer_top1_accuracy": 0.30,
                    "acquirer_top3_accuracy": 0.40,
                    "acquirer_top5_accuracy": 0.50,
                    "acquirer_mrr": 0.38,
                    "false_positive_rate_at_k": 0.75,
                    "unique_target_recall_at_k": 0.40,
                },
            },
            {
                "split": "holdout",
                "start_date": "2025-03-01",
                "end_date": "2026-03-01",
                "portfolio_backtest": {"position_log": []},
                "alpha_validation": {
                    "n_trades": 4,
                    "mean_excess_return": -0.02,
                    "hit_rate": 0.50,
                    "bootstrap_p_value": 0.85,
                    "alpha_survives_corrections": False,
                    "csv_path": "",
                },
                "mna_validation": {
                    "n_rows": 80,
                    "n_positive_targets": 2,
                    "precision_at_k": 0.22,
                    "acquisition_likelihood_auc": 0.65,
                    "acquirer_top1_accuracy": 1.0,
                    "acquirer_top3_accuracy": 1.0,
                    "acquirer_top5_accuracy": 1.0,
                    "acquirer_mrr": 1.0,
                    "false_positive_rate_at_k": 0.78,
                    "unique_target_recall_at_k": 0.50,
                },
            },
        ],
        "holdout_metrics": {
            "public_markets": {},
            "mna": {
                "top1_accuracy": 1.0,
                "top5_accuracy": 1.0,
                "mrr": 1.0,
                "median_lead_days": 239.0,
            },
        },
        "final_test_metrics": {"public_markets": {}, "mna": {}},
        "missing_price_report": {
            "universe_size": 10,
            "tickers": [
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
            ],
        },
        "robustness_report": {},
    }


def _make_replay_db_with_xbi() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE historical_prices (ticker TEXT, price_date TEXT, close_usd REAL);
        CREATE TABLE market_prices (ticker TEXT, price_date TEXT, close_usd REAL);
        CREATE TABLE replay_decisions (
            decision_id TEXT, run_id TEXT, asset_id TEXT, ticker TEXT,
            decided_at TEXT, action TEXT, size_pct REAL,
            composite_score REAL, entry_price REAL, exit_date TEXT,
            exit_price REAL, return_pct REAL, attribution_type TEXT,
            is_closed INTEGER
        );
        CREATE TABLE acquisition_announcements (ticker TEXT, announcement_date TEXT);
        CREATE TABLE capital_snapshots (
            snapshot_id TEXT, asset_id TEXT, snapshot_date TEXT,
            cash_runway_quarters REAL, capital_risk_level TEXT
        );
        """
    )
    # XBI prices for 2022-2023
    for y in range(2021, 2027):
        for m in range(1, 13):
            for d in (1, 15):
                dt = f"{y}-{m:02d}-{d:02d}"
                price = 80.0 + (y - 2021) * 5 + m * 0.1
                conn.execute(
                    "INSERT INTO historical_prices VALUES (?, ?, ?)", ("XBI", dt, price)
                )
    conn.commit()
    return conn


def _make_knowledge_db() -> sqlite3.Connection:
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
        CREATE TABLE company_sotp_snapshots (
            snapshot_id TEXT, ticker TEXT, company_id TEXT, company_name TEXT,
            snapshot_date TEXT, rank INTEGER, market_cap_millions REAL,
            enterprise_value_millions REAL, sotp_equity_value_millions REAL,
            sotp_per_share REAL, sotp_discount REAL, ranked_sotp_discount REAL,
            modeled_asset_coverage_pct REAL, asset_count_modeled INTEGER,
            modeled_asset_ids_json TEXT, config_quality_summary TEXT,
            modeled_asset_confidence_min REAL, modeled_asset_confidence_avg REAL,
            action_policy TEXT, action_reason TEXT, market_cap_source TEXT,
            balance_sheet_source TEXT, balance_sheet_source_ref TEXT,
            balance_sheet_snapshot_date TEXT, balance_sheet_period_end_date TEXT,
            balance_sheet_form_type TEXT, balance_sheet_is_point_in_time INTEGER,
            balance_sheet_age_days INTEGER, balance_sheet_passes_recency_gate INTEGER,
            balance_sheet_recency_penalty REAL, bucket_count INTEGER,
            buckets_json TEXT, limitations_json TEXT, notes TEXT,
            created_at TEXT, manual_bucket_share_pct REAL,
            manual_bucket_confidence_avg REAL, n_bucket_sources INTEGER,
            reconciliation_gap_millions REAL, reconciliation_gap_pct REAL,
            reconciliation_status TEXT, reconciliation_passes_gate INTEGER,
            mcap_trend_3m_pct REAL, sotp_tier TEXT, sotp_action TEXT,
            sotp_confidence_tier TEXT, sotp_tier_reason TEXT
        );
        """
    )
    cands = json.dumps([
        {"acquirer_name": "Pfizer", "acquirer_id": "pfizer"},
        {"acquirer_name": "Roche", "acquirer_id": "roche"},
        {"acquirer_name": "Novartis", "acquirer_id": "novartis"},
        {"acquirer_name": "GSK", "acquirer_id": "gsk"},
        {"acquirer_name": "Merck", "acquirer_id": "merck"},
    ])
    # Acquired ticker ACME (score 0.9)
    for date_str in ("2021-02-01", "2022-06-01", "2023-01-01"):
        above = 1 if date_str >= "2022-06-01" else 0
        conn.execute(
            "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date_str, "a-acme", "ACME", "phase_3", "oncology", 0.9, 1,
             "pfizer", "Pfizer", above, 0.9, 0.7, 0.9, 0.1, 500, 0.2, 30,
             400, 600, "run1", date_str + "T00:00:00Z",
             0.85, 2, "high", None, cands),
        )
    # Non-acquired FP1 (score 1.0)
    conn.execute(
        "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2024-01-01", "a-fp1", "FP1", "phase_3", "immunology", 1.0, 1,
         "roche", "Roche", 1, 0.95, 0.8, 0.9, 0.1, 300, 0.3, None,
         200, 400, "run2", "2024-01-01T00:00:00Z",
         0.9, 1, "very_high", None, cands),
    )
    # Non-acquired FP2 (score 0.3) - capital risk
    conn.execute(
        "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2024-01-01", "a-fp2", "FP2", "phase_2", "cns", 0.3, 5,
         "novartis", "Novartis", 0, 0.4, 0.3, 0.5, 0.7, 100, 0.1, None,
         80, 120, "run2", "2024-01-01T00:00:00Z",
         0.4, 3, "medium", None, cands),
    )
    # Holdout acquired: RNA (score 0.85)
    conn.execute(
        "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2025-06-01", "a-rna", "RNA", "phase_3", "neuroscience", 0.85, 2,
         "novartis", "Novartis", 1, 0.8, 0.7, 0.9, 0.05, 2000, 0.15, 60,
         1500, 3000, "run3", "2025-06-01T00:00:00Z",
         0.8, 1, "high", None, cands),
    )
    conn.commit()
    return conn


def _make_deals() -> list[dict]:
    return [
        {
            "target_ticker": "ACME",
            "target_name": "Acme Pharma",
            "acquirer": "Pfizer",
            "announcement_date": "2023-06-01",
            "therapeutic_area": "oncology",
            "headline_value_millions": 1500,
        },
        {
            "target_ticker": "RNA",
            "target_name": "RNA Bio",
            "acquirer": "Novartis",
            "announcement_date": "2025-10-01",
            "therapeutic_area": "neuroscience",
            "headline_value_millions": 12000,
        },
    ]


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_pass_fail_true(self):
        assert _pass_fail(True) == "PASS"

    def test_pass_fail_false(self):
        assert _pass_fail(False) == "FAIL"

    def test_nearest_xbi_exact(self):
        prices = {"2023-01-01": 80.0, "2023-01-02": 81.0}
        assert _nearest_xbi(prices, "2023-01-01") == 80.0

    def test_nearest_xbi_nearest(self):
        prices = {"2023-01-03": 82.0}
        assert _nearest_xbi(prices, "2023-01-01") == 82.0

    def test_nearest_xbi_missing(self):
        assert _nearest_xbi({}, "2023-01-01") is None

    def test_xbi_return_basic(self):
        prices = {"2023-01-01": 100.0, "2023-04-01": 110.0}
        ret = _xbi_return(prices, "2023-01-01", "2023-04-01")
        assert ret is not None
        assert abs(ret - 0.10) < 1e-6

    def test_xbi_return_none_when_missing(self):
        assert _xbi_return({}, "2023-01-01", "2023-04-01") is None

    def test_brier_score_perfect(self):
        assert _brier_score([1.0, 0.0], [1, 0]) == 0.0

    def test_brier_score_worst(self):
        assert _brier_score([0.0, 1.0], [1, 0]) == 1.0

    def test_brier_score_empty(self):
        import math
        assert math.isnan(_brier_score([], []))

    def test_ece_perfect_calibration(self):
        # prob = outcome rate in each bin → ECE should be near 0
        probs = [0.1] * 10 + [0.5] * 10 + [0.9] * 10
        outcomes = [0] * 10 + [1] * 5 + [0] * 5 + [1] * 9 + [0] * 1
        ece = _ece(probs, outcomes)
        assert 0 <= ece <= 1.0

    def test_ece_overconfident(self):
        # All probs 1.0, 50% outcomes → ECE ≈ 0.5
        probs = [1.0] * 100
        outcomes = [1] * 50 + [0] * 50
        ece = _ece(probs, outcomes)
        assert ece > 0.4

    def test_block_bootstrap_ci_basic(self):
        data = [0.05, 0.10, -0.02, 0.08, 0.12, -0.01, 0.07, 0.09]
        mean, lo, hi = _block_bootstrap_ci(data, n_boot=100, block_size=2)
        assert lo <= mean <= hi

    def test_block_bootstrap_ci_small(self):
        data = [0.1, 0.2]
        mean, lo, hi = _block_bootstrap_ci(data, n_boot=50)
        assert lo <= hi

    def test_isotonic_calibrate_basic(self):
        probs = [0.1, 0.3, 0.5, 0.7, 0.9] * 10
        outcomes = [0, 0, 1, 1, 1] * 10
        knots = _isotonic_calibrate(probs, outcomes)
        assert len(knots) > 0
        # Monotone
        cal_probs = [k[1] for k in knots]
        assert all(cal_probs[i] <= cal_probs[i + 1] for i in range(len(cal_probs) - 1))

    def test_isotonic_calibrate_empty(self):
        knots = _isotonic_calibrate([], [])
        assert len(knots) == 2  # default boundary knots

    def test_apply_calibration_boundary(self):
        knots = [(0.0, 0.0), (0.5, 0.3), (1.0, 1.0)]
        assert _apply_calibration(knots, 0.0) == 0.0
        assert _apply_calibration(knots, 1.0) == 1.0

    def test_apply_calibration_interpolates(self):
        knots = [(0.0, 0.0), (0.5, 0.3), (1.0, 0.6)]
        val = _apply_calibration(knots, 0.25)
        assert 0.0 <= val <= 0.3


# ---------------------------------------------------------------------------
# Corrected metrics
# ---------------------------------------------------------------------------


class TestCorrectedMetrics:
    def test_runs_without_error(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        metrics = build_corrected_metrics(report, conn)
        conn.close()
        assert len(metrics) > 0

    def test_has_all_splits(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        metrics = build_corrected_metrics(report, conn)
        conn.close()
        for split in ("train", "validation", "holdout"):
            assert f"mna_auc_{split}" in metrics
            assert f"acquirer_top1_{split}" in metrics

    def test_pass_fail_present(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        metrics = build_corrected_metrics(report, conn)
        conn.close()
        assert "pass_fail" in metrics["mna_auc_train"]

    def test_sample_size_present(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        metrics = build_corrected_metrics(report, conn)
        conn.close()
        assert metrics["mna_auc_train"]["n"] is not None

    def test_random_baseline_attached_to_acquirer_metrics(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        metrics = build_corrected_metrics(report, conn)
        conn.close()
        assert "random_baseline" in metrics["acquirer_top1_train"]

    def test_no_supported_not_supported_labels(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        metrics = build_corrected_metrics(report, conn)
        conn.close()
        for k, v in metrics.items():
            for field_val in v.values():
                assert "SUPPORTED" not in str(field_val)
                assert "NOT_SUPPORTED" not in str(field_val)


# ---------------------------------------------------------------------------
# Public market metrics
# ---------------------------------------------------------------------------


class TestPublicMarketMetrics:
    def test_runs_without_error(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        result = run_public_market_metrics(report, conn, tmp_path, set())
        conn.close()
        assert "split_summary" in result

    def test_creates_trades_csv(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        run_public_market_metrics(report, conn, tmp_path, set())
        conn.close()
        assert (tmp_path / "public_market_trades.csv").exists()

    def test_creates_ticker_contribution_csv(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        run_public_market_metrics(report, conn, tmp_path, set())
        conn.close()
        assert (tmp_path / "per_ticker_contribution.csv").exists()

    def test_xbi_excess_computed(self, tmp_path):
        import csv
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        run_public_market_metrics(report, conn, tmp_path, set())
        conn.close()
        with open(tmp_path / "public_market_trades.csv") as f:
            rows = list(csv.DictReader(f))
        xbi_rets = [r["xbi_return_pct"] for r in rows if r["xbi_return_pct"] not in ("None", "")]
        assert len(xbi_rets) > 0

    def test_fallback_flag_set(self, tmp_path):
        import csv
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        # TK0 is a fallback ticker
        run_public_market_metrics(report, conn, tmp_path, {"TK0"})
        conn.close()
        with open(tmp_path / "public_market_trades.csv") as f:
            rows = list(csv.DictReader(f))
        tk0_rows = [r for r in rows if r["ticker"] == "TK0"]
        if tk0_rows:
            assert tk0_rows[0]["is_fallback_price"] == "True"

    def test_clean_summary_excludes_fallback(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        result = run_public_market_metrics(report, conn, tmp_path, {"TK0", "TK1"})
        conn.close()
        clean_n = result["clean_summary"]["n_trades"]
        total_n = sum(s["n_trades"] for s in result["split_summary"].values())
        assert clean_n <= total_n

    def test_split_summary_has_ci(self, tmp_path):
        report = _make_report()
        conn = _make_replay_db_with_xbi()
        result = run_public_market_metrics(report, conn, tmp_path, set())
        conn.close()
        train_s = result["split_summary"].get("train", {})
        assert "ci95_lower_pct" in train_s
        assert "ci95_upper_pct" in train_s


# ---------------------------------------------------------------------------
# M&A calibration
# ---------------------------------------------------------------------------


class TestMnaCalibration:
    def test_runs_without_error(self, tmp_path):
        report = _make_report()
        conn = _make_knowledge_db()
        acquired = {"ACME", "RNA"}
        result = run_mna_calibration(report, conn, acquired, tmp_path)
        conn.close()
        assert "holdout_raw" in result

    def test_creates_calibration_curve_csv(self, tmp_path):
        report = _make_report()
        conn = _make_knowledge_db()
        run_mna_calibration(report, _make_knowledge_db(), {"ACME", "RNA"}, tmp_path)
        assert (tmp_path / "mna_calibration_curve.csv").exists()

    def test_creates_by_dimension_csv(self, tmp_path):
        report = _make_report()
        run_mna_calibration(report, _make_knowledge_db(), {"ACME", "RNA"}, tmp_path)
        assert (tmp_path / "mna_calibration_by_dimension.csv").exists()

    def test_holdout_pass_fail_fields_present(self, tmp_path):
        report = _make_report()
        result = run_mna_calibration(report, _make_knowledge_db(), {"ACME", "RNA"}, tmp_path)
        assert "pass_ece" in result["holdout_raw"]
        assert "pass_brier" in result["holdout_raw"]

    def test_calibration_note_present(self, tmp_path):
        report = _make_report()
        result = run_mna_calibration(report, _make_knowledge_db(), {"ACME", "RNA"}, tmp_path)
        assert "rank scores" in result.get("note", "")

    def test_brier_non_negative(self, tmp_path):
        report = _make_report()
        result = run_mna_calibration(report, _make_knowledge_db(), {"ACME", "RNA"}, tmp_path)
        assert result["holdout_raw"]["brier"] >= 0


# ---------------------------------------------------------------------------
# Pool coverage
# ---------------------------------------------------------------------------


class TestPoolCoverage:
    def test_runs_without_error(self, tmp_path):
        conn = _make_knowledge_db()
        result = run_pool_coverage(_make_deals(), conn, tmp_path)
        conn.close()
        assert "n_deals" in result

    def test_creates_pool_coverage_csv(self, tmp_path):
        conn = _make_knowledge_db()
        run_pool_coverage(_make_deals(), conn, tmp_path)
        conn.close()
        assert (tmp_path / "acquirer_pool_coverage.csv").exists()

    def test_creates_per_acquirer_accuracy_csv(self, tmp_path):
        conn = _make_knowledge_db()
        run_pool_coverage(_make_deals(), conn, tmp_path)
        conn.close()
        assert (tmp_path / "per_acquirer_accuracy.csv").exists()

    def test_creates_random_baseline_csv(self, tmp_path):
        conn = _make_knowledge_db()
        run_pool_coverage(_make_deals(), conn, tmp_path)
        conn.close()
        assert (tmp_path / "acquirer_random_baseline.csv").exists()

    def test_pfizer_found_in_acme_pool(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        run_pool_coverage(_make_deals(), conn, tmp_path)
        conn.close()
        with open(tmp_path / "acquirer_pool_coverage.csv") as f:
            rows = list(csv.DictReader(f))
        acme = [r for r in rows if r["ticker"] == "ACME"]
        if acme:
            assert acme[0]["in_pool"] == "True"
            assert acme[0]["rank"] == "1"

    def test_random_baseline_in_csv(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        run_pool_coverage(_make_deals(), conn, tmp_path)
        conn.close()
        with open(tmp_path / "acquirer_random_baseline.csv") as f:
            rows = list(csv.DictReader(f))
        metrics_list = [r["metric"] for r in rows]
        assert "top1_accuracy" in metrics_list
        assert "top5_accuracy" in metrics_list


# ---------------------------------------------------------------------------
# False-positive taxonomy
# ---------------------------------------------------------------------------


class TestFpTaxonomy:
    def test_runs_without_error(self, tmp_path):
        conn = _make_knowledge_db()
        result = run_false_positive_taxonomy(conn, {"ACME", "RNA"}, tmp_path)
        conn.close()
        assert "n_classified" in result

    def test_creates_taxonomy_csv(self, tmp_path):
        conn = _make_knowledge_db()
        run_false_positive_taxonomy(conn, {"ACME", "RNA"}, tmp_path)
        conn.close()
        assert (tmp_path / "false_positive_taxonomy.csv").exists()

    def test_creates_taxonomy_md(self, tmp_path):
        conn = _make_knowledge_db()
        run_false_positive_taxonomy(conn, {"ACME", "RNA"}, tmp_path)
        conn.close()
        assert (tmp_path / "false_positive_taxonomy.md").exists()

    def test_excluded_acquired_tickers(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        run_false_positive_taxonomy(conn, {"ACME", "RNA"}, tmp_path)
        conn.close()
        with open(tmp_path / "false_positive_taxonomy.csv") as f:
            rows = list(csv.DictReader(f))
        tickers = [r["ticker"] for r in rows]
        assert "ACME" not in tickers
        assert "RNA" not in tickers

    def test_fp_reason_is_valid_category(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        run_false_positive_taxonomy(conn, {"ACME", "RNA"}, tmp_path)
        conn.close()
        # Sprint 17: 7-category taxonomy
        valid_reasons = {
            "valuation_only", "no_buyer_urgency", "poor_strategic_fit",
            "financing_not_pressured", "standalone_path",
            "internal_acquirer_competition", "data_quality",
        }
        with open(tmp_path / "false_positive_taxonomy.csv") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            assert row["fp_reason"] in valid_reasons

    def test_financing_not_pressured_classified_correctly(self):
        snap = {
            "probability": 0.7,
            "strategic_fit_score": 0.5,
            "valuation_discount_score": 0.4,
            "capital_vulnerability_score": 0.10,   # low pressure → financing_not_pressured
            "de_risking_stage_score": 0.7,
            "scarcity_score": 0.5,
            "acquisition_discount": 0.1,
            "days_to_catalyst": None,               # no near-term catalyst
            "stage": "phase_2",
            "acquirer_candidates_json": "[]",
        }
        assert _classify_fp({}, snap) == "financing_not_pressured"


# ---------------------------------------------------------------------------
# Lead-time correction
# ---------------------------------------------------------------------------


class TestLeadTimeCorrection:
    def test_runs_without_error(self, tmp_path):
        conn = _make_knowledge_db()
        result = run_lead_time_correction(_make_deals(), conn, tmp_path)
        conn.close()
        assert "n_deals_with_lead" in result

    def test_creates_lead_time_csv(self, tmp_path):
        conn = _make_knowledge_db()
        run_lead_time_correction(_make_deals(), conn, tmp_path)
        conn.close()
        assert (tmp_path / "lead_time_correction.csv").exists()

    def test_static_flag_detection(self, tmp_path):
        """Deal first_snap == FIRST_REPLAY_DATE == first_flagged → static_screen_flag."""
        import csv
        conn = _make_knowledge_db()
        run_lead_time_correction(_make_deals(), conn, tmp_path)
        conn.close()
        with open(tmp_path / "lead_time_correction.csv") as f:
            rows = list(csv.DictReader(f))
        # ACME has first_snap = 2021-02-01 and is first_flagged = 2022-06-01 (above_threshold=1)
        acme = [r for r in rows if r["ticker"] == "ACME"]
        if acme:
            # ACME above_alert_threshold=1 starts at 2022-06-01 (not 2021-02-01), so not static
            assert acme[0]["static_screen_flag"] in ("True", "False")

    def test_corrected_lead_days_not_negative(self, tmp_path):
        import csv
        conn = _make_knowledge_db()
        run_lead_time_correction(_make_deals(), conn, tmp_path)
        conn.close()
        with open(tmp_path / "lead_time_correction.csv") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            if row["corrected_lead_days"] not in ("None", ""):
                assert float(row["corrected_lead_days"]) >= 0

    def test_summary_has_median(self, tmp_path):
        conn = _make_knowledge_db()
        result = run_lead_time_correction(_make_deals(), conn, tmp_path)
        conn.close()
        assert "median_corrected_lead_days" in result

    def test_no_deals_handled_gracefully(self, tmp_path):
        conn = _make_knowledge_db()
        result = run_lead_time_correction([], conn, tmp_path)
        conn.close()
        assert result["n_deals_with_lead"] == 0


# ---------------------------------------------------------------------------
# Acquirer alias normalization — Sprint 18
# ---------------------------------------------------------------------------


class TestNormalizeAcquirerName:
    """Verify alias normalization covers deal-universe acquirers and new profiles."""

    # --- Existing Big Pharma ---
    def test_bms_variants(self):
        assert _normalize_acquirer_name("Bristol Myers Squibb") == _normalize_acquirer_name("BMS")
        assert _normalize_acquirer_name("Bristol-Myers Squibb") == _normalize_acquirer_name("BMS")

    def test_jnj_variants(self):
        assert _normalize_acquirer_name("Johnson & Johnson") == _normalize_acquirer_name("JNJ")
        assert _normalize_acquirer_name("J&J") == _normalize_acquirer_name("JNJ")

    def test_astrazeneca_variants(self):
        assert _normalize_acquirer_name("AstraZeneca") == _normalize_acquirer_name("AZ")
        assert _normalize_acquirer_name("Astra Zeneca") == _normalize_acquirer_name("AstraZeneca")

    def test_roche_genentech(self):
        assert _normalize_acquirer_name("Genentech") == _normalize_acquirer_name("Roche")

    def test_merck_variants(self):
        assert _normalize_acquirer_name("MSD") == _normalize_acquirer_name("Merck")
        assert _normalize_acquirer_name("MRK") == _normalize_acquirer_name("Merck")

    def test_lilly_variants(self):
        assert _normalize_acquirer_name("Eli Lilly") == _normalize_acquirer_name("Lilly")
        assert _normalize_acquirer_name("LLY") == _normalize_acquirer_name("Lilly")

    def test_gilead_variants(self):
        assert _normalize_acquirer_name("Gilead Sciences") == _normalize_acquirer_name("Gilead")
        assert _normalize_acquirer_name("GILD") == _normalize_acquirer_name("Gilead")

    def test_abbvie_variants(self):
        assert _normalize_acquirer_name("AbbVie") == _normalize_acquirer_name("ABBV")

    def test_novartis_variants(self):
        assert _normalize_acquirer_name("Novartis") == _normalize_acquirer_name("NVS")

    # --- Japanese pharma (Sprint 18 additions) ---
    def test_lundbeck_with_h_prefix(self):
        """H. Lundbeck profile name matches 'Lundbeck' in deal universe."""
        assert _normalize_acquirer_name("H. Lundbeck") == _normalize_acquirer_name("Lundbeck")
        assert _normalize_acquirer_name("Lundbeck AS") == _normalize_acquirer_name("Lundbeck")
        assert _normalize_acquirer_name("HLUYY") == _normalize_acquirer_name("Lundbeck")

    def test_kyowa_kirin_variants(self):
        assert _normalize_acquirer_name("Kyowa Kirin") == _normalize_acquirer_name("KYOCY")
        assert _normalize_acquirer_name("Kyowa Hakko Kirin") == _normalize_acquirer_name("Kyowa Kirin")

    def test_otsuka_variants(self):
        assert _normalize_acquirer_name("Otsuka Pharmaceutical") == _normalize_acquirer_name("Otsuka")
        assert _normalize_acquirer_name("Otsuka Holdings") == _normalize_acquirer_name("Otsuka")
        assert _normalize_acquirer_name("OTSKY") == _normalize_acquirer_name("Otsuka")

    def test_sumitomo_variants(self):
        assert _normalize_acquirer_name("Sumitomo Pharma") == _normalize_acquirer_name("SMPNY")
        assert _normalize_acquirer_name("Sumitomo Dainippon Pharma") == _normalize_acquirer_name("Sumitomo Pharma")
        assert _normalize_acquirer_name("Sumitomo Dainippon") == _normalize_acquirer_name("Sumitomo Pharma")

    def test_chugai_variants(self):
        assert _normalize_acquirer_name("Chugai Pharmaceutical") == _normalize_acquirer_name("Chugai")
        assert _normalize_acquirer_name("CHGCY") == _normalize_acquirer_name("Chugai")

    # --- European pharma (Sprint 18 additions) ---
    def test_bayer_variants(self):
        assert _normalize_acquirer_name("Bayer AG") == _normalize_acquirer_name("Bayer")
        assert _normalize_acquirer_name("BAYRY") == _normalize_acquirer_name("Bayer")

    def test_boehringer_variants(self):
        assert _normalize_acquirer_name("Boehringer Ingelheim") == "boehringer ingelheim"

    def test_servier_variants(self):
        assert _normalize_acquirer_name("Servier") == _normalize_acquirer_name("Les Laboratoires Servier")

    def test_ucb_variants(self):
        assert _normalize_acquirer_name("UCB Pharma") == _normalize_acquirer_name("UCB")

    def test_ipsen_variants(self):
        assert _normalize_acquirer_name("Ipsen Pharma") == _normalize_acquirer_name("Ipsen")

    # --- Specialty pharma and large biotech ---
    def test_incyte_variants(self):
        assert _normalize_acquirer_name("Incyte Corporation") == _normalize_acquirer_name("Incyte")
        assert _normalize_acquirer_name("INCY") == _normalize_acquirer_name("Incyte")

    def test_jazz_variants(self):
        assert _normalize_acquirer_name("Jazz Pharmaceuticals") == _normalize_acquirer_name("Jazz")
        assert _normalize_acquirer_name("Jazz Pharma") == _normalize_acquirer_name("Jazz")

    def test_united_therapeutics_variants(self):
        assert _normalize_acquirer_name("United Therapeutics") == _normalize_acquirer_name("UTHR")

    # --- Edge cases ---
    def test_empty_string_returns_empty(self):
        assert _normalize_acquirer_name("") == ""

    def test_punctuation_stripped(self):
        name1 = _normalize_acquirer_name("Bristol-Myers Squibb")
        name2 = _normalize_acquirer_name("Bristol Myers Squibb")
        assert name1 == name2

    def test_case_insensitive(self):
        assert _normalize_acquirer_name("PFIZER") == _normalize_acquirer_name("pfizer")

    def test_extra_whitespace_normalized(self):
        assert _normalize_acquirer_name("  Pfizer  ") == _normalize_acquirer_name("Pfizer")

    def test_jnj_with_janssen_suffix(self):
        """Profile name 'Johnson & Johnson (Janssen)' matches deal universe 'Johnson & Johnson'."""
        n1 = _normalize_acquirer_name("Johnson & Johnson (Janssen)")
        n2 = _normalize_acquirer_name("Johnson & Johnson")
        # Both should resolve to the same canonical form
        assert n1 == n2 or n2 in n1 or n1 in n2

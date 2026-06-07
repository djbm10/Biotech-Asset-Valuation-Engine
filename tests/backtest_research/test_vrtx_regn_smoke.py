"""
Smoke tests for the full VRTX/REGN backtest pipeline.

These tests run the pipeline end-to-end with the real seed CSV but
stub out all external data sources (SEC, ClinicalTrials.gov, FDA, yfinance)
to avoid network calls and non-determinism.

They verify:
  - The dataset builder runs without error
  - The leakage audit passes
  - At least one feature row is produced per verified deal
  - The backtest runner scores rows and produces a results CSV
  - The report writer produces a non-empty markdown file
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_output(tmp_path):
    curated = tmp_path / "curated"
    outputs = tmp_path / "outputs"
    curated.mkdir()
    outputs.mkdir()
    return tmp_path


@pytest.fixture
def seed_csv(tmp_path):
    """Write minimal seed CSV with verified deals only."""
    csv_content = (
        "acquirer_ticker,acquirer_name,target_ticker,target_name,deal_type,"
        "announced_date,deal_value_usd_millions,deal_value_type,upfront_usd_millions,"
        "cvr_max_usd_millions,therapeutic_area,lead_asset,lead_asset_modality,"
        "lead_asset_stage_at_deal,indication,verified,verification_source,"
        "verification_url,notes\n"
        "VRTX,Vertex,ALPN,Alpine Immune Sciences,full_acquisition,2024-04-10,"
        "4900.0,cash,4900.0,,immunology_nephrology,povetacicept,biologic_fusion_protein,"
        "phase2,IgA_nephropathy,TRUE,vertex_press_release,https://example.com,Test\n"
        "REGN,Regeneron,DBTX,Decibel Therapeutics,full_acquisition,2023-08-09,"
        "109.0,cash_plus_cvr,109.0,213.0,rare_disease_hearing,DB-OTO,aav_gene_therapy,"
        "phase1_2,otoferlin_related_hearing_loss,TRUE,regeneron_press_release,"
        "https://example.com,Test\n"
    )
    p = tmp_path / "deals.csv"
    p.write_text(csv_content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Helpers to stub external calls
# ---------------------------------------------------------------------------

def _null_financials(ticker, snapshot_date=None, *args, **kwargs):
    return {
        "ticker": ticker,
        "cash_and_equivalents_millions": None,
        "rd_expense_ttm_millions": None,
        "filing_date": (snapshot_date or date.today()).isoformat() if snapshot_date else None,
        "filing_type": "10-K",
        "source_url": "https://sec.gov",
        "source_published_date": (snapshot_date or date.today()).isoformat() if snapshot_date else "2020-01-01",
        "data_as_of_date": (snapshot_date or date.today()).isoformat() if snapshot_date else "2020-01-01",
        "extraction_method": "sec_filing_text",
        "confidence": 0.70,
    }


def _null_market_cap(ticker, snapshot_date=None, *args, **kwargs):
    return {
        "ticker": ticker,
        "snapshot_date": (snapshot_date or date.today()).isoformat() if snapshot_date else "2020-01-01",
        "price_usd": None,
        "shares_outstanding": None,
        "market_cap_millions": None,
        "cash_millions": 0.0,
        "debt_millions": 0.0,
        "enterprise_value_millions": None,
        "source_url": "https://finance.yahoo.com",
        "source_published_date": (snapshot_date or date.today()).isoformat() if snapshot_date else "2020-01-01",
        "data_as_of_date": (snapshot_date or date.today()).isoformat() if snapshot_date else "2020-01-01",
        "extraction_method": "market_data_api",
        "confidence": 0.85,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDatasetBuilderSmoke:
    def test_runs_without_error(self, tmp_output, seed_csv):
        from bve.backtest_research.vrtx_regn_dataset_builder import build_dataset

        with (
            patch("bve.backtest_research.sec_client.SECClient.get_financials",
                  side_effect=_null_financials),
            patch("bve.backtest_research.historical_market_data_client.HistoricalMarketDataClient.get_enterprise_value",
                  side_effect=_null_market_cap),
            patch("bve.backtest_research.historical_market_data_client.HistoricalMarketDataClient.get_market_cap",
                  side_effect=_null_market_cap),
            patch("bve.backtest_research.historical_market_data_client.HistoricalMarketDataClient.is_publicly_traded",
                  return_value=False),
            patch("bve.backtest_research.clinicaltrials_client.ClinicalTrialsClient.get_trials_for_drug",
                  return_value=[]),
            patch("bve.backtest_research.clinicaltrials_client.ClinicalTrialsClient.get_highest_phase",
                  return_value=None),
            patch("bve.backtest_research.openfda_client.OpenFDAClient.is_approved",
                  return_value=False),
        ):
            summary = build_dataset(
                acquirers=["VRTX", "REGN"],
                since_year=2010,
                snapshot_days=[90, 30],
                min_negatives=5,
                max_negatives=10,
                output_dir=tmp_output / "curated",
                raw_dir=None,
                rnpv_config_dir=tmp_output / "rnpv_configs",
                include_unverified=False,
                seed_csv=seed_csv,
                dry_run=False,
            )

        assert summary["n_deals"] == 2
        assert summary["n_snapshots"] >= 2
        assert summary["n_candidates"] >= 2
        assert summary["leakage_violations"] == 0

    def test_feature_store_csv_written(self, tmp_output, seed_csv):
        from bve.backtest_research.vrtx_regn_dataset_builder import build_dataset

        with (
            patch("bve.backtest_research.sec_client.SECClient.get_financials",
                  side_effect=_null_financials),
            patch("bve.backtest_research.historical_market_data_client.HistoricalMarketDataClient.get_enterprise_value",
                  side_effect=_null_market_cap),
            patch("bve.backtest_research.historical_market_data_client.HistoricalMarketDataClient.get_market_cap",
                  side_effect=_null_market_cap),
            patch("bve.backtest_research.historical_market_data_client.HistoricalMarketDataClient.is_publicly_traded",
                  return_value=False),
            patch("bve.backtest_research.clinicaltrials_client.ClinicalTrialsClient.get_trials_for_drug",
                  return_value=[]),
            patch("bve.backtest_research.clinicaltrials_client.ClinicalTrialsClient.get_highest_phase",
                  return_value=None),
            patch("bve.backtest_research.openfda_client.OpenFDAClient.is_approved",
                  return_value=False),
        ):
            build_dataset(
                acquirers=["VRTX", "REGN"],
                since_year=2010,
                snapshot_days=[90],
                min_negatives=5,
                max_negatives=10,
                output_dir=tmp_output / "curated",
                raw_dir=None,
                rnpv_config_dir=None,
                include_unverified=False,
                seed_csv=seed_csv,
                dry_run=False,
            )

        feature_store = tmp_output / "curated" / "vrtx_regn_feature_store.csv"
        assert feature_store.exists()
        rows = list(csv.DictReader(feature_store.open()))
        assert len(rows) >= 2


class TestBacktestRunnerSmoke:
    def _write_minimal_feature_store(self, path: Path) -> None:
        """Write a minimal feature store CSV for the runner to consume."""
        rows = [
            {
                "deal_id": "VRTX_ALPN_20240410",
                "acquirer_ticker": "VRTX",
                "target_ticker": "ALPN",
                "snapshot_date": "2024-01-10",
                "days_before": "90",
                "is_actual_target": "True",
                "asset_quality": "0.7",
                "acquirer_appetite": "0.6",
                "ta_overlap": "0.8",
                "size_fit": "0.65",
                "acquirer_urgency": "0.6",
                "integration_capacity": "0.65",
                "acq_cash_millions": "",
                "acq_rd_expense_ttm_millions": "",
                "tgt_market_cap_millions": "4900.0",
                "tgt_lead_asset_stage_score": "0.7",
                "tgt_n_active_trials": "3",
                "tgt_is_approved": "False",
                "source_url": "https://example.com",
                "source_published_date": "2024-01-05",
                "data_as_of_date": "2024-01-05",
                "extraction_method": "market_data_api",
                "confidence": "0.85",
                "provenance_complete": "True",
                "gaps": "",
            },
            {
                "deal_id": "VRTX_ALPN_20240410",
                "acquirer_ticker": "VRTX",
                "target_ticker": "IMVT",
                "snapshot_date": "2024-01-10",
                "days_before": "90",
                "is_actual_target": "False",
                "asset_quality": "0.6",
                "acquirer_appetite": "0.6",
                "ta_overlap": "0.7",
                "size_fit": "0.55",
                "acquirer_urgency": "0.6",
                "integration_capacity": "0.65",
                "acq_cash_millions": "",
                "acq_rd_expense_ttm_millions": "",
                "tgt_market_cap_millions": "3000.0",
                "tgt_lead_asset_stage_score": "0.75",
                "tgt_n_active_trials": "2",
                "tgt_is_approved": "False",
                "source_url": "https://example.com",
                "source_published_date": "2024-01-05",
                "data_as_of_date": "2024-01-05",
                "extraction_method": "market_data_api",
                "confidence": "0.85",
                "provenance_complete": "True",
                "gaps": "",
            },
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_runner_scores_and_produces_results(self, tmp_output):
        from bve.backtest_research.vrtx_regn_backtest_runner import BacktestRunner

        feature_store_path = tmp_output / "curated" / "vrtx_regn_feature_store.csv"
        self._write_minimal_feature_store(feature_store_path)

        runner = BacktestRunner(score_mode="approved_only")
        summary = runner.run(
            feature_store_path=feature_store_path,
            output_dir=tmp_output / "outputs",
            dry_run=False,
        )
        results_path = tmp_output / "outputs" / "vrtx_regn_backtest_results.csv"
        assert results_path.exists()
        rows = list(csv.DictReader(results_path.open()))
        assert len(rows) == 2

    def test_runner_leakage_violation_raises(self, tmp_output):
        from bve.backtest_research.leakage_guard import LeakageViolationError
        from bve.backtest_research.vrtx_regn_backtest_runner import BacktestRunner

        feature_store_path = tmp_output / "curated" / "vrtx_regn_feature_store_bad.csv"
        feature_store_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a feature store with a future source_published_date
        bad_rows = [{
            "deal_id": "X",
            "acquirer_ticker": "VRTX",
            "target_ticker": "ALPN",
            "snapshot_date": "2024-01-10",
            "days_before": "90",
            "is_actual_target": "True",
            "asset_quality": "0.7",
            "acquirer_appetite": "0.6",
            "ta_overlap": "0.8",
            "size_fit": "0.65",
            "acquirer_urgency": "0.6",
            "integration_capacity": "0.65",
            "acq_cash_millions": "",
            "acq_rd_expense_ttm_millions": "",
            "tgt_market_cap_millions": "",
            "tgt_lead_asset_stage_score": "0.7",
            "tgt_n_active_trials": "0",
            "tgt_is_approved": "False",
            "source_url": "https://example.com",
            "source_published_date": "2025-01-01",  # FUTURE — violation
            "data_as_of_date": "2024-01-01",
            "extraction_method": "market_data_api",
            "confidence": "0.85",
            "provenance_complete": "False",
            "gaps": "target_market_cap",
        }]
        with feature_store_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(bad_rows[0].keys()))
            writer.writeheader()
            writer.writerows(bad_rows)

        runner = BacktestRunner()
        with pytest.raises(LeakageViolationError):
            runner.run(
                feature_store_path=feature_store_path,
                output_dir=tmp_output / "outputs",
                dry_run=False,
            )

    def test_actual_target_gets_a_rank(self, tmp_output):
        from bve.backtest_research.vrtx_regn_backtest_runner import BacktestRunner

        feature_store_path = tmp_output / "curated" / "vrtx_regn_feature_store.csv"
        self._write_minimal_feature_store(feature_store_path)

        runner = BacktestRunner()
        runner.run(
            feature_store_path=feature_store_path,
            output_dir=tmp_output / "outputs",
            dry_run=False,
        )
        results = list(csv.DictReader(
            (tmp_output / "outputs" / "vrtx_regn_backtest_results.csv").open()
        ))
        actual = next(r for r in results if r.get("is_actual_target", "").lower() == "true")
        assert int(actual["rank"]) >= 1


class TestBucketMinimumGate:
    """Tests for the bucket minimum gate in BacktestRunner / _check_bucket_minimums."""

    def _write_bucket_csv(self, path: Path, rows: list[dict]) -> None:
        fieldnames = ["deal_id", "acquirer", "bucket_name", "bucket_type",
                      "candidate_target", "candidate_ticker", "manual_review_status"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _make_approved_rows(self, bucket: str, n: int, status: str = "approved_core") -> list[dict]:
        return [
            {"deal_id": f"{bucket}_X", "acquirer": "VRTX", "bucket_name": bucket,
             "bucket_type": "core", "candidate_target": f"Co{i}",
             "candidate_ticker": f"TICK{i}", "manual_review_status": status}
            for i in range(n)
        ]

    def test_passes_when_all_buckets_meet_minimums(self, tmp_path):
        from bve.backtest_research.vrtx_regn_backtest_runner import _check_bucket_minimums

        rows = []
        rows += self._make_approved_rows("VRTX_SEMMA_2019", 25)
        rows += self._make_approved_rows("VRTX_VIACYTE_2022", 15)
        rows += self._make_approved_rows("VRTX_EXONICS_2019", 12)
        rows += self._make_approved_rows("VRTX_ALPINE_2024", 20)
        rows += self._make_approved_rows("REGN_DECIBEL_2023", 15)

        csv_path = tmp_path / "candidate_universe_by_deal_bucket.csv"
        self._write_bucket_csv(csv_path, rows)

        counts = _check_bucket_minimums(csv_path)
        assert counts["VRTX_SEMMA_2019"] == 25
        assert counts["REGN_DECIBEL_2023"] == 15

    def test_raises_when_bucket_below_minimum(self, tmp_path):
        from bve.backtest_research.vrtx_regn_backtest_runner import (
            BucketMinimumNotMetError,
            _check_bucket_minimums,
        )

        rows = []
        rows += self._make_approved_rows("VRTX_SEMMA_2019", 10)  # below 25
        rows += self._make_approved_rows("VRTX_VIACYTE_2022", 15)
        rows += self._make_approved_rows("VRTX_EXONICS_2019", 12)
        rows += self._make_approved_rows("VRTX_ALPINE_2024", 20)
        rows += self._make_approved_rows("REGN_DECIBEL_2023", 15)

        csv_path = tmp_path / "candidate_universe_by_deal_bucket.csv"
        self._write_bucket_csv(csv_path, rows)

        with pytest.raises(BucketMinimumNotMetError, match="VRTX_SEMMA_2019"):
            _check_bucket_minimums(csv_path)

    def test_error_message_lists_all_failing_buckets(self, tmp_path):
        from bve.backtest_research.vrtx_regn_backtest_runner import (
            BucketMinimumNotMetError,
            _check_bucket_minimums,
        )

        rows = []
        rows += self._make_approved_rows("VRTX_SEMMA_2019", 5)   # below 25
        rows += self._make_approved_rows("VRTX_VIACYTE_2022", 15)
        rows += self._make_approved_rows("VRTX_EXONICS_2019", 0)  # below 12
        rows += self._make_approved_rows("VRTX_ALPINE_2024", 20)
        rows += self._make_approved_rows("REGN_DECIBEL_2023", 15)

        csv_path = tmp_path / "candidate_universe_by_deal_bucket.csv"
        self._write_bucket_csv(csv_path, rows)

        with pytest.raises(BucketMinimumNotMetError) as exc_info:
            _check_bucket_minimums(csv_path)
        msg = str(exc_info.value)
        assert "VRTX_SEMMA_2019" in msg
        assert "VRTX_EXONICS_2019" in msg
        assert "VRTX_VIACYTE_2022" not in msg

    def test_pending_rows_do_not_count_toward_minimum(self, tmp_path):
        from bve.backtest_research.vrtx_regn_backtest_runner import (
            BucketMinimumNotMetError,
            _check_bucket_minimums,
        )

        rows = []
        # 10 approved + 20 pending = only 10 approved (below 25)
        rows += self._make_approved_rows("VRTX_SEMMA_2019", 10)
        rows += self._make_approved_rows("VRTX_SEMMA_2019", 20, status="pending")
        rows += self._make_approved_rows("VRTX_VIACYTE_2022", 15)
        rows += self._make_approved_rows("VRTX_EXONICS_2019", 12)
        rows += self._make_approved_rows("VRTX_ALPINE_2024", 20)
        rows += self._make_approved_rows("REGN_DECIBEL_2023", 15)

        csv_path = tmp_path / "candidate_universe_by_deal_bucket.csv"
        self._write_bucket_csv(csv_path, rows)

        with pytest.raises(BucketMinimumNotMetError):
            _check_bucket_minimums(csv_path)

    def test_missing_csv_returns_empty_dict_with_warning(self, tmp_path):
        import warnings
        from bve.backtest_research.vrtx_regn_backtest_runner import _check_bucket_minimums

        csv_path = tmp_path / "nonexistent.csv"
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = _check_bucket_minimums(csv_path)
        assert result == {}
        assert len(w) == 1
        assert "bucket minimum check skipped" in str(w[0].message).lower()

    def test_custom_minimums_override(self, tmp_path):
        from bve.backtest_research.vrtx_regn_backtest_runner import _check_bucket_minimums

        rows = self._make_approved_rows("VRTX_SEMMA_2019", 3)
        csv_path = tmp_path / "candidate_universe_by_deal_bucket.csv"
        self._write_bucket_csv(csv_path, rows)

        # Custom minimum of 3 — should pass
        counts = _check_bucket_minimums(csv_path, minimums={"VRTX_SEMMA_2019": 3})
        assert counts["VRTX_SEMMA_2019"] == 3


class TestReportWriterSmoke:
    def test_report_written_and_nonempty(self, tmp_output):
        from bve.backtest_research.report_writer import ReportWriter

        (tmp_output / "outputs").mkdir(exist_ok=True)
        results_path = tmp_output / "outputs" / "results.csv"
        metrics_path = tmp_output / "outputs" / "metrics.csv"

        # Minimal valid CSVs
        results_path.write_text(
            "deal_id,acquirer_ticker,target_ticker,snapshot_date,days_before,"
            "is_actual_target,pair_score,log_odds,rank,n_candidates,percentile,"
            "label_is_positive,provenance_complete\n"
            "X,VRTX,ALPN,2024-01-10,90,True,0.75,-0.1,1,2,1.0,True,True\n",
            encoding="utf-8",
        )
        metrics_path.write_text(
            "acquirer,days_before,n_groups,n_total_candidates,top_1_hit_rate,"
            "top_3_hit_rate,top_5_hit_rate,top_10_hit_rate,top_decile_hit_rate,"
            "mean_percentile_rank,median_percentile_rank,mean_reciprocal_rank,"
            "auc_roc,brier_score,precision_at_5,precision_at_10,calibration_error,"
            "n_verified_deals,caveats\n"
            "VRTX,90,1,2,1.0,1.0,1.0,1.0,1.0,1.0,1.0,1.0,0.75,0.1,1.0,1.0,0.1,1,"
            "N=1 verified deals.\n",
            encoding="utf-8",
        )

        writer = ReportWriter(tmp_output / "outputs")
        paths = writer.write(results_path=results_path, metrics_path=metrics_path)
        for p in paths:
            assert p.exists()
            assert p.stat().st_size > 0

    def test_report_contains_key_sections(self, tmp_output):
        from bve.backtest_research.report_writer import ReportWriter

        (tmp_output / "outputs").mkdir(exist_ok=True)
        results_path = tmp_output / "outputs" / "results.csv"
        metrics_path = tmp_output / "outputs" / "metrics.csv"
        results_path.write_text("deal_id,label_is_positive\nX,True\n", encoding="utf-8")
        metrics_path.write_text(
            "acquirer,days_before,n_groups,n_total_candidates,top_1_hit_rate,"
            "top_3_hit_rate,top_5_hit_rate,top_10_hit_rate,top_decile_hit_rate,"
            "mean_percentile_rank,median_percentile_rank,mean_reciprocal_rank,"
            "auc_roc,brier_score,precision_at_5,precision_at_10,calibration_error,"
            "n_verified_deals,caveats\n",
            encoding="utf-8",
        )

        writer = ReportWriter(tmp_output / "outputs")
        paths = writer.write(results_path=results_path, metrics_path=metrics_path)
        report = paths[0].read_text(encoding="utf-8")
        for section in [
            "Executive Summary",
            "Leakage Audit",
            "False Positives",
            "False Negatives",
            "Research Gaps",
            "Next Data Improvements",
        ]:
            assert section in report, f"Section {section!r} missing from report"


# ---------------------------------------------------------------------------
# Block 15 tests
# ---------------------------------------------------------------------------

class TestReportBucketTable:
    """15-1: bucket gate table shows in report when bucket_csv_path provided."""

    def _write_minimal_bucket_csv(self, path: Path) -> None:
        fieldnames = ["deal_id", "acquirer", "bucket_name", "bucket_type",
                      "candidate_target", "candidate_ticker", "manual_review_status"]
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for bucket, n in [
            ("VRTX_SEMMA_2019", 34),
            ("VRTX_VIACYTE_2022", 15),
            ("VRTX_EXONICS_2019", 12),
            ("VRTX_ALPINE_2024", 20),
            ("REGN_DECIBEL_2023", 15),
        ]:
            for i in range(n):
                rows.append({
                    "deal_id": f"{bucket}_{i}",
                    "acquirer": "VRTX",
                    "bucket_name": bucket,
                    "bucket_type": "core",
                    "candidate_target": f"Co{i}",
                    "candidate_ticker": f"TICK{i}",
                    "manual_review_status": "approved_core",
                })
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_bucket_table_appears_in_report(self, tmp_output):
        from bve.backtest_research.report_writer import ReportWriter

        (tmp_output / "outputs").mkdir(exist_ok=True)
        results_path = tmp_output / "outputs" / "results.csv"
        metrics_path = tmp_output / "outputs" / "metrics.csv"
        bucket_path = tmp_output / "curated" / "candidate_universe_by_deal_bucket.csv"

        results_path.write_text("deal_id,label_is_positive\nX,True\n", encoding="utf-8")
        metrics_path.write_text(
            "acquirer,days_before,n_groups,n_total_candidates,top_1_hit_rate,"
            "top_3_hit_rate,top_5_hit_rate,top_10_hit_rate,top_decile_hit_rate,"
            "mean_percentile_rank,median_percentile_rank,mean_reciprocal_rank,"
            "auc_roc,brier_score,precision_at_5,precision_at_10,calibration_error,"
            "n_verified_deals,caveats\n",
            encoding="utf-8",
        )
        self._write_minimal_bucket_csv(bucket_path)

        writer = ReportWriter(tmp_output / "outputs")
        paths = writer.write(
            results_path=results_path,
            metrics_path=metrics_path,
            bucket_csv_path=bucket_path,
        )
        report = paths[0].read_text(encoding="utf-8")
        assert "Bucket Minimum Gate" in report
        assert "VRTX_SEMMA_2019" in report
        assert "PASS" in report

    def test_bucket_table_shows_unknown_when_no_csv(self, tmp_output):
        from bve.backtest_research.report_writer import ReportWriter

        (tmp_output / "outputs").mkdir(exist_ok=True)
        results_path = tmp_output / "outputs" / "results.csv"
        metrics_path = tmp_output / "outputs" / "metrics.csv"
        results_path.write_text("deal_id,label_is_positive\nX,True\n", encoding="utf-8")
        metrics_path.write_text(
            "acquirer,days_before,n_groups,n_total_candidates,top_1_hit_rate,"
            "top_3_hit_rate,top_5_hit_rate,top_10_hit_rate,top_decile_hit_rate,"
            "mean_percentile_rank,median_percentile_rank,mean_reciprocal_rank,"
            "auc_roc,brier_score,precision_at_5,precision_at_10,calibration_error,"
            "n_verified_deals,caveats\n",
            encoding="utf-8",
        )
        writer = ReportWriter(tmp_output / "outputs")
        paths = writer.write(results_path=results_path, metrics_path=metrics_path)
        report = paths[0].read_text(encoding="utf-8")
        assert "Bucket Minimum Gate" in report
        assert "UNKNOWN" in report

    def test_report_contains_backtest_timeline_section(self, tmp_output):
        from bve.backtest_research.report_writer import ReportWriter

        (tmp_output / "outputs").mkdir(exist_ok=True)
        results_path = tmp_output / "outputs" / "results.csv"
        metrics_path = tmp_output / "outputs" / "metrics.csv"
        results_path.write_text("deal_id,label_is_positive\nX,True\n", encoding="utf-8")
        metrics_path.write_text(
            "acquirer,days_before,n_groups,n_total_candidates,top_1_hit_rate,"
            "top_3_hit_rate,top_5_hit_rate,top_10_hit_rate,top_decile_hit_rate,"
            "mean_percentile_rank,median_percentile_rank,mean_reciprocal_rank,"
            "auc_roc,brier_score,precision_at_5,precision_at_10,calibration_error,"
            "n_verified_deals,caveats\n",
            encoding="utf-8",
        )
        writer = ReportWriter(tmp_output / "outputs")
        paths = writer.write(results_path=results_path, metrics_path=metrics_path)
        report = paths[0].read_text(encoding="utf-8")
        assert "Backtest Timeline" in report
        assert "false-positive control" in report.lower()


class TestCTGovExclusion:
    """15-2: CT.gov post-snapshot phase must not enter model inputs."""

    def test_model_input_allowed_true_for_pre_snapshot(self):
        from datetime import date
        from bve.backtest_research.trial_phase_resolver import (
            TrialPhaseResolver, TrialPhaseSource, TrialPhaseSourceType,
        )

        resolver = TrialPhaseResolver()
        result = resolver.resolve(
            asset_id="TEST:asset",
            snapshot_date=date(2023, 5, 9),
            sources=[
                TrialPhaseSource(
                    source_type=TrialPhaseSourceType.PRESS_RELEASE,
                    phase="phase_2",
                    published_date=date(2023, 4, 1),
                ),
            ],
        )
        assert result.is_trustworthy
        assert result.model_input_allowed is True

    def test_model_input_allowed_false_for_post_snapshot_ctgov(self):
        from datetime import date
        from bve.backtest_research.trial_phase_resolver import (
            TrialPhaseResolver, TrialPhaseSource, TrialPhaseSourceType,
        )

        resolver = TrialPhaseResolver()
        result = resolver.resolve(
            asset_id="TEST:asset",
            snapshot_date=date(2023, 5, 9),
            sources=[
                TrialPhaseSource(
                    source_type=TrialPhaseSourceType.CLINICALTRIALS_CURRENT,
                    phase="phase_2",
                    published_date=date(2023, 9, 10),  # AFTER snapshot
                ),
            ],
        )
        assert not result.is_trustworthy
        assert result.model_input_allowed is False

    def test_pit_audit_csv_includes_model_input_allowed_column(self, tmp_path):
        from datetime import date
        from bve.backtest_research.trial_phase_resolver import (
            TrialPhaseResolver, TrialPhaseSource, TrialPhaseSourceType,
            write_clinicaltrials_pit_audit,
        )

        resolver = TrialPhaseResolver()
        result = resolver.resolve(
            asset_id="TEST:asset",
            snapshot_date=date(2023, 5, 9),
            sources=[
                TrialPhaseSource(
                    source_type=TrialPhaseSourceType.CLINICALTRIALS_CURRENT,
                    phase="phase_2",
                    published_date=date(2023, 9, 10),
                ),
            ],
        )
        audit_path = tmp_path / "pit_audit.csv"
        write_clinicaltrials_pit_audit([result], audit_path)
        rows = list(csv.DictReader(audit_path.open(newline="", encoding="utf-8")))
        assert len(rows) == 1
        assert "model_input_allowed" in rows[0]
        assert rows[0]["model_input_allowed"] == "False"

    def test_feature_store_neutralises_post_snapshot_ctgov_phase(self):
        """When extraction_method=ct_gov_api and source date > snapshot, asset_quality=0.3."""
        from datetime import date
        from bve.backtest_research.feature_store import FeatureStore
        from bve.backtest_research.candidate_universe_builder import CandidatePair

        store = FeatureStore()

        # Build a candidate pair with a post-snapshot CT.gov source
        cand = CandidatePair(
            deal_id="TEST_DEAL",
            acquirer_ticker="VRTX",
            target_ticker="TEST",
            target_name="Test Co",
            snapshot_date="2023-05-09",
            days_before=90,
            is_actual_target=False,
            therapeutic_area="rare_disease",
            modality="small_molecule",
            lead_asset_stage="phase_2",
            is_hard_negative=True,
        )

        # Patch the target snapshot builder to return CT.gov post-snapshot data
        future_date = "2023-09-10"  # after snapshot 2023-05-09
        tgt_snap_post = {
            "lead_asset_stage_score": 0.80,  # would be high if CT.gov allowed
            "extraction_method": "ct_gov_api",
            "source_published_date": future_date,
            "data_as_of_date": future_date,
            "market_cap_millions": 50.0,
            "n_active_clinical_trials": 2,
            "lead_asset_is_approved": False,
            "source_url": "https://clinicaltrials.gov",
            "confidence": 0.50,
        }
        acq_snap = {
            "urgency_score": 0.60,
            "therapeutic_areas": "rare_disease",
            "deal_min_millions": 50.0,
            "deal_max_millions": 5000.0,
            "cash_and_equivalents_millions": 10_000.0,
            "rd_expense_ttm_millions": 2_000.0,
            "data_as_of_date": "2023-05-01",
            "source_url": "https://sec.gov",
            "extraction_method": "sec_filing_text",
            "confidence": 0.70,
        }

        snap_date = date(2023, 5, 9)
        store._acq_cache[f"VRTX_{snap_date.isoformat()}"] = acq_snap
        store._tgt_builder.build = lambda **kw: tgt_snap_post  # type: ignore[method-assign]

        row = store._build_row(cand, snap_date, {}, {})
        # CT.gov source is post-snapshot → should be neutralised to 0.3
        assert row.ctgov_phase_excluded is True
        assert row.asset_quality == 0.30

    def test_feature_store_allows_pre_snapshot_ctgov_phase(self):
        """When extraction_method=ct_gov_api and source date <= snapshot, phase is used."""
        from datetime import date
        from bve.backtest_research.feature_store import FeatureStore
        from bve.backtest_research.candidate_universe_builder import CandidatePair

        store = FeatureStore()
        cand = CandidatePair(
            deal_id="TEST_DEAL2",
            acquirer_ticker="VRTX",
            target_ticker="TEST2",
            target_name="Test Co 2",
            snapshot_date="2023-05-09",
            days_before=90,
            is_actual_target=False,
            therapeutic_area="rare_disease",
            modality="small_molecule",
            lead_asset_stage="phase_2",
            is_hard_negative=True,
        )

        pre_date = "2023-04-01"  # before snapshot 2023-05-09
        tgt_snap_pre = {
            "lead_asset_stage_score": 0.80,
            "extraction_method": "ct_gov_api",
            "source_published_date": pre_date,
            "data_as_of_date": pre_date,
            "market_cap_millions": 50.0,
            "n_active_clinical_trials": 2,
            "lead_asset_is_approved": False,
            "source_url": "https://clinicaltrials.gov",
            "confidence": 0.50,
        }
        acq_snap = {
            "urgency_score": 0.60,
            "therapeutic_areas": "rare_disease",
            "deal_min_millions": 50.0,
            "deal_max_millions": 5000.0,
            "cash_and_equivalents_millions": 10_000.0,
            "rd_expense_ttm_millions": 2_000.0,
            "data_as_of_date": "2023-05-01",
            "source_url": "https://sec.gov",
            "extraction_method": "sec_filing_text",
            "confidence": 0.70,
        }

        snap_date = date(2023, 5, 9)
        store._acq_cache[f"VRTX_{snap_date.isoformat()}"] = acq_snap
        store._tgt_builder.build = lambda **kw: tgt_snap_pre  # type: ignore[method-assign]

        row = store._build_row(cand, snap_date, {}, {})
        # Pre-snapshot CT.gov → use actual stage score
        assert row.ctgov_phase_excluded is False
        assert row.asset_quality == 0.80


class TestRegnN1Warning:
    """15-5: REGN N=1 warning appears in metrics table when n_verified_deals == 1."""

    def test_n1_warning_in_metrics_table(self):
        from bve.backtest_research.report_writer import ReportWriter

        metrics = [{
            "acquirer": "REGN",
            "days_before": "90",
            "n_groups": "1",
            "n_total_candidates": "15",
            "top_1_hit_rate": "1.0",
            "top_3_hit_rate": "1.0",
            "top_5_hit_rate": "1.0",
            "top_10_hit_rate": "1.0",
            "mean_reciprocal_rank": "1.0",
            "auc_roc": "0.95",
            "brier_score": "0.05",
            "n_verified_deals": "1",
        }]
        table = ReportWriter._format_metrics_table(metrics)
        assert "STATISTICALLY MEANINGLESS" in table
        assert "N=1" in table

    def test_no_n1_warning_when_multiple_deals(self):
        from bve.backtest_research.report_writer import ReportWriter

        metrics = [{
            "acquirer": "VRTX",
            "days_before": "90",
            "n_groups": "4",
            "n_total_candidates": "60",
            "top_1_hit_rate": "0.75",
            "top_3_hit_rate": "1.0",
            "top_5_hit_rate": "1.0",
            "top_10_hit_rate": "1.0",
            "mean_reciprocal_rank": "0.87",
            "auc_roc": "0.83",
            "brier_score": "0.12",
            "n_verified_deals": "4",
        }]
        table = ReportWriter._format_metrics_table(metrics)
        assert "STATISTICALLY MEANINGLESS" not in table

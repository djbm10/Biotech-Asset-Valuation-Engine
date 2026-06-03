"""
Tests for feature_store module — specifically no-look-ahead invariants.

These tests verify that:
  1. Feature rows do not contain label fields
  2. source_published_date and data_as_of_date are <= snapshot_date
  3. The leakage guard correctly audits feature store output
  4. Required provenance fields are present
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from bve.backtest_research.candidate_universe_builder import CandidatePair
from bve.backtest_research.feature_store import (
    FeatureStore,
    FeatureRow,
    LABEL_FIELDS,
    FEATURE_COLUMNS,
    _ta_overlap_score,
    _size_fit_score,
)
from bve.backtest_research.leakage_guard import LeakageGuard


def _make_candidate(
    target_ticker="ALPN",
    is_actual=True,
    snapshot_date="2024-01-10",
    days_before=90,
    ta="immunology",
) -> CandidatePair:
    return CandidatePair(
        deal_id="VRTX_ALPN_20240410",
        acquirer_ticker="VRTX",
        target_ticker=target_ticker,
        target_name="Test",
        snapshot_date=snapshot_date,
        days_before=days_before,
        is_actual_target=is_actual,
        therapeutic_area=ta,
        modality="biologic",
        lead_asset_stage="phase2",
        is_hard_negative=not is_actual,
    )


class TestFeatureColumnNames:
    def test_label_fields_not_in_feature_columns(self):
        """Label field names must not appear in FEATURE_COLUMNS."""
        for label in LABEL_FIELDS:
            assert label not in FEATURE_COLUMNS, \
                f"Label field {label!r} found in FEATURE_COLUMNS"

    def test_feature_columns_in_zero_one(self):
        """All feature columns are expected to produce [0,1] values."""
        row = FeatureRow(
            deal_id="X",
            acquirer_ticker="VRTX",
            target_ticker="ALPN",
            snapshot_date="2024-01-10",
            days_before=90,
            is_actual_target=True,
            asset_quality=0.7,
            acquirer_appetite=0.6,
            ta_overlap=0.8,
            size_fit=0.5,
            acquirer_urgency=0.6,
            integration_capacity=0.65,
            acq_cash_millions=5000.0,
            acq_rd_expense_ttm_millions=2000.0,
            tgt_market_cap_millions=4900.0,
            tgt_lead_asset_stage_score=0.7,
            tgt_n_active_trials=3,
            tgt_is_approved=False,
            source_url="https://example.com",
            source_published_date="2024-01-01",
            data_as_of_date="2024-01-01",
            extraction_method="market_data_api",
            confidence=0.85,
            provenance_complete=True,
        )
        for col in FEATURE_COLUMNS:
            val = getattr(row, col)
            assert 0.0 <= val <= 1.0, f"Feature {col} = {val} out of [0,1]"


class TestProvenanceInvariant:
    """All rows must have source_published_date and data_as_of_date <= snapshot_date."""

    def test_leakage_guard_passes_on_valid_row(self):
        guard = LeakageGuard()
        row = {
            "snapshot_date": "2024-01-10",
            "source_published_date": "2024-01-05",
            "data_as_of_date": "2024-01-05",
        }
        violations = guard.check_feature_row(row, date(2024, 1, 10))
        assert violations == []

    def test_leakage_guard_fails_future_source(self):
        guard = LeakageGuard()
        row = {
            "snapshot_date": "2024-01-10",
            "source_published_date": "2024-03-01",  # AFTER snapshot
            "data_as_of_date": "2024-01-01",
        }
        violations = guard.check_feature_row(row, date(2024, 1, 10))
        assert any(v.violation_type == "future_source" for v in violations)

    def test_feature_row_to_dict_no_label_fields(self):
        row = FeatureRow(
            deal_id="VRTX_ALPN_20240410",
            acquirer_ticker="VRTX",
            target_ticker="ALPN",
            snapshot_date="2024-01-10",
            days_before=90,
            is_actual_target=True,
            asset_quality=0.7,
            acquirer_appetite=0.6,
            ta_overlap=0.8,
            size_fit=0.5,
            acquirer_urgency=0.6,
            integration_capacity=0.65,
            acq_cash_millions=None,
            acq_rd_expense_ttm_millions=None,
            tgt_market_cap_millions=None,
            tgt_lead_asset_stage_score=0.5,
            tgt_n_active_trials=0,
            tgt_is_approved=False,
            source_url="https://example.com",
            source_published_date="2024-01-01",
            data_as_of_date="2024-01-01",
            extraction_method="market_data_api",
            confidence=0.70,
            provenance_complete=False,
        )
        d = row.to_dict()
        for label in LABEL_FIELDS:
            assert label not in d, f"Label field {label!r} found in FeatureRow.to_dict()"

    def test_feature_store_audit_on_mocked_rows(self):
        """FeatureStore.run_leakage_audit should detect future source in rows."""
        store = FeatureStore()
        rows = [
            FeatureRow(
                deal_id="X",
                acquirer_ticker="VRTX",
                target_ticker="ALPN",
                snapshot_date="2024-01-10",
                days_before=90,
                is_actual_target=True,
                asset_quality=0.7,
                acquirer_appetite=0.6,
                ta_overlap=0.8,
                size_fit=0.5,
                acquirer_urgency=0.6,
                integration_capacity=0.65,
                acq_cash_millions=None,
                acq_rd_expense_ttm_millions=None,
                tgt_market_cap_millions=None,
                tgt_lead_asset_stage_score=0.5,
                tgt_n_active_trials=0,
                tgt_is_approved=False,
                source_url="https://example.com",
                source_published_date="2024-03-01",  # FUTURE
                data_as_of_date="2024-01-01",
                extraction_method="market_data_api",
                confidence=0.70,
                provenance_complete=False,
            )
        ]
        audit = store.run_leakage_audit(rows)
        assert audit.has_violations


class TestTAOverlapScore:
    def test_exact_match(self):
        score = _ta_overlap_score("immunology|rare_disease", "immunology")
        assert score > 0.5

    def test_no_overlap(self):
        score = _ta_overlap_score("cardiovascular", "oncology")
        assert score <= 0.5

    def test_empty_ta(self):
        score = _ta_overlap_score("", "oncology")
        assert 0.0 <= score <= 1.0


class TestSizeFitScore:
    def test_in_range_scores_high(self):
        score = _size_fit_score(5000.0, 1000.0, 10000.0)
        assert score >= 0.75

    def test_too_large_scores_low(self):
        score = _size_fit_score(100_000.0, 100.0, 5000.0)
        assert score <= 0.25

    def test_too_small_scores_low(self):
        score = _size_fit_score(10.0, 1000.0, 5000.0)
        assert score <= 0.30

    def test_unknown_market_cap_neutral(self):
        score = _size_fit_score(None, 1000.0, 5000.0)
        assert score == 0.50

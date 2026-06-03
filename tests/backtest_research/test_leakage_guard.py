"""Tests for leakage_guard module."""
from __future__ import annotations

from datetime import date

import pytest

from bve.backtest_research.leakage_guard import (
    LeakageGuard,
    LeakageViolationError,
    Violation,
    LeakageAuditResult,
    LABEL_PATTERNS,
)


class TestCheckFeatureRow:
    def setup_method(self):
        self.guard = LeakageGuard()
        self.snap = date(2023, 5, 10)

    def test_clean_row_passes(self):
        row = {
            "source_published_date": "2023-05-01",
            "data_as_of_date": "2023-05-01",
        }
        violations = self.guard.check_feature_row(row, self.snap)
        assert violations == []

    def test_future_source_flagged(self):
        row = {
            "source_published_date": "2023-05-15",  # AFTER snapshot
            "data_as_of_date": "2023-05-01",
        }
        violations = self.guard.check_feature_row(row, self.snap)
        types = [v.violation_type for v in violations]
        assert "future_source" in types

    def test_future_data_flagged(self):
        row = {
            "source_published_date": "2023-04-01",
            "data_as_of_date": "2023-06-01",  # AFTER snapshot
        }
        violations = self.guard.check_feature_row(row, self.snap)
        types = [v.violation_type for v in violations]
        assert "future_data" in types

    def test_same_day_passes(self):
        row = {
            "source_published_date": "2023-05-10",  # equal to snapshot
            "data_as_of_date": "2023-05-10",
        }
        violations = self.guard.check_feature_row(row, self.snap)
        assert violations == []

    def test_none_dates_ignored(self):
        row = {"source_published_date": None, "data_as_of_date": None}
        violations = self.guard.check_feature_row(row, self.snap)
        assert violations == []

    def test_date_object_accepted(self):
        row = {
            "source_published_date": date(2023, 6, 1),  # after snapshot
            "data_as_of_date": date(2023, 4, 1),
        }
        violations = self.guard.check_feature_row(row, self.snap)
        assert any(v.violation_type == "future_source" for v in violations)


class TestCheckColumnNames:
    def setup_method(self):
        self.guard = LeakageGuard()

    def test_label_columns_flagged(self):
        cols = ["ticker", "actual_deal", "asset_quality", "deal_premium"]
        violations = self.guard.check_column_names(cols)
        flagged = {v.column for v in violations}
        assert "actual_deal" in flagged
        assert "deal_premium" in flagged
        assert "ticker" not in flagged
        assert "asset_quality" not in flagged

    def test_acquired_column_flagged(self):
        cols = ["is_acquired"]
        violations = self.guard.check_column_names(cols)
        assert len(violations) > 0

    def test_clean_columns_pass(self):
        cols = ["ticker", "snapshot_date", "ta_overlap", "asset_quality",
                "acquirer_urgency", "confidence"]
        violations = self.guard.check_column_names(cols)
        assert violations == []

    def test_future_column_flagged(self):
        cols = ["future_revenue_estimate"]
        violations = self.guard.check_column_names(cols)
        assert any(v.violation_type == "label_pattern" for v in violations)

    def test_outcome_column_flagged(self):
        cols = ["outcome_success"]
        violations = self.guard.check_column_names(cols)
        assert len(violations) > 0


class TestAuditDataframe:
    def setup_method(self):
        self.guard = LeakageGuard()

    def test_clean_dataframe_passes(self):
        rows = [
            {
                "ticker": "ALPN",
                "snapshot_date": "2024-01-10",
                "asset_quality": 0.7,
                "source_published_date": "2024-01-01",
                "data_as_of_date": "2024-01-01",
            }
        ]
        result = self.guard.audit_dataframe(rows)
        assert not result.has_violations
        assert result.rows_audited == 1

    def test_future_source_in_dataframe(self):
        rows = [
            {
                "snapshot_date": "2024-01-10",
                "source_published_date": "2024-02-01",  # after snapshot
                "data_as_of_date": "2024-01-01",
            }
        ]
        result = self.guard.audit_dataframe(rows)
        assert result.has_violations
        assert result.n_future_source_violations == 1

    def test_label_column_in_dataframe(self):
        rows = [
            {
                "snapshot_date": "2024-01-10",
                "actual_deal": "YES",   # label field
                "source_published_date": "2024-01-01",
                "data_as_of_date": "2024-01-01",
            }
        ]
        result = self.guard.audit_dataframe(rows)
        assert result.has_violations
        assert result.n_label_violations > 0

    def test_empty_dataframe(self):
        result = self.guard.audit_dataframe([])
        assert not result.has_violations
        assert result.rows_audited == 0

    def test_summary_format(self):
        rows = [
            {
                "snapshot_date": "2024-01-10",
                "source_published_date": "2024-02-01",
                "data_as_of_date": "2024-01-01",
            }
        ]
        result = self.guard.audit_dataframe(rows)
        summary = result.summary()
        assert "Leakage Audit" in summary
        assert "violation" in summary.lower()


class TestAssertClean:
    def setup_method(self):
        self.guard = LeakageGuard()

    def test_clean_rows_no_exception(self):
        rows = [
            {
                "snapshot_date": "2024-01-10",
                "source_published_date": "2024-01-01",
                "data_as_of_date": "2024-01-01",
            }
        ]
        result = self.guard.assert_clean(rows)
        assert not result.has_violations

    def test_violation_raises(self):
        rows = [
            {
                "snapshot_date": "2024-01-10",
                "source_published_date": "2024-03-01",  # future
                "data_as_of_date": "2024-01-01",
            }
        ]
        with pytest.raises(LeakageViolationError):
            self.guard.assert_clean(rows)

    def test_extra_label_patterns(self):
        guard = LeakageGuard(extra_label_patterns=["proprietary_label"])
        cols = ["proprietary_label_score"]
        violations = guard.check_column_names(cols)
        assert len(violations) > 0

"""Tests for snapshot_dates module."""
from __future__ import annotations

from datetime import date

import pytest

from bve.backtest_research.snapshot_dates import (
    SnapshotDate,
    compute_snapshot_dates,
    compute_all_snapshot_dates,
    DEFAULT_LOOKBACK_DAYS,
)


class TestComputeSnapshotDates:
    def test_default_windows(self):
        ann = date(2024, 4, 10)   # ALPN announcement
        snaps = compute_snapshot_dates(ann)
        assert len(snaps) == 4
        days = {s.days_before for s in snaps}
        assert days == {365, 180, 90, 30}

    def test_dates_are_before_announcement(self):
        ann = date(2024, 4, 10)
        for snap in compute_snapshot_dates(ann):
            assert snap.snapshot_date < ann

    def test_correct_dates(self):
        ann = date(2024, 4, 10)
        snaps = {s.days_before: s.snapshot_date for s in compute_snapshot_dates(ann)}
        from datetime import timedelta
        assert snaps[30] == ann - timedelta(days=30)
        assert snaps[90] == ann - timedelta(days=90)
        assert snaps[365] == ann - timedelta(days=365)

    def test_announcement_date_preserved(self):
        ann = date(2019, 9, 3)
        for snap in compute_snapshot_dates(ann, deal_id="VRTX_SEMMA"):
            assert snap.announcement_date == ann
            assert snap.deal_id == "VRTX_SEMMA"

    def test_min_date_filters(self):
        ann = date(2011, 3, 1)
        snaps = compute_snapshot_dates(ann, min_date=date(2010, 6, 1))
        # 365d before = 2010-03-01 which is before min_date → filtered
        days = {s.days_before for s in snaps}
        assert 365 not in days
        assert 180 in days   # 2010-09-01, after min_date

    def test_acquirer_target_propagated(self):
        ann = date(2023, 8, 9)
        snaps = compute_snapshot_dates(
            ann, acquirer_ticker="REGN", target_ticker="DBTX"
        )
        for s in snaps:
            assert s.acquirer_ticker == "REGN"
            assert s.target_ticker == "DBTX"

    def test_custom_windows(self):
        ann = date(2024, 1, 1)
        snaps = compute_snapshot_dates(ann, lookback_days=[60, 120])
        assert len(snaps) == 2
        assert {s.days_before for s in snaps} == {60, 120}

    def test_to_dict(self):
        snap = compute_snapshot_dates(date(2024, 4, 10), lookback_days=[90])[0]
        d = snap.to_dict()
        assert "snapshot_date" in d
        assert "announcement_date" in d
        assert "days_before" in d
        assert d["days_before"] == 90


class TestComputeAllSnapshotDates:
    def test_multiple_deals(self):
        deals = [
            {"announced_date": "2019-09-03", "acquirer_ticker": "VRTX", "target_ticker": "SEMMA"},
            {"announced_date": "2024-04-10", "acquirer_ticker": "VRTX", "target_ticker": "ALPN"},
        ]
        snaps = compute_all_snapshot_dates(deals)
        # 2 deals × 4 windows = 8 snapshots (assuming min_date doesn't filter)
        assert len(snaps) >= 4

    def test_empty_list(self):
        assert compute_all_snapshot_dates([]) == []

    def test_missing_date_skipped(self):
        deals = [{"acquirer_ticker": "VRTX"}]  # no announced_date
        assert compute_all_snapshot_dates(deals) == []

    def test_date_object_accepted(self):
        deals = [{"announced_date": date(2024, 4, 10)}]
        snaps = compute_all_snapshot_dates(deals, lookback_days=[30])
        assert len(snaps) == 1

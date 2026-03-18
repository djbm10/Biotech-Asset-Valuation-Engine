"""
Tests for bve.utils.trading_calendar.

Covers trading_days_after, is_trading_day_elapsed, count_trading_days_between,
and resolution_targets using known Mon–Fri landmarks.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.utils.trading_calendar import (
    WINDOWS_TD,
    count_trading_days_between,
    is_trading_day_elapsed,
    resolution_targets,
    trading_days_after,
)

# 2024-01-02 is a Tuesday.
_TUE = date(2024, 1, 2)
# 2024-01-05 is a Friday.
_FRI = date(2024, 1, 5)
# 2024-01-06 is a Saturday.
_SAT = date(2024, 1, 6)


class TestTradingDaysAfter:
    def test_one_trading_day_from_tuesday(self):
        # T+1 from Tuesday → Wednesday
        result = trading_days_after(_TUE, 1)
        assert result == date(2024, 1, 3)

    def test_one_trading_day_from_friday(self):
        # T+1 from Friday → Monday
        result = trading_days_after(_FRI, 1)
        assert result == date(2024, 1, 8)

    def test_five_trading_days(self):
        # T+5 from Tuesday 2024-01-02 → Tuesday 2024-01-09
        result = trading_days_after(_TUE, 5)
        assert result == date(2024, 1, 9)

    def test_zero_trading_days(self):
        result = trading_days_after(_TUE, 0)
        assert result == _TUE

    def test_accepts_datetime(self):
        dt = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
        result = trading_days_after(dt, 1)
        assert result == date(2024, 1, 3)

    def test_thirty_trading_days(self):
        # Roughly 6 calendar weeks from 2024-01-02 → around 2024-02-14
        result = trading_days_after(_TUE, 30)
        # Must be a weekday; spot-check it's after ~30 business days
        assert result > date(2024, 2, 1)
        assert result.weekday() < 5  # Mon–Fri

    def test_weekend_start_rolls_forward(self):
        # Saturday input → rolled to Monday before offset
        result = trading_days_after(_SAT, 1)
        assert result.weekday() < 5


class TestIsTradingDayElapsed:
    def test_elapsed_when_past(self):
        # Signal was 10 trading days ago; T+5 should be elapsed
        signal = _TUE
        as_of = trading_days_after(_TUE, 10)
        assert is_trading_day_elapsed(signal, 5, as_of=as_of) is True

    def test_not_elapsed_when_future(self):
        signal = _TUE
        as_of = trading_days_after(_TUE, 3)
        assert is_trading_day_elapsed(signal, 5, as_of=as_of) is False

    def test_elapsed_at_exact_boundary(self):
        signal = _TUE
        as_of = trading_days_after(_TUE, 5)
        # T+5 exactly elapsed when as_of == target date
        assert is_trading_day_elapsed(signal, 5, as_of=as_of) is True


class TestCountTradingDaysBetween:
    def test_consecutive_days(self):
        assert count_trading_days_between(date(2024, 1, 2), date(2024, 1, 3)) == 1

    def test_over_weekend(self):
        # Friday to Monday = 1 trading day
        assert count_trading_days_between(date(2024, 1, 5), date(2024, 1, 8)) == 1

    def test_two_weeks(self):
        # 2024-01-15 is MLK Day (NYSE holiday), so 2024-01-02..2024-01-16 = 9 trading days
        assert count_trading_days_between(date(2024, 1, 2), date(2024, 1, 16)) == 9

    def test_same_day(self):
        assert count_trading_days_between(_TUE, _TUE) == 0


class TestResolutionTargets:
    def test_returns_all_windows(self):
        targets = resolution_targets(_TUE)
        assert set(targets.keys()) == set(WINDOWS_TD)

    def test_windows_are_dates(self):
        targets = resolution_targets(_TUE)
        for k, v in targets.items():
            assert isinstance(v, date), f"Window {k} should be a date"

    def test_windows_ordered(self):
        targets = resolution_targets(_TUE)
        dates = [targets[w] for w in sorted(targets.keys())]
        assert dates == sorted(dates)

    def test_t1_before_t5(self):
        targets = resolution_targets(_TUE)
        assert targets[1] < targets[5] < targets[30] < targets[90] < targets[180]

"""Tests for the persistent discovery exclusion ledger."""
from __future__ import annotations

from bve.discovery.exclusion_ledger import (
    REASON_ACQUIRED,
    REASON_REJECTED,
    ExclusionLedger,
)


def test_add_and_query(tmp_path):
    led = ExclusionLedger(tmp_path / "ex.yaml")
    led.add("ZYME", REASON_REJECTED, note="partner artifact", reviewer="doug")
    assert led.is_excluded("zyme")
    assert led.excluded_tickers() == {"ZYME"}


def test_save_and_reload_round_trip(tmp_path):
    path = tmp_path / "ex.yaml"
    led = ExclusionLedger(path)
    led.add("ABC", REASON_ACQUIRED, note="bought")
    led.save()

    reloaded = ExclusionLedger(path)
    assert reloaded.is_excluded("ABC")
    rec = reloaded.get("ABC")
    assert rec.reason == REASON_ACQUIRED
    assert rec.note == "bought"


def test_reexclude_updates_not_duplicates(tmp_path):
    led = ExclusionLedger(tmp_path / "ex.yaml")
    led.add("ABC", REASON_REJECTED)
    led.add("ABC", REASON_ACQUIRED, note="changed mind")
    assert len(led.records()) == 1
    assert led.get("ABC").reason == REASON_ACQUIRED


def test_missing_file_is_empty(tmp_path):
    led = ExclusionLedger(tmp_path / "nope.yaml")
    assert led.excluded_tickers() == set()

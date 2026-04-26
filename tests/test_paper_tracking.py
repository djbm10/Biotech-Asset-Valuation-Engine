"""Tests for the paper tracking log module."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pytest

from bve.intelligence.knowledge_layer import (
    AssetRegistryEntry,
    BacktestSnapshot,
    KnowledgeStore,
)
from bve.cli.paper_tracking import (
    _compute_paper_score,
    _score_to_recommendation,
    snapshot_main,
    summary_main,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    s = KnowledgeStore(":memory:")
    yield s
    s.close()


def _ts(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# score_to_recommendation
# ---------------------------------------------------------------------------


def test_recommendation_add():
    assert _score_to_recommendation(0.70) == "add"


def test_recommendation_hold():
    assert _score_to_recommendation(0.50) == "hold"


def test_recommendation_watch():
    assert _score_to_recommendation(0.35) == "watch"


def test_recommendation_avoid():
    assert _score_to_recommendation(0.10) == "avoid"


def test_recommendation_none_returns_watch():
    assert _score_to_recommendation(None) == "watch"


# ---------------------------------------------------------------------------
# KnowledgeStore.write_paper_tracking_entry / get_paper_tracking_entries
# ---------------------------------------------------------------------------


def test_write_and_read_paper_tracking_entry(store):
    store.write_paper_tracking_entry(
        entry_id="e1",
        snapshot_date=date(2024, 1, 15),
        asset_id="asset-rlay",
        recommendation="add",
        ticker="RLAY",
        composite_score=0.72,
        mna_likelihood=0.30,
        predicted_acquirer="Pfizer",
        catalyst="Ph2 readout",
        thesis="PI3K delta first-in-class",
        risk_flags=["high_burn"],
    )
    entries = store.get_paper_tracking_entries()
    assert len(entries) == 1
    row = entries[0]
    assert row["asset_id"] == "asset-rlay"
    assert row["recommendation"] == "add"
    assert row["ticker"] == "RLAY"
    assert row["composite_score"] == pytest.approx(0.72)
    assert row["predicted_acquirer"] == "Pfizer"
    flags = json.loads(row["risk_flags"])
    assert "high_burn" in flags


def test_write_paper_tracking_upserts_on_same_date_and_asset(store):
    """INSERT OR REPLACE: second write overwrites the first for same (date, asset)."""
    store.write_paper_tracking_entry(
        entry_id="e1",
        snapshot_date=date(2024, 1, 15),
        asset_id="asset-rlay",
        recommendation="watch",
        composite_score=0.40,
    )
    store.write_paper_tracking_entry(
        entry_id="e2",
        snapshot_date=date(2024, 1, 15),
        asset_id="asset-rlay",
        recommendation="add",
        composite_score=0.75,
    )
    entries = store.get_paper_tracking_entries()
    assert len(entries) == 1
    assert entries[0]["recommendation"] == "add"
    assert entries[0]["composite_score"] == pytest.approx(0.75)


def test_get_paper_tracking_entries_filter_by_since(store):
    for d, score in [(date(2024, 1, 1), 0.5), (date(2024, 2, 1), 0.6), (date(2024, 3, 1), 0.7)]:
        store.write_paper_tracking_entry(
            entry_id=str(uuid.uuid4()),
            snapshot_date=d,
            asset_id=f"asset-{d.month}",
            recommendation="watch",
            composite_score=score,
        )
    entries = store.get_paper_tracking_entries(since=date(2024, 2, 1))
    assert len(entries) == 2
    dates = {e["snapshot_date"] for e in entries}
    assert "2024-01-01" not in dates


def test_get_paper_tracking_entries_filter_by_asset(store):
    for asset in ["asset-a", "asset-b"]:
        store.write_paper_tracking_entry(
            entry_id=str(uuid.uuid4()),
            snapshot_date=date(2024, 1, 15),
            asset_id=asset,
            recommendation="watch",
        )
    entries = store.get_paper_tracking_entries(asset_id="asset-a")
    assert len(entries) == 1
    assert entries[0]["asset_id"] == "asset-a"


def test_get_paper_tracking_entries_empty_on_no_data(store):
    entries = store.get_paper_tracking_entries()
    assert entries == []


# ---------------------------------------------------------------------------
# snapshot_main CLI integration
# ---------------------------------------------------------------------------


def test_snapshot_main_writes_entries(tmp_path):
    """snapshot_main should write one entry per asset to paper_tracking_log.

    When only composite_score is present (no valuation gap, no catalyst score,
    no science confidence), the multi-signal composite is not computable and the
    recommendation must be 'watch', not 'add'.  High model_pos alone is
    insufficient evidence for an 'add' call.
    """
    db_path = str(tmp_path / "test_ks.db")
    store = KnowledgeStore(db_path)
    ts = _ts(date(2024, 3, 1))
    store.upsert_asset_registry_entry(
        AssetRegistryEntry(asset_id="asset-1", ticker="RLAY", source="test")
    )
    store.write_backtest_snapshot(
        BacktestSnapshot(
            snapshot_id="snap-1",
            alert_id="a1",
            asset_id="asset-1",
            signal_date=date(2024, 3, 1),
            composite_score=0.80,
            created_at=ts,
        )
    )
    store.close()

    snapshot_main(["--db", db_path, "--date", "2024-03-15"])

    store2 = KnowledgeStore(db_path)
    entries = store2.get_paper_tracking_entries()
    store2.close()

    assert len(entries) == 1
    assert entries[0]["asset_id"] == "asset-1"
    # model_pos alone → insufficient_data → capped at "watch"
    assert entries[0]["recommendation"] == "watch"
    assert entries[0]["ticker"] == "RLAY"


def test_snapshot_main_writes_add_when_all_signals_present(tmp_path):
    """When all corroborating signals are present with high values, 'add' is written."""
    db_path = str(tmp_path / "test_ks.db")
    store = KnowledgeStore(db_path)
    ts = _ts(date(2024, 3, 1))
    store.upsert_asset_registry_entry(
        AssetRegistryEntry(asset_id="asset-2", ticker="ALNY", source="test")
    )
    store.write_backtest_snapshot(
        BacktestSnapshot(
            snapshot_id="snap-2",
            alert_id="a2",
            asset_id="asset-2",
            signal_date=date(2024, 3, 1),
            composite_score=0.90,
            mispricing_score=0.85,
            catalyst_score=0.80,
            extraction_confidence=0.75,
            created_at=ts,
        )
    )
    store.close()

    snapshot_main(["--db", db_path, "--date", "2024-03-15"])

    store2 = KnowledgeStore(db_path)
    entries = store2.get_paper_tracking_entries()
    store2.close()

    assert len(entries) == 1
    assert entries[0]["recommendation"] == "add"


def test_snapshot_main_dry_run_does_not_write(tmp_path, capsys):
    """--dry-run should not modify the database."""
    db_path = str(tmp_path / "test_ks.db")
    store = KnowledgeStore(db_path)
    ts = _ts(date(2024, 3, 1))
    store.upsert_asset_registry_entry(
        AssetRegistryEntry(asset_id="asset-1", ticker="RLAY", source="test")
    )
    store.write_backtest_snapshot(
        BacktestSnapshot(
            snapshot_id="snap-1",
            alert_id="a1",
            asset_id="asset-1",
            signal_date=date(2024, 3, 1),
            composite_score=0.80,
            created_at=ts,
        )
    )
    store.close()

    snapshot_main(["--db", db_path, "--date", "2024-03-15", "--dry-run"])

    store2 = KnowledgeStore(db_path)
    entries = store2.get_paper_tracking_entries()
    store2.close()

    assert entries == []
    output = capsys.readouterr().out
    assert "DRY-RUN" in output


def test_snapshot_main_empty_db_prints_message(tmp_path, capsys):
    """snapshot_main on an empty store should print a no-signal message."""
    db_path = str(tmp_path / "empty.db")
    store = KnowledgeStore(db_path)
    store.close()

    snapshot_main(["--db", db_path, "--date", "2024-03-15"])

    output = capsys.readouterr().out
    assert "No backtest snapshots" in output


# ---------------------------------------------------------------------------
# summary_main CLI integration
# ---------------------------------------------------------------------------


def test_summary_main_prints_entries(tmp_path, capsys):
    """summary_main should print the tracking table with headers."""
    from datetime import date as _date
    db_path = str(tmp_path / "test_ks.db")
    store = KnowledgeStore(db_path)
    today = _date.today()
    store.write_paper_tracking_entry(
        entry_id="e1",
        snapshot_date=today,
        asset_id="asset-1",
        recommendation="add",
        ticker="RLAY",
        composite_score=0.80,
    )
    store.close()

    summary_main(["--db", db_path, "--days", "7"])

    output = capsys.readouterr().out
    assert today.isoformat() in output
    assert "asset-1" in output
    assert "RLAY" in output
    assert "add" in output


def test_summary_main_empty_db_prints_no_entries(tmp_path, capsys):
    """summary_main on an empty store should print a no-entries message."""
    db_path = str(tmp_path / "empty.db")
    store = KnowledgeStore(db_path)
    store.close()

    summary_main(["--db", db_path, "--days", "30"])

    output = capsys.readouterr().out
    assert "No paper tracking entries" in output


# ---------------------------------------------------------------------------
# _compute_paper_score — composite multi-signal scoring
# ---------------------------------------------------------------------------


class _MockSnap:
    """Minimal stand-in for BacktestSnapshot with configurable fields."""

    def __init__(self, composite_score=None, mispricing_score=None,
                 catalyst_score=None, extraction_confidence=None):
        self.composite_score = composite_score
        self.mispricing_score = mispricing_score
        self.catalyst_score = catalyst_score
        self.extraction_confidence = extraction_confidence


def test_compute_paper_score_insufficient_data_when_all_signals_missing():
    """When only composite_score is present, recommendation must NOT be 'add'
    — insufficient_data flag must be set and recommendation capped at 'watch'."""
    snap = _MockSnap(composite_score=0.90)
    score, rec, flags = _compute_paper_score(snap)
    assert rec != "add", "High composite_score alone must not produce 'add'"
    assert rec == "watch"
    assert "insufficient_data" in flags


def test_compute_paper_score_all_signals_high_produces_add():
    """Full signal set with high values → 'add' recommendation."""
    snap = _MockSnap(composite_score=0.90, mispricing_score=0.85,
                     catalyst_score=0.80, extraction_confidence=0.75)
    score, rec, flags = _compute_paper_score(snap)
    assert rec == "add"
    assert "insufficient_data" not in flags


def test_compute_paper_score_all_signals_low_produces_avoid():
    """Full signal set with low values → 'avoid' recommendation."""
    snap = _MockSnap(composite_score=0.10, mispricing_score=0.05,
                     catalyst_score=0.08, extraction_confidence=0.10)
    score, rec, flags = _compute_paper_score(snap)
    assert rec == "avoid"
    assert "low_score" in flags


def test_compute_paper_score_none_all_signals_returns_watch():
    """All-None snapshot → None score + watch recommendation."""
    snap = _MockSnap()
    score, rec, flags = _compute_paper_score(snap)
    assert score is None
    assert rec == "watch"
    assert "insufficient_data" in flags


def test_compute_paper_score_partial_signals_noted_in_flags():
    """When some corroborating signals are absent, flag is recorded."""
    snap = _MockSnap(composite_score=0.70, mispricing_score=0.80)
    score, rec, flags = _compute_paper_score(snap)
    # catalyst_score and extraction_confidence are missing → flagged
    missing_flag = next((f for f in flags if f.startswith("missing_signals:")), None)
    assert missing_flag is not None
    assert "catalyst_score" in missing_flag
    assert "science_confidence" in missing_flag


def test_compute_paper_score_composite_formula():
    """Verify composite formula: 0.45*model + 0.25*valuation + 0.20*catalyst + 0.10*confidence."""
    snap = _MockSnap(composite_score=0.80, mispricing_score=0.60,
                     catalyst_score=0.50, extraction_confidence=1.00)
    expected = round(0.45 * 0.80 + 0.25 * 0.60 + 0.20 * 0.50 + 0.10 * 1.00, 6)
    score, rec, flags = _compute_paper_score(snap)
    assert score == pytest.approx(expected, abs=1e-5)


def test_compute_paper_score_high_model_only_stays_watch_not_add():
    """Regression: snapshot_main must NOT write 'add' when only composite_score=0.95
    and no valuation gap / catalyst / confidence data is present."""
    snap = _MockSnap(composite_score=0.95)
    score, rec, flags = _compute_paper_score(snap)
    assert rec == "watch"
    assert "insufficient_data" in flags

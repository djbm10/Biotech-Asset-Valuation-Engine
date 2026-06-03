"""Tests for M&A auto-log wiring (Blocks A, B, C).

Tests that:
  A) _run_mna_scan() has persist_daily_snapshots=True
  B) _log_acquirer_fit_predictions_from_mna_result() groups by acquirer correctly
  C) bve-ma-grade CLI handles empty store gracefully
"""
from __future__ import annotations

import types
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Block A: persist_daily_snapshots flag
# ---------------------------------------------------------------------------

def test_run_mna_scan_has_persist_daily_snapshots_true(tmp_path):
    """MAProbabilityConfig built in _run_mna_scan must have persist_daily_snapshots=True."""
    captured_configs = []

    def fake_scanner(knowledge_store=None, config=None, **kwargs):
        captured_configs.append(config)
        mock = MagicMock()
        mock.scan_watchlist.return_value = MagicMock(rows=[], snapshots_written=0)
        return mock

    from bve.ops import weekly_runner

    with patch.object(Path, "exists", return_value=True), \
         patch("bve.intelligence.ma_probability.MAProbabilityScanner", side_effect=fake_scanner), \
         patch("bve.pipeline.watchlist_runner.WatchlistAsset", MagicMock):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(str(tmp_path / "test.db"))
        weekly_runner._run_mna_scan(store, top_n=5)

    assert len(captured_configs) >= 1
    config = captured_configs[0]
    assert config.persist_daily_snapshots is True, (
        "persist_daily_snapshots must be True to enable auto-logging"
    )


# ---------------------------------------------------------------------------
# Block B: acquirer-fit log grouping
# ---------------------------------------------------------------------------

def _make_mna_row(asset_id, ticker, acquirer_id, fit_score, rank=1, ta="oncology", stage="phase_2"):
    row = types.SimpleNamespace(
        asset_id=asset_id,
        ticker=ticker,
        best_acquirer_id=acquirer_id,
        best_acquirer_fit_score=fit_score,
        rank=rank,
        therapeutic_area=ta,
        stage=stage,
    )
    return row


def test_log_acquirer_fit_groups_by_acquirer(tmp_path):
    """Helper correctly groups rows by best_acquirer_id and logs separately."""
    from bve.ops.weekly_runner import _log_acquirer_fit_predictions_from_mna_result
    from bve.intelligence.acquirer_fit_log import get_fit_predictions

    rows = [
        _make_mna_row("asset_a", "AAA", "pfizer", 0.85),
        _make_mna_row("asset_b", "BBB", "pfizer", 0.72),
        _make_mna_row("asset_c", "CCC", "abbvie", 0.91),
    ]
    result = types.SimpleNamespace(rows=rows)

    store_path = tmp_path / "acquirer_fit_log.db"
    # Patch the store path used in the runner
    from bve.ops import weekly_runner
    with patch.object(weekly_runner, "DB_PATH", tmp_path / "ops.db"):
        n = _log_acquirer_fit_predictions_from_mna_result(result)

    assert n == 3  # 2 pfizer + 1 abbvie

    pfizer_recs = get_fit_predictions(store_path, acquirer_id="pfizer")
    abbvie_recs = get_fit_predictions(store_path, acquirer_id="abbvie")

    assert len(pfizer_recs) == 2
    assert len(abbvie_recs) == 1
    # Pfizer rows re-ranked by fit_score desc: asset_a (0.85) = rank 1, asset_b (0.72) = rank 2
    pfizer_map = {r.asset_id: r for r in pfizer_recs}
    assert pfizer_map["asset_a"].rank == 1
    assert pfizer_map["asset_b"].rank == 2


def test_log_acquirer_fit_empty_rows_returns_zero(tmp_path):
    """Helper returns 0 when result has no rows."""
    from bve.ops.weekly_runner import _log_acquirer_fit_predictions_from_mna_result

    result = types.SimpleNamespace(rows=[])
    from bve.ops import weekly_runner
    with patch.object(weekly_runner, "DB_PATH", tmp_path / "ops.db"):
        n = _log_acquirer_fit_predictions_from_mna_result(result)
    assert n == 0


def test_log_acquirer_fit_skips_rows_with_no_acquirer(tmp_path):
    """Rows where best_acquirer_id is None are skipped."""
    from bve.ops.weekly_runner import _log_acquirer_fit_predictions_from_mna_result

    rows = [
        _make_mna_row("asset_a", "AAA", None, 0.5),  # no acquirer
        _make_mna_row("asset_b", "BBB", "roche", 0.8),
    ]
    result = types.SimpleNamespace(rows=rows)
    from bve.ops import weekly_runner
    with patch.object(weekly_runner, "DB_PATH", tmp_path / "ops.db"):
        n = _log_acquirer_fit_predictions_from_mna_result(result)
    assert n == 1


def test_log_acquirer_fit_overwrite_same_date(tmp_path):
    """Running twice on the same date replaces, not appends."""
    from bve.ops.weekly_runner import _log_acquirer_fit_predictions_from_mna_result
    from bve.intelligence.acquirer_fit_log import get_fit_predictions

    rows = [_make_mna_row("asset_a", "AAA", "merck", 0.90)]
    result = types.SimpleNamespace(rows=rows)

    from bve.ops import weekly_runner
    with patch.object(weekly_runner, "DB_PATH", tmp_path / "ops.db"):
        _log_acquirer_fit_predictions_from_mna_result(result)
        _log_acquirer_fit_predictions_from_mna_result(result)  # second run

    store_path = tmp_path / "acquirer_fit_log.db"
    recs = get_fit_predictions(store_path, acquirer_id="merck")
    # overwrite_same_date=True so only 1 record, not 2
    assert len(recs) == 1


# ---------------------------------------------------------------------------
# Block C: bve-ma-grade empty store
# ---------------------------------------------------------------------------

def test_ma_grade_empty_store_exits_cleanly(tmp_path, capsys):
    """CLI exits cleanly (no error) when the store exists but has zero snapshots."""
    from bve.intelligence.knowledge_layer import KnowledgeStore

    db_path = tmp_path / "ops.db"
    store = KnowledgeStore(str(db_path))
    store.close()

    from bve.cli.ma_grade import main

    with patch("sys.argv", ["bve-ma-grade", "--db", str(db_path),
                            "--deal-universe",
                            "research/mna/deal_universe_2020_2026.yaml"]):
        main()  # should not raise

    captured = capsys.readouterr()
    assert "No M&A probability snapshots" in captured.out


def test_ma_grade_missing_db_exits_with_error(tmp_path, capsys):
    """CLI exits with error message when db does not exist."""
    from bve.cli.ma_grade import main

    with patch("sys.argv", ["bve-ma-grade", "--db", str(tmp_path / "nonexistent.db")]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1


def test_ma_grade_prints_header(tmp_path, capsys):
    """CLI prints the standard report header."""
    from bve.intelligence.knowledge_layer import KnowledgeStore

    db_path = tmp_path / "ops.db"
    KnowledgeStore(str(db_path)).close()

    from bve.cli.ma_grade import main

    with patch("sys.argv", ["bve-ma-grade", "--db", str(db_path),
                            "--deal-universe",
                            "research/mna/deal_universe_2020_2026.yaml"]):
        main()

    captured = capsys.readouterr()
    assert "BVE M&A Prediction Grade Report" in captured.out
    assert "KnowledgeStore" in captured.out

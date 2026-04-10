from __future__ import annotations

from datetime import date


def test_rows_from_store_resolves_latest_snapshot_on_or_before(tmp_path) -> None:
    from bve.analysis.implied_pos_batch import ScreenRow
    from bve.cli.universe_screen import _format_table, _rows_from_store
    from bve.intelligence.knowledge_layer import KnowledgeStore

    db_path = tmp_path / "snapshots.db"
    store = KnowledgeStore(db_path)
    try:
        store.write_screen_snapshots(
            [
                ScreenRow(
                    ticker="VKTX",
                    program_label="VKTX P2",
                    stage="phase_2",
                    ta="metabolic",
                    model_pos=0.55,
                    implied_pos=0.40,
                    spread_pp=15.0,
                    rnpv_millions=500.0,
                    ev_millions=300.0,
                    acquisition_discount_pct=66.7,
                    next_catalyst="Phase 2 readout",
                    catalyst_date=None,
                    days_to_catalyst=None,
                    single_asset=True,
                    approximation_warning=None,
                    data_date=date(2026, 3, 1),
                )
            ],
            snapshot_date=date(2026, 3, 1),
        )
    finally:
        store.close()

    resolved_date, rows = _rows_from_store("2026-03-15", db_path=db_path)

    assert resolved_date == date(2026, 3, 1)
    assert len(rows) == 1
    assert rows[0].ticker == "VKTX"
    assert rows[0].data_date == date(2026, 3, 1)

    rendered = _format_table(rows, use_color=False)
    assert "2026-03-01" in rendered

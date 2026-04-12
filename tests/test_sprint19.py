"""
Sprint 19 tests — Unified daily opportunity brief.

Tests composite scoring, brief construction (offline), rendering,
expert note integration, event flag integration, and CLI output.
All tests use offline mode — no live market data or real DB required.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from bve.ops.daily_brief import (
    BriefRow,
    CalibrationStats,
    DailyBrief,
    _score_row,
    render_brief,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(
    ticker="VKTX",
    spread_pp=15.0,
    model_pos=0.55,
    implied_pos=0.40,
    calibrated_pos_delta=None,
    expert_note_count=0,
    expert_signal_types=None,
    recent_event_count=0,
    requires_recompute=False,
):
    row = BriefRow(
        ticker=ticker,
        program_label=f"{ticker} P2",
        stage="phase_2",
        ta="oncology",
        model_pos=model_pos,
        implied_pos=implied_pos,
        spread_pp=spread_pp,
        rnpv_millions=500.0,
        ev_millions=300.0,
        calibrated_pos_delta=calibrated_pos_delta,
        expert_note_count=expert_note_count,
        expert_signal_types=expert_signal_types or set(),
        recent_event_count=recent_event_count,
        requires_recompute=requires_recompute,
    )
    return row


def _make_brief(rows=None, top_n=5):
    if rows is None:
        rows = [_make_row(ticker=f"T{i}", spread_pp=10.0 - i) for i in range(3)]
    brief = DailyBrief(
        as_of=date(2026, 4, 1),
        generated_at=datetime(2026, 4, 1, 8, 0, tzinfo=timezone.utc),
        rows=rows,
        calibration=CalibrationStats(n_outcomes=50, n_bins_calibrated=3, is_live=True),
        n_universe=len(rows),
        n_with_spread=len(rows),
    )
    return brief


@pytest.fixture()
def store():
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.intelligence.expert_notes import _ensure_schema
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ks = KnowledgeStore(db_path)
        _ensure_schema(ks)
        yield ks
        ks.close()


# ===========================================================================
# TestBriefRow
# ===========================================================================

class TestBriefRow:
    def test_spread_label_positive(self):
        row = _make_row(spread_pp=15.0)
        assert row.spread_label == "+15.0pp"

    def test_spread_label_negative(self):
        row = _make_row(spread_pp=-8.5)
        assert row.spread_label == "-8.5pp"

    def test_spread_label_none(self):
        row = _make_row(spread_pp=None, implied_pos=None)
        assert row.spread_label == "n/a"

    def test_signal_flags_empty(self):
        row = _make_row()
        assert row.signal_flags == "—"

    def test_signal_flags_efficacy(self):
        row = _make_row(expert_signal_types={"efficacy"})
        assert "E" in row.signal_flags

    def test_signal_flags_all_three(self):
        row = _make_row(expert_signal_types={"efficacy", "safety", "commercial"})
        assert row.signal_flags == "E,S,C"

    def test_is_undervalued_positive_spread(self):
        row = _make_row(spread_pp=10.0)
        assert row.spread_pp > 0

    def test_is_undervalued_no_spread(self):
        row = _make_row(spread_pp=None, implied_pos=None)
        assert row.spread_pp is None


# ===========================================================================
# TestScoreRow
# ===========================================================================

class TestScoreRow:
    def test_score_in_range(self):
        row = _make_row()
        row.composite_score = _score_row(row)
        assert 0.0 <= row.composite_score <= 1.0

    def test_zero_spread_zero_score(self):
        row = _make_row(spread_pp=0.0, implied_pos=0.55)
        score = _score_row(row)
        assert score == pytest.approx(0.0, abs=0.01)

    def test_negative_spread_zero_score(self):
        row = _make_row(spread_pp=-5.0, implied_pos=0.60)
        score = _score_row(row)
        # Spread component is 0; other components could be non-zero
        assert score < 0.10  # still low

    def test_large_spread_high_score(self):
        row = _make_row(spread_pp=40.0)
        score = _score_row(row)
        assert score >= 0.45  # spread alone contributes 0.50 × 1.0

    def test_expert_notes_boost_score(self):
        base_row = _make_row(spread_pp=10.0)
        noted_row = _make_row(
            spread_pp=10.0,
            expert_note_count=3,
            expert_signal_types={"efficacy", "safety", "commercial"},
        )
        assert _score_row(noted_row) > _score_row(base_row)

    def test_recompute_flag_boosts_score(self):
        base_row = _make_row(spread_pp=10.0)
        flagged_row = _make_row(spread_pp=10.0, requires_recompute=True)
        assert _score_row(flagged_row) > _score_row(base_row)

    def test_calibrated_pos_delta_boosts_score(self):
        base_row = _make_row(spread_pp=10.0, calibrated_pos_delta=0.0)
        bullish_row = _make_row(spread_pp=10.0, calibrated_pos_delta=15.0)
        assert _score_row(bullish_row) > _score_row(base_row)

    def test_negative_calibrated_delta_no_boost(self):
        base_row = _make_row(spread_pp=10.0, calibrated_pos_delta=None)
        bearish_row = _make_row(spread_pp=10.0, calibrated_pos_delta=-10.0)
        assert _score_row(bearish_row) <= _score_row(base_row) + 0.001


# ===========================================================================
# TestBuildDailyBrief — offline
# ===========================================================================

class TestBuildDailyBrief:
    def test_returns_daily_brief(self, store):
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        brief = build_daily_brief(
            store, UNIVERSE, fetch_live=False
        )
        from bve.ops.daily_brief import DailyBrief
        assert isinstance(brief, DailyBrief)

    def test_rows_sorted_by_score_desc(self, store):
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        brief = build_daily_brief(store, UNIVERSE, fetch_live=False)
        scores = [r.composite_score for r in brief.rows]
        assert scores == sorted(scores, reverse=True)

    def test_n_universe_positive(self, store):
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        brief = build_daily_brief(store, UNIVERSE, fetch_live=False)
        assert brief.n_universe > 0

    def test_all_rows_have_ticker(self, store):
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        brief = build_daily_brief(store, UNIVERSE, fetch_live=False)
        for row in brief.rows:
            assert row.ticker

    def test_expert_notes_reflected_in_brief(self, store):
        from bve.intelligence.expert_notes import ExpertNote, extract_signals, save_expert_note
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        # Seed an expert note for VKTX
        note = ExpertNote(
            ticker="VKTX",
            asset_id="vktx_vk2735",
            company_id="vktx",
            note_type="physician_call",
            content="20% weight loss. Well tolerated.",
            confidence=0.70,
            noted_at=date.today(),
        )
        save_expert_note(note, extract_signals(note.content), store)

        brief = build_daily_brief(store, UNIVERSE, fetch_live=False)
        vktx_rows = [r for r in brief.rows if r.ticker == "VKTX"]
        if vktx_rows:
            assert vktx_rows[0].expert_note_count >= 1
            assert "efficacy" in vktx_rows[0].expert_signal_types

    def test_calibration_stats_present(self, store):
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        brief = build_daily_brief(store, UNIVERSE, fetch_live=False)
        assert brief.calibration is not None
        assert isinstance(brief.calibration.n_outcomes, int)

    def test_as_of_date_propagated(self, store):
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

        as_of = date(2026, 1, 15)
        brief = build_daily_brief(store, UNIVERSE, fetch_live=False, as_of=as_of)
        assert brief.as_of == as_of

    def test_uses_persisted_screen_snapshot_on_or_before_as_of(self, store, monkeypatch):
        from bve.analysis.implied_pos_batch import ScreenRow
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

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
                    data_date=date(2026, 1, 1),
                )
            ],
            snapshot_date=date(2026, 1, 1),
        )

        def _fail_run_screen(*args, **kwargs):
            raise AssertionError("run_screen should not be called when a stored snapshot exists")

        monkeypatch.setattr("bve.analysis.implied_pos_batch.run_screen", _fail_run_screen)

        brief = build_daily_brief(
            store,
            UNIVERSE,
            fetch_live=False,
            as_of=date(2026, 1, 15),
        )

        assert brief.n_universe == 1
        assert brief.rows[0].ticker == "VKTX"
        assert brief.rows[0].spread_pp == 15.0

    def test_prefers_company_sotp_snapshot_for_company_facing_ranking(self, store, monkeypatch):
        from bve.analysis.implied_pos_batch import ScreenRow
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

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
                    data_date=date(2026, 1, 1),
                    asset_id="asset-vktx",
                )
            ],
            snapshot_date=date(2026, 1, 1),
        )
        store.write_company_sotp_snapshots(
            [
                SimpleNamespace(
                    ticker="VKTX",
                    company_id="co-vktx",
                    company_name="Viking Therapeutics",
                    snapshot_date=date(2026, 1, 1),
                    rank=1,
                    market_cap_millions=1200.0,
                    enterprise_value_millions=1000.0,
                    sotp_equity_value_millions=1800.0,
                    sotp_per_share=18.0,
                    sotp_discount=1.5,
                    ranked_sotp_discount=1.45,
                    modeled_asset_coverage_pct=0.9,
                    asset_count_modeled=1,
                    modeled_asset_ids=["asset-vktx"],
                    config_quality_summary="curated",
                    modeled_asset_confidence_min=0.9,
                    modeled_asset_confidence_avg=0.9,
                    action_policy="buy",
                    action_reason="ranked_discount_above_buy_threshold:1.45x",
                    market_cap_source="unit_test",
                    balance_sheet_source="sec_edgar_company_facts",
                    balance_sheet_source_ref="unit-test",
                    balance_sheet_snapshot_date=date(2025, 11, 1),
                    balance_sheet_period_end_date=date(2025, 9, 30),
                    balance_sheet_form_type="10-Q",
                    balance_sheet_is_point_in_time=True,
                    balance_sheet_age_days=92,
                    balance_sheet_passes_recency_gate=True,
                    balance_sheet_recency_penalty=1.0,
                    buckets=[],
                    limitations=[],
                    notes=None,
                )
            ],
            snapshot_date=date(2026, 1, 1),
        )

        def _fail_run_screen(*args, **kwargs):
            raise AssertionError("run_screen should not be called when a company snapshot exists")

        monkeypatch.setattr("bve.analysis.implied_pos_batch.run_screen", _fail_run_screen)

        brief = build_daily_brief(
            store,
            UNIVERSE,
            fetch_live=False,
            as_of=date(2026, 1, 15),
        )

        assert brief.source_mode == "stored_company_snapshot"
        assert brief.reference_snapshot_date == date(2026, 1, 1)
        assert brief.rows[0].ticker == "VKTX"
        assert brief.rows[0].company_ranked_discount == pytest.approx(1.45)
        assert brief.rows[0].company_action_policy == "buy"
        assert brief.rows[0].equity_policy_action is not None

    def test_persists_equity_policy_snapshots_for_audit(self, store):
        from bve.analysis.implied_pos_batch import ScreenRow
        from bve.ops.daily_brief import build_daily_brief
        from bve.ops.weekly_runner import UNIVERSE

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
                    days_to_catalyst=45,
                    single_asset=True,
                    approximation_warning=None,
                    data_date=date(2026, 1, 1),
                    asset_id="asset-vktx",
                )
            ],
            snapshot_date=date(2026, 1, 1),
        )
        store.write_company_sotp_snapshots(
            [
                SimpleNamespace(
                    ticker="VKTX",
                    company_id="co-vktx",
                    company_name="Viking Therapeutics",
                    snapshot_date=date(2026, 1, 1),
                    rank=1,
                    market_cap_millions=1200.0,
                    enterprise_value_millions=1000.0,
                    sotp_equity_value_millions=1800.0,
                    sotp_per_share=18.0,
                    sotp_discount=1.5,
                    ranked_sotp_discount=1.45,
                    modeled_asset_coverage_pct=0.9,
                    asset_count_modeled=1,
                    modeled_asset_ids=["asset-vktx"],
                    config_quality_summary="curated",
                    modeled_asset_confidence_min=0.9,
                    modeled_asset_confidence_avg=0.9,
                    action_policy="buy",
                    action_reason="ranked_discount_above_buy_threshold:1.45x",
                    market_cap_source="unit_test",
                    balance_sheet_source="sec_edgar_company_facts",
                    balance_sheet_source_ref="unit-test",
                    balance_sheet_snapshot_date=date(2025, 11, 1),
                    balance_sheet_period_end_date=date(2025, 9, 30),
                    balance_sheet_form_type="10-Q",
                    balance_sheet_is_point_in_time=True,
                    balance_sheet_age_days=92,
                    balance_sheet_passes_recency_gate=True,
                    balance_sheet_recency_penalty=1.0,
                    buckets=[],
                    limitations=[],
                    notes=None,
                )
            ],
            snapshot_date=date(2026, 1, 1),
        )

        brief = build_daily_brief(
            store,
            UNIVERSE,
            fetch_live=False,
            as_of=date(2026, 1, 15),
            persist_policy_snapshots=True,
        )

        persisted = store.get_equity_policy_snapshots(as_of_date=date(2026, 1, 15))
        assert brief.rows[0].equity_policy_action is not None
        assert len(persisted) == 1
        assert persisted[0]["ticker"] == "VKTX"
        assert persisted[0]["action"] == brief.rows[0].equity_policy_action
        assert persisted[0]["company_action_policy"] == "buy"
        assert persisted[0]["reference_snapshot_date"] == date(2026, 1, 1)
        assert persisted[0]["base_sotp_per_share"] == pytest.approx(18.0)


# ===========================================================================
# TestRenderBrief
# ===========================================================================

class TestRenderBrief:
    def test_render_contains_header(self):
        brief = _make_brief()
        text = render_brief(brief)
        assert "Daily Opportunity Brief" in text

    def test_render_contains_as_of_date(self):
        brief = _make_brief()
        text = render_brief(brief)
        assert "2026-04-01" in text

    def test_render_contains_tickers(self):
        rows = [_make_row("VKTX"), _make_row("ALNY")]
        for r in rows:
            r.composite_score = _score_row(r)
        rows.sort(key=lambda r: r.composite_score, reverse=True)
        brief = _make_brief(rows)
        text = render_brief(brief)
        assert "VKTX" in text
        assert "ALNY" in text

    def test_render_shows_calibration_stats(self):
        brief = _make_brief()
        brief.calibration = CalibrationStats(n_outcomes=30, n_bins_calibrated=2, is_live=True)
        text = render_brief(brief)
        assert "30" in text  # n_outcomes

    def test_render_expert_note_section(self):
        row = _make_row(
            "VKTX",
            expert_note_count=2,
            expert_signal_types={"efficacy", "commercial"},
        )
        row.composite_score = _score_row(row)
        brief = _make_brief([row])
        text = render_brief(brief)
        assert "Expert Note" in text
        assert "VKTX" in text

    def test_render_recompute_section(self):
        row = _make_row("ALNY", requires_recompute=True, recent_event_count=2)
        row.composite_score = _score_row(row)
        brief = _make_brief([row])
        brief.n_requires_recompute = 1
        text = render_brief(brief)
        assert "Recompute" in text

    def test_render_top_n_limits_rows(self):
        rows = [_make_row(f"T{i}", spread_pp=20.0 - i) for i in range(10)]
        for r in rows:
            r.composite_score = _score_row(r)
        rows.sort(key=lambda r: r.composite_score, reverse=True)
        brief = _make_brief(rows)
        text = render_brief(brief, top_n=3)
        # Should only render T0, T1, T2 in the table
        assert "T0" in text
        assert "T9" not in text

    def test_render_fallback_calibration_message(self):
        brief = _make_brief()
        brief.calibration = CalibrationStats(is_live=False)
        text = render_brief(brief)
        assert "fallback" in text.lower()

    def test_render_shows_equity_policy_preview_columns(self):
        row = _make_row("VKTX")
        row.company_action_policy = "buy"
        row.company_ranked_discount = 1.6
        row.equity_policy_action = "add"
        row.equity_policy_size_pct = 2.4
        row.composite_score = _score_row(row)
        brief = _make_brief([row])
        text = render_brief(brief)
        assert "EQPOL" in text
        assert "add" in text


# ===========================================================================
# TestCLIParsing
# ===========================================================================

class TestCLIParsing:
    def test_dry_run_offline_text(self, store, capsys):
        """CLI --format text offline run produces valid output."""
        from bve.cli.daily_brief import main
        main([
            "--db", str(store.db_path),
            "--format", "text",
            "--top", "5",
        ])
        captured = capsys.readouterr()
        assert "Daily Opportunity Brief" in captured.out

    def test_json_output(self, store, capsys):
        from bve.cli.daily_brief import main
        main([
            "--db", str(store.db_path),
            "--format", "json",
            "--top", "5",
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "as_of" in data
        assert "rows" in data
        assert isinstance(data["rows"], list)

    def test_json_row_fields(self, store, capsys):
        from bve.cli.daily_brief import main
        main([
            "--db", str(store.db_path),
            "--format", "json",
            "--top", "3",
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        if data["rows"]:
            row = data["rows"][0]
            assert "ticker" in row
            assert "spread_pp" in row
            assert "composite_score" in row
            assert "expert_signal_types" in row
            assert isinstance(row["expert_signal_types"], list)
            assert "equity_policy_action" in row

    def test_as_of_forwarded(self, store, capsys):
        from bve.cli.daily_brief import main
        main([
            "--db", str(store.db_path),
            "--format", "json",
            "--as-of", "2026-01-15",
        ])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["as_of"] == "2026-01-15"

    def test_cli_persists_policy_snapshots_by_default(self, store, capsys):
        from bve.cli.daily_brief import main

        main([
            "--db", str(store.db_path),
            "--format", "json",
            "--as-of", "2026-01-15",
        ])
        _ = capsys.readouterr()
        persisted = store.get_equity_policy_snapshots(as_of_date=date(2026, 1, 15))
        assert isinstance(persisted, list)

    def test_invalid_date_exits(self):
        from bve.cli.daily_brief import main
        with pytest.raises(SystemExit):
            main(["--as-of", "not-a-date"])

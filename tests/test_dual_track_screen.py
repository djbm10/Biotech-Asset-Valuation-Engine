"""Tests for the multi-name dual-track screen (compose layer + dedicated artifact)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from bve.analysis.dual_track_screen import (
    assess_target,
    assess_targets,
    dual_track_rows,
    load_investment_verdict,
    render_dual_track_report,
    write_dual_track_csv,
)


def _row(
    *,
    ticker="VRTX",
    rank=1,
    model_rnpv_millions=500.0,
    enterprise_value_millions=350.0,
    strategic_fit_score=0.78,
    recommended_deal_structure="full_acquisition",
    best_acquirer_name="Merck",
    watchlist_type="active",
    p_takeout_calibrated=0.3,
):
    return SimpleNamespace(
        ticker=ticker,
        rank=rank,
        model_rnpv_millions=model_rnpv_millions,
        enterprise_value_millions=enterprise_value_millions,
        strategic_fit_score=strategic_fit_score,
        mna_probability_score=0.6,
        recommended_deal_structure=recommended_deal_structure,
        best_acquirer_name=best_acquirer_name,
        best_acquirer_fit_score=0.7,
        watchlist_type=watchlist_type,
        gap_urgency="high",
        transaction_realism_label="HIGH",
        days_to_catalyst=30,
        matched_therapeutic_gap="CF adjacency",
        matched_priorities=["respiratory"],
        score_drivers=["clean IP"],
        p_takeout_calibrated=p_takeout_calibrated,
        estimated_deal_value_low_millions=800.0,
        estimated_deal_value_high_millions=1200.0,
    )


def _write_valuation_json(tmp_path, ticker, *, stance, evidence="full"):
    """Write a minimal valuation.json carrying a dual_track.investment block."""
    d = {
        "dual_track": {
            "investment": {
                "assessed": True,
                "stance": stance,
                "valuation_label": "overvalued" if stance == "avoid" else "undervalued",
                "market_expectation_read": "market_expectation_too_high"
                if stance == "avoid"
                else "market_expectation_too_low",
                "evidence": evidence,
                "rnpv_vs_ev_pct": -44.1 if stance == "avoid" else 30.0,
                "confidence": 0.6,
                "confidence_label": "medium",
                "rationale": ["from valuation.json"],
            }
        }
    }
    p = tmp_path / ticker.upper() / "valuation.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")


# ---------------------------------------------------------------------------
# Hybrid investment loader
# ---------------------------------------------------------------------------

def test_loads_full_investment_from_valuation_json(tmp_path):
    _write_valuation_json(tmp_path, "VRTX", stance="avoid")
    iv = load_investment_verdict("VRTX", outputs_dir=tmp_path)
    assert iv is not None
    assert iv.evidence == "full"
    assert iv.stance == "avoid"


def test_missing_valuation_json_returns_none(tmp_path):
    assert load_investment_verdict("NOPE", outputs_dir=tmp_path) is None


def test_assess_uses_full_when_valuation_present(tmp_path):
    _write_valuation_json(tmp_path, "VRTX", stance="avoid")
    a = assess_target(_row(ticker="VRTX"), outputs_dir=tmp_path)
    assert a.investment.evidence == "full"
    assert a.investment.stance == "avoid"
    assert a.bd.strategic_relevance == "high"
    # Rich stock + strong BD target → the divergence quadrant.
    assert a.quadrant == "bd_only"
    assert a.divergence is True


def test_assess_falls_back_to_coarse_when_no_valuation(tmp_path):
    # No valuation.json → coarse from rNPV 500 vs EV 350 → +42.9% → long (coarse).
    a = assess_target(_row(ticker="VRTX"), outputs_dir=tmp_path)
    assert a.investment.evidence == "coarse"
    assert a.investment.stance == "long"
    assert a.bd.recommended_route == "acquire"


def test_assess_not_assessed_when_no_valuation_and_no_rnpv(tmp_path):
    row = _row(ticker="ZZZ", model_rnpv_millions=None, enterprise_value_millions=None)
    a = assess_target(row, outputs_dir=tmp_path)
    assert a.investment.evidence == "not_assessed"
    assert a.investment.assessed is False
    assert a.quadrant == "incomplete"


# ---------------------------------------------------------------------------
# Ordering, CSV, report
# ---------------------------------------------------------------------------

def test_assess_targets_preserves_input_order(tmp_path):
    rows = [_row(ticker="A", rank=1), _row(ticker="B", rank=2), _row(ticker="C", rank=3)]
    out = assess_targets(rows, outputs_dir=tmp_path)
    assert [getattr(r, "ticker") for r, _ in out] == ["A", "B", "C"]


def test_dual_track_rows_has_evidence_and_route(tmp_path):
    out = assess_targets([_row(ticker="VRTX")], outputs_dir=tmp_path)
    rows = dual_track_rows(out)
    assert rows[0]["investment_evidence"] in ("full", "coarse", "not_assessed")
    assert rows[0]["bd_route"] == "acquire"
    assert "investment_stance" in rows[0]


def test_write_csv_and_report(tmp_path):
    _write_valuation_json(tmp_path, "VRTX", stance="avoid")
    rows = [_row(ticker="VRTX", rank=1), _row(ticker="RLAY", rank=2)]
    out = assess_targets(rows, outputs_dir=tmp_path)

    csv_path = write_dual_track_csv(out, tmp_path / "dual_track.csv")
    text = csv_path.read_text(encoding="utf-8")
    assert "investment_stance" in text.splitlines()[0]
    assert "investment_evidence" in text.splitlines()[0]
    assert "bd_route" in text.splitlines()[0]
    assert "VRTX" in text

    report = render_dual_track_report(out, as_of="2026-06-13")
    assert "# Dual-Track Screen" in report
    assert "Divergent names" in report  # VRTX is bd_only
    assert "not assessed" in report or "coarse" in report


# ---------------------------------------------------------------------------
# Weekly M&A screen augmentation (lightweight columns on ranked_targets)
# ---------------------------------------------------------------------------

def test_ranked_targets_augmentation_adds_columns(tmp_path):
    from bve.intelligence.weekly_ma_screen import _dual_track_columns_for_target

    target = SimpleNamespace(
        ticker="ABCD",
        ma_attractiveness=0.75,  # high relevance
        ma_probability=0.4,
        top_acquirer="Pfizer",
    )
    cols = _dual_track_columns_for_target(target, str(tmp_path))
    assert set(cols) == {"investment_stance", "investment_evidence", "bd_route"}
    # No valuation.json in tmp → investment not assessed; BD relevance present.
    assert cols["investment_evidence"] == "not_assessed"
    assert cols["bd_route"] in (
        "acquire", "license", "option", "watchlist", "no_action", "not_assessed"
    )


def test_ranked_targets_augmentation_uses_valuation_json_when_present(tmp_path):
    from bve.intelligence.weekly_ma_screen import _dual_track_columns_for_target

    _write_valuation_json(tmp_path, "ABCD", stance="avoid")
    target = SimpleNamespace(
        ticker="ABCD", ma_attractiveness=0.75, ma_probability=0.4, top_acquirer="Pfizer"
    )
    cols = _dual_track_columns_for_target(target, str(tmp_path))
    assert cols["investment_evidence"] == "full"
    assert cols["investment_stance"] == "avoid"


# ---------------------------------------------------------------------------
# Liveness classification + live-screen partition (live vs backtest separation)
# ---------------------------------------------------------------------------

def test_classify_liveness_by_config_source(tmp_path):
    from bve.analysis.dual_track_screen import classify_liveness

    # refreshed auto_generated config carries a market cap -> live
    live_auto = tmp_path / "auto_generated" / "acad.yaml"
    live_auto.parent.mkdir(parents=True, exist_ok=True)
    live_auto.write_text("company:\n  market_cap_millions: 3611.4\n", encoding="utf-8")
    # unrefreshed placeholder (delisted) -> inactive
    dead_auto = tmp_path / "auto_generated" / "blue.yaml"
    dead_auto.write_text("company:\n  current_price: 25.0\n", encoding="utf-8")

    config_map = {
        "ACAD": str(live_auto),                         # refreshed auto -> live
        "BLUE": str(dead_auto),                         # placeholder -> inactive
        "ARVN": "examples/configs/replay_generated/arvn.yaml",  # PIT -> pit_stale
        "BEAM": "examples/configs/provisional/beam.yaml",       # provisional -> live
    }
    assert classify_liveness("ACAD", config_map) == "live"
    assert classify_liveness("BLUE", config_map) == "inactive"
    assert classify_liveness("ARVN", config_map) == "pit_stale"
    assert classify_liveness("BEAM", config_map) == "live"
    assert classify_liveness("ZZZZ", config_map) == "no_config"
    assert classify_liveness(None, config_map) == "no_config"


def test_partition_by_liveness_excludes_pit_and_inactive(tmp_path):
    from bve.analysis.dual_track_screen import assess_targets, partition_by_liveness

    rows = [_row(ticker="BEAM", rank=1), _row(ticker="ARVN", rank=2), _row(ticker="ZZZZ", rank=3)]
    assessed = assess_targets(rows, outputs_dir=tmp_path)
    config_map = {
        "BEAM": "examples/configs/provisional/beam.yaml",      # live
        "ARVN": "examples/configs/replay_generated/arvn.yaml",  # pit_stale
        # ZZZZ unmapped -> no_config
    }
    live, excluded = partition_by_liveness(assessed, config_map)
    assert [getattr(r, "ticker") for r, _ in live] == ["BEAM"]
    assert excluded["pit_stale"] == ["ARVN"]
    assert excluded["no_config"] == ["ZZZZ"]


def test_acquirer_concentration_flags_dominant_buyer(tmp_path):
    from bve.analysis.dual_track_screen import acquirer_concentration, assess_targets

    rows = (
        [_row(ticker=f"A{i}", best_acquirer_name="AbbVie") for i in range(7)]
        + [_row(ticker="B1", best_acquirer_name="Merck")]
        + [_row(ticker="B2", best_acquirer_name="GSK")]
    )
    assessed = assess_targets(rows, outputs_dir=tmp_path)
    counts, flagged = acquirer_concentration(assessed, threshold=0.30)
    assert counts["AbbVie"] == 7
    assert any("AbbVie" in f for f in flagged)   # 7/9 = 78% >= 30%
    assert not any("Merck" in f for f in flagged)


def test_render_report_lists_excluded_and_acquirer_flag(tmp_path):
    from bve.analysis.dual_track_screen import assess_targets, render_dual_track_report

    assessed = assess_targets([_row(ticker="BEAM")], outputs_dir=tmp_path)
    report = render_dual_track_report(
        assessed,
        as_of="2026-06-13",
        excluded={"pit_stale": ["ARVN", "RVMD"], "inactive": ["BLUE"]},
        acquirer_flags=["AbbVie (10/31 = 32%)"],
    )
    assert "Excluded from the live screen" in report
    assert "ARVN" in report and "BLUE" in report
    assert "Acquirer concentration" in report and "AbbVie" in report


# ---------------------------------------------------------------------------
# Watchlist dedup (one ticker / asset -> one row)
# ---------------------------------------------------------------------------

def test_build_mna_watchlist_dedups_by_asset_id():
    from bve.ops.weekly_runner import _build_mna_watchlist

    assets = _build_mna_watchlist()
    asset_ids = [a.asset_id for a in assets]
    assert len(asset_ids) == len(set(asset_ids))   # no duplicate assets
    tickers = [a.ticker for a in assets if a.ticker]
    # ARVN / RVMD appeared twice in UNIVERSE; now exactly once each.
    assert tickers.count("ARVN") == 1
    assert tickers.count("RVMD") == 1

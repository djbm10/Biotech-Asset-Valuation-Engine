"""Phase 1 wiring: M&A scan attaches existing valuation configs by ticker.

Proves that a covered asset (one with a mapped, on-disk valuation config) is
given a ``valuation_config`` on its ``WatchlistAsset`` and therefore no longer
short-circuits in the acquisition screener with ``missing_valuation_config`` —
the gate that previously left every scanned name ``not_assessed`` on the
investment lens. Unmapped names keep ``valuation_config=None`` (honest
``not_assessed``), never a fabricated verdict.
"""
from __future__ import annotations

from datetime import date

from bve.ops.weekly_runner import (
    _build_mna_watchlist,
    _load_valuation_config_map,
)

# ALPN (povetacicept) is mapped to examples/configs/replay_generated/alpn.yaml in
# the canonical replay watchlist and is a complete, offline-runnable config.
_COVERED_TICKER = "ALPN"
# AKUS has no generated config — it must stay honestly unmapped.
_UNMAPPED_TICKER = "AKUS"


# ---------------------------------------------------------------------------
# ticker -> config map
# ---------------------------------------------------------------------------

def test_config_map_has_covered_ticker_as_existing_absolute_path():
    config_map = _load_valuation_config_map()
    assert _COVERED_TICKER in config_map
    from pathlib import Path

    p = Path(config_map[_COVERED_TICKER])
    assert p.is_absolute()
    assert p.exists()


def test_config_map_empty_on_missing_watchlist(tmp_path):
    missing = tmp_path / "does_not_exist.yaml"
    assert _load_valuation_config_map(str(missing)) == {}


def test_config_map_filters_absent_config_files_and_keeps_first(tmp_path):
    present = tmp_path / "present.yaml"
    present.write_text("company: x\n", encoding="utf-8")
    absent = tmp_path / "absent.yaml"  # deliberately not created

    watchlist = tmp_path / "wl.yaml"
    watchlist.write_text(
        "watchlist:\n"
        f"- ticker: AAA\n  valuation_config: {present}\n"
        f"- ticker: BBB\n  valuation_config: {absent}\n"
        # duplicate ticker — first occurrence must win
        f"- ticker: AAA\n  valuation_config: {absent}\n"
        # no ticker / no config — skipped
        f"- valuation_config: {present}\n"
        "- ticker: CCC\n",
        encoding="utf-8",
    )

    config_map = _load_valuation_config_map(str(watchlist))
    assert config_map == {"AAA": str(present.resolve())}
    assert "BBB" not in config_map  # config file absent
    assert "CCC" not in config_map  # no config path


# ---------------------------------------------------------------------------
# watchlist construction
# ---------------------------------------------------------------------------

def test_build_watchlist_attaches_config_for_covered_and_none_for_unmapped():
    assets = _build_mna_watchlist()
    by_ticker = {a.ticker: a for a in assets if a.ticker}

    covered = by_ticker[_COVERED_TICKER]
    assert covered.valuation_config is not None
    from pathlib import Path

    assert Path(covered.valuation_config).exists()

    unmapped = by_ticker[_UNMAPPED_TICKER]
    assert unmapped.valuation_config is None


def test_injected_config_map_controls_attachment():
    # A caller-supplied map is used verbatim — no implicit reload.
    assets = _build_mna_watchlist(config_map={_COVERED_TICKER: "/tmp/whatever.yaml"})
    by_ticker = {a.ticker: a for a in assets if a.ticker}
    assert by_ticker[_COVERED_TICKER].valuation_config == "/tmp/whatever.yaml"
    assert by_ticker[_UNMAPPED_TICKER].valuation_config is None


# ---------------------------------------------------------------------------
# the gate: covered asset no longer exits as missing_valuation_config
# ---------------------------------------------------------------------------

def test_covered_asset_passes_missing_valuation_config_gate():
    from bve.intelligence.acquisition_screen import AcquisitionScreener

    assets = _build_mna_watchlist()
    covered = next(a for a in assets if a.ticker == _COVERED_TICKER)

    screener = AcquisitionScreener(knowledge_store=None)
    row = screener._screen_asset(covered, snapshot_date=date(2024, 6, 1))

    # The first-gate exclusion is gone, and rNPV actually ran.
    assert row.exclusion_reason != "missing_valuation_config"
    assert row.model_rnpv_millions is not None


def test_unmapped_asset_still_exits_as_missing_valuation_config():
    from bve.intelligence.acquisition_screen import AcquisitionScreener

    assets = _build_mna_watchlist()
    unmapped = next(a for a in assets if a.ticker == _UNMAPPED_TICKER)

    screener = AcquisitionScreener(knowledge_store=None)
    row = screener._screen_asset(unmapped, snapshot_date=date(2024, 6, 1))

    # Honest degradation preserved — no config, no fabricated verdict.
    assert row.exclusion_reason == "missing_valuation_config"
    assert row.model_rnpv_millions is None

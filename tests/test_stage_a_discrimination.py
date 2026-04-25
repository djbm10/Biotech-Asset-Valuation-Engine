"""Tests for Stage A acquisition likelihood discrimination fixes.

Covers:
- _cross_sectional_scarcity: replaces stored 1.0 with TA-concentration-based score
- _seed_catalyst_days: populates days_to_catalyst from replay store
- _recompute_stage_a: Stage A probability spreads after feature correction
- New acquirer YAML profiles load without error
"""
from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest

from bve.intelligence.ma_calibration import (
    MACalibrationRow,
    _cross_sectional_scarcity,
    _recompute_stage_a,
    _seed_catalyst_days,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    ticker: str,
    snapshot_date: date,
    therapeutic_area: str | None = "oncology",
    scarcity_score: float | None = 1.0,
    days_to_catalyst: int | None = None,
    label: int = 0,
    capital_vulnerability_score: float | None = 0.5,
    de_risking_stage_score: float | None = 0.5,
    ta_heat_score: float = 0.3,
    valuation_discount_score: float | None = 0.4,
    enterprise_value_millions: float | None = 1000.0,
) -> MACalibrationRow:
    return MACalibrationRow(
        snapshot_date=snapshot_date,
        asset_id=f"a-{ticker.lower()}",
        ticker=ticker,
        label=label,
        probability=0.5,
        rank=1,
        best_acquirer_id="pfizer",
        therapeutic_area=therapeutic_area,
        scarcity_score=scarcity_score,
        days_to_catalyst=days_to_catalyst,
        capital_vulnerability_score=capital_vulnerability_score,
        de_risking_stage_score=de_risking_stage_score,
        ta_heat_score=ta_heat_score,
        valuation_discount_score=valuation_discount_score,
        enterprise_value_millions=enterprise_value_millions,
    )


# ---------------------------------------------------------------------------
# _cross_sectional_scarcity
# ---------------------------------------------------------------------------


def test_cross_sectional_scarcity_unique_ta_gets_high_score():
    d = date(2024, 1, 1)
    rows = [
        _row("RARE", d, therapeutic_area="gene_therapy"),   # unique TA
        _row("ONC1", d, therapeutic_area="oncology"),
        _row("ONC2", d, therapeutic_area="oncology"),
        _row("ONC3", d, therapeutic_area="oncology"),
    ]
    updated = _cross_sectional_scarcity(rows)
    rare_row = next(r for r in updated if r.ticker == "RARE")
    onc_rows = [r for r in updated if r.ticker.startswith("ONC")]

    assert rare_row.scarcity_score > onc_rows[0].scarcity_score, (
        "unique TA should have higher scarcity than dominant TA"
    )


def test_cross_sectional_scarcity_dominant_ta_gets_lower_score():
    d = date(2024, 1, 1)
    rows = [_row(f"ONC{i}", d, therapeutic_area="oncology") for i in range(10)]
    rows.append(_row("RARE", d, therapeutic_area="rare_disease"))
    updated = _cross_sectional_scarcity(rows)

    onc_score = next(r.scarcity_score for r in updated if r.ticker == "ONC0")
    rare_score = next(r.scarcity_score for r in updated if r.ticker == "RARE")
    assert rare_score > onc_score


def test_cross_sectional_scarcity_no_longer_all_ones():
    d = date(2024, 1, 1)
    # Three oncology, two rare_disease, one gene_therapy — mix should spread scores
    rows = [
        _row("ONC1", d, therapeutic_area="oncology"),
        _row("ONC2", d, therapeutic_area="oncology"),
        _row("ONC3", d, therapeutic_area="oncology"),
        _row("RD1", d, therapeutic_area="rare_disease"),
        _row("RD2", d, therapeutic_area="rare_disease"),
        _row("GT1", d, therapeutic_area="gene_therapy"),
    ]
    updated = _cross_sectional_scarcity(rows)
    scores = [r.scarcity_score for r in updated]
    assert min(scores) < max(scores), "scores must not all be the same after cross-sectional fix"
    assert max(scores) <= 1.0
    assert min(scores) >= 0.0


def test_cross_sectional_scarcity_none_ta_returns_neutral():
    d = date(2024, 1, 1)
    rows = [
        _row("NODATA", d, therapeutic_area=None),
        _row("ONC1", d, therapeutic_area="oncology"),
        _row("ONC2", d, therapeutic_area="oncology"),
    ]
    updated = _cross_sectional_scarcity(rows)
    nodata_row = next(r for r in updated if r.ticker == "NODATA")
    assert nodata_row.scarcity_score == pytest.approx(0.5)


def test_cross_sectional_scarcity_separate_snapshot_dates_computed_independently():
    d1 = date(2024, 1, 1)
    d2 = date(2024, 2, 1)
    # d1: oncology dominates (5), rare=1 → rare gets higher scarcity
    # d2: rare dominates (5), oncology=1 → oncology gets higher scarcity on d2
    rows = (
        [_row(f"ONC_D1_{i}", d1, therapeutic_area="oncology") for i in range(5)]
        + [_row("RD_D1", d1, therapeutic_area="rare_disease")]
        + [_row(f"RD_D2_{i}", d2, therapeutic_area="rare_disease") for i in range(5)]
        + [_row("ONC_D2", d2, therapeutic_area="oncology")]
    )
    updated = _cross_sectional_scarcity(rows)

    rd_d1 = next(r for r in updated if r.ticker == "RD_D1")
    onc_d1 = next(r for r in updated if r.ticker == "ONC_D1_0")
    onc_d2 = next(r for r in updated if r.ticker == "ONC_D2")
    rd_d2 = next(r for r in updated if r.ticker == "RD_D2_0")

    assert rd_d1.scarcity_score > onc_d1.scarcity_score, "rare_disease rarer on d1"
    assert onc_d2.scarcity_score > rd_d2.scarcity_score, "oncology rarer on d2"


def test_cross_sectional_scarcity_single_row_unchanged():
    d = date(2024, 1, 1)
    rows = [_row("SOLO", d, therapeutic_area="oncology", scarcity_score=1.0)]
    updated = _cross_sectional_scarcity(rows)
    # Single row — no cross-section possible, stays at original value
    assert updated[0].scarcity_score == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _seed_catalyst_days
# ---------------------------------------------------------------------------


def _make_replay_db(tmp_path: Path, events: list[tuple[str, str]]) -> Path:
    """Create a minimal replay sqlite3 db with catalyst_events rows."""
    db = tmp_path / "replay_store.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE catalyst_events "
        "(event_id TEXT, asset_id TEXT, ticker TEXT, event_type TEXT, "
        "event_date TEXT, signal_strength REAL, snapshot_date TEXT)"
    )
    for ticker, event_date in events:
        conn.execute(
            "INSERT INTO catalyst_events VALUES (?,?,?,?,?,?,?)",
            (f"ev-{ticker}", f"a-{ticker.lower()}", ticker, "trial_readout", event_date, 1.0, None),
        )
    conn.commit()
    conn.close()
    return db


def test_seed_catalyst_days_populates_days_for_matching_ticker(tmp_path):
    db = _make_replay_db(tmp_path, [("VKTX", "2024-06-01")])
    rows = [_row("VKTX", date(2024, 3, 1))]
    updated = _seed_catalyst_days(rows, db)
    assert updated[0].days_to_catalyst == 92  # 2024-06-01 - 2024-03-01 = 92 days


def test_seed_catalyst_days_ignores_past_events(tmp_path):
    db = _make_replay_db(tmp_path, [("VKTX", "2024-01-01")])
    rows = [_row("VKTX", date(2024, 3, 1))]  # snapshot AFTER event
    updated = _seed_catalyst_days(rows, db)
    assert updated[0].days_to_catalyst is None


def test_seed_catalyst_days_picks_nearest_future_event(tmp_path):
    db = _make_replay_db(tmp_path, [
        ("ALNY", "2024-05-01"),
        ("ALNY", "2024-09-01"),
        ("ALNY", "2025-01-01"),
    ])
    rows = [_row("ALNY", date(2024, 1, 1))]
    updated = _seed_catalyst_days(rows, db)
    assert updated[0].days_to_catalyst == (date(2024, 5, 1) - date(2024, 1, 1)).days


def test_seed_catalyst_days_case_insensitive_ticker(tmp_path):
    db = _make_replay_db(tmp_path, [("vktx", "2024-06-01")])
    rows = [_row("VKTX", date(2024, 3, 1))]
    updated = _seed_catalyst_days(rows, db)
    assert updated[0].days_to_catalyst == 92


def test_seed_catalyst_days_no_matching_ticker_unchanged(tmp_path):
    db = _make_replay_db(tmp_path, [("OTHER", "2024-06-01")])
    rows = [_row("VKTX", date(2024, 3, 1))]
    updated = _seed_catalyst_days(rows, db)
    assert updated[0].days_to_catalyst is None


def test_seed_catalyst_days_missing_db_returns_rows_unchanged(tmp_path):
    absent = tmp_path / "does_not_exist.sqlite"
    rows = [_row("VKTX", date(2024, 3, 1))]
    updated = _seed_catalyst_days(rows, absent)
    assert updated[0].days_to_catalyst is None


# ---------------------------------------------------------------------------
# _recompute_stage_a
# ---------------------------------------------------------------------------


def test_recompute_stage_a_produces_spread_after_scarcity_fix():
    d = date(2024, 1, 1)
    rows = [
        _row("ONC1", d, therapeutic_area="oncology", de_risking_stage_score=0.3, capital_vulnerability_score=0.2),
        _row("ONC2", d, therapeutic_area="oncology", de_risking_stage_score=0.3, capital_vulnerability_score=0.2),
        _row("ONC3", d, therapeutic_area="oncology", de_risking_stage_score=0.3, capital_vulnerability_score=0.2),
        _row("RD1", d, therapeutic_area="rare_disease", de_risking_stage_score=0.8, capital_vulnerability_score=0.9),
    ]
    rows = _cross_sectional_scarcity(rows)
    rows = _recompute_stage_a(rows)

    stage_a_scores = [r.stage_a_probability for r in rows]
    assert all(s is not None for s in stage_a_scores)
    assert min(stage_a_scores) < max(stage_a_scores), (
        "After scarcity fix, Stage A scores must spread across assets"
    )


def test_recompute_stage_a_higher_derisking_increases_score():
    d = date(2024, 1, 1)
    rows = [
        _row("LOW", d, de_risking_stage_score=0.1, capital_vulnerability_score=0.1),
        _row("HIGH", d, de_risking_stage_score=0.9, capital_vulnerability_score=0.9),
    ]
    rows = _recompute_stage_a(rows)
    low_score = next(r.stage_a_probability for r in rows if r.ticker == "LOW")
    high_score = next(r.stage_a_probability for r in rows if r.ticker == "HIGH")
    assert high_score > low_score


def test_recompute_stage_a_all_probabilities_in_bounds():
    d = date(2024, 1, 1)
    rows = [
        _row(f"T{i}", d, therapeutic_area="oncology",
             de_risking_stage_score=i / 10.0,
             capital_vulnerability_score=(10 - i) / 10.0)
        for i in range(11)
    ]
    rows = _recompute_stage_a(rows)
    for row in rows:
        assert row.stage_a_probability is not None
        assert 0.0 <= row.stage_a_probability <= 1.0


# ---------------------------------------------------------------------------
# New acquirer YAML files load correctly
# ---------------------------------------------------------------------------


def test_new_acquirer_profiles_load_without_error():
    from bve.intelligence.acquirer_profiles import AcquirerProfileLoader
    profiles_dir = Path("examples/research/acquirer_profiles")

    for name in ["vertex", "lundbeck", "ucb", "jazz", "united_therapeutics", "ipsen"]:
        yaml_path = profiles_dir / f"{name}.yaml"
        assert yaml_path.exists(), f"Missing acquirer profile: {yaml_path}"
        dataset = AcquirerProfileLoader.load(yaml_path)
        assert len(dataset.acquirers) == 1
        acquirer = dataset.acquirers[0]
        assert acquirer.company_name, f"{name}: company_name must not be empty"
        assert acquirer.therapeutic_area_gaps, f"{name}: must have at least one pipeline gap"


def test_acquirer_pool_now_includes_vertex_and_lundbeck():
    from bve.intelligence.acquirer_profiles import AcquirerProfileLoader
    profiles_dir = Path("examples/research/acquirer_profiles")
    dataset = AcquirerProfileLoader.load(profiles_dir)
    names_lower = {a.company_name.lower() for a in dataset.acquirers}
    assert any("vertex" in n for n in names_lower), "Vertex must be in the acquirer pool"
    assert any("lundbeck" in n for n in names_lower), "Lundbeck must be in the acquirer pool"


def test_acquirer_pool_expanded_to_at_least_24():
    from bve.intelligence.acquirer_profiles import AcquirerProfileLoader
    profiles_dir = Path("examples/research/acquirer_profiles")
    dataset = AcquirerProfileLoader.load(profiles_dir)
    assert len(dataset.acquirers) >= 24, (
        f"Expected ≥24 acquirers, got {len(dataset.acquirers)}"
    )

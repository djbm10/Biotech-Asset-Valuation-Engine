"""Regression tests for ma_probability_backfiller.

Key invariants (Sprint 20):
  - After rescore_ma_probability_snapshots(), scarcity_score is not constant
  - scarcity_score cap rate (>= 0.95) < 10%
  - de_risking_stage_score cap rate < 20%
  - mna_screening_score (probability) cap rate < 10%
"""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from bve.intelligence.ma_scoring import SATURATION_THRESHOLD
from bve.ops.ma_probability_backfiller import (
    MARescoredSummary,
    rescore_ma_probability_snapshots,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_db(tmp_path: Path) -> Path:
    """Create a minimal ma_probability_snapshots DB with stale saturated values."""
    db_path = tmp_path / "test_kb.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE ma_probability_snapshots (
            snapshot_date TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            ticker TEXT,
            stage TEXT,
            therapeutic_area TEXT,
            probability REAL NOT NULL,
            rank INTEGER NOT NULL,
            best_acquirer_id TEXT NOT NULL,
            above_alert_threshold INTEGER NOT NULL,
            strategic_fit_score REAL,
            valuation_discount_score REAL,
            de_risking_stage_score REAL,
            capital_vulnerability_score REAL,
            scarcity_score REAL,
            scarcity_peer_count INTEGER,
            scarcity_bucket TEXT,
            run_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    # Insert a mix of stale rows: all scarcity=1.0, all de_risking=1.0, all prob=1.0
    # Mirrors the pre-Sprint-20 saturated state
    test_rows = [
        # (asset_id, stage, therapeutic_area, peer_count, strategic_fit)
        ("a-alpn",  "phase_3", "immunology",   1, 1.0),
        ("a-arna",  "nda_bla", "immunology",   0, 1.0),
        ("a-arvn",  "phase_3", "oncology",      0, 1.0),
        ("a-bhvn",  "phase_2", "rare_disease",  0, 1.0),
        ("a-cbay",  "phase_2", "oncology",      5, 0.80),
        ("a-ccxi",  "phase_3", "rare_disease",  0, 0.90),
        ("a-cere",  "phase_2", "cardiovascular",2, 0.75),
        ("a-cinc",  "phase_3", "other",         3, 0.85),
        ("a-fulc",  "phase_2", "other",         4, 0.70),
        ("a-immu",  "nda_bla", "oncology",      7, 0.95),
    ]
    for i, (asset_id, stage, ta, peer_count, sf) in enumerate(test_rows):
        conn.execute(
            """
            INSERT INTO ma_probability_snapshots
              (snapshot_date, asset_id, ticker, stage, therapeutic_area,
               probability, rank, best_acquirer_id, above_alert_threshold,
               strategic_fit_score, valuation_discount_score,
               de_risking_stage_score, capital_vulnerability_score,
               scarcity_score, scarcity_peer_count, scarcity_bucket, run_id)
            VALUES (?, ?, ?, ?, ?, 1.0, ?, 'acq-x', 1, ?, 0.10, 1.0, 0.0, 1.0, ?, 'very_high', 'stale')
            """,
            (
                "2024-01-01", asset_id, asset_id.upper(), stage, ta,
                i + 1, sf, peer_count,
            ),
        )
    conn.commit()
    conn.close()
    return db_path


def _build_watchlist_config(tmp_path: Path) -> Path:
    """Write a minimal watchlist YAML."""
    import yaml
    wl_path = tmp_path / "watchlist.yaml"
    entries = [
        {"company_id": "alpn", "asset_id": "a-alpn",  "ticker": "ALPN",  "indication": "inflammatory disease"},
        {"company_id": "arna", "asset_id": "a-arna",  "ticker": "ARNA",  "indication": "autoimmune disease"},
        {"company_id": "arvn", "asset_id": "a-arvn",  "ticker": "ARVN",  "indication": "non-small cell lung cancer"},
        {"company_id": "bhvn", "asset_id": "a-bhvn",  "ticker": "BHVN",  "indication": "hereditary angioedema"},
        {"company_id": "cbay", "asset_id": "a-cbay",  "ticker": "CBAY",  "indication": "non-alcoholic steatohepatitis"},
        {"company_id": "ccxi", "asset_id": "a-ccxi",  "ticker": "CCXI",  "indication": "rare disease"},
        {"company_id": "cere", "asset_id": "a-cere",  "ticker": "CERE",  "indication": "cardiovascular disease"},
        {"company_id": "cinc", "asset_id": "a-cinc",  "ticker": "CINC",  "indication": "solid tumors"},
        {"company_id": "fulc", "asset_id": "a-fulc",  "ticker": "FULC",  "indication": "solid tumors"},
        {"company_id": "immu", "asset_id": "a-immu",  "ticker": "IMMU",  "indication": "metastatic cancer"},
    ]
    wl_path.write_text(yaml.dump({"watchlist": entries}))
    return wl_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRescoreMaProbabilitySnapshots:
    """Regression tests for rescore_ma_probability_snapshots (Sprint 20)."""

    @pytest.fixture()
    def rescored(self, tmp_path):
        db_path = _build_db(tmp_path)
        wl_path = _build_watchlist_config(tmp_path)
        summary = rescore_ma_probability_snapshots(
            knowledge_db_path=db_path,
            watchlist_path=wl_path,
            score_version="v1.4",
        )
        return summary, db_path

    def test_returns_mares_scored_summary(self, rescored):
        summary, _ = rescored
        assert isinstance(summary, MARescoredSummary)

    def test_all_rows_rescored(self, rescored):
        summary, _ = rescored
        assert summary.rows_rescored == 10

    def test_score_version_recorded(self, rescored):
        summary, _ = rescored
        assert summary.score_version == "v1.4"

    def test_scarcity_cap_rate_below_10pct(self, rescored):
        """After rescore, scarcity_score cap rate must be < 10%."""
        summary, _ = rescored
        assert summary.scarcity_cap_rate < 0.10, (
            f"scarcity cap rate {summary.scarcity_cap_rate:.1%} >= 10%"
        )

    def test_derisking_cap_rate_below_20pct(self, rescored):
        """After rescore, de_risking_stage_score cap rate must be < 20%."""
        summary, _ = rescored
        assert summary.derisking_cap_rate < 0.20, (
            f"derisking cap rate {summary.derisking_cap_rate:.1%} >= 20%"
        )

    def test_mna_screening_cap_rate_below_10pct(self, rescored):
        """After rescore, probability cap rate must be < 10%."""
        summary, _ = rescored
        assert summary.mna_screening_cap_rate < 0.10, (
            f"mna_screening cap rate {summary.mna_screening_cap_rate:.1%} >= 10%"
        )

    def test_scarcity_not_constant(self, rescored):
        """scarcity_score must vary across assets — not all identical."""
        _, db_path = rescored
        conn = sqlite3.connect(str(db_path))
        vals = [r[0] for r in conn.execute(
            "SELECT scarcity_score FROM ma_probability_snapshots"
        ).fetchall()]
        conn.close()
        assert len(set(round(v, 4) for v in vals)) > 1, (
            f"scarcity_score is constant at {vals[0]:.4f}"
        )

    def test_derisking_not_constant(self, rescored):
        """de_risking_stage_score must vary across assets."""
        _, db_path = rescored
        conn = sqlite3.connect(str(db_path))
        vals = [r[0] for r in conn.execute(
            "SELECT de_risking_stage_score FROM ma_probability_snapshots"
        ).fetchall()]
        conn.close()
        assert len(set(round(v, 4) for v in vals)) > 1, (
            f"de_risking_stage_score is constant at {vals[0]:.4f}"
        )

    def test_oncology_scarcity_below_rare_disease(self, rescored):
        """Oncology TA scarcity score must be lower than rare disease."""
        _, db_path = rescored
        conn = sqlite3.connect(str(db_path))
        onco_scores = [r[0] for r in conn.execute(
            "SELECT scarcity_score FROM ma_probability_snapshots WHERE therapeutic_area='oncology'"
        ).fetchall()]
        rare_scores = [r[0] for r in conn.execute(
            "SELECT scarcity_score FROM ma_probability_snapshots WHERE therapeutic_area='rare_disease'"
        ).fetchall()]
        conn.close()
        assert onco_scores and rare_scores
        assert max(onco_scores) < max(rare_scores), (
            f"oncology max scarcity {max(onco_scores):.3f} >= rare disease max {max(rare_scores):.3f}"
        )

    def test_phase3_derisking_above_phase2(self, rescored):
        """Phase 3 de_risking_stage_score must exceed Phase 2."""
        _, db_path = rescored
        conn = sqlite3.connect(str(db_path))
        p3 = [r[0] for r in conn.execute(
            "SELECT de_risking_stage_score FROM ma_probability_snapshots WHERE stage='phase_3'"
        ).fetchall()]
        p2 = [r[0] for r in conn.execute(
            "SELECT de_risking_stage_score FROM ma_probability_snapshots WHERE stage='phase_2'"
        ).fetchall()]
        conn.close()
        assert p3 and p2
        assert min(p3) > max(p2), (
            f"min Phase 3 derisking {min(p3):.3f} <= max Phase 2 {max(p2):.3f}"
        )

    def test_run_id_updated(self, rescored):
        """run_id must be updated to indicate rescoring."""
        _, db_path = rescored
        conn = sqlite3.connect(str(db_path))
        run_ids = set(r[0] for r in conn.execute(
            "SELECT run_id FROM ma_probability_snapshots"
        ).fetchall())
        conn.close()
        assert any("rescored" in (rid or "") for rid in run_ids), (
            "No rows have 'rescored' in run_id"
        )

    def test_stale_scarcity_1_0_eliminated(self, rescored):
        """No scarcity_score should remain at the old stale value of 1.0."""
        _, db_path = rescored
        conn = sqlite3.connect(str(db_path))
        n_stale = conn.execute(
            "SELECT COUNT(*) FROM ma_probability_snapshots WHERE scarcity_score >= 0.99"
        ).fetchone()[0]
        conn.close()
        assert n_stale == 0, f"{n_stale} rows still have scarcity_score >= 0.99"


class TestV14ScoreVersion:
    """Sanity checks on SCORE_VERSIONS['v1.4']."""

    def test_v14_in_score_versions(self):
        from bve.intelligence.ma_probability import SCORE_VERSIONS
        assert "v1.4" in SCORE_VERSIONS

    def test_v14_derisking_weight_positive(self):
        from bve.intelligence.ma_probability import SCORE_VERSIONS
        assert SCORE_VERSIONS["v1.4"]["derisking_stage"] > 0

    def test_v14_scarcity_weight_positive(self):
        from bve.intelligence.ma_probability import SCORE_VERSIONS
        assert SCORE_VERSIONS["v1.4"]["scarcity"] > 0

    def test_v14_weights_sum_to_one(self):
        from bve.intelligence.ma_probability import SCORE_VERSIONS
        total = sum(SCORE_VERSIONS["v1.4"].values())
        assert abs(total - 1.0) < 1e-9, f"v1.4 weights sum to {total}"

    def test_v14_in_valuation_component_modes(self):
        from bve.intelligence.ma_probability import _VALUATION_COMPONENT_MODES
        assert "v1.4" in _VALUATION_COMPONENT_MODES


class TestStageFallbackNormalization:
    """Confirm the _STAGE_FALLBACK_SCORES lookup works for normalized stage strings."""

    def test_normalized_phase3_returns_correct_base(self):
        """_normalize('phase_3') -> 'phase 3' must still look up correctly."""
        from types import SimpleNamespace
        from bve.intelligence.ma_probability import _derisking_stage_score, _DERISKING_STAGE_SCORE_CAP
        row = SimpleNamespace(
            stage="phase_3",
            acquisition_readiness_bucket=None,
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=False,
            prior_phase3_failure=False,
            label_uncertainty=False,
            prior_phase2_failure=False,
            regulatory_risk=False,
            endpoint_in_dispute=False,
            breakthrough_designation=False,
        )
        score = _derisking_stage_score(row)
        # Should not fall back to the default 0.30
        assert score > 0.30, f"phase_3 stage fallback returned {score}, expected > 0.30"
        assert score <= _DERISKING_STAGE_SCORE_CAP

    def test_normalized_phase2_below_phase3(self):
        from types import SimpleNamespace
        from bve.intelligence.ma_probability import _derisking_stage_score
        def _row(stage):
            return SimpleNamespace(
                stage=stage, acquisition_readiness_bucket=None,
                acquisition_readiness_design_tier="standard",
                acquisition_readiness_prior_pos=None,
                acquisition_readiness_posterior_pos=None,
                acquisition_readiness_low_power=False,
                safety_overhang=False, prior_phase3_failure=False,
                label_uncertainty=False, prior_phase2_failure=False,
                regulatory_risk=False, endpoint_in_dispute=False,
                breakthrough_designation=False,
            )
        assert _derisking_stage_score(_row("phase_2")) < _derisking_stage_score(_row("phase_3"))

    def test_normalized_nda_bla_above_phase3(self):
        from types import SimpleNamespace
        from bve.intelligence.ma_probability import _derisking_stage_score
        def _row(stage):
            return SimpleNamespace(
                stage=stage, acquisition_readiness_bucket=None,
                acquisition_readiness_design_tier="standard",
                acquisition_readiness_prior_pos=None,
                acquisition_readiness_posterior_pos=None,
                acquisition_readiness_low_power=False,
                safety_overhang=False, prior_phase3_failure=False,
                label_uncertainty=False, prior_phase2_failure=False,
                regulatory_risk=False, endpoint_in_dispute=False,
                breakthrough_designation=False,
            )
        assert _derisking_stage_score(_row("nda_bla")) > _derisking_stage_score(_row("phase_3"))

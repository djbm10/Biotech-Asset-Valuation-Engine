"""Tests for the candidate coverage report module."""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest
import yaml

from bve.analysis.candidate_coverage_report import (
    CoverageSummary,
    DealCoverageResult,
    _acquirers_match,
    _diagnose_miss,
    _find_real_buyer_in_candidates,
    analyze_coverage,
    render_coverage_report,
)


# ---------------------------------------------------------------------------
# Acquirer matching
# ---------------------------------------------------------------------------


def test_exact_match():
    assert _acquirers_match("Pfizer", "Pfizer") is True


def test_case_insensitive_match():
    assert _acquirers_match("pfizer", "PFIZER") is True


def test_alias_match_bms():
    assert _acquirers_match("Bristol Myers Squibb", "Bristol-Myers Squibb") is True


def test_alias_match_jnj():
    assert _acquirers_match("Johnson & Johnson", "Johnson & Johnson (Janssen)") is True


def test_no_match():
    assert _acquirers_match("Pfizer", "Merck") is False


def test_partial_name_no_match():
    assert _acquirers_match("Pfizer", "Pfizer Inc.") is False  # suffix not aliased


def test_vertex_alias():
    assert _acquirers_match("Vertex", "Vertex Pharmaceuticals") is True


def test_lundbeck_alias():
    assert _acquirers_match("Lundbeck", "H. Lundbeck") is True


def test_astellas_alias():
    assert _acquirers_match("Astellas", "Astellas Pharma") is True


def test_gsk_alias():
    assert _acquirers_match("GSK", "GlaxoSmithKline") is True


# ---------------------------------------------------------------------------
# Candidate pool search
# ---------------------------------------------------------------------------


def _make_candidates_json(entries: list[dict]) -> str:
    return json.dumps(entries)


def test_find_real_buyer_rank1():
    cands = _make_candidates_json([
        {"acquirer_name": "Pfizer", "mna_probability_score": 0.9},
        {"acquirer_name": "Merck", "mna_probability_score": 0.7},
    ])
    rank, score, pool_size = _find_real_buyer_in_candidates(cands, "Pfizer")
    assert rank == 1
    assert score == pytest.approx(0.9)
    assert pool_size == 2


def test_find_real_buyer_rank3():
    cands = _make_candidates_json([
        {"acquirer_name": "Novartis", "mna_probability_score": 0.9},
        {"acquirer_name": "Merck", "mna_probability_score": 0.8},
        {"acquirer_name": "Bristol-Myers Squibb", "mna_probability_score": 0.7},
    ])
    rank, score, pool_size = _find_real_buyer_in_candidates(cands, "Bristol Myers Squibb")
    assert rank == 3
    assert pool_size == 3


def test_find_real_buyer_not_present():
    cands = _make_candidates_json([
        {"acquirer_name": "Novartis", "mna_probability_score": 0.9},
    ])
    rank, score, pool_size = _find_real_buyer_in_candidates(cands, "Sanofi")
    assert rank is None
    assert score is None
    assert pool_size == 1


def test_find_real_buyer_empty_json():
    rank, score, pool_size = _find_real_buyer_in_candidates(None, "Pfizer")
    assert rank is None
    assert pool_size == 0


def test_find_real_buyer_invalid_json():
    rank, score, pool_size = _find_real_buyer_in_candidates("{not json}", "Pfizer")
    assert rank is None
    assert pool_size == 0


# ---------------------------------------------------------------------------
# Diagnosis
# ---------------------------------------------------------------------------


def test_diagnose_miss_not_in_library():
    cands = _make_candidates_json([
        {"acquirer_name": "Pfizer", "mna_probability_score": 0.9},
    ])
    reason = _diagnose_miss("Astellas", "ophthalmology", cands)
    assert "acquirer_not_in_profile_library" in reason


def test_diagnose_miss_name_mismatch():
    cands = _make_candidates_json([
        {"acquirer_name": "Vertex Pharmaceuticals", "mna_probability_score": 0.9},
    ])
    reason = _diagnose_miss("Vertex", "immunology", cands)
    assert "mismatch" in reason or "acquirer_not_in_profile" in reason


def test_diagnose_miss_no_candidates():
    reason = _diagnose_miss("Pfizer", "oncology", None)
    assert reason == "no_candidates_stored"


# ---------------------------------------------------------------------------
# analyze_coverage (integration with temp DB + temp YAML)
# ---------------------------------------------------------------------------


def _make_test_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute("""
        CREATE TABLE ma_probability_snapshots (
            snapshot_date TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            ticker TEXT,
            probability REAL NOT NULL,
            rank INTEGER NOT NULL,
            best_acquirer_id TEXT NOT NULL,
            best_acquirer_name TEXT,
            above_alert_threshold INTEGER NOT NULL DEFAULT 0,
            acquirer_candidates_json TEXT,
            therapeutic_area TEXT,
            PRIMARY KEY(snapshot_date, asset_id)
        )
    """)
    # Insert 3 pre-announcement snapshots for TPTX (acquired by BMS)
    for snap_date in ["2022-03-01", "2022-04-01", "2022-05-01"]:
        candidates = json.dumps([
            {"acquirer_name": "Bristol-Myers Squibb", "mna_probability_score": 0.9},
            {"acquirer_name": "Pfizer", "mna_probability_score": 0.7},
        ])
        con.execute(
            "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (snap_date, "a-tptx", "TPTX", 0.8, 1, "bms", "Bristol-Myers Squibb", 1, candidates, "oncology"),
        )
    # Insert for ARNA (acquired by Pfizer)
    for snap_date in ["2021-10-01", "2021-11-01"]:
        candidates = json.dumps([
            {"acquirer_name": "Pfizer", "mna_probability_score": 0.95},
        ])
        con.execute(
            "INSERT INTO ma_probability_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
            (snap_date, "a-arna", "ARNA", 0.9, 1, "pfizer", "Pfizer", 1, candidates, "immunology"),
        )
    con.commit()
    con.close()


def _make_test_deals_yaml(path: str) -> None:
    deals = {
        "deals": [
            {
                "target_name": "Turning Point Therapeutics",
                "target_ticker": "TPTX",
                "acquirer": "Bristol Myers Squibb",
                "announcement_date": "2022-06-03",
                "headline_value_millions": 4100,
                "therapeutic_area": "oncology",
            },
            {
                "target_name": "Arena Pharmaceuticals",
                "target_ticker": "ARNA",
                "acquirer": "Pfizer",
                "announcement_date": "2021-12-13",
                "headline_value_millions": 6700,
                "therapeutic_area": "immunology",
            },
            {
                "target_name": "VelosBio",  # private — no ticker
                "acquirer": "Merck",
                "announcement_date": "2020-11-05",
                "headline_value_millions": 2750,
                "therapeutic_area": "oncology",
            },
        ]
    }
    Path(path).write_text(yaml.dump(deals), encoding="utf-8")


def test_analyze_coverage_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        deals_path = str(Path(tmpdir) / "deals.yaml")
        _make_test_db(db_path)
        _make_test_deals_yaml(deals_path)

        summary = analyze_coverage(
            knowledge_db=db_path,
            deal_universe_path=deals_path,
            lookahead_days=365,
        )

        assert summary.total_deals == 3
        assert summary.public_deals == 2
        assert summary.in_universe == 2
        assert summary.top1_correct >= 1  # TPTX: BMS predicted correctly
        assert summary.mrr is not None


def test_analyze_coverage_tptx_top1_correct():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        deals_path = str(Path(tmpdir) / "deals.yaml")
        _make_test_db(db_path)
        _make_test_deals_yaml(deals_path)

        summary = analyze_coverage(
            knowledge_db=db_path,
            deal_universe_path=deals_path,
            lookahead_days=365,
        )

        tptx = next((r for r in summary.results if r.ticker == "TPTX"), None)
        assert tptx is not None
        assert tptx.top1_correct is True
        assert tptx.real_buyer_rank == 1


def test_analyze_coverage_private_deal_excluded():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        deals_path = str(Path(tmpdir) / "deals.yaml")
        _make_test_db(db_path)
        _make_test_deals_yaml(deals_path)

        summary = analyze_coverage(
            knowledge_db=db_path,
            deal_universe_path=deals_path,
            lookahead_days=365,
        )

        # VelosBio is private — should appear in results but not in_universe
        velos = next((r for r in summary.results if r.target_name == "VelosBio"), None)
        assert velos is not None
        assert velos.in_universe is False


def test_coverage_summary_as_dict_has_keys():
    summary = CoverageSummary(
        total_deals=10, public_deals=8, in_universe=6,
        top1_correct=3, top3_correct=4, top5_correct=5,
        in_pool=5, not_in_pool=1, not_in_universe=2,
        mean_rank_when_present=2.4, mrr=0.65,
    )
    d = summary.as_dict()
    for key in ["total_deals", "public_deals", "in_universe", "top1_accuracy",
                "top3_accuracy", "pool_coverage_rate", "mrr", "results"]:
        assert key in d, f"Missing key: {key}"


def test_render_coverage_report_structure():
    result = DealCoverageResult(
        ticker="TPTX",
        target_name="Turning Point",
        acquirer="Bristol Myers Squibb",
        announcement_date="2022-06-03",
        headline_value_millions=4100,
        therapeutic_area="oncology",
        in_universe=True,
        n_pre_snapshots=3,
        predicted_top1="Bristol-Myers Squibb",
        top1_correct=True,
        real_buyer_in_pool=True,
        real_buyer_rank=1,
        real_buyer_score=0.9,
        pool_size=10,
    )
    summary = CoverageSummary(
        total_deals=1, public_deals=1, in_universe=1,
        top1_correct=1, top3_correct=1, top5_correct=1,
        in_pool=1, not_in_pool=0, not_in_universe=0,
        mean_rank_when_present=1.0, mrr=1.0,
        results=[result],
    )
    text = render_coverage_report(summary)
    assert "Candidate Coverage Report" in text
    assert "TPTX" in text
    assert "Top-1 accuracy" in text


def test_analyze_coverage_with_real_db():
    """Integration test against live DBs if available."""
    kb = "outputs/intelligence/replay_knowledge.db"
    du = "research/mna/deal_universe_2020_2026.yaml"
    if not Path(kb).exists() or not Path(du).exists():
        pytest.skip("Live DBs not present")

    summary = analyze_coverage(knowledge_db=kb, deal_universe_path=du)
    assert summary.total_deals > 0
    assert summary.in_universe >= 10
    assert summary.mrr is not None
    assert 0 < summary.mrr <= 1.0

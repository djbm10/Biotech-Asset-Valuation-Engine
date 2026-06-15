"""Tests for _emit_profile_review_section in weekly_runner."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, pf
from bve.pipeline.profile_store import ProfileStore
from bve.ops.weekly_runner import _emit_profile_review_section

_RUN_DATE = date(2026, 6, 14)
_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _make_profile(ticker: str, *, has_nct: bool = False) -> CompanyProfile:
    """Minimal profile with one low-confidence commercial field (always flags)."""
    asset = AssetProfile(
        asset_id=f"a-{ticker.lower()}",
        nct_id="NCT12345678" if has_nct else None,
        drug_name=pf("DrugX", "seed", confidence="high"),
        indication=pf("cancer", "seed", confidence="high"),
        stage=pf("phase_2", "seed", confidence="high"),
        total_addressable_market_millions=pf(5000.0, "heuristic_prior", confidence="low"),
        net_price_per_patient_usd=pf(150_000.0, "heuristic_prior", confidence="low"),
        addressable_patients_annual=pf(50_000, "heuristic_prior", confidence="low"),
        peak_penetration=pf(0.15, "heuristic_prior", confidence="low"),
        patent_life_years=pf(11, "heuristic_prior", confidence="low"),
    )
    return CompanyProfile(
        ticker=ticker,
        name=f"{ticker} Inc",
        company_id=f"{ticker.lower()}-co",
        assets=[asset],
        generated_at=_NOW.isoformat(),
    )


def _seed_db(db_path: Path, profiles: list[CompanyProfile]) -> None:
    store = ProfileStore(db_path=str(db_path))
    try:
        for p in profiles:
            store.upsert(p)
    finally:
        store.close()


def _write_proposed_seeds(path: Path) -> None:
    import yaml

    doc = {
        "generated_at": _NOW.isoformat(),
        "proposals": [
            {"ticker": "VKTX", "asset_id": "asset-vktx-vk2735", "drug_name": "VK2735",
             "stage": "phase_3", "_meta": {"disposition": "high_confidence"}},
        ],
        "review": [
            {"ticker": "MRUS", "asset_id": "asset-mrus-peto", "drug_name": "Petosemtamab",
             "stage": "phase_3", "_meta": {"disposition": "approved_vs_active_pivotal",
                                           "approved_alternative": "Zenocutuzumab"}},
        ],
        "auto_added": [],
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


class TestProposedSeedWiring:
    def test_proposed_seeds_surface_in_report(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        seeds = tmp_path / "proposed_seeds.yaml"
        _write_proposed_seeds(seeds)
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE, proposed_seeds_path=seeds,
        )
        text = path.read_text(encoding="utf-8")
        assert "proposed_seed" in text
        assert "VK2735" in text and "Petosemtamab" in text

    def test_surfaces_even_with_no_profiles(self, tmp_path):
        db = tmp_path / "ops.db"
        ProfileStore(db_path=str(db)).close()  # empty store
        seeds = tmp_path / "proposed_seeds.yaml"
        _write_proposed_seeds(seeds)
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE, proposed_seeds_path=seeds,
        )
        assert path is not None
        assert "VK2735" in path.read_text(encoding="utf-8")

    def test_approved_ambiguous_is_high_severity(self, tmp_path):
        db = tmp_path / "ops.db"
        ProfileStore(db_path=str(db)).close()
        seeds = tmp_path / "proposed_seeds.yaml"
        _write_proposed_seeds(seeds)
        text = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE, proposed_seeds_path=seeds,
        ).read_text(encoding="utf-8")
        # The approved-vs-active-pivotal entry must appear under HIGH.
        high_block = text.split("[HIGH]")[1].split("[")[0]
        assert "MRUS" in high_block

    def test_missing_proposals_file_is_noop(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            proposed_seeds_path=tmp_path / "absent.yaml",
        )
        assert path is not None
        assert "proposed_seed" not in path.read_text(encoding="utf-8")


class TestEmitProfileReviewSection:
    def test_returns_path_when_profiles_present(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM"), _make_profile("DNLI", has_nct=True)])
        result = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert result is not None
        assert result.exists()

    def test_file_named_with_run_date(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert path is not None
        assert path.name == "review_report_2026-06-14.txt"

    def test_file_contains_review_items(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM"), _make_profile("DNLI")])
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert path is not None
        text = path.read_text()
        # Header and at least one item
        assert "PROFILE REVIEW QUEUE" in text
        assert _RUN_DATE.isoformat() in text
        assert "commercial_assumptions_heuristic" in text

    def test_missing_nct_shows_for_asset_without_nct(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM", has_nct=False)])
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert path is not None
        text = path.read_text()
        assert "missing_nct" in text

    def test_no_missing_nct_when_nct_present(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM", has_nct=True)])
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert path is not None
        text = path.read_text()
        assert "missing_nct" not in text

    def test_returns_none_when_no_profiles(self, tmp_path):
        db = tmp_path / "ops.db"
        # Empty store — no profiles inserted.
        store = ProfileStore(db_path=str(db))
        store.close()
        result = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            proposed_seeds_path=tmp_path / "no_seeds.yaml",
        )
        assert result is None

    def test_returns_none_when_db_missing(self, tmp_path):
        # Point at a nonexistent DB — should not raise, just skip.
        result = _emit_profile_review_section(
            out_dir=tmp_path,
            db_path=tmp_path / "nonexistent.db",
            run_date=_RUN_DATE,
            proposed_seeds_path=tmp_path / "no_seeds.yaml",
        )
        # Empty store (newly created) → None
        assert result is None

    def test_creates_out_dir_if_missing(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        nested = tmp_path / "new" / "subdir"
        path = _emit_profile_review_section(
            out_dir=nested, db_path=db, run_date=_RUN_DATE
        )
        assert path is not None
        assert path.parent == nested
        assert nested.exists()

    def test_multiple_profiles_all_appear(self, tmp_path):
        db = tmp_path / "ops.db"
        tickers = ["BEAM", "DNLI", "RVMD"]
        _seed_db(db, [_make_profile(t) for t in tickers])
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert path is not None
        text = path.read_text()
        for t in tickers:
            assert t in text

    def test_idempotent_second_run_overwrites(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        p1 = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        p2 = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert p1 == p2
        assert p1 is not None and p1.exists()


class TestScoreMovementDetection:
    """large_score_move is emitted when composite moves > threshold week-over-week."""

    def test_large_move_flagged(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        snap = tmp_path / "snap.json"
        # Prior score 0.80 → current 0.40 = 50% drop → exceeds 25% threshold.
        snap.write_text('{"BEAM": 0.80}', encoding="utf-8")
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"BEAM": 0.40},
            score_snapshot=snap,
        )
        assert path is not None
        text = path.read_text()
        assert "large_score_move" in text
        assert "BEAM" in text

    def test_small_move_not_flagged(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        snap = tmp_path / "snap.json"
        # Prior 0.60 → current 0.58 = 3% move → below threshold.
        snap.write_text('{"BEAM": 0.60}', encoding="utf-8")
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"BEAM": 0.58},
            score_snapshot=snap,
        )
        assert path is not None
        assert "large_score_move" not in path.read_text()

    def test_no_prior_snapshot_no_move_flag(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        # No snapshot file exists yet — first run ever.
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"BEAM": 0.70},
            score_snapshot=tmp_path / "snap.json",
        )
        assert path is not None
        assert "large_score_move" not in path.read_text()

    def test_snapshot_written_after_run(self, tmp_path):
        import json as _json
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM"), _make_profile("DNLI")])
        snap = tmp_path / "snap.json"
        _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"BEAM": 0.72, "DNLI": 0.55},
            score_snapshot=snap,
        )
        assert snap.exists()
        data = _json.loads(snap.read_text())
        assert abs(data["BEAM"] - 0.72) < 1e-6
        assert abs(data["DNLI"] - 0.55) < 1e-6

    def test_snapshot_updates_on_subsequent_run(self, tmp_path):
        import json as _json
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        snap = tmp_path / "snap.json"
        _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"BEAM": 0.60},
            score_snapshot=snap,
        )
        _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"BEAM": 0.35},
            score_snapshot=snap,
        )
        data = _json.loads(snap.read_text())
        assert abs(data["BEAM"] - 0.35) < 1e-6

    def test_ticker_case_insensitive(self, tmp_path):
        """Score snapshot uses upper-case keys; current_scores may be mixed case."""
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        snap = tmp_path / "snap.json"
        snap.write_text('{"BEAM": 0.80}', encoding="utf-8")
        path = _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores={"beam": 0.40},  # lower-case input
            score_snapshot=snap,
        )
        assert path is not None
        assert "large_score_move" in path.read_text()

    def test_no_scores_passed_no_snapshot_written(self, tmp_path):
        db = tmp_path / "ops.db"
        _seed_db(db, [_make_profile("BEAM")])
        snap = tmp_path / "snap.json"
        _emit_profile_review_section(
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE,
            current_scores=None,
            score_snapshot=snap,
        )
        assert not snap.exists()  # nothing to persist

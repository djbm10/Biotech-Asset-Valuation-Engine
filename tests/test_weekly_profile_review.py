"""Tests for _emit_profile_review_section in weekly_runner."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

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
            out_dir=tmp_path, db_path=db, run_date=_RUN_DATE
        )
        assert result is None

    def test_returns_none_when_db_missing(self, tmp_path):
        # Point at a nonexistent DB — should not raise, just skip.
        result = _emit_profile_review_section(
            out_dir=tmp_path,
            db_path=tmp_path / "nonexistent.db",
            run_date=_RUN_DATE,
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

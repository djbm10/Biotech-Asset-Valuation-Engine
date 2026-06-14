"""Tests for override staleness detection and review queue injection."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, pf
from bve.pipeline.override_staleness import (
    MCAP_MOVE_THRESHOLD,
    check_override_staleness,
    clear_stale_record,
    load_all_stale,
    update_after_rebuild,
    write_stale_record,
)
from bve.pipeline.review_queue import OVERRIDE_REVALIDATION, build_review_queue

_NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _asset(
    drug: str = "DrugX",
    indication: str = "cancer",
    stage: str = "phase_2",
    ta: str = "oncology",
    nct: str | None = "NCT12345",
) -> AssetProfile:
    return AssetProfile(
        asset_id="a-test",
        nct_id=nct,
        drug_name=pf(drug, "seed", confidence="high"),
        indication=pf(indication, "seed", confidence="high"),
        stage=pf(stage, "seed", confidence="high"),
        therapeutic_area=pf(ta, "seed", confidence="high"),
        total_addressable_market_millions=pf(5000.0, "heuristic_prior", confidence="low"),
        net_price_per_patient_usd=pf(150_000.0, "heuristic_prior", confidence="low"),
        addressable_patients_annual=pf(50_000, "heuristic_prior", confidence="low"),
        peak_penetration=pf(0.15, "heuristic_prior", confidence="low"),
        patent_life_years=pf(11, "heuristic_prior", confidence="low"),
    )


def _profile(
    ticker: str = "BEAM",
    *,
    drug: str = "DrugX",
    indication: str = "cancer",
    stage: str = "phase_2",
    ta: str = "oncology",
    nct: str | None = "NCT12345",
    mcap: float = 500.0,
    generated_at: str | None = None,
) -> CompanyProfile:
    ts = generated_at or _NOW.isoformat()
    return CompanyProfile(
        ticker=ticker,
        name=f"{ticker} Inc",
        company_id=f"{ticker.lower()}-co",
        assets=[_asset(drug=drug, indication=indication, stage=stage, ta=ta, nct=nct)],
        market_cap_millions=pf(mcap, "market_data", confidence="high"),
        generated_at=ts,
    )


# ---------------------------------------------------------------------------
# check_override_staleness
# ---------------------------------------------------------------------------


class TestCheckOverrideStaleness:
    def test_identical_profiles_no_change(self):
        old = _profile()
        new = _profile()
        assert check_override_staleness(old, new) == []

    def test_drug_name_change_flagged(self):
        old = _profile(drug="DrugX")
        new = _profile(drug="DrugY")
        changed = check_override_staleness(old, new)
        assert "lead_asset_name" in changed

    def test_indication_change_flagged(self):
        old = _profile(indication="AML")
        new = _profile(indication="CLL")
        assert "indication" in check_override_staleness(old, new)

    def test_stage_change_flagged(self):
        old = _profile(stage="phase_2")
        new = _profile(stage="phase_3")
        assert "stage" in check_override_staleness(old, new)

    def test_nct_change_flagged(self):
        old = _profile(nct="NCT00001")
        new = _profile(nct="NCT99999")
        assert "nct_id" in check_override_staleness(old, new)

    def test_therapeutic_area_change_flagged(self):
        old = _profile(ta="oncology")
        new = _profile(ta="rare_disease")
        assert "therapeutic_area" in check_override_staleness(old, new)

    def test_mcap_large_move_flagged(self):
        old = _profile(mcap=500.0)
        new = _profile(mcap=800.0)  # +60% > 20% threshold
        assert "market_cap_millions" in check_override_staleness(old, new)

    def test_mcap_small_move_not_flagged(self):
        old = _profile(mcap=500.0)
        new = _profile(mcap=520.0)  # +4% < threshold
        assert "market_cap_millions" not in check_override_staleness(old, new)

    def test_mcap_exactly_at_threshold_not_flagged(self):
        threshold = MCAP_MOVE_THRESHOLD
        old = _profile(mcap=500.0)
        new = _profile(mcap=500.0 * (1 + threshold))  # exactly at boundary
        # strictly greater, so exactly-at is NOT flagged
        assert "market_cap_millions" not in check_override_staleness(old, new)

    def test_mcap_just_over_threshold_flagged(self):
        old = _profile(mcap=500.0)
        new = _profile(mcap=500.0 * (1 + MCAP_MOVE_THRESHOLD + 0.01))
        assert "market_cap_millions" in check_override_staleness(old, new)

    def test_multiple_fields_all_returned(self):
        old = _profile(drug="A", stage="phase_2", mcap=500.0)
        new = _profile(drug="B", stage="phase_3", mcap=900.0)
        changed = check_override_staleness(old, new)
        assert "lead_asset_name" in changed
        assert "stage" in changed
        assert "market_cap_millions" in changed

    def test_nct_cleared_to_none_not_flagged(self):
        # If new value is None/empty, we don't flag — can't confirm a meaningful change.
        old = _profile(nct="NCT00001")
        new = _profile(nct=None)
        assert "nct_id" not in check_override_staleness(old, new)


# ---------------------------------------------------------------------------
# Sidecar I/O
# ---------------------------------------------------------------------------


class TestSidecarIO:
    def test_write_and_load_round_trip(self, tmp_path):
        write_stale_record("BEAM", ["stage", "nct_id"], tmp_path)
        data = load_all_stale(tmp_path)
        assert "BEAM" in data
        assert set(data["BEAM"]) == {"stage", "nct_id"}

    def test_ticker_upper_cased_on_write(self, tmp_path):
        write_stale_record("beam", ["stage"], tmp_path)
        assert (tmp_path / "BEAM.stale.json").exists()

    def test_clear_removes_sidecar(self, tmp_path):
        write_stale_record("BEAM", ["stage"], tmp_path)
        clear_stale_record("BEAM", tmp_path)
        assert not (tmp_path / "BEAM.stale.json").exists()

    def test_clear_is_noop_when_absent(self, tmp_path):
        clear_stale_record("BEAM", tmp_path)  # should not raise

    def test_load_empty_dir(self, tmp_path):
        assert load_all_stale(tmp_path) == {}

    def test_load_missing_dir(self, tmp_path):
        assert load_all_stale(tmp_path / "nonexistent") == {}

    def test_load_ignores_corrupt_files(self, tmp_path):
        (tmp_path / "BAD.stale.json").write_text("not json", encoding="utf-8")
        (tmp_path / "BEAM.stale.json").write_text(
            json.dumps({"ticker": "BEAM", "changed_fields": ["stage"]}), encoding="utf-8"
        )
        data = load_all_stale(tmp_path)
        assert "BEAM" in data
        assert "BAD" not in data

    def test_load_multiple_tickers(self, tmp_path):
        write_stale_record("BEAM", ["stage"], tmp_path)
        write_stale_record("DNLI", ["nct_id", "indication"], tmp_path)
        data = load_all_stale(tmp_path)
        assert set(data.keys()) == {"BEAM", "DNLI"}


# ---------------------------------------------------------------------------
# update_after_rebuild
# ---------------------------------------------------------------------------


class TestUpdateAfterRebuild:
    def test_first_build_clears_no_sidecar(self, tmp_path):
        new = _profile("BEAM")
        changed = update_after_rebuild(
            "BEAM", None, new,
            override_dir=tmp_path / "ov",
            profiles_dir=tmp_path / "prof",
        )
        assert changed == []
        assert not (tmp_path / "prof" / "BEAM.stale.json").exists()

    def test_material_change_with_override_writes_sidecar(self, tmp_path):
        ov_dir = tmp_path / "ov"
        ov_dir.mkdir()
        (ov_dir / "BEAM.yaml").write_text("confidential_overrides: {}", encoding="utf-8")
        old = _profile("BEAM", stage="phase_2")
        new = _profile("BEAM", stage="phase_3")
        changed = update_after_rebuild(
            "BEAM", old, new,
            override_dir=ov_dir,
            profiles_dir=tmp_path / "prof",
        )
        assert "stage" in changed
        assert (tmp_path / "prof" / "BEAM.stale.json").exists()

    def test_material_change_without_override_no_sidecar(self, tmp_path):
        old = _profile("BEAM", stage="phase_2")
        new = _profile("BEAM", stage="phase_3")
        changed = update_after_rebuild(
            "BEAM", old, new,
            override_dir=tmp_path / "ov",  # dir exists but no BEAM.yaml
            profiles_dir=tmp_path / "prof",
        )
        assert "stage" in changed
        assert not (tmp_path / "prof" / "BEAM.stale.json").exists()

    def test_no_change_clears_existing_sidecar(self, tmp_path):
        prof_dir = tmp_path / "prof"
        write_stale_record("BEAM", ["stage"], prof_dir)
        old = _profile("BEAM")
        new = _profile("BEAM")
        changed = update_after_rebuild(
            "BEAM", old, new,
            override_dir=tmp_path / "ov",
            profiles_dir=prof_dir,
        )
        assert changed == []
        assert not (prof_dir / "BEAM.stale.json").exists()


# ---------------------------------------------------------------------------
# Review queue injection
# ---------------------------------------------------------------------------


class TestReviewQueueInjection:
    def test_override_revalidation_item_injected(self):
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        items = build_review_queue(
            [profile],
            stale_overrides={"BEAM": ["stage", "nct_id"]},
            now=_NOW,
        )
        reasons = [i.reason for i in items]
        assert OVERRIDE_REVALIDATION in reasons

    def test_item_is_high_severity(self):
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        items = build_review_queue(
            [profile],
            stale_overrides={"BEAM": ["stage"]},
            now=_NOW,
        )
        match = next(i for i in items if i.reason == OVERRIDE_REVALIDATION)
        assert match.severity == "high"

    def test_changed_fields_appear_in_field_column(self):
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        items = build_review_queue(
            [profile],
            stale_overrides={"BEAM": ["stage", "nct_id"]},
            now=_NOW,
        )
        match = next(i for i in items if i.reason == OVERRIDE_REVALIDATION)
        assert "stage" in (match.field or "")
        assert "nct_id" in (match.field or "")

    def test_no_stale_overrides_no_injection(self):
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        items = build_review_queue([profile], now=_NOW)
        assert not any(i.reason == OVERRIDE_REVALIDATION for i in items)

    def test_ticker_not_in_stale_overrides_no_injection(self):
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        items = build_review_queue(
            [profile],
            stale_overrides={"DNLI": ["stage"]},  # different ticker
            now=_NOW,
        )
        assert not any(i.reason == OVERRIDE_REVALIDATION for i in items)

    def test_resolution_suppresses_override_flag(self):
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        # Decision made after the profile was generated.
        resolutions = {("BEAM", OVERRIDE_REVALIDATION): _NOW + timedelta(hours=1)}
        items = build_review_queue(
            [profile],
            stale_overrides={"BEAM": ["stage"]},
            resolutions=resolutions,
            now=_NOW,
        )
        assert not any(
            i.reason == OVERRIDE_REVALIDATION and not i.resolved for i in items
        )

    def test_stale_resolution_resurfaces_flag(self):
        """Profile rebuilt after decision → flag re-surfaces."""
        old_gen = _NOW.isoformat()
        resolutions = {("BEAM", OVERRIDE_REVALIDATION): _NOW + timedelta(hours=1)}
        # Profile rebuilt a day later (generated_at > decided_at).
        newer_profile = _profile(
            "BEAM", generated_at=(_NOW + timedelta(days=1)).isoformat()
        )
        items = build_review_queue(
            [newer_profile],
            stale_overrides={"BEAM": ["stage"]},
            resolutions=resolutions,
            now=_NOW + timedelta(days=1),
        )
        assert any(
            i.reason == OVERRIDE_REVALIDATION and not i.resolved for i in items
        )

    def test_lowercase_stale_overrides_key_matched(self):
        """build_review_queue upper-cases stale_overrides keys."""
        profile = _profile("BEAM", generated_at=_NOW.isoformat())
        items = build_review_queue(
            [profile],
            stale_overrides={"beam": ["stage"]},  # lower-case key
            now=_NOW,
        )
        assert any(i.reason == OVERRIDE_REVALIDATION for i in items)

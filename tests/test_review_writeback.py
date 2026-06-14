"""Tests for review disposition write-back + resolution suppression."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import yaml

from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, pf
from bve.pipeline.review_queue import CONFLICTING_SOURCES, build_review_queue
from bve.pipeline.review_writeback import (
    ProfileReviewStore,
    ReviewDispositionRecord,
    _deep_set,
    apply_decision,
    parse_value,
    set_override,
)

NOW = datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def test_parse_value_coercion():
    assert parse_value("12.5") == 12.5
    assert parse_value("100") == 100
    assert parse_value("true") is True
    assert parse_value("high") == "high"


def test_deep_set_dict_and_list():
    d: dict = {}
    _deep_set(d, "company.shares_outstanding_millions", 12.5)
    _deep_set(d, "trials.0.success_probability", 0.42)
    assert d["company"]["shares_outstanding_millions"] == 12.5
    assert d["trials"][0]["success_probability"] == 0.42


def test_set_override_writes_and_merges(tmp_path):
    p1 = set_override("GPCR", "company.shares_outstanding_millions", 12.5,
                      override_dir=tmp_path, rationale="10-K", reviewer="dmann")
    set_override("GPCR", "market_model.peak_penetration", 0.3, override_dir=tmp_path)
    doc = yaml.safe_load(p1.read_text())
    co = doc["confidential_overrides"]
    assert co["company"]["shares_outstanding_millions"] == 12.5
    assert co["market_model"]["peak_penetration"] == 0.3  # merge preserved first override
    assert doc["meta"]["analyst"] == "dmann"


def test_apply_decision_approve_writes_override_and_logs(tmp_path):
    res = apply_decision(
        "GPCR", CONFLICTING_SOURCES, "approve",
        field="company.shares_outstanding_millions", value=12.5,
        rationale="mcap feed stale", reviewer="dmann", asset_id="a-gpcr",
        override_dir=tmp_path / "ov", db_path=tmp_path / "ops.db",
    )
    assert res["override_file"] is not None
    assert (tmp_path / "ov" / "GPCR.yaml").exists()
    store = ProfileReviewStore(tmp_path / "ops.db")
    try:
        recs = store.list_for("GPCR")
        assert len(recs) == 1 and recs[0].action == "approve" and recs[0].value == "12.5"
    finally:
        store.close()


def test_apply_decision_reject_logs_only(tmp_path):
    res = apply_decision(
        "FATE", "commercial_assumptions_heuristic", "reject",
        rationale="TA prior fine for screen", db_path=tmp_path / "ops.db",
        override_dir=tmp_path / "ov",
    )
    assert res["override_file"] is None
    assert not (tmp_path / "ov").exists()  # no override written
    store = ProfileReviewStore(tmp_path / "ops.db")
    try:
        assert store.list_for("FATE")[0].action == "reject"
    finally:
        store.close()


def test_apply_decision_approve_requires_field_and_value(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        apply_decision("GPCR", CONFLICTING_SOURCES, "approve", db_path=tmp_path / "ops.db")


def _conflict_profile(generated_at: str) -> CompanyProfile:
    asset = AssetProfile(
        asset_id="a-1", nct_id="NCT1",
        drug_name=pf("D", "seed", confidence="high"),
        indication=pf("X", "seed", confidence="high"),
        stage=pf("phase_3", "seed", confidence="high"),
        total_addressable_market_millions=pf(5000.0, "seed", confidence="medium"),
        net_price_per_patient_usd=pf(1.0, "seed", confidence="medium"),
        addressable_patients_annual=pf(1, "seed", confidence="medium"),
        peak_penetration=pf(0.2, "seed", confidence="medium"),
        patent_life_years=pf(11, "seed", confidence="medium"),
    )
    return CompanyProfile(
        ticker="GPCR", name="G", company_id="gpcr-auto", assets=[asset],
        market_cap_millions=pf(1000.0, "market_data", confidence="high"),
        current_price=pf(10.0, "market_data", confidence="high"),
        shares_outstanding_millions=pf(300.0, "sec_edgar", confidence="high"),  # 3000 vs 1000
        generated_at=generated_at,
    )


def test_resolution_suppresses_then_reappears_after_rebuild():
    prof = _conflict_profile(generated_at=NOW.isoformat())
    # Unresolved → conflict shows.
    base = build_review_queue([prof], now=NOW)
    assert any(i.reason == CONFLICTING_SOURCES for i in base)

    # Decision made AFTER the profile was built → suppressed.
    resolved_after = {("GPCR", CONFLICTING_SOURCES): NOW + timedelta(hours=1)}
    q = build_review_queue([prof], now=NOW, resolutions=resolved_after)
    assert not any(i.reason == CONFLICTING_SOURCES for i in q)

    # Profile rebuilt LATER than the decision → item re-surfaces (stale resolution).
    newer = _conflict_profile(generated_at=(NOW + timedelta(days=1)).isoformat())
    q2 = build_review_queue([newer], now=NOW + timedelta(days=1), resolutions=resolved_after)
    assert any(i.reason == CONFLICTING_SOURCES for i in q2)

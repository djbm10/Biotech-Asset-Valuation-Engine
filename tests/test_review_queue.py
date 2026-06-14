"""Tests for the analyst review queue (pipeline/review_queue.py)."""
from __future__ import annotations

from datetime import datetime, timezone

from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, pf
from bve.pipeline.review_queue import (
    AMBIGUOUS_LEAD_ASSET,
    COMMERCIAL_HEURISTIC,
    CONFLICTING_SOURCES,
    LARGE_SCORE_MOVE,
    MISSING_NCT,
    STALE_DATA,
    build_review_queue,
    review_company,
)

NOW = datetime(2026, 6, 14, tzinfo=timezone.utc)


def _clean_asset(**over) -> AssetProfile:
    base = dict(
        asset_id="a-1",
        nct_id="NCT12345678",
        drug_name=pf("DRUG-1", "seed", confidence="high"),
        indication=pf("NSCLC", "seed", confidence="high"),
        stage=pf("phase_3", "clinicaltrials_gov", confidence="high"),
        total_addressable_market_millions=pf(5000.0, "seed", confidence="medium"),
        net_price_per_patient_usd=pf(100000.0, "seed", confidence="medium"),
        addressable_patients_annual=pf(10000, "seed", confidence="medium"),
        peak_penetration=pf(0.2, "seed", confidence="medium"),
        patent_life_years=pf(11, "seed", confidence="medium"),
    )
    base.update(over)
    return AssetProfile(**base)


def _clean_profile(asset=None, **over) -> CompanyProfile:
    base = dict(
        ticker="ABC",
        name="ABC Bio",
        company_id="abc-auto",
        assets=[asset or _clean_asset()],
        # 10 * 100 = 1000 == market cap → consistent
        market_cap_millions=pf(1000.0, "market_data", confidence="high"),
        current_price=pf(10.0, "market_data", confidence="high"),
        shares_outstanding_millions=pf(100.0, "sec_edgar", confidence="high"),
        generated_at=NOW.isoformat(),
    )
    base.update(over)
    return CompanyProfile(**base)


def _reasons(items):
    return {i.reason for i in items}


def test_clean_profile_has_no_flags():
    items = review_company(_clean_profile(), now=NOW)
    assert items == []


def test_missing_nct_flagged():
    items = review_company(_clean_profile(_clean_asset(nct_id=None)), now=NOW)
    assert MISSING_NCT in _reasons(items)


def test_heuristic_economics_flagged():
    asset = _clean_asset(
        total_addressable_market_millions=pf(5000.0, "heuristic_prior", confidence="low"),
        peak_penetration=pf(0.15, "heuristic_prior", confidence="low"),
    )
    item = next(i for i in review_company(_clean_profile(asset), now=NOW) if i.reason == COMMERCIAL_HEURISTIC)
    assert item.severity == "low"
    assert "total_addressable_market_millions" in item.field


def test_ambiguous_lead_asset_flagged():
    # Default (unset) drug_name is low-confidence.
    asset = _clean_asset(drug_name=pf(None, "unset", confidence="low"))
    item = next(i for i in review_company(_clean_profile(asset), now=NOW) if i.reason == AMBIGUOUS_LEAD_ASSET)
    assert item.severity == "high"
    assert "drug_name" in item.field


def test_stale_data_flagged():
    old = _clean_profile(generated_at="2026-01-01T00:00:00+00:00")
    items = review_company(old, now=NOW, stale_days=90)
    assert STALE_DATA in _reasons(items)
    # Fresh profile within threshold is not flagged stale.
    assert STALE_DATA not in _reasons(review_company(_clean_profile(), now=NOW, stale_days=90))


def test_conflicting_sources_flagged():
    # shares 200 -> implied mcap 2000 vs reported 1000 = 100% divergence.
    p = _clean_profile(shares_outstanding_millions=pf(200.0, "sec_edgar", confidence="high"))
    item = next(i for i in review_company(p, now=NOW) if i.reason == CONFLICTING_SOURCES)
    assert item.severity == "high"
    assert item.field == "market_cap_millions"


def test_large_score_move_flagged_only_above_threshold():
    p = _clean_profile()
    big = review_company(p, now=NOW, prior_score=0.40, current_score=0.60)  # +50%
    assert LARGE_SCORE_MOVE in _reasons(big)
    small = review_company(p, now=NOW, prior_score=0.40, current_score=0.42)  # +5%
    assert LARGE_SCORE_MOVE not in _reasons(small)


def test_build_queue_sorts_high_severity_first():
    flagged_asset = _clean_asset(nct_id=None, drug_name=pf(None, "unset", confidence="low"))
    queue = build_review_queue([_clean_profile(flagged_asset)], now=NOW)
    severities = [i.severity for i in queue]
    assert severities == sorted(severities, key={"high": 0, "medium": 1, "low": 2}.get)
    assert severities[0] == "high"

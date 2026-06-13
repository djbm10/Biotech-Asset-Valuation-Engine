"""Tests for the canonical profile models (pipeline/asset_profile.py)."""
from __future__ import annotations

import pytest

from bve.pipeline.asset_profile import (
    AssetProfile,
    CompanyProfile,
    ProvenancedField,
    pf,
)


def test_provenanced_field_defaults():
    field = ProvenancedField(value=42.0, source="sec_edgar")
    assert field.value == 42.0
    assert field.source == "sec_edgar"
    assert field.confidence == "medium"
    assert field.stale is False
    assert field.last_checked  # populated with an ISO timestamp


def test_pf_helper_sets_confidence_and_provenance():
    field = pf(0.1, "heuristic_prior", confidence="low", source_url="http://x")
    assert field.value == 0.1
    assert field.confidence == "low"
    assert field.source == "heuristic_prior"
    assert field.source_url == "http://x"


def test_asset_profile_empty_defaults_are_low_confidence():
    asset = AssetProfile(asset_id="a-1")
    # Unset provenanced fields default to value=None, confidence=low.
    assert asset.drug_name.value is None
    assert asset.drug_name.confidence == "low"
    # Every default field is therefore flagged low-confidence.
    assert "peak_penetration" in asset.low_confidence_fields()


def test_asset_profile_low_confidence_fields_tracks_only_low():
    asset = AssetProfile(
        asset_id="a-1",
        drug_name=pf("DRUG-1", "seed", confidence="high"),
        indication=pf("NSCLC", "clinicaltrials_gov", confidence="high"),
        peak_penetration=pf(0.1, "heuristic_prior", confidence="low"),
    )
    low = asset.low_confidence_fields()
    assert "peak_penetration" in low
    assert "drug_name" not in low
    assert "indication" not in low


def test_asset_profile_provenanced_items_excludes_identifiers():
    asset = AssetProfile(asset_id="a-1", nct_id="NCT1")
    items = asset.provenanced_items()
    assert "asset_id" not in items
    assert "nct_id" not in items
    assert "drug_name" in items


def test_company_profile_lead_asset():
    lead = AssetProfile(asset_id="lead")
    second = AssetProfile(asset_id="second")
    company = CompanyProfile(
        ticker="ABC",
        name="ABC Bio",
        company_id="abc-auto",
        assets=[lead, second],
    )
    assert company.lead_asset.asset_id == "lead"
    assert company.evidence_level == "coarse"  # default honesty label


def test_company_profile_lead_asset_raises_when_empty():
    company = CompanyProfile(ticker="ABC", name="ABC Bio", company_id="abc-auto")
    with pytest.raises(ValueError):
        _ = company.lead_asset


def test_company_provenanced_items_excludes_assets_list():
    company = CompanyProfile(ticker="ABC", name="ABC Bio", company_id="abc-auto")
    items = company.company_provenanced_items()
    assert "cash_millions" in items
    assert "assets" not in items
    assert "ticker" not in items

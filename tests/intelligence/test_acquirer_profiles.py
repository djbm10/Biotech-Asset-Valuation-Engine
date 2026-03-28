from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.intelligence.acquirer_profiles import (
    AcquirerProfileLoader,
    BudgetSnapshot,
    RecentDeal,
)


def test_acquirer_profile_loader_parses_repository_yaml():
    path = Path("research/mna/pipeline_gaps.yaml")

    dataset = AcquirerProfileLoader.load(path)
    regeneron = AcquirerProfileLoader.get_acquirer(dataset, "ReGeNeRoN")

    assert dataset.as_of_date.isoformat() == "2026-03-24"
    assert len(dataset.acquirers) == 1
    assert regeneron.company_name == "Regeneron Pharmaceuticals"
    assert regeneron.budget.net_cash_millions == pytest.approx(16879.9, abs=1e-9)
    assert len(regeneron.therapeutic_area_gaps) >= 4
    assert regeneron.recent_deal_history[0].deal_name == "Hansoh HS-20094 in-license"


def test_acquirer_profile_loader_rejects_duplicate_acquirer_ids(tmp_path: Path):
    path = tmp_path / "pipeline_gaps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-24",
                "acquirers": [
                    _profile("regeneron"),
                    _profile("REGENERON"),
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        AcquirerProfileLoader.load(path)


def test_budget_snapshot_requires_consistent_net_cash():
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate(
            {
                "as_of_date": "2025-12-31",
                "cash_and_marketable_securities_millions": 100.0,
                "long_term_debt_millions": 30.0,
                "net_cash_millions": 80.0,
                "capacity_notes": "Example",
                "source_refs": [_source_ref()],
            }
        )


def test_recent_deal_rejects_inverted_value_band():
    with pytest.raises(ValidationError):
        RecentDeal.model_validate(
            {
                "deal_name": "Example deal",
                "status": "announced",
                "announcement_date": "2025-05-01",
                "deal_type": "license",
                "therapeutic_area": "oncology",
                "modality": "antibody",
                "stage_context": "phase_2",
                "implied_value_band_millions_low": 500.0,
                "implied_value_band_millions_high": 400.0,
                "source_url": "https://example.com/deal",
            }
        )


def test_get_acquirer_raises_for_unknown_id(tmp_path: Path):
    path = tmp_path / "pipeline_gaps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-24",
                "acquirers": [_profile("regeneron")],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(KeyError):
        AcquirerProfileLoader.get_acquirer(path, "unknown")


def _profile(acquirer_id: str) -> dict[str, object]:
    return {
        "acquirer_id": acquirer_id,
        "company_name": "Regeneron Pharmaceuticals",
        "ticker": "REGN",
        "profile_as_of": "2026-03-24",
        "source_notes": "Example profile",
        "therapeutic_area_gaps": [
            {
                "therapeutic_area": "ophthalmology",
                "exposure_type": "loe_and_franchise_defense",
                "exposure_level": "high",
                "rationale": "Example rationale",
                "source_refs": [_source_ref()],
            }
        ],
        "preferred_modalities": [
            {
                "modality": "fully_human_antibody",
                "preference_strength": "high",
                "rationale": "Example rationale",
                "source_refs": [_source_ref()],
            }
        ],
        "strategic_priorities": [
            {
                "priority": "Complementary BD only",
                "priority_strength": "high",
                "source_refs": [_source_ref()],
            }
        ],
        "recent_deal_history": [
            {
                "deal_name": "Example deal",
                "status": "completed",
                "announcement_date": "2025-05-01",
                "deal_type": "license",
                "therapeutic_area": "ophthalmology",
                "modality": "antibody",
                "stage_context": "phase_2",
                "upfront_millions": 100.0,
                "implied_value_band_millions_low": 100.0,
                "implied_value_band_millions_high": 200.0,
                "source_url": "https://example.com/deal",
            }
        ],
        "budget": {
            "as_of_date": "2025-12-31",
            "cash_and_marketable_securities_millions": 100.0,
            "long_term_debt_millions": 20.0,
            "net_cash_millions": 80.0,
            "capacity_notes": "Example capacity notes",
            "source_refs": [_source_ref()],
        },
    }


def _source_ref() -> dict[str, str]:
    return {
        "source_date": "2026-01-30",
        "source_type": "earnings_release",
        "source_title": "Example source",
        "source_url": "https://example.com/source",
        "note": "Example note",
    }

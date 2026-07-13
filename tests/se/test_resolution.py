from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import CandidateHit, MergeStatus


def _hit(
    hit_id: str,
    asset: str,
    *,
    trial: str | None = None,
    alias: str | None = None,
    company: str = "Example Bio",
) -> CandidateHit:
    return CandidateHit(
        hit_id=hit_id,
        source="fixture",
        source_document_id=f"doc:{hit_id}",
        query="CD19",
        asset_name=asset,
        company_name=company,
        trial_id=trial,
        aliases=[alias] if alias else [],
        target_terms=["CD19"],
        modality_terms=["T_CELL_ENGAGER"],
        provisional_identity_key=f"example bio:{asset}",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 7, 10),
    )


def test_trial_id_deterministically_merges_mentions() -> None:
    registry = AssetRegistry()
    first = registry.ingest_hit(_hit("1", "Asset-A", trial="NCT00000001"))
    second = registry.ingest_hit(_hit("2", "Asset A", trial="nct00000001", alias="Asset-A"))
    assert first.asset_id == second.asset_id
    assert len(registry.assets) == 1
    assert len(second.mention_ids) == 2
    assert "Asset-A" in second.aliases


def test_distinct_interventions_in_same_trial_never_merge_by_trial_id_alone() -> None:
    registry = AssetRegistry()
    cd19 = registry.ingest_hit(_hit("1", "CD19 x CD3 BiTE", trial="NCT00000001"))
    bcma = registry.ingest_hit(_hit("2", "BCMA x CD3 BiTE", trial="NCT00000001"))
    assert cd19.asset_id != bcma.asset_id
    assert len(registry.assets) == 2


def test_distinct_assets_remain_separate_without_deterministic_key() -> None:
    registry = AssetRegistry()
    first = registry.ingest_hit(_hit("1", "Asset A"))
    second = registry.ingest_hit(_hit("2", "Asset B"))
    assert first.asset_id != second.asset_id
    assert len(registry.assets) == 2


def test_exact_asset_identity_merges_across_ownership_changes() -> None:
    registry = AssetRegistry()
    first = registry.ingest_hit(_hit("1", "CLN-978", company="Cullinan"))
    second = registry.ingest_hit(
        _hit("2", "CLN 978", company="Taiho", alias="CLN978", trial="NCT00000002")
    )

    assert first.asset_id == second.asset_id
    assert len(registry.assets) == 1
    assert len(second.company_ids) == 2
    assert second.provisional is False


def test_probabilistic_merge_requires_review_and_is_reversible() -> None:
    registry = AssetRegistry()
    first = registry.ingest_hit(_hit("1", "Asset A", alias="Former A"))
    second = registry.ingest_hit(_hit("2", "Asset Alpha", alias="Alpha"))
    before = {asset_id: asset.model_dump() for asset_id, asset in registry.assets.items()}
    proposal = registry.propose_merge(
        [first.asset_id, second.asset_id], target_asset_id="asset:canonical", confidence=0.88
    )
    with pytest.raises(PermissionError):
        registry.apply_merge(proposal.merge_id)
    merged = registry.apply_merge(proposal.merge_id, analyst_approved=True)
    assert registry.merges[proposal.merge_id].status == MergeStatus.APPLIED
    assert set(merged.aliases) == {"Asset A", "Former A", "Asset Alpha", "Alpha"}

    registry.reverse_merge(proposal.merge_id)
    assert registry.merges[proposal.merge_id].status == MergeStatus.REVERSED
    assert {asset_id: asset.model_dump() for asset_id, asset in registry.assets.items()} == before

from datetime import date, datetime, timezone

from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import CandidateHit, OwnershipRight


def test_ownership_rights_are_temporal_and_geographic() -> None:
    registry = AssetRegistry()
    asset = registry.ingest_hit(
        CandidateHit(
            hit_id="hit:1",
            source="fixture",
            source_document_id="doc:1",
            query="CD19",
            asset_name="Asset A",
            company_name="Original Bio",
            provisional_identity_key="original bio:asset a",
            retrieved_at=datetime.now(timezone.utc),
            applicable_as_of_date=date(2026, 7, 10),
        )
    )
    company_id = asset.company_ids[0]
    registry.add_right(
        OwnershipRight(
            right_id="right:old",
            asset_id=asset.asset_id,
            company_id=company_id,
            geography="US",
            right_type="LICENSE",
            effective_from=date(2020, 1, 1),
            effective_to=date(2024, 12, 31),
            supporting_claim_ids=["claim:old"],
        )
    )
    registry.add_right(
        OwnershipRight(
            right_id="right:new",
            asset_id=asset.asset_id,
            company_id=company_id,
            geography="EU",
            right_type="LICENSE",
            effective_from=date(2025, 1, 1),
            supporting_claim_ids=["claim:new"],
        )
    )
    assert registry.rights_as_of(asset.asset_id, as_of_date=date(2024, 1, 1), geography="US")
    assert registry.rights_as_of(asset.asset_id, as_of_date=date(2024, 1, 1), geography="EU") == []
    assert registry.rights_as_of(asset.asset_id, as_of_date=date(2026, 1, 1), geography="EU")[0].right_id == "right:new"

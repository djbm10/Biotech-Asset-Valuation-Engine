"""ARM_VARIANT_IDENTITY v1: dose/arm/cohort variants listed by one record are one asset.

Policy: ``docs/se_policies/arm_variant_identity_v1.md``.
"""

from __future__ import annotations

import pytest

from bve.se.resolution.registry import AssetRegistry, arm_variant_base
from bve.se.schemas.contracts import CanonicalAsset


def _registry(*assets: tuple[str, str, list[str]]) -> AssetRegistry:
    registry = AssetRegistry()
    for asset_id, name, trials in assets:
        registry._index_asset(
            CanonicalAsset(asset_id=asset_id, canonical_name=name, aliases=[name], trial_ids=trials)
        )
    return registry


@pytest.mark.parametrize(
    "name, base",
    [
        ("X-123 Dose 1", "X-123"),
        ("X-123 Dose level 2", "X-123"),
        ("Product T cells - iv high dose", "Product T cells"),
        ("Product T cells -iv low dose", "Product T cells"),
        ("Product for Group B", "Product for"),
        ("Product Cohort 3", "Product"),
        ("Product (Arm A)", "Product"),
    ],
)
def test_the_closed_qualifier_grammar(name, base) -> None:
    assert arm_variant_base(name) == base


@pytest.mark.parametrize("name", ["NKTR-255", "Group B", "Product Part Z", "Dose", "CAR-T 2"])
def test_names_without_a_qualifier_have_no_base(name) -> None:
    assert arm_variant_base(name) is None


def test_variants_listed_by_one_record_merge_with_all_names_kept() -> None:
    registry = _registry(("a", "P Dose 1", ["NCT1"]), ("b", "P Dose 2", ["NCT1", "NCT2"]))
    redirects = registry.consolidate_arm_variants()
    assert redirects == {"b": "a"}
    merged = registry.assets["a"]
    assert {"P Dose 1", "P Dose 2"} <= set(merged.aliases)
    assert set(merged.trial_ids) == {"NCT1", "NCT2"}
    assert "b" not in registry.assets


def test_textual_similarity_without_a_shared_record_never_merges() -> None:
    registry = _registry(("a", "P Dose 1", ["NCT1"]), ("b", "P Dose 2", ["NCT2"]))
    assert registry.consolidate_arm_variants() == {}
    assert {"a", "b"} <= set(registry.assets)


def test_a_qualified_name_never_attaches_to_an_unqualified_one() -> None:
    registry = _registry(("a", "P", ["NCT1"]), ("b", "P Dose 2", ["NCT1"]))
    assert registry.consolidate_arm_variants() == {}


def test_the_merge_is_reversible() -> None:
    registry = _registry(("a", "P Dose 1", ["NCT1"]), ("b", "P Dose 2", ["NCT1"]))
    registry.consolidate_arm_variants()
    (merge_id,) = list(registry.merges)
    assert registry.merges[merge_id].deterministic_basis == "arm_variant:p:NCT1"
    registry.reverse_merge(merge_id)
    assert {"a", "b"} <= set(registry.assets)

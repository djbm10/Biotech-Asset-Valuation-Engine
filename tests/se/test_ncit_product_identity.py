"""NCIT_PRODUCT_IDENTITY v1: assets linked to one NCIt product concept are one asset.

Policy: ``docs/se_policies/ncit_product_identity_v1.md``.
"""

from __future__ import annotations

import pytest

from bve.se.resolution.registry import AssetRegistry, is_generic_designator
from bve.se.schemas.contracts import CanonicalAsset

#: A stand-in for the NCIt link: a name -> code table, ambiguous when a name reaches two.
_NAMES = {"p-1": "C1", "product one": "C1", "car19": "C1", "q-2": "C2", "shared": "C1"}


def _link(names: list[str]) -> str | None:
    codes = {_NAMES[n.casefold()] for n in names if n.casefold() in _NAMES}
    return next(iter(codes)) if len(codes) == 1 else None


def _registry(*assets: tuple[str, str, list[str], list[str]]) -> AssetRegistry:
    registry = AssetRegistry()
    for asset_id, name, aliases, trials in assets:
        registry._index_asset(
            CanonicalAsset(
                asset_id=asset_id, canonical_name=name, aliases=[name, *aliases], trial_ids=trials
            )
        )
    return registry


@pytest.mark.parametrize(
    "name", ["CAR19", "CART19", "CAR-T19", "CAR-T 19", "CAR22", "CART-22", "car t 19", "CAR123"]
)
def test_the_generic_designator_grammar(name) -> None:
    assert is_generic_designator(name)


@pytest.mark.parametrize(
    "name", ["CAR039", "CAR-011", "CAR-T", "CARTmeso", "GC022", "TAK-007", "CAR1234", "MB-CART19.1"]
)
def test_sponsor_codes_and_products_are_not_designators(name) -> None:
    assert not is_generic_designator(name)


def test_same_concept_assets_merge_with_names_and_trials_kept() -> None:
    registry = _registry(("b", "Product One", [], ["NCT2"]), ("a", "P-1", [], ["NCT1"]))
    redirects = registry.consolidate_by_ncit_product(lambda asset: _link([asset.canonical_name]))
    assert redirects == {"b": "a"}
    merged = registry.assets["a"]
    assert {"P-1", "Product One"} <= set(merged.aliases)
    assert set(merged.trial_ids) == {"NCT1", "NCT2"}
    merge = next(iter(registry.merges.values()))
    assert merge.deterministic_basis == "ncit_product:C1"


def test_a_generic_designator_keeps_its_own_identity_and_trials() -> None:
    registry = _registry(
        ("a", "P-1", [], ["NCT1"]),
        ("b", "Product One", [], ["NCT2"]),
        ("c", "CART19", ["CART-19"], ["NCT9"]),
    )
    redirects = registry.consolidate_by_ncit_product(lambda asset: _link([asset.canonical_name]))
    assert redirects == {"b": "a"}
    assert registry.assets["c"].trial_ids == ["NCT9"]
    assert "NCT9" not in registry.assets["a"].trial_ids


def test_one_specific_name_makes_an_asset_participate() -> None:
    registry = _registry(("a", "P-1", [], ["NCT1"]), ("b", "CAR19", ["Product One"], ["NCT2"]))
    assert registry.consolidate_by_ncit_product(
        lambda asset: _link([asset.canonical_name])
    ) == {"a": "b"}


def test_a_lone_participant_and_a_designator_do_not_merge() -> None:
    registry = _registry(("a", "P-1", [], ["NCT1"]), ("b", "CAR19", [], ["NCT2"]))
    assert registry.consolidate_by_ncit_product(lambda asset: _link([asset.canonical_name])) == {}
    assert set(registry.assets) == {"a", "b"}


def test_different_concepts_and_unlinked_assets_stay_apart() -> None:
    registry = _registry(("a", "P-1", [], []), ("b", "Q-2", [], []), ("c", "Other", [], []))
    assert registry.consolidate_by_ncit_product(lambda asset: _link([asset.canonical_name])) == {}


def test_the_merge_is_reversible() -> None:
    registry = _registry(("a", "P-1", [], ["NCT1"]), ("b", "Product One", [], ["NCT2"]))
    registry.consolidate_by_ncit_product(lambda asset: _link([asset.canonical_name]))
    registry.reverse_merge(next(iter(registry.merges)))
    assert registry.assets["b"].trial_ids == ["NCT2"]

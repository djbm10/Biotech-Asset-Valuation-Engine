"""PROTOCOL_ID_TRIAL_ATTRIBUTION v1: a trial's own protocol id can move it to its coded product.

Policy: ``docs/se_policies/protocol_id_trial_attribution_v1.md``.
"""

from __future__ import annotations

import pytest

from bve.se.resolution.protocol_attribution import (
    is_generic_descriptor,
    plan_protocol_moves,
    protocol_prefix,
)
from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import CanonicalAsset


def _asset(asset_id: str, name: str, trials: list[str]) -> CanonicalAsset:
    return CanonicalAsset(asset_id=asset_id, canonical_name=name, aliases=[name], trial_ids=trials)


def _record(protocol_id: str, *interventions: str) -> dict:
    return {
        "identificationModule": {"orgStudyIdInfo": {"id": protocol_id}},
        "armsInterventionsModule": {"interventions": [{"name": n} for n in interventions]},
    }


def _no_drug(names: list[str]) -> bool:
    return False


def _plan(assets, records, has_drug=_no_drug):
    return [(m.trial_id, m.from_asset_id, m.to_asset_id) for m in plan_protocol_moves(assets, records, has_drug)]


@pytest.mark.parametrize(
    "protocol_id, prefix",
    [("XYZ123-005", "XYZ123"), ("ABC-321-ITP-01", "ABC-321"), ("QQ77", "QQ77"), ("Phase I", None), ("", None)],
)
def test_protocol_prefix(protocol_id, prefix) -> None:
    assert protocol_prefix(protocol_id) == prefix


def test_descriptor_trial_moves_to_its_demonstrated_coded_product() -> None:
    assets = [_asset("d", "XYZ123", ["NCT1"]), _asset("s", "CD19-targeted CAR T Cells", ["NCT2"])]
    records = {"NCT1": _record("XYZ123-001", "XYZ123"), "NCT2": _record("XYZ123-005", "CD19-targeted CAR T Cells")}
    assert _plan(assets, records) == [("NCT2", "s", "d")]


def test_a_study_series_prefix_no_intervention_uses_does_not_move() -> None:
    assets = [_asset("d", "SER-009", ["NCT1"]), _asset("s", "CAR-T cells", ["NCT2"])]
    records = {"NCT1": _record("SER-009-101", "Other Name"), "NCT2": _record("SER-009-201", "CAR-T cells")}
    assert _plan(assets, records) == []


def test_antigen_shaped_prefixes_never_move() -> None:
    assets = [_asset("d", "CD19", ["NCT1"]), _asset("s", "CAR-T cells", ["NCT2"])]
    records = {"NCT1": _record("CD19-001", "CD19"), "NCT2": _record("CD19-005", "CAR-T cells")}
    assert _plan(assets, records) == []


def test_product_specific_sources_keep_their_trials() -> None:
    coded = [_asset("d", "XYZ123", ["NCT1"]), _asset("s", "QRS44", ["NCT2"])]
    records = {"NCT1": _record("XYZ123-001", "XYZ123"), "NCT2": _record("XYZ123-002", "QRS44")}
    assert _plan(coded, records) == []
    drug = [_asset("d", "XYZ123", ["NCT1"]), _asset("s", "fludarabine", ["NCT2"])]
    records["NCT2"] = _record("XYZ123-002", "fludarabine")
    assert _plan(drug, records, has_drug=lambda names: "fludarabine" in names) == []


def test_generic_destinations_and_held_trials_do_not_move() -> None:
    assets = [_asset("d", "XYZ123", ["NCT1", "NCT2"]), _asset("s", "CAR-T cells", ["NCT2"])]
    records = {"NCT1": _record("XYZ123-001", "XYZ123"), "NCT2": _record("XYZ123-002", "CAR-T cells")}
    assert _plan(assets, records) == []


def test_ambiguous_destination_does_not_move() -> None:
    assets = [_asset("d1", "XYZ123", ["NCT1"]), _asset("d2", "XYZ-123", ["NCT3"]), _asset("s", "CAR-T cells", ["NCT2"])]
    records = {
        "NCT1": _record("x", "XYZ123"),
        "NCT3": _record("y", "XYZ-123"),
        "NCT2": _record("XYZ123-002", "CAR-T cells"),
    }
    assert _plan(assets, records) == []


@pytest.mark.parametrize("name, generic", [("CD19/BCMA CAR T-cells", True), ("CART19", True), ("ICG318", False), ("BCMA-CD19 cCAR T cells", False)])
def test_generic_descriptor_vocabulary(name, generic) -> None:
    assert is_generic_descriptor(name) is generic


def test_reattribution_moves_one_trial_and_keeps_an_emptied_source() -> None:
    registry = AssetRegistry()
    registry._index_asset(_asset("d", "XYZ123", ["NCT1"]))
    registry._index_asset(_asset("s", "CAR-T cells", ["NCT2"]))
    registry.reattribute_trial("NCT2", "s", "d")
    assert registry.assets["d"].trial_ids == ["NCT1", "NCT2"]
    assert registry.assets["s"].trial_ids == []
    with pytest.raises(ValueError):
        registry.reattribute_trial("NCT2", "s", "d")

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bve.se.ranking.acquisition import (
    AcquisitionCandidate,
    rank_acquisition_candidates,
)


def _candidate(asset_id: str, disposition: str = "INCLUDE", **updates: object) -> AcquisitionCandidate:
    values = dict(
        asset_id=asset_id,
        disposition=disposition,
        human_proof_of_concept=0.8,
        clinical_meaningfulness=0.8,
        evidence_quality=0.8,
        buyer_development_fit=0.8,
        differentiation=0.8,
        deal_feasibility=0.8,
        best_owner_rationale="Buyer has the relevant development and commercial capabilities.",
        supporting_claim_ids=[f"claim:{asset_id}"],
    )
    values.update(updates)
    return AcquisitionCandidate(**values)


def test_only_include_assets_are_ranked_and_unknown_is_routed() -> None:
    result = rank_acquisition_candidates(
        [
            _candidate("include-a", buyer_development_fit=1.0),
            _candidate("include-b", clinical_meaningfulness=0.9),
            _candidate("unknown-a", "UNKNOWN"),
            _candidate("exclude-a", "EXCLUDE"),
        ]
    )

    assert [item.asset_id for item in result.ranked] == ["include-a", "include-b"]
    assert [item.asset_id for item in result.diligence] == ["unknown-a"]
    assert result.excluded_asset_ids == ["exclude-a"]
    assert all(item.public_pre_diligence for item in result.ranked)


def test_best_owner_rationale_and_valuation_boundary_are_explicit() -> None:
    result = rank_acquisition_candidates([_candidate("asset-a")])
    item = result.ranked[0]
    assert "capabilities" in item.best_owner_rationale
    assert "valuation" not in item.model_dump()

    with pytest.raises(ValueError, match="extra_forbid|valuation"):
        _candidate("asset-b", valuation=123.0)


def test_exclude_can_never_enter_ranked_output() -> None:
    result = rank_acquisition_candidates([_candidate("excluded", "EXCLUDE")])
    assert result.ranked == []
    assert result.diligence == []
    assert result.excluded_asset_ids == ["excluded"]


def test_duplicate_assets_fail_closed() -> None:
    with pytest.raises(ValueError, match="unique"):
        rank_acquisition_candidates([_candidate("same"), _candidate("same")])


def _fixture_candidates(filename: str) -> tuple[list[AcquisitionCandidate], dict]:
    path = Path("research/se_benchmarks/acquisition_ranking") / filename
    payload = json.loads(path.read_text())
    candidates = [
        _candidate(
            case["asset_id"],
            case["disposition"],
            **dict(zip(
                (
                    "human_proof_of_concept",
                    "clinical_meaningfulness",
                    "evidence_quality",
                    "buyer_development_fit",
                    "differentiation",
                    "deal_feasibility",
                ),
                case["scores"],
                strict=True,
            )),
        )
        for case in payload["cases"]
    ]
    return candidates, payload


@pytest.mark.parametrize("filename", ["development.json", "unseen_holdout.json"])
def test_frozen_ranking_benchmarks(filename: str) -> None:
    candidates, payload = _fixture_candidates(filename)
    result = rank_acquisition_candidates(candidates)
    expected = {
        case["asset_id"]: case
        for case in payload["cases"]
        if case["disposition"] == "INCLUDE"
    }
    assert [item.asset_id for item in result.ranked] == [
        asset_id for asset_id, _ in sorted(
            ((asset_id, case["expected_rank"]) for asset_id, case in expected.items()),
            key=lambda item: item[1],
        )
    ]
    assert {item.asset_id for item in result.diligence} == {
        case["asset_id"]
        for case in payload["cases"]
        if case.get("route") == "DILIGENCE"
    }
    assert result.excluded_asset_ids == [
        case["asset_id"]
        for case in payload["cases"]
        if case.get("route") == "EXCLUDED"
    ]

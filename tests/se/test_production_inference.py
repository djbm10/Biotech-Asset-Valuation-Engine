from __future__ import annotations

from bve.se.evaluation.production_inference import QueryPrediction, build_predictions


def _fixture() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    candidates = ["strong", "partial", "uncertain", "poor", "excluded"]
    query = {
        "query_id": "Q1",
        "buyer_id": "B1",
        "target": "T1",
        "modality": "M1",
        "evidence_profile": "P1",
        "strategic_priority": "clinical fit",
        "candidate_ids": candidates,
    }
    evidence = []
    for candidate, fit, stage, completeness in zip(
        candidates,
        ("strong-fit", "partial-fit", "uncertain", "poor-fit", "disqualifying"),
        ("Phase 2", "Phase 1", "preclinical", "discontinued", "discontinued"),
        ("high", "medium", "low", "medium", "high"),
        strict=True,
    ):
        evidence.append(
            {
                "query_id": "Q1",
                "candidate_id": candidate,
                "evidence_id": f"E-{candidate}",
                "observed_attributes": {
                    "fit_signal": fit,
                    "development_stage": stage,
                    "evidence_completeness": completeness,
                },
            }
        )
    return [query], evidence


def test_end_to_end_unknowns_are_queued_once_and_never_ranked() -> None:
    queries, evidence = _fixture()
    prediction = build_predictions(queries, evidence)[0]

    assert prediction.ranked_asset_ids == ["strong", "partial"]
    assert prediction.diligence_asset_ids == ["uncertain", "poor"]
    assert prediction.excluded_asset_ids == ["excluded"]
    assert [item.asset_id for item in prediction.diligence_queue] == ["uncertain", "poor"]
    assert not set(prediction.ranked_asset_ids) & set(prediction.diligence_asset_ids)
    for item in prediction.diligence_queue:
        assert item.missing_or_conflicting_gate
        assert item.supporting_evidence == [f"E-{item.asset_id}"]
        assert item.specific_diligence_question
    serialized = prediction.serialized_output
    assert [item["asset_id"] for item in serialized["diligence_queue"]] == ["uncertain", "poor"]
    assert "diligence" not in serialized


def test_prediction_rejects_duplicate_or_ranked_queue_assets() -> None:
    queries, evidence = _fixture()
    prediction = build_predictions(queries, evidence)[0]
    queued = prediction.diligence_queue[0]

    try:
        QueryPrediction(**{
            **prediction.model_dump(),
            "diligence_asset_ids": [queued.asset_id, queued.asset_id],
            "diligence_queue": [queued, queued],
        })
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate diligence routing must fail")

    try:
        QueryPrediction(**{
            **prediction.model_dump(),
            "ranked_asset_ids": [queued.asset_id],
        })
    except ValueError as exc:
        assert "never be ranked" in str(exc)
    else:
        raise AssertionError("ranked UNKNOWN asset must fail")

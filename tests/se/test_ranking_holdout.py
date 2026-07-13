from __future__ import annotations

from bve.se.evaluation.ranking_holdout import (
    HoldoutPrediction,
    HoldoutQuery,
    ProductionValidationThresholds,
    evaluate_ranking_holdout,
)
from bve.se.ranking.acquisition import DiligenceItem


def _queue_item(asset_id: str, claim: str) -> DiligenceItem:
    return DiligenceItem(
        asset_id=asset_id,
        missing_or_conflicting_gate="human_proof_of_concept",
        supporting_evidence=[claim],
        specific_diligence_question=f"What resolves the evidence gate for {asset_id}?",
        rationale="UNKNOWN disposition requires diligence.",
        required_checks=["confirm evidence"],
    )


def _holdout() -> tuple[list[HoldoutQuery], list[HoldoutPrediction]]:
    queries: list[HoldoutQuery] = []
    predictions: list[HoldoutPrediction] = []
    for index in range(24):
        buyer = f"buyer-{index % 3}"
        target = f"target-{index % 3}"
        modality = f"modality-{index % 3}"
        profile = f"profile-{index % 4}"
        query_id = f"query-{index}"
        best = f"asset-{index}-best"
        other = f"asset-{index}-other"
        unknown = f"asset-{index}-unknown"
        queries.append(
            HoldoutQuery(
                query_id=query_id,
                buyer_id=buyer,
                target=target,
                modality=modality,
                evidence_profile=profile,
                relevance_by_asset={best: 3, other: 1, unknown: 0},
                dispositions_by_asset={best: "INCLUDE", other: "INCLUDE", unknown: "UNKNOWN"},
                required_citation_assets=[best],
                diligence_assets=[unknown],
            )
        )
        predictions.append(
            HoldoutPrediction(
                query_id=query_id,
                ranked_asset_ids=[best, other],
                diligence_asset_ids=[unknown],
                diligence_queue=[_queue_item(unknown, f"claim-{index}-unknown")],
                excluded_asset_ids=[],
                citations_by_asset={best: [f"claim-{index}"]},
                rationale_quality=0.9,
                diligence_question_usefulness=0.9,
            )
        )
    return queries, predictions


def test_only_sealed_holdout_can_grant_production_eligibility() -> None:
    queries, predictions = _holdout()
    for status in ("DEVELOPMENT", "EXPOSED"):
        rejected = evaluate_ranking_holdout(queries, predictions, holdout_status=status)
        assert rejected.status == "FAIL"
        assert rejected.release_eligible is False
        assert any("not sealed" in failure for failure in rejected.failures)

    scored = evaluate_ranking_holdout(queries, predictions, holdout_status="SEALED")
    assert scored.status == "PASS"
    assert scored.release_eligible is True
    assert scored.coverage.adequate is True
    assert scored.metrics is not None
    assert scored.metrics.top_k_shortlist_recall == 1.0
    assert scored.metrics.ndcg_at_k == 1.0
    assert scored.metrics.citation_completeness == 1.0


def test_semantic_route_and_valuation_leakage_fail_closed() -> None:
    queries, predictions = _holdout()
    predictions[0] = predictions[0].model_copy(
        update={
            "ranked_asset_ids": predictions[0].ranked_asset_ids + [predictions[0].diligence_asset_ids[0]],
            "serialized_output": {"valuation": {"rnpv": 10}},
        }
    )
    report = evaluate_ranking_holdout(
        queries,
        predictions,
        thresholds=ProductionValidationThresholds(),
        holdout_status="OPEN",
    )
    assert report.release_eligible is False
    assert report.metrics is not None
    assert report.metrics.zero_gate_leakage is False
    assert report.metrics.zero_valuation_leakage is False


def test_legitimate_gate_explanation_is_not_leakage() -> None:
    queries, predictions = _holdout()
    predictions[0] = predictions[0].model_copy(
        update={
            "serialized_output": {
                "diligence_queue": [
                    {
                        "asset_id": predictions[0].diligence_asset_ids[0],
                        "missing_or_conflicting_gate": "human_proof_of_concept",
                        "specific_diligence_question": "Which result resolves this gate?",
                    }
                ],
                "gate_explanation": "The gate is unresolved and requires diligence.",
            }
        }
    )
    report = evaluate_ranking_holdout(queries, predictions, holdout_status="SEALED")

    assert report.status == "PASS"
    assert report.metrics is not None
    assert report.metrics.zero_gate_leakage is True


def test_crossed_or_duplicate_routes_are_semantic_gate_leakage() -> None:
    queries, predictions = _holdout()
    unknown = predictions[0].diligence_asset_ids[0]
    predictions[0] = predictions[0].model_copy(
        update={"ranked_asset_ids": predictions[0].ranked_asset_ids + [unknown]}
    )
    report = evaluate_ranking_holdout(queries, predictions, holdout_status="SEALED")

    assert report.status == "FAIL"
    assert report.metrics is not None
    assert report.metrics.zero_gate_leakage is False
    assert any("semantic route leakage" in failure for failure in report.failures)


def test_public_output_label_is_not_production_proof() -> None:
    from bve.se.pipeline import DEVELOPMENT_SCREEN_LABEL

    assert DEVELOPMENT_SCREEN_LABEL == (
        "Production-validated public-data S&E screen; pre-diligence—not verified truth."
    )

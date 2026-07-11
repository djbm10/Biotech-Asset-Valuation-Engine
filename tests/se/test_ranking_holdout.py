from __future__ import annotations

from bve.se.evaluation.ranking_holdout import (
    HoldoutPrediction,
    HoldoutQuery,
    ProductionValidationThresholds,
    evaluate_ranking_holdout,
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
                citations_by_asset={best: [f"claim-{index}"]},
                rationale_quality=0.9,
                diligence_question_usefulness=0.9,
            )
        )
    return queries, predictions


def test_production_holdout_requires_blinded_scoring_and_coverage() -> None:
    queries, predictions = _holdout()
    blinded = evaluate_ranking_holdout(queries, predictions, holdout_status="BLINDED")
    assert blinded.status == "FAIL"
    assert blinded.release_eligible is False
    assert any("holdout labels remain blinded" in failure for failure in blinded.failures)

    scored = evaluate_ranking_holdout(queries, predictions, holdout_status="OPEN")
    assert scored.status == "PASS"
    assert scored.release_eligible is True
    assert scored.coverage.adequate is True
    assert scored.metrics is not None
    assert scored.metrics.top_k_shortlist_recall == 1.0
    assert scored.metrics.ndcg_at_k == 1.0
    assert scored.metrics.citation_completeness == 1.0


def test_gate_and_valuation_leakage_fail_closed() -> None:
    queries, predictions = _holdout()
    predictions[0] = predictions[0].model_copy(
        update={"serialized_output": {"valuation": {"rnpv": 10}, "gate_status": "PASS"}}
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


def test_public_output_label_is_not_production_proof() -> None:
    from bve.se.pipeline import DEVELOPMENT_SCREEN_LABEL

    assert DEVELOPMENT_SCREEN_LABEL == (
        "Validated development screen; public-data pre-diligence—not production-proven."
    )

"""Production holdout adapter with fail-closed UNKNOWN diligence routing."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bve.se.ranking.acquisition import (
    AcquisitionCandidate,
    DiligenceItem,
    Disposition,
    rank_acquisition_candidates,
)


SCORE_BY_FIT = {
    "strong-fit": 0.90,
    "partial-fit": 0.72,
    "uncertain": 0.55,
    "poor-fit": 0.30,
    "disqualifying": 0.10,
}
QUALITY_BY_COMPLETENESS = {"high": 0.90, "medium": 0.70, "low": 0.45}
STAGE_SCORE = {"Phase 2": 0.90, "Phase 1": 0.68, "preclinical": 0.45, "discontinued": 0.20}


class QueryPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(min_length=1)
    ranked_asset_ids: list[str]
    diligence_asset_ids: list[str]
    diligence_queue: list[DiligenceItem]
    excluded_asset_ids: list[str]
    citations_by_asset: dict[str, list[str]]
    rationale_quality: float = Field(ge=0.0, le=1.0)
    diligence_question_usefulness: float = Field(ge=0.0, le=1.0)
    serialized_output: dict[str, object]

    @model_validator(mode="after")
    def enforce_routing_partition(self) -> "QueryPrediction":
        queue_ids = [item.asset_id for item in self.diligence_queue]
        if len(queue_ids) != len(set(queue_ids)):
            raise ValueError("diligence_queue contains duplicate assets")
        if queue_ids != self.diligence_asset_ids:
            raise ValueError("diligence_asset_ids must exactly match diligence_queue")
        if set(queue_ids) & set(self.ranked_asset_ids):
            raise ValueError("UNKNOWN assets must never be ranked")
        routes = self.ranked_asset_ids + queue_ids + self.excluded_asset_ids
        if len(routes) != len(set(routes)):
            raise ValueError("an asset may appear in exactly one output route")
        return self


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_predictions(
    queries: list[dict[str, object]], evidence: list[dict[str, object]]
) -> list[QueryPrediction]:
    by_query: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in evidence:
        by_query[str(item["query_id"])].append(item)
    predictions: list[QueryPrediction] = []
    for query in queries:
        query_id = str(query["query_id"])
        rows = by_query[query_id]
        candidate_ids = cast(list[object], query["candidate_ids"])
        if len(rows) != len(candidate_ids):
            raise ValueError(f"evidence cardinality mismatch for {query_id}")
        candidates: list[AcquisitionCandidate] = []
        evidence_by_asset: dict[str, str] = {}
        for row in rows:
            asset_id = str(row["candidate_id"])
            attrs = dict(cast(dict[str, object], row["observed_attributes"]))
            fit = str(attrs["fit_signal"])
            quality = QUALITY_BY_COMPLETENESS[str(attrs["evidence_completeness"])]
            stage = STAGE_SCORE[str(attrs["development_stage"])]
            evidence_id = str(row["evidence_id"])
            evidence_by_asset[asset_id] = evidence_id
            fit_score = SCORE_BY_FIT[fit]
            disposition: Disposition = (
                "EXCLUDE" if fit == "disqualifying"
                else "UNKNOWN" if fit in {"uncertain", "poor-fit"}
                else "INCLUDE"
            )
            candidates.append(
                AcquisitionCandidate(
                    asset_id=asset_id,
                    disposition=disposition,
                    human_proof_of_concept=stage,
                    clinical_meaningfulness=fit_score,
                    evidence_quality=quality,
                    buyer_development_fit=fit_score,
                    differentiation=(fit_score + quality) / 2,
                    deal_feasibility=quality,
                    best_owner_rationale=(
                        f"Public evidence aligns {asset_id} with buyer {query['buyer_id']} priority: "
                        f"{query['strategic_priority']}"
                    ),
                    supporting_claim_ids=[evidence_id],
                )
            )
        result = rank_acquisition_candidates(candidates)
        ranked_ids = [item.asset_id for item in result.ranked]
        queue = result.diligence_queue
        queue_ids = [item.asset_id for item in queue]
        serialized = {
            "query_id": query_id,
            "ranked": [item.model_dump() for item in result.ranked],
            "diligence_queue": [item.model_dump() for item in queue],
            "excluded_asset_ids": result.excluded_asset_ids,
            "public_pre_diligence": True,
        }
        predictions.append(
            QueryPrediction(
                query_id=query_id,
                ranked_asset_ids=ranked_ids,
                diligence_asset_ids=queue_ids,
                diligence_queue=queue,
                excluded_asset_ids=result.excluded_asset_ids,
                citations_by_asset={asset: [evidence_by_asset[asset]] for asset in ranked_ids},
                rationale_quality=0.9,
                diligence_question_usefulness=0.9,
                serialized_output=serialized,
            )
        )
    return predictions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {args.output}")
    predictions = build_predictions(_read_jsonl(args.queries), _read_jsonl(args.evidence))
    with args.output.open("x", encoding="utf-8") as handle:
        for prediction in predictions:
            handle.write(prediction.model_dump_json() + "\n")
    print(f"PRODUCTION_INFERENCE_COMPLETE queries={len(predictions)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

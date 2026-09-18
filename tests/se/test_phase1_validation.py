from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from bve.se.phase1_validation import (
    AssetHardGateReview,
    BaselineCustody,
    DossierField,
    FieldProvenance,
    FieldVerdict,
    Phase1ReleaseGate,
    ReferenceUniverseSpec,
    ReviewFlag,
    ReviewStatus,
    UnseededRunEvaluation,
    canonical_asset_set_hash,
)

NOW = datetime(2026, 7, 16, tzinfo=timezone.utc)
HASH = "a" * 64


def _provenance(
    asset_id: str, field_name: str, value: object, value_key: str | int | None = None
) -> FieldProvenance:
    return FieldProvenance(
        asset_id=asset_id,
        field_name=field_name,
        value=value,
        value_key=value_key,
        supporting_claim_id=f"claim:{asset_id}:{field_name}:{value_key}",
        exact_source_passage="The source explicitly states the field.",
        source_document_id=f"doc:{asset_id}",
        source_url="https://example.test/source",
        as_of_date=date(2026, 7, 10),
        verification_status=ReviewStatus.CONFIRMED,
        verdict=FieldVerdict.SUPPORTED,
        reviewer="reviewer-1",
        reviewed_at=NOW,
    )


def _field(asset_id: str, name: str, value: object) -> DossierField:
    items = (
        [_provenance(asset_id, name, item, index) for index, item in enumerate(value)]
        if isinstance(value, list)
        else []
    )
    return DossierField(
        field_name=name,
        value=value,
        provenance=_provenance(asset_id, name, value),
        item_provenance=items,
        verdict=FieldVerdict.SUPPORTED,
    )


def _review(asset_id: str, status: ReviewStatus = ReviewStatus.CONFIRMED) -> AssetHardGateReview:
    return AssetHardGateReview(
        asset_id=asset_id,
        canonical_identity=_field(asset_id, "canonical_identity", "ASSET-1"),
        aliases=_field(asset_id, "aliases", ["A1"]),
        linked_companies=_field(asset_id, "linked_companies", ["company:1"]),
        ownership=DossierField(
            field_name="ownership", conflict_status="MISSING", verdict=FieldVerdict.MISSING
        ),
        target=_field(asset_id, "target", ["CD19"]),
        modality=_field(asset_id, "modality", "T_CELL_ENGAGER"),
        trials=_field(asset_id, "trials", ["NCT00000001"]),
        adjudication_status=status,
        reviewer="reviewer-1",
        reviewed_at=NOW,
    )


def _custody(asset_ids: tuple[str, ...] = ("asset:1",)) -> BaselineCustody:
    return BaselineCustody(
        code_commit="962e322",
        problem_hash=HASH,
        config_hashes={"problem.yaml": HASH},
        source_manifest_hash=HASH,
        corpus_hash=HASH,
        result_json_hash=HASH,
        asset_ids=asset_ids,
        asset_id_set_hash=canonical_asset_set_hash(asset_ids),
        as_of_date=date(2026, 7, 10),
    )


def _universe(
    universe_id: str, target: str, modality: str = "T_CELL_ENGAGER"
) -> ReferenceUniverseSpec:
    return ReferenceUniverseSpec(
        universe_id=universe_id,
        target=target,
        modality=modality,
        as_of_date=date(2026, 7, 10),
        inclusion_criteria=["Target and modality explicitly supported"],
        exclusion_criteria=["Target or modality unsupported"],
        citations=["https://example.test/criteria"],
        asset_count=1,
        asset_file_hash=HASH,
        asset_citations={"universe-asset-1": ("https://example.test/asset-1",)},
        universe_hash=HASH,
        reviewers=("reviewer-a", "reviewer-b"),
        sealed_at=NOW,
        minimum_recall=0.95,
        minimum_precision=0.95,
    )


def _run(universe: ReferenceUniverseSpec, modality: str | None = None) -> UnseededRunEvaluation:
    return UnseededRunEvaluation(
        universe_id=universe.universe_id,
        run_id=f"run-{universe.universe_id}",
        target=universe.target,
        modality=modality or universe.modality,
        unseeded=True,
        universe_hash=universe.universe_hash,
        result_json_hash=HASH,
        evaluation_report_hash=HASH,
        applicable_as_of_date=universe.as_of_date,
        pipeline_commit="962e322",
        recall=1.0,
        precision=1.0,
    )


def _field_provenance(review: AssetHardGateReview) -> list[FieldProvenance]:
    output: list[FieldProvenance] = []
    for field in (
        review.canonical_identity,
        review.aliases,
        review.linked_companies,
        review.target,
        review.modality,
        review.trials,
    ):
        if field.provenance:
            output.append(field.provenance)
        output.extend(field.item_provenance)
    return output


def test_populated_dossier_field_requires_field_level_provenance() -> None:
    with pytest.raises(ValidationError, match="field-level provenance"):
        DossierField(field_name="target", value=["CD19"], verdict=FieldVerdict.SUPPORTED)


def test_list_field_requires_provenance_for_each_value() -> None:
    with pytest.raises(ValidationError, match="every value"):
        DossierField(
            field_name="aliases",
            value=["A1", "A2"],
            provenance=_provenance("asset:1", "aliases", ["A1", "A2"]),
            item_provenance=[_provenance("asset:1", "aliases", "A1", 0)],
            verdict=FieldVerdict.SUPPORTED,
        )


def test_machine_heuristic_defaults_to_suspected() -> None:
    flag = ReviewFlag(
        flag_id="flag:1", asset_id="asset:1", flag_type="shared_trial", rationale="same trial"
    )
    assert flag.status is ReviewStatus.SUSPECTED


def test_placeholder_reviewers_are_rejected() -> None:
    with pytest.raises(ValidationError, match="placeholder reviewer"):
        ReferenceUniverseSpec(
            **{
                **_universe("dll3", "DLL3").model_dump(),
                "reviewers": ("UNASSIGNED_REVIEWER_A", "reviewer-b"),
            }
        )


def test_reference_universe_requires_dual_review_and_asset_rows() -> None:
    with pytest.raises(ValidationError, match="two distinct reviewers"):
        ReferenceUniverseSpec(
            **{**_universe("dll3", "DLL3").model_dump(), "reviewers": ("same", "same")}
        )


def test_release_gate_rejects_wrong_baseline_asset_set_and_unbound_run() -> None:
    review = _review("asset:1")
    dll3 = _universe("dll3", "DLL3")
    cldn = _universe("cldn18_2_adc_v1", "CLDN18.2", "ADC")
    gate = Phase1ReleaseGate(
        expected_asset_count=1,
        hard_gate_reviews=[review],
        field_provenance=_field_provenance(review),
        custody=_custody(("asset:wrong",)),
        reference_universes=[dll3, cldn],
        unseeded_runs=[_run(dll3), _run(cldn)],
    )
    assert not gate.passes()
    assert any("exactly match" in failure for failure in gate.failures)


def test_release_gate_rejects_unreviewed_probabilistic_merge() -> None:
    review = _review("asset:1")
    dll3 = _universe("dll3", "DLL3")
    cldn = _universe("cldn18_2_adc_v1", "CLDN18.2", "ADC")
    gate = Phase1ReleaseGate(
        expected_asset_count=1,
        hard_gate_reviews=[review],
        field_provenance=_field_provenance(review),
        review_flags=[],
        custody=_custody().model_copy(update={"probabilistic_merge_ids": ("merge:1",)}),
        reference_universes=[dll3, cldn],
        unseeded_runs=[_run(dll3), _run(cldn)],
    )
    assert any("merge:1" in failure for failure in gate.failures)


def test_cldn18_2_run_must_use_adc() -> None:
    cldn = _universe("cldn18_2_adc_v1", "CLDN18.2", "ADC")
    run = _run(cldn, modality="T_CELL_ENGAGER")
    assert run.modality == "T_CELL_ENGAGER"
    gate = Phase1ReleaseGate(
        expected_asset_count=1,
        hard_gate_reviews=[_review("asset:1")],
        field_provenance=_field_provenance(_review("asset:1")),
        custody=_custody(),
        reference_universes=[_universe("dll3", "DLL3"), cldn],
        unseeded_runs=[_run(_universe("dll3", "DLL3")), run],
    )
    assert any("does not match" in failure for failure in gate.failures)

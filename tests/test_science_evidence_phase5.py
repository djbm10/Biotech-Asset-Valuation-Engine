import pytest
from pydantic import ValidationError

from bve.intelligence.science_evidence import (
    ScienceEvidenceBundle,
    ScienceEvidenceDirection,
    ScienceEvidenceItem,
    ScienceEvidenceMappedComponent,
    ScienceEvidenceMappedField,
    ScienceEvidenceSourceType,
)
from bve.intelligence.science_thesis_builder import (
    ScienceThesisBuilder,
    ScienceThesisBuilderInput,
)


def item(
    evidence_id: str,
    component: ScienceEvidenceMappedComponent,
    field: ScienceEvidenceMappedField,
    *,
    direction: ScienceEvidenceDirection = ScienceEvidenceDirection.SUPPORTIVE,
    confidence: float = 0.8,
    quote: str = "The evidence supports the mapped claim in patients.",
) -> ScienceEvidenceItem:
    return ScienceEvidenceItem(
        evidence_id=evidence_id,
        asset_id="asset-1",
        source_type=ScienceEvidenceSourceType.CLINICAL_READOUT,
        source_id="doc-1",
        quote=quote,
        mapped_component=component,
        mapped_field=field,
        direction=direction,
        confidence=confidence,
        extraction_method="manual_test",
    )


def bundle(*items: ScienceEvidenceItem, unresolved_gaps: list[str] | None = None):
    return ScienceEvidenceBundle(
        asset_id="asset-1",
        asset_name="Asset 1",
        indication="ulcerative colitis",
        phase="phase2",
        modality="small_molecule",
        target="JAK1",
        mechanism="JAK1 inhibition",
        items=list(items),
        unresolved_gaps=unresolved_gaps or [],
    )


def test_science_evidence_item_requires_source_identity() -> None:
    with pytest.raises(ValidationError):
        ScienceEvidenceItem(
            evidence_id="ev-1",
            asset_id="asset-1",
            source_type=ScienceEvidenceSourceType.MANUAL,
            quote="target rationale",
            mapped_component=ScienceEvidenceMappedComponent.T,
            mapped_field=ScienceEvidenceMappedField.TARGET_PATHWAY,
            direction=ScienceEvidenceDirection.SUPPORTIVE,
            confidence=0.8,
        )


def test_science_evidence_item_requires_quote_or_span() -> None:
    with pytest.raises(ValidationError):
        ScienceEvidenceItem(
            evidence_id="ev-1",
            asset_id="asset-1",
            source_type=ScienceEvidenceSourceType.MANUAL,
            source_id="doc-1",
            mapped_component=ScienceEvidenceMappedComponent.T,
            mapped_field=ScienceEvidenceMappedField.TARGET_PATHWAY,
            direction=ScienceEvidenceDirection.SUPPORTIVE,
            confidence=0.8,
        )


def test_direct_target_evidence_maps_to_t() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "target-1",
                ScienceEvidenceMappedComponent.T,
                ScienceEvidenceMappedField.GENETIC_VALIDATION,
            )
        )
    )

    assert thesis.components["T"].score > 0.5
    assert "target/pathway causal evidence" not in thesis.missing_critical_evidence


def test_pkpd_evidence_maps_to_d_and_human_basis() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "pkpd-1",
                ScienceEvidenceMappedComponent.D,
                ScienceEvidenceMappedField.TARGET_ENGAGEMENT,
                quote="Phase 2 patients showed dose-dependent target engagement.",
            )
        )
    )

    assert thesis.components["D"].score > 0.5
    assert thesis.components["D"].resolution_basis.value == "human_pkpd"


def test_biomarker_bridge_maps_to_b() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "bio-1",
                ScienceEvidenceMappedComponent.B,
                ScienceEvidenceMappedField.BIOMARKER_CLINICAL_BRIDGE,
            )
        )
    )

    assert thesis.components["B"].score > 0.5
    assert "biomarker/translational validity" not in thesis.missing_critical_evidence


def test_trial_design_maps_to_warning_not_human_poc() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "design-1",
                ScienceEvidenceMappedComponent.Q,
                ScienceEvidenceMappedField.TRIAL_DESIGN,
                quote="The trial is randomized and double blind.",
            )
        )
    )

    assert thesis.components["H"].score < 0.5
    assert "human proof-of-concept" in thesis.missing_critical_evidence
    assert "design_score_not_human_poc" in thesis.modifier_result.warnings


def test_ambiguous_evidence_warns_without_credit() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "ambiguous-1",
                ScienceEvidenceMappedComponent.D,
                ScienceEvidenceMappedField.PKPD,
                direction=ScienceEvidenceDirection.AMBIGUOUS,
            )
        )
    )

    assert thesis.components["D"].score < 0.5
    assert "ambiguous_extracted_science_evidence" in thesis.modifier_result.warnings


def test_low_confidence_evidence_does_not_give_full_credit() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "low-1",
                ScienceEvidenceMappedComponent.H,
                ScienceEvidenceMappedField.HUMAN_POC,
                confidence=0.45,
            )
        )
    )

    assert thesis.components["H"].score < 0.5
    assert "low_confidence_extracted_science_evidence" in thesis.modifier_result.warnings


def test_unsupported_extracted_claim_warns_without_credit() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "unsupported-1",
                ScienceEvidenceMappedComponent.T,
                ScienceEvidenceMappedField.UNSUPPORTED,
            )
        )
    )

    assert thesis.components["T"].score < 0.5
    assert "unsupported_extracted_science_claim" in thesis.modifier_result.warnings


def test_bundle_unresolved_gaps_feed_builder_missing_evidence() -> None:
    thesis = ScienceThesisBuilder().from_evidence_bundle(
        bundle(
            item(
                "target-1",
                ScienceEvidenceMappedComponent.T,
                ScienceEvidenceMappedField.TARGET_PATHWAY,
            ),
            unresolved_gaps=["exposure-response evidence from active human dose"],
        )
    )

    assert "exposure-response evidence from active human dose" in thesis.missing_critical_evidence
    assert "exposure-response evidence from active human dose" in thesis.evidence_gaps


def test_from_existing_evidence_accepts_science_evidence_bundle() -> None:
    thesis = ScienceThesisBuilder().from_existing_evidence(
        science_evidence_bundle=bundle(
            item(
                "human-1",
                ScienceEvidenceMappedComponent.H,
                ScienceEvidenceMappedField.HUMAN_POC,
            )
        ),
        explicit_inputs=ScienceThesisBuilderInput(asset_id="asset-1"),
    )

    assert thesis.asset_id == "asset-1"
    assert thesis.components["H"].score > 0.5

from dataclasses import dataclass

from pydantic import BaseModel

from bve.intelligence.science_evidence import (
    ScienceEvidenceMappedComponent,
    ScienceEvidenceMappedField,
)
from bve.intelligence.science_evidence_extractor import ScienceEvidenceExtractor
from bve.intelligence.science_thesis_builder import ScienceThesisBuilder


@dataclass
class DataClassSignal:
    id: str
    asset_id: str
    source_id: str
    quote: str
    label: str
    confidence: float = 0.8


class PydanticSignal(BaseModel):
    id: str
    asset_id: str
    source_id: str
    quote: str
    label: str
    confidence: float = 0.8


def extract_one(signal: object, *, collection: str = "structured_signals"):
    kwargs = {collection: [signal]}
    bundle = ScienceEvidenceExtractor().extract_bundle(asset_id="asset-1", **kwargs)
    assert len(bundle.items) == 1, bundle.bundle_warnings
    return bundle.items[0], bundle


def signal(label: str, *, quote: str | None = None, **extra):
    return {
        "id": extra.pop("id", "sig-1"),
        "asset_id": "asset-1",
        "source_id": extra.pop("source_id", "doc-1"),
        "source_type": extra.pop("source_type", "press_release"),
        "quote": quote if quote is not None else label,
        "label": label,
        "confidence": extra.pop("confidence", 0.85),
        **extra,
    }


def test_target_signal_maps_to_T() -> None:
    item, _ = extract_one(signal("target pathway mechanism rationale"))
    assert item.mapped_component == ScienceEvidenceMappedComponent.T
    assert item.mapped_field == ScienceEvidenceMappedField.TARGET_PATHWAY


def test_pkpd_signal_maps_to_D() -> None:
    item, _ = extract_one(signal("PK/PD exposure and target engagement observed"))
    assert item.mapped_component == ScienceEvidenceMappedComponent.D


def test_biomarker_signal_maps_to_B() -> None:
    item, _ = extract_one(signal("biomarker translational bridge to clinical benefit"))
    assert item.mapped_component == ScienceEvidenceMappedComponent.B


def test_endpoint_met_maps_to_H() -> None:
    item, _ = extract_one(signal("primary endpoint met with clinical benefit"))
    assert item.mapped_component == ScienceEvidenceMappedComponent.H
    assert item.mapped_field == ScienceEvidenceMappedField.HUMAN_POC


def test_endpoint_validity_maps_to_M() -> None:
    item, _ = extract_one(signal("endpoint validity and clinically meaningful effect size"))
    assert item.mapped_component == ScienceEvidenceMappedComponent.M


def test_trial_design_maps_to_Q_not_H() -> None:
    item, _ = extract_one(
        signal(
            "randomized double blind controlled trial design",
            randomization="randomized",
            blinding="double_blind",
        )
    )
    assert item.mapped_component == ScienceEvidenceMappedComponent.Q
    assert item.mapped_field == ScienceEvidenceMappedField.TRIAL_DESIGN


def test_safety_signal_maps_to_S() -> None:
    item, _ = extract_one(signal("SAE safety tolerability dose-limiting toxicity"))
    assert item.mapped_component == ScienceEvidenceMappedComponent.S


def test_ambiguous_signal_adds_warning_or_gap() -> None:
    bundle = ScienceEvidenceExtractor().extract_bundle(
        asset_id="asset-1",
        structured_signals=[signal("strategic corporate update unrelated to science")],
    )
    assert bundle.items == []
    assert "unsupported_structured_science_signal" in bundle.bundle_warnings
    assert bundle.unresolved_gaps


def test_missing_source_skips_item_and_warns() -> None:
    bundle = ScienceEvidenceExtractor().extract_bundle(
        asset_id="asset-1",
        structured_signals=[signal("target mechanism rationale", source_id="")],
    )
    assert bundle.items == []
    assert "science_evidence_missing_source" in bundle.bundle_warnings


def test_missing_quote_or_span_skips_item_and_warns() -> None:
    bundle = ScienceEvidenceExtractor().extract_bundle(
        asset_id="asset-1",
        structured_signals=[signal("target mechanism rationale", quote="", description="")],
    )
    assert bundle.items == []
    assert "science_evidence_missing_quote_or_span" in bundle.bundle_warnings


def test_dict_pydantic_and_dataclass_like_objects_supported() -> None:
    dict_signal = signal("target mechanism rationale")
    pydantic_signal = PydanticSignal(
        id="pyd-1",
        asset_id="asset-1",
        source_id="doc-2",
        quote="PK/PD exposure signal",
        label="PK/PD exposure signal",
    )
    dataclass_signal = DataClassSignal(
        id="dc-1",
        asset_id="asset-1",
        source_id="doc-3",
        quote="biomarker bridge signal",
        label="biomarker bridge signal",
    )

    bundle = ScienceEvidenceExtractor().extract_bundle(
        asset_id="asset-1",
        structured_signals=[dict_signal, pydantic_signal, dataclass_signal],
    )

    assert len(bundle.items) == 3
    assert {item.mapped_component for item in bundle.items} == {
        ScienceEvidenceMappedComponent.T,
        ScienceEvidenceMappedComponent.D,
        ScienceEvidenceMappedComponent.B,
    }


def test_bundle_feeds_science_thesis_builder() -> None:
    bundle = ScienceEvidenceExtractor().extract_bundle(
        asset_id="asset-1",
        asset_name="Asset 1",
        indication="ulcerative colitis",
        phase="phase2",
        modality="small_molecule",
        structured_signals=[
            signal("target mechanism rationale"),
            signal("PK/PD exposure and target engagement observed", id="sig-2"),
            signal("primary endpoint met with clinical benefit", id="sig-3"),
        ],
    )
    thesis = ScienceThesisBuilder().from_existing_evidence(science_evidence_bundle=bundle)

    assert thesis.asset_id == "asset-1"
    assert thesis.components["T"].score > 0.5
    assert thesis.components["D"].score > 0.5
    assert thesis.components["H"].score > 0.5


def test_extractor_does_not_change_scoring_without_builder() -> None:
    bundle = ScienceEvidenceExtractor().extract_bundle(
        asset_id="asset-1",
        structured_signals=[signal("primary endpoint met with clinical benefit")],
    )

    assert bundle.items[0].mapped_component == ScienceEvidenceMappedComponent.H
    assert not hasattr(bundle, "modifier_result")
    assert not hasattr(bundle, "science_score")

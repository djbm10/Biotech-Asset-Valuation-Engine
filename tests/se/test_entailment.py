from datetime import date

from bve.se.evidence.entailment import check_structured_entailment
from bve.se.schemas.contracts import ExtractedClaim


def _claim(passage: str, *, value="CD19", endpoint: str | None = None) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id="claim:1",
        subject_id="asset:1",
        predicate="construct_target_set",
        normalized_value=value,
        endpoint=endpoint,
        source_document_id="doc:1",
        supporting_passage=passage,
        extraction_method="fixture",
        extractor_version="1",
        extraction_confidence=0.9,
        applicable_as_of_date=date(2026, 7, 10),
    )


def test_entailment_requires_normalized_value() -> None:
    assert check_structured_entailment(_claim("CD19-directed construct")).entailed is True
    result = check_structured_entailment(_claim("A B-cell directed construct"))
    assert result.entailed is False
    assert result.missing_qualifiers == ["cd19"]


def test_entailment_requires_material_qualifiers() -> None:
    claim = _claim("CD19 result", endpoint="overall response rate")
    result = check_structured_entailment(claim)
    assert result.entailed is False
    assert "overall response rate" in result.missing_qualifiers

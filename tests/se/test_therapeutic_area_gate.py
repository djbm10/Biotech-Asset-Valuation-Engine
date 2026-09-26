"""Therapeutic-area gate: canonical comparison and multi-valued evidence.

Declared in ``docs/se_policies/ta_gate_semantics.md`` before the change. Two defects are
pinned here: an ``ONCOLOGY`` request excluded every asset whose evidence said ``oncology``,
and no evidence could ever say anything but ``oncology``, so an ``AUTOIMMUNE`` request could
never pass.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.evidence.entailment import check_structured_entailment
from bve.se.evidence.generic import PublicDocumentEvidenceExtractor
from bve.se.gates.engine import GateEngine
from bve.se.ontology.therapeutic_areas import (
    AUTOIMMUNE,
    ONCOLOGY,
    canonical_therapeutic_area,
    classify_therapeutic_areas,
)
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    CandidateHit,
    GateStatus,
    NormalizedFact,
    SourceDocument,
    SourceTier,
)


class TestCanonicalArea:
    @pytest.mark.parametrize("raw", ["oncology", "Oncology", " ONCOLOGY ", "cancer"])
    def test_oncology_spellings_are_one_area(self, raw: str) -> None:
        assert canonical_therapeutic_area(raw) == ONCOLOGY

    @pytest.mark.parametrize("raw", ["autoimmune", "Autoimmunity", "autoimmune disease", "AUTOIMMUNE-DISEASE"])
    def test_autoimmune_spellings_are_one_area(self, raw: str) -> None:
        assert canonical_therapeutic_area(raw) == AUTOIMMUNE

    def test_immunology_is_not_an_alias_of_autoimmune(self) -> None:
        # Immunology is the broader field; equating them would be an unearned inference.
        assert canonical_therapeutic_area("immunology") == "IMMUNOLOGY"


class TestClassification:
    def test_one_document_can_support_two_areas(self) -> None:
        text = "Relapsed B-cell lymphoma; Autoimmune hemolytic anemia"
        assert classify_therapeutic_areas(text) == [AUTOIMMUNE, ONCOLOGY]

    @pytest.mark.parametrize(
        "text",
        ["Systemic Lupus Erythematosus", "Neuromyelitis Optica Spectrum Disorder", "Myasthenia Gravis"],
    )
    def test_autoimmune_conditions_are_classified(self, text: str) -> None:
        assert classify_therapeutic_areas(text) == [AUTOIMMUNE]

    @pytest.mark.parametrize("text", ["Amyotrophic Lateral Sclerosis", "Tuberous Sclerosis", "Healthy Volunteers"])
    def test_unclassified_text_supports_no_area(self, text: str) -> None:
        assert classify_therapeutic_areas(text) == []


def _problem(areas: list[str]) -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "problem_id": "p",
            "version": "1",
            "buyer": {"buyer_id": "b", "name": "Buyer", "as_of_date": "2026-09-26"},
            "strategic_gap": {
                "therapeutic_areas": areas,
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "CD19", "label": "CD19"}],
                },
                "acceptable_deal_routes": ["LICENSE"],
            },
        }
    )


def _ta(fact_id: str, value, *, contradicted: bool = False) -> NormalizedFact:
    return NormalizedFact(
        fact_id=fact_id,
        subject_id="asset:1",
        fact_type="therapeutic_area",
        value=value,
        supporting_claim_ids=[f"claim:{fact_id}"],
        contradicting_claim_ids=[f"claim:x{fact_id}"] if contradicted else [],
        confidence=0.9,
    )


def _ta_decisions(areas: list[str], facts: list[NormalizedFact]):
    evaluation = GateEngine().evaluate(_problem(areas), subject_id="asset:1", facts=facts)
    return [d for d in evaluation.decisions if d.requirement_id == "strategy.therapeutic_area"]


class TestGate:
    def test_case_differs_but_area_matches(self) -> None:
        # The live defect: requirement "ONCOLOGY", fact "oncology", status FAIL.
        [decision] = _ta_decisions(["ONCOLOGY"], [_ta("a", "oncology")])
        assert decision.status == GateStatus.PASS

    def test_any_supported_area_satisfies_the_request(self) -> None:
        facts = [_ta("a", [ONCOLOGY]), _ta("b", [AUTOIMMUNE])]
        [decision] = _ta_decisions(["AUTOIMMUNE"], facts)
        assert decision.status == GateStatus.PASS

    def test_a_multi_valued_fact_satisfies_either_area(self) -> None:
        [decision] = _ta_decisions(["autoimmune"], [_ta("a", [AUTOIMMUNE, ONCOLOGY])])
        assert decision.status == GateStatus.PASS

    def test_disjoint_classified_area_fails(self) -> None:
        [decision] = _ta_decisions(["AUTOIMMUNE"], [_ta("a", [ONCOLOGY])])
        assert decision.status == GateStatus.FAIL

    def test_disjoint_but_unclassifiable_request_is_unknown(self) -> None:
        # The evidence layer cannot see NEUROLOGY; its absence is not a negative.
        [decision] = _ta_decisions(["NEUROLOGY"], [_ta("a", [AUTOIMMUNE])])
        assert decision.status == GateStatus.UNKNOWN

    def test_no_fact_is_unknown(self) -> None:
        [decision] = _ta_decisions(["ONCOLOGY"], [])
        assert decision.status == GateStatus.UNKNOWN

    def test_contradicted_fact_is_unknown(self) -> None:
        [decision] = _ta_decisions(["ONCOLOGY"], [_ta("a", [ONCOLOGY], contradicted=True)])
        assert decision.status == GateStatus.UNKNOWN

    def test_unspecified_area_is_not_a_requirement(self) -> None:
        assert _ta_decisions(["UNSPECIFIED"], [_ta("a", [ONCOLOGY])]) == []


def _document(tmp_path, payload: dict | str, *, name: str) -> SourceDocument:
    path = tmp_path / name
    path.write_text(json.dumps(payload) if isinstance(payload, dict) else payload)
    return SourceDocument(
        document_id=f"doc:{name}",
        source_url=f"https://example.org/{name}",
        publisher="Example",
        document_type="trial_registry_record",
        retrieval_date=datetime(2026, 9, 26, tzinfo=timezone.utc),
        content_hash="a" * 64,
        snapshot_path=str(path),
        source_tier=SourceTier.PRIMARY,
    )


def _hit(source: str, *, snippet: str = "") -> CandidateHit:
    return CandidateHit(
        hit_id="hit:1",
        source=source,
        source_document_id="doc:1",
        query="CD19",
        asset_name="Asset A",
        target_terms=["CD19"],
        modality_terms=[],
        provisional_identity_key="k:asset-a",
        retrieved_at=datetime(2026, 9, 26, tzinfo=timezone.utc),
        applicable_as_of_date=date(2026, 9, 26),
        snippet=snippet,
    )


def _ta_output(bundle):
    [fact] = [f for f in bundle.facts if f.fact_type == "therapeutic_area"]
    claims = [c for c in bundle.claims if c.predicate == "therapeutic_area"]
    return fact, claims


class TestExtraction:
    def test_registry_record_emits_every_supported_area(self, tmp_path) -> None:
        protocol = {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Asset A"},
            "conditionsModule": {"conditions": ["Lupus Nephritis", "B-cell Lymphoma"]},
        }
        document = _document(tmp_path, protocol, name="NCT00000001.json")
        bundle = ClinicalTrialsEvidenceExtractor().extract(_hit("clinicaltrials_gov"), document)
        fact, claims = _ta_output(bundle)
        assert fact.value == [AUTOIMMUNE, ONCOLOGY]
        assert sorted(c.normalized_value for c in claims) == [AUTOIMMUNE, ONCOLOGY]
        assert set(fact.supporting_claim_ids) == {c.claim_id for c in claims}
        assert all(check_structured_entailment(c).entailed for c in claims)

    def test_public_document_is_not_hard_coded_to_oncology(self, tmp_path) -> None:
        text = "Asset A, a CD19 CAR T, induced remission in refractory systemic lupus erythematosus."
        document = _document(tmp_path, text, name="abstract.txt")
        bundle = PublicDocumentEvidenceExtractor().extract(_hit("pubmed", snippet=text), document)
        fact, claims = _ta_output(bundle)
        assert fact.value == [AUTOIMMUNE]
        assert all(check_structured_entailment(c).entailed for c in claims)

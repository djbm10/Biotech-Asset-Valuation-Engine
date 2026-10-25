"""gi_area_evidence_v1: a GASTROINTESTINAL area, PubMed area facts, and the status line.

Declared in ``docs/se_policies/gi_area_evidence_v1.md`` before implementation. The records
are synthetic, shaped like the PubMed abstracts that filled the GUCY2C development view
with laxatives. Each test pins a general rule, not a product name.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from bve.se.evidence.entailment import check_structured_entailment
from bve.se.evidence.pubmed import PubMedEvidenceExtractor
from bve.se.ontology.therapeutic_areas import (
    AUTOIMMUNE,
    CLASSIFIED_AREAS,
    GASTROINTESTINAL,
    ONCOLOGY,
    canonical_therapeutic_area,
    classify_therapeutic_areas,
)
from bve.se.schemas.contracts import CandidateHit, GateStatus, SourceDocument, SourceTier
from tests.se.test_therapeutic_area_gate import _ta, _ta_decisions


class TestLexicon:
    def test_gi_is_a_classified_area(self) -> None:
        assert GASTROINTESTINAL in CLASSIFIED_AREAS

    @pytest.mark.parametrize("raw", ["GI", "gastroenterology", "Gastrointestinal"])
    def test_gi_spellings_are_one_area(self, raw: str) -> None:
        assert canonical_therapeutic_area(raw) == GASTROINTESTINAL

    @pytest.mark.parametrize(
        "text",
        ["Chronic idiopathic constipation", "Irritable bowel syndrome with constipation",
         "Diabetic gastroparesis", "Functional dyspepsia"],
    )
    def test_non_malignant_gi_disease_is_gi(self, text: str) -> None:
        assert classify_therapeutic_areas(text) == [GASTROINTESTINAL]

    def test_gi_cancer_stays_oncology(self) -> None:
        assert classify_therapeutic_areas("Metastatic colorectal cancer") == [ONCOLOGY]

    def test_inflammatory_bowel_disease_stays_autoimmune(self) -> None:
        assert classify_therapeutic_areas("Ulcerative colitis") == [AUTOIMMUNE]

    @pytest.mark.parametrize(
        "text",
        ["DSS-induced colitis in mice", "Grade 2 diarrhea and nausea were reported",
         "Bowel preparation before colonoscopy"],
    )
    def test_model_terms_adverse_events_and_procedures_are_not_gi(self, text: str) -> None:
        assert GASTROINTESTINAL not in classify_therapeutic_areas(text)


class TestGate:
    def test_gi_only_evidence_fails_an_oncology_request(self) -> None:
        [decision] = _ta_decisions(["ONCOLOGY"], [_ta("a", GASTROINTESTINAL)])
        assert decision.status == GateStatus.FAIL

    def test_gi_and_oncology_evidence_passes_an_oncology_request(self) -> None:
        # A molecule with a legitimate oncology programme is never removed by its GI use.
        facts = [_ta("a", GASTROINTESTINAL), _ta("b", ONCOLOGY)]
        [decision] = _ta_decisions(["ONCOLOGY"], facts)
        assert decision.status == GateStatus.PASS


def _pubmed(tmp_path, title: str, abstract: str):
    path = tmp_path / "pubmed.json"
    path.write_text(json.dumps({"pmid": "1", "title": title, "abstract": abstract}))
    document = SourceDocument(
        document_id="doc:1", source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        publisher="PubMed", document_type="publication_abstract",
        retrieval_date=datetime.now(UTC),
        content_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        snapshot_path=str(path), source_tier=SourceTier.PRIMARY,
    )
    hit = CandidateHit(
        hit_id="hit:1", source="pubmed", source_document_id="doc:1", query="GUCY2C",
        asset_name="lactulose", provisional_identity_key="pubmed:1",
        retrieved_at=datetime.now(UTC), applicable_as_of_date=date(2026, 10, 25),
    )
    return PubMedEvidenceExtractor().extract(hit, document), document


class TestPubMedAreaFacts:
    def test_one_entailed_area_fact_per_supported_area(self, tmp_path) -> None:
        bundle, _ = _pubmed(
            tmp_path, "Cost-utility of treatments for chronic constipation",
            "Lactulose and magnesium oxide were compared. " + "Filler text. " * 80
            + "GUCY2C is also studied in colorectal cancer.",
        )
        # evidence_attribution_v1: an abstract's areas are document context now.
        areas = {f.value: f for f in bundle.facts if f.fact_type == "document_therapeutic_area"}
        assert set(areas) == {GASTROINTESTINAL, ONCOLOGY}
        claims = {c.claim_id: c for c in bundle.claims}
        for fact in areas.values():
            [claim_id] = fact.supporting_claim_ids
            assert check_structured_entailment(claims[claim_id]).entailed

    def test_abstract_without_an_area_term_emits_no_area_fact(self, tmp_path) -> None:
        bundle, _ = _pubmed(tmp_path, "Pharmacokinetics in rats", "Plasma levels were measured.")
        assert [f.fact_type for f in bundle.facts] == ["publication_relevance"]

    def test_no_clinical_claim_is_made(self, tmp_path) -> None:
        bundle, _ = _pubmed(tmp_path, "Constipation responders", "Response rate was 40%.")
        assert {f.fact_type for f in bundle.facts} <= {
            "publication_relevance", "therapeutic_area", "document_therapeutic_area"}


class TestStatusLine:
    def _asset_and_index(self, statuses):
        from types import SimpleNamespace

        from bve.se.reporting.shortlist import Citation

        claims = tuple(
            SimpleNamespace(predicate="development_status", normalized_value=s,
                            source_document_id=f"doc:{i}", supporting_passage=s,
                            locator=f"NCT0000000{i}")
            for i, s in enumerate(statuses)
        )
        index = SimpleNamespace(
            claims_by_subject={"asset:1": claims},
            documents={f"doc:{i}": object() for i in range(len(statuses))},
            document_citation=lambda *a, **k: Citation.model_construct(),
        )
        return SimpleNamespace(asset_id="asset:1"), index

    def test_every_cited_trial_status_is_shown(self) -> None:
        from bve.se.reporting.shortlist import _status_fact

        asset, index = self._asset_and_index(["TERMINATED", "COMPLETED", "TERMINATED"])
        [fact] = _status_fact(asset, index)
        assert fact.label == "Trial registry status"
        assert fact.value == "COMPLETED, TERMINATED"
        assert len(fact.citations) == 3

    def test_no_status_claim_shows_no_status_line(self) -> None:
        from bve.se.reporting.shortlist import _status_fact

        asset, index = self._asset_and_index([])
        assert _status_fact(asset, index) == ()

"""evidence_attribution_v1: document context is not a fact about every drug it names.

Declared in ``docs/se_policies/evidence_attribution_v1.md`` before the implementation. Every
record is synthetic. The cases cover several therapeutic areas and pin grammatical rules,
never a product name.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

import pytest

from bve.se.evidence.attribution import attributed_areas, attributed_modality
from bve.se.evidence.pubmed import PubMedEvidenceExtractor
from bve.se.ontology.therapeutic_areas import AUTOIMMUNE, GASTROINTESTINAL, ONCOLOGY
from bve.se.schemas.contracts import CandidateHit, GateStatus, SourceDocument, SourceTier
from tests.se.test_therapeutic_area_gate import _ta, _ta_decisions


def _areas(text: str, asset: str) -> set[str]:
    return {area for area, _ in attributed_areas(text, asset)}


class TestAreaAttribution:
    def test_reagent_in_an_oncology_paper_gets_no_area(self) -> None:
        text = ("Plasma and tumor samples contained the payload aniline as a catabolite. "
                "The conjugate was active in colorectal cancer xenografts.")
        assert _areas(text, "aniline") == set()

    def test_only_the_drug_evaluated_for_cancer_gets_oncology(self) -> None:
        text = ("Drugzumab improved stool frequency in volunteers. "
                "Tumorinib was evaluated in patients with metastatic colorectal cancer.")
        assert _areas(text, "Tumorinib") == {ONCOLOGY}
        assert _areas(text, "Drugzumab") == set()

    def test_coordinated_drugs_stay_unknown(self) -> None:
        text = "First-line options are lactulide or senoxin for chronic constipation."
        assert _areas(text, "lactulide") == set()
        assert _areas(text, "senoxin") == set()

    def test_combination_partner_stays_unknown(self) -> None:
        text = "Clozatide combined with macrogolum for bowel cleansing in patients with constipation."
        assert _areas(text, "macrogolum") == set()

    def test_a_drug_with_evidence_in_two_areas_gets_both(self) -> None:
        text = ("Dualimab is approved for the treatment of rheumatoid arthritis. "
                "Dualimab was then studied in patients with diffuse large B-cell lymphoma.")
        assert _areas(text, "Dualimab") == {AUTOIMMUNE, ONCOLOGY}

    @pytest.mark.parametrize(
        "text",
        ["In colorectal cancer, many agents including Ambiguol were discussed.",  # term first
         "Ambiguol was measured; tumor size was also recorded.",  # no indication cue
         "Ambiguol concentrations were measured by HPLC."],  # no area at all
    )
    def test_ambiguous_attribution_stays_unknown(self, text: str) -> None:
        assert _areas(text, "Ambiguol") == set()

    def test_title_form_attributes(self) -> None:
        text = "Evaluation of TAKX-264, an Antibody-Drug Conjugate in Pancreatic Cancer Cell Lines."
        assert _areas(text, "TAKX-264") == {ONCOLOGY}

    def test_gi_attribution_uses_the_same_rule(self) -> None:
        text = "Lactulide is effective for chronic idiopathic constipation in adults."
        assert _areas(text, "lactulide") == {GASTROINTESTINAL}

    def test_name_is_matched_as_a_whole_word(self) -> None:
        # "ether" inside "monomethyl ether" is a word; inside "together" it is not.
        text = "Drugs together for cancer treatment were reviewed."
        assert _areas(text, "ether") == set()


class TestModalityAttribution:
    def test_apposition_gives_the_modality(self) -> None:
        text = "TAKX-264, an investigational antibody-drug conjugate, was studied."
        assert attributed_modality(text, "TAKX-264") == "ANTIBODY_DRUG_CONJUGATE"

    def test_head_noun_gives_the_modality(self) -> None:
        text = "The antibody-drug conjugate TAKX-164 showed activity."
        assert attributed_modality(text, "TAKX-164") == "ANTIBODY_DRUG_CONJUGATE"

    def test_document_modality_is_not_the_reagents_modality(self) -> None:
        text = ("A bispecific T-cell engager was tested. Colitis was induced by dextran "
                "sulfate sodium in drinking water.")
        assert attributed_modality(text, "dextran") is None


def _pubmed(tmp_path, title: str, abstract: str, asset: str):
    path = tmp_path / f"{asset}.json"
    path.write_text(json.dumps({"pmid": "1", "title": title, "abstract": abstract}))
    document = SourceDocument(
        document_id="doc:1", source_url="https://pubmed.ncbi.nlm.nih.gov/1/",
        publisher="PubMed", document_type="publication_abstract",
        retrieval_date=datetime.now(UTC),
        content_hash=hashlib.sha256(path.read_bytes()).hexdigest(),
        snapshot_path=str(path), source_tier=SourceTier.PRIMARY,
    )
    hit = CandidateHit(
        hit_id=f"hit:{asset}", source="pubmed", source_document_id="doc:1", query="Q",
        asset_name=asset, provisional_identity_key=f"pubmed:{asset}",
        retrieved_at=datetime.now(UTC), applicable_as_of_date=date(2026, 10, 25),
    )
    return PubMedEvidenceExtractor().extract(hit, document)


class TestPubMedFacts:
    def test_document_area_is_context_not_an_asset_fact(self, tmp_path) -> None:
        bundle = _pubmed(tmp_path, "Catabolism of an ADC in tumor-bearing rats",
                         "Plasma and tumor samples contained aniline.", "aniline")
        types = {f.fact_type: f.value for f in bundle.facts}
        assert "therapeutic_area" not in types
        assert types["document_therapeutic_area"] == ONCOLOGY

    def test_attributed_area_cites_its_sentence(self, tmp_path) -> None:
        bundle = _pubmed(tmp_path, "Tumorinib in patients with gastric cancer",
                         "Response was assessed.", "Tumorinib")
        [fact] = [f for f in bundle.facts if f.fact_type == "therapeutic_area"]
        assert fact.value == ONCOLOGY
        claim = next(c for c in bundle.claims if c.claim_id in fact.supporting_claim_ids)
        assert "Tumorinib" in claim.supporting_passage


class TestGateReadsOnlyAssetFacts:
    def test_context_alone_is_unknown_not_fail(self) -> None:
        context = _ta("a", GASTROINTESTINAL).model_copy(update={"fact_type": "document_therapeutic_area"})
        [decision] = _ta_decisions(["ONCOLOGY"], [context])
        assert decision.status == GateStatus.UNKNOWN


class TestEligibilityDisplay:
    def test_historical_programme_keeps_eligible_with_scope_note(self) -> None:
        """A terminated programme meeting the declared criteria stays ELIGIBLE, labelled."""

        from bve.se.reporting.shortlist import ELIGIBLE_SCOPE_NOTE

        assert "not evidence of current development" in ELIGIBLE_SCOPE_NOTE
        assert "licensing" in ELIGIBLE_SCOPE_NOTE

    def test_phase_shows_the_highest_cited_stage(self) -> None:
        from types import SimpleNamespace

        from bve.se.reporting.shortlist import _phase_fact

        claims = tuple(
            SimpleNamespace(predicate="development_stage_order", normalized_value=order,
                            source_document_id=f"doc:{i}", supporting_passage="[]",
                            locator="designModule.phases")
            for i, order in enumerate([3, 2, 4])
        )
        from bve.se.reporting.shortlist import Citation

        index = SimpleNamespace(
            claims_by_subject={"asset:1": claims},
            documents={f"doc:{i}": object() for i in range(3)},
            document_citation=lambda *a, **k: Citation.model_construct(),
            phase_decision=lambda _id: None,
        )
        asset = SimpleNamespace(asset_id="asset:1", development_stage="PHASE2",
                                development_status="TERMINATED")
        fact = _phase_fact(asset, index)
        assert fact.value == "PHASE_3"
        assert fact.note == "highest of 3 cited trial records"


class TestStructuredTrialRelation:
    @pytest.mark.parametrize(
        ("title", "conditions", "expected"),
        [("Ad5 vaccine in colorectal cancer", ["Colorectal Cancer"], [ONCOLOGY]),
         ("CAR-T cells in lupus", ["Systemic Lupus Erythematosus"], [AUTOIMMUNE]),
         ("Drug X in IBS-C", ["Irritable Bowel Syndrome With Constipation"], [GASTROINTESTINAL])],
    )
    def test_registry_intervention_condition_is_an_asset_fact(
        self, tmp_path, title, conditions, expected
    ) -> None:
        # A trial record is a structured intervention -> condition relation, so its areas
        # stay gate-decisive for the intervention, vaccines and cell therapies included.
        from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
        from tests.se.test_therapeutic_area_gate import _document, _hit

        protocol = {"identificationModule": {"nctId": "NCT00000001", "briefTitle": title},
                    "conditionsModule": {"conditions": conditions}}
        document = _document(tmp_path, protocol, name="NCT00000001.json")
        bundle = ClinicalTrialsEvidenceExtractor().extract(_hit("clinicaltrials_gov"), document)
        assert sorted(f.value for f in bundle.facts if f.fact_type == "therapeutic_area") == expected


class TestModalityAmendment1:
    def test_long_appositive_is_read_to_the_end_of_its_clause(self) -> None:
        text = "Catabolism of TAKX-164, a Guanylyl Cyclase C Targeted Antibody-Drug Conjugate."
        assert attributed_modality(text, "TAKX-164") == "ANTIBODY_DRUG_CONJUGATE"

    @pytest.mark.parametrize(
        ("text", "word"),
        [("Resolving polymorphism in disulfide-rich peptide drugs.", "drugs"),
         ("Disulfide-rich peptide therapeutics often exhibit rigidity.", "often")],
    )
    def test_a_modifier_is_not_a_head_noun(self, text: str, word: str) -> None:
        assert attributed_modality(text, word) is None

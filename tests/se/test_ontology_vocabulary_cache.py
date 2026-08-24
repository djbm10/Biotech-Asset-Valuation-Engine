"""The whole-ontology vocabulary is per-run state, not per-record state.

`ClinicalTrialsEvidenceExtractor.extract` built the entire ontology vocabulary -- every
target, every alias, case-folded -- once per hit. On a 3,420-hit run that was ~6 hours in
the extraction stage alone, for a value that cannot change while the run holds a pinned
snapshot. These tests pin that it is built once and that installing a new snapshot still
invalidates it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.discovery.adapters import QueryVocabulary
from bve.se.ontology import targets as targets_module
from bve.se.schemas.contracts import CandidateHit, SourceDocument, SourceTier


class TestTheOntologyVocabularyIsBuiltOncePerSnapshot:
    def test_repeated_calls_return_the_same_object(self):
        first = QueryVocabulary.for_ontology()
        assert QueryVocabulary.for_ontology() is first

    def test_the_target_walk_happens_once_not_once_per_caller(self):
        """`known_targets` walks every target entity in the snapshot; that is per-run work."""

        targets_module.reset_resolver_cache()
        first = targets_module.known_targets()
        info = targets_module.known_targets.cache_info()
        for _ in range(20):
            targets_module.known_targets()
        after = targets_module.known_targets.cache_info()
        assert after.misses == info.misses, "re-walked the snapshot on a repeat call"
        assert targets_module.known_targets() is first

    def test_installing_a_new_snapshot_invalidates_the_vocabulary(self):
        """A cache that outlives its snapshot would silently label against the wrong ontology."""

        first = QueryVocabulary.for_ontology()
        targets_module.reset_resolver_cache()
        assert QueryVocabulary.for_ontology() is not first


class TestExtractionDoesNotRebuildTheVocabularyPerHit:
    def test_two_extractions_share_one_vocabulary_build(self, tmp_path, monkeypatch):
        import json

        from bve.se.evidence import clinicaltrials as ct

        protocol = {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "A study of drug-x"},
            "armsInterventionsModule": {"interventions": [{"name": "drug-x", "type": "DRUG"}]},
            "statusModule": {"overallStatus": "RECRUITING"},
        }
        snapshot = tmp_path / "p.json"
        snapshot.write_text(json.dumps(protocol))

        document = SourceDocument(
            document_id="doc:1",
            source_url="https://clinicaltrials.gov/study/NCT00000001",
            publisher="ClinicalTrials.gov",
            document_type="trial_registry_record",
            publication_date=None,
            retrieval_date=datetime.now(timezone.utc),
            content_hash="abc",
            snapshot_path=str(snapshot),
            source_tier=SourceTier.REGISTRY,
        )
        hit = CandidateHit(
            hit_id="hit:1",
            source="clinicaltrials_gov",
            source_document_id="doc:1",
            query="q",
            asset_name="drug-x",
            provisional_identity_key="k",
            retrieved_at=datetime.now(timezone.utc),
            applicable_as_of_date=date(2026, 8, 24),
        )

        builds = {"n": 0}
        real = QueryVocabulary.for_ontology

        def counting():
            builds["n"] += 1
            return real()

        monkeypatch.setattr(ct.QueryVocabulary, "for_ontology", staticmethod(counting))
        extractor = ct.ClinicalTrialsEvidenceExtractor()
        extractor.extract(hit, document)
        extractor.extract(hit, document)

        # Two calls are fine; two *builds* are not. The cache makes the second free.
        assert builds["n"] == 2
        assert real() is real(), "for_ontology must be memoized"

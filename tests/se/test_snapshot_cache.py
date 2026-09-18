"""Reading a sealed snapshot once must extract exactly what reading it N times extracted.

Discovery is 92% of a run and is live HTTP against distinct queries, so it is not available
to be optimized without weakening what convergence means. Extraction is, and the repeat
work there is arithmetic on bytes that cannot change mid-run: the same protocol was parsed
and canonically re-serialized once per hit, and one M17-scale run had ~3.6 hits per record.
These tests pin the only property that makes the cache acceptable -- identical output --
plus the staleness case that a path-keyed cache would get wrong.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from bve.se.evidence import snapshot_cache
from bve.se.evidence.clinicaltrials import ClinicalTrialsEvidenceExtractor
from bve.se.schemas.contracts import CandidateHit, SourceDocument, SourceTier


@pytest.fixture(autouse=True)
def _clean_cache():
    snapshot_cache.clear()
    yield
    snapshot_cache.clear()


_PROTOCOL = {
    "identificationModule": {"nctId": "NCT00000001", "briefTitle": "A study"},
    "designModule": {"phases": ["PHASE2"]},
    "conditionsModule": {"conditions": ["Multiple Myeloma"]},
    "statusModule": {"overallStatus": "RECRUITING"},
    "armsInterventionsModule": {
        "interventions": [{"name": "Teclistamab", "type": "BIOLOGICAL"}]
    },
}


def _document(path) -> SourceDocument:
    return SourceDocument(
        document_id="doc:1",
        source_url="https://clinicaltrials.gov/study/NCT00000001",
        publisher="ClinicalTrials.gov",
        document_type="trial_registry_record",
        retrieval_date=datetime(2026, 8, 20, tzinfo=timezone.utc),
        content_hash="a" * 64,
        snapshot_path=str(path),
        source_tier=SourceTier.PRIMARY,
    )


def _hit(hit_id: str) -> CandidateHit:
    return CandidateHit(
        hit_id=hit_id,
        source="clinicaltrials_gov",
        source_document_id="doc:1",
        query="TNFRSF17",
        asset_name="Teclistamab",
        target_terms=["TNFRSF17"],
        modality_terms=["T_CELL_ENGAGER"],
        provisional_identity_key="ctgov:NCT00000001:teclistamab",
        retrieved_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        applicable_as_of_date=date(2026, 8, 20),
    )


class TestTheCacheChangesNothingItReads:
    def test_a_cached_extraction_equals_an_uncached_one(self, tmp_path) -> None:
        path = tmp_path / "NCT00000001.json"
        path.write_text(json.dumps(_PROTOCOL))
        extractor = ClinicalTrialsEvidenceExtractor()
        document = _document(path)

        snapshot_cache.clear()
        cold = extractor.extract(_hit("hit:1"), document)
        warm = extractor.extract(_hit("hit:1"), document)
        snapshot_cache.clear()
        uncached = extractor.extract(_hit("hit:1"), document)

        assert warm.model_dump(mode="json") == cold.model_dump(mode="json")
        assert uncached.model_dump(mode="json") == cold.model_dump(mode="json")

    def test_the_file_is_read_once_for_many_hits(self, tmp_path, monkeypatch) -> None:
        path = tmp_path / "NCT00000001.json"
        path.write_text(json.dumps(_PROTOCOL))
        extractor = ClinicalTrialsEvidenceExtractor()
        document = _document(path)
        reads = {"n": 0}
        original = type(path).read_text

        def counting_read_text(self, *args, **kwargs):
            if str(self) == str(path):
                reads["n"] += 1
            return original(self, *args, **kwargs)

        monkeypatch.setattr(type(path), "read_text", counting_read_text)
        for index in range(5):
            extractor.extract(_hit(f"hit:{index}"), document)

        assert reads["n"] == 1, f"the sealed snapshot was re-read {reads['n']} times"


class TestTheCacheIsNotStale:
    def test_replacing_the_file_replaces_the_answer(self, tmp_path) -> None:
        """Keyed on the bytes' identity, not the path: tests reuse paths, runs reuse trees."""

        path = tmp_path / "NCT00000001.json"
        path.write_text(json.dumps(_PROTOCOL))
        assert snapshot_cache.load_json(path)["designModule"]["phases"] == ["PHASE2"]

        replaced = dict(_PROTOCOL, designModule={"phases": ["PHASE3"]})
        path.write_text(json.dumps(replaced) + " ")

        assert snapshot_cache.load_json(path)["designModule"]["phases"] == ["PHASE3"]

    def test_canonical_json_matches_a_direct_serialization(self, tmp_path) -> None:
        path = tmp_path / "NCT00000001.json"
        path.write_text(json.dumps(_PROTOCOL, indent=2))

        assert snapshot_cache.canonical_json(path) == json.dumps(
            _PROTOCOL, sort_keys=True, separators=(",", ":")
        )

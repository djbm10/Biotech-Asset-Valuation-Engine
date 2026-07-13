from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.discovery.corpus import CorpusDiscoveryAdapter, adapters_from_corpus
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome, SourceTier


AS_OF = date(2026, 7, 12)


def _query(
    target: str = "CD19",
    modality: str = "T_CELL_ENGAGER",
    *,
    text: str | None = None,
    depth: int = 0,
) -> CompiledQuery:
    return CompiledQuery(
        query_id="query:test",
        query=text or f"{target} T-cell engager",
        target_ids=[target] if depth == 0 else [],
        modality_ids=[modality] if depth == 0 else [],
        expansion_depth=depth,
    )


def test_ctgov_corpus_adapter_reuses_snapshot_and_structured_identity(tmp_path: Path) -> None:
    protocol = {
        "identificationModule": {
            "nctId": "NCT00000001",
            "briefTitle": "CLN-978 CD19 T-cell engager",
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "CLN-978",
                    "description": "CD19-directed CD3 bispecific T-cell engager",
                    "otherNames": ["CLN978"],
                }
            ]
        },
    }
    store = CorpusStore(tmp_path / "corpus")
    corpus_document = store.add(
        source_family="clinicaltrials_gov",
        source_url="https://clinicaltrials.gov/study/NCT00000001",
        publisher="ClinicalTrials.gov",
        document_type="trial_registry_record",
        source_tier=SourceTier.REGISTRY,
        raw_payload=protocol,
        text="CLN-978 CD19-directed CD3 bispecific T-cell engager Example Bio",
        title="CLN-978 study",
        as_of_date=AS_OF,
        native_snapshot=True,
    )
    snapshot = Path(corpus_document.snapshot_path)
    before = snapshot.read_bytes()
    before_mtime = snapshot.stat().st_mtime_ns

    adapter = adapters_from_corpus(store, ["clinicaltrials_gov"])[0]
    result = adapter.search(_query(), as_of_date=AS_OF)

    assert adapter.source_name == "clinicaltrials_gov"
    assert adapter.mandatory is True
    assert len(result.hits) == 1
    hit = result.hits[0]
    assert hit.asset_name == "CLN-978"
    assert hit.company_name == "Example Bio"
    assert hit.trial_id == "NCT00000001"
    assert hit.aliases == ["CLN978"]
    source_document = result.source_documents[0]
    assert source_document.snapshot_path == corpus_document.snapshot_path
    assert source_document.content_hash == hashlib.sha256(before).hexdigest()
    assert snapshot.read_bytes() == before
    assert snapshot.stat().st_mtime_ns == before_mtime


def test_matching_identity_free_document_is_evidence_not_a_title_asset(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus")
    corpus_document = store.add(
        source_family="company_press_release",
        source_url="https://example.test/releases/platform-update",
        publisher="Example Bio",
        document_type="press_release",
        source_tier=SourceTier.COMPANY_AUTHORED,
        raw_payload={
            "text": "Our CD19-directed CD3 bispecific T-cell engager platform advanced."
        },
        text="Our CD19-directed CD3 bispecific T-cell engager platform advanced.",
        title="Platform update",
        as_of_date=AS_OF,
    )
    adapter = CorpusDiscoveryAdapter(
        "company_press_release",
        [corpus_document],
        mandatory=True,
    )

    result = adapter.search(_query(), as_of_date=AS_OF)

    assert result.outcome is SearchOutcome.SUCCESS
    assert result.source_documents
    assert result.hits == []
    serialized = " ".join(
        str(value)
        for hit in result.hits
        for value in (hit.asset_name, hit.provisional_identity_key)
    )
    assert "Platform update" not in serialized
    assert corpus_document.source_url not in serialized


def test_generic_observed_asset_is_extracted_once_and_follow_up_is_filtered(
    tmp_path: Path,
) -> None:
    store = CorpusStore(tmp_path / "corpus")
    corpus_document = store.add(
        source_family="pubmed",
        source_url="https://pubmed.ncbi.nlm.nih.gov/123/",
        publisher="PubMed",
        document_type="publication_abstract",
        source_tier=SourceTier.PRIMARY,
        raw_payload={
            "pmid": "123",
            "title": "CLN-978 in B-cell malignancies",
            "abstract": "CLN-978 is a CD19 x CD3 bispecific T-cell engager.",
        },
        text="CLN-978 is a CD19 x CD3 bispecific T-cell engager.",
        title="CLN-978 in B-cell malignancies",
        as_of_date=AS_OF,
        native_snapshot=True,
    )
    adapter = CorpusDiscoveryAdapter("pubmed", [corpus_document])

    initial = adapter.search(_query(), as_of_date=AS_OF)
    matching_follow_up = adapter.search(
        _query(text="CLN-978", depth=1),
        as_of_date=AS_OF,
    )
    unrelated_follow_up = adapter.search(
        _query(text="ABC-999", depth=1),
        as_of_date=AS_OF,
    )

    assert [hit.asset_name for hit in initial.hits] == ["CLN-978"]
    assert [hit.hit_id for hit in matching_follow_up.hits] == [initial.hits[0].hit_id]
    assert unrelated_follow_up.hits == []
    assert unrelated_follow_up.source_documents == []


def test_factory_has_unique_family_names_and_rejects_missing_required_family(
    tmp_path: Path,
) -> None:
    store = CorpusStore(tmp_path / "corpus")
    for family in ("pubmed", "sec_edgar"):
        store.add(
            source_family=family,
            source_url=f"https://example.test/{family}",
            publisher=family,
            document_type=family,
            source_tier=SourceTier.PRIMARY,
            raw_payload={"text": "CLN-978 CD19 CD3 T-cell engager"},
            text="CLN-978 CD19 CD3 T-cell engager",
            as_of_date=AS_OF,
        )

    adapters = adapters_from_corpus(store, ["sec_edgar"])

    assert [adapter.source_name for adapter in adapters] == ["pubmed", "sec_edgar"]
    assert len({adapter.source_name for adapter in adapters}) == len(adapters)
    assert {adapter.source_name: adapter.mandatory for adapter in adapters} == {
        "pubmed": False,
        "sec_edgar": True,
    }
    with pytest.raises(ValueError, match="conference_ash"):
        adapters_from_corpus(store, ["sec_edgar", "conference_ash"])


def test_factory_builds_empty_mandatory_adapter_only_for_proven_no_data(
    tmp_path: Path,
) -> None:
    store = CorpusStore(tmp_path / "corpus")

    adapters = adapters_from_corpus(
        store,
        ["clinicaltrials_gov"],
        proven_no_data_source_families=["clinicaltrials_gov"],
    )

    assert len(adapters) == 1
    adapter = adapters[0]
    assert adapter.source_name == "clinicaltrials_gov"
    assert adapter.mandatory is True
    result = adapter.search(_query(), as_of_date=AS_OF)
    assert result.outcome is SearchOutcome.NO_EVIDENCE_FOUND
    assert result.hits == []
    assert result.source_documents == []


def test_factory_rejects_invalid_no_data_proof(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path / "corpus")
    store.add(
        source_family="clinicaltrials_gov",
        source_url="https://clinicaltrials.gov/study/NCT00000001",
        publisher="ClinicalTrials.gov",
        document_type="trial_registry_record",
        source_tier=SourceTier.REGISTRY,
        raw_payload={},
        text="evidence",
        as_of_date=AS_OF,
        native_snapshot=True,
    )

    with pytest.raises(ValueError, match="must be required"):
        adapters_from_corpus(
            store,
            ["clinicaltrials_gov"],
            proven_no_data_source_families=["pubmed"],
        )
    with pytest.raises(ValueError, match="unexpectedly contain corpus documents"):
        adapters_from_corpus(
            store,
            ["clinicaltrials_gov"],
            proven_no_data_source_families=["clinicaltrials_gov"],
        )

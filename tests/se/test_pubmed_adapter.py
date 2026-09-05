from __future__ import annotations

from datetime import date

from bve.se.discovery.adapters import PubMedDiscoveryAdapter, UnavailableSourceAdapter
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome


def test_pubmed_adapter_normalizes_matching_abstract_and_snapshot(tmp_path) -> None:
    adapter = PubMedDiscoveryAdapter(
        lambda query, limit: [
            {
                "pmid": "12345",
                "title": "A phase 1 study of CLN-978 CD19 T-cell engager",
                "abstract": "A CD19 x CD3 bispecific T-cell engager was evaluated.",
                "publication_date": "2026",
            }
        ],
        snapshot_root=tmp_path / "snapshots",
    )
    result = adapter.search(
        CompiledQuery(
            query_id="q",
            query="CD19 T-cell engager",
            target_ids=["CD19"],
            modality_ids=["T_CELL_ENGAGER"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    assert result.outcome == SearchOutcome.SUCCESS
    assert result.hits[0].asset_name == "CLN-978"
    assert result.source_documents[0].source_url.endswith("/12345/")
    assert result.source_documents[0].snapshot_path


def test_pubmed_adapter_does_not_turn_nonmatching_abstract_into_candidate() -> None:
    adapter = PubMedDiscoveryAdapter(
        lambda query, limit: [
            {"pmid": "1", "title": "BCMA antibody", "abstract": "An ADC study."}
        ]
    )
    result = adapter.search(
        CompiledQuery(query_id="q", query="CD19", target_ids=["CD19"], modality_ids=["T_CELL_ENGAGER"]),
        as_of_date=date(2026, 7, 10),
    )
    assert result.hits == []


def test_unavailable_source_is_explicitly_not_configured() -> None:
    """Not FAILED: nothing was attempted, so nothing broke.

    The distinction is load-bearing. While these were the same outcome, seven unbuilt
    connectors made run B6 unscoreable even though its CT.gov acquisition was clean.
    """

    result = UnavailableSourceAdapter("conference_ash").search(
        CompiledQuery(query_id="q", query="CD19"), as_of_date=date(2026, 7, 10)
    )
    assert result.outcome == SearchOutcome.NOT_CONFIGURED
    assert result.error == "connector not configured"

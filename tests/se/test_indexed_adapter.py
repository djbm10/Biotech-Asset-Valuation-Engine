from datetime import date

from bve.se.discovery.adapters import IndexedDocumentAdapter
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome


def test_indexed_adapter_supports_declared_company_and_conference_corpus(tmp_path) -> None:
    adapter = IndexedDocumentAdapter(
        "conference_ash",
        [
            {
                "url": "https://example.test/abstract/1",
                "publisher": "ASH",
                "document_type": "conference_abstract",
                "title": "CLN-978 in B-cell disease",
                "text": "CLN-978 is a CD19 T-cell engager.",
                "candidates": [
                    {"asset_name": "CLN-978", "target_ids": ["CD19"], "modality_ids": ["T_CELL_ENGAGER"]}
                ],
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
    assert result.source_documents[0].publisher == "ASH"
    assert result.source_documents[0].snapshot_path

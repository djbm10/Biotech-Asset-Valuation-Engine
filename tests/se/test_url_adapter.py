from datetime import date

from bve.se.discovery.adapters import UrlDocumentAdapter
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome


def test_url_adapter_fetches_declared_public_page_and_preserves_failure() -> None:
    def fetch(url: str):
        if url.endswith("bad"):
            raise RuntimeError("timeout")
        return {
            "url": url,
            "publisher": "Example Bio",
            "document_type": "company_pipeline",
            "title": "CLN-978",
            "text": "CLN-978 is a CD19 T-cell engager.",
            "candidates": [
                {"asset_name": "CLN-978", "target_ids": ["CD19"], "modality_ids": ["T_CELL_ENGAGER"]}
            ],
        }

    adapter = UrlDocumentAdapter(
        "company_pipeline_or_presentation",
        ["https://example.test/good", "https://example.test/bad"],
        fetch_fn=fetch,
    )
    result = adapter.search(
        CompiledQuery(query_id="q", query="CD19 TCE", target_ids=["CD19"], modality_ids=["T_CELL_ENGAGER"]),
        as_of_date=date(2026, 7, 10),
    )
    assert result.outcome == SearchOutcome.PARTIAL
    assert result.hits[0].asset_name == "CLN-978"
    assert "timeout" in (result.error or "")

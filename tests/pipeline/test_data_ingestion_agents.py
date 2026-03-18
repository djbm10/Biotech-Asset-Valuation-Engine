from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bve.agents.data_ingestion import (
    ClinicalTrialsAgent,
    FDAAgent,
    NewsAgent,
    PubMedAgent,
    SECAgent,
)
from bve.agents.data_ingestion.base import BaseDataIngestionAgent
from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints
from bve.pipeline.pipeline_state import PipelineStateStore
from bve.pipeline.watchlist_runner import WatchlistAsset


class _FakeConnector:
    source_type = "fake_source"

    def __init__(self) -> None:
        self.calls: list[Optional[datetime]] = []

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> FetchResult:
        self.calls.append(since)
        return FetchResult(
            documents=[],
            fetch_errors=[],
            source=self.source_type,
            fetched_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        )


def test_base_ingestion_agent_uses_source_checkpoint(tmp_path: Path):
    state = PipelineStateStore(tmp_path / "state.json")
    connector = _FakeConnector()
    agent = BaseDataIngestionAgent(connector=connector, source_name="fake_source")
    asset = WatchlistAsset(company_id="co-1", asset_id="asset-1")

    agent.poll_source(asset=asset, state_store=state, limit=5)
    agent.poll_source(asset=asset, state_store=state, limit=5)

    assert connector.calls[0] is None
    assert connector.calls[1] is not None


def test_ingestion_agent_source_names():
    assert FDAAgent().source_name == "fda_website"
    assert ClinicalTrialsAgent().source_name == "clinicaltrials_gov"
    assert PubMedAgent().source_name == "pubmed"
    assert SECAgent().source_name == "sec_filing"
    assert NewsAgent().source_name == "press_release"

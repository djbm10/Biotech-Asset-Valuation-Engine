"""Shared runtime behavior for polling ingestion agents."""
from __future__ import annotations

import inspect
from typing import Any, Optional, Protocol

from bve.connectors.base import FetchResult, SourceConnector
from bve.intelligence.extraction.raw_document import EntityHints
from bve.pipeline.pipeline_state import PipelineStateStore


class AssetLike(Protocol):
    company_id: str
    asset_id: str
    drug_name: Optional[str]
    indication: Optional[str]
    ticker: Optional[str]
    nct_id: Optional[str]


class BaseDataIngestionAgent:
    """Polls one source connector with per-source checkpoint cursors."""

    source_name: str

    def __init__(self, connector: SourceConnector, source_name: str) -> None:
        self.connector = connector
        self.source_name = source_name

    def poll_source(
        self,
        *,
        asset: AssetLike,
        state_store: PipelineStateStore,
        limit: int = 20,
        options: Optional[dict[str, Any]] = None,
    ) -> FetchResult:
        since = state_store.get_since(asset.company_id, asset.asset_id, self.source_name)
        hints = EntityHints(
            asset_id=asset.asset_id,
            company_id=asset.company_id,
            drug_name=asset.drug_name,
            indication=asset.indication,
            ticker=asset.ticker,
            nct_id=asset.nct_id,
        )

        kwargs: dict[str, Any] = {
            "entity_hints": hints,
            "since": since,
            "limit": limit,
        }
        sig = inspect.signature(self.connector.fetch)
        for key, value in (options or {}).items():
            if key in sig.parameters:
                kwargs[key] = value
        result = self.connector.fetch(**kwargs)
        state_store.set_last_fetch(
            asset.company_id,
            asset.asset_id,
            self.source_name,
            result.fetched_at,
        )
        return result

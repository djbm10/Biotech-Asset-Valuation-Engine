"""PubMed ingestion agent."""
from __future__ import annotations

from typing import Optional

from bve.agents.data_ingestion.base import BaseDataIngestionAgent
from bve.connectors.pubmed import PubMedConnector


class PubMedAgent(BaseDataIngestionAgent):
    def __init__(
        self,
        connector: Optional[PubMedConnector] = None,
        *,
        api_key: Optional[str] = None,
    ) -> None:
        super().__init__(connector or PubMedConnector(api_key=api_key), "pubmed")

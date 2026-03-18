"""FDA ingestion agent."""
from __future__ import annotations

from bve.agents.data_ingestion.base import BaseDataIngestionAgent
from bve.connectors.fda import FDAConnector


class FDAAgent(BaseDataIngestionAgent):
    def __init__(self, connector: FDAConnector | None = None) -> None:
        super().__init__(connector or FDAConnector(), "fda_website")

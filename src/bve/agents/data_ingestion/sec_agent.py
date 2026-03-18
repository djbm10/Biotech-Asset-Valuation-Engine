"""SEC EDGAR ingestion agent."""
from __future__ import annotations

from bve.agents.data_ingestion.base import BaseDataIngestionAgent
from bve.connectors.sec_edgar import SECEdgarConnector


class SECAgent(BaseDataIngestionAgent):
    def __init__(self, connector: SECEdgarConnector | None = None) -> None:
        super().__init__(connector or SECEdgarConnector(), "sec_filing")

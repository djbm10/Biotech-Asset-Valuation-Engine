"""ClinicalTrials.gov ingestion agent."""
from __future__ import annotations

from bve.agents.data_ingestion.base import BaseDataIngestionAgent
from bve.connectors.clinicaltrials import ClinicalTrialsConnector


class ClinicalTrialsAgent(BaseDataIngestionAgent):
    def __init__(self, connector: ClinicalTrialsConnector | None = None) -> None:
        super().__init__(connector or ClinicalTrialsConnector(), "clinicaltrials_gov")

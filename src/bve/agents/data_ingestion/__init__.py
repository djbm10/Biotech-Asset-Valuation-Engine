"""Data ingestion agents."""

from bve.agents.data_ingestion.clinical_trials_agent import ClinicalTrialsAgent
from bve.agents.data_ingestion.fda_agent import FDAAgent
from bve.agents.data_ingestion.news_agent import NewsAgent
from bve.agents.data_ingestion.pubmed_agent import PubMedAgent
from bve.agents.data_ingestion.sec_agent import SECAgent

__all__ = [
    "ClinicalTrialsAgent",
    "FDAAgent",
    "NewsAgent",
    "PubMedAgent",
    "SECAgent",
]

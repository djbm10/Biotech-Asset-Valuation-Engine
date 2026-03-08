"""
Source connectors for the intelligence ingestion pipeline.

Each connector wraps a specific external data source and normalizes
fetched content into ``RawDocument`` objects for the extraction layer.

Connectors never call LLM APIs and never create ``StructuredSignal`` objects.

Available connectors
--------------------
ClinicalTrialsConnector
    ClinicalTrials.gov v2 REST API — trial protocol records.
FDAConnector
    openFDA drug approval database — NDA/BLA submissions and review history.
PressReleaseConnector
    Direct URL fetch of company press releases; also provides ``from_text()``
    for loading pre-fetched or local documents.
SECEdgarConnector
    SEC EDGAR submissions API — 8-K, 10-K, 10-Q filings.
"""
from bve.connectors.base import FetchResult, SourceConnector
from bve.connectors.clinicaltrials import ClinicalTrialsConnector
from bve.connectors.fda import FDAConnector
from bve.connectors.press_release import PressReleaseConnector
from bve.connectors.sec_edgar import SECEdgarConnector

__all__ = [
    "FetchResult",
    "SourceConnector",
    "ClinicalTrialsConnector",
    "FDAConnector",
    "PressReleaseConnector",
    "SECEdgarConnector",
]

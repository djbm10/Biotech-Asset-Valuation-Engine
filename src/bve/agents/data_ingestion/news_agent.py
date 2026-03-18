"""News/press-release ingestion agent."""
from __future__ import annotations

from bve.agents.data_ingestion.base import BaseDataIngestionAgent
from bve.connectors.press_release import PressReleaseConnector


class NewsAgent(BaseDataIngestionAgent):
    def __init__(self, connector: PressReleaseConnector | None = None) -> None:
        super().__init__(connector or PressReleaseConnector(), "press_release")

"""
deal_researcher — orchestrate per-deal research across all data sources.

DealResearcher pulls together SEC, ClinicalTrials.gov, FDA, press release,
and market data for a single deal at a given snapshot date.  All returned
records carry provenance fields; gaps are recorded to research_gaps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional

from bve.backtest_research.clinicaltrials_client import ClinicalTrialsClient
from bve.backtest_research.company_press_release_client import CompanyPressReleaseClient
from bve.backtest_research.deal_seed_loader import DealRecord
from bve.backtest_research.historical_market_data_client import HistoricalMarketDataClient
from bve.backtest_research.openfda_client import OpenFDAClient
from bve.backtest_research.sec_client import SECClient


@dataclass
class ResearchGap:
    deal_id: str
    target_ticker: str
    snapshot_date: str
    field_name: str
    reason: str


@dataclass
class DealResearchResult:
    deal_id: str
    target_ticker: str
    acquirer_ticker: str
    snapshot_date: date

    # Collected data (None = not found / gap)
    target_market_data: Optional[dict[str, Any]] = None
    acquirer_financials: Optional[dict[str, Any]] = None
    target_trials: list[dict[str, Any]] = field(default_factory=list)
    target_fda_approvals: list[dict[str, Any]] = field(default_factory=list)
    acquirer_deal_history: list[dict[str, Any]] = field(default_factory=list)

    # Research gaps discovered
    gaps: list[ResearchGap] = field(default_factory=list)

    def record_gap(self, field_name: str, reason: str) -> None:
        self.gaps.append(ResearchGap(
            deal_id=self.deal_id,
            target_ticker=self.target_ticker,
            snapshot_date=self.snapshot_date.isoformat(),
            field_name=field_name,
            reason=reason,
        ))


class DealResearcher:
    """
    Research a deal at a given snapshot date using all available data sources.

    Usage::

        researcher = DealResearcher(raw_dir="research/backtests/vrtx_regn_2010/raw")
        result = researcher.research(deal_record, snapshot_date)
    """

    def __init__(self, raw_dir: Optional["str | Path"] = None) -> None:
        pr_raw_dir = Path(raw_dir) / "company_press_releases" if raw_dir else Path(".")
        self._sec = SECClient(raw_dir=str(raw_dir) if raw_dir else None)
        self._ct  = ClinicalTrialsClient()
        self._fda = OpenFDAClient()
        self._pr  = CompanyPressReleaseClient(raw_dir=pr_raw_dir)
        self._mkt = HistoricalMarketDataClient()

    def research(
        self,
        deal: DealRecord,
        snapshot_date: date,
    ) -> DealResearchResult:
        result = DealResearchResult(
            deal_id=deal.deal_id,
            target_ticker=deal.target_ticker,
            acquirer_ticker=deal.acquirer_ticker,
            snapshot_date=snapshot_date,
        )

        # 1. Target market data (None for private companies)
        mkt = self._mkt.get_market_cap(deal.target_ticker, snapshot_date)
        if mkt.get("market_cap_millions") is None:
            result.record_gap(
                "target_market_cap",
                f"{deal.target_ticker} may be private or delisted at {snapshot_date.isoformat()}",
            )
        result.target_market_data = mkt

        # 2. Acquirer financials
        fin = self._sec.get_financials(deal.acquirer_ticker, snapshot_date)
        if fin.get("cash_and_equivalents_millions") is None:
            result.record_gap(
                "acquirer_cash",
                f"SEC financials unavailable for {deal.acquirer_ticker} at {snapshot_date.isoformat()}",
            )
        result.acquirer_financials = fin

        # 3. Target clinical trials
        trials = self._ct.get_trials_for_drug(deal.lead_asset, snapshot_date)
        if not trials:
            result.record_gap(
                "target_clinical_trials",
                f"No ClinicalTrials.gov records found for {deal.lead_asset!r}",
            )
        result.target_trials = trials

        # 4. FDA approvals for lead asset
        approvals = self._fda.get_approvals_for_drug(deal.lead_asset, snapshot_date)
        result.target_fda_approvals = approvals

        # 5. Acquirer deal history (8-K)
        deal_hist = self._sec.get_deal_announcements(deal.acquirer_ticker, snapshot_date)
        result.acquirer_deal_history = deal_hist

        return result

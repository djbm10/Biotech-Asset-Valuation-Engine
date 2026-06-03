"""
target_snapshot_builder — build target company profiles as of a snapshot date.

Produces a flat dict describing the target's state at snapshot_date with
provenance fields.  No deal labels appear in the output.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Optional

from bve.backtest_research.clinicaltrials_client import ClinicalTrialsClient
from bve.backtest_research.historical_market_data_client import HistoricalMarketDataClient
from bve.backtest_research.openfda_client import OpenFDAClient
from bve.backtest_research.sec_client import SECClient


# Therapeutic area overlap helper
TA_KEYWORDS: dict[str, list[str]] = {
    "oncology": ["cancer", "tumor", "oncol", "leukemia", "lymphoma", "myeloma"],
    "rare_disease": ["rare", "orphan", "genetic", "enzyme"],
    "immunology": ["immune", "autoimmune", "inflamm", "lupus", "nephropathy", "baff"],
    "diabetes_endocrine": ["diabetes", "islet", "insulin", "endocrine", "beta cell"],
    "rare_disease_hearing": ["hearing", "ototoxic", "cochlea", "otoferlin", "deaf"],
    "neuroscience": ["neuro", "cns", "brain", "alzheimer", "parkinson"],
    "cardiovascular": ["heart", "cardiac", "atrial", "lipid", "cardiovascular"],
}


class TargetSnapshotBuilder:
    """
    Build a point-in-time target company snapshot.

    Usage::

        builder = TargetSnapshotBuilder()
        snap = builder.build(
            ticker="ALPN",
            lead_asset="povetacicept",
            snapshot_date=date(2024, 1, 10),
        )
    """

    def __init__(self, raw_dir: Optional["str | Path"] = None) -> None:
        self._sec = SECClient(raw_dir=str(raw_dir) if raw_dir else None)
        self._ct  = ClinicalTrialsClient()
        self._fda = OpenFDAClient()
        self._mkt = HistoricalMarketDataClient()

    def build(
        self,
        ticker: str,
        lead_asset: str,
        snapshot_date: date,
        therapeutic_area: str = "",
        indication: str = "",
        modality: str = "",
        is_public: Optional[bool] = None,
    ) -> dict[str, Any]:
        """
        Return flat target snapshot dict.

        is_public: if None, auto-detected via market data availability.
        """
        # -- Market / financial data
        if is_public is None:
            is_public = self._mkt.is_publicly_traded(ticker, snapshot_date)

        market_data: dict[str, Any] = {}
        if is_public:
            market_data = self._mkt.get_enterprise_value(ticker, snapshot_date)
        fin_data = self._sec.get_financials(ticker, snapshot_date)

        market_cap = market_data.get("market_cap_millions")
        ev = market_data.get("enterprise_value_millions")
        cash_m = market_data.get("cash_millions") or fin_data.get("cash_and_equivalents_millions")
        rd_m = fin_data.get("rd_expense_ttm_millions")

        # -- Clinical trials
        trials = self._ct.get_trials_for_drug(lead_asset, snapshot_date)
        highest_phase = self._ct.get_highest_phase(lead_asset, snapshot_date)
        n_active_trials = sum(1 for t in trials if "active" in str(t.get("status", "")).lower())

        # -- FDA approvals
        is_approved = self._fda.is_approved(lead_asset, snapshot_date)

        # -- Pipeline stage score [0–1]
        stage_score = self._stage_to_score(highest_phase, is_approved)

        # -- Provenance
        prov_date = (
            market_data.get("data_as_of_date")
            or fin_data.get("data_as_of_date")
            or snapshot_date.isoformat()
        )
        prov_url = (
            market_data.get("source_url")
            or fin_data.get("source_url")
            or ""
        )

        return {
            "ticker": ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "is_public": is_public,
            "market_cap_millions": market_cap,
            "enterprise_value_millions": ev,
            "cash_millions": cash_m,
            "rd_expense_ttm_millions": rd_m,
            "lead_asset": lead_asset,
            "lead_asset_modality": modality,
            "lead_asset_highest_phase": highest_phase,
            "lead_asset_stage_score": stage_score,
            "lead_asset_is_approved": is_approved,
            "n_active_clinical_trials": n_active_trials,
            "therapeutic_area": therapeutic_area,
            "indication": indication,
            # Provenance
            "source_url": prov_url,
            "source_published_date": prov_date,
            "data_as_of_date": prov_date,
            "extraction_method": market_data.get("extraction_method", "market_data_api"),
            "confidence": min(
                float(market_data.get("confidence", 0.85) if market_data else 0.5),
                float(fin_data.get("confidence", 0.70)),
            ),
        }

    @staticmethod
    def _stage_to_score(phase: Optional[str], is_approved: bool) -> float:
        if is_approved:
            return 1.0
        if phase is None:
            return 0.10
        phase_lower = phase.lower()
        if "3" in phase_lower:
            return 0.75
        if "2" in phase_lower:
            return 0.50
        if "1" in phase_lower:
            return 0.25
        return 0.10

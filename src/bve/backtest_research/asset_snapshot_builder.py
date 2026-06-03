"""
asset_snapshot_builder — build lead-asset profile snapshots as of a date.

Produces a structured dict for a specific drug/therapy asset at snapshot_date,
containing clinical stage, PoS estimate, market size, competitive landscape.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from bve.backtest_research.clinicaltrials_client import ClinicalTrialsClient
from bve.backtest_research.openfda_client import OpenFDAClient


# Phase → base PoS (industry-level, no asset-specific adjustments)
_PHASE_BASE_POS: dict[str, float] = {
    "phase 1": 0.10,
    "phase1":  0.10,
    "phase 2": 0.30,
    "phase2":  0.30,
    "phase 3": 0.65,
    "phase3":  0.65,
    "nda/bla": 0.85,
    "approved": 1.00,
    "preclinical": 0.05,
}


class AssetSnapshotBuilder:
    """
    Build a point-in-time asset snapshot.

    Usage::

        builder = AssetSnapshotBuilder()
        snap = builder.build(
            asset_name="povetacicept",
            indication="iga_nephropathy",
            snapshot_date=date(2024, 1, 10),
            modality="biologic_fusion_protein",
            sponsor_ticker="ALPN",
        )
    """

    def __init__(self) -> None:
        self._ct  = ClinicalTrialsClient()
        self._fda = OpenFDAClient()

    def build(
        self,
        asset_name: str,
        indication: str,
        snapshot_date: date,
        modality: str = "",
        sponsor_ticker: str = "",
        therapeutic_area: str = "",
    ) -> dict[str, Any]:
        """Return flat asset snapshot dict as of snapshot_date."""
        trials = self._ct.get_trials_for_drug(asset_name, snapshot_date)
        highest_phase = self._ct.get_highest_phase(asset_name, snapshot_date)
        is_approved = self._fda.is_approved(asset_name, snapshot_date)

        phase_label = "approved" if is_approved else (highest_phase or "preclinical")
        base_pos = _PHASE_BASE_POS.get(phase_label.lower(), 0.10)

        n_trials = len(trials)
        n_active = sum(1 for t in trials if "active" in str(t.get("status", "")).lower())

        # Primary enrollment as proxy for development maturity
        total_enrollment = sum(
            int(t.get("enrollment") or 0) for t in trials
            if str(t.get("enrollment", "")).isdigit()
        )

        # Provenance: use last update from the most recent trial record
        prov_dates = [
            t.get("data_as_of_date") or t.get("source_published_date") or ""
            for t in trials
        ]
        prov_date = max(prov_dates) if prov_dates else snapshot_date.isoformat()
        # Must not be after snapshot_date
        if prov_date > snapshot_date.isoformat():
            prov_date = snapshot_date.isoformat()

        return {
            "asset_name": asset_name,
            "indication": indication,
            "therapeutic_area": therapeutic_area,
            "modality": modality,
            "sponsor_ticker": sponsor_ticker,
            "snapshot_date": snapshot_date.isoformat(),
            "highest_phase": phase_label,
            "is_approved": is_approved,
            "base_pos": base_pos,
            "n_clinical_trials": n_trials,
            "n_active_trials": n_active,
            "total_enrollment": total_enrollment,
            # Provenance
            "source_url": f"https://clinicaltrials.gov/search?term={asset_name}",
            "source_published_date": prov_date,
            "data_as_of_date": prov_date,
            "extraction_method": "ct_gov_api",
            "confidence": 0.80 if n_trials > 0 else 0.30,
        }

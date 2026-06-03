"""
clinicaltrials_client — point-in-time ClinicalTrials.gov data with provenance.

IMPORTANT: ClinicalTrials.gov v2 API does not provide true point-in-time
historical snapshots.  The ``last_update_posted`` field is used as a proxy
for when data was published.  Studies updated after snapshot_date are
excluded from results.

This is a known limitation noted in the backtest README.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional


EXTRACTION_METHOD = "ct_gov_api"
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def _make_provenance(
    nct_id: str,
    last_update: str,
    snapshot_date: str,
    confidence: float = 0.80,
) -> dict[str, Any]:
    return {
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "source_published_date": last_update,
        "data_as_of_date": last_update,
        "extraction_method": EXTRACTION_METHOD,
        "confidence": confidence,
    }


class ClinicalTrialsClient:
    """
    Point-in-time ClinicalTrials.gov client.

    Only returns studies where last_update_posted <= snapshot_date.
    """

    def get_trials_for_drug(
        self,
        drug_name: str,
        snapshot_date: date,
        sponsor: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Return trials for a drug published before snapshot_date.

        Each trial dict contains:
          nct_id, title, phase, status, enrollment,
          primary_completion_date, last_update_posted,
          sponsor, conditions, interventions
          + provenance fields
        """
        try:
            from bve.ingestion.clinicaltrials_gov import fetch_trials_for_drug
            trials_raw = fetch_trials_for_drug(drug_name, asset_id=drug_name)
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        for t in trials_raw:
            last_update = t.get("last_update_posted") or ""
            # Exclude if last updated after snapshot_date
            if last_update and last_update > snapshot_date.isoformat():
                continue
            nct_id = t.get("nct_id", "")
            prov = _make_provenance(nct_id, last_update or snapshot_date.isoformat(),
                                    snapshot_date.isoformat())
            results.append({**t, **prov})
        return results

    def get_trial_by_nct(
        self,
        nct_id: str,
        snapshot_date: date,
    ) -> Optional[dict[str, Any]]:
        """
        Return a single trial record if it was updated before snapshot_date.
        Returns None if the trial was not yet published / updated.
        """
        try:
            from bve.ingestion.clinicaltrials_gov import fetch_trial_by_nct
            trial = fetch_trial_by_nct(nct_id, asset_id=nct_id)
        except Exception:
            return None
        if trial is None:
            return None
        last_update = trial.get("last_update_posted") or ""
        if last_update and last_update > snapshot_date.isoformat():
            return None
        prov = _make_provenance(nct_id, last_update or snapshot_date.isoformat(),
                                snapshot_date.isoformat())
        return {**trial, **prov}

    def get_highest_phase(
        self,
        drug_name: str,
        snapshot_date: date,
    ) -> Optional[str]:
        """
        Return the highest clinical phase achieved as of snapshot_date.
        Returns None if no trial data available.
        """
        trials = self.get_trials_for_drug(drug_name, snapshot_date)
        phase_order = {"phase 1": 1, "phase 2": 2, "phase 3": 3, "phase 4": 4,
                       "phase1": 1, "phase2": 2, "phase3": 3}
        best: Optional[tuple[int, str]] = None
        for t in trials:
            phase_raw = (t.get("phase") or "").lower()
            score = phase_order.get(phase_raw)
            if score and (best is None or score > best[0]):
                best = (score, t.get("phase", ""))
        return best[1] if best else None

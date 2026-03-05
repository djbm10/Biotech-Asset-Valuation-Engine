"""
ClinicalTrials.gov v2 REST API client.

Docs: https://clinicaltrials.gov/data-api/api
"""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

from bve.config.constants import PHASE_DURATIONS_YEARS, PHASE_COSTS_MILLIONS
from bve.entities.trial import (
    ClinicalTrial, TrialArm, TrialPhase, TrialStatus, EndpointType
)

BASE_URL = "https://clinicaltrials.gov/api/v2"

_STATUS_MAP: dict[str, TrialStatus] = {
    "NOT_YET_RECRUITING": TrialStatus.NOT_YET_RECRUITING,
    "RECRUITING": TrialStatus.RECRUITING,
    "ACTIVE_NOT_RECRUITING": TrialStatus.ACTIVE_NOT_RECRUITING,
    "COMPLETED": TrialStatus.COMPLETED,
    "TERMINATED": TrialStatus.TERMINATED,
    "WITHDRAWN": TrialStatus.WITHDRAWN,
}

_PHASE_MAP: dict[str, TrialPhase] = {
    "PHASE1": TrialPhase.PHASE_1,
    "PHASE2": TrialPhase.PHASE_2,
    "PHASE3": TrialPhase.PHASE_3,
    "PHASE4": TrialPhase.PHASE_3,  # treat Phase 4 as Phase 3 for valuation
}


def _get(path: str, params: dict | None = None, timeout: int = 30, retries: int = 3) -> dict:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return {}  # unreachable but satisfies type checker


def fetch_study(nct_id: str) -> dict[str, Any]:
    """Fetch a single study by NCT ID. Returns raw protocol section dict."""
    data = _get(f"/studies/{nct_id}")
    return data.get("protocolSection", {})


def search_studies(
    condition: Optional[str] = None,
    intervention: Optional[str] = None,
    sponsor: Optional[str] = None,
    status_filter: Optional[list[str]] = None,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """
    Search ClinicalTrials.gov and return a list of raw protocol sections.

    Parameters
    ----------
    condition:   disease/condition keyword  (query.cond)
    intervention: drug/treatment name       (query.intr)
    sponsor:     sponsor name               (query.spons)
    status_filter: list of statuses to include, e.g. ["RECRUITING", "ACTIVE_NOT_RECRUITING"]
    page_size:   results per page (max 1000)
    """
    params: dict[str, Any] = {"pageSize": min(page_size, 1000)}
    if condition:
        params["query.cond"] = condition
    if intervention:
        params["query.intr"] = intervention
    if sponsor:
        params["query.spons"] = sponsor
    if status_filter:
        params["filter.overallStatus"] = ",".join(status_filter)

    studies: list[dict] = []
    page_token: Optional[str] = None

    while True:
        if page_token:
            params["pageToken"] = page_token
        data = _get("/studies", params=params)
        for s in data.get("studies", []):
            proto = s.get("protocolSection", {})
            if proto:
                studies.append(proto)
        page_token = data.get("nextPageToken")
        if not page_token or len(studies) >= page_size:
            break

    return studies[:page_size]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_phase(protocol: dict) -> Optional[TrialPhase]:
    design = protocol.get("designModule", {})
    phases: list[str] = design.get("phases", [])
    for p in phases:
        if p in _PHASE_MAP:
            return _PHASE_MAP[p]
    return None


def _parse_status(protocol: dict) -> TrialStatus:
    raw = protocol.get("statusModule", {}).get("overallStatus", "")
    return _STATUS_MAP.get(raw, TrialStatus.UNKNOWN)


def _parse_enrollment(protocol: dict) -> Optional[int]:
    enroll = protocol.get("designModule", {}).get("enrollmentInfo", {})
    count = enroll.get("count")
    return int(count) if count else None


def _parse_dates(protocol: dict) -> tuple[Optional[str], Optional[str]]:
    sm = protocol.get("statusModule", {})
    start = sm.get("startDateStruct", {}).get("date")
    primary_completion = sm.get("primaryCompletionDateStruct", {}).get("date")
    return start, primary_completion


def _parse_primary_endpoint(protocol: dict) -> Optional[str]:
    outcomes = protocol.get("outcomesModule", {})
    primary = outcomes.get("primaryOutcomes", [])
    if primary:
        return primary[0].get("measure")
    return None


def _parse_arms(protocol: dict) -> list[TrialArm]:
    arms_raw = protocol.get("armsInterventionsModule", {}).get("armGroups", [])
    arms = []
    for a in arms_raw:
        arms.append(TrialArm(
            label=a.get("label", ""),
            arm_type=a.get("type", "EXPERIMENTAL"),
            intervention=a.get("interventionNames", [None])[0],
        ))
    return arms


def _estimate_duration(start: Optional[str], completion: Optional[str]) -> float:
    """Compute duration in years from ISO date strings. Falls back to phase default."""
    if start and completion:
        try:
            from datetime import date
            fmt = "%Y-%m-%d"
            # Handle YYYY-MM and YYYY-MM-DD
            s = start[:10].ljust(10, "-01"[:10 - len(start[:7])])
            c = completion[:10].ljust(10, "-01"[:10 - len(completion[:7])])
            d0 = date.fromisoformat(start[:7] + "-01")
            d1 = date.fromisoformat(completion[:7] + "-01")
            years = (d1 - d0).days / 365.25
            if 0.25 < years < 15:
                return round(years, 1)
        except (ValueError, TypeError):
            pass
    return None


def parse_trial(
    protocol: dict,
    asset_id: str,
    fallback_success_prob: float = 0.40,
) -> Optional[ClinicalTrial]:
    """
    Convert a raw ClinicalTrials.gov protocol section → ClinicalTrial entity.

    success_probability is set to fallback_success_prob; caller should override
    with the POS model after construction.
    """
    phase = _parse_phase(protocol)
    if phase is None:
        return None

    id_module = protocol.get("identificationModule", {})
    nct_id = id_module.get("nctId")
    title = id_module.get("briefTitle")

    status = _parse_status(protocol)
    enrollment = _parse_enrollment(protocol)
    start_date, completion_date = _parse_dates(protocol)
    primary_endpoint = _parse_primary_endpoint(protocol)
    arms = _parse_arms(protocol)

    duration = _estimate_duration(start_date, completion_date)
    if duration is None:
        duration = PHASE_DURATIONS_YEARS[phase.value]

    cost = PHASE_COSTS_MILLIONS[phase.value]

    return ClinicalTrial(
        asset_id=asset_id,
        phase=phase,
        nct_id=nct_id,
        title=title,
        success_probability=fallback_success_prob,
        primary_endpoint=primary_endpoint,
        duration_years=duration,
        cost_millions=cost,
        start_date=start_date,
        primary_completion_date=completion_date,
        enrollment=enrollment,
        arms=arms,
        status=status,
        data_source="clinicaltrials_gov",
    )


def fetch_trials_for_drug(
    drug_name: str,
    asset_id: str,
    status_filter: Optional[list[str]] = None,
) -> list[ClinicalTrial]:
    """
    Convenience: search by drug name, parse all returned studies into ClinicalTrial objects.

    Parameters
    ----------
    drug_name:  intervention name to search (e.g. "sotorasib")
    asset_id:   asset ID to tag on returned trials
    status_filter: default includes recruiting + active + completed

    Returns
    -------
    List of ClinicalTrial objects (success_probability set to phase default; override with POS model).
    """
    if status_filter is None:
        status_filter = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"]

    protocols = search_studies(intervention=drug_name, status_filter=status_filter)
    trials = []
    for proto in protocols:
        t = parse_trial(proto, asset_id=asset_id)
        if t is not None:
            trials.append(t)
    return trials


def fetch_trial_by_nct(nct_id: str, asset_id: str) -> Optional[ClinicalTrial]:
    """Fetch a single trial by NCT ID and parse it."""
    proto = fetch_study(nct_id)
    if not proto:
        return None
    return parse_trial(proto, asset_id=asset_id)

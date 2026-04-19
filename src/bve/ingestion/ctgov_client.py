"""
ClinicalTrials.gov v2 ingestion client.

Returns typed RawEvent records from the CT.gov REST API.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from bve.ingestion.raw_event import RawEvent

BASE_URL = "https://clinicaltrials.gov/api/v2"

_STATUS_WHITELIST = {
    "NOT_YET_RECRUITING",
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "TERMINATED",
    "WITHDRAWN",
    "SUSPENDED",
}


def _get(path: str, params: dict | None = None, retries: int = 3) -> dict:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return {}


def _study_url(nct_id: str) -> str:
    return f"{BASE_URL}/studies/{nct_id}"


def _extract_study_payload(study: dict[str, Any]) -> dict[str, Any]:
    """Normalise a raw CT.gov study dict into a flat payload."""
    proto = study.get("protocolSection", {})
    id_mod = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    design_mod = proto.get("designModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    outcomes_mod = proto.get("outcomesModule", {})
    eligibility_mod = proto.get("eligibilityModule", {})
    contacts_mod = proto.get("contactsLocationsModule", {})

    phases = design_mod.get("phases", [])
    arms = arms_mod.get("armGroups", [])
    primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
    secondary_outcomes = outcomes_mod.get("secondaryOutcomes", [])

    locations = contacts_mod.get("locations", [])
    n_sites = len(locations)

    return {
        "nct_id": id_mod.get("nctId", ""),
        "brief_title": id_mod.get("briefTitle", ""),
        "official_title": id_mod.get("officialTitle", ""),
        "status": status_mod.get("overallStatus", ""),
        "start_date": status_mod.get("startDateStruct", {}).get("date", ""),
        "primary_completion_date": status_mod.get(
            "primaryCompletionDateStruct", {}
        ).get("date", ""),
        "completion_date": status_mod.get("completionDateStruct", {}).get("date", ""),
        "phases": phases,
        "enrollment": design_mod.get("enrollmentInfo", {}).get("count"),
        "allocation": design_mod.get("designInfo", {}).get("allocation", ""),
        "intervention_model": design_mod.get("designInfo", {}).get(
            "interventionModel", ""
        ),
        "masking": design_mod.get("designInfo", {})
        .get("maskingInfo", {})
        .get("masking", ""),
        "arms": [
            {
                "label": a.get("label", ""),
                "type": a.get("type", ""),
                "description": a.get("description", ""),
            }
            for a in arms
        ],
        "primary_outcomes": [
            {"measure": o.get("measure", ""), "time_frame": o.get("timeFrame", "")}
            for o in primary_outcomes
        ],
        "secondary_outcomes": [
            {"measure": o.get("measure", ""), "time_frame": o.get("timeFrame", "")}
            for o in secondary_outcomes
        ],
        "eligibility_criteria": eligibility_mod.get("eligibilityCriteria", ""),
        "minimum_age": eligibility_mod.get("minimumAge", ""),
        "maximum_age": eligibility_mod.get("maximumAge", ""),
        "n_sites": n_sites,
    }


def fetch_trial(nct_id: str, entity_ids: list[str] | None = None) -> list[RawEvent]:
    """
    Fetch a single CT.gov study by NCT ID.

    Returns one RawEvent with record_type="trial_study".
    """
    url = _study_url(nct_id)
    data = _get(f"/studies/{nct_id}")
    if not data:
        return []
    payload = _extract_study_payload(data)
    return [
        RawEvent(
            source="ctgov",
            record_type="trial_study",
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def search_trials(
    drug_name: str | None = None,
    condition: str | None = None,
    sponsor: str | None = None,
    status: list[str] | None = None,
    phase: list[str] | None = None,
    limit: int = 20,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Search CT.gov and return a RawEvent per matching study.

    record_type="trial_study"
    """
    params: dict[str, Any] = {"pageSize": min(limit, 100)}
    if drug_name:
        params["query.intr"] = drug_name
    if condition:
        params["query.cond"] = condition
    if sponsor:
        params["query.lead"] = sponsor
    if status:
        params["filter.overallStatus"] = ",".join(status)
    if phase:
        params["filter.phase"] = ",".join(phase)

    data = _get("/studies", params=params)
    studies = data.get("studies", [])

    events: list[RawEvent] = []
    for study in studies[:limit]:
        proto = study.get("protocolSection", {})
        nct_id = proto.get("identificationModule", {}).get("nctId", "")
        source_url = _study_url(nct_id) if nct_id else BASE_URL + "/studies"
        payload = _extract_study_payload(study)
        events.append(
            RawEvent(
                source="ctgov",
                record_type="trial_study",
                source_url=source_url,
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
                entity_ids=entity_ids or [],
            )
        )
    return events

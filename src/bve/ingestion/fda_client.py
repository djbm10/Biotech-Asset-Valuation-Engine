"""
openFDA / Drugs@FDA ingestion client.

Returns typed RawEvent records from:
- openFDA drug approval endpoint (NDA/BLA)
- openFDA drug event (adverse event) endpoint
- FDA label endpoint
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from bve.ingestion.raw_event import RawEvent

OPENFDA_BASE = "https://api.fda.gov/drug"


def _get(
    url: str,
    params: dict | None = None,
    retries: int = 3,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            if diagnostics is not None:
                diagnostics.append({
                    "url": getattr(r, "url", url),
                    "status": r.status_code,
                    "records_returned": 0,
                })
            if r.status_code == 404:
                if diagnostics is not None:
                    diagnostics[-1]["zero_match_reason"] = "no_match"
                return {
                    "results": [],
                    "status": "no_fda_record",
                    "reason": "not_found",
                }
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)
    return {}


def _approval_url(app_type: str = "nda") -> str:
    """Return the FDA Drugs@FDA endpoint.

    ``nda.json`` and ``bla.json`` are not openFDA endpoints.  They used to be
    accepted by some proxies, but currently return an HTML 404, which the
    caller historically misreported as a quiet window.
    """
    return f"{OPENFDA_BASE}/drugsfda.json"


def fetch_approvals(
    drug_name: str,
    limit: int = 20,
    entity_ids: list[str] | None = None,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[RawEvent]:
    """
    Search openFDA for NDA/BLA approvals matching a drug name.

    Returns one RawEvent per application record, record_type="drug_approval".
    """
    url = _approval_url()
    params = {
        "search": (
            f'openfda.brand_name:"{drug_name}"'
            f' OR openfda.generic_name:"{drug_name}"'
        ),
        "limit": limit,
    }
    data = _get(url, params=params, diagnostics=diagnostics)
    results = data.get("results", [])
    if diagnostics is not None and diagnostics:
        diagnostics[-1]["records_returned"] = len(results)
    if results:
        events: list[RawEvent] = []
        for rec in results:
            payload: dict[str, Any] = {
                "application_number": rec.get("application_number", ""),
                "sponsor_name": rec.get("sponsor_name", ""),
                "products": [
                    {
                        "brand_name": p.get("brand_name", ""),
                        "generic_name": p.get("active_ingredients", [{}])[0].get(
                            "name", ""
                        ) if p.get("active_ingredients") else "",
                        "dosage_form": p.get("dosage_form", ""),
                        "route": p.get("route", ""),
                        "marketing_status": p.get("marketing_status", ""),
                    }
                    for p in rec.get("products", [])
                ],
                "submissions": [
                    {
                        "submission_type": s.get("submission_type", ""),
                        "submission_number": s.get("submission_number", ""),
                        "submission_status": s.get("submission_status", ""),
                        "submission_status_date": s.get("submission_status_date", ""),
                        "submission_class_code_description": s.get(
                            "submission_class_code_description", ""
                        ),
                        "action_type": s.get("submission_type", ""),
                    }
                    for s in rec.get("submissions", [])
                ],
                "openfda": rec.get("openfda", {}),
            }
            events.append(
                RawEvent(
                    source="openfda",
                    record_type="drug_approval",
                    source_url=url,
                    fetched_at=datetime.now(timezone.utc),
                    payload=payload,
                    entity_ids=entity_ids or [],
                )
            )
        return events
    return []


def fetch_application(
    application_number: str,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch a specific NDA/BLA application by number.

    application_number: e.g. "NDA212608" or "BLA125514"
    Returns zero or one RawEvent with record_type="drug_approval".
    """
    app_type = application_number[:3].upper()
    endpoint = "nda" if app_type == "NDA" else "bla"
    url = _approval_url(endpoint)
    params = {"search": f"application_number:{application_number}", "limit": 1}
    data = _get(url, params=params)
    results = data.get("results", [])
    if not results:
        return []
    rec = results[0]
    payload: dict[str, Any] = {
        "application_number": rec.get("application_number", application_number),
        "sponsor_name": rec.get("sponsor_name", ""),
        "submissions": rec.get("submissions", []),
        "products": rec.get("products", []),
        "openfda": rec.get("openfda", {}),
    }
    return [
        RawEvent(
            source="openfda",
            record_type="drug_approval",
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def fetch_adverse_events(
    drug_name: str,
    limit: int = 100,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Search openFDA adverse event reports for a drug.

    Returns one RawEvent with record_type="adverse_event_summary" containing
    aggregated reaction counts.
    """
    url = f"{OPENFDA_BASE}/event.json"
    params = {
        "search": f'patient.drug.medicinalproduct:"{drug_name}"',
        "count": "patient.reaction.reactionmeddrapt.exact",
        "limit": limit,
    }
    data = _get(url, params=params)
    results = data.get("results", [])
    if not results:
        return []
    payload: dict[str, Any] = {
        "drug_name": drug_name,
        "reaction_counts": [
            {"reaction": r.get("term", ""), "count": r.get("count", 0)}
            for r in results
        ],
        "total_reactions": sum(r.get("count", 0) for r in results),
    }
    return [
        RawEvent(
            source="openfda",
            record_type="adverse_event_summary",
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def fetch_drug_label(
    drug_name: str,
    limit: int = 5,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch drug label sections (indications, warnings, boxed warning) from openFDA.

    Returns one RawEvent per label result, record_type="drug_label".
    """
    url = f"{OPENFDA_BASE}/label.json"
    params = {
        "search": (
            f'openfda.brand_name:"{drug_name}"'
            f' OR openfda.generic_name:"{drug_name}"'
        ),
        "limit": limit,
    }
    data = _get(url, params=params)
    results = data.get("results", [])
    events: list[RawEvent] = []
    for rec in results:
        payload: dict[str, Any] = {
            "drug_name": drug_name,
            "indications_and_usage": rec.get("indications_and_usage", []),
            "warnings_and_cautions": rec.get("warnings_and_cautions", []),
            "boxed_warning": rec.get("boxed_warning", []),
            "dosage_and_administration": rec.get("dosage_and_administration", []),
            "contraindications": rec.get("contraindications", []),
            "openfda": rec.get("openfda", {}),
        }
        events.append(
            RawEvent(
                source="openfda",
                record_type="drug_label",
                source_url=url,
                fetched_at=datetime.now(timezone.utc),
                payload=payload,
                entity_ids=entity_ids or [],
            )
        )
    return events

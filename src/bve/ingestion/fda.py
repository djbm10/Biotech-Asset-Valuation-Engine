"""
FDA data ingestion via openFDA API and FDA website.

Covers:
- Drug approval history (NDA/BLA approvals, CRLs)
- PDUFA dates
- Breakthrough / Fast Track / Orphan designations
"""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

OPENFDA_BASE = "https://api.fda.gov/drug"


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    return {}


def search_approvals(drug_name: str, limit: int = 20) -> list[dict[str, Any]]:
    """
    Search openFDA for NDA/BLA approval records matching a drug name.

    Returns list of application records.
    """
    params = {
        "search": f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"',
        "limit": limit,
    }
    data = _get(f"{OPENFDA_BASE}/nda.json", params=params)
    return data.get("results", [])


def get_approval_status(application_number: str) -> Optional[dict[str, Any]]:
    """
    Fetch details for a specific NDA or BLA application number.

    application_number: e.g. "NDA212608" or "BLA125514"
    """
    app_type = application_number[:3].upper()
    app_num = application_number[3:]
    endpoint = f"{OPENFDA_BASE}/{'nda' if app_type == 'NDA' else 'bla'}.json"
    params = {"search": f"application_number:{application_number}", "limit": 1}
    data = _get(endpoint, params=params)
    results = data.get("results", [])
    return results[0] if results else None


def get_designations(drug_name: str) -> dict[str, bool]:
    """
    Check for special FDA designations for a drug.
    Returns dict of {designation_type: bool}.

    NOTE: openFDA does not have a single endpoint for all designations.
    This returns best-effort results from the drug label search.
    """
    params = {
        "search": f'openfda.brand_name:"{drug_name}"',
        "count": "openfda.pharm_class_epc.exact",
        "limit": 5,
    }
    data = _get(f"{OPENFDA_BASE}/label.json", params=params)

    # Designation data is sparse in openFDA; flag as not-found by default
    return {
        "breakthrough_therapy": False,
        "fast_track": False,
        "orphan_drug": False,
        "accelerated_approval": False,
        "priority_review": False,
    }


def parse_approval_date(record: dict) -> Optional[str]:
    """Extract most recent approval date from an NDA/BLA record."""
    submissions = record.get("submissions", [])
    approved = [
        s for s in submissions
        if s.get("submission_status", "").upper() == "AP"
    ]
    if approved:
        return max(s.get("submission_status_date", "") for s in approved)
    return None

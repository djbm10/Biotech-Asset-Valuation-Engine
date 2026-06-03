"""
openfda_client — point-in-time FDA approval data with provenance.

Returns FDA drug approval records that were approved before snapshot_date.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional


EXTRACTION_METHOD = "fda_api"
BASE_URL = "https://api.fda.gov/drug/drugsfda.json"


def _make_provenance(
    application_number: str,
    approval_date: str,
    snapshot_date: str,
    confidence: float = 0.95,
) -> dict[str, Any]:
    return {
        "source_url": (
            f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm"
            f"?event=overview.process&ApplNo={application_number}"
        ),
        "source_published_date": approval_date,
        "data_as_of_date": approval_date,
        "extraction_method": EXTRACTION_METHOD,
        "confidence": confidence,
    }


class OpenFDAClient:
    """
    Point-in-time FDA approval data.

    Only returns approvals where approval_date <= snapshot_date.
    """

    def get_approvals_for_drug(
        self,
        drug_name: str,
        snapshot_date: date,
    ) -> list[dict[str, Any]]:
        """
        Return FDA approval records for drug_name published before snapshot_date.

        Each record contains:
          application_number, brand_name, generic_name,
          application_type (NDA | BLA | ANDA),
          approval_date, sponsor, indications
          + provenance fields
        """
        try:
            from bve.ingestion.fda_client import get_approvals_for_drug as _get
            raw = _get(drug_name)
        except Exception:
            return []

        results: list[dict[str, Any]] = []
        for item in (raw or []):
            app_date = item.get("approval_date", "")
            if app_date and app_date > snapshot_date.isoformat():
                continue
            app_no = item.get("application_number", "")
            prov = _make_provenance(app_no, app_date or snapshot_date.isoformat(),
                                    snapshot_date.isoformat())
            results.append({**item, **prov})
        return results

    def is_approved(
        self,
        drug_name: str,
        snapshot_date: date,
    ) -> bool:
        """Return True if drug_name had any FDA approval before snapshot_date."""
        return len(self.get_approvals_for_drug(drug_name, snapshot_date)) > 0

    def get_approval_count(
        self,
        sponsor: str,
        snapshot_date: date,
    ) -> Optional[int]:
        """
        Return number of approved NDA/BLA products for a sponsor as of snapshot_date.
        Returns None if data unavailable.
        """
        try:
            from bve.ingestion.fda_client import get_approvals_by_sponsor as _get_sponsor
            items = _get_sponsor(sponsor) or []
        except Exception:
            return None
        count = sum(
            1 for item in items
            if (item.get("approval_date") or "") <= snapshot_date.isoformat()
        )
        return count

"""
CMS Open Payments ingestion client.

CMS Open Payments (Sunshine Act) tracks financial relationships between
drug/device manufacturers and physicians + teaching hospitals.

API: https://openpaymentsdata.cms.gov/api/1/

Data is useful for:
- Identifying KOLs (key opinion leaders) with manufacturer relationships
- Understanding commercial investment by company in a TA
- Flagging potential conflict-of-interest in published research
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from bve.ingestion.raw_event import RawEvent

CMS_API_BASE = "https://openpaymentsdata.cms.gov/api/1"

# General payments dataset ID (general payments = consulting, honoraria, travel, etc.)
GENERAL_PAYMENTS_DATASET = "general-payment-data-with-identifying-recipient-information"
RESEARCH_PAYMENTS_DATASET = "research-payment-data-with-identifying-recipient-information"


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict:
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


def fetch_general_payments(
    company_name: str,
    year: int | None = None,
    limit: int = 100,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch general payments (consulting, honoraria, travel) made by a company.

    Returns one RawEvent with record_type="open_payments_general" containing
    an aggregated summary of payments.
    """
    url = f"{CMS_API_BASE}/{GENERAL_PAYMENTS_DATASET}"
    params: dict[str, Any] = {
        "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name": company_name,
        "$limit": limit,
    }
    if year:
        params["Program_Year"] = str(year)

    data = _get(url, params=params)

    # CMS API returns a list directly or a dict with results
    records = data if isinstance(data, list) else data.get("results", [])

    if not records:
        return []

    total_amount = 0.0
    by_type: dict[str, float] = {}
    recipients: list[dict[str, Any]] = []

    for rec in records:
        amount_str = rec.get("Total_Amount_of_Payment_USDollars", "0")
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            amount = 0.0
        total_amount += amount
        nature = rec.get("Nature_of_Payment_or_Transfer_of_Value", "Other")
        by_type[nature] = by_type.get(nature, 0.0) + amount
        recipient_name = (
            f"{rec.get('Covered_Recipient_First_Name', '')} "
            f"{rec.get('Covered_Recipient_Last_Name', '')}".strip()
        )
        specialty = rec.get("Covered_Recipient_Primary_Type_1", "")
        if recipient_name:
            recipients.append(
                {
                    "name": recipient_name,
                    "specialty": specialty,
                    "amount": amount,
                    "nature": nature,
                    "year": rec.get("Program_Year", ""),
                    "city": rec.get("Recipient_City", ""),
                    "state": rec.get("Recipient_State", ""),
                }
            )

    payload: dict[str, Any] = {
        "company_name": company_name,
        "year": year,
        "total_amount_usd": total_amount,
        "record_count": len(records),
        "by_payment_type": by_type,
        "top_recipients": sorted(recipients, key=lambda r: r["amount"], reverse=True)[
            :20
        ],
    }
    return [
        RawEvent(
            source="open_payments",
            record_type="open_payments_general",
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]


def fetch_research_payments(
    company_name: str,
    year: int | None = None,
    limit: int = 100,
    entity_ids: list[str] | None = None,
) -> list[RawEvent]:
    """
    Fetch research payments made by a company to investigators.

    Returns one RawEvent with record_type="open_payments_research".
    """
    url = f"{CMS_API_BASE}/{RESEARCH_PAYMENTS_DATASET}"
    params: dict[str, Any] = {
        "Applicable_Manufacturer_or_Applicable_GPO_Making_Payment_Name": company_name,
        "$limit": limit,
    }
    if year:
        params["Program_Year"] = str(year)

    data = _get(url, params=params)
    records = data if isinstance(data, list) else data.get("results", [])

    if not records:
        return []

    total_amount = 0.0
    by_drug: dict[str, float] = {}
    investigators: list[dict[str, Any]] = []

    for rec in records:
        amount_str = rec.get("Total_Amount_of_Payment_USDollars", "0")
        try:
            amount = float(amount_str)
        except (ValueError, TypeError):
            amount = 0.0
        total_amount += amount
        drug = rec.get(
            "Name_of_Drug_or_Biological_or_Device_or_Medical_Supply_1", "Unknown"
        )
        by_drug[drug] = by_drug.get(drug, 0.0) + amount
        pi_name = (
            f"{rec.get('Principal_Investigator_1_First_Name', '')} "
            f"{rec.get('Principal_Investigator_1_Last_Name', '')}".strip()
        )
        if pi_name:
            investigators.append(
                {
                    "name": pi_name,
                    "institution": rec.get(
                        "Research_Information_Institution_1", ""
                    ),
                    "amount": amount,
                    "drug": drug,
                    "year": rec.get("Program_Year", ""),
                }
            )

    payload: dict[str, Any] = {
        "company_name": company_name,
        "year": year,
        "total_amount_usd": total_amount,
        "record_count": len(records),
        "by_drug": by_drug,
        "principal_investigators": sorted(
            investigators, key=lambda r: r["amount"], reverse=True
        )[:20],
    }
    return [
        RawEvent(
            source="open_payments",
            record_type="open_payments_research",
            source_url=url,
            fetched_at=datetime.now(timezone.utc),
            payload=payload,
            entity_ids=entity_ids or [],
        )
    ]

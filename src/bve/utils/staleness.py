"""Staleness warnings for YAML-sourced financial inputs and acquirer profiles."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

_FINANCIAL_THRESHOLD_DAYS = 60
_PROFILE_THRESHOLD_DAYS = 90


@dataclass
class StalenessWarning:
    """A warning that a data source is older than its acceptable threshold."""

    field: str
    data_as_of: date
    age_days: int
    threshold_days: int
    severity: str  # "warning" | "critical"
    message: str


def check_staleness(
    data_as_of: date,
    field: str,
    threshold_days: int = 60,
    reference_date: Optional[date] = None,
) -> Optional[StalenessWarning]:
    """Return a StalenessWarning if data_as_of is older than threshold_days.

    Parameters
    ----------
    data_as_of:
        The as-of date of the data.
    field:
        Human-readable name of the data field (used in the warning message).
    threshold_days:
        Number of days before a warning is raised. Strictly greater than
        (i.e. exactly at threshold → no warning).
    reference_date:
        Date to measure age from. Defaults to today.

    Returns
    -------
    StalenessWarning or None
    """
    ref = reference_date if reference_date is not None else date.today()
    age = (ref - data_as_of).days
    if age > threshold_days:
        severity = "critical" if age > threshold_days * 2 else "warning"
        return StalenessWarning(
            field=field,
            data_as_of=data_as_of,
            age_days=age,
            threshold_days=threshold_days,
            severity=severity,
            message=(
                f"{field} is {age} days old (threshold: {threshold_days} days)"
            ),
        )
    return None


def check_financial_staleness(
    data_as_of: date,
    reference_date: Optional[date] = None,
) -> Optional[StalenessWarning]:
    """Check staleness of YAML-sourced financial inputs (60-day threshold)."""
    return check_staleness(
        data_as_of,
        field="financial_data",
        threshold_days=_FINANCIAL_THRESHOLD_DAYS,
        reference_date=reference_date,
    )


def check_profile_staleness(
    profile_as_of: date,
    reference_date: Optional[date] = None,
) -> Optional[StalenessWarning]:
    """Check staleness of acquirer profile data (90-day threshold)."""
    return check_staleness(
        profile_as_of,
        field="acquirer_profile",
        threshold_days=_PROFILE_THRESHOLD_DAYS,
        reference_date=reference_date,
    )

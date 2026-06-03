"""
trial_phase_resolver — resolve trial phase as of a snapshot date without look-ahead bias.

ClinicalTrials.gov's v2 API returns the *current* record, not the historical state.
Using ``last_update_posted`` as a proxy introduces look-ahead bias when that date
is after the snapshot_date.  This module enforces a source-hierarchy to obtain
the most accurate pre-snapshot phase available.

Source hierarchy (highest confidence first):
  1. SEC filing (10-K / 10-Q) before snapshot_date
  2. Company press release before snapshot_date
  3. Investor deck / earnings call before snapshot_date
  4. Peer-reviewed publication before snapshot_date
  5. ClinicalTrials.gov historical record / Wayback Machine archive
  6. ClinicalTrials.gov current record (fallback) — ONLY when
     last_update_posted <= snapshot_date

When no pre-snapshot source exists:
  phase = null
  status = clinicaltrials_after_snapshot_rejected  (or  unknown)
  Evidence-coverage penalty applied by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Source types
# ---------------------------------------------------------------------------

class TrialPhaseSourceType(str, Enum):
    SEC_FILING               = "confirmed_from_sec"
    PRESS_RELEASE            = "confirmed_from_press_release"
    INVESTOR_DECK            = "confirmed_from_investor_deck"
    PUBLICATION              = "confirmed_from_publication"
    CLINICALTRIALS_ARCHIVE   = "clinicaltrials_historical_archive"
    CLINICALTRIALS_CURRENT   = "clinicaltrials_current_fallback"
    REJECTED_POST_SNAPSHOT   = "clinicaltrials_after_snapshot_rejected"
    UNKNOWN                  = "unknown"


# Priority order: lower index = higher confidence
_SOURCE_PRIORITY: list[TrialPhaseSourceType] = [
    TrialPhaseSourceType.SEC_FILING,
    TrialPhaseSourceType.PRESS_RELEASE,
    TrialPhaseSourceType.INVESTOR_DECK,
    TrialPhaseSourceType.PUBLICATION,
    TrialPhaseSourceType.CLINICALTRIALS_ARCHIVE,
    TrialPhaseSourceType.CLINICALTRIALS_CURRENT,
]


# ---------------------------------------------------------------------------
# Source record
# ---------------------------------------------------------------------------

@dataclass
class TrialPhaseSource:
    """A single sourced phase assertion with provenance."""
    source_type: TrialPhaseSourceType
    phase: Optional[str]
    published_date: Optional[date]
    source_url: str = ""
    notes: str = ""
    is_pre_snapshot: bool = True


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class TrialPhaseResult:
    """Output of resolve_phase_as_of_snapshot()."""
    asset_id: str
    snapshot_date: date
    resolved_phase: Optional[str]
    source_type: TrialPhaseSourceType
    source_url: str
    published_date: Optional[date]
    is_pre_snapshot: bool
    near_snapshot_update_risk: bool     # True when CT.gov updated <30d after snapshot
    point_in_time_status: str           # human-readable status field for audit CSV
    all_sources_checked: list[TrialPhaseSource] = field(default_factory=list)

    @property
    def is_trustworthy(self) -> bool:
        """True when the resolved phase comes from a confirmed pre-snapshot source."""
        return self.is_pre_snapshot and self.source_type not in (
            TrialPhaseSourceType.REJECTED_POST_SNAPSHOT,
            TrialPhaseSourceType.UNKNOWN,
        )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

class TrialPhaseResolver:
    """
    Resolve the clinical phase of an asset as of a given snapshot date.

    Pass a list of ``TrialPhaseSource`` objects in preference order.
    The resolver picks the highest-priority source whose ``published_date``
    is on or before ``snapshot_date``.

    Usage::

        resolver = TrialPhaseResolver()
        result = resolver.resolve(
            asset_id="DB-OTO",
            snapshot_date=date(2023, 5, 9),
            sources=[
                TrialPhaseSource(
                    source_type=TrialPhaseSourceType.PRESS_RELEASE,
                    phase="phase_1_2",
                    published_date=date(2023, 4, 15),
                    source_url="https://investor.decibel.com/...",
                ),
                TrialPhaseSource(
                    source_type=TrialPhaseSourceType.CLINICALTRIALS_CURRENT,
                    phase="phase_2",
                    published_date=date(2023, 9, 10),   # AFTER snapshot
                ),
            ],
        )
        # result.resolved_phase == "phase_1_2"
        # result.source_type == TrialPhaseSourceType.PRESS_RELEASE
    """

    _NEAR_SNAPSHOT_DAYS = 30

    def resolve(
        self,
        asset_id: str,
        snapshot_date: date,
        sources: list[TrialPhaseSource],
    ) -> TrialPhaseResult:
        """Pick the best pre-snapshot phase source."""
        pre_snapshot: list[TrialPhaseSource] = []
        post_snapshot: list[TrialPhaseSource] = []

        for src in sources:
            if src.published_date is None:
                src.is_pre_snapshot = False
                post_snapshot.append(src)
                continue
            if src.published_date <= snapshot_date:
                src.is_pre_snapshot = True
                pre_snapshot.append(src)
            else:
                src.is_pre_snapshot = False
                post_snapshot.append(src)

        # Sort pre-snapshot by source priority then by recency (most recent first)
        def priority_key(s: TrialPhaseSource) -> tuple[int, date]:
            pri = _SOURCE_PRIORITY.index(s.source_type) if s.source_type in _SOURCE_PRIORITY else 99
            published = s.published_date or date.min
            return (pri, -published.toordinal())

        pre_snapshot.sort(key=priority_key)

        near_risk = any(
            s.published_date is not None
            and 0 < (s.published_date - snapshot_date).days <= self._NEAR_SNAPSHOT_DAYS
            for s in post_snapshot
        )

        if pre_snapshot:
            best = pre_snapshot[0]
            return TrialPhaseResult(
                asset_id=asset_id,
                snapshot_date=snapshot_date,
                resolved_phase=best.phase,
                source_type=best.source_type,
                source_url=best.source_url,
                published_date=best.published_date,
                is_pre_snapshot=True,
                near_snapshot_update_risk=near_risk,
                point_in_time_status=best.source_type.value,
                all_sources_checked=sources,
            )

        # No pre-snapshot source — check if CT.gov current is right post-snapshot
        if post_snapshot:
            return TrialPhaseResult(
                asset_id=asset_id,
                snapshot_date=snapshot_date,
                resolved_phase=None,
                source_type=TrialPhaseSourceType.REJECTED_POST_SNAPSHOT,
                source_url="",
                published_date=None,
                is_pre_snapshot=False,
                near_snapshot_update_risk=near_risk,
                point_in_time_status=TrialPhaseSourceType.REJECTED_POST_SNAPSHOT.value,
                all_sources_checked=sources,
            )

        return TrialPhaseResult(
            asset_id=asset_id,
            snapshot_date=snapshot_date,
            resolved_phase=None,
            source_type=TrialPhaseSourceType.UNKNOWN,
            source_url="",
            published_date=None,
            is_pre_snapshot=False,
            near_snapshot_update_risk=False,
            point_in_time_status=TrialPhaseSourceType.UNKNOWN.value,
            all_sources_checked=sources,
        )


# ---------------------------------------------------------------------------
# Audit CSV writer
# ---------------------------------------------------------------------------

def write_clinicaltrials_pit_audit(
    results: list[TrialPhaseResult],
    output_path: "str | Any",
) -> "Any":
    """Write a point-in-time audit CSV for all resolved phase results."""
    import csv
    from pathlib import Path
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "asset_id", "snapshot_date", "resolved_phase", "source_type",
        "source_url", "published_date", "is_pre_snapshot",
        "near_snapshot_update_risk", "point_in_time_status", "is_trustworthy",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "asset_id": r.asset_id,
                "snapshot_date": r.snapshot_date.isoformat(),
                "resolved_phase": r.resolved_phase or "",
                "source_type": r.source_type.value,
                "source_url": r.source_url,
                "published_date": r.published_date.isoformat() if r.published_date else "",
                "is_pre_snapshot": r.is_pre_snapshot,
                "near_snapshot_update_risk": r.near_snapshot_update_risk,
                "point_in_time_status": r.point_in_time_status,
                "is_trustworthy": r.is_trustworthy,
            })
    return output_path

"""ClinicalTrials.gov trial diff — compare stored trial records vs. live CT.gov status.

Fetches the current trial status from ClinicalTrials.gov for a list of NCT IDs
and compares against stored records. Differences are emitted as structured
``TrialChange`` objects.

Change types
------------
``"status_change"``      — OverallStatus differs (e.g. RECRUITING → COMPLETED)
``"phase_change"``       — Phase differs
``"enrollment_change"``  — Enrollment count changed by ≥ 20%
``"title_change"``       — Brief title changed
``"not_found"``          — NCT ID no longer exists in CT.gov
``"new_data"``           — NCT ID found when no stored record existed

Design notes
------------
- ``TrialDiffResult`` is a pure data container.
- ``run_trial_diff`` accepts an injectable ``fetcher`` for unit-testable code.
- All CT.gov network calls are optional: when ``fetcher`` returns ``None`` for
  an NCT ID, the NCT ID is skipped rather than raising.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional


# ---------------------------------------------------------------------------
# Change container
# ---------------------------------------------------------------------------

@dataclass
class TrialChange:
    """One detected change for a single trial.

    Parameters
    ----------
    nct_id:
        ClinicalTrials.gov identifier.
    change_type:
        Category of change (see module docstring).
    field_name:
        Which field changed.
    old_value:
        Previously stored value.
    new_value:
        Currently observed value from CT.gov.
    severity:
        ``"high"`` — status/phase change; ``"medium"`` — enrollment; ``"low"`` — title
    alert_text:
        Pre-formatted alert string for reports.
    """

    nct_id: str
    change_type: str
    field_name: str
    old_value: Any
    new_value: Any
    severity: str = "medium"
    alert_text: str = ""

    def to_dict(self) -> dict:
        return {
            "nct_id": self.nct_id,
            "change_type": self.change_type,
            "field_name": self.field_name,
            "old_value": str(self.old_value) if self.old_value is not None else None,
            "new_value": str(self.new_value) if self.new_value is not None else None,
            "severity": self.severity,
            "alert_text": self.alert_text,
        }


# ---------------------------------------------------------------------------
# Aggregate diff result
# ---------------------------------------------------------------------------

@dataclass
class TrialDiffResult:
    """Aggregated diff result across all compared trials.

    Parameters
    ----------
    changes:
        All detected ``TrialChange`` objects.
    n_compared:
        Total NCT IDs compared.
    n_changed:
        Count of NCT IDs with at least one change.
    n_not_found:
        Count of NCT IDs that returned no result from CT.gov.
    run_date:
        Date the diff was run.
    """

    changes: list[TrialChange] = field(default_factory=list)
    n_compared: int = 0
    n_changed: int = 0
    n_not_found: int = 0
    run_date: Optional[date] = None

    @property
    def high_severity_changes(self) -> list[TrialChange]:
        return [c for c in self.changes if c.severity == "high"]

    def to_dict(self) -> dict:
        return {
            "run_date": self.run_date.isoformat() if self.run_date else None,
            "n_compared": self.n_compared,
            "n_changed": self.n_changed,
            "n_not_found": self.n_not_found,
            "n_high_severity": len(self.high_severity_changes),
            "changes": [c.to_dict() for c in self.changes],
        }


# ---------------------------------------------------------------------------
# Stored record container
# ---------------------------------------------------------------------------

@dataclass
class StoredTrialRecord:
    """Minimal stored trial record to diff against.

    Callers can build this from a YAML config, a database row, or a
    ``ClinicalTrial`` entity.

    Parameters
    ----------
    nct_id:
        ClinicalTrials.gov identifier.
    status:
        Stored overall status string (e.g. ``"RECRUITING"``).
    phase:
        Stored phase string (e.g. ``"PHASE2"``).
    enrollment:
        Stored enrollment count (actual or estimated).
    title:
        Stored brief title.
    """

    nct_id: str
    status: Optional[str] = None
    phase: Optional[str] = None
    enrollment: Optional[int] = None
    title: Optional[str] = None


# ---------------------------------------------------------------------------
# Default fetcher (ClinicalTrials.gov API)
# ---------------------------------------------------------------------------

def _ctgov_fetcher(nct_id: str) -> Optional[dict]:
    """Default live fetcher using the CT.gov v2 REST API."""
    try:
        from bve.ingestion.clinicaltrials_gov import fetch_study
        data = fetch_study(nct_id)
        return data if data else None
    except Exception:
        return None


def _extract_fields(raw_protocol: dict) -> dict:
    """Extract comparable fields from a raw CT.gov protocol section."""
    status_module = raw_protocol.get("statusModule") or {}
    design_module = raw_protocol.get("designModule") or {}
    id_module = raw_protocol.get("identificationModule") or {}

    status = status_module.get("overallStatus")
    phases = design_module.get("phases") or []
    phase = phases[0] if phases else None
    enrollment = None
    enrollment_info = design_module.get("enrollmentInfo") or {}
    if enrollment_info.get("count"):
        try:
            enrollment = int(enrollment_info["count"])
        except (ValueError, TypeError):
            pass
    title = id_module.get("briefTitle")

    return {
        "status": status,
        "phase": phase,
        "enrollment": enrollment,
        "title": title,
    }


# ---------------------------------------------------------------------------
# Main diff function
# ---------------------------------------------------------------------------

def run_trial_diff(
    stored_records: list[StoredTrialRecord],
    *,
    fetcher: Optional[Callable[[str], Optional[dict]]] = None,
    run_date: Optional[date] = None,
    enrollment_change_threshold: float = 0.20,
) -> TrialDiffResult:
    """Compare stored trial records against current CT.gov status.

    Parameters
    ----------
    stored_records:
        List of ``StoredTrialRecord`` objects representing the current
        known state of each trial.
    fetcher:
        Callable ``(nct_id) → dict | None`` returning a raw CT.gov
        protocolSection dict. Defaults to the live CT.gov API.
    run_date:
        Date to stamp on the result; defaults to today.
    enrollment_change_threshold:
        Fraction change in enrollment that triggers an ``"enrollment_change"``
        alert (default 0.20 = 20%).

    Returns
    -------
    TrialDiffResult
    """
    fn = fetcher or _ctgov_fetcher
    ref = run_date or date.today()
    all_changes: list[TrialChange] = []
    changed_nct_ids: set[str] = set()
    n_not_found = 0

    for record in stored_records:
        nct_id = record.nct_id
        live_raw = fn(nct_id)

        if live_raw is None:
            n_not_found += 1
            change = TrialChange(
                nct_id=nct_id,
                change_type="not_found",
                field_name="nct_id",
                old_value=nct_id,
                new_value=None,
                severity="high",
                alert_text=f"Trial {nct_id} no longer found in ClinicalTrials.gov",
            )
            all_changes.append(change)
            changed_nct_ids.add(nct_id)
            continue

        live = _extract_fields(live_raw)
        trial_changes = _compare_trial(
            record, live, enrollment_change_threshold=enrollment_change_threshold
        )
        if trial_changes:
            all_changes.extend(trial_changes)
            changed_nct_ids.add(nct_id)

    return TrialDiffResult(
        changes=all_changes,
        n_compared=len(stored_records),
        n_changed=len(changed_nct_ids),
        n_not_found=n_not_found,
        run_date=ref,
    )


def _compare_trial(
    stored: StoredTrialRecord,
    live: dict,
    enrollment_change_threshold: float,
) -> list[TrialChange]:
    """Return list of changes between stored and live trial data."""
    changes: list[TrialChange] = []
    nct_id = stored.nct_id

    # Status
    live_status = live.get("status")
    if stored.status and live_status and stored.status != live_status:
        changes.append(
            TrialChange(
                nct_id=nct_id,
                change_type="status_change",
                field_name="overall_status",
                old_value=stored.status,
                new_value=live_status,
                severity="high",
                alert_text=(
                    f"Trial {nct_id} status changed: {stored.status} → {live_status}"
                ),
            )
        )

    # Phase
    live_phase = live.get("phase")
    if stored.phase and live_phase and stored.phase != live_phase:
        changes.append(
            TrialChange(
                nct_id=nct_id,
                change_type="phase_change",
                field_name="phase",
                old_value=stored.phase,
                new_value=live_phase,
                severity="high",
                alert_text=(
                    f"Trial {nct_id} phase changed: {stored.phase} → {live_phase}"
                ),
            )
        )

    # Enrollment
    live_enrollment = live.get("enrollment")
    if (
        stored.enrollment is not None
        and live_enrollment is not None
        and stored.enrollment > 0
    ):
        frac_change = abs(live_enrollment - stored.enrollment) / stored.enrollment
        if frac_change >= enrollment_change_threshold:
            changes.append(
                TrialChange(
                    nct_id=nct_id,
                    change_type="enrollment_change",
                    field_name="enrollment",
                    old_value=stored.enrollment,
                    new_value=live_enrollment,
                    severity="medium",
                    alert_text=(
                        f"Trial {nct_id} enrollment changed: "
                        f"{stored.enrollment} → {live_enrollment} "
                        f"({frac_change:+.0%})"
                    ),
                )
            )

    # Title
    live_title = live.get("title")
    if stored.title and live_title and stored.title != live_title:
        changes.append(
            TrialChange(
                nct_id=nct_id,
                change_type="title_change",
                field_name="brief_title",
                old_value=stored.title,
                new_value=live_title,
                severity="low",
                alert_text=f"Trial {nct_id} title changed",
            )
        )

    return changes


def build_stored_records_from_trials(trials: list) -> list[StoredTrialRecord]:
    """Build StoredTrialRecord objects from ClinicalTrial entity objects.

    Parameters
    ----------
    trials:
        List of ``bve.entities.trial.ClinicalTrial`` objects (or duck-typed).

    Returns
    -------
    list[StoredTrialRecord]
        Only trials with a valid nct_id are included.
    """
    records: list[StoredTrialRecord] = []
    for trial in trials:
        nct_id = getattr(trial, "nct_id", None)
        if not nct_id:
            continue
        status = getattr(trial, "status", None)
        status_str = status.value if hasattr(status, "value") else str(status) if status else None
        phase = getattr(trial, "phase", None)
        phase_str = phase.value if hasattr(phase, "value") else str(phase) if phase else None
        records.append(
            StoredTrialRecord(
                nct_id=str(nct_id),
                status=status_str,
                phase=phase_str,
                enrollment=getattr(trial, "enrollment", None),
                title=getattr(trial, "title", None),
            )
        )
    return records


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_trial_diff(result: TrialDiffResult) -> str:
    """Render a TrialDiffResult as a compact Markdown section."""
    na = "Not available"
    run_str = result.run_date.isoformat() if result.run_date else na

    lines = [
        "### ClinicalTrials.gov Diff",
        "",
        f"**Run date:** {run_str}  |  "
        f"**Compared:** {result.n_compared}  |  "
        f"**Changed:** {result.n_changed}  |  "
        f"**Not found:** {result.n_not_found}",
        "",
    ]

    if not result.changes:
        lines += ["_No trial changes detected._", ""]
        return "\n".join(lines)

    high = result.high_severity_changes
    if high:
        lines += [f"**{len(high)} high-severity change(s):**", ""]
        for c in high:
            lines.append(f"- ✗ {c.alert_text}")
        lines.append("")

    other = [c for c in result.changes if c.severity != "high"]
    if other:
        lines += [f"**{len(other)} other change(s):**", ""]
        for c in other:
            lines.append(f"- ⚠ {c.alert_text}")
        lines.append("")

    return "\n".join(lines)

"""Cluster a sponsor's trials into candidate drug programs.

One investigational drug == one program. Trials are grouped by their primary
investigational drug (the first non-comparator intervention), so a drug studied
across Phase 1 and Phase 3 collapses into a single program carrying the max phase.
Pure functions over ``TrialRecord`` lists — no network.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from bve.discovery.sponsor_trials import TrialRecord

_PHASE_RANK: dict[str, int] = {"phase_1": 1, "phase_2": 2, "phase_3": 3}


def _drug_key(name: str) -> str:
    """Normalize a drug name to a clustering key (lower, strip dose/salt noise)."""
    text = name.lower().strip()
    # Drop common formulation/salt suffixes that fragment the same molecule.
    text = re.sub(
        r"\b(hydrochloride|hcl|sodium|sulfate|mesylate|tablet|tablets|capsule|"
        r"capsules|injection|oral|iv|for injection)\b",
        " ",
        text,
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _max_phase(trials: list[TrialRecord]) -> Optional[str]:
    phases = [t.phase for t in trials if t.phase]
    if not phases:
        return None
    return max(phases, key=lambda p: _PHASE_RANK[p])


def _latest(values: list[Optional[str]]) -> Optional[str]:
    present = [v for v in values if v]
    return max(present) if present else None


class CandidateProgram(BaseModel, frozen=True):
    """A drug program inferred from one or more trials of the same molecule."""

    drug: str
    drug_key: str
    trials: tuple[TrialRecord, ...]
    max_phase: Optional[str] = None
    n_trials: int = 0
    latest_completion: Optional[str] = None
    enrollment_max: Optional[int] = None
    sponsor_is_lead: bool = False
    conditions: tuple[str, ...] = ()

    @property
    def nct_ids(self) -> tuple[str, ...]:
        return tuple(t.nct_id for t in self.trials)


def cluster_programs(trials: list[TrialRecord]) -> list[CandidateProgram]:
    """Group trials by primary investigational drug → candidate programs.

    Trials with no investigational drug name are skipped (nothing to cluster on).
    Programs are returned sorted by max phase desc, then trial count desc.
    """
    groups: dict[str, list[TrialRecord]] = {}
    display: dict[str, str] = {}
    for t in trials:
        if not t.drug_names:
            continue
        primary = t.drug_names[0]
        key = _drug_key(primary)
        if not key:
            continue
        groups.setdefault(key, []).append(t)
        # Prefer the shortest display name (usually the bare molecule, not a combo).
        if key not in display or len(primary) < len(display[key]):
            display[key] = primary

    programs: list[CandidateProgram] = []
    for key, group in groups.items():
        conditions: list[str] = []
        seen: set[str] = set()
        for t in group:
            for c in t.conditions:
                cl = c.lower()
                if cl not in seen:
                    seen.add(cl)
                    conditions.append(c)
        enrollments = [t.enrollment for t in group if t.enrollment is not None]
        programs.append(CandidateProgram(
            drug=display[key],
            drug_key=key,
            trials=tuple(group),
            max_phase=_max_phase(group),
            n_trials=len(group),
            latest_completion=_latest([t.primary_completion_date for t in group]),
            enrollment_max=max(enrollments) if enrollments else None,
            sponsor_is_lead=any(t.sponsor_is_lead for t in group),
            conditions=tuple(conditions),
        ))

    programs.sort(
        key=lambda p: (_PHASE_RANK.get(p.max_phase or "", 0), p.n_trials),
        reverse=True,
    )
    return programs

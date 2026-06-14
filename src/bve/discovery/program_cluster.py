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

from bve.discovery.drug_identity import canonical_drug_key
from bve.discovery.sponsor_trials import TrialRecord

_PHASE_RANK: dict[str, int] = {"phase_1": 1, "phase_2": 2, "phase_3": 3}
_CODE_TOKEN_RE = re.compile(r"\b[A-Za-z]{2,6}[\s\-'’.]?\d{2,6}\b")


def _trial_variants(trial: TrialRecord) -> list[str]:
    """All name variants for a trial's primary drug (name + CT.gov synonyms)."""
    primary = trial.drug_names[0] if trial.drug_names else ""
    return [primary, *trial.primary_drug_aliases] if primary else []


def _pretty_label(name: str, key: str) -> str:
    """Surface the code name (original case) from a descriptive name when possible."""
    m = _CODE_TOKEN_RE.search(name)
    if m and canonical_drug_key(m.group()) == key:
        return m.group()
    return name.strip()


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
    aliases: tuple[str, ...] = ()  # all distinct name variants (incl. synonyms)
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
    labels: dict[str, list[str]] = {}
    raw_variants: dict[str, list[str]] = {}
    for t in trials:
        variants = _trial_variants(t)
        if not variants:
            continue
        key = canonical_drug_key(*variants)
        if not key:
            continue
        groups.setdefault(key, []).append(t)
        labels.setdefault(key, []).extend(
            _pretty_label(v, key) for v in variants if v
        )
        raw_variants.setdefault(key, []).extend(v for v in variants if v)

    # Display name = shortest code-surfaced label across the group's variants.
    display = {
        key: min(set(lbls), key=len) if lbls else key
        for key, lbls in labels.items()
    }

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
            aliases=tuple(dict.fromkeys(raw_variants[key])),
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

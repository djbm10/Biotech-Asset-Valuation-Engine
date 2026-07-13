"""Rank candidate programs to pick a company's likely lead asset.

Transparent additive heuristic — every weight is a module constant and every
program carries its score breakdown, so the backtest can calibrate thresholds and
a human can see *why* a lead was chosen. The tier (high/medium/low) is driven by
the margin between the top two programs plus single-program clarity; those
thresholds are exactly what the 50-seed backtest exists to calibrate.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from bve.discovery.program_cluster import CandidateProgram

# ── Scoring weights (evidence-informed priors; calibrated by the backtest) ──────
_PHASE_SCORE: dict[str, float] = {"phase_3": 1.0, "phase_2": 0.6, "phase_1": 0.3}
_PHASE_SCORE_NONE = 0.1

W_PHASE = 1.0            # dominant term
W_REGISTRATIONAL = 0.25  # pivotal-size enrollment / pivotal keywords
W_SPONSOR_LEAD = 0.20    # company is the lead sponsor (not a collaborator)
W_ACTIVITY = 0.15        # stage-aware liveness (active early / completed-pivotal late)
W_CORROBORATION = 0.10   # multiple trials on the same molecule (diminishing)
W_DEAD_PENALTY = 0.40    # program with only terminated/withdrawn trials is not a lead

# Pivotal-size enrollment thresholds by phase.
_PIVOTAL_ENROLL = {"phase_3": 300, "phase_2": 100}
_PIVOTAL_TITLE_RE = re.compile(
    r"\b(pivotal|registrational|phase 3|phase iii|confirmatory|"
    r"nda|bla|marketing auth)\b", re.I
)
_ACTIVE_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}
# A completed/marketed trial is a positive late-stage signal, not a dead one — a
# Phase 3 program whose pivotal trial has read out has graduated, not stalled.
_COMPLETED_STATUSES = {"COMPLETED", "APPROVED_FOR_MARKETING"}
# Trial statuses that mean the program stopped (vs. progressed).
_DEAD_STATUSES = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}

# Tier thresholds (margin between #1 and #2). Calibrated by the backtest sweep.
HIGH_MARGIN = 0.15
MED_MARGIN = 0.08


class RankedLead(BaseModel, frozen=True):
    """The chosen lead program plus its score, margin, and confidence tier."""

    program: CandidateProgram
    score: float
    components: dict[str, float]
    runner_up_score: float = 0.0
    margin: float = 0.0
    confidence: float = 0.0
    tier: str = "low"  # high | medium | low


def _registrational_signal(program: CandidateProgram) -> float:
    threshold = _PIVOTAL_ENROLL.get(program.max_phase or "")
    if threshold and program.enrollment_max and program.enrollment_max >= threshold:
        return 1.0
    if any(_PIVOTAL_TITLE_RE.search(t.title or "") for t in program.trials):
        return 0.6
    return 0.0


def _activity_signal(program: CandidateProgram) -> float:
    """Stage-aware liveness in [0, 1].

    Recency should mean different things at different stages:
    - early-stage (Phase 1/2): an actively recruiting/running trial is the signal
      that the program is alive and advancing.
    - late-stage (Phase 3): the pivotal trial having *completed* (read out) is an
      equally strong signal — a marketed or filed asset whose registrational
      trial is COMPLETED has graduated, not stalled, so it should not be
      penalized relative to a still-recruiting earlier asset.
    """
    statuses = {t.status for t in program.trials}
    if statuses & _ACTIVE_STATUSES:
        return 1.0
    if program.max_phase == "phase_3" and (statuses & _COMPLETED_STATUSES):
        return 1.0
    return 0.0


def _is_dead(program: CandidateProgram) -> bool:
    """True when a program has trials but none are active or completed.

    A drug whose every trial was terminated/withdrawn/suspended is not a viable
    lead, even if it once reached a late phase. Without this, a single
    terminated Phase 3 outscores a live Phase 2.
    """
    statuses = {t.status for t in program.trials}
    if not statuses:
        return False
    return not (statuses & (_ACTIVE_STATUSES | _COMPLETED_STATUSES))


def _corroboration_signal(program: CandidateProgram) -> float:
    # Diminishing: 1 trial → 0.0, 2 → 0.5, 3 → ~0.67, capped at 1.0.
    return min(1.0, (program.n_trials - 1) / 2.0) if program.n_trials > 1 else 0.0


def score_program(program: CandidateProgram) -> tuple[float, dict[str, float]]:
    """Return (total_score, component_breakdown) for one program."""
    phase = _PHASE_SCORE.get(program.max_phase or "", _PHASE_SCORE_NONE)
    components = {
        "phase": round(W_PHASE * phase, 4),
        "registrational": round(W_REGISTRATIONAL * _registrational_signal(program), 4),
        "sponsor_is_lead": round(W_SPONSOR_LEAD * (1.0 if program.sponsor_is_lead else 0.0), 4),
        "activity": round(W_ACTIVITY * _activity_signal(program), 4),
        "corroboration": round(W_CORROBORATION * _corroboration_signal(program), 4),
        "dead_penalty": round(-W_DEAD_PENALTY if _is_dead(program) else 0.0, 4),
    }
    return round(sum(components.values()), 4), components


def _tier(margin: float, n_programs: int, top: CandidateProgram) -> str:
    # A dead lead (only terminated/withdrawn trials) is never high-confidence.
    if _is_dead(top):
        return "low"
    if n_programs == 1:
        # One fetched program is weak evidence, not certainty: it usually means we
        # only retrieved a fragment of the sponsor's pipeline, a collaboration
        # trial, or a single stalled asset. Promote to high only when the company
        # is the lead sponsor of a genuinely late-stage program.
        if top.sponsor_is_lead and top.max_phase == "phase_3":
            return "high"
        if top.sponsor_is_lead:
            return "medium"
        return "low"
    if margin >= HIGH_MARGIN:
        return "high"
    if margin >= MED_MARGIN:
        return "medium"
    return "low"


def rank_leads(programs: list[CandidateProgram]) -> Optional[RankedLead]:
    """Score all programs and return the top one with margin + tier.

    Returns None when there are no programs to rank.
    """
    if not programs:
        return None

    scored = [(p, *score_program(p)) for p in programs]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_program, top_score, components = scored[0]
    # Margin only means something when there is a runner-up to separate from; for
    # a single program it would equal the raw score, which is not a confidence
    # signal, so it is pinned to 0 and the tier is decided on program quality.
    if len(programs) > 1:
        runner_up = scored[1][1]
        margin = round(top_score - runner_up, 4)
    else:
        runner_up = 0.0
        margin = 0.0
    tier = _tier(margin, len(programs), top_program)
    confidence = round(min(1.0, margin / HIGH_MARGIN), 4) if HIGH_MARGIN else 0.0

    return RankedLead(
        program=top_program,
        score=top_score,
        components=components,
        runner_up_score=runner_up,
        margin=margin,
        confidence=confidence,
        tier=tier,
    )

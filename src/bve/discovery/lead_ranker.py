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
W_RECENCY = 0.15         # actively running
W_CORROBORATION = 0.10   # multiple trials on the same molecule (diminishing)

# Pivotal-size enrollment thresholds by phase.
_PIVOTAL_ENROLL = {"phase_3": 300, "phase_2": 100}
_PIVOTAL_TITLE_RE = re.compile(
    r"\b(pivotal|registrational|phase 3|phase iii|confirmatory)\b", re.I
)
_ACTIVE_STATUSES = {"RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}

# Tier thresholds (margin between #1 and #2). Calibrated by the backtest sweep.
HIGH_MARGIN = 0.20
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


def _recency_signal(program: CandidateProgram) -> float:
    return 1.0 if any(t.status in _ACTIVE_STATUSES for t in program.trials) else 0.0


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
        "recency": round(W_RECENCY * _recency_signal(program), 4),
        "corroboration": round(W_CORROBORATION * _corroboration_signal(program), 4),
    }
    return round(sum(components.values()), 4), components


def _tier(margin: float, n_programs: int) -> str:
    if n_programs == 1:
        return "high"  # unambiguous: only one program
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
    runner_up = scored[1][1] if len(scored) > 1 else 0.0
    margin = round(top_score - runner_up, 4)
    tier = _tier(margin, len(programs))
    # Confidence: blend normalized margin with single-program clarity.
    confidence = 1.0 if len(programs) == 1 else round(min(1.0, margin / HIGH_MARGIN), 4)

    return RankedLead(
        program=top_program,
        score=top_score,
        components=components,
        runner_up_score=runner_up,
        margin=margin,
        confidence=confidence,
        tier=tier,
    )

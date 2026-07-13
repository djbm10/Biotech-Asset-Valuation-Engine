"""Killer-Question engine (Batch A) — the model's proposed *diligence agenda*.

For each asset this surfaces the 1–2 questions whose resolution actually decides
the asset, ranked by value-of-information (VOI), with explicit safeguards:
ranked candidates (not just a winner), abstention when no question dominates,
a per-question confidence, and a company-focus cross-check. The set is never
asserted as truth — it is the agenda a human reviews and can override.

OWNERSHIP BOUNDARY (critical — see docs/killer_question_build_plan.md §0)
------------------------------------------------------------------------
This module *reads* the science objects and never writes back:

    ScienceScoredQuestions  (T/D/B)   -> positive science score   [read-only]
    ScienceContext          (H/M)     -> non-scored context       [read-only]
    ScienceGuardrail        (S/kills) -> downside-only guardrails  [read-only]

H / M / S may be elevated to a *decisive diligence question* here, but they are
NEVER reintroduced as positive components of the science modifier. POS/calibration
is downstream-isolated: running ``derive_killer_questions`` cannot change
``compute_science_modifier`` output.

VOI valuation reuses ``compute_rnpv_full`` — the confirmed/refuted branches are
two runs with the governing phase's success probability forced high vs ~0. The
VOI uses the *spread* between branches, not the absolute rNPV, which cancels much
of the far-out assumption noise the rNPV point estimate carries.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Protocol

from pydantic import BaseModel, ConfigDict, Field

from bve.config.meaningfulness_bars import MeaningfulnessBars
from bve.intelligence.science_thesis import (
    ClinicalMeaningfulnessContext,
    EvidenceResolution,
    EvidenceResolutionBasis,
    ScienceContext,
    ScienceGuardrail,
    ScienceQuestion,
    ScienceScoredQuestions,
)


# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------

class KillerArchetype(str, Enum):
    TARGET_VALIDITY = "target_validity"
    DELIVERY_EXPOSURE = "delivery_exposure"
    DOSE_ADEQUACY = "dose_adequacy"
    DIFFERENTIATION = "differentiation"
    TOLERABILITY_CEILING = "tolerability_ceiling"
    NOVEL_OR_UNMODELED_RISK = "novel_or_unmodeled_risk"


# Read-only mapping: archetype -> the source ScienceQuestion it reads from, so
# there is one source of truth. Delivery + dose both read ENOUGH_DRUG in v1 but
# keep distinct labels (dose adequacy is often the real Harvey-style question).
ARCHETYPE_SOURCE: dict[KillerArchetype, Optional[ScienceQuestion]] = {
    KillerArchetype.TARGET_VALIDITY: ScienceQuestion.RIGHT_TARGET,
    KillerArchetype.DELIVERY_EXPOSURE: ScienceQuestion.ENOUGH_DRUG,
    KillerArchetype.DOSE_ADEQUACY: ScienceQuestion.ENOUGH_DRUG,
    KillerArchetype.DIFFERENTIATION: ScienceQuestion.CLINICAL_MEANINGFULNESS,
    KillerArchetype.TOLERABILITY_CEILING: ScienceQuestion.SAFETY_MARGIN,
    KillerArchetype.NOVEL_OR_UNMODELED_RISK: None,
}


# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------

class KillerQuestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    archetype: KillerArchetype
    question_text: str
    is_live: bool = True
    value_if_confirmed_m: float = 0.0
    value_if_refuted_m: float = 0.0
    swing_m: float = 0.0
    voi_score: float = Field(default=0.0, ge=0.0, le=1.0)
    openness: float = Field(default=1.0, ge=0.0, le=1.0)
    posterior: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    resolving_readout: str = ""
    evidence_touched: EvidenceResolution = EvidenceResolution.UNRESOLVED
    diligence_question: str = ""
    why_fired: str = ""
    flags: list[str] = Field(default_factory=list)


class KillerQuestionSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidates: list[KillerQuestion] = Field(default_factory=list)
    decisive: list[KillerQuestion] = Field(default_factory=list)
    abstained: bool = False
    abstain_reason: str = ""
    company_focus_mismatch: Optional[str] = None

    def decisive_question(self) -> Optional[KillerQuestion]:
        return self.decisive[0] if self.decisive else None


# ---------------------------------------------------------------------------
# VOI branch valuator
# ---------------------------------------------------------------------------

class BranchValuator(Protocol):
    """Returns (rNPV_if_confirmed_m, rNPV_if_refuted_m) for a question's branch."""

    def value(self, archetype: KillerArchetype) -> tuple[float, float]: ...


class RnpvBranchValuator:
    """Default VOI valuator built on ``compute_rnpv_full``.

    Confirmed branch forces the governing phase's success_probability to 1.0;
    refuted branch forces it to ~0 (an epsilon, since the field is ``gt=0``).
    DIFFERENTIATION governs the pivotal (latest) phase; every other archetype
    governs the earliest phase still carrying risk (the next gate).
    """

    _EPS_FAIL = 1e-6  # success_probability is gt=0.0; cannot be exactly zero

    def __init__(self, asset, trials, market_model, *, deal=None) -> None:
        self._asset = asset
        self._trials: list = list(trials or [])
        self._market = market_model
        self._deal = deal
        self._cache: dict[int, tuple[float, float]] = {}

    def _governing_index(self, archetype: KillerArchetype) -> Optional[int]:
        if not self._trials:
            return None
        ordered = sorted(range(len(self._trials)), key=lambda i: self._trials[i].phase_order)
        if archetype == KillerArchetype.DIFFERENTIATION:
            return ordered[-1]
        for i in ordered:
            if self._trials[i].success_probability < 1.0:
                return i
        return ordered[0]

    def value(self, archetype: KillerArchetype) -> tuple[float, float]:
        idx = self._governing_index(archetype)
        if idx is None or self._asset is None or self._market is None:
            return (0.0, 0.0)
        if idx in self._cache:
            return self._cache[idx]
        from bve.models.rnpv_model import compute_rnpv_full

        confirmed = list(self._trials)
        refuted = list(self._trials)
        confirmed[idx] = self._trials[idx].model_copy(update={"success_probability": 1.0})
        refuted[idx] = self._trials[idx].model_copy(
            update={"success_probability": self._EPS_FAIL}
        )
        c = compute_rnpv_full(self._asset, confirmed, self._market, deal=self._deal).rnpv_millions
        r = compute_rnpv_full(self._asset, refuted, self._market, deal=self._deal).rnpv_millions
        self._cache[idx] = (float(c), float(r))
        return self._cache[idx]


# ---------------------------------------------------------------------------
# Selection constants
# ---------------------------------------------------------------------------

_OPENNESS: dict[EvidenceResolution, float] = {
    EvidenceResolution.UNRESOLVED: 1.0,
    EvidenceResolution.PARTIALLY_RESOLVED: 0.5,
    EvidenceResolution.RESOLVED: 0.0,
    EvidenceResolution.REFUTED: 0.0,
}

_DOSE_RESPONSE_BASES = {
    EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE,
    EvidenceResolutionBasis.HUMAN_EXPOSURE_RESPONSE,
}
# The dose-response raise is no longer a hardcoded posterior bump; it is a log-odds
# EvidenceUpdate applied downstream (see conviction_update.apply_dose_response_conviction).
_BAR_NOISE_TOLERANCE = 0.05  # within 5% of the bar is "noise / clears"

# Default selection thresholds.
DEFAULT_DOMINANCE_MARGIN = 0.15   # top must clear the pack by this, else abstain
DEFAULT_CO_DECISIVE_MARGIN = 0.10  # a near-tied #2 is co-decisive


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------------------
# Candidate builders (one per archetype) — all READ-ONLY over science objects
# ---------------------------------------------------------------------------

def _draft(
    archetype: KillerArchetype,
    *,
    question_text: str,
    openness: float,
    posterior: float,
    confidence: float,
    evidence_touched: EvidenceResolution,
    resolving_readout: str,
    diligence_question: str,
    why_fired: str,
    flags: Optional[list[str]] = None,
) -> KillerQuestion:
    return KillerQuestion(
        archetype=archetype,
        question_text=question_text,
        is_live=True,
        openness=_clamp01(openness),
        posterior=_clamp01(posterior),
        confidence=_clamp01(confidence),
        evidence_touched=evidence_touched,
        resolving_readout=resolving_readout,
        diligence_question=diligence_question,
        why_fired=why_fired,
        flags=flags or [],
    )


def _target_validity(
    scored: ScienceScoredQuestions, guardrail: ScienceGuardrail, target_has_precedent: bool
) -> Optional[KillerQuestion]:
    comp = scored.right_target
    if target_has_precedent or guardrail.target_refuted:
        return None
    if comp.resolution not in (EvidenceResolution.UNRESOLVED, EvidenceResolution.PARTIALLY_RESOLVED):
        return None
    return _draft(
        KillerArchetype.TARGET_VALIDITY,
        question_text="Is the target causally linked to the disease?",
        openness=_OPENNESS.get(comp.resolution, 1.0),
        posterior=comp.score,
        confidence=comp.confidence,
        evidence_touched=comp.resolution,
        resolving_readout="Genetic association + clinical validation that the target modifies the disease",
        diligence_question="Is there genetic + clinical evidence the target drives this disease?",
        why_fired="Novel/unvalidated target — disease linkage not yet established.",
    )


# ENOUGH_DRUG splits into two mutually-exclusive archetype labels by evidence
# stage: before human dosing data it reads as a *delivery* question; once human
# PK/dose data exist it reads as a *dose-adequacy* question. Mutual exclusion
# avoids the two labels tying on the same component.
_DELIVERY_BASES = {
    EvidenceResolutionBasis.UNSPECIFIED,
    EvidenceResolutionBasis.PRECLINICAL,
}
_DOSE_BASES = {
    EvidenceResolutionBasis.HUMAN_PKPD,
    EvidenceResolutionBasis.HUMAN_DOSE_RESPONSE,
    EvidenceResolutionBasis.HUMAN_EXPOSURE_RESPONSE,
}


def _delivery_exposure(scored: ScienceScoredQuestions) -> Optional[KillerQuestion]:
    comp = scored.enough_drug
    if comp.resolution not in (EvidenceResolution.UNRESOLVED, EvidenceResolution.PARTIALLY_RESOLVED):
        return None
    if comp.resolution_basis not in _DELIVERY_BASES:
        return None
    return _draft(
        KillerArchetype.DELIVERY_EXPOSURE,
        question_text="Can enough drug reach the target tissue?",
        openness=_OPENNESS.get(comp.resolution, 1.0),
        posterior=comp.score,
        confidence=comp.confidence,
        evidence_touched=comp.resolution,
        resolving_readout="Tissue biodistribution / target-site exposure at tolerable dose",
        diligence_question="Does enough drug reach the target tissue at a tolerable dose?",
        why_fired="Delivery to the target compartment is unproven.",
    )


def _dose_adequacy(scored: ScienceScoredQuestions) -> Optional[KillerQuestion]:
    comp = scored.enough_drug
    if comp.resolution not in (EvidenceResolution.UNRESOLVED, EvidenceResolution.PARTIALLY_RESOLVED):
        return None
    # Live once human dosing data exist but engagement isn't yet established.
    if comp.resolution_basis not in _DOSE_BASES:
        return None
    trend = comp.resolution_basis in _DOSE_RESPONSE_BASES
    # Base posterior is the raw component score. The dose-response *raise* is applied
    # downstream by the Conviction Update Layer (apply_dose_response_conviction), so it
    # is a principled, auditable log-odds update rather than a hardcoded +0.10 bump.
    posterior = comp.score
    flags = ["dose_response_trend"] if trend else []
    why = (
        "Dose-response trend seen — engagement plausible but not confirmed."
        if trend
        else "Regimen may not suppress the pathway enough; no human dose-response yet."
    )
    return _draft(
        KillerArchetype.DOSE_ADEQUACY,
        question_text="Is the dose/interval enough to suppress the pathway?",
        openness=_OPENNESS.get(comp.resolution, 1.0),
        posterior=posterior,
        confidence=comp.confidence,
        evidence_touched=comp.resolution,
        resolving_readout="Dose-response across >=2 dose levels showing target engagement",
        diligence_question="Is the dose/interval enough to suppress the pathway to the needed level?",
        why_fired=why,
        flags=flags,
    )


def _differentiation(
    context: ScienceContext, indication: Optional[str], claimed_effect: Optional[float]
) -> Optional[KillerQuestion]:
    # Only a live differentiation question when there is an actual claimed effect
    # to test against the bar — otherwise it would fire as noise on every asset.
    if claimed_effect is None:
        return None
    cm: ClinicalMeaningfulnessContext = context.clinical_meaningfulness
    bar = cm.clinically_meaningful_delta
    if bar is None:
        bar = MeaningfulnessBars.get().delta(indication)

    flags: list[str] = []
    if bar is None:
        posterior = 0.5
        flags.append("unknown_bar")
        why = f"Claimed effect {claimed_effect} known but no disease bar to judge it against."
    else:
        if claimed_effect >= bar * (1.0 - _BAR_NOISE_TOLERANCE):
            return None  # clears the bar (or within noise) — not a live killer question
        posterior = _clamp01(claimed_effect / bar if bar else 0.0)
        flags.append("below_bar")
        why = f"Claimed effect {claimed_effect} below the meaningful bar {bar}."
    unit = cm.standard_of_care_context or (MeaningfulnessBars.get().bar(indication).get("unit", ""))
    return _draft(
        KillerArchetype.DIFFERENTIATION,
        question_text="Is the effect clinically meaningful vs the disease bar?",
        openness=1.0,
        posterior=posterior,
        confidence=0.4,
        evidence_touched=EvidenceResolution.UNRESOLVED,
        resolving_readout=f"Pivotal effect size vs the bar ({bar} {unit})".strip(),
        diligence_question=f"Does the effect clear the clinically-meaningful bar ({bar} {unit})?".strip(),
        why_fired=why,
        flags=flags,
    )


def _tolerability_ceiling(guardrail: ScienceGuardrail) -> Optional[KillerQuestion]:
    if not (guardrail.manageable_safety_concern or guardrail.mechanism_linked_severe_safety):
        return None
    severe = guardrail.mechanism_linked_severe_safety
    return _draft(
        KillerArchetype.TOLERABILITY_CEILING,
        question_text="Does an on/off-target tox cap developability?",
        openness=1.0 if severe else 0.5,
        posterior=0.4 if severe else 0.6,
        confidence=0.4,
        evidence_touched=EvidenceResolution.UNRESOLVED,
        resolving_readout="On/off-target tissue safety; tolerability/adherence at efficacious dose",
        diligence_question="Is there an on/off-target tox or tolerability issue that kills developability?",
        why_fired=(
            "Mechanism-linked severe safety risk is open."
            if severe
            else "A manageable but unresolved safety/tolerability concern is open."
        ),
    )


def _novel(novel_question: Optional[str]) -> Optional[KillerQuestion]:
    if not novel_question:
        return None
    return _draft(
        KillerArchetype.NOVEL_OR_UNMODELED_RISK,
        question_text=novel_question,
        openness=1.0,
        posterior=0.5,
        confidence=0.4,
        evidence_touched=EvidenceResolution.UNRESOLVED,
        resolving_readout="(analyst/LLM-specified)",
        diligence_question=novel_question,
        why_fired="Asset-specific risk not captured by the standard archetypes (escape hatch).",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def derive_killer_questions(
    asset=None,
    trials=None,
    market_model=None,
    scored: Optional[ScienceScoredQuestions] = None,
    *,
    context: Optional[ScienceContext] = None,
    guardrail: Optional[ScienceGuardrail] = None,
    deal=None,
    indication: Optional[str] = None,
    claimed_effect: Optional[float] = None,
    target_has_precedent: bool = False,
    novel_question: Optional[str] = None,
    company_focus: Optional[KillerArchetype] = None,
    branch_valuator: Optional[BranchValuator] = None,
    dominance_margin: float = DEFAULT_DOMINANCE_MARGIN,
    co_decisive_margin: float = DEFAULT_CO_DECISIVE_MARGIN,
) -> KillerQuestionSet:
    """Derive the ranked killer-question set for an asset.

    All science inputs are read-only; this never writes back into the science
    score or POS. When ``branch_valuator`` is omitted and a full asset/trials/
    market are provided, a :class:`RnpvBranchValuator` is built; otherwise VOI
    falls back to openness-only ranking (neutral swing), which keeps the engine
    usable when only science objects are available.
    """
    scored = scored or ScienceScoredQuestions()
    context = context or ScienceContext()
    guardrail = guardrail or ScienceGuardrail()

    # Stage 1 — liveness: build the live candidates (read-only over science objects).
    drafts: list[KillerQuestion] = []
    for candidate in (
        _target_validity(scored, guardrail, target_has_precedent),
        _delivery_exposure(scored),
        _dose_adequacy(scored),
        _differentiation(context, indication, claimed_effect),
        _tolerability_ceiling(guardrail),
        _novel(novel_question),
    ):
        if candidate is not None:
            drafts.append(candidate)

    if not drafts:
        return KillerQuestionSet(
            abstained=True,
            abstain_reason="No live killer question — every modeled risk is resolved.",
        )

    # Stage 2 — VOI = normalize(swing) * openness.
    if branch_valuator is None and asset is not None and market_model is not None and trials:
        branch_valuator = RnpvBranchValuator(asset, trials, market_model, deal=deal)

    swings: list[float] = []
    branch_vals: list[tuple[float, float]] = []
    for d in drafts:
        if branch_valuator is not None:
            c, r = branch_valuator.value(d.archetype)
        else:
            c, r = (0.0, 0.0)
        branch_vals.append((c, r))
        swings.append(abs(c - r))

    max_swing = max(swings) if swings else 0.0
    enriched: list[KillerQuestion] = []
    for d, (c, r), swing in zip(drafts, branch_vals, swings):
        # No valuator (or all-zero swings) => openness-only ranking (neutral swing=1).
        norm_swing = (swing / max_swing) if max_swing > 0 else 1.0
        voi = _clamp01(norm_swing * d.openness)
        enriched.append(
            d.model_copy(
                update={
                    "value_if_confirmed_m": round(c, 1),
                    "value_if_refuted_m": round(r, 1),
                    "swing_m": round(swing, 1),
                    "voi_score": round(voi, 4),
                }
            )
        )

    # Stage 3 — rank, select, abstain, cross-check.
    candidates = sorted(enriched, key=lambda q: q.voi_score, reverse=True)[:5]
    top = candidates[0]

    if top.voi_score <= 0.0:
        return KillerQuestionSet(
            candidates=candidates,
            abstained=True,
            abstain_reason="All modeled questions are resolved (no open value at stake).",
        )

    others = candidates[1:]
    dominance = top.voi_score - (sum(q.voi_score for q in others) / len(others)) if others else top.voi_score
    if others and dominance < dominance_margin:
        return KillerQuestionSet(
            candidates=candidates,
            abstained=True,
            abstain_reason=(
                "No dominant killer question — VOI field is flat. Human review required."
            ),
        )

    decisive = [top]
    if others and (top.voi_score - others[0].voi_score) <= co_decisive_margin:
        decisive.append(others[0])

    mismatch: Optional[str] = None
    if company_focus is not None and company_focus not in {q.archetype for q in decisive}:
        mismatch = (
            f"Company de-risking focus ({company_focus.value}) differs from the "
            f"model-selected killer question ({decisive[0].archetype.value}) — "
            "model miss or company dodge; review."
        )

    return KillerQuestionSet(
        candidates=candidates,
        decisive=decisive,
        abstained=False,
        company_focus_mismatch=mismatch,
    )

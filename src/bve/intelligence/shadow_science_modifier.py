"""Shadow science modifier + System 1 <-> System 2 consistency audit (Phase 1 slice).

The live science path (System 1) is ``compute_science_modifier`` — a T/D/B scalar ->
0.70-1.10 multiplier -> POS. This module computes a **shadow** modifier (System 2)
from the claim ledger and *only* produces audit output. It never returns a value that
the POS stack consumes.

NO LIVE POS GATE (hard rule, Execution Discipline point 5): no claim-ledger output may
affect live POS until it has passed shadow-mode calibration, reason-fidelity review,
AND governance approval — all three. This module is the shadow surface; every result
carries ``affects_live_pos = False`` as a machine-checkable assertion of that gate.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.claim_ledger import (
    EXPOSURE_WINDOW_FAMILY,
    ClaimPosterior,
    ClaimType,
    ScienceClaim,
)
from bve.intelligence.killer_question import KillerArchetype

# Killer-question archetype -> claim family, for the exposure/window vertical slice.
# Delivery/exposure is the drug-reaches-target claim; dose adequacy and the
# tolerability ceiling jointly define the therapeutic window (the navitoclax /
# dose-limiting-toxicity class the slice targets).
_ARCHETYPE_TO_CLAIM: dict[KillerArchetype, ClaimType] = {
    KillerArchetype.DELIVERY_EXPOSURE: ClaimType.EXPOSURE_DELIVERY,
    KillerArchetype.DOSE_ADEQUACY: ClaimType.THERAPEUTIC_WINDOW,
    KillerArchetype.TOLERABILITY_CEILING: ClaimType.THERAPEUTIC_WINDOW,
}


class ShadowScienceModifier(BaseModel):
    """Audit-only science modifier derived from the claim ledger.

    Mirrors the *shape* of the live modifier (0.70 + 0.40 * science_score, capped at
    1.10, weakest claim as binding constraint) so the two are comparable — but it is
    explicitly not calibrated and not wired to POS.
    """

    model_config = ConfigDict(frozen=True)

    #: Hard invariant of the NO LIVE POS GATE. Always False in this slice.
    affects_live_pos: bool = False
    calibration_status: str = "shadow_uncalibrated"
    shadow_science_score: float
    shadow_modifier: float
    binding_constraint: float
    binding_claim: Optional[ClaimType] = None
    mean_openness: float
    max_openness: float
    n_claims: int
    warnings: list[str] = Field(default_factory=list)
    rationale: str = ""


def shadow_science_modifier(posteriors: list[ClaimPosterior]) -> ShadowScienceModifier:
    """Combine exposure/window claim posteriors into a shadow (audit-only) modifier."""
    family = [p for p in posteriors if p.claim_type in EXPOSURE_WINDOW_FAMILY]
    warnings: list[str] = []
    if not family:
        return ShadowScienceModifier(
            shadow_science_score=0.5,
            shadow_modifier=0.90,
            binding_constraint=0.5,
            binding_claim=None,
            mean_openness=1.0,
            max_openness=1.0,
            n_claims=0,
            warnings=["no_exposure_window_claims"],
            rationale="no exposure/window claims fed; shadow modifier is inert (neutral)",
        )

    binding = min(family, key=lambda p: p.posterior)
    weighted = sum(p.posterior for p in family) / len(family)
    binding_constraint = binding.posterior
    # Weakest claim governs, exactly as the live path caps at binding + 0.15.
    shadow_score = min(weighted, binding_constraint + 0.15)
    shadow_modifier = round(min(0.70 + 0.40 * shadow_score, 1.10), 4)

    mean_openness = sum(p.openness for p in family) / len(family)
    max_openness = max(p.openness for p in family)
    if max_openness >= 0.75:
        warnings.append("high_openness_low_evidence")
    if any(p.conflicting_evidence for p in family):
        warnings.append("conflicting_evidence_present")

    return ShadowScienceModifier(
        shadow_science_score=round(shadow_score, 4),
        shadow_modifier=shadow_modifier,
        binding_constraint=round(binding_constraint, 4),
        binding_claim=binding.claim_type,
        mean_openness=round(mean_openness, 4),
        max_openness=round(max_openness, 4),
        n_claims=len(family),
        warnings=warnings,
        rationale=(
            f"weakest claim {binding.claim_type.value} posterior={binding_constraint:.3f}; "
            f"mean posterior={weighted:.3f}; shadow modifier is audit-only (no live POS)"
        ),
    )


# ---------------------------------------------------------------------------
# System 1 <-> System 2 consistency audit
# ---------------------------------------------------------------------------


class ConsistencyVerdict(str, Enum):
    CONSISTENT = "consistent"
    DIVERGENT = "divergent"
    CONFLICT = "conflict"  # a live kill-flag contradicted by a favorable shadow claim


class ConsistencyAudit(BaseModel):
    """Diagnostic comparison of the live scalar modifier vs the shadow claim ledger."""

    model_config = ConfigDict(frozen=True)

    verdict: ConsistencyVerdict
    live_modifier: float
    shadow_modifier: float
    modifier_delta: float
    findings: list[str] = Field(default_factory=list)
    #: Restates the gate: this audit never authorizes a POS change on its own.
    affects_live_pos: bool = False


# How far the two modifiers may drift before we call them divergent. Loose on
# purpose: the shadow path is uncalibrated, so this is a smell test, not a gate.
_DIVERGENCE_TOLERANCE = 0.10

# Live kill-flags that assert an exposure/window failure. If the shadow ledger is
# simultaneously favorable on that family, the two systems genuinely conflict.
_EXPOSURE_WINDOW_KILL_FLAGS = {"infeasible_exposure", "unacceptable_safety"}


def audit_system_consistency(
    live_modifier: float,
    live_kill_flags: list[str],
    shadow: ShadowScienceModifier,
    posteriors: list[ClaimPosterior],
) -> ConsistencyAudit:
    """Compare System 1 (live scalar) against System 2 (shadow claim ledger).

    This is display/diagnostic only — it surfaces where the auditable ledger and the
    live scalar disagree so a human can look, and it never moves POS. ``live_kill_flags``
    are the ``.value`` strings from ``ScienceModifierResult.kill_flags``.
    """
    delta = round(shadow.shadow_modifier - live_modifier, 4)
    findings: list[str] = []

    kill_set = {str(f) for f in live_kill_flags}
    family = [p for p in posteriors if p.claim_type in EXPOSURE_WINDOW_FAMILY]
    favorable_family = family and min(p.posterior for p in family) >= 0.5

    verdict = ConsistencyVerdict.CONSISTENT

    exposure_kill = kill_set & _EXPOSURE_WINDOW_KILL_FLAGS
    if exposure_kill and favorable_family:
        verdict = ConsistencyVerdict.CONFLICT
        findings.append(
            "live path raised exposure/window kill-flag(s) "
            f"{sorted(exposure_kill)} but shadow ledger is favorable on that family "
            "(weakest posterior >= 0.5) — reconcile before trusting either"
        )

    if abs(delta) > _DIVERGENCE_TOLERANCE and verdict is not ConsistencyVerdict.CONFLICT:
        verdict = ConsistencyVerdict.DIVERGENT
        findings.append(
            f"live modifier {live_modifier:.3f} and shadow modifier "
            f"{shadow.shadow_modifier:.3f} differ by {abs(delta):.3f} "
            f"(> {_DIVERGENCE_TOLERANCE:.2f} tolerance)"
        )

    if shadow.max_openness >= 0.75:
        findings.append(
            "shadow claims are largely untested (high openness) — divergence may just "
            "reflect missing evidence, not a real disagreement"
        )

    if not findings:
        findings.append("live and shadow paths agree within tolerance")

    return ConsistencyAudit(
        verdict=verdict,
        live_modifier=round(live_modifier, 4),
        shadow_modifier=shadow.shadow_modifier,
        modifier_delta=delta,
        findings=findings,
    )


# ---------------------------------------------------------------------------
# Openness wiring — seed exposure/window claims from the killer-question set
# ---------------------------------------------------------------------------


def seed_exposure_window_claims(killer_question_set: object | None) -> list[ScienceClaim]:
    """Seed exposure/window ``ScienceClaim`` shells from a ``KillerQuestionSet``.

    Wires System 2's killer-question ``openness`` into the claim ledger as each
    claim's ``baseline_openness``: an untested killer question (openness 1.0) yields a
    fully-open claim awaiting evidence atoms. Read-only over the set; evidence atoms
    are attached separately. Archetypes outside the exposure/window family are skipped
    in this slice.
    """
    if killer_question_set is None:
        return []

    questions = [
        *list(getattr(killer_question_set, "decisive", []) or []),
        *list(getattr(killer_question_set, "candidates", []) or []),
    ]
    seen: set[tuple[ClaimType, str]] = set()
    claims: list[ScienceClaim] = []
    for q in questions:
        archetype = getattr(q, "archetype", None)
        claim_type = _ARCHETYPE_TO_CLAIM.get(archetype)
        if claim_type is None:
            continue
        question_text = str(getattr(q, "question_text", "") or "")
        key = (claim_type, question_text)
        if key in seen:
            continue
        seen.add(key)
        openness = float(getattr(q, "openness", 1.0))
        claims.append(
            ScienceClaim(
                claim_type=claim_type,
                question=question_text or claim_type.value,
                baseline_openness=min(max(openness, 0.0), 1.0),
            )
        )
    return claims


# ---------------------------------------------------------------------------
# Surfacing
# ---------------------------------------------------------------------------


def shadow_modifier_to_dict(shadow: ShadowScienceModifier) -> dict:
    """Compact, JSON-safe dict for memo/JSON output. Pure presentation."""
    return {
        "affects_live_pos": shadow.affects_live_pos,
        "calibration_status": shadow.calibration_status,
        "shadow_science_score": shadow.shadow_science_score,
        "shadow_modifier": shadow.shadow_modifier,
        "binding_constraint": shadow.binding_constraint,
        "binding_claim": shadow.binding_claim.value if shadow.binding_claim else None,
        "mean_openness": shadow.mean_openness,
        "max_openness": shadow.max_openness,
        "n_claims": shadow.n_claims,
        "warnings": list(shadow.warnings),
        "rationale": shadow.rationale,
    }


def consistency_audit_to_dict(audit: ConsistencyAudit) -> dict:
    """Compact, JSON-safe dict for memo/JSON output. Pure presentation."""
    return {
        "verdict": audit.verdict.value,
        "live_modifier": audit.live_modifier,
        "shadow_modifier": audit.shadow_modifier,
        "modifier_delta": audit.modifier_delta,
        "findings": list(audit.findings),
        "affects_live_pos": audit.affects_live_pos,
    }

"""Science Claim Ledger (POS Claim-Ledger Build Plan, Phase 1 vertical slice).

A claim-level, auditable, provenance-carrying evidence ledger that generalizes the
conviction layer's log-odds primitives (``EvidenceUpdate`` / ``ConvictionRecord``)
from killer-question posteriors to *biological claims*. This is the first vertical
slice: the **EXPOSURE_DELIVERY / THERAPEUTIC_WINDOW** claim family only. The other
eight families in :class:`ClaimType` are declared for shape but are deliberately NOT
wired end-to-end yet (Execution Discipline point 1: one family to calibration beats
twelve half-built).

Design invariants (enforced by tests):
  * **Shadow only.** Nothing here may move live POS. There is no import of, and no
    write path into, ``compute_science_modifier`` or the POS stack.
  * **Extend, not rebuild.** Evidence atoms *wrap* an :class:`EvidenceUpdate` and
    reuse its log-odds delta + the conviction kernel's sigmoid/logit math, rather
    than standing up a parallel ledger.
  * **Evidence hierarchy is a materiality gate (Phase 3).** Weak / unreviewed /
    inferred evidence *raises a question* but does not materially move the claim
    posterior; only strong, reviewed, observed evidence moves it at full weight.
  * **Missing evidence != claim false (Phase 4).** Absence of evidence leaves the
    posterior at prior and keeps *openness* (remaining uncertainty) high.
  * **Refutation is first-class.** A likelihood ratio < 1 lowers conviction and is
    never drowned by weak confirmations (log-odds composition).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.conviction_update import (
    EvidenceSource,
    EvidenceUpdate,
    UpdateDirection,
    _clamp01,
    _logit,
    _sigmoid,
)


# ---------------------------------------------------------------------------
# Phase 2 — claim taxonomy (replaces vague scalar T/D/B)
# ---------------------------------------------------------------------------


class ClaimType(str, Enum):
    """Specific biology claims, each answering one concrete question.

    Separable failure modes -> separable value swings (fixes the governing-index
    collapse of a single scalar). Only the exposure/window family is wired in the
    Phase 1 vertical slice; the rest are declared for future slices.
    """

    TARGET_VALIDITY = "target_validity"
    EXPOSURE_DELIVERY = "exposure_delivery"
    PHARMACODYNAMIC_ENGAGEMENT = "pharmacodynamic_engagement"
    THERAPEUTIC_WINDOW = "therapeutic_window"
    PREDICTIVE_BIOMARKER = "predictive_biomarker"
    PATIENT_SELECTION = "patient_selection"
    ENDPOINT_VALIDITY = "endpoint_validity"
    DIFFERENTIATION = "differentiation"
    MODALITY_SPECIFIC_RISK = "modality_specific_risk"
    NOVEL_OR_UNMODELED_RISK = "novel_or_unmodeled_risk"


#: The Phase 1 vertical slice: only these two families are validated end-to-end.
EXPOSURE_WINDOW_FAMILY: frozenset[ClaimType] = frozenset(
    {ClaimType.EXPOSURE_DELIVERY, ClaimType.THERAPEUTIC_WINDOW}
)


# ---------------------------------------------------------------------------
# Phase 3 — evidence hierarchy + provenance
# ---------------------------------------------------------------------------


class EvidenceTier(str, Enum):
    """Default strength tier for an evidence atom.

    HIGH: randomized human, direct human exposure-response, FDA/EMA review
    conclusions, validated predictive biomarker, human genetic causal.
    MEDIUM: single-arm human efficacy, human PK/PD, translational biomarker
    movement, competitor same-target clinical validation, replicated animal model.
    LOW: company slides, press releases, unreviewed abstracts, preclinical-only,
    inferred biomarker logic, non-disease-relevant in vitro.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ReviewStatus(str, Enum):
    """Human review state of the atom (mirrors expected-signature review_status)."""

    APPROVED = "approved"
    DRAFT = "draft"
    REJECTED = "rejected"


class MatchStatus(str, Enum):
    """Population / assay / endpoint concordance between evidence and the claim."""

    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class ObservationBasis(str, Enum):
    OBSERVED = "observed"
    INFERRED = "inferred"


# Base materiality multiplier by tier: how much of an atom's log-odds delta is
# allowed to move the *posterior*. Seeds for the Phase 1 slice, not final numbers.
_TIER_MATERIALITY: dict[EvidenceTier, float] = {
    EvidenceTier.HIGH: 1.0,
    EvidenceTier.MEDIUM: 0.5,
    EvidenceTier.LOW: 0.0,  # weak evidence raises a question; it does not move POS
}


class ClaimProvenance(BaseModel):
    """Provenance + quality metadata for one evidence atom (Phase 3 atom fields).

    The materiality gate lives here: :meth:`materiality_weight` returns the fraction
    of an atom's log-odds delta that is allowed to reach the posterior. An atom that
    is LOW-tier, not review-approved, inferred rather than observed, or drawn from a
    mismatched population is throttled toward zero — it still surfaces as a raised
    question, but it cannot masquerade as a POS-moving fact.
    """

    model_config = ConfigDict(frozen=True)

    source_id: str
    source_type: str = ""
    evidence_type: str = ""
    tier: EvidenceTier
    observed_vs_inferred: ObservationBasis = ObservationBasis.OBSERVED
    population_match: MatchStatus = MatchStatus.UNKNOWN
    assay_match: MatchStatus = MatchStatus.UNKNOWN
    endpoint_match: MatchStatus = MatchStatus.UNKNOWN
    review_status: ReviewStatus = ReviewStatus.DRAFT
    freshness_status: str = "current"
    conflict_status: str = "none"
    limitations: str = ""

    def materiality_weight(self) -> float:
        """Fraction of this atom's log-odds delta allowed to move the posterior.

        Zero => the atom is non-material: it only raises a question / adds openness.
        """
        weight = _TIER_MATERIALITY[self.tier]
        if weight == 0.0:
            return 0.0
        # Only strong, *reviewed*, *observed* evidence moves POS materially.
        if self.review_status is not ReviewStatus.APPROVED:
            return 0.0
        if self.observed_vs_inferred is ObservationBasis.INFERRED:
            return 0.0
        if self.population_match is MatchStatus.MISMATCH:
            return 0.0
        return weight

    def is_material(self) -> bool:
        return self.materiality_weight() > 0.0


class ClaimEvidenceAtom(BaseModel):
    """One evidence atom bearing on a claim: a wrapped ``EvidenceUpdate`` + provenance.

    Reuses the conviction layer's log-odds machinery (``EvidenceUpdate.log_odds_delta``)
    so there is a single updating primitive across the codebase, then throttles it by
    the provenance materiality gate before it reaches the posterior.
    """

    model_config = ConfigDict(frozen=True)

    claim_type: ClaimType
    update: EvidenceUpdate
    provenance: ClaimProvenance

    def material_log_odds_delta(self) -> float:
        return self.provenance.materiality_weight() * self.update.log_odds_delta()

    def material_informativeness(self) -> float:
        """Effective informativeness after the materiality gate (drives openness)."""
        return self.provenance.materiality_weight() * self.update.informativeness

    @property
    def direction(self) -> UpdateDirection:
        return self.update.direction


def make_claim_atom(
    claim_type: ClaimType,
    *,
    likelihood_ratio: float,
    tier: EvidenceTier,
    rationale: str,
    source_id: str,
    informativeness: float = 1.0,
    review_status: ReviewStatus = ReviewStatus.DRAFT,
    observed_vs_inferred: ObservationBasis = ObservationBasis.OBSERVED,
    population_match: MatchStatus = MatchStatus.UNKNOWN,
    assay_match: MatchStatus = MatchStatus.UNKNOWN,
    endpoint_match: MatchStatus = MatchStatus.UNKNOWN,
    source_type: str = "",
    evidence_type: str = "",
    limitations: str = "",
    as_of: str = "",
    source: EvidenceSource = EvidenceSource.MANUAL,
) -> ClaimEvidenceAtom:
    """Construct a claim evidence atom with a wrapped ``EvidenceUpdate`` + provenance."""
    direction = (
        UpdateDirection.CONFIRMING
        if likelihood_ratio > 1.0
        else UpdateDirection.REFUTING
        if likelihood_ratio < 1.0
        else UpdateDirection.NEUTRAL
    )
    update = EvidenceUpdate(
        source=source,
        likelihood_ratio=likelihood_ratio,
        informativeness=informativeness,
        rationale=rationale,
        provenance=source_id,
        as_of=as_of,
        direction=direction,
        label=tier.value,
    )
    provenance = ClaimProvenance(
        source_id=source_id,
        source_type=source_type,
        evidence_type=evidence_type,
        tier=tier,
        observed_vs_inferred=observed_vs_inferred,
        population_match=population_match,
        assay_match=assay_match,
        endpoint_match=endpoint_match,
        review_status=review_status,
        limitations=limitations,
    )
    return ClaimEvidenceAtom(claim_type=claim_type, update=update, provenance=provenance)


# ---------------------------------------------------------------------------
# Phase 4 — claim posterior engine
# ---------------------------------------------------------------------------


class ScienceClaim(BaseModel):
    """A single biological claim with its prior and evidence atoms."""

    model_config = ConfigDict(frozen=True)

    claim_type: ClaimType
    question: str
    prior: float = Field(default=0.5, gt=0.0, lt=1.0)
    atoms: list[ClaimEvidenceAtom] = Field(default_factory=list)
    #: Residual uncertainty before any evidence — e.g. seeded from a killer
    #: question's ``openness`` (1.0 = fully open / untested).
    baseline_openness: float = Field(default=1.0, ge=0.0, le=1.0)


class ClaimPosterior(BaseModel):
    """Per-claim posterior + the analyst-facing audit trail (Phase 4 outputs)."""

    model_config = ConfigDict(frozen=True)

    claim_type: ClaimType
    question: str
    prior: float
    posterior: float
    openness: float
    review_status: ReviewStatus
    n_material_atoms: int
    n_raised_questions: int
    top_positive: list[str] = Field(default_factory=list)
    top_negative: list[str] = Field(default_factory=list)
    missing_critical_evidence: list[str] = Field(default_factory=list)
    conflicting_evidence: list[str] = Field(default_factory=list)
    raised_questions: list[str] = Field(default_factory=list)


def _aggregate_review_status(atoms: list[ClaimEvidenceAtom]) -> ReviewStatus:
    """A claim is only APPROVED if it has at least one material approved atom."""
    if any(a.provenance.is_material() for a in atoms):
        return ReviewStatus.APPROVED
    if any(a.provenance.review_status is ReviewStatus.REJECTED for a in atoms):
        return ReviewStatus.REJECTED
    return ReviewStatus.DRAFT


def compute_claim_posterior(claim: ScienceClaim) -> ClaimPosterior:
    """Update a claim's posterior from its evidence atoms (log-odds, materiality-gated).

    Missing / weak evidence leaves the posterior near prior and keeps openness high;
    only material atoms move the posterior and close openness. Both confirming and
    refuting material atoms are first-class.
    """
    log_odds = _logit(claim.prior)
    applied_informativeness = 0.0
    material: list[ClaimEvidenceAtom] = []
    raised: list[ClaimEvidenceAtom] = []
    for atom in claim.atoms:
        if atom.provenance.is_material():
            log_odds += atom.material_log_odds_delta()
            applied_informativeness += atom.material_informativeness()
            material.append(atom)
        else:
            raised.append(atom)

    posterior = _clamp01(_sigmoid(log_odds))
    # Openness = residual uncertainty. No material evidence => openness stays at the
    # baseline (missing evidence is uncertainty, not falsification).
    openness = _clamp01(claim.baseline_openness * max(0.0, 1.0 - applied_informativeness))

    confirming = [a for a in material if a.direction is UpdateDirection.CONFIRMING]
    refuting = [a for a in material if a.direction is UpdateDirection.REFUTING]

    def _rationales(atoms: list[ClaimEvidenceAtom]) -> list[str]:
        return [
            f"[{a.provenance.tier.value}] {a.update.rationale} ({a.provenance.source_id})"
            for a in sorted(atoms, key=lambda x: abs(x.material_log_odds_delta()), reverse=True)
        ]

    conflicting: list[str] = []
    if confirming and refuting:
        conflicting = [
            "confirming and refuting material evidence coexist on this claim: "
            + f"{len(confirming)} confirming vs {len(refuting)} refuting"
        ]

    missing: list[str] = []
    if not material:
        missing.append(
            f"no material (strong, reviewed, observed) evidence for {claim.claim_type.value}"
        )

    return ClaimPosterior(
        claim_type=claim.claim_type,
        question=claim.question,
        prior=round(claim.prior, 4),
        posterior=round(posterior, 4),
        openness=round(openness, 4),
        review_status=_aggregate_review_status(claim.atoms),
        n_material_atoms=len(material),
        n_raised_questions=len(raised),
        top_positive=_rationales(confirming),
        top_negative=_rationales(refuting),
        missing_critical_evidence=missing,
        conflicting_evidence=conflicting,
        raised_questions=[
            f"[{a.provenance.tier.value}/{a.provenance.review_status.value}] "
            f"{a.update.rationale} ({a.provenance.source_id})"
            for a in raised
        ],
    )


# ---------------------------------------------------------------------------
# Surfacing — compact, JSON-safe rendering of the claim ledger
# ---------------------------------------------------------------------------


def claim_posterior_to_dict(posterior: ClaimPosterior) -> dict:
    """One ``ClaimPosterior`` as a compact, JSON-safe dict. Pure presentation."""
    return {
        "claim_type": posterior.claim_type.value,
        "question": posterior.question,
        "prior": posterior.prior,
        "posterior": posterior.posterior,
        "openness": posterior.openness,
        "review_status": posterior.review_status.value,
        "n_material_atoms": posterior.n_material_atoms,
        "n_raised_questions": posterior.n_raised_questions,
        "top_positive": list(posterior.top_positive),
        "top_negative": list(posterior.top_negative),
        "missing_critical_evidence": list(posterior.missing_critical_evidence),
        "conflicting_evidence": list(posterior.conflicting_evidence),
        "raised_questions": list(posterior.raised_questions),
    }


def build_claim_ledger_summary(
    posteriors: Optional[list[ClaimPosterior]],
) -> Optional[list[dict]]:
    """Render claim posteriors to JSON-safe dicts, or ``None`` if empty."""
    rows = [claim_posterior_to_dict(p) for p in (posteriors or [])]
    return rows or None

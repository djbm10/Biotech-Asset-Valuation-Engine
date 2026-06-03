"""
Layer 3B — Pair-Specific Asset-Control / Partner-Control Adjustment.

Answers: "For THIS specific acquirer, does the target's encumbrance profile
create additional deal-level risk beyond the universal target-level baseline?"

Takes the target-level result from 0D-T (AssetControlTargetResult) plus
acquirer-specific signals and applies pair-specific multipliers / caps.

Anti-double-counting contract:
  Universal target encumbrances (rights, economic, IP, diligence)
    → scored only in 0D-T (ma_asset_control_target.py)
  ROFR / opt-in / consent impact on THIS buyer
    → scored only here
  Acquirer manufacturing fit vs target complexity
    → scored only here
  Existing partner bonus / waiver
    → applied only here (never in 0D-T)
  Regional rights mismatch for THIS buyer
    → scored only here

pair_multiplier ∈ [0.0, 1.0]:
  1.0 = no additional adjustment beyond target-level
  < 1.0 = additional pair-specific reduction

How to combine with target-level result (in Layer 3 orchestrator):
  effective_penalty = target.penalty_multiplier × pair_multiplier
  effective_cap = min(target.max_mna_score_cap or 1.0, pair_cap or 1.0)

Manufacturing mismatch rules (per product spec):
  target complexity "high"   + acquirer_mfg_fit < 0.40 → mult ≤ 0.75, cap ≤ 0.65
  target complexity "medium" + acquirer_mfg_fit < 0.40 → mult ≤ 0.85
  target complexity "high"   + acquirer_mfg_fit 0.40–0.80 → mult ≤ 0.90 (mild)
  acquirer_mfg_fit >= 0.80   → no manufacturing penalty regardless of complexity
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.intelligence.ma_asset_control_target import AssetControlTargetResult


# ---------------------------------------------------------------------------
# Double-count guard
# ---------------------------------------------------------------------------

# These encumbrance codes must NOT appear in AssetControlTargetResult.triggered_encumbrances.
# If they do, the target-level module was called with pair-specific inputs — a bug.
_PAIR_ONLY_ENCUMBRANCE_CODES: frozenset[str] = frozenset({
    "partner_freedom:existing_partner_bonus_applied",
    "partner_freedom:ROFR_or_opt_in_blocks_this_acquirer",
    "partner_freedom:consent_right_blocking",
    "manufacturing_control:acquirer_strong_capability",
    "manufacturing_control:acquirer_weak_capability_amplifies_risk",
    "existing_partner:non_partner_acquirer_penalized",
})


def _assert_no_pair_contamination(target: AssetControlTargetResult) -> None:
    """Raise ValueError if the target result contains pair-specific codes."""
    bad = _PAIR_ONLY_ENCUMBRANCE_CODES & set(target.triggered_encumbrances)
    if bad:
        raise ValueError(
            f"AssetControlTargetResult contains pair-specific encumbrance codes: {bad}. "
            "The target was scored with pair-level inputs — use "
            "ma_asset_control_target.compute_asset_control_target() and pass only "
            "target-level AssetControlTargetInput."
        )


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class PairAssetControlInput(BaseModel):
    """Signal bag for Layer 3B: pair-specific asset-control adjustment.

    ``target_asset_control`` is the result from 0D-T for this target.
    All remaining fields are acquirer-specific.
    """
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    target_id: str

    # ── Target-level baseline from 0D-T ───────────────────────────────────────
    target_asset_control: AssetControlTargetResult

    # ── Acquirer partner status ───────────────────────────────────────────────
    acquirer_is_existing_partner: bool = Field(default=False,
        description="Acquirer IS the existing development/commercial partner. "
                    "Suppresses ROFR and consent penalties (partner waives its own rights).")

    # ── ROFR / opt-in ─────────────────────────────────────────────────────────
    rofr_blocks_this_acquirer: bool = Field(default=False,
        description="ROFR holder would exercise against this specific acquirer. "
                    "Pair-level cap applies unless acquirer_is_existing_partner.")
    opt_in_right_active: bool = Field(default=False,
        description="Partner has an active opt-in right; may delay or complicate close.")

    # ── Consent right ─────────────────────────────────────────────────────────
    consent_required_for_this_coc: bool = Field(default=False,
        description="Third-party consent required for this specific change-of-control.")

    # ── Regional rights fit ───────────────────────────────────────────────────
    acquirer_target_geography_overlap: float = Field(default=1.0, ge=0.0, le=1.0,
        description="Geographic rights overlap between what acquirer wants and what "
                    "target owns. 1.0 = full overlap; 0.0 = complete mismatch.")

    # ── Acquirer manufacturing fit ────────────────────────────────────────────
    acquirer_manufacturing_fit: float = Field(default=0.70, ge=0.0, le=1.0,
        description="Acquirer's manufacturing capability for this modality/complexity. "
                    "0.0 = no capability; 1.0 = fully in-house expertise. "
                    "Combined with target.manufacturing_complexity_flag for mismatch scoring.")

    # ── Exclusivity conflict ──────────────────────────────────────────────────
    exclusivity_conflict_for_this_acquirer: bool = Field(default=False,
        description="Acquirer has competing exclusivity clause triggered by this deal.")


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class PairAssetControlResult(BaseModel):
    """Layer 3B pair-specific asset-control result.

    pair_multiplier and pair_cap are applied ON TOP of the target-level
    penalty_multiplier and max_mna_score_cap in the Layer 3 orchestrator.
    """
    model_config = ConfigDict(frozen=True)

    acquirer_id: str
    target_id: str
    is_pair_scope: bool = True

    # ── Pair-level impact descriptors ─────────────────────────────────────────
    existing_partner_match: bool
    rofr_impact: str = Field(
        description="'none' / 'soft' / 'blocking' / 'waived_partner'")
    consent_right_impact: str = Field(
        description="'none' / 'required' / 'waived_partner'")
    regional_rights_fit: float = Field(ge=0.0, le=1.0)
    acquirer_manufacturing_fit: float = Field(ge=0.0, le=1.0)

    # ── Pair score adjustments ────────────────────────────────────────────────
    pair_asset_control_score: float = Field(ge=0.0, le=1.0,
        description="Target composite score adjusted by pair_multiplier")
    pair_multiplier: float = Field(ge=0.0, le=1.0,
        description="Additional multiplier applied on top of target penalty_multiplier. "
                    "1.0 = no additional adjustment.")
    pair_cap: Optional[float] = Field(default=None, ge=0.0, le=1.0,
        description="Pair-specific M&A score cap. Combined with target cap in orchestrator.")
    pair_level_fail: bool = Field(
        description="True only for this acquirer; target remains valid for other buyers.")

    # ── Manufacturing / geography detail ──────────────────────────────────────
    manufacturing_adjustment_applied: str = Field(
        description="'none' / 'mild' / 'moderate' / 'severe'")
    manufacturing_mismatch_flag: bool
    partner_bonus_applied: bool = Field(
        description="True when existing_partner_match suppresses ROFR/consent penalties.")

    # ── Metadata ──────────────────────────────────────────────────────────────
    rationale: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_pair_asset_control(inp: PairAssetControlInput) -> PairAssetControlResult:
    """Compute Layer 3B pair-specific asset-control adjustment.

    pair_multiplier starts at 1.0 (no additional adjustment).
    Each pair-specific risk factor can only reduce it further — they are
    applied multiplicatively via min() to enforce the tightest constraint wins.
    """
    _assert_no_pair_contamination(inp.target_asset_control)

    target = inp.target_asset_control
    pair_multiplier = 1.0
    pair_cap: Optional[float] = None
    rationale: list[str] = []
    data_gaps: list[str] = []

    existing_partner_match = inp.acquirer_is_existing_partner
    rofr_impact = "none"
    consent_right_impact = "none"
    manufacturing_adjustment = "none"
    manufacturing_mismatch_flag = False
    partner_bonus_applied = False

    # ── Existing partner: waive ROFR and consent penalties ────────────────────
    if inp.acquirer_is_existing_partner:
        partner_bonus_applied = True
        if target.has_rofr_fact:
            rofr_impact = "waived_partner"
            rationale.append("rofr: waived — acquirer is existing partner")
        if target.has_existing_partner_fact:
            consent_right_impact = "waived_partner"
            rationale.append("consent: waived — acquirer is existing partner")

    # ── ROFR / opt-in impact (only for non-partner acquirers) ─────────────────
    if not inp.acquirer_is_existing_partner:
        if inp.rofr_blocks_this_acquirer:
            pair_multiplier = min(pair_multiplier, 0.65)
            pair_cap = min(pair_cap if pair_cap is not None else 0.55, 0.55)
            rofr_impact = "blocking"
            rationale.append(
                "rofr: blocking this acquirer — pair_multiplier ≤ 0.65, pair_cap ≤ 0.55"
            )
        elif inp.opt_in_right_active:
            pair_multiplier = min(pair_multiplier, 0.80)
            rofr_impact = "soft"
            rationale.append(
                "opt_in: active right may delay close — pair_multiplier ≤ 0.80"
            )
        elif target.has_rofr_fact:
            # ROFR exists but buyer-specific blocking not confirmed
            rofr_impact = "soft"
            data_gaps.append(
                "rofr_impact_unconfirmed: ROFR exists; buyer-specific blocking unknown"
            )

    # ── Consent right impact (only for non-partner acquirers) ─────────────────
    if not inp.acquirer_is_existing_partner:
        if inp.consent_required_for_this_coc:
            pair_multiplier = min(pair_multiplier, 0.70)
            consent_right_impact = "required"
            rationale.append(
                "consent: required for this CoC — pair_multiplier ≤ 0.70"
            )

    # ── Exclusivity conflict ───────────────────────────────────────────────────
    if inp.exclusivity_conflict_for_this_acquirer:
        pair_multiplier = min(pair_multiplier, 0.80)
        rationale.append(
            "exclusivity: conflict for this acquirer — pair_multiplier ≤ 0.80"
        )

    # ── Regional rights fit ────────────────────────────────────────────────────
    geo = inp.acquirer_target_geography_overlap
    if geo < 0.50:
        pair_multiplier = min(pair_multiplier, 0.75)
        pair_cap = min(pair_cap if pair_cap is not None else 0.65, 0.65)
        rationale.append(
            f"regional_rights: severe mismatch (overlap={geo:.2f}) — "
            "pair_multiplier ≤ 0.75, pair_cap ≤ 0.65"
        )
    elif geo < 0.80:
        pair_multiplier = min(pair_multiplier, 0.90)
        rationale.append(
            f"regional_rights: partial mismatch (overlap={geo:.2f}) — "
            "pair_multiplier ≤ 0.90"
        )

    # ── Manufacturing fit vs target complexity ────────────────────────────────
    mfg_fit = inp.acquirer_manufacturing_fit
    mfg_complexity = target.manufacturing_complexity_flag

    if mfg_fit >= 0.80:
        # Strong acquirer capability — no manufacturing penalty applied
        manufacturing_adjustment = "none"
        if mfg_complexity == "high":
            rationale.append(
                f"manufacturing: strong acquirer capability ({mfg_fit:.2f}) offsets "
                "high modality complexity — no penalty"
            )
    elif mfg_complexity == "high" and mfg_fit < 0.40:
        # Severe mismatch: high-complexity target + weak acquirer capability
        pair_multiplier = min(pair_multiplier, 0.75)
        pair_cap = min(pair_cap if pair_cap is not None else 0.65, 0.65)
        manufacturing_adjustment = "severe"
        manufacturing_mismatch_flag = True
        rationale.append(
            f"manufacturing_complexity_buyer_mismatch: high complexity + "
            f"low acquirer fit ({mfg_fit:.2f}) — pair_multiplier ≤ 0.75, pair_cap ≤ 0.65"
        )
    elif mfg_complexity == "medium" and mfg_fit < 0.40:
        # Moderate mismatch: medium-complexity + weak acquirer capability
        pair_multiplier = min(pair_multiplier, 0.85)
        manufacturing_adjustment = "moderate"
        manufacturing_mismatch_flag = True
        rationale.append(
            f"manufacturing: medium complexity + low acquirer fit ({mfg_fit:.2f}) — "
            "pair_multiplier ≤ 0.85"
        )
    elif mfg_complexity == "high" and 0.40 <= mfg_fit < 0.80:
        # Mild mismatch: high-complexity target but acquirer has partial capability
        pair_multiplier = min(pair_multiplier, 0.90)
        manufacturing_adjustment = "mild"
        rationale.append(
            f"manufacturing: high complexity + moderate acquirer fit ({mfg_fit:.2f}) — "
            "pair_multiplier ≤ 0.90"
        )
    # else: low/medium complexity + moderate fit, or any complexity + strong fit → no penalty

    # ── Pair-level fail threshold ─────────────────────────────────────────────
    # A pair is not viable when the combined multiplier would be so low that
    # even a clean target would score below any actionable threshold.
    pair_level_fail = pair_multiplier <= 0.30

    # ── Pair-adjusted composite score ────────────────────────────────────────
    adjusted = target.asset_control_score * pair_multiplier
    if pair_cap is not None:
        adjusted = min(adjusted, pair_cap)
    pair_asset_control_score = round(max(0.0, min(1.0, adjusted)), 4)

    return PairAssetControlResult(
        acquirer_id=inp.acquirer_id,
        target_id=inp.target_id,
        existing_partner_match=existing_partner_match,
        rofr_impact=rofr_impact,
        consent_right_impact=consent_right_impact,
        regional_rights_fit=round(geo, 4),
        acquirer_manufacturing_fit=round(mfg_fit, 4),
        pair_asset_control_score=pair_asset_control_score,
        pair_multiplier=round(pair_multiplier, 4),
        pair_cap=pair_cap,
        pair_level_fail=pair_level_fail,
        manufacturing_adjustment_applied=manufacturing_adjustment,
        manufacturing_mismatch_flag=manufacturing_mismatch_flag,
        partner_bonus_applied=partner_bonus_applied,
        rationale=rationale,
        data_gaps=data_gaps,
    )


# ---------------------------------------------------------------------------
# Layer 3B combination helper
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PairAdjustedModifiers:
    """Combined score modifiers for a single acquirer-target pair.

    Produced by ``combine_layer0_and_3b()`` and consumed by the Layer 3
    orchestrator to assemble ``pre_gate_score`` and ``effective_cap`` before
    calling ``compute_layer3()``.

    Fields
    ------
    effective_multiplier
        Product of target-level, pair-level, and affordability multipliers.
        Applied to the raw score *before* Layer 3 gate evaluation.
        Formula::

            effective_multiplier =
                layer0_score_multiplier        # 0D-T encumbrance.penalty_multiplier
                × pair_result.pair_multiplier  # 3B ROFR / consent / mfg mismatch
                × affordability_score_mult     # 3A pair affordability

    effective_cap
        Tightest cap from all independent sources, or ``None`` when no cap
        applies.  Applied to ``final_score`` *after* Layer 3 gates.
        Formula::

            effective_cap = min(
                layer0_score_cap,          # 0F distress guard cap
                target_max_mna_score_cap,  # 0D-T gate treatment (SEVERE/ROUTE)
                pair_result.pair_cap,      # 3B ROFR / mfg mismatch cap
                integration_cap,           # G8 pair integration cap
            )

    pair_asset_control
        The raw ``PairAssetControlResult`` from 3B, or ``None`` when no 3B
        signals were present and 3B was not invoked.
    """

    effective_multiplier: float
    effective_cap: Optional[float]
    pair_asset_control: Optional[PairAssetControlResult]


def combine_layer0_and_3b(
    layer0_score_multiplier: float,
    layer0_score_cap: Optional[float],
    target_max_mna_score_cap: Optional[float],
    pair_result: Optional[PairAssetControlResult],
    affordability_score_multiplier: float = 1.0,
    integration_cap: Optional[float] = None,
) -> PairAdjustedModifiers:
    """Combine Layer 0 target-level and Layer 3B pair-specific score modifiers.

    Anti-double-counting contract
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    ``layer0_score_multiplier`` covers universal target encumbrances evaluated
    without knowing the buyer (0D-T).  ``pair_result.pair_multiplier`` covers
    buyer-specific signals that 0D-T deliberately omits: ROFR impact on *this*
    acquirer, consent rights, manufacturing fit, existing-partner waiver.
    These score independent risk sources and never overlap.

    The ``_assert_no_pair_contamination()`` guard in ``compute_pair_asset_control()``
    prevents pair-specific encumbrance codes from appearing in the target result,
    enforcing the contract at runtime.

    Parameters
    ----------
    layer0_score_multiplier:
        ``Layer0Result.score_multiplier`` (= ``encumbrance.penalty_multiplier``).
    layer0_score_cap:
        ``Layer0Result.score_cap`` (from 0F distress guard; ``None`` = no cap).
    target_max_mna_score_cap:
        ``Layer0Result.encumbrance.max_mna_score_cap`` (from 0D-T gate; ``None`` = no cap).
    pair_result:
        ``PairAssetControlResult`` from ``compute_pair_asset_control()``, or
        ``None`` when ``"pair_asset_control_adjustment"`` was not in
        ``required_downstream_checks``.
    affordability_score_multiplier:
        ``AffordabilityResult.score_multiplier`` from Layer 3A (defaults to 1.0
        when affordability has not been evaluated).
    integration_cap:
        Cap from Layer 3 G8 pair-integration check (``None`` = not triggered).

    Returns
    -------
    PairAdjustedModifiers
    """
    pair_mult = pair_result.pair_multiplier if pair_result is not None else 1.0
    effective_mult = round(
        layer0_score_multiplier * pair_mult * affordability_score_multiplier,
        6,
    )

    caps = [
        c for c in (
            layer0_score_cap,
            target_max_mna_score_cap,
            pair_result.pair_cap if pair_result is not None else None,
            integration_cap,
        )
        if c is not None
    ]
    effective_cap = round(min(caps), 4) if caps else None

    return PairAdjustedModifiers(
        effective_multiplier=effective_mult,
        effective_cap=effective_cap,
        pair_asset_control=pair_result,
    )

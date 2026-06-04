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

from bve.intelligence.deal_type_classification import DealStructureRoute
from bve.intelligence.ma_asset_control_target import AssetControlTargetResult


# ---------------------------------------------------------------------------
# Route-specific bucket weight tables
# ---------------------------------------------------------------------------
#
# Each route re-weights the six 0D-T bucket scores to reflect what matters
# for that deal structure.  Weights sum to 1.0 for every route.
#
# Design rationale:
#   rights_control  shrinks as deal moves toward minority equity / licensing
#                   (full global rights less critical for non-acquisition routes)
#   ip_control      grows for licensing/option routes (betting on the IP, not the company)
#   economic_control stays roughly flat (royalty/milestone burden matters everywhere)
#   manufacturing   peaks for co-dev (licensor retains mfg → transferability critical)
#                   lower for minority equity (investor not operating the asset)
#   diligence       grows for minority equity (governance/data gaps harder to fix post-close)
# ---------------------------------------------------------------------------

_ROUTE_BUCKET_WEIGHTS: dict[DealStructureRoute, dict[str, float]] = {
    # Full acquisition routes: identical to 0D-T default weights
    DealStructureRoute.FULL_COMPANY_TAKEOUT: {
        "rights": 0.25, "economic": 0.20, "partner": 0.20,
        "ip": 0.15, "mfg": 0.10, "diligence": 0.10,
    },
    DealStructureRoute.LEAD_ASSET_TAKEOUT: {
        "rights": 0.25, "economic": 0.20, "partner": 0.20,
        "ip": 0.15, "mfg": 0.10, "diligence": 0.10,
    },
    DealStructureRoute.PIPELINE_PORTFOLIO_TAKEOUT: {
        "rights": 0.25, "economic": 0.20, "partner": 0.20,
        "ip": 0.15, "mfg": 0.10, "diligence": 0.10,
    },
    DealStructureRoute.PLATFORM_ACQUISITION: {
        "rights": 0.25, "economic": 0.20, "partner": 0.20,
        "ip": 0.15, "mfg": 0.10, "diligence": 0.10,
    },
    DealStructureRoute.COMMERCIAL_FRANCHISE_ACQUISITION: {
        "rights": 0.25, "economic": 0.20, "partner": 0.20,
        "ip": 0.15, "mfg": 0.10, "diligence": 0.10,
    },
    # Licensing routes: rights matter less, IP matters more
    DealStructureRoute.GLOBAL_LICENSE: {
        "rights": 0.20, "economic": 0.22, "partner": 0.18,
        "ip": 0.18, "mfg": 0.12, "diligence": 0.10,
    },
    DealStructureRoute.REGIONAL_LICENSE: {
        "rights": 0.15, "economic": 0.22, "partner": 0.18,
        "ip": 0.20, "mfg": 0.12, "diligence": 0.13,
    },
    DealStructureRoute.OPTION_TO_LICENSE_OR_ACQUIRE: {
        "rights": 0.12, "economic": 0.20, "partner": 0.16,
        "ip": 0.22, "mfg": 0.18, "diligence": 0.12,
    },
    DealStructureRoute.CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION: {
        "rights": 0.12, "economic": 0.18, "partner": 0.14,
        "ip": 0.22, "mfg": 0.18, "diligence": 0.16,
    },
    # Minority equity: IP and diligence are primary; manufacturing moderate
    DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION: {
        "rights": 0.08, "economic": 0.22, "partner": 0.12,
        "ip": 0.24, "mfg": 0.14, "diligence": 0.20,
    },
    # Distressed: same as full takeout (distress is real regardless of structure)
    DealStructureRoute.DISTRESSED_OPTIONALITY: {
        "rights": 0.25, "economic": 0.20, "partner": 0.20,
        "ip": 0.15, "mfg": 0.10, "diligence": 0.10,
    },
}

# Sanity check at import time
for _route, _w in _ROUTE_BUCKET_WEIGHTS.items():
    assert abs(sum(_w.values()) - 1.0) < 1e-9, (
        f"_ROUTE_BUCKET_WEIGHTS[{_route.value}] sums to {sum(_w.values()):.6f}, expected 1.0"
    )


# ---------------------------------------------------------------------------
# Licensing routes: where fully_licensed_away can be demoted to a warning
# ---------------------------------------------------------------------------

_LICENSING_ROUTES: frozenset[DealStructureRoute] = frozenset({
    DealStructureRoute.GLOBAL_LICENSE,
    DealStructureRoute.REGIONAL_LICENSE,
    DealStructureRoute.OPTION_TO_LICENSE_OR_ACQUIRE,
    DealStructureRoute.CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION,
    DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
})


# ---------------------------------------------------------------------------
# Geography region normalisation
# ---------------------------------------------------------------------------

_GEO_REGION_MAP: dict[str, frozenset] = {
    "global":   frozenset({"US", "EU", "APAC", "LATAM", "MEA"}),
    "us":       frozenset({"US"}),
    "eu":       frozenset({"EU"}),
    "ex-us":    frozenset({"EU", "APAC", "LATAM", "MEA"}),
    "ex_us":    frozenset({"EU", "APAC", "LATAM", "MEA"}),
    "us+eu":    frozenset({"US", "EU"}),
    "eu+us":    frozenset({"US", "EU"}),
    "apac":     frozenset({"APAC"}),
    "latam":    frozenset({"LATAM"}),
    "mea":      frozenset({"MEA"}),
}


def _geo_regions(geo: str) -> frozenset:
    """Normalise a geography string to a frozenset of canonical region codes."""
    key = geo.lower().replace(" ", "")
    if key in _GEO_REGION_MAP:
        return _GEO_REGION_MAP[key]
    # Handle compound geographies (e.g. "US+APAC") not explicitly listed
    parts = key.replace("+", " ").split()
    result: set = set()
    for p in parts:
        result.update(_GEO_REGION_MAP.get(p, {p.upper()}))
    return frozenset(result)


def _classify_geo_fit(buyer_desired: str, target_controlled: str) -> str:
    """Return 'full_match', 'superset', 'partial_match', or 'mismatch'.

    Semantics: does target_controlled give buyer everything buyer_desired needs?
      full_match    — target has exactly the regions buyer wants
      superset      — target has buyer's regions plus more (buyer over-served, still fine)
      partial_match — target covers ≥ 50% of buyer's desired regions
      mismatch      — target covers < 50% of buyer's desired regions (includes zero overlap)

    The 50% coverage threshold matters for wide buyer requests:
      "global" buyer (5 regions) + "EU" target (1 region) → coverage=20% → mismatch
      "US+EU" buyer + "EU" target → coverage=50% → partial_match
      "APAC" buyer + "EU" target → coverage=0% → mismatch
    """
    buyer_set = _geo_regions(buyer_desired)
    target_set = _geo_regions(target_controlled)
    intersection = buyer_set & target_set
    if buyer_set <= target_set:
        return "full_match" if buyer_set == target_set else "superset"
    if not intersection:
        return "mismatch"
    coverage = len(intersection) / len(buyer_set) if buyer_set else 0.0
    return "partial_match" if coverage >= 0.50 else "mismatch"


# ---------------------------------------------------------------------------
# Route-adjusted composite helper
# ---------------------------------------------------------------------------

def _route_adjusted_composite(
    target: AssetControlTargetResult,
    route: Optional[DealStructureRoute],
) -> tuple[float, str]:
    """Recompute the 0D-T composite using route-specific bucket weights.

    Returns (route_adjusted_base_score, route_adjustment_applied_label).
    When route is None the raw asset_control_score is returned unchanged.
    """
    if route is None or route not in _ROUTE_BUCKET_WEIGHTS:
        return target.asset_control_score, "none"

    w = _ROUTE_BUCKET_WEIGHTS[route]
    composite = (
        w["rights"]   * target.rights_control_score
        + w["economic"] * target.economic_control_score
        + w["partner"]  * target.partner_encumbrance_facts_score
        + w["ip"]       * target.ip_control_score
        + w["mfg"]      * target.manufacturing_readiness_score
        + w["diligence"]* target.diligence_readiness_score
    )
    return round(max(0.0, min(1.0, composite)), 4), f"route_{route.value}"


# ---------------------------------------------------------------------------
# Geography fit helper
# ---------------------------------------------------------------------------

def _geography_fit_from_float(
    overlap: float,
) -> tuple[str, list[str], float, Optional[float]]:
    """Backward-compatible float-path geography check."""
    if overlap < 0.50:
        return "not_provided", [
            f"regional_rights: severe mismatch (overlap={overlap:.2f}) — "
            "pair_multiplier ≤ 0.75, pair_cap ≤ 0.65"
        ], 0.75, 0.65
    if overlap < 0.80:
        return "not_provided", [
            f"regional_rights: partial mismatch (overlap={overlap:.2f}) — "
            "pair_multiplier ≤ 0.90"
        ], 0.90, None
    return "not_provided", [], 1.0, None


def _geography_fit(
    buyer_desired: Optional[str],
    target_controlled: Optional[str],
    route: Optional[DealStructureRoute],
    overlap_float: float,
) -> tuple[str, list[str], float, Optional[float]]:
    """Route-aware geography fit check.

    Returns: (fit_detail, rationale_items, pair_mult_upper_bound, pair_cap_or_None)

    String-based path (preferred when both buyer_desired and target_controlled provided):
      - fit = _classify_geo_fit(buyer_desired, target_controlled)
      - CO_DEV / MINORITY_EQUITY: partial_match → no penalty; mismatch → mild 0.85
      - All other routes (including REGIONAL_LICENSE): mismatch → 0.75/cap 0.65
      - full_match / superset: always no penalty regardless of route

    Float fallback: existing overlap-based logic (unchanged behavior).

    Key principle: a wrong region is a wrong region regardless of route type.
    REGIONAL_LICENSE only avoids penalty when the buyer's desired region actually
    matches the target's controlled region — not just because it's a licensing deal.
    """
    if buyer_desired is not None and target_controlled is not None:
        fit = _classify_geo_fit(buyer_desired, target_controlled)
        desc = f"{buyer_desired}→{target_controlled}"

        if fit in ("full_match", "superset"):
            return fit, [f"geography: {fit} ({desc}) — no penalty"], 1.0, None

        # CO_DEV / MINORITY_EQUITY: reduced penalties (shared structure accommodates partial overlap)
        if route in (
            DealStructureRoute.CO_DEVELOPMENT_OR_CO_COMMERCIALIZATION,
            DealStructureRoute.MINORITY_EQUITY_PLUS_COLLABORATION,
        ):
            if fit == "partial_match":
                return fit, [
                    f"geography: partial_match ({desc}) — no penalty for {route.value}"
                ], 1.0, None
            # mismatch → mild penalty, no hard cap
            return fit, [
                f"geography: mismatch ({desc}) — mild penalty for {route.value}: "
                "pair_multiplier ≤ 0.85"
            ], 0.85, None

        # All other routes (FULL_COMPANY_TAKEOUT, REGIONAL_LICENSE, GLOBAL_LICENSE, etc.):
        # same penalty matrix — wrong region is penalized the same way
        if fit == "partial_match":
            return fit, [
                f"geography: partial_match ({desc}) — pair_multiplier ≤ 0.90"
            ], 0.90, None
        # mismatch
        return fit, [
            f"geography: mismatch ({desc}) — pair_multiplier ≤ 0.75, pair_cap ≤ 0.65"
        ], 0.75, 0.65

    # Float fallback (both string fields absent)
    return _geography_fit_from_float(overlap_float)


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

    # ── 0B deal-structure route ───────────────────────────────────────────────
    deal_structure_route: Optional[DealStructureRoute] = Field(default=None,
        description="Layer 0B deal-structure route for this pair. When provided, Layer 3B "
                    "recomputes the base score from raw 0D-T bucket scores using route-specific "
                    "weights, and applies route-aware geography fit logic.")

    # ── Explicit geography fields (string-based; preferred over overlap float) ─
    buyer_desired_geography: Optional[str] = Field(default=None,
        description="Regions the acquirer is seeking rights to: "
                    "'global', 'US', 'EU', 'ex-US', 'US+EU', 'APAC', etc. "
                    "When provided together with target_controlled_geography, "
                    "enables explicit region-match scoring instead of the overlap float.")
    target_controlled_geography: Optional[str] = Field(default=None,
        description="Regions the target actually controls (not out-licensed). "
                    "Paired with buyer_desired_geography for route-aware geo scoring. "
                    "Falls back to acquirer_target_geography_overlap when absent.")


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

    # ── Route-aware scoring audit fields ─────────────────────────────────────
    route_adjusted_base_score: float = Field(..., ge=0.0, le=1.0,
        description="Composite recomputed from raw 0D-T bucket scores using route-specific "
                    "weights. Equals target.asset_control_score when deal_structure_route is None "
                    "or a full-acquisition route (which uses the same 0D-T weights).")
    route_adjustment_applied: str = Field(...,
        description="'none' / 'route_<route_value>' — label of the route weight table applied.")
    geography_fit_detail: str = Field(default="not_provided",
        description="'full_match' / 'superset' / 'partial_match' / 'mismatch' / 'not_provided'. "
                    "'not_provided' when string geography fields were absent and the float "
                    "overlap fallback was used instead.")

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

    Route-aware additions (new):
      1. route_adjusted_base_score — 0D-T bucket scores re-weighted by deal_structure_route.
         When route is None, falls back to target.asset_control_score unchanged.
      2. Geography fit — explicit buyer_desired_geography vs target_controlled_geography
         when both are provided; falls back to acquirer_target_geography_overlap float.
         Key principle: a wrong region is penalized regardless of route.
         REGIONAL_LICENSE only avoids a geo penalty when the buyer's desired region
         actually matches what the target controls.
      3. Hard blocker pass-through — target.is_hard_fail (no_ownable_rights /
         fatal_ip_dispute) forces pair_multiplier=0.0 regardless of route.
      4. fully_licensed_away (target.route_to_licensing):
         - licensing route + economics retained (economic_control_score ≥ 0.50)
           → route-consistent: no additional pair penalty; mark as data_gap warning
         - any other case (non-licensing route OR no economics)
           → severe pair penalty (pair_multiplier ≤ 0.55)
    """
    _assert_no_pair_contamination(inp.target_asset_control)

    target = inp.target_asset_control
    route = inp.deal_structure_route

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

    # ── 1. Route-adjusted base score ─────────────────────────────────────────
    route_adjusted_base_score, route_adjustment_applied = _route_adjusted_composite(target, route)
    if route_adjustment_applied != "none":
        rationale.append(
            f"route_adjusted_composite: {route_adjustment_applied} "
            f"(raw={target.asset_control_score:.4f} → route_adjusted={route_adjusted_base_score:.4f})"
        )

    # ── 2. Hard blocker pass-through from 0D-T ───────────────────────────────
    # is_hard_fail (no_ownable_rights / fatal_ip_dispute): fatal for ALL routes.
    # The route does not change whether you can own something or whether IP is contested.
    if target.is_hard_fail:
        pair_multiplier = 0.0
        rationale.append(
            "0D-T hard fail propagated: no ownable rights or fatal IP dispute — "
            "pair_level_fail forced regardless of route"
        )

    # ── 3. fully_licensed_away routing ───────────────────────────────────────
    # 0D-T sets route_to_licensing=True when fully_licensed_away=True.
    # For licensing routes: demote to warning IF target retains meaningful economics.
    # Otherwise (non-licensing route OR economics gone): additional pair penalty.
    # Note: 0D-T already applies penalty_multiplier=0.40 via the orchestrator;
    # Layer 3B adds a further pair penalty only when economics cannot support even
    # a licensing deal.
    if target.route_to_licensing and not target.is_hard_fail:
        economics_retained = target.economic_control_score >= 0.50
        if route in _LICENSING_ROUTES and economics_retained:
            # Route-consistent: 0D-T penalty stands; no additional Layer 3B reduction
            data_gaps.append(
                "fully_licensed_away:route_consistent_economics_retained"
            )
            rationale.append(
                f"fully_licensed_away: route-consistent for {route.value} "
                f"(economic_control_score={target.economic_control_score:.2f} ≥ 0.50) — "
                "0D-T penalty accepted; no additional pair reduction"
            )
        else:
            # No controllable economics, or buyer wants full acquisition of a licensed-away asset
            pair_multiplier = min(pair_multiplier, 0.55)
            label = (
                "no controllable economics "
                f"(economic_control_score={target.economic_control_score:.2f} < 0.50)"
                if not economics_retained
                else f"non-licensing route ({route.value if route else 'none'}) on licensed-away asset"
            )
            rationale.append(
                f"fully_licensed_away: {label} — "
                "pair_multiplier ≤ 0.55"
            )

    # ── 4. Existing partner: waive ROFR and consent penalties ─────────────────
    if inp.acquirer_is_existing_partner:
        partner_bonus_applied = True
        if target.has_rofr_fact:
            rofr_impact = "waived_partner"
            rationale.append("rofr: waived — acquirer is existing partner")
        if target.has_existing_partner_fact:
            consent_right_impact = "waived_partner"
            rationale.append("consent: waived — acquirer is existing partner")

    # ── 5. ROFR / opt-in impact (only for non-partner acquirers) ──────────────
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
            rofr_impact = "soft"
            data_gaps.append(
                "rofr_impact_unconfirmed: ROFR exists; buyer-specific blocking unknown"
            )

    # ── 6. Consent right impact (only for non-partner acquirers) ──────────────
    if not inp.acquirer_is_existing_partner:
        if inp.consent_required_for_this_coc:
            pair_multiplier = min(pair_multiplier, 0.70)
            consent_right_impact = "required"
            rationale.append(
                "consent: required for this CoC — pair_multiplier ≤ 0.70"
            )

    # ── 7. Exclusivity conflict ───────────────────────────────────────────────
    if inp.exclusivity_conflict_for_this_acquirer:
        pair_multiplier = min(pair_multiplier, 0.80)
        rationale.append(
            "exclusivity: conflict for this acquirer — pair_multiplier ≤ 0.80"
        )

    # ── 8. Geography fit (route-aware) ───────────────────────────────────────
    geo_fit_detail, geo_rationale, geo_mult, geo_cap = _geography_fit(
        inp.buyer_desired_geography,
        inp.target_controlled_geography,
        route,
        inp.acquirer_target_geography_overlap,
    )
    if geo_mult < 1.0:
        pair_multiplier = min(pair_multiplier, geo_mult)
    if geo_cap is not None:
        pair_cap = min(pair_cap if pair_cap is not None else geo_cap, geo_cap)
    rationale.extend(geo_rationale)

    # ── 9. Manufacturing fit vs target complexity ─────────────────────────────
    mfg_fit = inp.acquirer_manufacturing_fit
    mfg_complexity = target.manufacturing_complexity_flag

    if mfg_fit >= 0.80:
        manufacturing_adjustment = "none"
        if mfg_complexity == "high":
            rationale.append(
                f"manufacturing: strong acquirer capability ({mfg_fit:.2f}) offsets "
                "high modality complexity — no penalty"
            )
    elif mfg_complexity == "high" and mfg_fit < 0.40:
        pair_multiplier = min(pair_multiplier, 0.75)
        pair_cap = min(pair_cap if pair_cap is not None else 0.65, 0.65)
        manufacturing_adjustment = "severe"
        manufacturing_mismatch_flag = True
        rationale.append(
            f"manufacturing_complexity_buyer_mismatch: high complexity + "
            f"low acquirer fit ({mfg_fit:.2f}) — pair_multiplier ≤ 0.75, pair_cap ≤ 0.65"
        )
    elif mfg_complexity == "medium" and mfg_fit < 0.40:
        pair_multiplier = min(pair_multiplier, 0.85)
        manufacturing_adjustment = "moderate"
        manufacturing_mismatch_flag = True
        rationale.append(
            f"manufacturing: medium complexity + low acquirer fit ({mfg_fit:.2f}) — "
            "pair_multiplier ≤ 0.85"
        )
    elif mfg_complexity == "high" and 0.40 <= mfg_fit < 0.80:
        pair_multiplier = min(pair_multiplier, 0.90)
        manufacturing_adjustment = "mild"
        rationale.append(
            f"manufacturing: high complexity + moderate acquirer fit ({mfg_fit:.2f}) — "
            "pair_multiplier ≤ 0.90"
        )
    # else: low/medium complexity + moderate fit, or any complexity + strong fit → no penalty

    # ── 10. Pair-level fail threshold ─────────────────────────────────────────
    pair_level_fail = pair_multiplier <= 0.30

    # ── 11. Pair-adjusted composite score ────────────────────────────────────
    # Use route_adjusted_base_score (not raw target.asset_control_score).
    # For hard fails pair_multiplier=0.0, so score=0.0 regardless of base.
    adjusted = route_adjusted_base_score * pair_multiplier
    if pair_cap is not None:
        adjusted = min(adjusted, pair_cap)
    pair_asset_control_score = round(max(0.0, min(1.0, adjusted)), 4)

    geo = inp.acquirer_target_geography_overlap
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
        route_adjusted_base_score=route_adjusted_base_score,
        route_adjustment_applied=route_adjustment_applied,
        geography_fit_detail=geo_fit_detail,
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

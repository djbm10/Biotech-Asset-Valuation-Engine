"""
Layer 2 Inputs Builder — real data source adapters.

Converts live engine outputs into the typed Layer2Inputs model consumed by
``compute_layer2_bd_priority``.  Each adapter is a pure function: input a
real data object, output a score or sub-model.  No side effects.

Public API
----------
    financing_pressure_from_assessment(assessment) -> float
    valuation_distress_from_assessment(assessment) -> float
    valuation_data_freshness_from_assessment(assessment, as_of) -> float
    catalyst_timing_from_events(events, as_of) -> tuple[float, float]
    acquirer_pull_row_from_profile(profile, *, target_ta, target_modality,
                                   target_ticker, as_of) -> AcquirerPullInputRow
    acquirer_profile_freshness_score(profiles, as_of) -> float
    pipeline_gap_urgency_from_profiles(profiles, target_ta) -> float
    loe_revenue_cliff_urgency_from_profiles(profiles, target_ta) -> float
    rights_encumbrance_clarity_from_layer0(layer0) -> float
    build_layer2_inputs(...) -> Layer2Inputs

Scoring conventions
-------------------
    All scores are [0, 1].
    Higher = more favourable for BD action (e.g. higher financing pressure
    → target more motivated to transact → higher Layer 2 score component).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from bve.intelligence.ma_layer2_bd_priority import (
    AcquirerPullInputRow,
    Layer2BuyerSideUrgencyInputs,
    Layer2InformationReadinessInputs,
    Layer2Inputs,
    Layer2StrategicPriorityInputs,
    Layer2TargetSidePressureInputs,
)

# ---------------------------------------------------------------------------
# Catalyst date-confidence → numeric score
# ---------------------------------------------------------------------------

_DATE_CONFIDENCE_SCORE: dict[str, float] = {
    "exact":     1.00,
    "quarter":   0.75,
    "half_year": 0.50,
    "estimate":  0.30,
}

# Catalyst timing: days_until → score
# Ordered from most urgent to least urgent.
_CATALYST_TIMING_BINS: list[tuple[int, float]] = [
    (30,  1.00),
    (60,  0.85),
    (90,  0.70),
    (120, 0.55),
    (180, 0.40),
]
_CATALYST_TIMING_FAR: float = 0.20       # > 180 days away
_CATALYST_TIMING_NONE: float = 0.10      # no upcoming catalyst

# ---------------------------------------------------------------------------
# Profile freshness: age in days → score
# ---------------------------------------------------------------------------

_FRESHNESS_BINS: list[tuple[int, float]] = [
    (90,  1.00),
    (180, 0.85),
    (365, 0.65),
    (730, 0.40),
]
_FRESHNESS_STALE: float = 0.20           # > 730 days

# Valuation data freshness (from FinancingModuleOutput.freshness datetime)
_VALUATION_FRESHNESS_BINS: list[tuple[int, float]] = [
    (30,  1.00),
    (60,  0.85),
    (90,  0.70),
    (180, 0.50),
    (365, 0.30),
]
_VALUATION_FRESHNESS_STALE: float = 0.15

# ---------------------------------------------------------------------------
# Therapeutic area / modality fit → score
# ---------------------------------------------------------------------------

_EXPOSURE_SCORE: dict[str, float] = {
    "high":   0.90,
    "medium": 0.65,
    "low":    0.40,
}
_EXPOSURE_NO_MATCH: float = 0.15

_MODALITY_PREF_SCORE: dict[str, float] = {
    "high":   0.90,
    "medium": 0.65,
    "low":    0.40,
}
_MODALITY_NO_MATCH: float = 0.25

# Buyer deal appetite: recent deals in past 24 months → score
_DEAL_APPETITE_PER_DEAL: float = 0.25    # 4 deals → 1.0, capped
_DEAL_APPETITE_NO_HISTORY: float = 0.50  # neutral; no evidence either way


# ---------------------------------------------------------------------------
# Financing engine adapters
# ---------------------------------------------------------------------------

def _extract_financing_value(assessment: object) -> object:
    """Return a FinancingAssessmentValue (or dict-like) from any assessment."""
    output = getattr(assessment, "output", None)
    if output is None:
        return assessment
    value = getattr(output, "value", None)
    if value is None:
        return output
    return value


def _get_float(obj: object, field: str, default: float = 0.5) -> float:
    """Safely get a float attribute from an object or dict."""
    if isinstance(obj, dict):
        return float(obj.get(field, default))
    return float(getattr(obj, field, default))


def financing_pressure_from_assessment(assessment: object) -> float:
    """Convert FinancingAssessment → financing_pressure score [0, 1].

    Maps ``FinancingAssessmentValue.financing_risk_score`` directly.
    Higher financing risk = higher pressure to transact = higher score.
    """
    value = _extract_financing_value(assessment)
    return _get_float(value, "financing_risk_score", default=0.50)


def valuation_distress_from_assessment(assessment: object) -> float:
    """Convert FinancingAssessment → valuation_distress score [0, 1].

    Maps ``FinancingAssessmentValue.balance_sheet_stress_score`` directly.
    """
    value = _extract_financing_value(assessment)
    return _get_float(value, "balance_sheet_stress_score", default=0.50)


def valuation_data_freshness_from_assessment(
    assessment: object,
    as_of: date,
) -> float:
    """Score how fresh the financing/valuation data is.

    Uses ``FinancingModuleOutput.freshness`` (a datetime).  Converts to
    days-old and applies the standard freshness bins.
    """
    output = getattr(assessment, "output", None)
    if output is None:
        return 0.50
    freshness_dt = getattr(output, "freshness", None)
    if freshness_dt is None:
        return 0.50
    try:
        freshness_date = freshness_dt.date() if hasattr(freshness_dt, "date") else freshness_dt
        days_old = max(0, (as_of - freshness_date).days)
    except Exception:
        return 0.50
    return _days_to_score(days_old, _VALUATION_FRESHNESS_BINS, _VALUATION_FRESHNESS_STALE)


# ---------------------------------------------------------------------------
# Catalyst calendar adapters
# ---------------------------------------------------------------------------

def catalyst_timing_from_events(
    events: list[object],
    as_of: date,
) -> tuple[float, float]:
    """Convert a list of CatalystEvents → (catalyst_timing_score, catalyst_date_confidence).

    Finds the nearest upcoming active + unresolved catalyst.
    Returns (timing_score, confidence_score) both in [0, 1].
    """
    upcoming = [
        e for e in events
        if _is_upcoming(e, as_of)
    ]
    if not upcoming:
        return _CATALYST_TIMING_NONE, 0.30

    # Sort by expected_date ascending; nearest first
    upcoming.sort(key=lambda e: getattr(e, "expected_date", date.max))
    nearest = upcoming[0]

    expected = getattr(nearest, "expected_date", None)
    if expected is None:
        return _CATALYST_TIMING_NONE, 0.30

    days_until = max(0, (expected - as_of).days)
    timing_score = _days_to_score(days_until, _CATALYST_TIMING_BINS, _CATALYST_TIMING_FAR)

    confidence_raw = getattr(nearest, "date_confidence", "estimate")
    confidence_score = _DATE_CONFIDENCE_SCORE.get(str(confidence_raw), 0.30)

    return timing_score, confidence_score


def _is_upcoming(event: object, as_of: date) -> bool:
    """Return True if the event is active, unresolved, and in the future."""
    if not getattr(event, "is_active", True):
        return False
    if getattr(event, "resolved", False):
        return False
    expected = getattr(event, "expected_date", None)
    if expected is None:
        return False
    return expected >= as_of


# ---------------------------------------------------------------------------
# Acquirer profile adapters
# ---------------------------------------------------------------------------

def acquirer_pull_row_from_profile(
    profile: object,
    *,
    target_ta: str,
    target_modality: str,
    target_ticker: str,
    as_of: date,
) -> AcquirerPullInputRow:
    """Build an AcquirerPullInputRow from a live AcquirerProfile.

    Parameters
    ----------
    profile:
        ``AcquirerProfile`` instance.
    target_ta:
        Therapeutic area of the acquisition target (e.g. ``"oncology"``).
    target_modality:
        Modality of the target asset (e.g. ``"small_molecule"``).
    target_ticker:
        Ticker/identifier of the target company.
    as_of:
        Reference date for freshness calculation.
    """
    ta_fit, pgu = _ta_fit_and_gap_urgency(profile, target_ta)
    modality_fit = _modality_fit(profile, target_modality)
    deal_appetite = _buyer_deal_appetite(profile, as_of)
    existing_rel = _existing_relationship(profile, target_ticker)

    profile_as_of = getattr(profile, "profile_as_of", None)
    freshness_days: Optional[int] = None
    if profile_as_of is not None:
        try:
            freshness_days = max(0, (as_of - profile_as_of).days)
        except Exception:
            pass

    acquirer_id = getattr(profile, "acquirer_id", "unknown")
    acquirer_name = getattr(profile, "company_name", acquirer_id)

    return AcquirerPullInputRow(
        acquirer_id=acquirer_id,
        acquirer_name=acquirer_name,
        ta_fit=ta_fit,
        modality_fit=modality_fit,
        pipeline_gap_urgency=pgu,
        buyer_deal_appetite=deal_appetite,
        existing_relationship=existing_rel,
        profile_freshness_days=freshness_days,
    )


def _ta_fit_and_gap_urgency(profile: object, target_ta: str) -> tuple[float, float]:
    """Return (ta_fit_score, pipeline_gap_urgency) for a TA match."""
    gaps = getattr(profile, "therapeutic_area_gaps", [])
    ta_lower = target_ta.lower()

    best_exposure: Optional[str] = None
    for gap in gaps:
        gap_ta = str(getattr(gap, "therapeutic_area", "")).lower()
        if gap_ta == ta_lower or ta_lower in gap_ta or gap_ta in ta_lower:
            exposure = str(getattr(gap, "exposure_level", "medium")).lower()
            # Keep the highest urgency match
            if best_exposure is None or _exposure_ordinal(exposure) > _exposure_ordinal(best_exposure):
                best_exposure = exposure

    if best_exposure is None:
        return _EXPOSURE_NO_MATCH, _EXPOSURE_NO_MATCH

    score = _EXPOSURE_SCORE.get(best_exposure, 0.50)
    return score, score


def _exposure_ordinal(level: str) -> int:
    return {"high": 2, "medium": 1, "low": 0}.get(level, 1)


def _modality_fit(profile: object, target_modality: str) -> float:
    """Return modality fit score based on preferred_modalities list."""
    prefs = getattr(profile, "preferred_modalities", [])
    mod_lower = target_modality.lower()

    best_pref: Optional[str] = None
    for pref in prefs:
        pref_mod = str(getattr(pref, "modality", "")).lower()
        if pref_mod == mod_lower or mod_lower in pref_mod or pref_mod in mod_lower:
            strength = str(getattr(pref, "preference_strength", "medium")).lower()
            if best_pref is None or _pref_ordinal(strength) > _pref_ordinal(best_pref):
                best_pref = strength

    if best_pref is None:
        return _MODALITY_NO_MATCH

    return _MODALITY_PREF_SCORE.get(best_pref, 0.50)


def _pref_ordinal(strength: str) -> int:
    return {"high": 2, "medium": 1, "low": 0}.get(strength, 1)


def _buyer_deal_appetite(profile: object, as_of: date) -> float:
    """Score deal appetite from recent deal history (last 24 months)."""
    deals = getattr(profile, "recent_deal_history", [])
    cutoff = date(as_of.year - 2, as_of.month, as_of.day)
    recent_count = 0
    for deal in deals:
        announced = getattr(deal, "announcement_date", None)
        if announced is not None and announced >= cutoff:
            recent_count += 1

    if not deals:
        return _DEAL_APPETITE_NO_HISTORY

    score = min(1.0, recent_count * _DEAL_APPETITE_PER_DEAL)
    # If deals list is non-empty but none recent, signal low appetite
    if recent_count == 0:
        return 0.25
    return score


def _existing_relationship(profile: object, target_ticker: str) -> float:
    """Return relationship score: 1.0 if acquisition_option, 0.85 if partnership, else 0.10."""
    partnerships = getattr(profile, "existing_partnerships", [])
    ticker_lower = target_ticker.lower()

    for p in partnerships:
        partner_target = str(getattr(p, "target", "")).lower()
        if partner_target == ticker_lower or ticker_lower in partner_target:
            has_option = getattr(p, "acquisition_option", False)
            return 0.95 if has_option else 0.85

    return 0.10


def acquirer_profile_freshness_score(
    profiles: list[object],
    as_of: date,
) -> float:
    """Score how fresh the acquirer profile data is overall.

    Uses the oldest profile's age to penalise staleness conservatively.
    Empty list → 0.20 (very stale / no data).
    """
    if not profiles:
        return 0.20

    ages: list[int] = []
    for p in profiles:
        profile_as_of = getattr(p, "profile_as_of", None)
        if profile_as_of is not None:
            try:
                ages.append(max(0, (as_of - profile_as_of).days))
            except Exception:
                pass

    if not ages:
        return 0.50  # unknown freshness

    # Use oldest profile to be conservative
    worst_age = max(ages)
    return _days_to_score(worst_age, _FRESHNESS_BINS, _FRESHNESS_STALE)


def pipeline_gap_urgency_from_profiles(
    profiles: list[object],
    target_ta: str,
) -> float:
    """Compute buyer-side pipeline gap urgency across all profiles for a TA.

    Returns the maximum urgency score across all acquirer profiles that have
    a matching therapeutic area gap.  Falls back to a neutral 0.50 when no
    profiles match.
    """
    if not profiles:
        return 0.50

    scores: list[float] = []
    for p in profiles:
        _, pgu = _ta_fit_and_gap_urgency(p, target_ta)
        if pgu > _EXPOSURE_NO_MATCH:
            scores.append(pgu)

    if not scores:
        return 0.30  # no acquirer has this TA as a gap

    return max(scores)


def loe_revenue_cliff_urgency_from_profiles(
    profiles: list[object],
    target_ta: str,
) -> float:
    """Infer LOE / revenue cliff urgency from acquirer strategic priorities.

    Looks for strategic priorities referencing LOE, patent cliff, or revenue
    diversification.  Returns urgency score based on priority_strength.
    Falls back to neutral 0.50 when no matching signals found.
    """
    if not profiles:
        return 0.50

    loe_keywords = {"loe", "patent", "cliff", "loss of exclusivity", "revenue gap",
                    "revenue cliff", "diversif", "pipeline replenish"}

    for p in profiles:
        priorities = getattr(p, "strategic_priorities", [])
        for sp in priorities:
            text = (str(getattr(sp, "priority", "")) + " " +
                    str(getattr(sp, "rationale", "") if hasattr(sp, "rationale") else "")).lower()
            if any(kw in text for kw in loe_keywords):
                strength = str(getattr(sp, "priority_strength", "medium")).lower()
                return {"high": 0.90, "medium": 0.70, "low": 0.45}.get(strength, 0.60)

        # Also check TA gaps for LOE signals in notes
        for gap in getattr(p, "therapeutic_area_gaps", []):
            notes = str(getattr(gap, "notes", "") or "").lower()
            rationale = str(getattr(gap, "rationale", "") or "").lower()
            combined = notes + " " + rationale
            if any(kw in combined for kw in loe_keywords):
                exposure = str(getattr(gap, "exposure_level", "medium")).lower()
                return _EXPOSURE_SCORE.get(exposure, 0.60)

    return 0.50


# ---------------------------------------------------------------------------
# Layer 0 encumbrance adapter
# ---------------------------------------------------------------------------

def rights_encumbrance_clarity_from_layer0(layer0: object) -> float:
    """Score rights/IP clarity from Layer 0 encumbrance result.

    Uses ``Layer0Result.encumbrance.asset_control_score``.
    Higher asset_control_score = cleaner rights = higher clarity score.
    """
    encumbrance = getattr(layer0, "encumbrance", None)
    if encumbrance is None:
        return 0.50

    score = getattr(encumbrance, "asset_control_score", None)
    if score is None:
        return 0.50

    return float(score)


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------

def build_layer2_inputs(
    *,
    target_name: str,
    layer1_output: Optional[object] = None,
    financing_assessment: Optional[object] = None,
    catalyst_events: Optional[list[object]] = None,
    acquirer_profiles: Optional[list[object]] = None,
    layer0_result: Optional[object] = None,
    target_ta: str = "",
    target_modality: str = "",
    target_ticker: str = "",
    as_of_date: Optional[date] = None,
    # Pass-through overrides (explicit caller values win over wired)
    seller_openness: Optional[float] = None,
    governance_activist_pressure: Optional[float] = None,
    competitive_fomo: Optional[float] = None,
    recent_bd_pattern: Optional[float] = None,
    strategic_priority_recency: Optional[float] = None,
    acquirer_strategic_fit: Optional[float] = None,
    strategic_option_value: Optional[float] = None,
    transaction_driver_source_quality: Optional[float] = None,
    # Layer 3-only pass-through
    affordability_override: Optional[float] = None,
    antitrust_risk: Optional[float] = None,
    rofr_impact: Optional[float] = None,
    integration_feasibility: Optional[float] = None,
) -> Layer2Inputs:
    """Assemble a Layer2Inputs from live engine outputs.

    Only the wired fields are populated from real data sources.  All other
    Layer 2 inputs remain None (engine uses neutral 0.50 fallback).

    Parameters that can be overridden by the caller are accepted as keyword
    arguments so they propagate cleanly through the sub-group input models.

    Parameters
    ----------
    target_name:
        Display name of the BD target.
    layer1_output:
        Live ``Layer1Output`` — auto-populates strategic priority fields.
    financing_assessment:
        Live ``FinancingAssessment`` — populates financing_pressure,
        valuation_distress, and valuation_data_freshness.
    catalyst_events:
        List of ``CatalystEvent`` for this target — populates catalyst_timing
        and catalyst_date_confidence.
    acquirer_profiles:
        List of ``AcquirerProfile`` objects — populates acquirer pull rows,
        pipeline_gap_urgency, loe_revenue_cliff_urgency, and
        acquirer_profile_freshness.
    layer0_result:
        ``Layer0Result`` — populates rights_encumbrance_clarity.
    target_ta:
        Therapeutic area of the target asset.
    target_modality:
        Modality of the target asset.
    target_ticker:
        Ticker/identifier of the target company.
    as_of_date:
        Reference date; defaults to ``date.today()``.
    """
    as_of = as_of_date or date.today()
    events = catalyst_events or []
    profiles = acquirer_profiles or []

    # ── Target-side pressure ──────────────────────────────────────────────
    financing_pressure: Optional[float] = None
    valuation_distress: Optional[float] = None
    catalyst_timing: Optional[float] = None
    catalyst_date_confidence: Optional[float] = None

    if financing_assessment is not None:
        financing_pressure = financing_pressure_from_assessment(financing_assessment)
        valuation_distress = valuation_distress_from_assessment(financing_assessment)

    if events:
        catalyst_timing, catalyst_date_confidence = catalyst_timing_from_events(events, as_of)

    # ── Buyer-side urgency ────────────────────────────────────────────────
    pgu_buyer: Optional[float] = None
    loe_urgency: Optional[float] = None

    if profiles and target_ta:
        pgu_buyer = pipeline_gap_urgency_from_profiles(profiles, target_ta)
        loe_urgency = loe_revenue_cliff_urgency_from_profiles(profiles, target_ta)

    # ── Acquirer pull rows ────────────────────────────────────────────────
    pull_rows: list[AcquirerPullInputRow] = []
    if profiles:
        for p in profiles:
            row = acquirer_pull_row_from_profile(
                p,
                target_ta=target_ta,
                target_modality=target_modality,
                target_ticker=target_ticker,
                as_of=as_of,
            )
            pull_rows.append(row)

    # ── Information readiness ─────────────────────────────────────────────
    layer1_confidence: Optional[float] = None
    if layer1_output is not None:
        layer1_confidence = getattr(layer1_output, "overall_confidence", None)

    profile_freshness: Optional[float] = None
    if profiles:
        profile_freshness = acquirer_profile_freshness_score(profiles, as_of)

    val_data_freshness: Optional[float] = None
    if financing_assessment is not None:
        val_data_freshness = valuation_data_freshness_from_assessment(financing_assessment, as_of)

    encumbrance_clarity: Optional[float] = None
    if layer0_result is not None:
        encumbrance_clarity = rights_encumbrance_clarity_from_layer0(layer0_result)

    # ── Assemble sub-group inputs ─────────────────────────────────────────
    sp_inputs = Layer2StrategicPriorityInputs(
        acquirer_strategic_fit=acquirer_strategic_fit,
        strategic_option_value=strategic_option_value,
        # layer1 fields auto-populated by the engine from layer1_output
    )

    tsp_inputs = Layer2TargetSidePressureInputs(
        financing_pressure=financing_pressure,
        seller_openness=seller_openness,
        catalyst_timing=catalyst_timing,
        valuation_distress=valuation_distress,
        governance_activist_pressure=governance_activist_pressure,
    )

    bsu_inputs = Layer2BuyerSideUrgencyInputs(
        pipeline_gap_urgency=pgu_buyer,
        loe_revenue_cliff_urgency=loe_urgency,
        competitive_fomo=competitive_fomo,
        recent_bd_pattern=recent_bd_pattern,
        strategic_priority_recency=strategic_priority_recency,
    )

    ir_inputs = Layer2InformationReadinessInputs(
        layer1_confidence=layer1_confidence,
        acquirer_profile_freshness=profile_freshness,
        transaction_driver_source_quality=transaction_driver_source_quality,
        valuation_data_freshness=val_data_freshness,
        rights_encumbrance_clarity=encumbrance_clarity,
        catalyst_date_confidence=catalyst_date_confidence,
    )

    return Layer2Inputs(
        target_name=target_name,
        layer1_output=layer1_output,
        strategic_priority=sp_inputs,
        target_side_pressure=tsp_inputs,
        buyer_side_urgency=bsu_inputs,
        acquirer_pull=pull_rows,
        information_readiness=ir_inputs,
        affordability_override=affordability_override,
        antitrust_risk=antitrust_risk,
        rofr_impact=rofr_impact,
        integration_feasibility=integration_feasibility,
    )


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _days_to_score(
    days: int,
    bins: list[tuple[int, float]],
    fallback: float,
) -> float:
    """Map an age/proximity in days to a score using ordered bins."""
    for threshold, score in bins:
        if days <= threshold:
            return score
    return fallback

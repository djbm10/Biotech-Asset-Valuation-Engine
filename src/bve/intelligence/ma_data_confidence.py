"""
0G — Data Confidence Output

Purpose:
    Measure how much the model should trust its own M&A score.

Two dimensions per data category:
    1. Completeness  — do we have the fields?
    2. Reliability   — do we trust the fields? (source quality + freshness)

Example: market cap may be complete but stale. Partner rights may exist
but come only from an investor deck, not a contract or 10-K.

Five categories with composite weights:
    financial_data     0.30  (cash, debt, burn, runway, revenue mix)
    asset_data         0.25  (clinical stage, trial status, ownership)
    rights_ip_data     0.20  (partner rights, patents, LOE, ROFR)
    market_data        0.15  (market cap, enterprise value, price/liquidity)
    acquirer_data      0.10  (acquirer profile, TA priorities, deal capacity)

Special rule — rights/IP gate:
    If rights_ip_data confidence < 0.50:
        cap label at MEDIUM (cannot rank above Medium)
    Rationale: M&A depends heavily on whether the buyer can actually own the asset.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DataConfidenceLabel(str, Enum):
    """Data confidence grade (completeness × reliability composite)."""
    HIGH     = "high"      # ≥ 0.80  — eligible for ranked output
    MEDIUM   = "medium"    # 0.60–0.79 — eligible but flagged
    LOW      = "low"       # 0.40–0.59 — diligence queue by default
    VERY_LOW = "very_low"  # < 0.40  — exclude from ranking


class RankingTreatment(str, Enum):
    ELIGIBLE_RANKED  = "eligible_ranked"   # HIGH
    ELIGIBLE_FLAGGED = "eligible_flagged"  # MEDIUM
    DILIGENCE_QUEUE  = "diligence_queue"   # LOW
    EXCLUDE          = "exclude"           # VERY_LOW


# Source quality scores — maps named sources to 0–1 reliability
SOURCE_QUALITY_SCORES: dict[str, float] = {
    "sec_filing":          0.95,
    "annual_report":       0.90,
    "quarterly_report":    0.90,
    "trial_registry":      0.85,
    "press_release":       0.75,
    "earnings_transcript": 0.70,
    "news_article":        0.55,
    "investor_deck":       0.45,
    "manual_note":         0.35,
    "unknown":             0.50,
}


def source_quality(source: str) -> float:
    """Return 0–1 reliability score for a named data source."""
    return SOURCE_QUALITY_SCORES.get(source.lower(), SOURCE_QUALITY_SCORES["unknown"])


# ---------------------------------------------------------------------------
# Input model
# ---------------------------------------------------------------------------

class DataConfidenceInput(BaseModel):
    """All inputs needed for the 0G Data Confidence computation."""
    model_config = ConfigDict(frozen=True)

    # ── Market data ────────────────────────────────────────────────────────
    has_market_cap: bool = False
    has_enterprise_value: bool = False
    market_data_source_quality: float = Field(default=0.70, ge=0.0, le=1.0,
        description="0.95=SEC; 0.70=market data provider; 0.45=investor deck")
    market_data_fresh: bool = True

    # ── Financial data ─────────────────────────────────────────────────────
    has_cash_debt: bool = False
    has_quarterly_burn: bool = False
    has_revenue_mix: bool = False
    financial_data_source_quality: float = Field(default=0.70, ge=0.0, le=1.0)
    financial_data_fresh: bool = True

    # ── Asset data ─────────────────────────────────────────────────────────
    has_clinical_stage: bool = False
    has_trial_status: bool = False
    has_asset_ownership_data: bool = False
    asset_data_source_quality: float = Field(default=0.70, ge=0.0, le=1.0)
    asset_data_fresh: bool = True

    # ── Rights / IP data (lower default — often from investor decks) ───────
    has_partner_rights_data: bool = False
    has_patent_loe_data: bool = False
    rights_ip_source_quality: float = Field(default=0.50, ge=0.0, le=1.0,
        description="Rights data from 10-K=0.90; investor deck=0.45; unknown=0.50")
    rights_ip_data_fresh: bool = True

    # ── Acquirer profile data ──────────────────────────────────────────────
    has_acquirer_profile_data: bool = False
    acquirer_data_source_quality: float = Field(default=0.60, ge=0.0, le=1.0)
    acquirer_data_fresh: bool = True

    # ── Explicit field-level overrides (optional diagnostic lists) ─────────
    stale_fields: list[str] = Field(default_factory=list)
    low_reliability_fields: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------

class DataConfidenceResult(BaseModel):
    """Complete 0G Data Confidence output.

    Primary fields (spec names):
        data_confidence_score, confidence_label, category_scores,
        missing_fields, stale_fields, low_reliability_fields,
        source_quality_summary, ranking_treatment, rationale

    Backward-compatibility aliases (old DataConfidenceResult contract):
        grade  (= confidence_label)
        score  (= data_confidence_score)
        eligible_for_ranked_output
        eligible_for_diligence_queue
    """
    model_config = ConfigDict(frozen=True)

    # ── Spec-defined primary fields ────────────────────────────────────────
    data_confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_label: DataConfidenceLabel

    category_scores: dict[str, float]   # category → confidence score (0–1)

    missing_fields: list[str]
    stale_fields: list[str]
    low_reliability_fields: list[str]
    source_quality_summary: dict[str, float]  # category → source_quality value
    ranking_treatment: RankingTreatment
    rationale: list[str]

    # ── Critical field cap results ─────────────────────────────────────────
    critical_field_caps: list[str] = Field(default_factory=list,
        description="Reasons why confidence label was reduced by a critical field ceiling rule")
    field_cap_applied: bool = Field(default=False,
        description="True when at least one critical-field cap reduced the label below the composite score")

    # ── Backward-compatibility aliases ─────────────────────────────────────
    grade: DataConfidenceLabel           # = confidence_label
    score: float                         # = data_confidence_score
    eligible_for_ranked_output: bool     # HIGH or MEDIUM
    eligible_for_diligence_queue: bool   # MEDIUM or LOW


# ---------------------------------------------------------------------------
# Category weights (must sum to 1.0)
# ---------------------------------------------------------------------------

_CATEGORY_WEIGHTS: dict[str, float] = {
    "financial": 0.30,
    "asset":     0.25,
    "rights_ip": 0.20,
    "market":    0.15,
    "acquirer":  0.10,
}
assert abs(sum(_CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9

_FRESHNESS_PENALTY = 0.80   # staleness reduces reliability to 80%
_RIGHTS_IP_CAP_THRESHOLD = 0.50   # below this → cannot rank above MEDIUM

# Label ordinal — lower number = worse confidence
_LABEL_ORDINAL: dict[str, int] = {
    "high":     3,
    "medium":   2,
    "low":      1,
    "very_low": 0,
}

# Critical field cap rules: (cap_label, condition_name, rationale)
# Applied after composite + rights/IP gate; take the most restrictive cap.
_CRITICAL_FIELD_CAPS: list[tuple[str, str, str]] = [
    (
        "low",
        "no_asset_profile",
        "has_clinical_stage and has_trial_status both missing — no asset profile available → cap LOW",
    ),
    (
        "low",
        "no_valuation_data",
        "has_market_cap and has_enterprise_value both missing — valuation impossible → cap LOW",
    ),
    (
        "medium",
        "no_asset_ownership_data",
        "has_asset_ownership_data missing — encumbrance cannot be assessed → cap MEDIUM",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _completeness(flags: list[bool]) -> float:
    if not flags:
        return 0.0
    return sum(flags) / len(flags)


def _reliability(source_quality: float, fresh: bool) -> float:
    return round(source_quality * (1.0 if fresh else _FRESHNESS_PENALTY), 4)


def _label(score: float) -> DataConfidenceLabel:
    if score >= 0.80:
        return DataConfidenceLabel.HIGH
    if score >= 0.60:
        return DataConfidenceLabel.MEDIUM
    if score >= 0.40:
        return DataConfidenceLabel.LOW
    return DataConfidenceLabel.VERY_LOW


def _ranking_treatment(label: DataConfidenceLabel) -> RankingTreatment:
    return {
        DataConfidenceLabel.HIGH:     RankingTreatment.ELIGIBLE_RANKED,
        DataConfidenceLabel.MEDIUM:   RankingTreatment.ELIGIBLE_FLAGGED,
        DataConfidenceLabel.LOW:      RankingTreatment.DILIGENCE_QUEUE,
        DataConfidenceLabel.VERY_LOW: RankingTreatment.EXCLUDE,
    }[label]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_data_confidence(inp: DataConfidenceInput) -> DataConfidenceResult:
    """Compute 0G Data Confidence for a target.

    Each category confidence = completeness × reliability.
    Composite = weighted sum across 5 categories.
    Special rule: rights_ip confidence < 0.50 → label capped at MEDIUM.
    """
    # ── Per-category scores ────────────────────────────────────────────────
    cat_completeness: dict[str, float] = {
        "market":    _completeness([inp.has_market_cap, inp.has_enterprise_value]),
        "financial": _completeness([inp.has_cash_debt, inp.has_quarterly_burn, inp.has_revenue_mix]),
        "asset":     _completeness([inp.has_clinical_stage, inp.has_trial_status, inp.has_asset_ownership_data]),
        "rights_ip": _completeness([inp.has_partner_rights_data, inp.has_patent_loe_data]),
        "acquirer":  _completeness([inp.has_acquirer_profile_data]),
    }
    cat_reliability: dict[str, float] = {
        "market":    _reliability(inp.market_data_source_quality, inp.market_data_fresh),
        "financial": _reliability(inp.financial_data_source_quality, inp.financial_data_fresh),
        "asset":     _reliability(inp.asset_data_source_quality, inp.asset_data_fresh),
        "rights_ip": _reliability(inp.rights_ip_source_quality, inp.rights_ip_data_fresh),
        "acquirer":  _reliability(inp.acquirer_data_source_quality, inp.acquirer_data_fresh),
    }
    cat_scores: dict[str, float] = {
        cat: round(cat_completeness[cat] * cat_reliability[cat], 4)
        for cat in _CATEGORY_WEIGHTS
    }

    # ── Composite ─────────────────────────────────────────────────────────
    raw_score = round(
        sum(cat_scores[cat] * _CATEGORY_WEIGHTS[cat] for cat in _CATEGORY_WEIGHTS),
        4,
    )

    label = _label(raw_score)

    # ── Rights/IP gate: cap at MEDIUM if rights data is unreliable ─────────
    rights_ip_capped = False
    if cat_scores["rights_ip"] < _RIGHTS_IP_CAP_THRESHOLD:
        if label == DataConfidenceLabel.HIGH:
            label = DataConfidenceLabel.MEDIUM
            rights_ip_capped = True

    # ── Critical field caps: ceiling rules based on missing key fields ──────
    critical_caps_applied: list[str] = []
    label_before_field_caps = label
    for cap_label_str, condition_name, rationale_text in _CRITICAL_FIELD_CAPS:
        # Evaluate condition
        if condition_name == "no_asset_profile":
            fired = not inp.has_clinical_stage and not inp.has_trial_status
        elif condition_name == "no_valuation_data":
            fired = not inp.has_market_cap and not inp.has_enterprise_value
        elif condition_name == "no_asset_ownership_data":
            fired = not inp.has_asset_ownership_data
        else:
            fired = False

        if fired:
            cap_label = DataConfidenceLabel(cap_label_str)
            if _LABEL_ORDINAL[cap_label.value] < _LABEL_ORDINAL[label.value]:
                label = cap_label
                critical_caps_applied.append(f"{condition_name}: {rationale_text}")

    field_cap_applied = label != label_before_field_caps

    treatment = _ranking_treatment(label)

    # ── Missing fields (completeness = 0 for any has_* flag) ──────────────
    missing: list[str] = []
    flag_names = [
        ("has_market_cap",          "market_cap"),
        ("has_enterprise_value",    "enterprise_value"),
        ("has_cash_debt",           "cash_debt"),
        ("has_quarterly_burn",      "quarterly_burn"),
        ("has_revenue_mix",         "revenue_mix"),
        ("has_clinical_stage",      "clinical_stage"),
        ("has_trial_status",        "trial_status"),
        ("has_asset_ownership_data", "asset_ownership_data"),
        ("has_partner_rights_data", "partner_rights_data"),
        ("has_patent_loe_data",     "patent_loe_data"),
        ("has_acquirer_profile_data", "acquirer_profile_data"),
    ]
    for attr, name in flag_names:
        if not getattr(inp, attr):
            missing.append(name)

    # ── Stale fields (freshness = False → category is stale) ──────────────
    stale: list[str] = list(inp.stale_fields)
    freshness_map = {
        "market_data":    inp.market_data_fresh,
        "financial_data": inp.financial_data_fresh,
        "asset_data":     inp.asset_data_fresh,
        "rights_ip_data": inp.rights_ip_data_fresh,
        "acquirer_data":  inp.acquirer_data_fresh,
    }
    for category, fresh in freshness_map.items():
        if not fresh and category not in stale:
            stale.append(category)

    # ── Low-reliability fields ─────────────────────────────────────────────
    low_rel: list[str] = list(inp.low_reliability_fields)
    for cat, rel in cat_reliability.items():
        label_key = f"{cat}_data"
        if rel < 0.50 and label_key not in low_rel:
            low_rel.append(label_key)

    # ── Source quality summary ─────────────────────────────────────────────
    sq_summary = {
        "market":    round(inp.market_data_source_quality, 3),
        "financial": round(inp.financial_data_source_quality, 3),
        "asset":     round(inp.asset_data_source_quality, 3),
        "rights_ip": round(inp.rights_ip_source_quality, 3),
        "acquirer":  round(inp.acquirer_data_source_quality, 3),
    }

    # ── Rationale ──────────────────────────────────────────────────────────
    rationale: list[str] = [
        f"data_confidence={raw_score:.3f}  label={label.value}  treatment={treatment.value}",
        "category_scores: " + "  ".join(
            f"{c}={cat_scores[c]:.2f}" for c in _CATEGORY_WEIGHTS
        ),
    ]
    if rights_ip_capped:
        rationale.append(
            f"rights_ip_gate: rights_ip_confidence={cat_scores['rights_ip']:.2f} < "
            f"{_RIGHTS_IP_CAP_THRESHOLD} → label capped at MEDIUM "
            "(cannot rank above Medium without reliable rights/IP data)"
        )
    for cap_reason in critical_caps_applied:
        rationale.append(f"critical_field_cap: {cap_reason}")
    if missing:
        rationale.append(f"missing_fields({len(missing)}): {', '.join(missing[:5])}"
                         + ("…" if len(missing) > 5 else ""))
    if stale:
        rationale.append(f"stale_categories: {', '.join(stale)}")

    return DataConfidenceResult(
        data_confidence_score=raw_score,
        confidence_label=label,
        category_scores=cat_scores,
        missing_fields=missing,
        stale_fields=stale,
        low_reliability_fields=low_rel,
        source_quality_summary=sq_summary,
        ranking_treatment=treatment,
        rationale=rationale,
        critical_field_caps=critical_caps_applied,
        field_cap_applied=field_cap_applied,
        # backward-compat aliases
        grade=label,
        score=raw_score,
        eligible_for_ranked_output=(label in (DataConfidenceLabel.HIGH, DataConfidenceLabel.MEDIUM)),
        eligible_for_diligence_queue=(label in (DataConfidenceLabel.MEDIUM, DataConfidenceLabel.LOW)),
    )


# ---------------------------------------------------------------------------
# Target adapter
# ---------------------------------------------------------------------------

def data_confidence_from_target(t: object) -> DataConfidenceInput:
    """Map a TargetEligibilityInput (or compatible object) to DataConfidenceInput."""
    def _g(attr: str, default):
        return getattr(t, attr, default)

    return DataConfidenceInput(
        # Market
        has_market_cap=_g("has_market_cap", False),
        has_enterprise_value=_g("has_enterprise_value", False),
        market_data_source_quality=_g("market_data_source_quality", 0.70),
        market_data_fresh=_g("market_data_fresh", True),
        # Financial
        has_cash_debt=_g("has_cash_debt", False),
        has_quarterly_burn=_g("has_quarterly_burn", False),
        has_revenue_mix=_g("has_revenue_mix", False),
        financial_data_source_quality=_g("financial_data_source_quality", 0.70),
        financial_data_fresh=_g("financial_data_fresh", True),
        # Asset
        has_clinical_stage=_g("has_clinical_stage", False),
        has_trial_status=_g("has_trial_status", False),
        has_asset_ownership_data=_g("has_asset_ownership_data", False),
        asset_data_source_quality=_g("asset_data_source_quality", 0.70),
        asset_data_fresh=_g("asset_data_fresh", True),
        # Rights/IP
        has_partner_rights_data=_g("has_partner_rights_data", False),
        has_patent_loe_data=_g("has_patent_loe_data", False),
        rights_ip_source_quality=_g("rights_ip_source_quality", 0.50),
        rights_ip_data_fresh=_g("rights_ip_data_fresh", True),
        # Acquirer
        has_acquirer_profile_data=_g("has_acquirer_profile_data", False),
        acquirer_data_source_quality=_g("acquirer_data_source_quality", 0.60),
        acquirer_data_fresh=_g("acquirer_data_fresh", True),
        # Explicit overrides
        stale_fields=_g("stale_field_names", []),
        low_reliability_fields=_g("low_reliability_field_names", []),
    )

"""
Management execution risk scoring model.

Scores a biotech management team on a 0.0–1.0 scale using observable,
publicly available signals: FDA approval track record, guidance credibility,
capital discipline, strategic validation, and identified red flags.

The score is converted to a tier (strong / adequate / weak / unknown) and
three downstream modifiers used by the valuation engine:

  timeline_confidence_modifier  — multiplier on trial duration estimates
  financing_risk_modifier       — additive risk premium on cost of capital
  execution_risk_modifier       — log-odds adjustment on trial completion POS

No proprietary data or machine learning is required; all adjusters are
documented with business rationale and can be audited by an analyst.

Reference: Hamilton (2019) "Management Quality in Biotech" JPM Healthcare;
Biomedtracker execution risk framework; internal calibration from BVE Sprint 31.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ManagementRecord:
    """Observable signals for management quality assessment."""
    prior_fda_approvals: int = 0            # FDA approvals under current leadership
    prior_fda_failures: int = 0             # CRLs, Phase 3 failures, discontinuations
    years_experience_oncology: int = 0      # team experience in the indication class
    dilution_events_3yr: int = 0            # equity raises (ATM, PIPE, follow-on) in 3yr
    guidance_hits_3yr: int = 0              # times hit / beat guidance in 3yr
    guidance_misses_3yr: int = 0            # times missed guidance in 3yr
    strategic_partnerships: int = 0         # active big-pharma co-dev / license deals
    insider_buying_recent: bool = False     # net insider buying in last 6 months
    ceo_turnover_2yr: bool = False          # CEO change in last 2 years
    operational_stumble: bool = False       # disclosed clinical hold, manufacturing issue, etc.


@dataclass(frozen=True)
class ManagementRiskScore:
    """Composite management risk assessment."""
    raw_score: float                        # 0.0 (worst) to 1.0 (best)
    tier: str                               # "strong" / "adequate" / "weak" / "unknown"
    timeline_confidence_modifier: float     # multiplier on timeline estimates (0.85–1.10)
    financing_risk_modifier: float          # 0=no change; positive=more risk
    execution_risk_modifier: float          # log-odds adjustment on trial completion POS
    strengths: list[str]
    concerns: list[str]
    data_completeness: float                # fraction of ManagementRecord fields that are non-default


# ---------------------------------------------------------------------------
# Tier thresholds and tier-level modifiers
# ---------------------------------------------------------------------------

_TIER_TIMELINE_CONFIDENCE: dict[str, float] = {
    "strong":   1.05,
    "adequate": 1.00,
    "weak":     0.92,
    "unknown":  0.95,
}

_TIER_FINANCING_RISK: dict[str, float] = {
    "strong":   -0.05,
    "adequate":  0.00,
    "weak":     +0.10,
    "unknown":  +0.05,
}

_TIER_EXECUTION_RISK: dict[str, float] = {
    "strong":   +0.05,
    "adequate":  0.00,
    "weak":     -0.10,
    "unknown":  -0.03,
}

_SCORE_FLOOR: float = 0.10
_SCORE_CEILING: float = 0.95
_BASE_SCORE: float = 0.55


# ---------------------------------------------------------------------------
# Public scoring function
# ---------------------------------------------------------------------------

def score_management(record: ManagementRecord) -> ManagementRiskScore:
    """
    Score management execution quality from observable signals.

    Parameters
    ----------
    record:
        ManagementRecord populated from public filings, press releases,
        and analyst research.

    Returns
    -------
    ManagementRiskScore with tier classification, three downstream
    valuation modifiers, and itemised strengths / concerns.
    """
    strengths: list[str] = []
    concerns: list[str] = []

    delta = 0.0

    # -- Approval track record -----------------------------------------------

    approval_bonus = min(0.12 * record.prior_fda_approvals, 0.24)
    if approval_bonus > 0.0:
        delta += approval_bonus
        strengths.append(
            f"FDA approval track record: {record.prior_fda_approvals} approval(s) under current leadership"
        )

    failure_penalty = max(-0.08 * record.prior_fda_failures, -0.16)
    if failure_penalty < 0.0:
        delta += failure_penalty
        concerns.append(
            f"Prior FDA failures: {record.prior_fda_failures} CRL / Phase 3 discontinuation(s)"
        )

    # -- Guidance credibility ------------------------------------------------

    total_guidance = record.guidance_hits_3yr + record.guidance_misses_3yr
    guidance_ratio = record.guidance_hits_3yr / max(total_guidance, 1)
    guidance_bonus = guidance_ratio * 0.15
    delta += guidance_bonus
    if guidance_ratio >= 0.75 and total_guidance >= 2:
        strengths.append(
            f"Strong guidance credibility: {record.guidance_hits_3yr}/{total_guidance} hits in 3yr"
        )
    elif record.guidance_misses_3yr > record.guidance_hits_3yr and total_guidance >= 2:
        concerns.append(
            f"Guidance credibility concern: {record.guidance_misses_3yr}/{total_guidance} misses in 3yr"
        )

    # -- Capital / dilution discipline ---------------------------------------

    excess_dilution = max(record.dilution_events_3yr - 2, 0)
    dilution_penalty = max(-0.05 * excess_dilution, -0.10)
    if dilution_penalty < 0.0:
        delta += dilution_penalty
        concerns.append(
            f"Elevated dilution: {record.dilution_events_3yr} equity raise(s) in 3yr "
            f"(>{2} threshold)"
        )

    # -- Strategic validation ------------------------------------------------

    partnership_bonus = min(0.06 * record.strategic_partnerships, 0.12)
    if partnership_bonus > 0.0:
        delta += partnership_bonus
        strengths.append(
            f"Strategic partnerships: {record.strategic_partnerships} active big-pharma co-dev/license deal(s)"
        )

    # -- Insider alignment ---------------------------------------------------

    if record.insider_buying_recent:
        delta += 0.05
        strengths.append("Insider buying: net insider purchases in last 6 months")

    # -- Red flags -----------------------------------------------------------

    if record.ceo_turnover_2yr:
        delta -= 0.10
        concerns.append("CEO turnover in last 2 years: leadership continuity risk")

    if record.operational_stumble:
        delta -= 0.08
        concerns.append(
            "Operational stumble: disclosed clinical hold, manufacturing issue, or equivalent"
        )

    if record.years_experience_oncology < 5:
        delta -= 0.05
        concerns.append(
            f"Limited indication experience: {record.years_experience_oncology} year(s) "
            f"in oncology (threshold: 5)"
        )

    # -- Composite score -----------------------------------------------------

    raw_score = float(
        max(_SCORE_FLOOR, min(_SCORE_CEILING, _BASE_SCORE + delta))
    )

    data_completeness = _compute_data_completeness(record)
    tier = _classify_tier(raw_score, data_completeness)

    return ManagementRiskScore(
        raw_score=round(raw_score, 4),
        tier=tier,
        timeline_confidence_modifier=_TIER_TIMELINE_CONFIDENCE[tier],
        financing_risk_modifier=_TIER_FINANCING_RISK[tier],
        execution_risk_modifier=_TIER_EXECUTION_RISK[tier],
        strengths=strengths,
        concerns=concerns,
        data_completeness=round(data_completeness, 4),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_tier(raw_score: float, data_completeness: float) -> str:
    """Map a raw score to a management quality tier."""
    if data_completeness < 0.30:
        return "unknown"
    if raw_score >= 0.75:
        return "strong"
    if raw_score >= 0.55:
        return "adequate"
    if raw_score >= 0.35:
        return "weak"
    return "unknown"


def _compute_data_completeness(record: ManagementRecord) -> float:
    """
    Return the fraction of ManagementRecord fields that differ from their defaults.

    A field counts as "provided" when its value deviates from the dataclass
    default, indicating that an analyst has explicitly populated it.
    """
    defaults = ManagementRecord()
    all_fields = dataclasses.fields(record)
    populated = sum(
        1
        for f in all_fields
        if getattr(record, f.name) != getattr(defaults, f.name)
    )
    return populated / len(all_fields)

"""Phase E timeline distribution model."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TimelineDistributionInputs(BaseModel):
    years_to_approval: float = Field(ge=0.0)
    regulatory_risk_score: float = Field(ge=0.0, le=1.0)
    design_score: float = Field(ge=0.0, le=1.0)
    financing_risk_score: float = Field(ge=0.0, le=1.0)


class TimelineDistributionResult(BaseModel):
    on_time_years: float = Field(ge=0.0)
    delayed_years: float = Field(ge=0.0)
    delay_probability: float = Field(ge=0.0, le=1.0)
    rationale: str


def infer_timeline_distribution(inputs: TimelineDistributionInputs) -> TimelineDistributionResult:
    delay_probability = (
        ((1.0 - inputs.design_score) * 0.35)
        + ((1.0 - inputs.regulatory_risk_score) * 0.45)
        + (inputs.financing_risk_score * 0.20)
    )
    delay_probability = round(max(0.0, min(1.0, delay_probability)), 4)
    on_time = round(inputs.years_to_approval, 2)
    delayed = round(inputs.years_to_approval + max(0.5, 1.5 * delay_probability), 2)
    return TimelineDistributionResult(
        on_time_years=on_time,
        delayed_years=delayed,
        delay_probability=delay_probability,
        rationale="Delay probability increases with weaker design, weaker regulatory posture, and financing stress.",
    )


# ---------------------------------------------------------------------------
# Step 7: TimelineRisk + PhaseTimeline + TimelineDistribution — new types
# ---------------------------------------------------------------------------


class TimelineRisk(str, Enum):
    ON_TRACK = "on_track"
    MINOR_DELAY = "minor_delay"
    MAJOR_DELAY = "major_delay"
    HOLD = "hold"
    TERMINATED = "terminated"


PHASE_DURATIONS: dict[str, dict[str, float]] = {
    "phase1": {"p10": 12.0, "p50": 18.0, "p90": 30.0},
    "phase2": {"p10": 18.0, "p50": 30.0, "p90": 48.0},
    "phase3": {"p10": 24.0, "p50": 42.0, "p90": 60.0},
    "nda_bla": {"p10": 10.0, "p50": 14.0, "p90": 22.0},
}

PHASE_ORDER: list[str] = ["phase1", "phase2", "phase3", "nda_bla"]


class PhaseTimeline(BaseModel):
    """Per-phase timeline with percentile distribution."""

    model_config = {"frozen": True}

    phase: str
    expected_duration_months: float
    p10_months: float
    p50_months: float
    p90_months: float
    delay_risk: TimelineRisk
    delay_probability: float


class TimelineDistributionV2(BaseModel):
    """Step 7 full timeline distribution across remaining phases."""

    model_config = {"frozen": True}

    asset_id: str
    current_phase: str
    phases_remaining: list[PhaseTimeline]
    expected_approval_months: float
    p10_approval_months: float
    p50_approval_months: float
    p90_approval_months: float
    overall_delay_prob: float
    catalyst_months_away: "float | None"
    rationale: str


def _delay_risk_from_prob(prob: float) -> TimelineRisk:
    if prob < 0.20:
        return TimelineRisk.ON_TRACK
    elif prob < 0.35:
        return TimelineRisk.MINOR_DELAY
    elif prob < 0.50:
        return TimelineRisk.MAJOR_DELAY
    else:
        return TimelineRisk.HOLD


def compute_timeline_distribution(
    asset_id: str,
    current_phase: str,
    has_fast_track: bool = False,
    has_breakthrough: bool = False,
    enrollment_on_track: bool = True,
    prior_hold: bool = False,
    as_of_date: str = "",
) -> TimelineDistributionV2:
    """Compute a TimelineDistributionV2 for remaining phases starting from current_phase."""
    # Determine phases remaining (inclusive of current phase)
    if current_phase in PHASE_ORDER:
        idx = PHASE_ORDER.index(current_phase)
        remaining_phase_names = PHASE_ORDER[idx:]
    else:
        # For 'approved' or unknown — no phases remaining
        remaining_phase_names = []

    phase_timelines: list[PhaseTimeline] = []
    for phase_name in remaining_phase_names:
        base = PHASE_DURATIONS.get(phase_name, {"p10": 12.0, "p50": 18.0, "p90": 30.0})
        p10 = base["p10"]
        p50 = base["p50"]
        p90 = base["p90"]

        if has_fast_track:
            p50 *= 0.85
        if has_breakthrough:
            p50 *= 0.80
            p90 *= 0.90
        if not enrollment_on_track:
            p50 *= 1.20
            p90 *= 1.30
        if prior_hold:
            p90 *= 1.20

        denom = p90 - p10 if (p90 - p10) > 0 else 1.0
        delay_probability = (p90 - p50) / denom
        delay_probability = max(0.0, min(1.0, delay_probability))
        delay_risk = _delay_risk_from_prob(delay_probability)

        phase_timelines.append(
            PhaseTimeline(
                phase=phase_name,
                expected_duration_months=p50,
                p10_months=p10,
                p50_months=p50,
                p90_months=p90,
                delay_risk=delay_risk,
                delay_probability=round(delay_probability, 4),
            )
        )

    if phase_timelines:
        expected_approval_months = sum(pt.p50_months for pt in phase_timelines)
        p10_approval_months = sum(pt.p10_months for pt in phase_timelines)
        p50_approval_months = sum(pt.p50_months for pt in phase_timelines)
        p90_approval_months = sum(pt.p90_months for pt in phase_timelines)
        catalyst_months_away: float | None = phase_timelines[0].p50_months
    else:
        expected_approval_months = 0.0
        p10_approval_months = 0.0
        p50_approval_months = 0.0
        p90_approval_months = 0.0
        catalyst_months_away = None

    # overall_delay_prob = 1 - product(1 - phase.delay_probability)
    overall_delay_prob = 1.0
    for pt in phase_timelines:
        overall_delay_prob *= 1.0 - pt.delay_probability
    overall_delay_prob = max(0.0, min(1.0, 1.0 - overall_delay_prob))

    modifiers: list[str] = []
    if has_fast_track:
        modifiers.append("fast_track")
    if has_breakthrough:
        modifiers.append("breakthrough")
    if not enrollment_on_track:
        modifiers.append("enrollment_off_track")
    if prior_hold:
        modifiers.append("prior_hold")

    rationale = (
        f"Timeline distribution for {asset_id} from {current_phase}. "
        f"Phases remaining: {len(phase_timelines)}. "
        f"p50 approval in {p50_approval_months:.0f} months. "
        f"Overall delay prob: {overall_delay_prob:.2f}."
        + (f" Modifiers: {', '.join(modifiers)}." if modifiers else "")
    )

    return TimelineDistributionV2(
        asset_id=asset_id,
        current_phase=current_phase,
        phases_remaining=phase_timelines,
        expected_approval_months=expected_approval_months,
        p10_approval_months=p10_approval_months,
        p50_approval_months=p50_approval_months,
        p90_approval_months=p90_approval_months,
        overall_delay_prob=overall_delay_prob,
        catalyst_months_away=catalyst_months_away,
        rationale=rationale,
    )

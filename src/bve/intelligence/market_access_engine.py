"""Phase H market access and launch realism engine."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from bve.models.commercial_inputs import CommercialInputs
from bve.models.market_access import MarketAccessResult, PayerDynamics, assess_market_access
from bve.models.probability_stack import ProbabilityStackInputs


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketAccessModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class GeographySplit(BaseModel):
    us_fraction: float = Field(ge=0.0, le=1.0)
    ex_us_fraction: float = Field(ge=0.0, le=1.0)


class SegmentShare(BaseModel):
    segment: str
    peak_share: float = Field(ge=0.0, le=1.0)


class AdoptionPoint(BaseModel):
    year: int = Field(ge=1)
    patients: float = Field(ge=0.0)
    revenue_millions: float = Field(ge=0.0)


class MarketAccessAssessmentValue(BaseModel):
    asset_id: str
    accessible_patient_pool: float = Field(ge=0.0)
    diagnosed_population: float = Field(ge=0.0)
    treated_population: float = Field(ge=0.0)
    eligible_population: float = Field(ge=0.0)
    reachable_population: float = Field(ge=0.0)
    reimbursed_population: float = Field(ge=0.0)
    initiating_patients: float = Field(ge=0.0)
    persistent_patients: float = Field(ge=0.0)
    switching_rate: float = Field(ge=0.0, le=1.0)
    ramp_speed_years: float = Field(ge=0.0)
    net_realized_price_usd: float = Field(ge=0.0)
    price_durability_years: float = Field(ge=0.0)
    rebate_burden_pct: float = Field(ge=0.0, le=1.0)
    price_erosion_pct: float = Field(ge=0.0, le=1.0)
    medicare_negotiation_risk_score: float = Field(ge=0.0, le=1.0)
    peak_share_by_segment: list[SegmentShare] = Field(default_factory=list)
    adoption_curve: list[AdoptionPoint] = Field(default_factory=list)
    commercial_uncertainty_low: float = Field(ge=0.0)
    commercial_uncertainty_base: float = Field(ge=0.0)
    commercial_uncertainty_high: float = Field(ge=0.0)
    geography_split: GeographySplit
    access_risk_score: float = Field(ge=0.0, le=1.0)
    access_risk_tier: str


class MarketAccessAssessment(BaseModel):
    asset_id: str
    output: MarketAccessModuleOutput
    plain_english_summary: str


class MarketAccessEngine:
    """
    Patient-funnel commercialization engine with payer constraints.

    This is the Phase H layer above the lower-level market_access model. It turns
    payer/access signals plus commercial inputs into a constrained launch model.
    """

    def assess(
        self,
        *,
        asset_id: str,
        commercial_inputs: CommercialInputs,
        payer_dynamics: PayerDynamics,
        years: int = 6,
        label_expansion_factor: float = 1.0,
    ) -> MarketAccessAssessment:
        access = assess_market_access(payer_dynamics)
        pool = commercial_inputs.patient_pool
        pricing = commercial_inputs.pricing
        share = commercial_inputs.share

        addressable = float(pool.to_addressable())
        diagnosed = float(pool.prevalence_thousands * 1_000 * pool.diagnosed_fraction)
        eligible = float(diagnosed * pool.eligible_rate * label_expansion_factor)
        treated = float(eligible * pool.treated_fraction)
        reachable = float(treated * max(0.50, 0.92 - max(0.0, payer_dynamics.net_price_to_list_ratio - 0.65)))
        reimbursed = float(reachable * access.effective_patient_pool_multiplier)
        initiating = float(reimbursed * (0.55 + max(-0.20, access.adoption_speed_modifier)))
        persistent = float(initiating * self._persistence_rate(access, pricing.annual_erosion_rate))

        net_realized_price = float(
            pricing.effective_launch_price()
            * max(0.50, payer_dynamics.net_price_to_list_ratio)
            * (1.0 - max(0.0, pricing.annual_erosion_rate * 0.25))
        )
        rebate_burden = round(max(0.0, 1.0 - max(0.50, payer_dynamics.net_price_to_list_ratio)), 4)
        price_erosion = round(
            min(0.40, pricing.annual_erosion_rate + max(0.0, access.access_risk_score - 0.35) * 0.10),
            4,
        )
        ramp_speed_years = round(
            max(1.0, share.years_to_peak * (1.0 - access.adoption_speed_modifier)),
            4,
        )
        medicare_risk = round(
            min(
                1.0,
                (0.65 if payer_dynamics.medicare_heavy_indication else 0.20)
                + (0.20 if payer_dynamics.cost_effectiveness_risk.value in {"high", "unknown"} else 0.0),
            ),
            4,
        )

        effective_peak_share = min(1.0, max(0.01, share.peak_share + access.peak_penetration_modifier))
        segment_shares = [
            SegmentShare(segment="reimbursed", peak_share=round(effective_peak_share, 4)),
            SegmentShare(segment="reachable", peak_share=round(min(1.0, effective_peak_share * 0.85), 4)),
            SegmentShare(segment="broad_access", peak_share=round(min(1.0, effective_peak_share * 1.10), 4)),
        ]
        adoption_curve = self._adoption_curve(
            reimbursed_population=reimbursed,
            net_realized_price_usd=net_realized_price,
            peak_share=effective_peak_share,
            years_to_peak=ramp_speed_years,
            years=years,
            ex_us_multiple=commercial_inputs.ex_us_revenue_multiple,
        )
        base_peak = adoption_curve[-1].revenue_millions if adoption_curve else 0.0
        uncertainty_low = round(base_peak * 0.70, 4)
        uncertainty_high = round(base_peak * 1.30, 4)
        uncertainty_base = round(base_peak, 4)

        us_fraction = round(1.0 / commercial_inputs.ex_us_revenue_multiple, 4)
        geography = GeographySplit(
            us_fraction=us_fraction,
            ex_us_fraction=round(max(0.0, 1.0 - us_fraction), 4),
        )
        value = MarketAccessAssessmentValue(
            asset_id=asset_id,
            accessible_patient_pool=round(reimbursed, 4),
            diagnosed_population=round(diagnosed, 4),
            treated_population=round(treated, 4),
            eligible_population=round(eligible, 4),
            reachable_population=round(reachable, 4),
            reimbursed_population=round(reimbursed, 4),
            initiating_patients=round(initiating, 4),
            persistent_patients=round(persistent, 4),
            switching_rate=round(self._switching_rate(access), 4),
            ramp_speed_years=ramp_speed_years,
            net_realized_price_usd=round(net_realized_price, 4),
            price_durability_years=round(access.net_price_durability_years, 4),
            rebate_burden_pct=rebate_burden,
            price_erosion_pct=price_erosion,
            medicare_negotiation_risk_score=medicare_risk,
            peak_share_by_segment=segment_shares,
            adoption_curve=adoption_curve,
            commercial_uncertainty_low=uncertainty_low,
            commercial_uncertainty_base=uncertainty_base,
            commercial_uncertainty_high=uncertainty_high,
            geography_split=geography,
            access_risk_score=round(access.access_risk_score, 4),
            access_risk_tier=access.access_risk_tier,
        )
        explanation = (
            f"Accessible pool is constrained from {addressable:,.0f} addressable patients to "
            f"{reimbursed:,.0f} reimbursed patients using payer access, prior-auth, and pricing friction."
        )
        output = MarketAccessModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(access=access, payer_dynamics=payer_dynamics),
            provenance=self._provenance(payer_dynamics=payer_dynamics),
            freshness=_utcnow(),
            explainability=explanation,
            downstream_dependencies=[
                "market_model",
                "probability_stack",
                "market_expectations",
            ],
        )
        summary = (
            f"{asset_id} has accessible pool {value.accessible_patient_pool:,.0f}, "
            f"net realized price ${value.net_realized_price_usd:,.0f}, and access tier "
            f"{value.access_risk_tier}."
        )
        return MarketAccessAssessment(
            asset_id=asset_id,
            output=output,
            plain_english_summary=summary,
        )

    def apply_to_probability_stack_inputs(
        self,
        inputs: ProbabilityStackInputs,
        assessment: MarketAccessAssessment,
    ) -> ProbabilityStackInputs:
        value = MarketAccessAssessmentValue.model_validate(assessment.output.value)
        return inputs.model_copy(
            update={
                "market_access_pressure_score": round(value.access_risk_score, 4),
            }
        )

    @staticmethod
    def _switching_rate(access: MarketAccessResult) -> float:
        base = 0.18
        if access.payer_dynamics.step_edit_required:
            base -= 0.05
        if access.payer_dynamics.formulary_tier.value in {"tier_1", "tier_2"}:
            base += 0.04
        return max(0.02, min(0.40, base))

    @staticmethod
    def _persistence_rate(access: MarketAccessResult, erosion_rate: float) -> float:
        persistence = 0.78 + (access.adoption_speed_modifier * 0.20) - (erosion_rate * 0.35)
        return max(0.45, min(0.92, persistence))

    @staticmethod
    def _s_curve_progress(year: int, years_to_peak: float) -> float:
        midpoint = max(1.0, years_to_peak / 2.0)
        steepness = 8.0 / max(1.0, years_to_peak)
        raw = 1.0 / (1.0 + math.exp(-steepness * (year - midpoint)))
        peak_raw = 1.0 / (1.0 + math.exp(-steepness * (years_to_peak - midpoint)))
        return min(1.0, raw / max(peak_raw, 1e-6))

    def _adoption_curve(
        self,
        *,
        reimbursed_population: float,
        net_realized_price_usd: float,
        peak_share: float,
        years_to_peak: float,
        years: int,
        ex_us_multiple: float,
    ) -> list[AdoptionPoint]:
        curve: list[AdoptionPoint] = []
        for year in range(1, max(1, years) + 1):
            progress = self._s_curve_progress(year, years_to_peak)
            patients = reimbursed_population * peak_share * progress
            revenue = patients * net_realized_price_usd * ex_us_multiple / 1e6
            curve.append(
                AdoptionPoint(
                    year=year,
                    patients=round(patients, 4),
                    revenue_millions=round(revenue, 4),
                )
            )
        return curve

    @staticmethod
    def _confidence(
        *,
        access: MarketAccessResult,
        payer_dynamics: PayerDynamics,
    ) -> float:
        confidence = 0.68
        if payer_dynamics.formulary_tier.value != "unknown":
            confidence += 0.08
        if payer_dynamics.prior_auth_burden.value != "unknown":
            confidence += 0.06
        if payer_dynamics.cost_effectiveness_risk.value != "unknown":
            confidence += 0.06
        if payer_dynamics.commercial_payer_coverage_pct > 0:
            confidence += 0.05
        if access.access_risk_tier == "unknown":
            confidence -= 0.10
        return round(max(0.35, min(0.95, confidence)), 4)

    @staticmethod
    def _provenance(*, payer_dynamics: PayerDynamics) -> list[str]:
        provenance = ["commercial_inputs", "payer_dynamics"]
        if payer_dynamics.commercial_payer_coverage_pct > 0:
            provenance.append("coverage_proxy")
        if payer_dynamics.list_price_usd_thousands > 0:
            provenance.append("pricing_proxy")
        return provenance

"""Phase G financing and dilution engine."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.entities.company import Company
from bve.entities.company_snapshot import DilutionBridge
from bve.models.probability_stack import ProbabilityStackInputs


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FinancingModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class FinancingCatalyst(BaseModel):
    catalyst_id: str
    label: str
    expected_date: date
    catalyst_type: str = "readout"


class BurnPath(BaseModel):
    base_quarterly_burn_millions: float = Field(ge=0.0)
    bull_quarterly_burn_millions: float = Field(ge=0.0)
    bear_quarterly_burn_millions: float = Field(ge=0.0)


class FinancingAssessmentValue(BaseModel):
    asset_id: str
    company_id: str
    company_name: str
    months_of_runway: float = Field(ge=0.0)
    burn_path: BurnPath
    capital_needed_to_next_catalyst_millions: float = Field(ge=0.0)
    capital_needed_to_approval_millions: float = Field(ge=0.0)
    likely_raise_timing_months: float = Field(ge=0.0)
    likely_raise_size_millions: float = Field(ge=0.0)
    expected_dilution_pct_low: float = Field(ge=0.0, le=1.0)
    expected_dilution_pct_base: float = Field(ge=0.0, le=1.0)
    expected_dilution_pct_high: float = Field(ge=0.0, le=1.0)
    probability_of_pre_catalyst_financing: float = Field(ge=0.0, le=1.0)
    financing_risk_score: float = Field(ge=0.0, le=1.0)
    financing_risk_tier: str
    balance_sheet_stress_score: float = Field(ge=0.0, le=1.0)
    partnership_alternative_value_millions: float = Field(ge=0.0)
    financing_adjusted_intrinsic_value_millions: float
    financing_overhang_impact_pct: float


class FinancingAssessment(BaseModel):
    asset_id: str
    company_id: str
    company_name: str
    output: FinancingModuleOutput
    plain_english_summary: str


class FinancingEngine:
    """
    Runway, raise timing, dilution, and financing-adjusted value model.

    Phase G sits above the older Wave 7 catalyst-specific capital check. It
    produces a company-level financing view that can feed PoS, market
    expectations, and catalyst trees.
    """

    def assess_company(
        self,
        *,
        asset_id: str,
        company: Company,
        next_catalyst: Optional[FinancingCatalyst],
        approval_target_date: Optional[date],
        intrinsic_value_millions: float,
        market_snapshot_date: Optional[date] = None,
        dilution_bridge: Optional[DilutionBridge] = None,
    ) -> FinancingAssessment:
        as_of = market_snapshot_date or date.today()
        freshness = datetime.combine(as_of, datetime.min.time(), tzinfo=timezone.utc)

        quarterly_burn = float(company.burn_rate_millions_per_quarter or 0.0)
        base_burn = max(quarterly_burn, 0.0)
        bull_burn = round(base_burn * 0.85, 4)
        bear_burn = round(base_burn * 1.25, 4)
        burn_path = BurnPath(
            base_quarterly_burn_millions=round(base_burn, 4),
            bull_quarterly_burn_millions=round(bull_burn, 4),
            bear_quarterly_burn_millions=round(bear_burn, 4),
        )

        months_of_runway = self._months_of_runway(company.cash_millions, base_burn)
        months_to_next_catalyst = self._months_until(next_catalyst.expected_date, as_of) if next_catalyst else 0.0
        months_to_approval = self._months_until(approval_target_date, as_of)

        capital_to_next = self._capital_needed(
            company.cash_millions,
            base_burn,
            months_to_next_catalyst,
            buffer_months=6.0,
        )
        capital_to_approval = self._capital_needed(
            company.cash_millions,
            bear_burn,
            months_to_approval,
            buffer_months=9.0,
        )

        likely_raise_timing_months = round(max(0.0, months_of_runway - 3.0), 4)
        raise_size = round(
            max(
                capital_to_next if next_catalyst else 0.0,
                capital_to_approval,
                base_burn,
            ),
            4,
        )

        market_cap = float(company.market_cap_millions or 0.0)
        current_shares = float(company.shares_outstanding_millions)
        price_per_share = self._price_per_share(company)
        price_stress = self._price_stress_discount(months_of_runway, market_cap)
        base_dilution = self._dilution_pct(
            raise_size_millions=raise_size,
            price_per_share=price_per_share,
            current_shares_millions=current_shares,
            execution_discount=price_stress,
        )
        low_dilution = self._dilution_pct(
            raise_size_millions=max(0.0, raise_size * 0.75),
            price_per_share=price_per_share,
            current_shares_millions=current_shares,
            execution_discount=max(0.05, price_stress - 0.03),
        )
        high_dilution = self._dilution_pct(
            raise_size_millions=raise_size * 1.30,
            price_per_share=price_per_share,
            current_shares_millions=current_shares,
            execution_discount=min(0.35, price_stress + 0.05),
        )
        if dilution_bridge is not None:
            bridge_floor = float(dilution_bridge.expected_dilution_pct)
            base_dilution = max(base_dilution, bridge_floor)
            high_dilution = max(high_dilution, min(1.0, bridge_floor + 0.05))

        pre_catalyst_probability = self._pre_catalyst_probability(
            months_of_runway=months_of_runway,
            months_to_next_catalyst=months_to_next_catalyst,
            market_cap_millions=market_cap,
            atm_active=bool(dilution_bridge.atm_active) if dilution_bridge else False,
        )
        stress_score = self._balance_sheet_stress_score(
            months_of_runway=months_of_runway,
            base_dilution=base_dilution,
            debt_millions=float(company.debt_millions),
            cash_millions=float(company.cash_millions),
        )
        financing_risk_score = round(
            min(
                1.0,
                0.55 * pre_catalyst_probability
                + 0.25 * stress_score
                + 0.20 * min(1.0, base_dilution / 0.30),
            ),
            4,
        )
        tier = self._risk_tier(financing_risk_score)

        partnership_value = round(max(0.0, capital_to_approval * 0.25), 4)
        financing_adjusted_value = round(
            intrinsic_value_millions * (1.0 - base_dilution) - (raise_size * price_stress * 0.35),
            4,
        )
        financing_overhang_pct = round(
            -(0.60 * base_dilution + 0.40 * pre_catalyst_probability),
            4,
        )

        value = FinancingAssessmentValue(
            asset_id=asset_id,
            company_id=company.id,
            company_name=company.name,
            months_of_runway=round(months_of_runway, 4),
            burn_path=burn_path,
            capital_needed_to_next_catalyst_millions=round(capital_to_next, 4),
            capital_needed_to_approval_millions=round(capital_to_approval, 4),
            likely_raise_timing_months=likely_raise_timing_months,
            likely_raise_size_millions=raise_size,
            expected_dilution_pct_low=round(low_dilution, 4),
            expected_dilution_pct_base=round(base_dilution, 4),
            expected_dilution_pct_high=round(high_dilution, 4),
            probability_of_pre_catalyst_financing=pre_catalyst_probability,
            financing_risk_score=financing_risk_score,
            financing_risk_tier=tier,
            balance_sheet_stress_score=stress_score,
            partnership_alternative_value_millions=partnership_value,
            financing_adjusted_intrinsic_value_millions=financing_adjusted_value,
            financing_overhang_impact_pct=financing_overhang_pct,
        )
        explanation = self._explain(value, next_catalyst, approval_target_date)
        output = FinancingModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(company=company, dilution_bridge=dilution_bridge, raise_size=raise_size),
            provenance=self._provenance(company=company, next_catalyst=next_catalyst, dilution_bridge=dilution_bridge),
            freshness=freshness,
            explainability=explanation,
            downstream_dependencies=[
                "probability_stack",
                "market_expectations",
                "catalyst_payoff_trees",
            ],
        )
        summary = (
            f"{company.name} has {value.months_of_runway:.1f} months of runway, "
            f"{value.probability_of_pre_catalyst_financing:.0%} pre-catalyst financing probability, "
            f"and base dilution of {value.expected_dilution_pct_base:.0%}."
        )
        return FinancingAssessment(
            asset_id=asset_id,
            company_id=company.id,
            company_name=company.name,
            output=output,
            plain_english_summary=summary,
        )

    def apply_to_probability_stack_inputs(
        self,
        inputs: ProbabilityStackInputs,
        assessment: FinancingAssessment,
    ) -> ProbabilityStackInputs:
        value = FinancingAssessmentValue.model_validate(assessment.output.value)
        return inputs.model_copy(
            update={
                "financing_risk_score": round(value.financing_risk_score, 4),
            }
        )

    @staticmethod
    def _months_of_runway(cash_millions: float, quarterly_burn_millions: float) -> float:
        if quarterly_burn_millions <= 0:
            return 60.0
        return round((cash_millions / quarterly_burn_millions) * 3.0, 4)

    @staticmethod
    def _months_until(target: Optional[date], as_of: date) -> float:
        if target is None:
            return 0.0
        return round(max(0.0, (target - as_of).days / 30.0), 4)

    @staticmethod
    def _capital_needed(
        cash_millions: float,
        quarterly_burn_millions: float,
        target_months: float,
        *,
        buffer_months: float,
    ) -> float:
        if quarterly_burn_millions <= 0:
            return 0.0
        monthly_burn = quarterly_burn_millions / 3.0
        need = (monthly_burn * (target_months + buffer_months)) - cash_millions
        return round(max(0.0, need), 4)

    @staticmethod
    def _price_per_share(company: Company) -> float:
        if company.current_price is not None and company.current_price > 0:
            return float(company.current_price)
        if company.market_cap_millions and company.market_cap_millions > 0:
            return float(company.market_cap_millions) / float(company.shares_outstanding_millions)
        return 1.0

    @staticmethod
    def _price_stress_discount(months_of_runway: float, market_cap_millions: float) -> float:
        discount = 0.08
        if months_of_runway < 9:
            discount += 0.06
        if months_of_runway < 6:
            discount += 0.06
        if 0 < market_cap_millions < 500:
            discount += 0.03
        return round(min(0.35, discount), 4)

    @staticmethod
    def _dilution_pct(
        *,
        raise_size_millions: float,
        price_per_share: float,
        current_shares_millions: float,
        execution_discount: float,
    ) -> float:
        if raise_size_millions <= 0 or price_per_share <= 0 or current_shares_millions <= 0:
            return 0.0
        effective_price = price_per_share * max(0.05, 1.0 - execution_discount)
        new_shares = raise_size_millions / effective_price
        return round(max(0.0, min(1.0, new_shares / current_shares_millions)), 4)

    @staticmethod
    def _pre_catalyst_probability(
        *,
        months_of_runway: float,
        months_to_next_catalyst: float,
        market_cap_millions: float,
        atm_active: bool,
    ) -> float:
        if months_to_next_catalyst <= 0:
            base = 0.15
        else:
            gap = months_to_next_catalyst - months_of_runway
            if gap <= -6:
                base = 0.10
            elif gap <= -2:
                base = 0.25
            elif gap <= 0:
                base = 0.45
            elif gap <= 4:
                base = 0.72
            else:
                base = 0.88
        if 0 < market_cap_millions < 300:
            base += 0.07
        if atm_active:
            base += 0.05
        return round(min(0.98, max(0.02, base)), 4)

    @staticmethod
    def _balance_sheet_stress_score(
        *,
        months_of_runway: float,
        base_dilution: float,
        debt_millions: float,
        cash_millions: float,
    ) -> float:
        runway_score = 1.0 - min(1.0, months_of_runway / 24.0)
        leverage_score = 0.0 if cash_millions <= 0 else min(1.0, debt_millions / max(cash_millions, 1.0))
        return round(min(1.0, 0.60 * runway_score + 0.25 * base_dilution + 0.15 * leverage_score), 4)

    @staticmethod
    def _risk_tier(financing_risk_score: float) -> str:
        if financing_risk_score >= 0.80:
            return "critical"
        if financing_risk_score >= 0.60:
            return "high"
        if financing_risk_score >= 0.35:
            return "medium"
        return "low"

    @staticmethod
    def _confidence(
        *,
        company: Company,
        dilution_bridge: Optional[DilutionBridge],
        raise_size: float,
    ) -> float:
        confidence = 0.82 if company.burn_rate_millions_per_quarter is not None else 0.52
        if dilution_bridge is not None:
            confidence += 0.08
        if company.market_cap_millions is None:
            confidence -= 0.10
        if raise_size > max(float(company.cash_millions), 1.0):
            confidence -= 0.08
        return round(max(0.25, min(0.95, confidence)), 4)

    @staticmethod
    def _provenance(
        *,
        company: Company,
        next_catalyst: Optional[FinancingCatalyst],
        dilution_bridge: Optional[DilutionBridge],
    ) -> list[str]:
        provenance = [
            f"company:{company.id}",
            "balance_sheet_snapshot",
            "market_snapshot",
        ]
        if next_catalyst is not None:
            provenance.append(f"catalyst:{next_catalyst.catalyst_id}")
        if dilution_bridge is not None and dilution_bridge.source_ref:
            provenance.append(dilution_bridge.source_ref)
        return provenance

    @staticmethod
    def _explain(
        value: FinancingAssessmentValue,
        next_catalyst: Optional[FinancingCatalyst],
        approval_target_date: Optional[date],
    ) -> str:
        catalyst_text = (
            f"next catalyst {next_catalyst.label} on {next_catalyst.expected_date.isoformat()}"
            if next_catalyst is not None
            else "no explicit next catalyst"
        )
        approval_text = (
            approval_target_date.isoformat() if approval_target_date is not None else "unknown approval date"
        )
        return (
            f"Runway is {value.months_of_runway:.1f} months with base quarterly burn "
            f"{value.burn_path.base_quarterly_burn_millions:.1f}M. The model expects "
            f"{value.probability_of_pre_catalyst_financing:.0%} odds of financing before "
            f"{catalyst_text}, with approval funding needs traced to {approval_text}."
        )

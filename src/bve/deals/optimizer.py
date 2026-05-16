"""DealOptimizer — finds the optimal structure for buyer given seller constraints."""

from __future__ import annotations

from dataclasses import dataclass, field

from .seller_utility import SellerUtilityModel, SellerValuation
from .structure import DealStructure, DealStructureType


@dataclass
class DealOptimizerInput:
    """Buyer inputs to the deal optimizer."""

    buyer_rnpv_full_acquisition_usd_m: float
    seller_standalone_rnpv_usd_m: float
    seller_cash_runway_months: float
    seller_strategic_alternatives: int = 0
    seller_founder_control_preference: float = 0.0
    budget_usd_m: float = 1_000.0
    min_seller_acceptance_probability: float = 0.40
    approval_probability: float = 0.50   # P(asset succeeds)


@dataclass
class OptimizedDeal:
    """Output of the deal optimizer."""

    best_structure: DealStructure
    all_structures: list[DealStructure] = field(default_factory=list)
    optimization_target: str = "max buyer_rnpv subject to seller_acceptance >= threshold"

    def describe(self) -> str:
        lines = [f"Best structure: {self.best_structure.structure_type.value}"]
        lines.append(self.best_structure.summary())
        return "\n".join(lines)


class DealOptimizer:
    """
    Generates candidate deal structures and selects the one that maximises
    buyer rNPV subject to: seller_acceptance >= threshold AND upfront <= budget.
    """

    def __init__(self) -> None:
        self._seller_model = SellerUtilityModel()

    def optimize(self, inp: DealOptimizerInput) -> OptimizedDeal:
        seller = SellerValuation(
            standalone_rnpv_usd_m=inp.seller_standalone_rnpv_usd_m,
            cash_runway_months=inp.seller_cash_runway_months,
            strategic_alternatives=inp.seller_strategic_alternatives,
            founder_control_preference=inp.seller_founder_control_preference,
        )

        structures = self._generate_candidates(inp, seller)
        feasible = [
            s for s in structures
            if s.upfront_cash_usd_m <= inp.budget_usd_m
            and s.probability_seller_accepts >= inp.min_seller_acceptance_probability
        ]

        if not feasible:
            # Fall back to best on seller acceptance even if below threshold
            feasible = sorted(structures, key=lambda s: s.probability_seller_accepts, reverse=True)[:1]

        best = max(feasible, key=lambda s: s.buyer_rnpv_usd_m)
        return OptimizedDeal(best_structure=best, all_structures=structures)

    def _generate_candidates(
        self, inp: DealOptimizerInput, seller: SellerValuation
    ) -> list[DealStructure]:
        buyer_rnpv = inp.buyer_rnpv_full_acquisition_usd_m
        p_success = inp.approval_probability
        standalone = inp.seller_standalone_rnpv_usd_m

        structures = []

        # 1. Full acquisition
        fa_upfront = standalone * 2.0  # typical 2× premium
        fa_total = fa_upfront
        structures.append(
            DealStructure(
                structure_type=DealStructureType.FULL_ACQUISITION,
                upfront_cash_usd_m=fa_upfront,
                buyer_rnpv_usd_m=buyer_rnpv - fa_upfront,
                seller_expected_value_usd_m=fa_total,
                risk_transfer_to_buyer=1.0,
                control_score=1.0,
                accounting_complexity="low",
                probability_seller_accepts=self._seller_model.acceptance_probability(fa_total, seller),
                rationale="Clean, full control; avoids milestone disputes",
            )
        )

        # 2. Option to acquire
        option_upfront = standalone * 0.20
        option_exercise = standalone * 1.80
        option_total_expected = option_upfront + option_exercise * p_success
        structures.append(
            DealStructure(
                structure_type=DealStructureType.OPTION_TO_ACQUIRE,
                upfront_cash_usd_m=option_upfront,
                option_exercise_price_usd_m=option_exercise,
                buyer_rnpv_usd_m=buyer_rnpv * p_success - option_upfront - option_exercise * p_success,
                seller_expected_value_usd_m=option_total_expected,
                risk_transfer_to_buyer=0.5,
                control_score=0.4,
                accounting_complexity="medium",
                probability_seller_accepts=self._seller_model.acceptance_probability(
                    option_total_expected, seller
                ),
                rationale="Preserves optionality; avoids pre-PoC overpayment",
            )
        )

        # 3. Asset license (royalty deal)
        license_upfront = standalone * 0.15
        license_milestones = standalone * 1.20
        royalty = 0.12
        license_seller_value = license_upfront + license_milestones * p_success + buyer_rnpv * royalty * 0.60
        structures.append(
            DealStructure(
                structure_type=DealStructureType.ASSET_LICENSE,
                upfront_cash_usd_m=license_upfront,
                milestones_total_usd_m=license_milestones,
                royalty_rate=royalty,
                buyer_rnpv_usd_m=buyer_rnpv * (1 - royalty) * p_success - license_upfront,
                seller_expected_value_usd_m=license_seller_value,
                risk_transfer_to_buyer=0.80,
                control_score=0.80,
                accounting_complexity="medium",
                probability_seller_accepts=self._seller_model.acceptance_probability(
                    license_seller_value, seller
                ),
                rationale="Back-loaded; reduces upfront risk; seller retains royalty participation",
            )
        )

        # 4. Co-development
        co_dev_upfront = standalone * 0.10
        co_dev_milestones = standalone * 0.60
        co_dev_cost_share = 0.50
        co_dev_seller_value = co_dev_upfront + co_dev_milestones * p_success
        structures.append(
            DealStructure(
                structure_type=DealStructureType.CO_DEVELOPMENT,
                upfront_cash_usd_m=co_dev_upfront,
                milestones_total_usd_m=co_dev_milestones,
                buyer_cost_share_pct=co_dev_cost_share,
                buyer_rnpv_usd_m=buyer_rnpv * 0.50 * p_success - co_dev_upfront,
                seller_expected_value_usd_m=co_dev_seller_value,
                risk_transfer_to_buyer=0.50,
                control_score=0.50,
                accounting_complexity="high",
                probability_seller_accepts=self._seller_model.acceptance_probability(
                    co_dev_seller_value, seller
                ),
                rationale="Shared risk/reward; suitable when seller has strong operational capabilities",
            )
        )

        return structures

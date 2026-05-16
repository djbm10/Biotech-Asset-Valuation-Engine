"""Seller utility model — estimates seller's willingness to accept."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SellerValuation:
    """Seller's internal view of asset value."""

    standalone_rnpv_usd_m: float       # Seller's own rNPV
    cash_runway_months: float           # How urgently seller needs capital
    strategic_alternatives: int         # Number of alternative deals in play
    founder_control_preference: float   # 0=doesn't care, 1=strongly prefers independence


class SellerUtilityModel:
    """
    Estimates probability that a seller would accept a given deal structure.
    Based on: (deal_value / seller_standalone_value) and urgency modifiers.
    """

    def acceptance_probability(
        self,
        offer_total_value_usd_m: float,
        seller: SellerValuation,
    ) -> float:
        """
        Returns P(seller accepts).
        - At 1× standalone value → P=0.40 (some sellers hold out for premium)
        - At 2× → P=0.80
        - Low cash runway → increases acceptance at any price
        - Many alternatives → decreases acceptance
        """
        if seller.standalone_rnpv_usd_m <= 0:
            return 0.5

        multiple = offer_total_value_usd_m / seller.standalone_rnpv_usd_m
        # Sigmoid-like: P(accept) increases with multiple
        base_p = min(0.95, max(0.05, -0.20 + 0.60 * multiple))

        # Urgency modifier: low cash → more willing to sell
        urgency_bonus = max(0.0, (18 - seller.cash_runway_months) / 18) * 0.20

        # Competition modifier: more alternatives → less willing to accept
        competition_penalty = min(0.20, seller.strategic_alternatives * 0.05)

        # Control preference modifier
        control_penalty = seller.founder_control_preference * 0.10

        p = base_p + urgency_bonus - competition_penalty - control_penalty
        return max(0.05, min(0.95, p))

    def minimum_acceptable_value(self, seller: SellerValuation) -> float:
        """Seller's walk-away price (rough estimate)."""
        # Typically sellers want 1.5–2× standalone in competitive situations
        urgency_discount = max(0.0, (18 - seller.cash_runway_months) / 18) * 0.30
        multiple = max(1.2, 1.8 - urgency_discount)
        return seller.standalone_rnpv_usd_m * multiple

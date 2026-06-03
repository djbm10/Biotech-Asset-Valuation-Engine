"""
Position Policy Engine — Step 5 of the institutional-grade upgrade plan.

Converts company-level SOTP + conviction + risk inputs into explicit
capital allocation decisions:

  Equity actions:   buy | add | monitor | avoid
  BD actions:       acquire | partner | pass

Design principles
-----------------
- Deterministic: same inputs always produce the same output (no randomness).
- Composable: each gate (downside, conviction, catalyst, liquidity) is applied
  independently and its contribution is logged in ``rationale``.
- Conservative defaults: when uncertain, the engine defaults to monitor or
  smaller size rather than avoid (avoid is reserved for clear value traps or
  conviction failures).

Sizing model
------------
  base_size = min(discount_fraction × conviction × sizing_scale, max_position_pct)
  catalyst_boost: if catalyst within catalyst_boost_days → +20% of base_size
  liquidity_cap:  if adv_millions < min_adv_millions → × 0.50
  downside_floor: if downside_risk > avoid_downside_threshold × 0.75 → × 0.75
  sizing_pct = 0 for monitor / avoid actions

Action ladder (checked in order — first gate wins)
---------------------------------------------------
  1. avoid_downside_trap: bear_case > current_price → avoid (value trap)
  2. avoid_conviction: conviction < min_conviction → avoid
  3. avoid_premium: sotp_discount_fraction < 0 (trading above SOTP) → avoid
  4. monitor_catalyst_gate: next_catalyst_days > catalyst_gate_days → monitor
  5. buy: discount ≥ buy_discount_threshold AND conviction ≥ buy_conviction_floor
     AND catalyst within catalyst_gate_days
  6. add: discount ≥ add_discount_threshold
  7. monitor: otherwise
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

ActionEquity = Literal["buy", "add", "monitor", "avoid"]
ActionBD = Literal["acquire", "partner", "pass"]
ProcessRisk = Literal["low", "medium", "high"]

# Thresholds that govern the buy/add split of conviction
_BUY_CONVICTION_FLOOR = 0.55


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class PositionPolicyConfig(BaseModel, frozen=True):
    """
    Tunable parameters for the policy engine.

    All thresholds are fractions (0-1) unless stated otherwise.
    Sizing outputs are in percent of portfolio (0-100 scale).
    """

    # Action thresholds
    buy_discount_threshold: float = Field(
        default=0.40, ge=0.0, le=2.0,
        description="SOTP discount fraction required for 'buy' action",
    )
    add_discount_threshold: float = Field(
        default=0.20, ge=0.0, le=2.0,
        description="SOTP discount fraction required for 'add' action",
    )
    avoid_downside_threshold: float = Field(
        default=0.40, ge=0.0, le=1.0,
        description=(
            "Downside risk fraction that triggers 'avoid' (value trap gate). "
            "Default 0.40 (40%) is appropriate for biotech, where high risk is the norm; "
            "lower values (e.g., 0.15) suit defensive sectors."
        ),
    )
    min_conviction: float = Field(
        default=0.30, ge=0.0, le=1.0,
        description="Minimum conviction score; below this → avoid",
    )

    # Catalyst gates
    catalyst_gate_days: int = Field(
        default=90, gt=0,
        description="Catalyst must be within this many days for buy/add; else monitor",
    )
    catalyst_boost_days: int = Field(
        default=30, gt=0,
        description="Catalyst within this many days → apply boost to sizing",
    )

    # Sizing parameters
    max_position_pct: float = Field(
        default=5.0, gt=0.0, le=100.0,
        description="Maximum single-name position as % of portfolio",
    )
    sizing_scale: float = Field(
        default=8.0, gt=0.0,
        description=(
            "Scale factor: base_size = discount_fraction × conviction × sizing_scale. "
            "Default 8 maps a 50% discount + 0.60 conviction to 2.4% base size."
        ),
    )
    catalyst_boost_pct: float = Field(
        default=0.20, ge=0.0, le=1.0,
        description="Fractional increase to base_size when catalyst is near (0.20 = +20%)",
    )
    liquidity_haircut: float = Field(
        default=0.50, ge=0.0, le=1.0,
        description="Multiplier applied to sizing when ADV < min_adv_millions",
    )
    downside_haircut: float = Field(
        default=0.75, ge=0.0, le=1.0,
        description="Multiplier applied when downside_risk > avoid_downside_threshold × 0.75",
    )
    min_adv_millions: float = Field(
        default=1.0, gt=0,
        description="Minimum average daily volume (ADV) in $M; below → liquidity haircut",
    )


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class PositionPolicyInput(BaseModel, frozen=True):
    """
    Company-level SOTP inputs for the policy engine.

    All prices in USD per share.
    """

    ticker: str
    current_price: float = Field(gt=0)
    base_sotp_per_share: float = Field(gt=0, description="Base-case SOTP value per share")
    bear_sotp_per_share: float = Field(gt=0, description="Bear-case SOTP per share")
    bull_sotp_per_share: float = Field(gt=0, description="Bull-case SOTP per share")
    conviction: float = Field(ge=0.0, le=1.0, description="Analyst conviction 0–1")
    next_catalyst_days: int = Field(
        ge=0,
        description="Days until the next material catalyst; 0 = imminent",
    )
    adv_millions: float = Field(
        gt=0,
        description="Average daily volume in USD millions (20-day lookback)",
    )
    catalyst_description: str = Field(
        default="",
        description="Short description of the next catalyst",
    )
    existing_position_pct: float = Field(
        default=0.0, ge=0.0,
        description="Current portfolio weight (%) — used to cap incremental add size",
    )

    @property
    def sotp_discount_fraction(self) -> float:
        """(SOTP - price) / price. Positive = trading below SOTP."""
        return (self.base_sotp_per_share - self.current_price) / self.current_price

    @property
    def implied_upside_pct(self) -> float:
        """Implied upside in percent from current price to base SOTP."""
        return self.sotp_discount_fraction * 100.0

    @property
    def downside_risk_pct(self) -> float:
        """Fraction of current price at risk if bear case materialises. Always ≥ 0."""
        return max(0.0, (self.current_price - self.bear_sotp_per_share) / self.current_price)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PositionPolicy:
    """
    Recommended position policy for a single equity name.

    Fields are documented inline.
    """

    ticker: str
    action: ActionEquity
    sizing_pct: float              # Recommended portfolio weight (%)
    base_sotp_per_share: float
    downside_case_per_share: float
    upside_case_per_share: float
    current_price: float
    implied_upside_pct: float
    downside_risk_pct: float
    catalyst_gate: str             # Description of the next catalyst (or "")
    next_catalyst_days: int
    rationale: str                 # Human-readable explanation of each gate applied


@dataclass(frozen=True)
class BDRecommendation:
    """
    BD / M&A recommendation for a target company.

    Actions:
      acquire  — outright acquisition recommended
      partner  — licensing / co-development preferred over full acquisition
      pass     — do not pursue at current price / risk level
    """

    ticker: str
    action: ActionBD
    ma_probability: float
    strategic_fit: float
    implied_deal_premium_pct: float   # (deal_value / price - 1) × 100
    process_risk: ProcessRisk
    rationale: str

    @classmethod
    def from_scores(
        cls,
        ticker: str,
        ma_probability: float,
        strategic_fit: float,
        current_price: float,
        estimated_deal_value: float,
        process_risk: ProcessRisk,
        *,
        acquire_ma_threshold: float = 0.70,
        acquire_fit_threshold: float = 0.65,
        partner_ma_threshold: float = 0.45,
        partner_fit_threshold: float = 0.50,
    ) -> "BDRecommendation":
        """
        Construct a BD recommendation from probability + fit scores.

        Action logic:
          acquire  — M&A prob ≥ acquire_ma_threshold AND fit ≥ acquire_fit_threshold
                     AND deal_value > current_price (positive deal premium)
          partner  — M&A prob ≥ partner_ma_threshold AND fit ≥ partner_fit_threshold
                     AND deal_value > current_price
          pass     — otherwise (including negative deal premium)
        """
        if estimated_deal_value <= current_price:
            implied_premium_pct = (estimated_deal_value / current_price - 1.0) * 100.0
            rationale = (
                f"PASS: Estimated deal value (${estimated_deal_value:.1f}) ≤ current price "
                f"(${current_price:.1f}). No positive deal premium; no incentive for target "
                "board to accept."
            )
            return cls(
                ticker=ticker,
                action="pass",
                ma_probability=ma_probability,
                strategic_fit=strategic_fit,
                implied_deal_premium_pct=implied_premium_pct,
                process_risk=process_risk,
                rationale=rationale,
            )

        implied_premium_pct = (estimated_deal_value / current_price - 1.0) * 100.0
        parts: list[str] = []

        if (
            ma_probability >= acquire_ma_threshold
            and strategic_fit >= acquire_fit_threshold
        ):
            action: ActionBD = "acquire"
            parts.append(
                f"ACQUIRE: M&A probability {ma_probability:.0%} ≥ threshold "
                f"{acquire_ma_threshold:.0%}; strategic fit {strategic_fit:.0%} ≥ "
                f"{acquire_fit_threshold:.0%}."
            )
        elif (
            ma_probability >= partner_ma_threshold
            and strategic_fit >= partner_fit_threshold
        ):
            action = "partner"
            parts.append(
                f"PARTNER: M&A probability {ma_probability:.0%} below full-acquisition "
                f"threshold ({acquire_ma_threshold:.0%}) but ≥ partnership "
                f"threshold ({partner_ma_threshold:.0%}); fit {strategic_fit:.0%} ≥ "
                f"{partner_fit_threshold:.0%}."
            )
        else:
            action = "pass"
            parts.append(
                f"PASS: M&A probability {ma_probability:.0%} or strategic fit "
                f"{strategic_fit:.0%} below minimum thresholds."
            )

        if process_risk == "high":
            parts.append("Process risk is HIGH — expect competitive bidding or regulatory scrutiny.")
        elif process_risk == "medium":
            parts.append("Process risk is MEDIUM — potential competing interest.")

        parts.append(
            f"Implied deal premium: {implied_premium_pct:.0f}%. "
            f"Current price: ${current_price:.1f}, estimated deal value: "
            f"${estimated_deal_value:.1f}."
        )

        return cls(
            ticker=ticker,
            action=action,
            ma_probability=ma_probability,
            strategic_fit=strategic_fit,
            implied_deal_premium_pct=implied_premium_pct,
            process_risk=process_risk,
            rationale=" ".join(parts),
        )


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PositionPolicyEngine:
    """
    Deterministic policy engine — evaluates a PositionPolicyInput against
    the configured thresholds and returns a PositionPolicy.
    """

    def __init__(self, config: PositionPolicyConfig | None = None) -> None:
        self.config = config or PositionPolicyConfig()

    def evaluate(self, inp: PositionPolicyInput) -> PositionPolicy:
        """Apply all gates in order and return the policy."""
        cfg = self.config
        discount = inp.sotp_discount_fraction
        downside = inp.downside_risk_pct
        conviction = inp.conviction

        gates: list[str] = []
        action: ActionEquity

        # Gate 1: Downside value-trap (bear case implies large loss)
        if downside > cfg.avoid_downside_threshold:
            action = "avoid"
            gates.append(
                f"AVOID (value trap): downside risk {downside:.0%} > "
                f"threshold {cfg.avoid_downside_threshold:.0%}. "
                f"Bear case ${inp.bear_sotp_per_share:.2f} vs current ${inp.current_price:.2f}."
            )

        # Gate 2: Low conviction
        elif conviction < cfg.min_conviction:
            action = "avoid"
            gates.append(
                f"AVOID (conviction): conviction {conviction:.2f} < "
                f"minimum {cfg.min_conviction:.2f}."
            )

        # Gate 3: Trading at premium to SOTP
        elif discount < 0:
            action = "avoid"
            gates.append(
                f"AVOID (premium): current price ${inp.current_price:.2f} exceeds "
                f"base SOTP ${inp.base_sotp_per_share:.2f} "
                f"(discount {discount:.0%}). No margin of safety."
            )

        # Gate 4: No near-term catalyst (downgrade to monitor)
        elif inp.next_catalyst_days > cfg.catalyst_gate_days:
            action = "monitor"
            gates.append(
                f"MONITOR (catalyst gate): next catalyst in "
                f"{inp.next_catalyst_days}d > gate {cfg.catalyst_gate_days}d. "
                "Waiting for clearer entry timing."
            )

        # Gate 5: Buy — deep discount + strong conviction
        elif (
            discount >= cfg.buy_discount_threshold
            and conviction >= _BUY_CONVICTION_FLOOR
        ):
            action = "buy"
            gates.append(
                f"BUY: SOTP discount {discount:.0%} ≥ {cfg.buy_discount_threshold:.0%} "
                f"and conviction {conviction:.2f} ≥ {_BUY_CONVICTION_FLOOR:.2f}."
            )

        # Gate 6: Add — moderate discount
        elif discount >= cfg.add_discount_threshold:
            action = "add"
            gates.append(
                f"ADD: SOTP discount {discount:.0%} ≥ {cfg.add_discount_threshold:.0%} "
                f"but below buy threshold {cfg.buy_discount_threshold:.0%} "
                f"or conviction {conviction:.2f} < {_BUY_CONVICTION_FLOOR:.2f}."
            )

        # Default: monitor
        else:
            action = "monitor"
            gates.append(
                f"MONITOR: SOTP discount {discount:.0%} < add threshold "
                f"{cfg.add_discount_threshold:.0%}. Watching for better entry."
            )

        # Sizing
        sizing_pct = 0.0
        if action in ("buy", "add"):
            sizing_pct = self._compute_sizing(inp, action)

        # Existing position cap
        if action == "add" and inp.existing_position_pct > 0:
            remaining = max(0.0, cfg.max_position_pct - inp.existing_position_pct)
            if sizing_pct > remaining:
                sizing_pct = remaining
                gates.append(
                    f"Size capped at remaining capacity {remaining:.1f}% "
                    f"(existing: {inp.existing_position_pct:.1f}%, "
                    f"max: {cfg.max_position_pct:.1f}%)."
                )

        # Catalyst context
        if inp.catalyst_description:
            gates.append(
                f"Next catalyst: '{inp.catalyst_description}' in ~{inp.next_catalyst_days}d."
            )

        # Risk summary
        gates.append(
            f"Bull/Bear range: ${inp.bull_sotp_per_share:.2f} / "
            f"${inp.bear_sotp_per_share:.2f} vs current ${inp.current_price:.2f}. "
            f"Implied upside: {inp.implied_upside_pct:.0f}%."
        )

        return PositionPolicy(
            ticker=inp.ticker,
            action=action,
            sizing_pct=round(sizing_pct, 2),
            base_sotp_per_share=inp.base_sotp_per_share,
            downside_case_per_share=inp.bear_sotp_per_share,
            upside_case_per_share=inp.bull_sotp_per_share,
            current_price=inp.current_price,
            implied_upside_pct=inp.implied_upside_pct,
            downside_risk_pct=downside,
            catalyst_gate=inp.catalyst_description,
            next_catalyst_days=inp.next_catalyst_days,
            rationale=" ".join(gates),
        )

    def _compute_sizing(self, inp: PositionPolicyInput, action: ActionEquity) -> float:
        cfg = self.config
        discount = inp.sotp_discount_fraction

        # Base size: scaled by discount depth and conviction
        base = discount * inp.conviction * cfg.sizing_scale

        # Catalyst proximity boost
        if inp.next_catalyst_days <= cfg.catalyst_boost_days:
            base *= 1.0 + cfg.catalyst_boost_pct

        # Downside haircut (downside between 75% and 100% of avoid threshold)
        soft_haircut_floor = cfg.avoid_downside_threshold * 0.75
        if inp.downside_risk_pct > soft_haircut_floor:
            base *= cfg.downside_haircut

        # Liquidity haircut
        if inp.adv_millions < cfg.min_adv_millions:
            base *= cfg.liquidity_haircut

        # Cap at max_position_pct
        return min(cfg.max_position_pct, max(0.0, base))

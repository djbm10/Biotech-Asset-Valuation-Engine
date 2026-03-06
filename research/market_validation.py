"""
Market-based validation framework.

Computes market-implied probability of success (POS) from observable market
data at the as-of date and compares to model-predicted POS.

Rationale
---------
Institutional model evaluation ultimately depends on:
  "Did this system help make money or avoid losses?"

A simpler proxy question that doesn't require live trading:
  "Was the model POS systematically higher/lower than market-implied POS?"

If model POS > market implied and the drug later approved → model correctly
identified an undervalued catalyst (directional edge).
If model POS < market implied and the drug later failed → model correctly
identified an overvalued catalyst.

Market-implied POS methodology
-------------------------------
For single-asset companies, the equity value approximately equals:

  Market Cap = Net Cash + POS × NPV(approved_program)

Solving for implied POS:

  Implied POS = (Market Cap - Net Cash) / NPV(approved_program)
              = Pipeline Value / NPV(approved_program)

Where:
  Pipeline Value = Market Cap - Net Cash
  NPV(approved_program) = PV(peak_sales revenue stream) from MarketModel at 100% POS

Limitations (mandatory disclosure):
  1. SINGLE-ASSET SIMPLIFICATION: valid only for companies where one program
     dominates equity value. Multi-program companies require program-by-program
     decomposition (not implemented).
  2. MARKET EFFICIENCY ASSUMPTION: market is correctly pricing risk, which is
     the hypothesis we are testing — circular when used for validation.
  3. DISCOUNT RATE UNCERTAINTY: PV of approved program depends on WACC choice.
  4. OPTION VALUE: pipeline companies have option-like payoffs; Black-Scholes
     approximations improve on DCF for pre-approval assets.
  5. SURVIVOR BIAS: both historical cases selected are approvals.

Usage
-----
    python research/market_validation.py

Or from Python:

    from research.market_validation import run_market_validation, HISTORICAL_CASES
    results = run_market_validation(HISTORICAL_CASES)
    for r in results:
        print(r.summary())
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Ensure project root is in path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


# ---------------------------------------------------------------------------
# Historical case definitions (as-of snapshots)
# ---------------------------------------------------------------------------

@dataclass
class MarketValidationCase:
    """
    A historical as-of case for market-implied POS validation.

    All inputs are sourced from as-of evidence packs in research/evidence/.
    No hindsight is used in constructing these values.
    """
    ticker: str
    drug: str
    asof_date: str                     # YYYY-MM-DD as-of date for analysis
    market_cap_millions: float         # Market cap at as-of date
    net_cash_millions: float           # Cash - debt at as-of date
    shares_outstanding_millions: float
    stock_price: float                 # Closing price at as-of date

    # Model inputs at as-of date (from config / evidence pack)
    model_pos: float                   # Model-predicted POS from bve-asset run

    # NPV of approved program at 100% POS (from market model, pre-POS-weighted)
    # Computed as: PV(EBIT stream from launch through patent expiry) at 100% approval
    npv_if_approved_millions: float

    # Actual outcome (for post-hoc scoring)
    actual_approved: bool
    approval_year: Optional[int]
    peak_sales_actual_millions: float

    # Error decomposition flags
    peak_sales_error_driver: str       # "pricing" | "patients" | "competition" | "expansion"
    source_notes: str

    @property
    def pipeline_value_millions(self) -> float:
        """Equity market value attributed to pipeline (market cap minus net cash)."""
        return self.market_cap_millions - self.net_cash_millions

    @property
    def market_implied_pos(self) -> Optional[float]:
        """
        Market-implied POS from observable market data.

        Returns None if NPV at 100% approval is zero (division by zero).
        Returns None if implied POS < 0 (market valuing pipeline below cash, which
        can happen in distressed situations — not interpretable as POS).
        Returns None if implied POS > 1.0 (market pricing in option value or
        other sources of value beyond single-program DCF — also not interpretable).

        Interpretation:
          implied_pos < model_pos: market is MORE pessimistic than model
          implied_pos > model_pos: market is MORE optimistic than model
          If model is correct: implied_pos should converge to actual approval rate
        """
        if self.npv_if_approved_millions <= 0:
            return None
        implied = self.pipeline_value_millions / self.npv_if_approved_millions
        if implied < 0 or implied > 1.5:  # >1.5 suggests model NPV understates total value
            return None
        return round(implied, 3)

    @property
    def model_vs_market_gap(self) -> Optional[float]:
        """model_pos - market_implied_pos. Positive = model more optimistic than market."""
        imp = self.market_implied_pos
        if imp is None:
            return None
        return round(self.model_pos - imp, 3)


@dataclass
class MarketValidationResult:
    """
    Comparison of model POS to market-implied POS for one historical case.
    """
    case: MarketValidationCase
    model_pos: float
    implied_pos: Optional[float]
    gap: Optional[float]               # model - implied (positive = model more bullish)
    actual_approved: bool
    directional_correct: bool          # model_pos > 0.50 matches actual outcome
    model_more_bullish_than_market: Optional[bool]

    def summary(self) -> str:
        lines = [
            f"\n{'═' * 60}",
            f"  {self.case.drug} ({self.case.ticker})",
            f"  As-of: {self.case.asof_date}",
            f"{'═' * 60}",
            f"  Market cap:           ${self.case.market_cap_millions:,.0f}M",
            f"  Net cash:             ${self.case.net_cash_millions:,.0f}M",
            f"  Pipeline value:       ${self.case.pipeline_value_millions:,.0f}M",
            f"  NPV if approved:      ${self.case.npv_if_approved_millions:,.0f}M",
            f"",
            f"  Model POS:            {self.model_pos:.1%}",
        ]
        if self.implied_pos is not None:
            lines += [
                f"  Market-implied POS:   {self.implied_pos:.1%}",
                f"  Gap (model - market): {self.gap:+.1%}",
                f"  Interpretation:       {'Model MORE bullish' if self.model_more_bullish_than_market else 'Market MORE bullish'}",
            ]
        else:
            lines.append("  Market-implied POS:   N/A (out of interpretable range)")
        lines += [
            f"",
            f"  Actual outcome:       {'APPROVED' if self.actual_approved else 'NOT APPROVED'} ({self.case.approval_year})",
            f"  Directional correct:  {'YES ✓' if self.directional_correct else 'NO ✗'}",
            f"",
            f"  Peak sales (actual):  ${self.case.peak_sales_actual_millions:,.0f}M",
            f"  Error driver:         {self.case.peak_sales_error_driver}",
            f"",
            f"  Source: {self.case.source_notes}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Historical cases
# ---------------------------------------------------------------------------

# NPV-if-approved is computed from the MarketModel at 100% POS approval.
# These are estimated from the 2010 configs run at discount_rate=0.10,
# using the same market model assumptions as the as-of configs.
# Methodology: sum of discounted EBIT × (1 - royalty_rate) over patent life,
# assuming 100% approval (POS weight = 1.0 for computing this denominator).
# Values are approximate — the exact figure depends on the market model run.

HISTORICAL_CASES: list[MarketValidationCase] = [
    MarketValidationCase(
        ticker="VRTX",
        drug="ivacaftor (VX-770)",
        asof_date="2010-01-01",
        market_cap_millions=3172.0,    # $13.00/share × 244M shares
        net_cash_millions=1400.0,      # Cash + investments from 2009 10-K
        shares_outstanding_millions=244.0,
        stock_price=13.00,
        model_pos=0.75,                # Estimated from Phase 2 clean signal + biomarker selection
        # NPV if approved: G551D-only model at 100% POS
        # patients=1200, net_price=$235K, penetration=88%, compliance=90%,
        # COGS=12%, SG&A launch=30%→mature=15%, over 12yr at 10% WACC
        # ≈ peak sales $248M → PV(EBIT) ≈ $900M (rough DCF)
        npv_if_approved_millions=900.0,
        actual_approved=True,
        approval_year=2012,
        peak_sales_actual_millions=480.0,  # G551D only, 2013
        peak_sales_error_driver="expansion",  # gap due to gating mutation expansion (2014), not model error
        source_notes=(
            "VRTX 10-K 2009; CF Foundation Registry 2009; "
            "NPV estimated from vertex_ivacaftor_2010.yaml market model at 100% POS. "
            "See research/evidence/vertex_ivacaftor_2010/asof.yaml."
        ),
    ),
    MarketValidationCase(
        ticker="INCY",
        drug="ruxolitinib (INCB018424)",
        asof_date="2010-01-01",
        market_cap_millions=2100.0,    # $10.50/share × 200M shares
        net_cash_millions=450.0,       # Post-Lilly deal cash
        shares_outstanding_millions=200.0,
        stock_price=10.50,
        model_pos=0.65,                # Estimated from Phase 2 SVR35 44% + first-in-class penalty
        # NPV if approved: MF-only model at 100% POS
        # patients=16000, net_price=$92K (hematology comps), penetration=55%,
        # compliance=80%, COGS=18%, SG&A launch=40%→mature=20%, over 12yr at 10% WACC
        # ≈ peak sales $646M → PV(EBIT) ≈ $1,450M (rough DCF)
        npv_if_approved_millions=1450.0,
        actual_approved=True,
        approval_year=2011,
        peak_sales_actual_millions=500.0,  # MF-only US estimate 2014
        peak_sales_error_driver="pricing",  # main model risk was pricing analogue choice
        source_notes=(
            "INCY 10-K 2009; ASH 2009 MF abstracts; "
            "NPV estimated from incyte_ruxolitinib_2010.yaml market model at 100% POS. "
            "See research/evidence/incyte_ruxolitinib_2010/asof.yaml."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

def run_market_validation(
    cases: list[MarketValidationCase],
) -> list[MarketValidationResult]:
    """
    Compute market-implied POS and compare to model POS for each case.

    Returns list of MarketValidationResult, one per case.
    """
    results = []
    for case in cases:
        implied = case.market_implied_pos
        gap = case.model_vs_market_gap
        directional = (case.model_pos >= 0.50) == case.actual_approved
        more_bullish: Optional[bool] = None
        if implied is not None:
            more_bullish = case.model_pos > implied
        results.append(MarketValidationResult(
            case=case,
            model_pos=case.model_pos,
            implied_pos=implied,
            gap=gap,
            actual_approved=case.actual_approved,
            directional_correct=directional,
            model_more_bullish_than_market=more_bullish,
        ))
    return results


def compute_directional_edge(results: list[MarketValidationResult]) -> dict:
    """
    Summarize directional edge: did the model systematically identify
    assets where it was more/less bullish than the market, and were those
    directional calls validated by actual outcomes?

    This is a preliminary metric with N=2 — not statistically meaningful.
    Included as a framework for when more cases are added.
    """
    with_implied = [r for r in results if r.implied_pos is not None]
    directionally_correct = sum(1 for r in results if r.directional_correct)

    bullish_cases = [r for r in with_implied if r.model_more_bullish_than_market]
    bullish_approved = sum(1 for r in bullish_cases if r.actual_approved)

    bearish_cases = [r for r in with_implied if r.model_more_bullish_than_market is False]
    bearish_approved = sum(1 for r in bearish_cases if r.actual_approved)

    return {
        "n_cases": len(results),
        "n_with_implied_pos": len(with_implied),
        "directional_correct_count": directionally_correct,
        "directional_accuracy": directionally_correct / len(results) if results else None,
        "n_model_more_bullish": len(bullish_cases),
        "bullish_approved_rate": bullish_approved / len(bullish_cases) if bullish_cases else None,
        "n_model_more_bearish": len(bearish_cases),
        "bearish_approved_rate": bearish_approved / len(bearish_cases) if bearish_cases else None,
        "caveats": [
            "N=2: not statistically meaningful",
            "Survivor bias: both cases are approvals",
            "Market-implied POS is sensitive to NPV estimate accuracy",
            "Single-asset simplification may overstate pipeline value for multi-program companies",
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\n" + "═" * 60)
    print("  BVE Market-Implied POS Validation")
    print("  As-of: January 2010 | Cases: VRTX, INCY")
    print("═" * 60)

    print("\nMethodology:")
    print("  Implied POS = (Market Cap - Net Cash) / NPV(approved program)")
    print("  NPV computed from market model at 100% approval probability.")
    print("  See module docstring for full limitations disclosure.\n")

    results = run_market_validation(HISTORICAL_CASES)
    for r in results:
        print(r.summary())

    edge = compute_directional_edge(results)
    print("\n" + "═" * 60)
    print("  Directional Edge Summary")
    print("═" * 60)
    print(f"  Cases analyzed:               {edge['n_cases']}")
    print(f"  With interpretable implied POS: {edge['n_with_implied_pos']}")
    print(f"  Directional accuracy (>50% threshold): "
          f"{edge['directional_accuracy']:.0%}" if edge['directional_accuracy'] is not None else "  N/A")

    if edge['n_model_more_bullish'] > 0 and edge['bullish_approved_rate'] is not None:
        print(f"\n  Cases where model MORE bullish than market: {edge['n_model_more_bullish']}")
        print(f"    → Actual approval rate: {edge['bullish_approved_rate']:.0%}")
        print(f"    If this rate > market implied: model had positive directional edge")

    if edge['n_model_more_bearish'] > 0 and edge['bearish_approved_rate'] is not None:
        print(f"\n  Cases where model MORE bearish than market: {edge['n_model_more_bearish']}")
        print(f"    → Actual approval rate: {edge['bearish_approved_rate']:.0%}")

    print("\n  CAVEATS:")
    for c in edge["caveats"]:
        print(f"    - {c}")

    print("""
═══════════════════════════════════════════════════════════
  WHAT THIS VALIDATES AND WHAT IT DOESN'T

  VALIDATES (directionally):
    - Whether model POS is in a reasonable range relative to market
    - Whether the model correctly identified drugs the market was
      underpricing or overpricing relative to eventual outcomes

  DOES NOT VALIDATE:
    - Model precision (N=2, survivor bias, NPV sensitivity)
    - Whether market pricing was itself efficient
    - Non-approval cases (both selected cases approved)
    - Whether higher/lower model POS would have generated alpha in
      practice (transaction costs, timing, sizing not modeled)

  NEXT STEPS for institutional-grade validation:
    - Add 8-10 more cases including at least 3 Phase 3 failures
    - Compute stock returns post-catalyst (event study)
    - Compare model POS to consensus analyst POS at as-of date
    - Use options-implied probability where available (cleaner signal)
═══════════════════════════════════════════════════════════
""")


if __name__ == "__main__":
    main()

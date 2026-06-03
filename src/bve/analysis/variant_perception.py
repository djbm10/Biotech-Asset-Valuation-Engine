"""
Variant Perception Back-Solve — Sprint 34.

Back-solves the market's implicit assumptions from the current enterprise
value, answering: "What must the market believe for today's price to be fair?"

The module isolates the portion of company EV attributable to the modeled
asset, then inverts the rNPV equation across five dimensions:

  1. Probability of approval
  2. Peak sales
  3. Peak penetration
  4. Net price per patient
  5. Eligible patient population

Because asset-level EV allocation is uncertain (a company may have multiple
assets, royalty streams, platform value), the module reports a range across
three allocation cases: conservative, base, aggressive.

Core formula
------------
    market_implied_POS =
        (asset_implied_EV
         + pv_expected_remaining_dev_costs
         − pv_receivable_milestones
         − upfront_receipts)
        / pv_full_success_after_tax_fcf

Where:
    asset_implied_EV          = company_EV
                                 − other_pipeline_value
                                 − royalty_stream_value
                                 − platform_value
                                 − non_core_value

    pv_full_success_after_tax_fcf = RNPVResult.gross_revenue_pv_millions
        (already = Σ_t [after_tax_FCF_t × net_ownership / (1+r)^t],
        no probability weighting)

    pv_expected_remaining_dev_costs = RNPVResult.trial_costs_pv_millions
        (probability-weighted PV of all remaining phase costs)

Commercial back-solves (2–5) share the same revenue scale factor:
    revenue_scale = implied_gross_pv / model_gross_pv

    implied_peak_sales     = model_peak_sales      × revenue_scale
    implied_penetration    = model_peak_penetration × revenue_scale  (if patients/price known)
    implied_net_price      = model_net_price        × revenue_scale  (if patients/pen known)
    implied_eligible_pts   = model_eligible_patients × revenue_scale (if price/pen known)

Guardrails
----------
- implied_pos < 0  : asset_implied_EV is negative or costs dominate; flag "ev_below_cost"
- implied_pos > 1  : market pricing more than full-success; flag "ev_above_full_success"
- gross_pv <= 0    : denominator invalid; flag "pv_fcf_invalid"
- no current_price : back-solve not possible; return None
"""
from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from bve.valuation.outputs import ValuationOutput


# ---------------------------------------------------------------------------
# Guardrail identifiers
# ---------------------------------------------------------------------------

GuardrailCode = Literal[
    "ev_below_cost",        # implied_pos < 0
    "ev_above_full_success",# implied_pos > 1
    "pv_fcf_invalid",       # gross_revenue_pv <= 0
    "no_price",             # current_price not set
    "multi_asset_required", # asset_ids > 1 and no explicit allocation
    "implied_pos_clipped",  # raw_pos outside [0,1] — clipped for commercial back-solves
]

VariantCategory = Literal[
    "clinical",     # POS gap ≥ 15pp and dominant
    "commercial",   # peak-sales gap ≥ 30% and dominant
    "pricing",      # net-price gap ≥ 30% and POS gap < 15pp
    "mixed",        # both clinical and commercial significant
    "allocation",   # gap disappears under aggressive asset allocation
    "indeterminate",# not enough information to classify
]


# ---------------------------------------------------------------------------
# AssetAllocationSpec
# ---------------------------------------------------------------------------

class AssetAllocationSpec(BaseModel):
    """
    Declares the value of non-modeled assets to be subtracted from company EV
    before back-solving the modeled asset's implied assumptions.

    Three allocation cases: conservative (least EV to the modeled asset),
    base (central estimate), aggressive (most EV to the modeled asset).

    All deduction fields default to 0.0 so that a single-asset company with
    no partnerships requires no explicit input.

    Parameters
    ----------
    other_pipeline_conservative / base / aggressive : float
        Estimated value of all pipeline assets NOT included in this valuation,
        in USD millions.  Conservative allocates more to other assets (less to
        the modeled asset); aggressive allocates less to other assets (more to
        the modeled asset).

    royalty_stream_value : float
        PV of royalty income from existing out-licensed programs (USD millions).
        Applied identically across all three cases (typically well-defined).

    platform_value : float
        Value assigned to the discovery / technology platform beyond individual
        programs (USD millions).  Set to 0 when not applicable.

    non_core_value : float
        Cash, other non-pipeline assets, or business segments unrelated to the
        modeled asset (USD millions).  Usually 0 — net cash is handled via
        company.net_cash_millions already.
    """
    model_config = ConfigDict(frozen=True)

    # Other pipeline assets — vary by allocation case
    other_pipeline_conservative: float = Field(default=0.0, ge=0.0,
        description="Value of other pipeline (conservative: high deduction, less to modeled asset)")
    other_pipeline_base: float = Field(default=0.0, ge=0.0,
        description="Value of other pipeline (base estimate)")
    other_pipeline_aggressive: float = Field(default=0.0, ge=0.0,
        description="Value of other pipeline (aggressive: low deduction, more to modeled asset)")

    # Fixed deductions — same across all cases
    royalty_stream_value: float = Field(default=0.0, ge=0.0,
        description="PV of existing royalty income streams (USD millions)")
    platform_value: float = Field(default=0.0, ge=0.0,
        description="Technology platform value beyond individual programs (USD millions)")
    non_core_value: float = Field(default=0.0, ge=0.0,
        description="Non-pipeline assets not in net_cash_millions (USD millions)")

    def total_fixed_deductions(self) -> float:
        """Sum of deductions that don't vary by allocation case."""
        return self.royalty_stream_value + self.platform_value + self.non_core_value

    def other_pipeline(self, case: str) -> float:
        """Return the other-pipeline deduction for the given case."""
        if case == "conservative":
            return self.other_pipeline_conservative
        if case == "aggressive":
            return self.other_pipeline_aggressive
        return self.other_pipeline_base


# ---------------------------------------------------------------------------
# BackSolvePoint — one allocation case
# ---------------------------------------------------------------------------

class BackSolvePoint(BaseModel):
    """
    All back-solved market assumptions for one allocation case.

    Fields are None when the back-solve is invalid (e.g. negative denominator,
    missing market data, or the base commercial driver is not available in
    the MarketModel).
    """
    model_config = ConfigDict(frozen=True)

    case: Literal["conservative", "base", "aggressive"]

    # EV isolation
    company_ev_millions: float
    other_deductions_millions: float          # total deducted from company EV
    asset_implied_ev_millions: float          # company_ev - deductions

    # Back-solve 1: implied POS
    implied_pos: Optional[float]              # None when guardrail fires
    raw_implied_pos: float                    # unclamped value (may be <0 or >1)

    # Back-solve 2: implied peak sales
    implied_peak_sales_millions: Optional[float]

    # Back-solve 3–5: granular commercial drivers (None when not applicable)
    implied_peak_penetration: Optional[float] = None   # requires patients + price in model
    implied_net_price_usd: Optional[float] = None      # requires patients + penetration
    implied_eligible_patients: Optional[float] = None  # requires price + penetration


# ---------------------------------------------------------------------------
# VariantPerceptionResult — full output
# ---------------------------------------------------------------------------

class VariantPerceptionResult(BaseModel):
    """
    Full variant perception back-solve result.

    Contains three allocation cases (conservative/base/aggressive) plus
    model estimates, gap table, guardrails, and a memo interpretation.
    """
    model_config = ConfigDict(frozen=True)

    # Market inputs used
    current_price: float
    shares_outstanding_millions: float
    market_cap_millions: float
    net_cash_millions: float
    company_ev_millions: float                  # market_cap - net_cash

    # Structural PV inputs (from RNPVResult)
    pv_full_success_fcf_millions: float         # gross_revenue_pv_millions
    pv_remaining_dev_costs_millions: float      # trial_costs_pv_millions
    pv_receivable_milestones_millions: float    # deal_milestone_receipts_pv_millions
    upfront_receipts_millions: float            # upfront_receipt_millions

    # Model estimates (for gap comparison)
    model_pos: float
    model_peak_sales_millions: float
    model_peak_penetration: Optional[float]     # None when using LOT or TAM mode
    model_net_price_usd: Optional[float]        # None when using LOT or TAM mode
    model_eligible_patients: Optional[float]    # None when using LOT or TAM mode

    # Three allocation cases
    conservative: BackSolvePoint
    base: BackSolvePoint
    aggressive: BackSolvePoint

    # Analysis
    guardrails: list[str] = Field(default_factory=list)
    variant_perception_category: VariantCategory = "indeterminate"
    memo_interpretation: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _company_ev(output: "ValuationOutput") -> float:
    """Compute company EV from market cap and net cash."""
    company = output.company
    price = company.current_price
    shares = company.shares_outstanding_millions
    net_cash = company.net_cash_millions
    return price * shares - net_cash  # type: ignore[operator]


def _numerator(
    asset_implied_ev: float,
    pv_costs: float,
    pv_milestones: float,
    upfront: float,
) -> float:
    """
    The numerator of the market_implied_POS formula.

        asset_implied_EV
        + pv_expected_remaining_dev_costs
        − pv_receivable_milestones
        − upfront_receipts
    """
    return asset_implied_ev + pv_costs - pv_milestones - upfront


def _revenue_scale(numerator: float, pv_fcf: float, model_pos: float) -> Optional[float]:
    """
    Revenue scale factor for commercial back-solves (2–5).

    implied_gross_pv / model_gross_pv
    = numerator / (model_pos × pv_fcf)

    Returns None when the denominator is zero or model_pos is zero.
    """
    denom = model_pos * pv_fcf
    if denom <= 0.0:
        return None
    return numerator / denom


def _back_solve_point(
    case: str,
    company_ev: float,
    other_pipeline: float,
    fixed_deductions: float,
    pv_fcf: float,
    pv_costs: float,
    pv_milestones: float,
    upfront: float,
    model_pos: float,
    model_peak_sales: float,
    model_penetration: Optional[float],
    model_price: Optional[float],
    model_patients: Optional[float],
) -> BackSolvePoint:
    """Compute one BackSolvePoint for a given allocation case."""
    total_deductions = other_pipeline + fixed_deductions
    asset_implied_ev = company_ev - total_deductions

    num = _numerator(asset_implied_ev, pv_costs, pv_milestones, upfront)

    # Back-solve 1: implied POS
    if pv_fcf > 0.0:
        raw_pos = num / pv_fcf
    else:
        raw_pos = float("nan")

    implied_pos: Optional[float]
    if pv_fcf <= 0.0 or raw_pos != raw_pos:  # nan check
        implied_pos = None
    else:
        implied_pos = round(max(0.0, min(1.0, raw_pos)), 4)

    # Back-solve 2: implied peak sales (hold POS constant)
    scale = _revenue_scale(num, pv_fcf, model_pos)
    implied_peak_sales: Optional[float]
    if scale is not None and model_peak_sales > 0.0:
        implied_peak_sales = round(model_peak_sales * scale, 1)
    else:
        implied_peak_sales = None

    # Back-solve 3: implied penetration
    implied_penetration: Optional[float] = None
    if scale is not None and model_penetration is not None and model_penetration > 0.0:
        raw_pen = model_penetration * scale
        implied_penetration = round(min(1.0, max(0.0, raw_pen)), 4)

    # Back-solve 4: implied net price
    implied_price: Optional[float] = None
    if scale is not None and model_price is not None and model_price > 0.0:
        implied_price = round(model_price * scale, 0)

    # Back-solve 5: implied eligible patients
    implied_patients: Optional[float] = None
    if scale is not None and model_patients is not None and model_patients > 0.0:
        implied_patients = round(model_patients * scale, 0)

    return BackSolvePoint(
        case=case,  # type: ignore[arg-type]
        company_ev_millions=round(company_ev, 1),
        other_deductions_millions=round(total_deductions, 1),
        asset_implied_ev_millions=round(asset_implied_ev, 1),
        implied_pos=implied_pos,
        raw_implied_pos=round(raw_pos, 4) if raw_pos == raw_pos else 0.0,
        implied_peak_sales_millions=implied_peak_sales,
        implied_peak_penetration=implied_penetration,
        implied_net_price_usd=implied_price,
        implied_eligible_patients=implied_patients,
    )


def _collect_guardrails(
    pv_fcf: float,
    base_point: BackSolvePoint,
    has_price: bool,
    is_multi_asset: bool,
    allocation_spec: AssetAllocationSpec,
) -> list[str]:
    msgs: list[str] = []

    if not has_price:
        msgs.append(
            "[no_price] current_price not set on Company — back-solve not available."
        )
        return msgs

    if pv_fcf <= 0.0:
        msgs.append(
            "[pv_fcf_invalid] PV(full-success FCF) ≤ 0 — the rNPV model produced no "
            "positive commercial value. Back-solve denominators are invalid."
        )

    if base_point.raw_implied_pos < 0.0:
        msgs.append(
            f"[ev_below_cost] Base asset-implied EV (${base_point.asset_implied_ev_millions:.0f}M) "
            f"is less than remaining development costs — implied POS is negative. "
            f"Check that other_pipeline_base deductions are not overstated, or that "
            f"the asset is not loss-of-value pricing."
        )

    if base_point.raw_implied_pos > 1.0:
        msgs.append(
            f"[ev_above_full_success] Base implied POS ({base_point.raw_implied_pos:.1%}) "
            f"exceeds 100%. The market is pricing more value than the modeled full-success "
            f"scenario. Either the full-success FCF assumptions are too conservative, or "
            f"the asset allocation overstates this asset's contribution to company EV."
        )

    if is_multi_asset and allocation_spec.other_pipeline_base == 0.0:
        msgs.append(
            "[multi_asset_required] Company has multiple asset_ids but "
            "other_pipeline_base = 0. Provide AssetAllocationSpec.other_pipeline_base "
            "to properly isolate this asset's EV contribution."
        )

    return msgs


def _classify_variant(
    model_pos: float,
    model_peak_sales: float,
    base_point: BackSolvePoint,
    con_point: BackSolvePoint,
    agg_point: BackSolvePoint,
) -> VariantCategory:
    """
    Classify what the primary source of variant perception is.

    Rules (applied in order):
    1. allocation: implied_pos converges across cases or gap changes sign
    2. clinical: POS gap > 15pp and > commercial gap
    3. commercial: peak-sales gap > 30% and POS gap < 15pp
    4. mixed: both significant
    5. indeterminate: not enough info
    """
    base_pos = base_point.implied_pos
    if base_pos is None:
        return "indeterminate"

    pos_gap_pp = (model_pos - base_pos) * 100.0

    # Check if gap vanishes under aggressive allocation
    agg_pos = agg_point.implied_pos
    con_pos = con_point.implied_pos
    if agg_pos is not None and con_pos is not None:
        # If sign flips between conservative and aggressive, allocation is the driver
        if (con_pos - model_pos) * (agg_pos - model_pos) < 0:
            return "allocation"

    # Peak-sales gap (use base)
    ps_gap_pct = 0.0
    if base_point.implied_peak_sales_millions is not None and model_peak_sales > 0.0:
        ps_gap_pct = abs(
            (model_peak_sales - base_point.implied_peak_sales_millions) / model_peak_sales
        ) * 100.0

    clinical_significant = round(abs(pos_gap_pp), 4) >= 15.0
    commercial_significant = ps_gap_pct >= 30.0

    if clinical_significant and commercial_significant:
        return "mixed"
    if clinical_significant:
        return "clinical"
    if commercial_significant:
        # Distinguish price vs broader commercial
        if base_point.implied_net_price_usd is not None:
            return "pricing" if ps_gap_pct < 50.0 else "commercial"
        return "commercial"
    return "indeterminate"


def _build_memo(
    result_partial: dict,
    model_pos: float,
    model_peak_sales: float,
    base_point: BackSolvePoint,
    category: VariantCategory,
    guardrails: list[str],
) -> str:
    if guardrails and any("no_price" in g or "pv_fcf_invalid" in g for g in guardrails):
        return "Variant perception back-solve could not be completed — see guardrails."

    base_pos = base_point.implied_pos
    pos_gap_pp = (model_pos - (base_pos or 0.0)) * 100.0
    sign = "+" if pos_gap_pp >= 0 else ""

    asset_ev = base_point.asset_implied_ev_millions
    imp_ps = base_point.implied_peak_sales_millions

    if category == "clinical":
        return (
            f"Variant perception appears primarily clinical: the market is pricing a "
            f"{base_pos:.0%} approval probability vs. the model's {model_pos:.0%} "
            f"({sign}{pos_gap_pp:.0f}pp gap). "
            f"The commercial assumptions (peak sales ~${imp_ps:,.0f}M) "
            f"are broadly consistent with the model's ${model_peak_sales:,.0f}M."
        )
    if category == "commercial":
        return (
            f"Variant perception appears primarily commercial: the market-implied POS "
            f"({base_pos:.0%}) is close to the model ({model_pos:.0%}), but "
            f"implied peak sales (${imp_ps:,.0f}M) are "
            f"{'below' if (imp_ps or 0) < model_peak_sales else 'above'} "
            f"the model's ${model_peak_sales:,.0f}M. "
            f"The market may be discounting label breadth, penetration, or pricing."
        )
    if category == "pricing":
        return (
            f"Variant perception appears driven by pricing and access assumptions. "
            f"Model POS ({model_pos:.0%}) is near market-implied ({base_pos:.0%}), "
            f"but implied peak sales (${imp_ps:,.0f}M) suggest the market prices "
            f"a lower net price or tighter payer access than the model."
        )
    if category == "mixed":
        return (
            f"Variant perception is mixed — both clinical and commercial. "
            f"Market-implied POS is {base_pos:.0%} vs. model {model_pos:.0%} "
            f"({sign}{pos_gap_pp:.0f}pp), and implied peak sales "
            f"(${imp_ps:,.0f}M) differ materially from the model's "
            f"${model_peak_sales:,.0f}M. Edge requires conviction on both axes."
        )
    if category == "allocation":
        return (
            f"Variant perception appears sensitive to asset value allocation. "
            f"The market-implied POS ranges widely across allocation assumptions, "
            f"suggesting the key uncertainty is how much of the ${asset_ev:,.0f}M "
            f"asset-implied EV reflects this specific program."
        )
    # indeterminate
    return (
        f"Back-solve produced an asset-implied EV of ${asset_ev:,.0f}M. "
        f"Market-implied POS ({base_pos:.0%}) vs. model ({model_pos:.0%}); "
        f"implied peak sales ${imp_ps:,.0f}M vs. model ${model_peak_sales:,.0f}M."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def back_solve_variant_perception(
    output: "ValuationOutput",
    allocation_spec: Optional[AssetAllocationSpec] = None,
    *,
    emit_guardrail_warnings: bool = True,
) -> Optional[VariantPerceptionResult]:
    """
    Back-solve the market's implicit assumptions from the current stock price.

    Parameters
    ----------
    output : ValuationOutput
        Full valuation output from the engine.
    allocation_spec : AssetAllocationSpec, optional
        Declares how much of the company EV to attribute to this asset.
        Defaults to AssetAllocationSpec() — i.e., the entire company EV is
        assigned to this asset (appropriate for single-asset companies).
    emit_guardrail_warnings : bool
        When True, each guardrail fires a UserWarning.

    Returns
    -------
    VariantPerceptionResult, or None when current_price is not set.
    """
    company = output.company
    rnpv = output.rnpv

    if not company.current_price or company.current_price <= 0.0:
        return None

    if allocation_spec is None:
        allocation_spec = AssetAllocationSpec()

    # ── Market inputs ─────────────────────────────────────────────────────
    price = company.current_price
    shares = company.shares_outstanding_millions
    net_cash = company.net_cash_millions
    market_cap = price * shares
    company_ev = market_cap - net_cash

    # ── Structural PV inputs from RNPVResult ──────────────────────────────
    pv_fcf = rnpv.gross_revenue_pv_millions            # full-success after-tax FCF PV
    pv_costs = rnpv.trial_costs_pv_millions             # prob-weighted remaining dev costs
    pv_milestones = getattr(rnpv, "deal_milestone_receipts_pv_millions", 0.0)
    upfront = getattr(rnpv, "upfront_receipt_millions", 0.0)

    model_pos = rnpv.cumulative_success_probability
    model_peak_sales = rnpv.peak_sales_millions

    # ── Commercial driver fields (None when using LOT or TAM mode) ────────
    market_model = output.market_model
    model_penetration: Optional[float] = getattr(market_model, "peak_penetration", None)
    model_price: Optional[float] = getattr(market_model, "net_price_per_patient_usd", None)
    model_patients: Optional[float] = (
        float(market_model.addressable_patients_annual)
        if getattr(market_model, "addressable_patients_annual", None) is not None
        else None
    )

    fixed_deductions = allocation_spec.total_fixed_deductions()
    is_multi_asset = len(company.asset_ids) > 1

    # ── Compute three BackSolvePoints ─────────────────────────────────────
    def _make(case: str) -> BackSolvePoint:
        return _back_solve_point(
            case=case,
            company_ev=company_ev,
            other_pipeline=allocation_spec.other_pipeline(case),
            fixed_deductions=fixed_deductions,
            pv_fcf=pv_fcf,
            pv_costs=pv_costs,
            pv_milestones=pv_milestones,
            upfront=upfront,
            model_pos=model_pos,
            model_peak_sales=model_peak_sales,
            model_penetration=model_penetration,
            model_price=model_price,
            model_patients=model_patients,
        )

    con = _make("conservative")
    base = _make("base")
    agg = _make("aggressive")

    # ── Guardrails ────────────────────────────────────────────────────────
    guardrails = _collect_guardrails(
        pv_fcf=pv_fcf,
        base_point=base,
        has_price=True,
        is_multi_asset=is_multi_asset,
        allocation_spec=allocation_spec,
    )

    if emit_guardrail_warnings:
        for msg in guardrails:
            warnings.warn(msg, UserWarning, stacklevel=2)

    # ── Classify and build memo ───────────────────────────────────────────
    category = _classify_variant(model_pos, model_peak_sales, base, con, agg)
    memo = _build_memo(
        result_partial={},
        model_pos=model_pos,
        model_peak_sales=model_peak_sales,
        base_point=base,
        category=category,
        guardrails=guardrails,
    )

    return VariantPerceptionResult(
        current_price=price,
        shares_outstanding_millions=shares,
        market_cap_millions=round(market_cap, 1),
        net_cash_millions=round(net_cash, 1),
        company_ev_millions=round(company_ev, 1),
        pv_full_success_fcf_millions=round(pv_fcf, 1),
        pv_remaining_dev_costs_millions=round(pv_costs, 1),
        pv_receivable_milestones_millions=round(pv_milestones, 1),
        upfront_receipts_millions=round(upfront, 1),
        model_pos=model_pos,
        model_peak_sales_millions=model_peak_sales,
        model_peak_penetration=model_penetration,
        model_net_price_usd=model_price,
        model_eligible_patients=model_patients,
        conservative=con,
        base=base,
        aggressive=agg,
        guardrails=guardrails,
        variant_perception_category=category,
        memo_interpretation=memo,
    )

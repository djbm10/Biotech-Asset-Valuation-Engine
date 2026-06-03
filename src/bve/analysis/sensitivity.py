"""
Sensitivity / Tornado analysis — Sprint 35 (Step 10).

Independently shocks each of N key assumptions ±X% while holding all others
at their base values. The resulting rNPV range for each parameter is ranked by
absolute swing (high_rnpv − low_rnpv) to produce a tornado chart.

This tells you which single input most determines asset value — typically
P(approval) for early-stage assets and peak sales / penetration for late-stage
or commercial-ready assets.

Design
------
- ``SensitivitySpec``: declares one parameter to shock (name, label, shock_pct)
- ``DEFAULT_SENSITIVITY_SPECS``: 8 named specs covering the most material drivers
- ``SensitivityResult``: sorted list of ``SensitivityPoint`` objects + metadata
- ``compute_sensitivity()``: standalone function; takes explicit base_rnpv so the
  full engine does not need to rerun the base case

Each shocked run uses ``compute_rnpv_full()`` — the same economic stack as the
base case (LOE, deal economics, tax profile). No shortcuts.

Shock conventions
-----------------
Relative shocks (POS, peak sales, penetration):
    shocked_value = base_value × (1 ± shock_pct / 100)

Absolute shocks (discount rate, tax rate, patent life, G2N):
    shocked_value = base_value ± absolute_delta

Competitive entries shock: penetration haircut per entrant (not ±%).

Low/High ordering: ``low_rnpv`` is always the lower rNPV outcome regardless
of whether the "low" parameter value produces it (e.g. lower discount rate →
higher rNPV, so the low_rnpv corresponds to the high discount rate).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, ConfigDict, Field

from bve.valuation.outputs import SensitivityPoint

if TYPE_CHECKING:
    from bve.entities.asset import Asset
    from bve.entities.trial import ClinicalTrial
    from bve.models.deal_economics import DealEconomics
    from bve.models.market_model import MarketModel


# ---------------------------------------------------------------------------
# SensitivitySpec
# ---------------------------------------------------------------------------

class SensitivitySpec(BaseModel):
    """
    Specification for one sensitivity parameter.

    Parameters
    ----------
    name : str
        Machine-readable identifier, e.g. ``"pos"``, ``"peak_sales"``.
    label : str
        Human-readable label for chart display, e.g. ``"Phase POS (±20%)``.
    shock_pct : float
        Percentage shock.  Interpretation depends on the parameter type:
        - Relative parameters (POS, peak sales, penetration): multiply base × (1 ± shock_pct/100)
        - Absolute parameters (discount_rate, tax_rate, patent_life, g2n):
          the field ``absolute_delta`` is used instead; shock_pct is informational only.
    absolute_delta : float, optional
        For parameters where an absolute shock is more meaningful.
        When set, overrides the relative shock calculation.
    active : bool
        When False, the spec is skipped. Useful for disabling a spec without
        removing it from the list.
    """
    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    shock_pct: float = Field(ge=0.0, description="Shock magnitude as a percentage; may be 0 when absolute_delta is set")
    absolute_delta: Optional[float] = Field(
        default=None, description="Absolute shock amount (overrides relative calculation)"
    )
    active: bool = True


# ---------------------------------------------------------------------------
# SensitivityResult
# ---------------------------------------------------------------------------

class SensitivityResult(BaseModel):
    """
    Full tornado analysis output.

    Attributes
    ----------
    base_rnpv : float
        The unshocked base-case rNPV used as the anchor for all tornado bars.
    points : list[SensitivityPoint]
        All active sensitivity points, sorted descending by |swing|.
        Each point has ``rank`` set (1 = largest swing).
    dominant_driver : str
        ``parameter`` label of the point with the largest |swing|.
    dominant_is_clinical : bool
        True when the dominant driver is the phase POS parameter — signals
        that value is primarily driven by clinical risk, not commercial risk.
    memo_interpretation : str
        One-sentence plain-English summary, e.g.
        "Value is primarily driven by clinical probability of approval (±$Xm swing),
        followed by peak sales (±$Ym swing)."
    """
    model_config = ConfigDict(frozen=True)

    base_rnpv: float
    points: list[SensitivityPoint]
    dominant_driver: str
    dominant_is_clinical: bool
    memo_interpretation: str


# ---------------------------------------------------------------------------
# Default specs
# ---------------------------------------------------------------------------

DEFAULT_SENSITIVITY_SPECS: list[SensitivitySpec] = [
    SensitivitySpec(name="pos",          label="Phase POS (±20%)",          shock_pct=20.0),
    SensitivitySpec(name="peak_sales",   label="Peak Sales (±30%)",         shock_pct=30.0),
    SensitivitySpec(name="penetration",  label="Peak Penetration (±30%)",   shock_pct=30.0),
    SensitivitySpec(name="discount_rate",label="Discount Rate (±2pp)",      shock_pct=2.0,
                    absolute_delta=0.02),
    SensitivitySpec(name="patent_life",  label="Patent Life (±3 yrs)",      shock_pct=3.0,
                    absolute_delta=3.0),
    SensitivitySpec(name="g2n",          label="Gross-to-Net Rate (±10pp)", shock_pct=10.0,
                    absolute_delta=None),
    SensitivitySpec(name="tax_rate",     label="Eff. Tax Rate (±5pp)",      shock_pct=5.0,
                    absolute_delta=0.05),
    SensitivitySpec(name="competition",  label="Competition (+1/+2 entrants)",
                    shock_pct=15.0),
]

# Names that indicate the dominant driver is clinical risk
_CLINICAL_DRIVER_NAMES = {"pos"}


# ---------------------------------------------------------------------------
# Internal shock helpers
# ---------------------------------------------------------------------------

def _shocked_rnpv(asset, trials, market_model, loe_profile, deal, **updates_market) -> float:
    from bve.models.rnpv_model import compute_rnpv_full
    mm = market_model.model_copy(update={**updates_market, "uptake_curve": None})
    return compute_rnpv_full(asset, trials, mm, loe_profile=loe_profile, deal=deal).rnpv_millions


def _shocked_rnpv_asset(asset, trials, market_model, loe_profile, deal, **updates_asset) -> float:
    from bve.models.rnpv_model import compute_rnpv_full
    a = asset.model_copy(update=updates_asset)
    return compute_rnpv_full(a, trials, market_model, loe_profile=loe_profile, deal=deal).rnpv_millions


def _shocked_rnpv_trials(asset, trials, market_model, loe_profile, deal, shocked_trials) -> float:
    from bve.models.rnpv_model import compute_rnpv_full
    return compute_rnpv_full(asset, shocked_trials, market_model,
                             loe_profile=loe_profile, deal=deal).rnpv_millions


def _make_point(
    label: str,
    shock_pct: float,
    base_rnpv: float,
    lo_rnpv: float,
    hi_rnpv: float,
    lo_val: float,
    hi_val: float,
) -> SensitivityPoint:
    """
    Build a SensitivityPoint ensuring low_rnpv ≤ high_rnpv regardless of shock direction.
    """
    if lo_rnpv <= hi_rnpv:
        return SensitivityPoint(
            parameter=label, base_rnpv=base_rnpv, shock_pct=shock_pct,
            low_value=lo_val, high_value=hi_val,
            low_rnpv=lo_rnpv, high_rnpv=hi_rnpv,
        )
    # Swap — the "low" parameter value produced the higher rNPV
    return SensitivityPoint(
        parameter=label, base_rnpv=base_rnpv, shock_pct=shock_pct,
        low_value=hi_val, high_value=lo_val,
        low_rnpv=hi_rnpv, high_rnpv=lo_rnpv,
    )


# ---------------------------------------------------------------------------
# Per-parameter shock runners
# ---------------------------------------------------------------------------

def _run_pos(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    f = spec.shock_pct / 100.0
    t_lo = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * (1 - f))})
            for t in trials]
    t_hi = [t.model_copy(update={"success_probability": min(0.99, t.success_probability * (1 + f))})
            for t in trials]
    lo = _shocked_rnpv_trials(asset, trials, market_model, loe_profile, deal, t_lo)
    hi = _shocked_rnpv_trials(asset, trials, market_model, loe_profile, deal, t_hi)
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo, hi,
                       lo_val=1.0 - f, hi_val=1.0 + f)


def _run_peak_sales(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    f = spec.shock_pct / 100.0
    mm = market_model
    if mm.total_addressable_market_millions is not None:
        tam = mm.total_addressable_market_millions
        lo = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           total_addressable_market_millions=tam * (1 - f))
        hi = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           total_addressable_market_millions=tam * (1 + f))
        lo_val = tam * (1 - f)
        hi_val = tam * (1 + f)
    else:
        price = mm.net_price_per_patient_usd or 100_000.0
        lo = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           net_price_per_patient_usd=price * (1 - f))
        hi = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           net_price_per_patient_usd=price * (1 + f))
        lo_val = price * (1 - f)
        hi_val = price * (1 + f)
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo, hi, lo_val, hi_val)


def _run_penetration(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    f = spec.shock_pct / 100.0
    pen = market_model.peak_penetration
    lo = _shocked_rnpv(asset, trials, market_model, loe_profile, deal,
                       peak_penetration=max(0.001, pen * (1 - f)))
    hi = _shocked_rnpv(asset, trials, market_model, loe_profile, deal,
                       peak_penetration=min(0.999, pen * (1 + f)))
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo, hi,
                       lo_val=pen * (1 - f), hi_val=pen * (1 + f))


def _run_discount_rate(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    delta = spec.absolute_delta or (spec.shock_pct / 100.0)
    r = asset.discount_rate
    lo_r = max(0.01, r - delta)
    hi_r = min(0.50, r + delta)
    # Higher rate → lower NPV, so: hi_rate = lo_rnpv
    lo_rnpv = _shocked_rnpv_asset(asset, trials, market_model, loe_profile, deal, discount_rate=hi_r)
    hi_rnpv = _shocked_rnpv_asset(asset, trials, market_model, loe_profile, deal, discount_rate=lo_r)
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo_rnpv, hi_rnpv,
                       lo_val=hi_r * 100, hi_val=lo_r * 100)


def _run_patent_life(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    delta = int(spec.absolute_delta or 3)
    pl = market_model.patent_life_years
    lo = _shocked_rnpv(asset, trials, market_model, loe_profile, deal,
                       patent_life_years=max(1, pl - delta))
    hi = _shocked_rnpv(asset, trials, market_model, loe_profile, deal,
                       patent_life_years=pl + delta)
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo, hi,
                       lo_val=float(max(1, pl - delta)), hi_val=float(pl + delta))


def _run_g2n(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    # G2N shock: ±10pp applied as a net-price multiplier (1 ± 0.10)
    f = spec.shock_pct / 100.0
    mm = market_model
    if mm.total_addressable_market_millions is not None:
        tam = mm.total_addressable_market_millions
        lo = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           total_addressable_market_millions=tam * (1 - f))
        hi = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           total_addressable_market_millions=tam * (1 + f))
    else:
        price = mm.net_price_per_patient_usd or 100_000.0
        lo = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           net_price_per_patient_usd=price * (1 - f))
        hi = _shocked_rnpv(asset, trials, mm, loe_profile, deal,
                           net_price_per_patient_usd=price * (1 + f))
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo, hi,
                       lo_val=f * 100, hi_val=-f * 100)


def _run_tax_rate(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    delta = spec.absolute_delta or (spec.shock_pct / 100.0)
    tax = asset.effective_tax_rate
    lo_tax = max(0.0, tax - delta)
    hi_tax = min(0.50, tax + delta)
    # Higher tax → lower rNPV
    lo_rnpv = _shocked_rnpv_asset(asset, trials, market_model, loe_profile, deal,
                                   effective_tax_rate=hi_tax)
    hi_rnpv = _shocked_rnpv_asset(asset, trials, market_model, loe_profile, deal,
                                   effective_tax_rate=lo_tax)
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo_rnpv, hi_rnpv,
                       lo_val=hi_tax * 100, hi_val=lo_tax * 100)


def _run_competition(spec, asset, trials, market_model, loe_profile, deal, base_rnpv):
    haircut = spec.shock_pct / 100.0   # 0.15 = 15% per entrant
    pen = market_model.peak_penetration
    pen_1 = max(0.001, pen * (1 - haircut))
    pen_2 = max(0.001, pen * (1 - 2 * haircut))
    lo_rnpv = _shocked_rnpv(asset, trials, market_model, loe_profile, deal, peak_penetration=pen_2)
    hi_rnpv = _shocked_rnpv(asset, trials, market_model, loe_profile, deal, peak_penetration=pen_1)
    return _make_point(spec.label, spec.shock_pct, base_rnpv, lo_rnpv, hi_rnpv,
                       lo_val=pen_2, hi_val=pen_1)


_RUNNERS = {
    "pos":           _run_pos,
    "peak_sales":    _run_peak_sales,
    "penetration":   _run_penetration,
    "discount_rate": _run_discount_rate,
    "patent_life":   _run_patent_life,
    "g2n":           _run_g2n,
    "tax_rate":      _run_tax_rate,
    "competition":   _run_competition,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_sensitivity(
    asset: "Asset",
    trials: "list[ClinicalTrial]",
    market_model: "MarketModel",
    *,
    base_rnpv: float,
    specs: Optional[list[SensitivitySpec]] = None,
    loe_profile: Optional[dict] = None,
    deal: Optional["DealEconomics"] = None,
) -> SensitivityResult:
    """
    Compute tornado sensitivity analysis.

    Parameters
    ----------
    asset : Asset
        The asset being valued (base case).
    trials : list[ClinicalTrial]
        Trials for the base case (unshocked).
    market_model : MarketModel
        Market model for the base case (unshocked).
    base_rnpv : float
        Pre-computed base-case rNPV in USD millions.  Passed explicitly so
        the caller does not need to re-run the engine for the base case.
    specs : list[SensitivitySpec], optional
        Which parameters to shock.  Defaults to ``DEFAULT_SENSITIVITY_SPECS``.
        Inactive specs (``active=False``) are silently skipped.
        Unknown ``name`` values are skipped with a no-op (no error).
    loe_profile : dict, optional
        LOE erosion profile forwarded to ``compute_rnpv_full()`` for each shocked run.
    deal : DealEconomics, optional
        Deal economics forwarded to ``compute_rnpv_full()`` for each shocked run.

    Returns
    -------
    SensitivityResult
        Points sorted descending by |swing|, with rank 1 = largest swing.
    """
    if specs is None:
        specs = DEFAULT_SENSITIVITY_SPECS

    points: list[SensitivityPoint] = []
    for spec in specs:
        if not spec.active:
            continue
        runner = _RUNNERS.get(spec.name)
        if runner is None:
            continue
        pt = runner(spec, asset, trials, market_model, loe_profile, deal, base_rnpv)
        points.append(pt)

    # Sort by |swing| descending and assign ranks
    points.sort(key=lambda p: p.abs_swing, reverse=True)
    ranked: list[SensitivityPoint] = [
        p.model_copy(update={"rank": i + 1}) for i, p in enumerate(points)
    ]

    dominant = ranked[0].parameter if ranked else ""
    dominant_name = "" if not ranked else next(
        (s.name for s in specs if s.label == dominant), ""
    )
    is_clinical = dominant_name in _CLINICAL_DRIVER_NAMES

    memo = _build_memo(ranked, base_rnpv, is_clinical)

    return SensitivityResult(
        base_rnpv=base_rnpv,
        points=ranked,
        dominant_driver=dominant,
        dominant_is_clinical=is_clinical,
        memo_interpretation=memo,
    )


def _build_memo(points: list[SensitivityPoint], base_rnpv: float, is_clinical: bool) -> str:
    if not points:
        return "No sensitivity parameters computed."
    top = points[0]
    swing1 = top.abs_swing
    msg = (
        f"Value is primarily driven by {top.parameter} "
        f"(±${swing1:,.0f}M swing around ${base_rnpv:,.0f}M base)"
    )
    if len(points) >= 2:
        p2 = points[1]
        msg += f", followed by {p2.parameter} (±${p2.abs_swing:,.0f}M)"
    msg += "."
    if is_clinical:
        msg += " Clinical risk dominates — POS improvement would have the largest value impact."
    else:
        msg += " Commercial risk dominates — sales/penetration assumptions are the primary lever."
    return msg

"""
Market expectation math.

Two paths are supported:

1. Stored-snapshot backsolve for ranking and cheap local scans.
   Uses only persisted model_rnpv, model_pos, and market_cap.

2. NAV-style backsolve for richer standalone expectation studies.
   Uses peak-sales assumptions and optional cash estimates.

Phase I extends this into a primary market-expectation comparison layer so each
asset can expose model vs implied PoS, peak sales, dilution, and value in one
place.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

_LOG = logging.getLogger("bve.intelligence.market_expectations")


class MarketExpectation(BaseModel):
    """One row in the market_expectations table."""

    expectation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: str
    expectation_date: date
    implied_pos: Optional[float]          # back-solved; None if market cap unavailable
    implied_success_probability: Optional[float] = None
    model_pos: Optional[float]            # from valuation config / probability model
    pos_gap: Optional[float]              # implied_pos - model_pos
    model_rnpv_millions: Optional[float] = None
    market_cap_millions: Optional[float] = None
    mispricing: Optional[float] = None
    cash_estimate_millions: Optional[float]
    methodology: str = "nav_backsolve"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MarketMispricing(BaseModel):
    """Raw market-cap mispricing signal used by ranking."""

    model_rnpv_millions: float
    market_cap_millions: float
    mispricing: float


class MarketExpectationModuleOutput(BaseModel):
    value: object
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class MarketExpectationComparisonValue(BaseModel):
    asset_id: str
    ticker: str
    model_pos: Optional[float] = None
    implied_pos: Optional[float] = None
    pos_delta: Optional[float] = None
    model_peak_sales_millions: Optional[float] = None
    implied_peak_sales_millions: Optional[float] = None
    peak_sales_delta_millions: Optional[float] = None
    model_dilution_pct: Optional[float] = None
    implied_dilution_pct: Optional[float] = None
    dilution_delta: Optional[float] = None
    financing_adjusted_intrinsic_value_millions: Optional[float] = None
    current_ev_millions: Optional[float] = None
    upside_downside_pct: Optional[float] = None
    consensus_valuation_range_low_millions: Optional[float] = None
    consensus_valuation_range_high_millions: Optional[float] = None
    optionality_not_reflected_millions: Optional[float] = None
    market_cap_millions: Optional[float] = None


class MarketExpectationComparison(BaseModel):
    asset_id: str
    ticker: str
    output: MarketExpectationModuleOutput
    plain_english_summary: str


def compute_market_mispricing(
    *,
    model_rnpv_millions: Optional[float],
    market_cap_millions: Optional[float],
) -> Optional[MarketMispricing]:
    """
    Compute Sprint 5 raw mispricing:

        mispricing = (model_rnpv - market_cap) / market_cap

    Returns None when the inputs are incomplete or the denominator is invalid.
    """
    if model_rnpv_millions is None or market_cap_millions is None or market_cap_millions <= 0:
        return None
    mispricing = (float(model_rnpv_millions) - float(market_cap_millions)) / float(
        market_cap_millions
    )
    return MarketMispricing(
        model_rnpv_millions=float(model_rnpv_millions),
        market_cap_millions=float(market_cap_millions),
        mispricing=round(mispricing, 6),
    )


def compute_implied_success_probability(
    *,
    model_rnpv_millions: Optional[float],
    market_cap_millions: Optional[float],
    model_pos: Optional[float],
) -> Optional[float]:
    """
    Back-solve implied success probability from stored valuation snapshots.

    Uses the proportional relationship:

        model_rnpv = peak_npv * model_pos
        implied_pos = market_cap / peak_npv
                    = market_cap * model_pos / model_rnpv

    Returns None when the stored snapshot is incomplete or degenerate.
    """
    if (
        model_rnpv_millions is None
        or market_cap_millions is None
        or model_pos is None
        or model_rnpv_millions <= 0
        or market_cap_millions <= 0
        or model_pos <= 0
    ):
        return None
    raw_implied = (float(market_cap_millions) * float(model_pos)) / float(model_rnpv_millions)
    return round(max(0.0, min(1.0, raw_implied)), 4)


def compute_implied_peak_sales(
    *,
    market_cap_millions: Optional[float],
    cash_estimate_millions: Optional[float],
    model_pos: Optional[float],
    patent_life_years: int,
    discount_rate: float,
    margin_rate: float,
) -> Optional[float]:
    """
    Back-solve implied peak sales from EV and model PoS.

    Uses the same flat-annuity NAV framing as ``ImpliedPoSEstimator.compute``.
    """
    if (
        market_cap_millions is None
        or model_pos is None
        or model_pos <= 0
        or patent_life_years <= 0
        or margin_rate <= 0
    ):
        return None
    equity_value = float(market_cap_millions) - float(cash_estimate_millions or 0.0)
    if discount_rate > 0:
        pv_factor = (1.0 - (1.0 + discount_rate) ** (-patent_life_years)) / discount_rate
    else:
        pv_factor = float(patent_life_years)
    denominator = float(model_pos) * float(margin_rate) * pv_factor
    if denominator <= 0:
        return None
    return round(max(0.0, equity_value / denominator), 4)


def build_market_expectation_from_snapshot(
    *,
    asset_id: str,
    ticker: str,
    model_rnpv_millions: Optional[float],
    market_cap_millions: Optional[float],
    model_pos: Optional[float],
    expectation_date: Optional[date] = None,
    methodology: str = "stored_rnpv_backsolve",
) -> MarketExpectation:
    """Build a market expectation record from stored DB snapshot fields only."""
    if expectation_date is None:
        expectation_date = datetime.now(timezone.utc).date()

    mispricing_record = compute_market_mispricing(
        model_rnpv_millions=model_rnpv_millions,
        market_cap_millions=market_cap_millions,
    )
    implied_pos = compute_implied_success_probability(
        model_rnpv_millions=model_rnpv_millions,
        market_cap_millions=market_cap_millions,
        model_pos=model_pos,
    )
    pos_gap = None
    if implied_pos is not None and model_pos is not None:
        pos_gap = round(implied_pos - float(model_pos), 4)

    return MarketExpectation(
        asset_id=asset_id,
        ticker=ticker,
        expectation_date=expectation_date,
        implied_pos=implied_pos,
        implied_success_probability=implied_pos,
        model_pos=model_pos,
        pos_gap=pos_gap,
        model_rnpv_millions=(
            float(model_rnpv_millions) if model_rnpv_millions is not None else None
        ),
        market_cap_millions=(
            float(market_cap_millions) if market_cap_millions is not None else None
        ),
        mispricing=mispricing_record.mispricing if mispricing_record is not None else None,
        cash_estimate_millions=None,
        methodology=methodology,
    )


class ImpliedPoSEstimator:
    """
    Computes implied PoS from observed market cap using NAV decomposition.

    Parameters
    ----------
    logger:
        Optional logger override.
    """

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or _LOG

    def compute(
        self,
        *,
        asset_id: str,
        ticker: str,
        market_cap_millions: float,
        model_pos: Optional[float],
        peak_sales_millions: float,
        patent_life_years: int = 12,
        discount_rate: float = 0.12,
        margin_rate: float = 0.35,
        cash_estimate_millions: float = 0.0,
        expectation_date: Optional[date] = None,
    ) -> MarketExpectation:
        """
        Compute implied PoS for one asset.

        The NAV formula used:
            pipeline_value = PV(annuity of peak_sales × margin, patent_life, r)
            implied_pos = (market_cap - cash) / pipeline_value

        Parameters
        ----------
        asset_id, ticker:
            Asset identity.
        market_cap_millions:
            Observed market cap in $M (from market_prices table or yfinance).
        model_pos:
            Our model's cumulative P(approval).  Used to compute pos_gap.
        peak_sales_millions:
            Estimated peak annual revenue in $M (from valuation config).
        patent_life_years:
            Remaining patent exclusivity years (annuity duration).
        discount_rate:
            Risk-free + sector risk premium (default 12% for clinical biotech).
        margin_rate:
            Assumed EBIT margin on peak sales (default 35%).
        cash_estimate_millions:
            Company cash from latest balance sheet ($M).  Default 0 (conservative).
        expectation_date:
            Date of this estimate.  Defaults to today (UTC).

        Returns
        -------
        MarketExpectation
        """
        if expectation_date is None:
            expectation_date = datetime.now(timezone.utc).date()

        implied_pos: Optional[float] = None
        pos_gap: Optional[float] = None

        try:
            if peak_sales_millions <= 0:
                self.logger.warning(
                    "implied_pos skipped: peak_sales_millions <= 0 for asset=%s", asset_id
                )
            else:
                # PV of a flat annuity of peak_sales × margin over patent_life years.
                annual_cash_flow = peak_sales_millions * margin_rate
                if discount_rate > 0:
                    pv_factor = (1.0 - (1.0 + discount_rate) ** (-patent_life_years)) / discount_rate
                else:
                    pv_factor = float(patent_life_years)
                pipeline_pv = annual_cash_flow * pv_factor

                equity_value = market_cap_millions - cash_estimate_millions

                if equity_value < 0:
                    self.logger.warning(
                        "implied_pos: equity_value < 0 for asset=%s "
                        "(market_cap=%.1fM cash=%.1fM); clamping to 0. "
                        "This may indicate cash > market cap or data quality issue.",
                        asset_id,
                        market_cap_millions,
                        cash_estimate_millions,
                    )

                if pipeline_pv > 0:
                    raw_implied = equity_value / pipeline_pv
                    if raw_implied > 1.0:
                        self.logger.info(
                            "implied_pos > 1.0 (%.4f) for asset=%s — "
                            "market cap implies higher PoS than physically possible; "
                            "clamping to 1.0 (speculative premium or stale peak_sales).",
                            raw_implied,
                            asset_id,
                        )
                    # Clamp to [0, 1] — negative equity or extreme outliers are clamped.
                    implied_pos = max(0.0, min(1.0, round(raw_implied, 4)))

                if implied_pos is not None and model_pos is not None:
                    pos_gap = round(implied_pos - model_pos, 4)

        except Exception as exc:
            self.logger.warning("implied_pos compute error asset=%s: %s", asset_id, exc)

        mispricing_record = compute_market_mispricing(
            model_rnpv_millions=None,
            market_cap_millions=market_cap_millions,
        )

        return MarketExpectation(
            asset_id=asset_id,
            ticker=ticker,
            expectation_date=expectation_date,
            implied_pos=implied_pos,
            implied_success_probability=implied_pos,
            model_pos=model_pos,
            pos_gap=pos_gap,
            market_cap_millions=market_cap_millions,
            mispricing=mispricing_record.mispricing if mispricing_record is not None else None,
            cash_estimate_millions=cash_estimate_millions,
        )

    def compute_from_snapshot(
        self,
        *,
        asset_id: str,
        ticker: str,
        model_rnpv_millions: Optional[float],
        market_cap_millions: Optional[float],
        model_pos: Optional[float],
        expectation_date: Optional[date] = None,
    ) -> MarketExpectation:
        """Back-solve expectation fields from stored valuation and price rows only."""
        expectation = build_market_expectation_from_snapshot(
            asset_id=asset_id,
            ticker=ticker,
            model_rnpv_millions=model_rnpv_millions,
            market_cap_millions=market_cap_millions,
            model_pos=model_pos,
            expectation_date=expectation_date,
        )
        if (
            expectation.implied_pos is None
            and model_rnpv_millions is not None
            and market_cap_millions is not None
            and model_pos is not None
        ):
            self.logger.info(
                "stored_snapshot_implied_pos_unavailable asset=%s model_rnpv=%.3f market_cap=%.3f model_pos=%.4f",
                asset_id,
                float(model_rnpv_millions),
                float(market_cap_millions),
                float(model_pos),
            )
        return expectation

    def compute_from_yfinance(
        self,
        *,
        asset_id: str,
        ticker: str,
        model_pos: Optional[float],
        peak_sales_millions: float,
        patent_life_years: int = 12,
        discount_rate: float = 0.12,
        margin_rate: float = 0.35,
    ) -> Optional[MarketExpectation]:
        """
        Convenience method: fetch market cap and cash from yfinance, then compute.

        Returns None if yfinance data is unavailable.
        """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            fast_info = t.fast_info
            mc = getattr(fast_info, "market_cap", None)
            if not mc:
                return None
            market_cap_millions = float(mc) / 1e6

            # Cash from balance sheet (total_cash is in absolute dollars).
            cash_estimate_millions = 0.0
            try:
                bs = t.balance_sheet
                if bs is not None and not bs.empty:
                    cash_row = bs.loc[bs.index.str.contains("Cash", case=False)] if hasattr(bs.index, "str") else None
                    if cash_row is not None and not cash_row.empty:
                        raw_cash = cash_row.iloc[0, 0]
                        if raw_cash and raw_cash > 0:
                            cash_estimate_millions = float(raw_cash) / 1e6
            except Exception:
                pass

            return self.compute(
                asset_id=asset_id,
                ticker=ticker,
                market_cap_millions=market_cap_millions,
                model_pos=model_pos,
                peak_sales_millions=peak_sales_millions,
                patent_life_years=patent_life_years,
                discount_rate=discount_rate,
                margin_rate=margin_rate,
                cash_estimate_millions=cash_estimate_millions,
            )
        except Exception as exc:
            self.logger.warning("yfinance data unavailable for ticker=%s: %s", ticker, exc)
            return None


class MarketExpectationEngine:
    """Phase I comparison engine placing market expectations at the center."""

    def build_comparison(
        self,
        *,
        asset_id: str,
        ticker: str,
        model_pos: Optional[float],
        model_peak_sales_millions: Optional[float],
        market_cap_millions: Optional[float],
        cash_estimate_millions: Optional[float] = None,
        financing_adjusted_intrinsic_value_millions: Optional[float] = None,
        model_dilution_pct: Optional[float] = None,
        implied_dilution_pct: Optional[float] = None,
        consensus_valuation_range_low_millions: Optional[float] = None,
        consensus_valuation_range_high_millions: Optional[float] = None,
        patent_life_years: int = 12,
        discount_rate: float = 0.12,
        margin_rate: float = 0.35,
        freshness: Optional[datetime] = None,
    ) -> MarketExpectationComparison:
        freshness = freshness or datetime.now(timezone.utc)
        implied_pos = None
        if (
            market_cap_millions is not None
            and model_pos is not None
            and model_peak_sales_millions is not None
            and model_peak_sales_millions > 0
        ):
            expectation = ImpliedPoSEstimator().compute(
                asset_id=asset_id,
                ticker=ticker,
                market_cap_millions=float(market_cap_millions),
                model_pos=model_pos,
                peak_sales_millions=float(model_peak_sales_millions),
                patent_life_years=patent_life_years,
                discount_rate=discount_rate,
                margin_rate=margin_rate,
                cash_estimate_millions=float(cash_estimate_millions or 0.0),
            )
            implied_pos = expectation.implied_pos
        implied_peak_sales = compute_implied_peak_sales(
            market_cap_millions=market_cap_millions,
            cash_estimate_millions=cash_estimate_millions,
            model_pos=model_pos,
            patent_life_years=patent_life_years,
            discount_rate=discount_rate,
            margin_rate=margin_rate,
        )
        current_ev = None
        if market_cap_millions is not None:
            current_ev = round(float(market_cap_millions) - float(cash_estimate_millions or 0.0), 4)
        upside_downside = None
        if (
            financing_adjusted_intrinsic_value_millions is not None
            and current_ev is not None
            and current_ev > 0
        ):
            upside_downside = round(
                (float(financing_adjusted_intrinsic_value_millions) - current_ev) / current_ev,
                4,
            )
        value = MarketExpectationComparisonValue(
            asset_id=asset_id,
            ticker=ticker,
            model_pos=model_pos,
            implied_pos=implied_pos,
            pos_delta=(
                round(float(model_pos) - float(implied_pos), 4)
                if model_pos is not None and implied_pos is not None
                else None
            ),
            model_peak_sales_millions=model_peak_sales_millions,
            implied_peak_sales_millions=implied_peak_sales,
            peak_sales_delta_millions=(
                round(float(model_peak_sales_millions) - float(implied_peak_sales), 4)
                if model_peak_sales_millions is not None and implied_peak_sales is not None
                else None
            ),
            model_dilution_pct=model_dilution_pct,
            implied_dilution_pct=implied_dilution_pct,
            dilution_delta=(
                round(float(model_dilution_pct) - float(implied_dilution_pct), 4)
                if model_dilution_pct is not None and implied_dilution_pct is not None
                else None
            ),
            financing_adjusted_intrinsic_value_millions=financing_adjusted_intrinsic_value_millions,
            current_ev_millions=current_ev,
            upside_downside_pct=upside_downside,
            consensus_valuation_range_low_millions=consensus_valuation_range_low_millions,
            consensus_valuation_range_high_millions=consensus_valuation_range_high_millions,
            optionality_not_reflected_millions=(
                round(
                    max(
                        0.0,
                        float(financing_adjusted_intrinsic_value_millions)
                        - float(consensus_valuation_range_high_millions),
                    ),
                    4,
                )
                if financing_adjusted_intrinsic_value_millions is not None
                and consensus_valuation_range_high_millions is not None
                else None
            ),
            market_cap_millions=market_cap_millions,
        )
        explainability = (
            "This comparison card starts with model vs implied PoS, model vs implied peak sales, "
            "and financing-adjusted value vs current EV so mispricing is visible before deeper valuation detail."
        )
        output = MarketExpectationModuleOutput(
            value=value.model_dump(),
            confidence=self._confidence(value),
            provenance=["market_snapshot", "valuation_model", "financing_engine"],
            freshness=freshness,
            explainability=explainability,
            downstream_dependencies=[
                "variant_view_engine",
                "catalyst_payoff_trees",
                "portfolio_decision_engine",
            ],
        )
        summary = (
            f"{ticker}: model PoS {self._fmt_pct(value.model_pos)} vs implied {self._fmt_pct(value.implied_pos)}, "
            f"model peak sales {self._fmt_money(value.model_peak_sales_millions)} vs implied "
            f"{self._fmt_money(value.implied_peak_sales_millions)}, "
            f"financing-adjusted value {self._fmt_money(value.financing_adjusted_intrinsic_value_millions)} "
            f"vs EV {self._fmt_money(value.current_ev_millions)}."
        )
        return MarketExpectationComparison(
            asset_id=asset_id,
            ticker=ticker,
            output=output,
            plain_english_summary=summary,
        )

    @staticmethod
    def _confidence(value: MarketExpectationComparisonValue) -> float:
        confidence = 0.55
        if value.implied_pos is not None:
            confidence += 0.15
        if value.implied_peak_sales_millions is not None:
            confidence += 0.15
        if value.financing_adjusted_intrinsic_value_millions is not None:
            confidence += 0.10
        if value.implied_dilution_pct is not None:
            confidence += 0.05
        return round(min(0.95, confidence), 4)

    @staticmethod
    def _fmt_pct(value: Optional[float]) -> str:
        return "n/a" if value is None else f"{value:.0%}"

    @staticmethod
    def _fmt_money(value: Optional[float]) -> str:
        return "n/a" if value is None else f"${value:,.0f}M"


# ---------------------------------------------------------------------------
# Step 5: MarketExpectationRow + universe screener
# ---------------------------------------------------------------------------


from datetime import date as _date  # noqa: E402 — local import to avoid circular
from bve.models.financing_risk import FinancingRiskV2 as FinancingRisk  # noqa: E402
from bve.valuation.implied_expectations import (  # noqa: E402
    ImpliedExpectationsInput,
    compute_implied_expectations,
)


class MarketExpectationRow(BaseModel):
    """
    One row in the market-expectation screening table (Step 5).

    Contains both raw model/implied values and the financing-adjusted signal
    for quick universe screening.
    """

    model_config = {"frozen": True}

    asset_id: str
    ticker: str | None
    as_of_date: str
    market_cap_usd: float | None
    net_cash_usd: float | None
    pipeline_value_usd: float | None
    implied_pos: float | None
    model_pos: float | None
    pos_gap: float | None
    implied_peak_sales_millions: float | None
    model_peak_sales_millions: float | None
    peak_sales_gap_millions: float | None
    signal: str
    confidence: str
    financing_haircut: float
    financing_adjusted_signal: str


def build_market_expectation_row(
    asset_id: str,
    ticker: str | None,
    market_cap_usd: float,
    net_cash_usd: float,
    model_pos: float | None = None,
    peak_sales_millions: float | None = None,
    financing_risk: "FinancingRisk | None" = None,
    years_to_approval: float = 3.0,
    as_of_date: str = "",
) -> MarketExpectationRow:
    """
    Build a MarketExpectationRow from market data and optional model parameters.

    The financing_adjusted_signal re-runs the expectation engine with the
    market cap scaled by the financing haircut so that distressed companies
    are not rated 'UNDERPRICED' when they face dilution risk.
    """
    if not as_of_date:
        as_of_date = _date.today().isoformat()

    # Base implied expectations
    base_inp = ImpliedExpectationsInput(
        asset_id=asset_id,
        market_cap_usd=market_cap_usd,
        net_cash_usd=net_cash_usd,
        years_to_approval=years_to_approval,
        peak_sales_millions=peak_sales_millions,
        model_pos=model_pos,
    )
    result = compute_implied_expectations(base_inp)

    # Financing haircut
    financing_haircut = (
        financing_risk.financing_adjusted_value_haircut
        if financing_risk is not None
        else 1.0
    )

    # Financing-adjusted signal
    adjusted_market_cap = market_cap_usd * financing_haircut
    adj_inp = ImpliedExpectationsInput(
        asset_id=asset_id,
        market_cap_usd=adjusted_market_cap,
        net_cash_usd=net_cash_usd,
        years_to_approval=years_to_approval,
        peak_sales_millions=peak_sales_millions,
        model_pos=model_pos,
    )
    adj_result = compute_implied_expectations(adj_inp)

    return MarketExpectationRow(
        asset_id=asset_id,
        ticker=ticker,
        as_of_date=as_of_date,
        market_cap_usd=market_cap_usd,
        net_cash_usd=net_cash_usd,
        pipeline_value_usd=result.pipeline_value_usd,
        implied_pos=result.implied_pos,
        model_pos=result.model_pos,
        pos_gap=result.pos_gap,
        implied_peak_sales_millions=result.implied_peak_sales_millions,
        model_peak_sales_millions=result.model_peak_sales_millions,
        peak_sales_gap_millions=result.peak_sales_gap_millions,
        signal=result.signal,
        confidence=result.confidence,
        financing_haircut=financing_haircut,
        financing_adjusted_signal=adj_result.signal,
    )


def screen_universe(
    rows: list[MarketExpectationRow],
    signal_filter: str | None = None,
    min_confidence: str | None = None,
    max_pos_gap: float | None = None,
) -> list[MarketExpectationRow]:
    """
    Filter and sort a list of MarketExpectationRows.

    Parameters
    ----------
    rows:
        Full universe of rows.
    signal_filter:
        When provided, keep only rows where signal == signal_filter.
    min_confidence:
        "HIGH" → keep only HIGH confidence rows.
        "MEDIUM" → keep HIGH and MEDIUM rows.
    max_pos_gap:
        Keep only rows where pos_gap < max_pos_gap (or pos_gap is None).
    Returns
    -------
    Filtered rows sorted by pos_gap ascending (most underpriced first).
    Rows with pos_gap=None sort to the end.
    """
    _CONFIDENCE_RANK = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}

    filtered: list[MarketExpectationRow] = []
    min_rank = _CONFIDENCE_RANK.get(min_confidence or "", -1)

    for row in rows:
        if signal_filter is not None and row.signal != signal_filter:
            continue
        if min_confidence is not None:
            row_rank = _CONFIDENCE_RANK.get(row.confidence, -1)
            if row_rank < min_rank:
                continue
        if max_pos_gap is not None and row.pos_gap is not None:
            if row.pos_gap >= max_pos_gap:
                continue
        filtered.append(row)

    # Sort by pos_gap ascending; None values go to the end
    filtered.sort(key=lambda r: (r.pos_gap is None, r.pos_gap if r.pos_gap is not None else 0.0))
    return filtered

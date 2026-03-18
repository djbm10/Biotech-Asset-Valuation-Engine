"""
Market expectation math.

Two paths are supported:

1. Stored-snapshot backsolve for ranking and cheap local scans.
   Uses only persisted model_rnpv, model_pos, and market_cap.

2. NAV-style backsolve for richer standalone expectation studies.
   Uses peak-sales assumptions and optional cash estimates.
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

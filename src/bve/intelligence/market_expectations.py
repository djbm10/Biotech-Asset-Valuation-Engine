"""
Market expectation modeling — Wave 1D.

Back-solves the market's implied probability of success (implied PoS) from
the observed market cap using a simplified NAV decomposition:

    market_cap ≈ cash + Σ_i(implied_PoS_i × PV(peak_sales_i))

For a single-asset company with known cash and valuation parameters, this
gives a closed-form solution for implied_PoS.  For multi-asset companies,
the single-asset approximation is used (the dominant asset).

Mispricing signal
-----------------
    pos_gap = implied_pos - model_pos

    pos_gap > 0 → market more optimistic than model (long signal)
    pos_gap < 0 → market more pessimistic than model (short signal)

This is qualitatively distinct from the raw rNPV mispricing used in
ranking (which compares model_rnpv vs market_cap directly).  The implied
PoS gap is scale-independent and comparable across assets of different sizes.

Limitations
-----------
- Cash estimates from yfinance are approximate (last reported balance sheet).
- The NAV formula assumes a single dominant asset — appropriate for most
  clinical-stage biotechs with one lead program.
- Peak sales estimates come from the valuation config; if the config is stale,
  the implied PoS will absorb both market disagreement and model staleness.
- Options-based implied PoS (binary event pricing) is deferred to a future wave.

Usage
-----
    estimator = ImpliedPoSEstimator(knowledge)
    exp = estimator.compute(
        asset_id="rly-2608",
        ticker="RLAY",
        model_pos=0.22,
        peak_sales_millions=800.0,
        patent_life_years=12,
        discount_rate=0.12,
    )
    knowledge.upsert_market_expectation(exp)
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
    model_pos: Optional[float]            # from valuation config / probability model
    pos_gap: Optional[float]              # implied_pos - model_pos
    cash_estimate_millions: Optional[float]
    methodology: str = "nav_backsolve"
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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

        return MarketExpectation(
            asset_id=asset_id,
            ticker=ticker,
            expectation_date=expectation_date,
            implied_pos=implied_pos,
            model_pos=model_pos,
            pos_gap=pos_gap,
            cash_estimate_millions=cash_estimate_millions,
        )

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

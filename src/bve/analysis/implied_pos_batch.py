"""
Batch market-implied PoS screen across the 27-name UNIVERSE.

Standalone — requires no KnowledgeStore or pre-populated database.
Fetches live market data from yfinance; builds screening-grade valuations
from research/universe_params.yaml; back-solves implied PoS for each name.

Primary output: list[ScreenRow] sorted by spread_pp descending (biggest
mispricing first).

Usage
-----
    from bve.analysis.implied_pos_batch import run_screen
    from bve.ops.weekly_runner import UNIVERSE

    rows = run_screen(UNIVERSE)
    for row in rows:
        print(f"{row.ticker:6s}  spread={row.spread_pp:+.1f}pp  model={row.model_pos:.1%}  implied={row.implied_pos:.1%}")

    # Offline / test mode (no yfinance calls):
    rows = run_screen(UNIVERSE, fetch_live=False)
"""
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

_LOG = logging.getLogger("bve.analysis.implied_pos_batch")


@dataclass
class ScreenRow:
    """One row in the universe-level implied PoS screen."""

    ticker: str
    program_label: str
    stage: str
    ta: str

    # Primary mispricing signal
    model_pos: float            # cumulative P(approval) from parametric engine
    implied_pos: Optional[float]    # back-solved from EV; None if price unavailable
    spread_pp: Optional[float]  # model_pos - implied_pos, in percentage points
                                # positive = market too pessimistic (potential upside)
                                # negative = market too optimistic (potential risk)

    # Valuation
    rnpv_millions: float
    ev_millions: Optional[float]
    acquisition_discount_pct: Optional[float]   # (rnpv - ev) / ev × 100

    # Catalyst
    next_catalyst: str
    catalyst_date: Optional[date]
    days_to_catalyst: Optional[int]

    # Quality flags
    single_asset: bool
    approximation_warning: Optional[str]    # set when single_asset=False
    data_date: date = field(default_factory=date.today)

    # Thesis quality (populated from KnowledgeStore when available)
    # None = no resolved claims; 0.0–1.0 = n_confirmed / n_resolved
    thesis_strength: Optional[float] = None

    @property
    def is_undervalued(self) -> Optional[bool]:
        """True if market is more pessimistic than model (spread > 0)."""
        if self.spread_pp is None:
            return None
        return self.spread_pp > 0

    def spread_label(self) -> str:
        if self.spread_pp is None:
            return "n/a"
        return f"{self.spread_pp:+.1f}pp"


def _days_to(target_date: Optional[date], as_of: date) -> Optional[int]:
    if target_date is None:
        return None
    delta = (target_date - as_of).days
    return delta if delta >= 0 else None


def _run_one(
    ticker: str,
    universe_entry: dict,
    params: dict,
    as_of: date,
    fetch_live: bool,
) -> Optional[ScreenRow]:
    """
    Build and value one universe entry. Returns None on unrecoverable error.
    """
    from bve.analysis.implied_probability import compute_implied_market_assumptions
    from bve.models.monte_carlo import MonteCarloParams
    from bve.ops.universe_configs import build_program, fetch_company_snapshot
    from bve.valuation.valuation_engine import ValuationEngine

    # Screening uses 200 MC draws — enough for deterministic rNPV/implied_pos
    # while keeping per-ticker runtime under 1 second.
    _SCREEN_MC = MonteCarloParams(n_simulations=200, random_seed=42)

    try:
        if fetch_live:
            company = fetch_company_snapshot(ticker)
        else:
            company = None  # build_program will produce zero-financial placeholder

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            program, company = build_program(ticker, params, company)

        # Approved assets with no trials produce a trivial valuation
        # (model_pos = 1.0 by convention; gross_pv = PV of commercial stream)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            output = ValuationEngine.from_program(
                program, company, mc_params=_SCREEN_MC
            ).run()

        model_pos = output.rnpv.cumulative_success_probability
        rnpv = output.rnpv.rnpv_millions

        # EV from company snapshot
        ev: Optional[float] = None
        if company.current_price and company.shares_outstanding_millions:
            mktcap = company.current_price * company.shares_outstanding_millions
            ev = round(mktcap - company.net_cash_millions, 1)

        acq_discount: Optional[float] = None
        if ev and ev != 0:
            acq_discount = round((rnpv - ev) / abs(ev) * 100, 1)

        # Implied PoS back-solve
        implied = compute_implied_market_assumptions(output)
        implied_pos: Optional[float] = implied.implied_pos if implied else None
        raw_spread: Optional[float] = None
        if implied_pos is not None:
            # Use the raw (unclamped) implied pos for spread so we can show
            # deep discounts as large negative spreads
            raw_implied = implied.implied_pos if implied else None
            if raw_implied is not None:
                raw_spread = round((model_pos - raw_implied) * 100, 1)

        # Catalyst info
        next_cat = universe_entry.get("catalyst") or params.get("program_label", ticker)
        cat_date_str = params.get("catalyst_date")
        cat_date: Optional[date] = None
        if cat_date_str:
            try:
                cat_date = date.fromisoformat(str(cat_date_str))
            except (ValueError, TypeError):
                pass

        days_cat = _days_to(cat_date, as_of)

        # Approximation warning
        single = bool(params.get("single_asset", True))
        approx_warn = params.get("approximation_note") if not single else None

        return ScreenRow(
            ticker=ticker,
            program_label=params.get("program_label", ticker),
            stage=params.get("phase", "unknown"),
            ta=params.get("ta", "other"),
            model_pos=round(model_pos, 4),
            implied_pos=round(implied_pos, 4) if implied_pos is not None else None,
            spread_pp=raw_spread,
            rnpv_millions=round(rnpv, 1),
            ev_millions=ev,
            acquisition_discount_pct=acq_discount,
            next_catalyst=next_cat,
            catalyst_date=cat_date,
            days_to_catalyst=days_cat,
            single_asset=single,
            approximation_warning=approx_warn,
            data_date=as_of,
        )

    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Screen failed for %s: %s", ticker, exc)
        return None


def run_screen(
    universe: list[dict],
    *,
    params_path: Optional[Path] = None,
    fetch_live: bool = True,
    as_of: Optional[date] = None,
    sort_by: str = "spread",
    single_asset_only: bool = False,
) -> list[ScreenRow]:
    """
    Run the implied PoS screen across all universe entries.

    Parameters
    ----------
    universe     : list of dicts from weekly_runner.UNIVERSE
    params_path  : override path to research/universe_params.yaml
    fetch_live   : if True, fetch live Company data from yfinance (default True)
    as_of        : screen date (default today)
    sort_by      : 'spread' (default) | 'rnpv' | 'ev' | 'd2cat' | 'ticker'
    single_asset_only : if True, exclude multi-program names (approximation_warning set)

    Returns
    -------
    list[ScreenRow] sorted per sort_by parameter
    """
    from bve.ops.universe_configs import load_params

    as_of = as_of or date.today()
    all_params = load_params(params_path)

    # Build ticker → universe_entry map
    entry_map: dict[str, dict] = {e["ticker"]: e for e in universe}

    rows: list[ScreenRow] = []
    for ticker, params in all_params.items():
        universe_entry = entry_map.get(ticker, {})
        row = _run_one(ticker, universe_entry, params, as_of, fetch_live)
        if row is not None:
            rows.append(row)

    if single_asset_only:
        rows = [r for r in rows if r.single_asset]

    # Sort
    def _sort_key(r: ScreenRow):
        if sort_by == "spread":
            # None (missing price) goes to the bottom
            return (r.spread_pp is None, -(r.spread_pp or 0))
        if sort_by == "rnpv":
            return -r.rnpv_millions
        if sort_by == "ev":
            return -(r.ev_millions or 0)
        if sort_by == "d2cat":
            return (r.days_to_catalyst is None, r.days_to_catalyst or 9999)
        return r.ticker  # alphabetical fallback

    rows.sort(key=_sort_key)
    return rows

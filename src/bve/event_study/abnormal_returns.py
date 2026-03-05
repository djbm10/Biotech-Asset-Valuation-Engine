"""
Abnormal return calculation for biotech catalyst events.

Methodology (standard event study — Brown & Warner 1985):
  1. Define estimation window: [–(pre + estimation), –pre – 1] trading days
  2. Fit OLS: ret_stock = alpha + beta × ret_benchmark
  3. Define event window: [–pre, +post] trading days
  4. AR_t = ret_stock_t – (alpha + beta × ret_benchmark_t)
  5. CAR = Σ AR_t over the event window
  6. t-statistic = CAR / (std_dev_estimation × sqrt(window_length))

The benchmark defaults to XBI (SPDR S&P Biotech ETF) — more appropriate
than SPY for capturing biotech sector effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm

from bve.config.constants import EVENT_PRE_WINDOW, EVENT_POST_SHORT_WINDOW, EVENT_POST_DRIFT_WINDOW
from bve.event_study.events import CatalystEvent, EventOutcome
from bve.ingestion.market_data import fetch_returns


@dataclass
class AbnormalReturnResult:
    event_id: str
    ticker: str
    event_date: str
    outcome: str

    # Estimation window stats
    alpha: float
    beta: float
    estimation_window_r2: float

    # Abnormal returns per window
    ar_series: pd.Series         # daily AR in event window
    car_pre: float               # cumulative AR in [–pre, –1]
    car_event: float             # cumulative AR on [0, +1]
    car_post: float              # cumulative AR in [+2, +post]
    car_full: float              # cumulative AR across full event window

    # Statistical significance
    car_event_tstat: float
    car_event_pvalue: float
    is_significant_5pct: bool


def compute_abnormal_returns(
    event: CatalystEvent,
    pre_window: int = EVENT_PRE_WINDOW,
    post_window: int = EVENT_POST_DRIFT_WINDOW,
    estimation_window: int = 120,
    benchmark: str = "XBI",
    min_obs: int = 60,
) -> Optional[AbnormalReturnResult]:
    """
    Compute abnormal returns around a single catalyst event.

    Parameters
    ----------
    event:              CatalystEvent with a known event_date and outcome
    pre_window:         trading days before event date to include
    post_window:        trading days after event date to include
    estimation_window:  trading days before pre_window to estimate market model
    benchmark:          benchmark ticker for market model (default XBI)
    min_obs:            minimum observations required for estimation

    Returns
    -------
    AbnormalReturnResult or None if insufficient data
    """
    ticker = event.company_ticker
    total_lookback_days = int((estimation_window + pre_window + post_window + 10) * 1.5)

    try:
        rets = fetch_returns(ticker, benchmark=benchmark, lookback_days=total_lookback_days)
    except Exception:
        return None

    col_stock = f"ret_{ticker.upper()}" if f"ret_{ticker.upper()}" in rets.columns else f"ret_{ticker}"
    col_bench = f"ret_{benchmark.upper()}"

    if col_stock not in rets.columns or col_bench not in rets.columns:
        return None

    # Align on event date
    rets.index = pd.to_datetime(rets.index)
    try:
        event_dt = pd.to_datetime(event.event_date)
        # Find nearest trading day at or after event date
        future = rets.index[rets.index >= event_dt]
        if len(future) == 0:
            return None
        t0 = future[0]
        t0_loc = rets.index.get_loc(t0)
    except (KeyError, ValueError):
        return None

    # Slice estimation window
    est_start = max(0, t0_loc - pre_window - estimation_window)
    est_end = t0_loc - pre_window
    if est_end - est_start < min_obs:
        return None

    est = rets.iloc[est_start:est_end]
    y = est[col_stock].values
    X = sm.add_constant(est[col_bench].values)
    try:
        model = sm.OLS(y, X).fit()
    except Exception:
        return None

    alpha, beta = model.params[0], model.params[1]
    r2 = model.rsquared
    resid_std = np.std(model.resid)

    # Slice event window
    evt_start = max(0, t0_loc - pre_window)
    evt_end = min(len(rets), t0_loc + post_window + 1)
    evt = rets.iloc[evt_start:evt_end]

    # Compute AR
    expected = alpha + beta * evt[col_bench].values
    ar = evt[col_stock].values - expected
    ar_series = pd.Series(ar, index=evt.index)

    # Index relative to t0
    t0_in_window = t0_loc - evt_start

    car_pre = float(ar[:t0_in_window].sum()) if t0_in_window > 0 else 0.0
    car_event = float(ar[t0_in_window: t0_in_window + 2].sum())  # [0, +1]
    car_post_slice = ar[t0_in_window + 2:]
    car_post = float(car_post_slice.sum()) if len(car_post_slice) > 0 else 0.0
    car_full = float(ar.sum())

    # t-stat for event window CAR
    event_window_len = 2
    se = resid_std * np.sqrt(event_window_len)
    tstat = car_event / se if se > 0 else 0.0
    from scipy.stats import t as t_dist
    pvalue = 2 * t_dist.sf(abs(tstat), df=len(y) - 2)

    return AbnormalReturnResult(
        event_id=event.id,
        ticker=ticker,
        event_date=event.event_date,
        outcome=event.outcome.value,
        alpha=float(alpha),
        beta=float(beta),
        estimation_window_r2=float(r2),
        ar_series=ar_series,
        car_pre=car_pre,
        car_event=car_event,
        car_post=car_post,
        car_full=car_full,
        car_event_tstat=float(tstat),
        car_event_pvalue=float(pvalue),
        is_significant_5pct=pvalue < 0.05,
    )


def aggregate_abnormal_returns(
    events: list[CatalystEvent],
    benchmark: str = "XBI",
    **kwargs,
) -> pd.DataFrame:
    """
    Run abnormal return analysis across a list of events and return summary DataFrame.

    Useful for cross-sectional analysis: average CAR by outcome type, phase, etc.
    """
    records = []
    for event in events:
        result = compute_abnormal_returns(event, benchmark=benchmark, **kwargs)
        if result is None:
            continue
        records.append({
            "event_id": result.event_id,
            "ticker": result.ticker,
            "event_date": result.event_date,
            "outcome": result.outcome,
            "event_type": event.event_type.value,
            "trial_phase": event.trial_phase,
            "indication": event.indication,
            "alpha": result.alpha,
            "beta": result.beta,
            "r2": result.estimation_window_r2,
            "car_pre": result.car_pre,
            "car_event": result.car_event,
            "car_post": result.car_post,
            "car_full": result.car_full,
            "tstat": result.car_event_tstat,
            "pvalue": result.car_event_pvalue,
            "significant": result.is_significant_5pct,
        })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return df

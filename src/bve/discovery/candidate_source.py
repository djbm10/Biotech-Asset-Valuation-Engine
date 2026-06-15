"""Enumerate routing candidates from the rules-based universe screen.

The routing slice (``discovery/routing.py``) needs a list of companies to look at.
Rather than invent a new enumeration, this adapter reuses the existing
``ops/universe_builder`` — the XBI/IBB liquidity screen that already produces
``(ticker, company_name)`` for every name passing a market-cap / ADV filter — and
maps its output into ``CandidateCompany``.

Division of labour: universe_builder does the *liquidity* screen (mktcap/ADV from
yfinance); routing does the *clinical* lead detection (CT.gov). So we deliberately
skip universe_builder's own Phase 2+ gate by default — it would re-hit CT.gov for
information routing fetches anyway — and let routing decide clinical readiness.

Pure over an injectable ``builder``, so enumeration logic tests offline.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from bve.discovery.routing import CandidateCompany
from bve.ops.universe_builder import UniverseCandidate, UniverseFilter, build_universe


def candidates_from_universe(
    universe: list[UniverseCandidate],
    *,
    passed_only: bool = True,
    limit: Optional[int] = None,
) -> list[CandidateCompany]:
    """Map ``UniverseCandidate`` rows → ``CandidateCompany`` (ticker + sponsor name).

    ``passed_only`` keeps just the names that cleared the liquidity screen. The
    company name falls back to the ticker when yfinance returned none, so the
    sponsor-query fallback in ``sponsor_trials`` still has something to work with.
    """
    out: list[CandidateCompany] = []
    seen: set[str] = set()
    for c in universe:
        if passed_only and not c.passed:
            continue
        ticker = c.ticker.upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        out.append(CandidateCompany(ticker=ticker, company_name=c.company_name or c.ticker))
        if limit is not None and len(out) >= limit:
            break
    return out


def enumerate_candidates(
    *,
    as_of: Optional[date] = None,
    filt: Optional[UniverseFilter] = None,
    builder: Callable[..., list[UniverseCandidate]] = build_universe,
    seed_tickers: Optional[list[str]] = None,
    skip_clinical_check: bool = True,
    max_tickers: Optional[int] = None,
    passed_only: bool = True,
    limit: Optional[int] = None,
) -> list[CandidateCompany]:
    """Run the universe screen and return routing candidates.

    ``builder`` is injectable for offline tests. ``skip_clinical_check`` defaults
    to True: routing performs its own CT.gov clinical detection, so the builder's
    Phase 2+ gate is redundant here.
    """
    universe = builder(
        as_of or date.today(),
        filt or UniverseFilter(),
        seed_tickers=seed_tickers,
        skip_clinical_check=skip_clinical_check,
        max_tickers=max_tickers,
    )
    return candidates_from_universe(universe, passed_only=passed_only, limit=limit)

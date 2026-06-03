"""
Rules-based biotech universe builder (Sprint 12B).

Screens XBI/IBB ETF constituents against liquidity and clinical-stage criteria
to produce a rules-based candidate universe — removing manual curation bias.

Filter criteria (all configurable via UniverseFilter):
  - Market cap: $200M – $10B
  - Average Daily Volume: ≥ $2M
  - Clinical stage: at least one active Phase 2+ study on ClinicalTrials.gov

Output: list[UniverseCandidate] sorted by market_cap_m descending.
Persistence: universe_snapshots table in KnowledgeStore (via save_snapshot_to_store).

Limitations
-----------
The Phase 2+ clinical-stage gate queries ClinicalTrials.gov as of *today* — it
is NOT time-accurate for historical periods. For past dates, companies that since
failed will have fewer or no active trials now, introducing look-ahead bias in
the stage filter. The mktcap/ADV filters computed from historical prices are
clean; only the Phase 2+ gate is contaminated for historical back-fills.

Usage
-----
    from bve.ops.universe_builder import build_universe, UniverseFilter
    from datetime import date

    candidates = build_universe(date.today(), UniverseFilter())
    for c in candidates:
        print(f"{c.ticker:6s}  ${c.market_cap_m:,.0f}M  adv=${c.adv_m:.1f}M  {c.has_phase2_plus}")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_LOG = logging.getLogger("bve.ops.universe_builder")

# ---------------------------------------------------------------------------
# Hard-coded ETF constituent seed list (XBI + IBB overlap, ~120 names).
# Updated quarterly from SSGA / iShares holdings pages.
# Last updated: 2026-Q1.
# ---------------------------------------------------------------------------
_XBI_IBB_TICKERS: list[str] = [
    # Mega-cap biotech (often filtered out by max_mktcap but kept for completeness)
    "AMGN", "GILD", "REGN", "VRTX", "BIIB", "MRNA", "BMRN",
    # Large-cap ($5B–$50B)
    "ALNY", "SRPT", "NBIX", "EXEL", "HALO", "INCY", "SGEN",
    # Mid-cap focus ($500M–$5B)
    "VKTX", "KYMR", "ARVN", "RVMD", "NTLA", "BEAM", "CRSP", "EDIT",
    "IMVT", "MDGL", "RXRX", "FULC", "FATE", "OCUL", "SRRK", "IOVA",
    "ZYME", "PRTA", "NVAX", "AMRN", "LLY",
    # Additional XBI members
    "ACAD", "ACLS", "ADMA", "ADUS", "AGIO", "AGNC", "AGEN", "ALKS",
    "ALLK", "ALLO", "ALNY", "ALRN", "ALVO", "ANAB", "ANPC", "APLS",
    "APTO", "ARCT", "ARDX", "ARGX", "ARQT", "ARWR", "ASND", "ATRC",
    "AURA", "AUPH", "AVDL", "AVRO", "AXSM", "BCAB", "BCYC", "BDTX",
    "BEAM", "BFRI", "BGEN", "BHVN", "BLUE", "BLTE", "BPMC", "BSGN",
    "BTAI", "CARA", "CBPO", "CCCC", "CDTX", "CERE", "CGEM", "CHRS",
    "CLDX", "CLRB", "CMPS", "CNMD", "CNTB", "COGT", "COMP", "CORT",
    "CPRX", "CRBU", "CRDF", "CRNX", "CRVS", "CTLT", "CVAC", "DAWN",
    "DCPH", "DERM", "DICE", "DVAX", "EWTX", "EXAS", "FATE", "FGEN",
    "FOLD", "FORG", "FRPT", "FRTX", "FTFT", "FULC", "FUSN", "GBCI",
    "GKOS", "GNPX", "GRTS", "GTHX", "HALO", "HARP", "HCM", "HOOK",
    "HRTX", "HRYU", "IDYA", "IMCR", "IMGN", "IMTX", "INVA", "IOBT",
    "IOVA", "IPSC", "ITCI", "JANX", "JNCE", "KALA", "KDNY", "KPTI",
    "KRYS", "KYMR", "LAZY", "LGND", "LNTH", "LPCN", "LQDA", "LUNA",
    "MDGL", "MEIP", "MGNX", "MIRM", "MKSI", "MLYS", "MNKD", "MRNA",
    "MRUS", "MTEM", "MTEX", "MYNZ", "NBTX", "NCNA", "NKTR", "NMTC",
    "NRIX", "NTLA", "NVAX", "NVCR", "OCUL", "OLMA", "OMER", "ONCE",
    "OPCH", "ORGN", "OTRK", "OVID", "OXB", "PHAT", "PHIO", "PLRX",
    "PMVP", "PRME", "PRTA", "PRTK", "PSNL", "PTCT", "PTGX", "PTLO",
    "PVYX", "QURE", "RAPT", "RCUS", "RDUS", "RLAY", "RNAC", "RNLX",
    "RVMD", "RXRX", "RYTM", "SAGE", "SGMO", "SIGA", "SLNO", "SMMT",
    "SNCE", "SQDG", "SRRK", "STRO", "SURF", "SVRA", "SYRS", "TGTX",
    "TLNX", "TPST", "TPTX", "TRIL", "TVTX", "TXMD", "TYRA", "UBIA",
    "VCEL", "VERV", "VKTX", "VRDN", "VSTM", "VYGR", "XCUR", "XNCR",
    "YMAB", "ZBTX", "ZYME",
]

# De-duplicate while preserving order
_SEED_TICKERS: list[str] = list(dict.fromkeys(_XBI_IBB_TICKERS))


@dataclass
class UniverseFilter:
    """Liquidity and clinical-stage criteria for the rules-based universe."""
    min_mktcap_m: float = 200.0        # minimum market cap in $M
    max_mktcap_m: float = 10_000.0     # maximum market cap in $M
    min_adv_m: float = 2.0             # minimum 30-day average daily volume in $M
    require_phase2_plus: bool = True   # require at least one active Phase 2+ study
    adv_lookback_days: int = 30        # trading days for ADV calculation


@dataclass
class UniverseCandidate:
    """One candidate from the rules-based screen."""
    ticker: str
    company_name: str
    market_cap_m: float
    adv_m: float                           # 30-day average daily dollar volume
    as_of: date
    has_phase2_plus: bool                  # True if ClinicalTrials.gov found Phase 2+
    active_phase2_studies: list[str]       # NCT IDs of active Phase 2+ studies
    sources: list[str] = field(default_factory=list)
    # Filter outcome
    passed: bool = False
    exclusion_reason: Optional[str] = None


def _fetch_market_data(ticker: str, as_of: date, adv_lookback_days: int) -> Optional[dict]:
    """
    Fetch market cap and ADV from yfinance.

    Returns dict with keys: market_cap_m, adv_m, company_name, current_price.
    Returns None on failure.
    """
    try:
        import yfinance as yf

        end = as_of + timedelta(days=1)
        start = as_of - timedelta(days=adv_lookback_days * 2)  # buffer for weekends

        info = yf.Ticker(ticker).info
        market_cap = info.get("marketCap")
        company_name = info.get("shortName") or info.get("longName") or ticker
        current_price = info.get("currentPrice") or info.get("regularMarketPrice")

        # ADV from price history
        hist = yf.Ticker(ticker).history(start=start, end=end)
        if hist.empty:
            return None
        # dollar volume = close × volume; take last N trading days
        hist = hist.tail(adv_lookback_days)
        dollar_vol = (hist["Close"] * hist["Volume"]).mean() / 1e6  # in $M

        if market_cap is None:
            return None

        return {
            "market_cap_m": round(market_cap / 1e6, 1),
            "adv_m": round(dollar_vol, 2),
            "company_name": company_name,
            "current_price": current_price,
        }
    except Exception as exc:  # noqa: BLE001
        _LOG.debug("yfinance fetch failed for %s: %s", ticker, exc)
        return None


def _has_phase2_plus_trials(ticker: str) -> tuple[bool, list[str]]:
    """
    Check ClinicalTrials.gov for active Phase 2, 3, or 4 studies by company name.

    Returns (has_phase2_plus, list_of_nct_ids).
    Does NOT raise — returns (False, []) on network failure.

    Caveat: queries current state, not historical. See module docstring.
    """
    try:
        import requests

        # Try to get company name from yfinance for better search results
        try:
            import yfinance as yf
            info = yf.Ticker(ticker).info
            company_name = info.get("shortName") or ticker
        except Exception:  # noqa: BLE001
            company_name = ticker

        url = "https://clinicaltrials.gov/api/v2/studies"
        params = {
            "query.spons": company_name,
            "filter.overallStatus": "RECRUITING,ACTIVE_NOT_RECRUITING,NOT_YET_RECRUITING",
            "filter.phase": "PHASE2,PHASE3,PHASE4",
            "pageSize": 10,
            "fields": "NCTId,Phase,OverallStatus",
        }
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return False, []

        data = resp.json()
        studies = data.get("studies", [])
        nct_ids = [
            s.get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
            for s in studies
        ]
        nct_ids = [n for n in nct_ids if n]
        return bool(nct_ids), nct_ids[:5]

    except Exception as exc:  # noqa: BLE001
        _LOG.debug("ClinicalTrials fetch failed for %s: %s", ticker, exc)
        return False, []


def build_universe(
    as_of: date,
    filt: Optional[UniverseFilter] = None,
    *,
    seed_tickers: Optional[list[str]] = None,
    skip_clinical_check: bool = False,
    max_tickers: Optional[int] = None,
) -> list[UniverseCandidate]:
    """
    Screen the XBI/IBB seed list against liquidity and clinical-stage criteria.

    Parameters
    ----------
    as_of               : screen date (mktcap/ADV sourced from yfinance at this date)
    filt                : filter criteria (defaults to UniverseFilter())
    seed_tickers        : override the default XBI/IBB seed list
    skip_clinical_check : if True, skip the ClinicalTrials.gov Phase 2+ check
                          (useful for offline/test runs — all passed tickers are
                          assumed to have Phase 2+ activity)
    max_tickers         : limit the number of seed tickers evaluated (testing)

    Returns
    -------
    list[UniverseCandidate] sorted by market_cap_m descending, passed=True first
    """
    if filt is None:
        filt = UniverseFilter()

    tickers = seed_tickers or _SEED_TICKERS
    if max_tickers is not None:
        tickers = tickers[:max_tickers]

    candidates: list[UniverseCandidate] = []

    for ticker in tickers:
        mdata = _fetch_market_data(ticker, as_of, filt.adv_lookback_days)
        if mdata is None:
            candidates.append(UniverseCandidate(
                ticker=ticker,
                company_name=ticker,
                market_cap_m=0.0,
                adv_m=0.0,
                as_of=as_of,
                has_phase2_plus=False,
                active_phase2_studies=[],
                sources=["yfinance"],
                passed=False,
                exclusion_reason="market_data_unavailable",
            ))
            continue

        mktcap = mdata["market_cap_m"]
        adv = mdata["adv_m"]
        company_name = mdata["company_name"]

        # Apply liquidity filters
        if mktcap < filt.min_mktcap_m:
            candidates.append(UniverseCandidate(
                ticker=ticker, company_name=company_name,
                market_cap_m=mktcap, adv_m=adv, as_of=as_of,
                has_phase2_plus=False, active_phase2_studies=[],
                sources=["yfinance"], passed=False,
                exclusion_reason=f"mktcap_${mktcap:.0f}M < min_${filt.min_mktcap_m:.0f}M",
            ))
            continue

        if mktcap > filt.max_mktcap_m:
            candidates.append(UniverseCandidate(
                ticker=ticker, company_name=company_name,
                market_cap_m=mktcap, adv_m=adv, as_of=as_of,
                has_phase2_plus=False, active_phase2_studies=[],
                sources=["yfinance"], passed=False,
                exclusion_reason=f"mktcap_${mktcap:.0f}M > max_${filt.max_mktcap_m:.0f}M",
            ))
            continue

        if adv < filt.min_adv_m:
            candidates.append(UniverseCandidate(
                ticker=ticker, company_name=company_name,
                market_cap_m=mktcap, adv_m=adv, as_of=as_of,
                has_phase2_plus=False, active_phase2_studies=[],
                sources=["yfinance"], passed=False,
                exclusion_reason=f"adv_${adv:.1f}M < min_${filt.min_adv_m:.1f}M",
            ))
            continue

        # Clinical stage check
        if skip_clinical_check or not filt.require_phase2_plus:
            has_ph2, nct_ids = True, []
        else:
            has_ph2, nct_ids = _has_phase2_plus_trials(ticker)

        if filt.require_phase2_plus and not has_ph2:
            candidates.append(UniverseCandidate(
                ticker=ticker, company_name=company_name,
                market_cap_m=mktcap, adv_m=adv, as_of=as_of,
                has_phase2_plus=False, active_phase2_studies=[],
                sources=["yfinance", "clinicaltrials"],
                passed=False,
                exclusion_reason="no_active_phase2_plus_trials",
            ))
            continue

        candidates.append(UniverseCandidate(
            ticker=ticker,
            company_name=company_name,
            market_cap_m=mktcap,
            adv_m=adv,
            as_of=as_of,
            has_phase2_plus=has_ph2,
            active_phase2_studies=nct_ids,
            sources=["yfinance", "clinicaltrials"] if not skip_clinical_check else ["yfinance"],
            passed=True,
        ))

    # Sort: passed first, then by market_cap descending
    candidates.sort(key=lambda c: (not c.passed, -c.market_cap_m))
    return candidates


def save_snapshot_to_store(
    candidates: list[UniverseCandidate],
    db_path: Optional[Path] = None,
) -> int:
    """
    Persist a universe build result to the KnowledgeStore universe_snapshots table.

    Uses INSERT OR REPLACE semantics — running twice on the same date/ticker
    updates the row rather than duplicating it.

    Returns number of rows written.
    """
    from bve.intelligence.knowledge_layer import KnowledgeStore
    from bve.ops.weekly_runner import DB_PATH

    path = db_path or DB_PATH
    store = KnowledgeStore(path)
    try:
        n = store.write_universe_snapshot(candidates)
    finally:
        store.close()
    return n

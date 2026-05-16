"""Failure mode postmortems — systematic diagnosis of losing trades.

For each trade classified as a loss (attribution = thesis_error, timing_error,
or pos_error), we attach structured remediation data and aggregate them into a
FailureModeReport.

Design
------
- ``FailureTrade`` — enriched record for one losing trade with diagnosis fields
- ``FailureCategory`` enum — mutually exclusive primary failure cause
- ``FailureModeReport`` — aggregate stats + per-category breakdown + remediation
- ``diagnose_failures(trades)`` — classifies trades and returns report

Primary failure categories
--------------------------
  THESIS_ERROR_POOR_EVIDENCE — entered on weak/unverified claims
  THESIS_ERROR_STALE_DATA    — data was stale at decision time
  TIMING_ERROR_TOO_EARLY     — right direction, wrong entry timing
  TIMING_ERROR_TOO_LATE      — catalyst already priced in at entry
  POS_ERROR_MKT_REGIME       — market regime swamped the signal (XBI beta)
  POS_ERROR_IDIO_RISK        — idiosyncratic company risk (safety, management)
  INSUFFICIENT_CASH_RUNWAY   — company ran out of cash before catalyst
  COMPETITION_UNDERESTIMATED — competitor launched / priced-in before us
  DATA_QUALITY               — return data or signal data was unreliable
  UNKNOWN                    — no remediation identified

Usage
-----
    from bve.analysis.failure_diagnostics import diagnose_failures
    from bve.validation.stat_tests import trades_from_decisions

    trades = trades_from_decisions(decisions)
    report = diagnose_failures(trades)
    print(report.summary())
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class FailureCategory(str, Enum):
    THESIS_ERROR_POOR_EVIDENCE  = "thesis_error_poor_evidence"
    THESIS_ERROR_STALE_DATA     = "thesis_error_stale_data"
    TIMING_ERROR_TOO_EARLY      = "timing_error_too_early"
    TIMING_ERROR_TOO_LATE       = "timing_error_too_late"
    POS_ERROR_MKT_REGIME        = "pos_error_mkt_regime"
    POS_ERROR_IDIO_RISK         = "pos_error_idio_risk"
    INSUFFICIENT_CASH_RUNWAY    = "insufficient_cash_runway"
    COMPETITION_UNDERESTIMATED  = "competition_underestimated"
    DATA_QUALITY                = "data_quality"
    UNKNOWN                     = "unknown"


class EvidenceQuality(str, Enum):
    STRONG   = "strong"    # ≥2 confirmed claims, recent data
    MODERATE = "moderate"  # 1 confirmed claim or mixed signals
    WEAK     = "weak"      # 0 confirmed claims, unverified thesis
    UNKNOWN  = "unknown"


class MarketRegime(str, Enum):
    RISK_ON    = "risk_on"    # XBI > 20d MA; bullish biotech
    RISK_OFF   = "risk_off"   # XBI < 20d MA; bearish biotech
    NEUTRAL    = "neutral"    # near 20d MA ±2%
    UNKNOWN    = "unknown"


# ---------------------------------------------------------------------------
# Input record — enriched trade with optional diagnostic fields
# ---------------------------------------------------------------------------

@dataclass
class FailureTrade:
    """A losing trade with diagnosis fields attached.

    Core fields come from TradeRecord (or replay decisions).
    Diagnostic fields are optional — populated when available.
    """
    # Core
    decision_id: str
    asset_id: str
    company_id: str
    model_score: float
    return_pct: float
    attribution: str          # thesis_error | timing_error | pos_error | etc.

    # Timing context
    entry_date: Optional[str] = None           # ISO date
    catalyst_date: Optional[str] = None        # ISO date of targeted catalyst
    days_to_catalyst_at_entry: Optional[int] = None   # +ve = pre-catalyst

    # Evidence quality at entry
    evidence_quality_at_entry: EvidenceQuality = EvidenceQuality.UNKNOWN
    n_confirmed_claims_at_entry: int = 0       # thesis claims confirmed before entry
    n_refuted_claims_at_entry: int = 0         # thesis claims refuted before entry
    data_staleness_days: Optional[int] = None  # days since most recent update

    # Company fundamentals at entry
    cash_runway_at_entry_quarters: Optional[float] = None
    market_cap_at_entry_millions: Optional[float] = None

    # Market regime at entry
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    xbi_return_over_hold: Optional[float] = None   # XBI return during same hold

    # Competition signal
    n_competitors_at_entry: Optional[int] = None
    new_competitor_launched_during_hold: bool = False

    # Diagnosis (set by diagnose_failure_trade)
    primary_failure_cause: FailureCategory = FailureCategory.UNKNOWN
    model_score_component_responsible: Optional[str] = None  # "thesis" | "opportunity" | "ranking"
    remediation_note: str = ""


# ---------------------------------------------------------------------------
# Aggregate report
# ---------------------------------------------------------------------------

@dataclass
class CategoryBreakdown:
    """Stats for one failure category."""
    category: FailureCategory
    n: int
    mean_return_pct: Optional[float]
    median_return_pct: Optional[float]
    pct_of_failures: float       # fraction of total failures

    def to_dict(self) -> dict:
        return {
            "category": self.category.value,
            "n": self.n,
            "mean_return_pct": _r(self.mean_return_pct),
            "median_return_pct": _r(self.median_return_pct),
            "pct_of_failures": _r(self.pct_of_failures),
        }


@dataclass
class FailureModeReport:
    """Aggregate failure mode statistics across all losing trades."""
    model_name: str
    n_total_trades: int
    n_losers: int
    n_winners: int
    loss_rate: float                          # fraction of trades that lost
    mean_loser_return_pct: Optional[float]
    mean_winner_return_pct: Optional[float]
    skill_adjusted_n: int                     # losers excluding pos_error
    by_category: list[CategoryBreakdown] = field(default_factory=list)
    top_failure_cause: Optional[FailureCategory] = None
    remediation_summary: list[str] = field(default_factory=list)
    failing_trades: list[FailureTrade] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 70,
            f"  FAILURE MODE REPORT — {self.model_name}",
            "=" * 70,
            f"  Total trades:   {self.n_total_trades}",
            f"  Losers:         {self.n_losers} ({self.loss_rate*100:.1f}%)",
            f"  Winners:        {self.n_winners}",
        ]
        if self.mean_loser_return_pct is not None:
            lines.append(f"  Mean loser P&L: {self.mean_loser_return_pct:+.2f}%")
        if self.mean_winner_return_pct is not None:
            lines.append(f"  Mean winner P&L: {self.mean_winner_return_pct:+.2f}%")
        lines.append("")
        lines.append("  Failure breakdown by category:")
        for cat in self.by_category:
            lines.append(
                f"    {cat.category.value:<40} N={cat.n:>3}  "
                f"({cat.pct_of_failures*100:.0f}%)  "
                f"mean={_fmt(cat.mean_return_pct)}"
            )
        if self.top_failure_cause:
            lines.append(f"\n  Top failure cause: {self.top_failure_cause.value}")
        if self.remediation_summary:
            lines.append("\n  Remediation actions:")
            for r in self.remediation_summary:
                lines.append(f"    • {r}")
        lines.append("=" * 70)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "n_total_trades": self.n_total_trades,
            "n_losers": self.n_losers,
            "n_winners": self.n_winners,
            "loss_rate": _r(self.loss_rate),
            "mean_loser_return_pct": _r(self.mean_loser_return_pct),
            "mean_winner_return_pct": _r(self.mean_winner_return_pct),
            "skill_adjusted_n": self.skill_adjusted_n,
            "top_failure_cause": self.top_failure_cause.value if self.top_failure_cause else None,
            "by_category": [c.to_dict() for c in self.by_category],
            "remediation_summary": self.remediation_summary,
        }


# ---------------------------------------------------------------------------
# Diagnostic logic
# ---------------------------------------------------------------------------

def diagnose_failure_trade(trade: FailureTrade) -> FailureTrade:
    """Assign primary_failure_cause and remediation_note to a losing trade.

    Uses a decision tree based on attribution + available diagnostic fields.
    Returns a new FailureTrade (immutable pattern — dataclass copy).
    """
    attr = trade.attribution.lower()
    cause = FailureCategory.UNKNOWN
    component = None
    note = ""

    # --- thesis_error: model was wrong on direction ---
    if "thesis_error" in attr:
        if (trade.cash_runway_at_entry_quarters is not None
                and trade.cash_runway_at_entry_quarters < 2.0):
            cause = FailureCategory.INSUFFICIENT_CASH_RUNWAY
            component = "thesis"
            note = (
                f"Cash runway was {trade.cash_runway_at_entry_quarters:.1f}Q "
                "at entry — below 2Q minimum. Add runway gate to entry policy."
            )
        elif trade.evidence_quality_at_entry == EvidenceQuality.WEAK:
            cause = FailureCategory.THESIS_ERROR_POOR_EVIDENCE
            component = "thesis"
            note = (
                f"Evidence quality was WEAK at entry "
                f"(confirmed={trade.n_confirmed_claims_at_entry}, "
                f"refuted={trade.n_refuted_claims_at_entry}). "
                "Require ≥1 confirmed claim before entry."
            )
        elif (trade.data_staleness_days is not None
              and trade.data_staleness_days > 14):
            cause = FailureCategory.THESIS_ERROR_STALE_DATA
            component = "thesis"
            note = (
                f"Data was {trade.data_staleness_days}d stale at entry. "
                "Refresh claims within 7d of catalyst."
            )
        elif trade.new_competitor_launched_during_hold:
            cause = FailureCategory.COMPETITION_UNDERESTIMATED
            component = "opportunity"
            note = "New competitor launched during hold. Pre-screen competitive pipeline."
        else:
            cause = FailureCategory.THESIS_ERROR_POOR_EVIDENCE
            component = "thesis"
            note = "Thesis was not confirmed; evidence quality unknown or moderate."

    # --- timing_error: model was right on direction but lost money ---
    elif "timing_error" in attr:
        if (trade.days_to_catalyst_at_entry is not None
                and trade.days_to_catalyst_at_entry < 3):
            cause = FailureCategory.TIMING_ERROR_TOO_LATE
            component = "ranking"
            note = (
                f"Entered {trade.days_to_catalyst_at_entry}d before catalyst — "
                "likely already priced in. Enforce ≥5d pre-catalyst entry."
            )
        elif (trade.days_to_catalyst_at_entry is not None
              and trade.days_to_catalyst_at_entry > 30):
            cause = FailureCategory.TIMING_ERROR_TOO_EARLY
            component = "ranking"
            note = (
                f"Entered {trade.days_to_catalyst_at_entry}d before catalyst — "
                "too early; capital tied up. Use ≤30d entry gate."
            )
        elif trade.market_regime == MarketRegime.RISK_OFF:
            cause = FailureCategory.POS_ERROR_MKT_REGIME
            component = "opportunity"
            note = "Market regime was RISK_OFF at entry. Apply XBI trend filter."
        else:
            cause = FailureCategory.TIMING_ERROR_TOO_EARLY
            component = "ranking"
            note = "Event occurred but return was negative — timing imprecision."

    # --- pos_error: lucky win when model was wrong — included for completeness ---
    elif "pos_error" in attr:
        if trade.market_regime == MarketRegime.RISK_OFF:
            cause = FailureCategory.POS_ERROR_MKT_REGIME
        else:
            cause = FailureCategory.POS_ERROR_IDIO_RISK
        component = "ranking"
        note = "Model called direction wrong but profited — exclude from skill-adjusted stats."

    # --- market_drift or unclassified ---
    elif trade.market_regime == MarketRegime.RISK_OFF:
        cause = FailureCategory.POS_ERROR_MKT_REGIME
        component = "opportunity"
        note = "Return negative; market regime was RISK_OFF. XBI beta dominant."

    return FailureTrade(
        **{k: v for k, v in trade.__dict__.items()
           if k not in ("primary_failure_cause", "model_score_component_responsible", "remediation_note")},
        primary_failure_cause=cause,
        model_score_component_responsible=component,
        remediation_note=note,
    )


def diagnose_failures(
    trades,   # list[TradeRecord] or list[FailureTrade]
    *,
    model_name: str = "model",
    loss_threshold_pct: float = 0.0,
) -> FailureModeReport:
    """Build FailureModeReport from a list of trades.

    Accepts TradeRecord objects (from stat_tests.py) or FailureTrade objects.
    TradeRecord objects are automatically converted to FailureTrade.

    Parameters
    ----------
    trades:
        Closed trade records.
    model_name:
        Label for this model in the report.
    loss_threshold_pct:
        Return below this value is considered a loss (default 0 = any negative return).
    """
    failure_trades = [_to_failure_trade(t) for t in trades]

    losers = [t for t in failure_trades if t.return_pct < loss_threshold_pct]
    winners = [t for t in failure_trades if t.return_pct >= loss_threshold_pct]

    diagnosed = [diagnose_failure_trade(t) for t in losers]

    n_total = len(failure_trades)
    loss_rate = len(losers) / n_total if n_total > 0 else 0.0

    mean_loser = statistics.mean(t.return_pct for t in losers) if losers else None
    mean_winner = statistics.mean(t.return_pct for t in winners) if winners else None

    # Aggregate by category
    cat_map: dict[FailureCategory, list[float]] = {}
    for t in diagnosed:
        cat_map.setdefault(t.primary_failure_cause, []).append(t.return_pct)

    by_category = []
    for cat, returns in sorted(cat_map.items(), key=lambda x: -len(x[1])):
        by_category.append(CategoryBreakdown(
            category=cat,
            n=len(returns),
            mean_return_pct=round(statistics.mean(returns), 4) if returns else None,
            median_return_pct=round(statistics.median(returns), 4) if returns else None,
            pct_of_failures=len(returns) / max(len(losers), 1),
        ))

    top_cause = by_category[0].category if by_category else None

    # Skill-adjusted N: losers excluding pos_error (lucky wins)
    skill_losers = [t for t in diagnosed
                    if "pos_error" not in t.attribution.lower()]
    skill_adjusted_n = len(skill_losers)

    remediation = _build_remediation(by_category, skill_losers)

    return FailureModeReport(
        model_name=model_name,
        n_total_trades=n_total,
        n_losers=len(losers),
        n_winners=len(winners),
        loss_rate=round(loss_rate, 4),
        mean_loser_return_pct=round(mean_loser, 4) if mean_loser is not None else None,
        mean_winner_return_pct=round(mean_winner, 4) if mean_winner is not None else None,
        skill_adjusted_n=skill_adjusted_n,
        by_category=by_category,
        top_failure_cause=top_cause,
        remediation_summary=remediation,
        failing_trades=diagnosed,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_failure_trade(t) -> FailureTrade:
    """Convert TradeRecord (from stat_tests) to FailureTrade. Pass-through if already FailureTrade."""
    if isinstance(t, FailureTrade):
        return t
    # TradeRecord duck-type conversion
    return FailureTrade(
        decision_id=getattr(t, "decision_id", ""),
        asset_id=getattr(t, "asset_id", ""),
        company_id=getattr(t, "company_id", ""),
        model_score=getattr(t, "model_score", 0.5),
        return_pct=getattr(t, "return_pct", 0.0),
        attribution=getattr(t, "attribution", "unclassified"),
        entry_date=getattr(t, "entry_date", None),
        market_cap_at_entry_millions=getattr(t, "market_cap_millions", None),
        cash_runway_at_entry_quarters=getattr(t, "cash_runway_quarters", None),
    )


def _build_remediation(
    by_category: list[CategoryBreakdown],
    skill_losers: list[FailureTrade],
) -> list[str]:
    """Derive actionable remediation steps from failure breakdown."""
    remediations = []
    cat_names = {c.category for c in by_category}

    if FailureCategory.THESIS_ERROR_POOR_EVIDENCE in cat_names:
        remediations.append(
            "Require ≥1 confirmed thesis claim before entry — weak-evidence trades "
            "account for a material share of losses."
        )
    if FailureCategory.INSUFFICIENT_CASH_RUNWAY in cat_names:
        remediations.append(
            "Add hard cash runway gate: block entry when runway < 2Q."
        )
    if FailureCategory.TIMING_ERROR_TOO_LATE in cat_names:
        remediations.append(
            "Enforce minimum 5-day pre-catalyst entry; avoid entering < 3d before event."
        )
    if FailureCategory.TIMING_ERROR_TOO_EARLY in cat_names:
        remediations.append(
            "Tighten catalyst window to ≤30d; reduce capital tie-up on early positions."
        )
    if FailureCategory.POS_ERROR_MKT_REGIME in cat_names:
        remediations.append(
            "Enable XBI trend filter (--xbi-filter): block entries when XBI < 20d MA."
        )
    if FailureCategory.COMPETITION_UNDERESTIMATED in cat_names:
        remediations.append(
            "Pre-screen competitive pipeline on entry; block if major competitor ≤90d from launch."
        )
    if FailureCategory.THESIS_ERROR_STALE_DATA in cat_names:
        remediations.append(
            "Enforce 7-day data freshness check before entry; skip if last update > 14d."
        )

    # Catch-all if nothing specific
    low_runway = [t for t in skill_losers
                  if t.cash_runway_at_entry_quarters is not None
                  and t.cash_runway_at_entry_quarters < 4.0]
    if low_runway and FailureCategory.INSUFFICIENT_CASH_RUNWAY not in cat_names:
        remediations.append(
            f"{len(low_runway)} losing trades had runway < 4Q at entry — "
            "consider raising the runway threshold."
        )

    return remediations


def _r(v: Optional[float], d: int = 4) -> Optional[float]:
    return round(v, d) if v is not None else None


def _fmt(v: Optional[float]) -> str:
    return f"{v:+.2f}%" if v is not None else "n/a"

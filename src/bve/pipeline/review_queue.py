"""Analyst review queue over canonical profiles.

Surfaces the auto-generated names that need human eyes, with a specific reason
and severity per item, so the analyst reviews *targeted* fields instead of whole
configs. Operates on the canonical profile store (the coarse, pipeline-built
names); curated / point-in-time configs are out of scope (already vetted).

Reason codes (the six review triggers):
- commercial_assumptions_heuristic — economics came from per-TA heuristic priors
- missing_nct                      — no NCT linked, so trial facts are defaulted
- stale_data                       — profile older than the freshness threshold
- ambiguous_lead_asset             — lead identity (drug/indication/stage) uncertain
- conflicting_sources              — independent sources disagree (e.g. mcap vs px*sh)
- large_score_move                 — score moved materially vs the prior snapshot
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from bve.pipeline.asset_profile import CompanyProfile

# Reason codes
COMMERCIAL_HEURISTIC = "commercial_assumptions_heuristic"
MISSING_NCT = "missing_nct"
STALE_DATA = "stale_data"
AMBIGUOUS_LEAD_ASSET = "ambiguous_lead_asset"
CONFLICTING_SOURCES = "conflicting_sources"
LARGE_SCORE_MOVE = "large_score_move"

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

_ECON_FIELDS = (
    "total_addressable_market_millions",
    "net_price_per_patient_usd",
    "addressable_patients_annual",
    "peak_penetration",
    "patent_life_years",
)


@dataclass(frozen=True)
class ReviewItem:
    """One actionable review flag for a name."""

    ticker: str
    asset_id: str
    reason: str
    severity: str  # high | medium | low
    field: Optional[str]
    detail: str


def _age_days(iso: Optional[str], now: datetime) -> Optional[float]:
    if not iso:
        return None
    try:
        text = iso.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds() / 86400.0
    except ValueError:
        return None


def review_company(
    profile: CompanyProfile,
    *,
    now: Optional[datetime] = None,
    stale_days: int = 90,
    prior_score: Optional[float] = None,
    current_score: Optional[float] = None,
    move_threshold: float = 0.25,
    conflict_threshold: float = 0.15,
) -> list[ReviewItem]:
    """Compute review items for a single profile's lead asset."""
    now = now or datetime.now(timezone.utc)
    asset = profile.lead_asset
    tkr, aid = profile.ticker.upper(), asset.asset_id
    items: list[ReviewItem] = []

    def add(reason: str, severity: str, field: Optional[str], detail: str) -> None:
        items.append(ReviewItem(tkr, aid, reason, severity, field, detail))

    # 1. Ambiguous lead asset — identity uncertain
    ambiguous = [
        name
        for name in ("drug_name", "indication", "stage")
        if getattr(asset, name).value in (None, "", "unknown")
        or getattr(asset, name).confidence == "low"
    ]
    if ambiguous:
        add(AMBIGUOUS_LEAD_ASSET, "high", ",".join(ambiguous),
            f"lead-asset identity uncertain: {', '.join(ambiguous)}")

    # 2. Conflicting sources — market cap vs price x shares
    mc = profile.market_cap_millions.value
    px = profile.current_price.value
    sh = profile.shares_outstanding_millions.value
    if mc and px and sh and mc > 0:
        implied = px * sh
        diff = abs(implied - mc) / mc
        if diff > conflict_threshold:
            add(CONFLICTING_SOURCES, "high", "market_cap_millions",
                f"market_cap {mc:.0f} vs price*shares {implied:.0f} differ {diff:.0%}")

    # 3. Large score move (only when both scores supplied)
    if prior_score is not None and current_score is not None and prior_score != 0:
        move = abs(current_score - prior_score) / abs(prior_score)
        if move > move_threshold:
            add(LARGE_SCORE_MOVE, "high", None,
                f"score moved {move:.0%} ({prior_score:.2f} -> {current_score:.2f})")

    # 4. Missing NCT — trial facts defaulted
    if not asset.nct_id:
        add(MISSING_NCT, "medium", "nct_id",
            "no NCT linked; trial facts (enrollment/endpoint/completion) are defaulted")

    # 5. Stale data — profile older than threshold
    age = _age_days(profile.generated_at, now)
    if age is not None and age > stale_days:
        add(STALE_DATA, "medium", None,
            f"profile built {int(age)}d ago (> {stale_days}d); economics/financials may be stale")

    # 6. Commercial assumptions are heuristic priors
    heuristic = [f for f in _ECON_FIELDS if getattr(asset, f).source == "heuristic_prior"]
    if heuristic:
        add(COMMERCIAL_HEURISTIC, "low", ",".join(heuristic),
            f"{len(heuristic)} commercial assumptions are heuristic priors (not name-specific)")

    return items


def build_review_queue(
    profiles: list[CompanyProfile],
    *,
    prior_scores: Optional[dict[str, float]] = None,
    current_scores: Optional[dict[str, float]] = None,
    now: Optional[datetime] = None,
    stale_days: int = 90,
    move_threshold: float = 0.25,
) -> list[ReviewItem]:
    """Build a severity-sorted review queue across all profiles."""
    prior_scores = prior_scores or {}
    current_scores = current_scores or {}
    now = now or datetime.now(timezone.utc)
    items: list[ReviewItem] = []
    for profile in profiles:
        tkr = profile.ticker.upper()
        items.extend(
            review_company(
                profile,
                now=now,
                stale_days=stale_days,
                prior_score=prior_scores.get(tkr),
                current_score=current_scores.get(tkr),
                move_threshold=move_threshold,
            )
        )
    items.sort(key=lambda i: (_SEVERITY_RANK.get(i.severity, 9), i.ticker, i.reason))
    return items


def render_text(items: list[ReviewItem]) -> str:
    """Render the queue grouped by severity, with a summary line."""
    if not items:
        return "Review queue: empty — nothing flagged."
    by_reason: dict[str, int] = {}
    for it in items:
        by_reason[it.reason] = by_reason.get(it.reason, 0) + 1
    lines = [
        f"Review queue: {len(items)} item(s) across {len({i.ticker for i in items})} name(s)",
        "  " + ", ".join(f"{r}={n}" for r, n in sorted(by_reason.items())),
        "",
    ]
    current = None
    for it in items:
        if it.severity != current:
            current = it.severity
            lines.append(f"[{it.severity.upper()}]")
        field = f" ({it.field})" if it.field else ""
        lines.append(f"  {it.ticker:6s} {it.reason}{field}: {it.detail}")
    return "\n".join(lines)

"""InputIntegrityScore — aggregated data freshness and source quality signal.

Combines signals from four refresh surfaces to produce a single
``InputIntegrityScore`` that can be included in decision reports.

Surfaces
--------
1. **Market data**  — price, market cap, EV freshness (``MarketDataSnapshot``)
2. **Financials**   — cash, burn, runway freshness (``FinancialSnapshot``)
3. **Profiles**     — acquirer profile age (``AcquirerProfileAuditResult``)
4. **Trials**       — CT.gov diff alert count (``TrialDiffResult``)

Score
-----
``overall_score`` ∈ [0.0, 1.0]; higher = better integrity.
- Each surface contributes up to 0.25.
- Surfaces with missing data contribute 0.00 (not 0.25) so reports clearly show
  which surfaces were not checked.
- ``overall_grade``: ``"A"`` (≥0.85), ``"B"`` (≥0.70), ``"C"`` (≥0.50), ``"D"`` (<0.50)

Design notes
------------
- ``InputIntegrityScore`` is a pure data container.
- ``build_input_integrity_score`` never raises.
- ``render_input_integrity`` returns a Markdown section.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


# ---------------------------------------------------------------------------
# Confidence → numeric weight mapping
# ---------------------------------------------------------------------------

_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "high": 1.0,
    "medium": 0.75,
    "low": 0.50,
    "stale": 0.25,
    "not_available": 0.0,
}

_MAX_PER_SURFACE: float = 0.25


def _confidence_to_score(confidence: str) -> float:
    return _CONFIDENCE_WEIGHTS.get(confidence, 0.0) * _MAX_PER_SURFACE


# ---------------------------------------------------------------------------
# Per-surface sub-score
# ---------------------------------------------------------------------------

@dataclass
class SurfaceScore:
    """Score and metadata for one refresh surface.

    Parameters
    ----------
    surface_name:
        Human-readable name (``"market_data"``, ``"financials"``, etc.).
    score:
        0.0–0.25 contribution to overall score.
    confidence:
        Confidence level of the underlying data.
    as_of:
        Date the underlying data was fetched/verified.
    notes:
        List of staleness or alert notes.
    """

    surface_name: str
    score: float = 0.0
    confidence: str = "not_available"
    as_of: Optional[date] = None
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregate score
# ---------------------------------------------------------------------------

@dataclass
class InputIntegrityScore:
    """Aggregated input integrity score across all four refresh surfaces.

    Parameters
    ----------
    overall_score:
        Weighted sum of surface scores ∈ [0.0, 1.0].
    overall_grade:
        Letter grade: ``"A"`` (≥0.85) | ``"B"`` (≥0.70) | ``"C"`` (≥0.50) | ``"D"``
    market_data:
        Sub-score for price/market cap freshness.
    financials:
        Sub-score for cash/burn/runway freshness.
    profiles:
        Sub-score for acquirer profile age.
    trials:
        Sub-score for CT.gov trial status freshness.
    as_of:
        Date this score was computed.
    warnings:
        List of human-readable integrity warnings.
    """

    overall_score: float = 0.0
    overall_grade: str = "D"
    market_data: SurfaceScore = field(default_factory=lambda: SurfaceScore("market_data"))
    financials: SurfaceScore = field(default_factory=lambda: SurfaceScore("financials"))
    profiles: SurfaceScore = field(default_factory=lambda: SurfaceScore("profiles"))
    trials: SurfaceScore = field(default_factory=lambda: SurfaceScore("trials"))
    as_of: Optional[date] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _surface(s: SurfaceScore) -> dict:
            return {
                "score": s.score,
                "confidence": s.confidence,
                "as_of": s.as_of.isoformat() if s.as_of else None,
                "notes": s.notes,
            }

        return {
            "overall_score": self.overall_score,
            "overall_grade": self.overall_grade,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "surfaces": {
                "market_data": _surface(self.market_data),
                "financials": _surface(self.financials),
                "profiles": _surface(self.profiles),
                "trials": _surface(self.trials),
            },
            "warnings": self.warnings,
        }


def _grade(score: float) -> str:
    if score >= 0.85:
        return "A"
    if score >= 0.70:
        return "B"
    if score >= 0.50:
        return "C"
    return "D"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def build_input_integrity_score(
    *,
    market_snapshot=None,
    financial_snapshot=None,
    profile_audit=None,
    trial_diff=None,
    reference_date: Optional[date] = None,
) -> InputIntegrityScore:
    """Build an InputIntegrityScore from available refresh surface results.

    All parameters are optional — surfaces with missing data contribute 0.0
    to the overall score and show ``"not_available"`` confidence.

    Parameters
    ----------
    market_snapshot:
        ``bve.refresh.market_data_refresh.MarketDataSnapshot`` (or None).
    financial_snapshot:
        ``bve.refresh.financial_refresh.FinancialSnapshot`` (or None).
    profile_audit:
        ``bve.refresh.profile_audit.AcquirerProfileAuditResult`` (or None).
    trial_diff:
        ``bve.refresh.trial_diff.TrialDiffResult`` (or None).
    reference_date:
        Date of computation; defaults to today.

    Returns
    -------
    InputIntegrityScore
    """
    ref = reference_date or date.today()
    all_warnings: list[str] = []

    # --- Market data ---
    md = SurfaceScore("market_data")
    if market_snapshot is not None:
        md.confidence = getattr(market_snapshot, "confidence", "not_available")
        md.score = _confidence_to_score(md.confidence)
        md.as_of = getattr(market_snapshot, "as_of", None)
        stale_warn = getattr(market_snapshot, "staleness_warning", None)
        if stale_warn:
            md.notes.append(stale_warn)
            all_warnings.append(f"[market_data] {stale_warn}")

    # --- Financials ---
    fin = SurfaceScore("financials")
    if financial_snapshot is not None:
        fin.confidence = getattr(financial_snapshot, "confidence", "not_available")
        fin.score = _confidence_to_score(fin.confidence)
        fin.as_of = getattr(financial_snapshot, "as_of", None)
        stale_warn = getattr(financial_snapshot, "staleness_warning", None)
        if stale_warn:
            fin.notes.append(stale_warn)
            all_warnings.append(f"[financials] {stale_warn}")

    # --- Profiles ---
    prof = SurfaceScore("profiles")
    if profile_audit is not None:
        # Profile score: penalize per stale/critical profile
        n_fresh = getattr(profile_audit, "n_fresh", 0)
        n_stale = getattr(profile_audit, "n_stale", 0)
        n_critical = getattr(profile_audit, "n_critical", 0)
        total = n_fresh + n_stale + n_critical
        if total > 0:
            fraction_fresh = n_fresh / total
            fraction_stale = n_stale / total
            # fresh → 1.0, stale → 0.5, critical → 0.0
            surface_quality = fraction_fresh * 1.0 + fraction_stale * 0.5
            prof.score = round(surface_quality * _MAX_PER_SURFACE, 4)
            if n_critical > 0:
                prof.confidence = "low"
            elif n_stale > 0:
                prof.confidence = "medium"
            else:
                prof.confidence = "high"
        else:
            prof.confidence = "not_available"
            prof.score = 0.0
        overall_cap = getattr(profile_audit, "overall_confidence_cap", None)
        if overall_cap:
            warn_msg = f"{n_stale} stale + {n_critical} critical acquirer profiles — confidence capped at {overall_cap}"
            prof.notes.append(warn_msg)
            all_warnings.append(f"[profiles] {warn_msg}")

    # --- Trial diff ---
    trl = SurfaceScore("trials")
    if trial_diff is not None:
        n_compared = getattr(trial_diff, "n_compared", 0)
        n_changed = getattr(trial_diff, "n_changed", 0)
        n_not_found = getattr(trial_diff, "n_not_found", 0)
        high_changes = getattr(trial_diff, "high_severity_changes", [])

        if n_compared > 0:
            # Penalise high-severity changes heavily, others moderately
            n_high = len(high_changes)
            penalty = min(1.0, (n_high * 0.25 + (n_changed - n_high) * 0.10 + n_not_found * 0.25))
            surface_quality = max(0.0, 1.0 - penalty)
            trl.score = round(surface_quality * _MAX_PER_SURFACE, 4)
            if n_high > 0 or n_not_found > 0:
                trl.confidence = "low"
            elif n_changed > 0:
                trl.confidence = "medium"
            else:
                trl.confidence = "high"
            trl.as_of = getattr(trial_diff, "run_date", None)
            for c in high_changes:
                alert_text = getattr(c, "alert_text", str(c))
                trl.notes.append(alert_text)
                all_warnings.append(f"[trials] {alert_text}")
        else:
            trl.confidence = "not_available"

    overall = round(md.score + fin.score + prof.score + trl.score, 4)

    return InputIntegrityScore(
        overall_score=overall,
        overall_grade=_grade(overall),
        market_data=md,
        financials=fin,
        profiles=prof,
        trials=trl,
        as_of=ref,
        warnings=all_warnings,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_input_integrity(score: InputIntegrityScore) -> str:
    """Render an InputIntegrityScore as a Markdown section."""
    na = "Not available"
    as_of_str = score.as_of.isoformat() if score.as_of else na

    grade_emoji = {"A": "✓", "B": "✓", "C": "⚠", "D": "✗"}.get(score.overall_grade, "")

    lines = [
        "## Input Integrity",
        "",
        f"**Grade:** {grade_emoji} **{score.overall_grade}** "
        f"({score.overall_score:.2f} / 1.00)  |  **As of:** {as_of_str}",
        "",
        "| Surface | Score | Confidence | As Of | Notes |",
        "|---|---|---|---|---|",
    ]

    def _surface_row(s: SurfaceScore) -> str:
        score_str = f"{s.score:.2f}"
        as_of_str = s.as_of.isoformat() if s.as_of else "—"
        notes_str = "; ".join(s.notes) if s.notes else "—"
        if len(notes_str) > 80:
            notes_str = notes_str[:77] + "..."
        return (
            f"| {s.surface_name} | {score_str} | {s.confidence} | "
            f"{as_of_str} | {notes_str} |"
        )

    for surface in [score.market_data, score.financials, score.profiles, score.trials]:
        lines.append(_surface_row(surface))

    lines.append("")

    if score.warnings:
        lines += ["**Integrity warnings:**", ""]
        for w in score.warnings:
            lines.append(f"- ⚠ {w}")
        lines.append("")

    return "\n".join(lines)

"""Multi-name dual-track screen: join BD/M&A rows with the investment lens.

Produces the dedicated dual-track artifact (the polished primary surface) and
the flat columns used to augment the existing M&A screen. For each screened
name it composes:

  - the INVESTMENT verdict, hybrid / no-recompute:
      1. the full verdict from ``outputs/<TICKER>/valuation.json`` when present
         (``dual_track.investment`` block — NAV upside + mispricing read), else
      2. a coarse rNPV-vs-EV stance from the row's own
         ``model_rnpv_millions`` / ``enterprise_value_millions``, else
      3. ``not_assessed``.
    The evidence level (full / coarse / not_assessed) is always carried so the
    reader knows how the stance was derived.

  - the BD verdict from the row (strategic relevance, best acquirer, route, …).

The two verdicts are kept separate; the cross-read only describes their
relationship. No blended score is produced, and the existing screen sort order
is never changed by this module.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Optional

from bve.analysis.dual_track import (
    BDVerdict,
    DualTrackAssessment,
    DualTrackThresholds,
    InvestmentVerdict,
    build_bd_verdict,
    build_dual_track,
    compose_assessment,
)

_DEFAULT_OUTPUTS_DIR = "outputs"


# ---------------------------------------------------------------------------
# Investment lens — hybrid loader
# ---------------------------------------------------------------------------

def load_investment_verdict(
    ticker: str,
    *,
    outputs_dir: str | Path = _DEFAULT_OUTPUTS_DIR,
) -> Optional[InvestmentVerdict]:
    """Load the full investment verdict from a saved ``valuation.json``.

    Reads ``<outputs_dir>/<TICKER>/valuation.json`` and reconstructs the
    ``dual_track.investment`` block. Returns ``None`` when the file or block is
    absent (the caller then falls back to the coarse path).
    """
    if not ticker:
        return None
    path = Path(outputs_dir) / ticker.upper() / "valuation.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        block = raw.get("dual_track", {}).get("investment")
        if not block:
            return None
        verdict = InvestmentVerdict.model_validate(block)
        # Only the full, price-anchored verdict is reusable here.
        return verdict if verdict.evidence == "full" and verdict.assessed else None
    except Exception:
        return None


def _coarse_investment(row: Any, thresholds: DualTrackThresholds) -> InvestmentVerdict:
    """Coarse investment verdict from a row's rNPV / EV (or not_assessed)."""
    rnpv = getattr(row, "model_rnpv_millions", None)
    ev = getattr(row, "enterprise_value_millions", None)
    return build_dual_track(
        None,
        coarse_rnpv_millions=rnpv,
        coarse_ev_millions=ev,
        thresholds=thresholds,
    ).investment


# ---------------------------------------------------------------------------
# Per-row assessment
# ---------------------------------------------------------------------------

def assess_target(
    row: Any,
    *,
    outputs_dir: str | Path = _DEFAULT_OUTPUTS_DIR,
    thresholds: Optional[DualTrackThresholds] = None,
    bdma_output: Any | None = None,
) -> DualTrackAssessment:
    """Compose the dual-track assessment for one screen row.

    ``row`` is duck-typed; an ``MAProbabilityRow`` is ideal (it carries
    ``ticker``, ``model_rnpv_millions``, ``enterprise_value_millions``,
    ``recommended_deal_structure``, ``best_acquirer_name`` …).
    """
    t = thresholds or DualTrackThresholds()
    ticker = getattr(row, "ticker", None)

    investment = load_investment_verdict(ticker or "", outputs_dir=outputs_dir)
    if investment is None:
        investment = _coarse_investment(row, t)

    bd: BDVerdict = build_bd_verdict(ma_row=row, bdma_output=bdma_output, thresholds=t)
    return compose_assessment(investment, bd)


def assess_targets(
    rows: list[Any],
    *,
    outputs_dir: str | Path = _DEFAULT_OUTPUTS_DIR,
    thresholds: Optional[DualTrackThresholds] = None,
) -> list[tuple[Any, DualTrackAssessment]]:
    """Assess a list of rows, preserving their input order (sort unchanged)."""
    t = thresholds or DualTrackThresholds()
    return [
        (row, assess_target(row, outputs_dir=outputs_dir, thresholds=t))
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Liveness — separate the LIVE screen from the backtest universe
# ---------------------------------------------------------------------------

Liveness = Literal["live", "pit_stale", "inactive", "no_config"]

_LIVENESS_REASON = {
    "pit_stale": "stale point-in-time economics (refresh to include)",
    "inactive": "inactive / delisted / acquired (no current market data)",
    "no_config": "no valuation config yet (not assessed)",
}


def classify_liveness(ticker: str | None, config_map: dict[str, str]) -> Liveness:
    """Classify a name for the LIVE screen from its valuation-config source.

    - ``live``      — a current-economics config (provisional, named, or a
                      refreshed auto_generated config that carries a real
                      market cap).
    - ``pit_stale`` — only a point-in-time replay config exists; the company may
                      well be live, but its investment economics are frozen at the
                      backtest date and should not be trusted as a current read.
    - ``inactive``  — an auto_generated config whose economics could not be
                      refreshed (no current market data → delisted / acquired).
    - ``no_config`` — no config; cannot be assessed.

    Pure config-source classification — deterministic and offline.
    """
    if not ticker:
        return "no_config"
    path = config_map.get(ticker.upper())
    if not path:
        return "no_config"
    if "replay_generated" in path:
        return "pit_stale"
    if "auto_generated" in path:
        # Refreshed configs carry an explicit market_cap_millions; the unrefreshed
        # placeholders (delisted/acquired names) do not.
        try:
            import yaml

            cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
            company = cfg.get("company", {}) if isinstance(cfg, dict) else {}
            if company.get("market_cap_millions") is None:
                return "inactive"
        except Exception:
            return "inactive"
    return "live"  # provisional / named / refreshed auto_generated


def partition_by_liveness(
    assessed: list[tuple[Any, DualTrackAssessment]],
    config_map: dict[str, str],
) -> tuple[list[tuple[Any, DualTrackAssessment]], dict[str, list[str]]]:
    """Split assessed rows into the live screen vs everything excluded from it.

    Returns ``(live_assessed, excluded)`` where ``excluded`` maps a liveness
    reason (``pit_stale`` / ``inactive`` / ``no_config``) to the tickers dropped
    for that reason. The live set preserves input order.
    """
    live: list[tuple[Any, DualTrackAssessment]] = []
    excluded: dict[str, list[str]] = {}
    for row, a in assessed:
        tkr = getattr(row, "ticker", None)
        kind = classify_liveness(tkr, config_map)
        if kind == "live":
            live.append((row, a))
        else:
            excluded.setdefault(kind, []).append((tkr or "?").upper())
    return live, excluded


# ---------------------------------------------------------------------------
# Acquirer concentration diagnostic
# ---------------------------------------------------------------------------

def acquirer_concentration(
    assessed: list[tuple[Any, DualTrackAssessment]],
    *,
    threshold: float = 0.30,
) -> tuple[Counter, list[str]]:
    """Count best-acquirer frequency and flag over-concentration.

    If any single acquirer is the named "natural acquirer" for ``threshold`` or
    more of the names with a BD verdict, it is flagged — that usually means the
    acquirer-fit scoring is too generic to be trusted as a specific call.
    """
    counts: Counter = Counter()
    for _row, a in assessed:
        acquirer = (a.bd.best_acquirer or "").split(" (")[0].strip()
        if acquirer:
            counts[acquirer] += 1
    total = sum(counts.values())
    flagged: list[str] = []
    if total > 0:
        for acquirer, n in counts.items():
            if n / total >= threshold:
                flagged.append(f"{acquirer} ({n}/{total} = {100 * n / total:.0f}%)")
    return counts, flagged


# ---------------------------------------------------------------------------
# Flat rows + renderers (the dedicated artifact)
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "rank",
    "ticker",
    "investment_stance",
    "investment_evidence",
    "investment_rnpv_vs_ev_pct",
    "bd_relevance",
    "bd_route",
    "bd_best_acquirer",
    "bd_timing",
    "quadrant",
    "divergence",
    "headline",
]


def dual_track_rows(
    assessed: list[tuple[Any, DualTrackAssessment]],
) -> list[dict[str, Any]]:
    """Flat dict rows for ``dual_track.csv`` (input order preserved)."""
    rows: list[dict[str, Any]] = []
    for row, a in assessed:
        iv, bd = a.investment, a.bd
        rows.append(
            {
                "rank": getattr(row, "rank", ""),
                "ticker": getattr(row, "ticker", "") or "",
                "investment_stance": iv.stance,
                "investment_evidence": iv.evidence,
                "investment_rnpv_vs_ev_pct": (
                    round(iv.rnpv_vs_ev_pct, 1) if iv.rnpv_vs_ev_pct is not None else ""
                ),
                "bd_relevance": bd.strategic_relevance,
                "bd_route": bd.recommended_route,
                "bd_best_acquirer": bd.best_acquirer or "",
                "bd_timing": bd.timing,
                "quadrant": a.quadrant,
                "divergence": a.divergence,
                "headline": a.headline,
            }
        )
    return rows


def write_dual_track_csv(
    assessed: list[tuple[Any, DualTrackAssessment]],
    path: str | Path,
) -> Path:
    """Write the dedicated dual_track.csv."""
    import csv

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = dual_track_rows(assessed)
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return out


def render_dual_track_report(
    assessed: list[tuple[Any, DualTrackAssessment]],
    *,
    as_of: str | None = None,
    excluded: dict[str, list[str]] | None = None,
    acquirer_flags: list[str] | None = None,
) -> str:
    """Markdown dual-track report — the polished primary artifact.

    Leads with the divergence cases (where the two lenses disagree), then the
    full table. Never blends the two axes into a single score. When ``excluded``
    is supplied (live-screen mode), the names dropped from the live view are
    listed with their reason so nothing is silently lost. ``acquirer_flags``
    surfaces any over-concentrated "natural acquirer".
    """
    lines: list[str] = ["# Dual-Track Screen", ""]
    if as_of:
        lines += [f"**As of:** {as_of}", ""]
    lines += [
        "> Two independent lenses — investment (is the stock undervalued?) and "
        "BD/M&A (is the asset a good target?) — shown separately. A missing lens "
        "is _not assessed_, never a negative verdict. Investment evidence is "
        "labelled full / coarse / not_assessed.",
        "",
    ]

    if acquirer_flags:
        lines += [
            "> ⚠ **Acquirer concentration:** "
            + "; ".join(acquirer_flags)
            + ". One buyer dominating the 'natural acquirer' column usually means "
            "acquirer-fit scoring is too generic — treat the named acquirer as "
            "low-confidence.",
            "",
        ]

    diverging = [(r, a) for (r, a) in assessed if a.divergence]
    if diverging:
        lines += ["## Divergent names (the two lenses disagree)", ""]
        for _row, a in diverging:
            tkr = getattr(_row, "ticker", "") or "?"
            lines.append(f"- **{tkr}** — {a.headline}")
        lines.append("")

    lines += [
        "## All names",
        "",
        "| Rank | Ticker | Investment | Evidence | BD relevance → route | Best acquirer | Quadrant |",
        "|---|---|---|---|---|---|---|",
    ]
    for row, a in assessed:
        iv, bd = a.investment, a.bd
        rank = getattr(row, "rank", "") or ""
        tkr = getattr(row, "ticker", "") or "?"
        inv = f"{iv.stance} ({iv.valuation_label})" if iv.assessed else "not assessed"
        bd_cell = f"{bd.strategic_relevance} → {bd.recommended_route}" if bd.assessed else "not run"
        acq = bd.best_acquirer or "—"
        lines.append(
            f"| {rank} | {tkr} | {inv} | {iv.evidence} | {bd_cell} | {acq} | `{a.quadrant}` |"
        )
    lines.append("")

    if excluded:
        lines += ["## Excluded from the live screen", ""]
        for kind in ("pit_stale", "inactive", "no_config"):
            tickers = excluded.get(kind)
            if not tickers:
                continue
            reason = _LIVENESS_REASON.get(kind, kind)
            lines.append(f"- **{reason}** ({len(tickers)}): {', '.join(sorted(set(tickers)))}")
        lines.append("")
    return "\n".join(lines)

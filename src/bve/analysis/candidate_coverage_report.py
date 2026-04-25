"""Candidate coverage report: for each real deal, was the buyer in the candidate pool?

Reads deal_universe YAML and ma_probability_snapshots to answer:
  1. Was the target in our universe (scored)?
  2. If yes, who was the predicted top-1 acquirer?
  3. Was the real buyer in the candidate pool (any rank)?
  4. What rank was the real buyer?
  5. If missing: likely reason.

Usage::

    python -m bve.analysis.candidate_coverage_report \
        --knowledge-db outputs/intelligence/replay_knowledge.db \
        --deal-universe research/mna/deal_universe_2020_2026.yaml \
        --output outputs/analysis/candidate_coverage_report.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DealCoverageResult:
    ticker: str
    target_name: str
    acquirer: str
    announcement_date: str
    headline_value_millions: Optional[float]
    therapeutic_area: str

    # Universe coverage
    in_universe: bool = False
    n_pre_snapshots: int = 0
    closest_snapshot_date: Optional[str] = None

    # Acquirer prediction
    predicted_top1: Optional[str] = None
    top1_correct: bool = False

    # Candidate pool presence
    real_buyer_in_pool: bool = False
    real_buyer_rank: Optional[int] = None  # 1-indexed
    real_buyer_score: Optional[float] = None
    pool_size: int = 0

    # Diagnosis
    miss_reason: str = ""  # why real buyer missing or low-ranked

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "target_name": self.target_name,
            "acquirer": self.acquirer,
            "announcement_date": self.announcement_date,
            "headline_value_millions": self.headline_value_millions,
            "therapeutic_area": self.therapeutic_area,
            "in_universe": self.in_universe,
            "n_pre_snapshots": self.n_pre_snapshots,
            "closest_snapshot_date": self.closest_snapshot_date,
            "predicted_top1": self.predicted_top1,
            "top1_correct": self.top1_correct,
            "real_buyer_in_pool": self.real_buyer_in_pool,
            "real_buyer_rank": self.real_buyer_rank,
            "real_buyer_score": self.real_buyer_score,
            "pool_size": self.pool_size,
            "miss_reason": self.miss_reason,
        }


@dataclass
class CoverageSummary:
    total_deals: int
    public_deals: int
    in_universe: int
    top1_correct: int
    top3_correct: int
    top5_correct: int
    in_pool: int
    not_in_pool: int
    not_in_universe: int
    mean_rank_when_present: Optional[float]
    mrr: Optional[float]
    results: list[DealCoverageResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_deals": self.total_deals,
            "public_deals": self.public_deals,
            "in_universe": self.in_universe,
            "top1_correct": self.top1_correct,
            "top3_correct": self.top3_correct,
            "top5_correct": self.top5_correct,
            "in_pool": self.in_pool,
            "not_in_pool": self.not_in_pool,
            "not_in_universe": self.not_in_universe,
            "top1_accuracy": round(self.top1_correct / max(self.in_universe, 1), 4),
            "top3_accuracy": round(self.top3_correct / max(self.in_universe, 1), 4),
            "top5_accuracy": round(self.top5_correct / max(self.in_universe, 1), 4),
            "pool_coverage_rate": round(self.in_pool / max(self.in_universe, 1), 4),
            "mean_rank_when_present": self.mean_rank_when_present,
            "mrr": self.mrr,
            "results": [r.as_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# Acquirer name normalization
# ---------------------------------------------------------------------------

_ACQUIRER_ALIASES: dict[str, list[str]] = {
    "bristol-myers squibb": ["bms", "bristol myers squibb", "bristol-myers", "bmy"],
    "johnson & johnson": ["j&j", "janssen", "johnson and johnson", "johnson & johnson (janssen)"],
    "johnson & johnson (janssen)": ["j&j", "janssen", "johnson & johnson"],
    "eli lilly": ["lilly", "eli lilly and company"],
    "gilead sciences": ["gilead"],
    "roche / genentech": ["roche", "genentech", "roche/genentech"],
    "novo nordisk": ["novonordisk"],
    "astrazeneca": ["az", "astra zeneca"],
    "pfizer": ["pfizer inc"],
    # Vertex: canonical ticker VRTX; deal universe uses short form "Vertex"
    "vertex pharmaceuticals": ["vertex", "vrtx"],
    # Lundbeck: traded as HLUYY ADR; deal universe uses short form "Lundbeck"
    "h. lundbeck": ["lundbeck", "h lundbeck", "lundbeck a/s", "hluyy"],
    # Astellas: Japanese pharma (4503.T); acquirer of Iveric Bio (ophthalmology)
    "astellas pharma": ["astellas", "astellas pharma us", "astellas pharma inc", "4503.t"],
    # GSK: common short form used in deal universe
    "gsk": ["glaxosmithkline", "gsk plc", "glaxo smith kline", "glaxo wellcome"],
}


def _normalize_acquirer(name: str) -> str:
    return name.strip().lower()


def _acquirers_match(real: str, predicted: str) -> bool:
    r = _normalize_acquirer(real)
    p = _normalize_acquirer(predicted)
    if r == p:
        return True
    # Check aliases in both directions
    for canonical, aliases in _ACQUIRER_ALIASES.items():
        canon_n = _normalize_acquirer(canonical)
        all_forms = {canon_n} | {_normalize_acquirer(a) for a in aliases}
        if r in all_forms and p in all_forms:
            return True
    return False


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------


def _get_pre_announcement_snapshots(
    cur: sqlite3.Cursor,
    ticker: str,
    announcement_date: str,
    lookahead_days: int = 365,
) -> list[dict[str, Any]]:
    """Return snapshots from [announcement_date - lookahead_days, announcement_date)."""
    ann = date.fromisoformat(announcement_date)
    earliest = (ann - timedelta(days=lookahead_days)).isoformat()
    cur.execute(
        """
        SELECT snapshot_date, best_acquirer_name, acquirer_candidates_json, probability, rank
        FROM ma_probability_snapshots
        WHERE ticker = ?
          AND snapshot_date < ?
          AND snapshot_date >= ?
        ORDER BY snapshot_date DESC
        """,
        (ticker, ann.isoformat(), earliest),
    )
    rows = []
    for row in cur.fetchall():
        rows.append({
            "snapshot_date": row[0],
            "best_acquirer_name": row[1],
            "candidates_json": row[2],
            "probability": row[3],
            "rank": row[4],
        })
    return rows


def _find_real_buyer_in_candidates(
    candidates_json: Optional[str],
    real_acquirer: str,
) -> tuple[Optional[int], Optional[float], int]:
    """Return (1-indexed rank, score, pool_size) of real buyer in candidate list."""
    if not candidates_json:
        return None, None, 0
    try:
        candidates: list[dict[str, Any]] = json.loads(candidates_json)
    except (json.JSONDecodeError, TypeError):
        return None, None, 0

    pool_size = len(candidates)
    for idx, c in enumerate(candidates):
        name = c.get("acquirer_name") or ""
        if _acquirers_match(real_acquirer, name):
            score = c.get("mna_probability_score") or c.get("strategic_fit_score")
            return idx + 1, score, pool_size

    return None, None, pool_size


def _diagnose_miss(
    real_acquirer: str,
    therapeutic_area: str,
    candidates_json: Optional[str],
) -> str:
    """Produce a brief reason string when the real buyer is not in the pool."""
    if not candidates_json:
        return "no_candidates_stored"
    try:
        candidates: list[dict[str, Any]] = json.loads(candidates_json)
    except (json.JSONDecodeError, TypeError):
        return "candidates_parse_error"

    acquirer_names_in_pool = {
        _normalize_acquirer(c.get("acquirer_name") or "") for c in candidates
    }
    # Check if acquirer has any profile at all
    norm_real = _normalize_acquirer(real_acquirer)
    close_matches = [n for n in acquirer_names_in_pool if norm_real[:6] in n or n[:6] in norm_real]
    if close_matches:
        return f"acquirer_in_pool_but_name_mismatch: closest={close_matches[0]}"

    return f"acquirer_not_in_profile_library: {real_acquirer}"


def analyze_coverage(
    *,
    knowledge_db: str,
    deal_universe_path: str,
    lookahead_days: int = 365,
) -> CoverageSummary:
    payload = yaml.safe_load(Path(deal_universe_path).read_text(encoding="utf-8")) or {}
    deals_raw = payload.get("deals", []) if isinstance(payload, dict) else payload

    con = sqlite3.connect(knowledge_db)
    cur = con.cursor()

    # Get all tickers present in snapshots
    cur.execute("SELECT DISTINCT ticker FROM ma_probability_snapshots")
    universe_tickers = {row[0].upper() for row in cur.fetchall() if row[0]}

    results: list[DealCoverageResult] = []
    total = 0
    public_count = 0

    for deal in deals_raw:
        if not isinstance(deal, dict):
            continue
        total += 1
        ticker_raw = deal.get("target_ticker")
        target_name = deal.get("target_name", "")
        acquirer = deal.get("acquirer", "Unknown")
        ann_date = str(deal.get("announcement_date", "")).strip()
        headline = deal.get("headline_value_millions")
        ta = deal.get("therapeutic_area", "")

        if not ticker_raw or not ann_date:
            # Private deal — skip acquirer analysis
            results.append(DealCoverageResult(
                ticker="—",
                target_name=target_name,
                acquirer=acquirer,
                announcement_date=ann_date or "unknown",
                headline_value_millions=headline,
                therapeutic_area=ta,
                in_universe=False,
                miss_reason="private_company_no_ticker",
            ))
            continue

        public_count += 1
        ticker = str(ticker_raw).upper()
        res = DealCoverageResult(
            ticker=ticker,
            target_name=target_name,
            acquirer=acquirer,
            announcement_date=ann_date,
            headline_value_millions=headline,
            therapeutic_area=ta,
        )

        if ticker not in universe_tickers:
            res.in_universe = False
            res.miss_reason = "ticker_not_in_universe"
            results.append(res)
            continue

        res.in_universe = True
        snapshots = _get_pre_announcement_snapshots(cur, ticker, ann_date, lookahead_days)
        res.n_pre_snapshots = len(snapshots)

        if not snapshots:
            res.miss_reason = "in_universe_but_no_pre_announcement_snapshots"
            results.append(res)
            continue

        # Use the snapshot closest to announcement (most informed)
        closest = snapshots[0]
        res.closest_snapshot_date = closest["snapshot_date"]
        res.predicted_top1 = closest["best_acquirer_name"]
        res.top1_correct = bool(
            res.predicted_top1 and _acquirers_match(acquirer, res.predicted_top1)
        )

        rank, score, pool_size = _find_real_buyer_in_candidates(
            closest["candidates_json"], acquirer
        )
        res.real_buyer_in_pool = rank is not None
        res.real_buyer_rank = rank
        res.real_buyer_score = score
        res.pool_size = pool_size

        if not res.real_buyer_in_pool:
            res.miss_reason = _diagnose_miss(acquirer, ta, closest["candidates_json"])

        results.append(res)

    con.close()

    # Compute summary stats over public, in-universe deals
    in_univ = [r for r in results if r.in_universe]
    with_snapshots = [r for r in in_univ if r.n_pre_snapshots > 0]
    top1 = sum(1 for r in with_snapshots if r.top1_correct)
    top3 = sum(1 for r in with_snapshots if r.real_buyer_in_pool and (r.real_buyer_rank or 99) <= 3)
    top5 = sum(1 for r in with_snapshots if r.real_buyer_in_pool and (r.real_buyer_rank or 99) <= 5)
    in_pool = sum(1 for r in with_snapshots if r.real_buyer_in_pool)

    ranks = [r.real_buyer_rank for r in with_snapshots if r.real_buyer_rank is not None]
    mean_rank = round(sum(ranks) / len(ranks), 2) if ranks else None
    mrr = round(sum(1 / rk for rk in ranks) / len(ranks), 4) if ranks else None

    return CoverageSummary(
        total_deals=total,
        public_deals=public_count,
        in_universe=len(in_univ),
        top1_correct=top1,
        top3_correct=top3,
        top5_correct=top5,
        in_pool=in_pool,
        not_in_pool=len(with_snapshots) - in_pool,
        not_in_universe=public_count - len(in_univ),
        mean_rank_when_present=mean_rank,
        mrr=mrr,
        results=results,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_coverage_report(summary: CoverageSummary) -> str:
    lines = [
        "Candidate Coverage Report",
        f"  Deals total:      {summary.total_deals}  (public w/ ticker: {summary.public_deals})",
        f"  In universe:      {summary.in_universe} / {summary.public_deals}",
        f"  Top-1 accuracy:   {summary.top1_correct} / {summary.in_universe}"
        f"  = {summary.top1_correct / max(summary.in_universe, 1):.1%}",
        f"  Top-3 accuracy:   {summary.top3_correct} / {summary.in_universe}"
        f"  = {summary.top3_correct / max(summary.in_universe, 1):.1%}",
        f"  Pool coverage:    {summary.in_pool} / {summary.in_universe}"
        f"  = {summary.in_pool / max(summary.in_universe, 1):.1%}",
        f"  Mean rank (if present): {summary.mean_rank_when_present}",
        f"  MRR:              {summary.mrr}",
        "",
        f"  {'ticker':<8} {'acquirer':<30} {'date':<12} {'in_univ':<8} "
        f"{'snap':<5} {'pred_top1':<30} {'match':<6} {'rank':<6} {'miss_reason'}",
        "-" * 140,
    ]

    for r in summary.results:
        if r.ticker == "—":
            continue  # skip private deals in table
        rank_str = str(r.real_buyer_rank) if r.real_buyer_rank else "—"
        match_str = "YES" if r.top1_correct else ("—" if not r.in_universe else "no")
        pred = (r.predicted_top1 or "—")[:29]
        miss = r.miss_reason[:50] if r.miss_reason else ""
        lines.append(
            f"  {r.ticker:<8} {r.acquirer:<30} {r.announcement_date:<12} "
            f"{'Y' if r.in_universe else 'N':<8} {r.n_pre_snapshots:<5} "
            f"{pred:<30} {match_str:<6} {rank_str:<6} {miss}"
        )

    lines += [
        "",
        "Failure analysis (buyers missing from pool):",
    ]
    missing = [r for r in summary.results if r.in_universe and r.n_pre_snapshots > 0 and not r.real_buyer_in_pool]
    for r in missing:
        lines.append(f"  {r.ticker}: real={r.acquirer}  reason={r.miss_reason}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser(description="Candidate coverage report")
    p.add_argument("--knowledge-db", default="outputs/intelligence/replay_knowledge.db")
    p.add_argument("--deal-universe", default="research/mna/deal_universe_2020_2026.yaml")
    p.add_argument("--lookahead-days", type=int, default=365)
    p.add_argument("--output", default="outputs/analysis/candidate_coverage_report.json")
    args = p.parse_args()

    summary = analyze_coverage(
        knowledge_db=args.knowledge_db,
        deal_universe_path=args.deal_universe,
        lookahead_days=args.lookahead_days,
    )
    print(render_coverage_report(summary))
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary.as_dict(), indent=2), encoding="utf-8")
    print(f"\nJSON: {out}")


if __name__ == "__main__":
    main()

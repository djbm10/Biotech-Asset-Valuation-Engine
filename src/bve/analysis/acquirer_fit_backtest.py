"""
Acquirer-fit model backtest: grade precision@1, precision@3, and MRR
on closed M&A deals from research/mna/comparable_deals.yaml.

For each deal, a synthetic AcquirerFitCandidate is built from the deal
metadata and scored against all loaded acquirer profiles.  The actual
acquirer's rank in the sorted result list is recorded.

Usage:
    python -m bve.analysis.acquirer_fit_backtest
    python -m bve.analysis.acquirer_fit_backtest --verbose
    python -m bve.analysis.acquirer_fit_backtest --min-data-quality high
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from bve.intelligence.acquirer_fit import AcquirerFitCandidate, AcquirerFitScorer
from bve.intelligence.acquirer_profiles import AcquirerProfile, AcquirerProfileLoader

# ---------------------------------------------------------------------------
# Acquirer name → profile acquirer_id
# ---------------------------------------------------------------------------

_ACQUIRER_ALIAS_MAP: dict[str, str] = {
    "pfizer": "pfizer",
    "bristol myers squibb": "bristol_myers_squibb",
    "bristol-myers squibb": "bristol_myers_squibb",
    "bms": "bristol_myers_squibb",
    "merck": "merck",
    "merck & co": "merck",
    "merck & co.": "merck",
    "eli lilly": "eli_lilly",
    "lilly": "eli_lilly",
    "abbvie": "abbvie",
    "johnson & johnson": "johnson_johnson_janssen",
    "johnson and johnson": "johnson_johnson_janssen",
    "janssen": "johnson_johnson_janssen",
    "jnj": "johnson_johnson_janssen",
    "roche": "roche_genentech",
    "genentech": "roche_genentech",
    "roche / genentech": "roche_genentech",
    "novartis": "novartis",
    "astrazeneca": "astrazeneca",
    "gsk": "gsk",
    "glaxosmithkline": "gsk",
    "sanofi": "sanofi",
    "amgen": "amgen",
    "gilead sciences": "gilead_sciences",
    "gilead": "gilead_sciences",
    "biogen": "biogen",
    "vertex pharmaceuticals": "vertex_pharmaceuticals",
    "vertex": "vertex_pharmaceuticals",
    "bayer": "bayer_ag",
    "bayer ag": "bayer_ag",
    "astellas": "astellas_pharma",
    "astellas pharma": "astellas_pharma",
    "daiichi sankyo": "daiichi_sankyo",
    "lundbeck": "h_lundbeck",
    "h. lundbeck": "h_lundbeck",
    "regeneron": "regeneron_pharmaceuticals",
    "regeneron pharmaceuticals": "regeneron_pharmaceuticals",
    "incyte": "incyte_corporation",
    "incyte corporation": "incyte_corporation",
    "jazz pharmaceuticals": "jazz_pharmaceuticals",
    "jazz": "jazz_pharmaceuticals",
    "ipsen": "ipsen",
    "ucb": "ucb",
    "united therapeutics": "united_therapeutics",
    "novo nordisk": "novo_nordisk",
    "takeda": "takeda_pharmaceutical",
    "takeda pharmaceutical": "takeda_pharmaceutical",
    "servier": "servier",
    "sumitomo pharma": "sumitomo_pharma",
    "chugai": "chugai_pharmaceutical",
    "chugai pharmaceutical": "chugai_pharmaceutical",
    "kyowa kirin": "kyowa_kirin",
    "otsuka": "otsuka_pharmaceutical",
    "otsuka pharmaceutical": "otsuka_pharmaceutical",
    "boehringer ingelheim": "boehringer_ingelheim",
}

_DATA_QUALITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _resolve_acquirer_id(raw_name: str) -> Optional[str]:
    return _ACQUIRER_ALIAS_MAP.get(raw_name.strip().lower())


def _primary_indication(raw: str) -> str:
    """Extract the primary indication from a compound string.

    Compound indications in deal records often look like:
        "IgA nephropathy / autoimmune (B cell / T cell co-stimulation)"
        "ulcerative colitis / Crohn's disease"
    We take only the text before the first "/" or "(" to get the canonical
    primary indication that the cross-TA wiring can look up.
    """
    for sep in ("/", "(", ";"):
        if sep in raw:
            raw = raw.split(sep)[0]
    return raw.strip()


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class AcquirerFitBacktestRow:
    target_name: str
    target_ticker: Optional[str]
    indication: str
    therapeutic_area: str
    phase: str
    acquirer_raw: str
    acquirer_id: str
    deal_date: str
    data_quality: str
    ranked_acquirer_ids: list[str]
    ranked_scores: list[float]
    actual_rank: Optional[int]       # 1-based; None only if acquirer somehow missing after filtering
    reciprocal_rank: float

    @property
    def hit_at_1(self) -> bool:
        return self.actual_rank == 1

    @property
    def hit_at_3(self) -> bool:
        return self.actual_rank is not None and self.actual_rank <= 3


@dataclass
class AcquirerFitBacktestResult:
    rows: list[AcquirerFitBacktestRow]
    n_total_deals: int
    n_skipped_no_profile: int
    n_graded: int
    precision_at_1: float
    precision_at_3: float
    mean_reciprocal_rank: float
    hits_at_1: int
    hits_at_3: int

    def print_summary(self, *, verbose: bool = False) -> None:
        print()
        print("Acquirer-Fit Backtest Results")
        print("=" * 72)
        print(f"  Deals loaded:          {self.n_total_deals}")
        print(f"  Skipped (no profile):  {self.n_skipped_no_profile}")
        print(f"  Graded:                {self.n_graded}")
        print(f"  Precision@1:           {self.precision_at_1:.1%}  ({self.hits_at_1}/{self.n_graded})")
        print(f"  Precision@3:           {self.precision_at_3:.1%}  ({self.hits_at_3}/{self.n_graded})")
        print(f"  Mean Reciprocal Rank:  {self.mean_reciprocal_rank:.3f}")
        print()

        if verbose:
            print(f"  {'Target':<33} {'Actual Acquirer':<26} {'Rank':>4}  {'Top-3 Predictions'}")
            print("  " + "-" * 95)
            for row in sorted(self.rows, key=lambda r: (r.actual_rank or 999, r.target_name)):
                rank_str = str(row.actual_rank) if row.actual_rank is not None else "—"
                top3 = ", ".join(row.ranked_acquirer_ids[:3])
                hit = "P1" if row.hit_at_1 else ("P3" if row.hit_at_3 else "  ")
                print(
                    f"  [{hit}] {row.target_name:<31} {row.acquirer_raw:<26} "
                    f"{rank_str:>4}  {top3}"
                )
            print()


# ---------------------------------------------------------------------------
# Core runner
# ---------------------------------------------------------------------------

def run_acquirer_fit_backtest(
    *,
    deals_path: Path,
    profiles_path: Path,
    ma_only: bool = True,
    min_data_quality: str = "medium",
) -> AcquirerFitBacktestResult:
    dataset = AcquirerProfileLoader.load(profiles_path)
    profiles: list[AcquirerProfile] = dataset.acquirers
    profile_id_set = {p.acquirer_id for p in profiles}

    scorer = AcquirerFitScorer()
    min_rank = _DATA_QUALITY_RANK.get(min_data_quality, 1)

    raw = yaml.safe_load(deals_path.read_text(encoding="utf-8")) or {}
    all_deals = raw.get("deals", [])

    n_total = 0
    n_skipped = 0
    rows: list[AcquirerFitBacktestRow] = []

    for record in all_deals:
        # Structure filter
        deal_structure = record.get("deal_structure")
        if ma_only and deal_structure != "M&A":
            continue
        # Quality filter
        dq = record.get("data_quality", "medium")
        if _DATA_QUALITY_RANK.get(dq, 1) < min_rank:
            continue

        n_total += 1
        acquirer_raw = record.get("acquirer", "")
        acquirer_id = _resolve_acquirer_id(acquirer_raw)

        if acquirer_id is None or acquirer_id not in profile_id_set:
            n_skipped += 1
            continue

        # EV/peak-sales ratio
        ev = record.get("enterprise_value_millions")
        ps = record.get("peak_sales_millions")
        ev_ps = record.get("ev_to_peak_sales")
        if ev_ps is None and ev is not None and ps and ps > 0:
            ev_ps = round(ev / ps, 3)

        raw_indication = record.get("indication", "")
        target = AcquirerFitCandidate(
            asset_id=f"bt_{record.get('target_name', 'unknown').lower().replace(' ', '_')[:30]}",
            company_name=record.get("target_name"),
            ticker=record.get("target_ticker"),
            therapeutic_area=record.get("therapeutic_area", ""),
            indication=_primary_indication(raw_indication),
            modality=record.get("modality"),
            stage=record.get("phase_at_acquisition", ""),
            enterprise_value_millions=ev,
            ev_to_peak_sales=ev_ps,
        )

        scored: list[tuple[str, float]] = []
        for profile in profiles:
            fit = scorer.score_target(acquirer=profile, target=target)
            scored.append((profile.acquirer_id, fit.fit_score))

        scored.sort(key=lambda x: (-x[1], x[0]))
        ranked_ids = [s[0] for s in scored]
        ranked_scores = [s[1] for s in scored]

        try:
            actual_rank = ranked_ids.index(acquirer_id) + 1
        except ValueError:
            actual_rank = None

        rr = 1.0 / actual_rank if actual_rank is not None else 0.0

        rows.append(AcquirerFitBacktestRow(
            target_name=record.get("target_name", ""),
            target_ticker=record.get("target_ticker"),
            indication=record.get("indication", ""),
            therapeutic_area=record.get("therapeutic_area", ""),
            phase=record.get("phase_at_acquisition", ""),
            acquirer_raw=acquirer_raw,
            acquirer_id=acquirer_id,
            deal_date=str(record.get("deal_date", "")),
            data_quality=dq,
            ranked_acquirer_ids=ranked_ids,
            ranked_scores=ranked_scores,
            actual_rank=actual_rank,
            reciprocal_rank=rr,
        ))

    n_graded = len(rows)
    hits1 = sum(1 for r in rows if r.hit_at_1)
    hits3 = sum(1 for r in rows if r.hit_at_3)
    mrr = sum(r.reciprocal_rank for r in rows) / n_graded if n_graded > 0 else 0.0

    return AcquirerFitBacktestResult(
        rows=rows,
        n_total_deals=n_total,
        n_skipped_no_profile=n_skipped,
        n_graded=n_graded,
        precision_at_1=hits1 / n_graded if n_graded > 0 else 0.0,
        precision_at_3=hits3 / n_graded if n_graded > 0 else 0.0,
        mean_reciprocal_rank=mrr,
        hits_at_1=hits1,
        hits_at_3=hits3,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bve.analysis.acquirer_fit_backtest",
        description="Grade acquirer-fit model on closed M&A deals.",
    )
    p.add_argument("--deals", default="research/mna/comparable_deals.yaml")
    p.add_argument("--profiles", default="examples/research/acquirer_profiles/")
    p.add_argument("--all-deals", action="store_true", default=False,
                   help="Include licensing/option deals (default: M&A only)")
    p.add_argument("--min-data-quality", choices=["low", "medium", "high"], default="medium")
    p.add_argument("--verbose", "-v", action="store_true", default=False)
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    deals_path = Path(args.deals)
    profiles_path = Path(args.profiles)

    if not deals_path.exists():
        print(f"ERROR: deals file not found: {deals_path}", file=sys.stderr)
        return 1
    if not profiles_path.exists():
        print(f"ERROR: profiles path not found: {profiles_path}", file=sys.stderr)
        return 1

    result = run_acquirer_fit_backtest(
        deals_path=deals_path,
        profiles_path=profiles_path,
        ma_only=not args.all_deals,
        min_data_quality=args.min_data_quality,
    )
    result.print_summary(verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())

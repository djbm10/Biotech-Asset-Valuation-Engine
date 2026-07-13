"""bve-discover — autonomous lead-asset discovery (Slice 1: read-only).

Commands
--------
  backtest  Run the lead-asset ranker against the universe seeds and print/write
            a precision/recall + failure-mode report. Go/no-go evidence for
            enabling routing + auto-add in a later slice.
  detect    Spot-check one company: print its candidate programs + ranked lead.

Both commands are READ-ONLY. The only thing written is the CT.gov disk cache and
an optional report file, both under outputs/discovery/.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from bve.discovery.backtest import run_backtest
from bve.discovery.lead_ranker import rank_leads, score_program
from bve.discovery.program_cluster import cluster_programs
from bve.discovery.routing import CandidateCompany, run_routing
from bve.discovery.sponsor_trials import TrialRecord, fetch_sponsor_trials
from bve.pipeline.disk_cache import DiskCache
from bve.pipeline.universe_registry import load_universe_registry

_DEFAULT_REGISTRY = "examples/configs/universe_registry.yaml"
_DEFAULT_OUT_DIR = "outputs/discovery"
_DEFAULT_CACHE_DIR = "outputs/discovery/ctgov_cache"
_DEFAULT_AUDIT_OUT = "outputs/discovery/routing_audit.txt"
_DEFAULT_PROPOSALS_OUT = "outputs/discovery/proposed_seeds.yaml"
_DEFAULT_SEEDS_AUTO = "examples/configs/seeds_auto.yaml"
_DEFAULT_EXCLUSIONS = "examples/configs/discovery_exclusions.yaml"
_DEFAULT_DB = "outputs/intelligence/ops.db"


def _make_fetch(cache_dir: str, *, cache_only: bool, refresh: bool):
    """Build a name→[TrialRecord] fetcher backed by a DiskCache under outputs/discovery/."""
    cache = None if refresh else DiskCache(root=Path(cache_dir))

    def fetch(company_name: str) -> list[TrialRecord]:
        return fetch_sponsor_trials(company_name, cache=cache, cache_only=cache_only)

    return fetch


def _cmd_backtest(args: argparse.Namespace) -> None:
    seeds = load_universe_registry(args.registry)
    if args.limit:
        seeds = seeds[: args.limit]
    fetch = _make_fetch(args.cache_dir, cache_only=args.cache_only, refresh=args.refresh)

    report = run_backtest(seeds, fetch_fn=fetch)
    out = json.dumps(report.to_dict(), indent=2) if args.format == "json" else report.to_text()

    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(out + "\n", encoding="utf-8")
        print(f"Wrote backtest report ({report.n_seeds} seeds): {path}")
    else:
        print(out)


def _resolve_sponsor(args: argparse.Namespace) -> str:
    if args.sponsor:
        return args.sponsor
    wanted = args.ticker.upper()
    for seed in load_universe_registry(args.registry):
        if seed.ticker.upper() == wanted:
            return seed.company_name
    raise SystemExit(f"Ticker {wanted} not in {args.registry}; use --sponsor instead")


def _cmd_detect(args: argparse.Namespace) -> None:
    company = _resolve_sponsor(args)
    fetch = _make_fetch(args.cache_dir, cache_only=args.cache_only, refresh=args.refresh)
    trials = fetch(company)
    programs = cluster_programs(trials)

    print(f"{company}: {len(trials)} trial(s) → {len(programs)} program(s)")
    lead = rank_leads(programs)
    for i, prog in enumerate(programs, 1):
        score, _ = score_program(prog)
        flag = "  <== LEAD" if lead and prog.drug_key == lead.program.drug_key else ""
        print(
            f"  {i:2d}. {prog.drug:32s} {prog.max_phase or 'no-phase':9s} "
            f"n={prog.n_trials} enroll={prog.enrollment_max or '-'} "
            f"score={score:.3f}{flag}"
        )
    if lead:
        print(
            f"\nLead: {lead.program.drug}  tier={lead.tier} "
            f"margin={lead.margin:.3f} confidence={lead.confidence:.2f}"
        )
        print(f"  components: {lead.components}")
    else:
        print("\nNo lead — no clusterable programs found.")


def _load_candidates(args: argparse.Namespace) -> tuple[list[CandidateCompany], set[str]]:
    """Candidates to route + the set of already-seeded tickers (for exclusion).

    Three sources, in priority order:
    - ``--enumerate``: the rules-based universe screen (ops/universe_builder) — the
      automatic discovery path.
    - ``--candidates PATH``: a supplied YAML list of new names.
    - neither: self-audit the registry's own companies (writes nothing, since all
      are seeded) so the decision logic — including the MRUS rule — can be
      inspected against known companies.

    "Already seeded" spans both the curated registry and any staged seeds_auto.yaml,
    so a name already promoted is not proposed again.
    """
    seeds = load_universe_registry(args.registry)
    existing = {s.ticker.upper() for s in seeds}
    seeds_auto_path = Path(getattr(args, "seeds_auto", _DEFAULT_SEEDS_AUTO))
    if seeds_auto_path.exists():
        try:
            existing |= {s.ticker.upper() for s in load_universe_registry(seeds_auto_path)}
        except Exception:
            pass
    if getattr(args, "enumerate_universe", False):
        from bve.discovery.candidate_source import enumerate_candidates
        from bve.ops.universe_builder import UniverseFilter

        filt = UniverseFilter()
        if args.min_mktcap is not None:
            filt.min_mktcap_m = args.min_mktcap
        if args.max_mktcap is not None:
            filt.max_mktcap_m = args.max_mktcap
        candidates = enumerate_candidates(
            filt=filt, max_tickers=args.max_tickers,
            skip_clinical_check=args.skip_clinical_check,
        )
    elif args.candidates:
        raw = yaml.safe_load(Path(args.candidates).read_text(encoding="utf-8")) or []
        rows = raw.get("candidates", []) if isinstance(raw, dict) else raw
        candidates = [CandidateCompany.model_validate(r) for r in rows]
    else:
        candidates = [CandidateCompany(ticker=s.ticker, company_name=s.company_name)
                      for s in seeds]
    return candidates, existing


def _cmd_route(args: argparse.Namespace) -> None:
    candidates, existing = _load_candidates(args)
    if args.limit:
        candidates = candidates[: args.limit]
    fetch = _make_fetch(args.cache_dir, cache_only=args.cache_only, refresh=args.refresh)

    from bve.discovery.exclusion_ledger import ExclusionLedger

    excluded = ExclusionLedger(args.exclusions).excluded_tickers()

    result = run_routing(
        candidates, fetch_fn=fetch, existing_tickers=existing,
        excluded_tickers=excluded, auto_add_high=args.auto_add_high_confidence,
    )

    audit = json.dumps(result.to_dict(), indent=2) if args.format == "json" else result.to_audit_text()
    print(audit)
    audit_path = Path(args.audit_out)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(audit + "\n", encoding="utf-8")
    print(f"\nWrote routing audit: {audit_path}")

    # Conservative: --write-proposals is the single switch that persists seeds.
    # --auto-add-high-confidence only reclassifies high→auto_add; it still needs
    # --write-proposals to write anything. Two explicit opt-ins to mutate state.
    if args.write_proposals:
        doc = result.proposals_doc()
        prop_path = Path(args.proposals_out)
        prop_path.parent.mkdir(parents=True, exist_ok=True)
        prop_path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
        print(f"Wrote {len(result.proposals)} proposal(s) + {len(result.auto_added)} "
              f"auto-add(s): {prop_path}")
    else:
        n_would = len(result.proposals) + len(result.auto_added)
        print(f"\nDRY RUN — only the audit was written. {n_would} seed(s) would be "
              f"proposed/added; pass --write-proposals to persist.")


def _log_decision(ticker: str, action: str, *, reviewer, rationale, db_path: str) -> None:
    """Record a proposed_seed disposition so the review queue suppresses it."""
    from datetime import datetime, timezone

    from bve.pipeline.review_queue import PROPOSED_SEED
    from bve.pipeline.review_writeback import ProfileReviewStore, ReviewDispositionRecord

    store = ProfileReviewStore(db_path)
    try:
        store.record(ReviewDispositionRecord(
            ticker=ticker, asset_id=None, reason=PROPOSED_SEED, field=None,
            action=action, value=None, rationale=rationale, reviewer=reviewer,
            decided_at=datetime.now(timezone.utc).isoformat(),
        ))
    finally:
        store.close()


def _cmd_approve(args: argparse.Namespace) -> None:
    from bve.discovery.seed_promotion import STATUS_PROMOTED, promote_seed

    result = promote_seed(
        args.ticker,
        proposals_path=args.proposals_out,
        seeds_auto_path=args.seeds_auto,
        registry_path=args.registry,
        exclusion_path=args.exclusions,
        reviewer=args.reviewer,
        rationale=args.rationale,
    )
    print(f"{result.status.upper()}: {result.detail}")
    if result.status != STATUS_PROMOTED:
        raise SystemExit(1)
    _log_decision(args.ticker, "approve", reviewer=args.reviewer,
                  rationale=args.rationale, db_path=args.db)
    print(f"Logged approval; run `bve-profile build --missing --seeds-auto {args.seeds_auto}` "
          f"to build {args.ticker.upper()}.")


def _cmd_reject(args: argparse.Namespace) -> None:
    from bve.discovery.exclusion_ledger import REASON_REJECTED, ExclusionLedger

    ledger = ExclusionLedger(args.exclusions)
    ledger.add(args.ticker, args.reason or REASON_REJECTED,
               note=args.rationale, reviewer=args.reviewer)
    path = ledger.save()
    _log_decision(args.ticker, "reject", reviewer=args.reviewer,
                  rationale=args.rationale, db_path=args.db)
    print(f"REJECTED: {args.ticker.upper()} ({args.reason or REASON_REJECTED}) "
          f"added to exclusion ledger {path}")


def _cmd_defer(args: argparse.Namespace) -> None:
    _log_decision(args.ticker, "defer", reviewer=args.reviewer,
                  rationale=args.rationale, db_path=args.db)
    print(f"DEFERRED: {args.ticker.upper()} — suppressed until the next enumeration "
          f"re-proposes it (not excluded).")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="bve-discover", description="Lead-asset discovery")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bt = sub.add_parser("backtest", help="Backtest the ranker against universe seeds")
    p_bt.add_argument("--registry", default=_DEFAULT_REGISTRY)
    p_bt.add_argument("--limit", type=int, default=0, help="Only evaluate the first N seeds")
    p_bt.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR)
    p_bt.add_argument("--refresh", action="store_true", help="Ignore cache; refetch from CT.gov")
    p_bt.add_argument("--cache-only", action="store_true", help="Never hit the network")
    p_bt.add_argument("--format", choices=["text", "json"], default="text")
    p_bt.add_argument("--output", help="Write report here (default: stdout)")

    p_dt = sub.add_parser("detect", help="Spot-check one company's programs + lead")
    grp = p_dt.add_mutually_exclusive_group(required=True)
    grp.add_argument("--ticker", help="Resolve company name from the registry")
    grp.add_argument("--sponsor", help="Use this sponsor name directly")
    p_dt.add_argument("--registry", default=_DEFAULT_REGISTRY)
    p_dt.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR)
    p_dt.add_argument("--refresh", action="store_true")
    p_dt.add_argument("--cache-only", action="store_true")

    p_rt = sub.add_parser("route", help="Route detected leads to propose/review/exception")
    p_rt.add_argument("--registry", default=_DEFAULT_REGISTRY)
    p_rt.add_argument("--candidates", help="YAML list of {ticker, company_name} to route "
                                           "(default: self-audit the registry companies)")
    p_rt.add_argument("--enumerate", dest="enumerate_universe", action="store_true",
                      help="Enumerate candidates via ops/universe_builder liquidity screen")
    p_rt.add_argument("--max-tickers", type=int, default=None,
                      help="Limit universe seed tickers screened (with --enumerate)")
    p_rt.add_argument("--skip-clinical-check", action="store_true",
                      help="Skip the universe builder's Phase 2+ gate (routing does its own)")
    p_rt.add_argument("--min-mktcap", type=float, default=None, help="Min market cap $M")
    p_rt.add_argument("--max-mktcap", type=float, default=None, help="Max market cap $M")
    p_rt.add_argument("--limit", type=int, default=0, help="Only route the first N candidates")
    p_rt.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR)
    p_rt.add_argument("--refresh", action="store_true")
    p_rt.add_argument("--cache-only", action="store_true")
    p_rt.add_argument("--write-proposals", action="store_true",
                      help="Persist proposed/auto-added seeds (default: dry run, audit only)")
    p_rt.add_argument("--auto-add-high-confidence", action="store_true",
                      help="Reclassify high-confidence leads to auto_add (default off; still "
                           "requires --write-proposals to persist)")
    p_rt.add_argument("--seeds-auto", default=_DEFAULT_SEEDS_AUTO,
                      help="Staged seeds file; its tickers are excluded from re-proposal")
    p_rt.add_argument("--exclusions", default=_DEFAULT_EXCLUSIONS,
                      help="Exclusion ledger; rejected/acquired names are not re-proposed")
    p_rt.add_argument("--audit-out", default=_DEFAULT_AUDIT_OUT)
    p_rt.add_argument("--proposals-out", default=_DEFAULT_PROPOSALS_OUT)
    p_rt.add_argument("--format", choices=["text", "json"], default="text")

    for name, helptext in (
        ("approve", "Approve a proposed_seed → stage it into seeds_auto.yaml"),
        ("reject", "Reject a proposed_seed → add to the exclusion ledger"),
        ("defer", "Defer a proposed_seed → suppress until next enumeration"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--ticker", required=True)
        p.add_argument("--reviewer", default=None)
        p.add_argument("--rationale", default=None)
        p.add_argument("--db", default=_DEFAULT_DB)
        if name in ("approve", "reject"):
            p.add_argument("--exclusions", default=_DEFAULT_EXCLUSIONS)
        if name == "approve":
            p.add_argument("--registry", default=_DEFAULT_REGISTRY)
            p.add_argument("--seeds-auto", default=_DEFAULT_SEEDS_AUTO)
            p.add_argument("--proposals-out", default=_DEFAULT_PROPOSALS_OUT)
        if name == "reject":
            p.add_argument("--reason", default=None,
                           help="rejected | acquired | delisted | not_drug_developer | bad_data")

    args = parser.parse_args(argv)
    {
        "backtest": _cmd_backtest, "detect": _cmd_detect, "route": _cmd_route,
        "approve": _cmd_approve, "reject": _cmd_reject, "defer": _cmd_defer,
    }[args.command](args)


if __name__ == "__main__":
    main()

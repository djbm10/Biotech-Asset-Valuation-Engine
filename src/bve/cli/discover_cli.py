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


def _load_candidates(path: str | None, registry: str) -> tuple[list[CandidateCompany], set[str]]:
    """Candidates to route + the set of already-seeded tickers (for exclusion).

    With ``--candidates`` we route a supplied list of new names; without it we
    self-audit the registry's own companies (writes nothing, since all are
    seeded) so the decision logic — including the MRUS approved-vs-pivotal rule —
    can be inspected against known companies.
    """
    seeds = load_universe_registry(registry)
    existing = {s.ticker.upper() for s in seeds}
    if path:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
        rows = raw.get("candidates", []) if isinstance(raw, dict) else raw
        candidates = [CandidateCompany.model_validate(r) for r in rows]
    else:
        candidates = [CandidateCompany(ticker=s.ticker, company_name=s.company_name)
                      for s in seeds]
    return candidates, existing


def _cmd_route(args: argparse.Namespace) -> None:
    candidates, existing = _load_candidates(args.candidates, args.registry)
    if args.limit:
        candidates = candidates[: args.limit]
    fetch = _make_fetch(args.cache_dir, cache_only=args.cache_only, refresh=args.refresh)

    result = run_routing(
        candidates, fetch_fn=fetch, existing_tickers=existing,
        auto_add_high=args.auto_add_high_confidence,
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
    p_rt.add_argument("--limit", type=int, default=0, help="Only route the first N candidates")
    p_rt.add_argument("--cache-dir", default=_DEFAULT_CACHE_DIR)
    p_rt.add_argument("--refresh", action="store_true")
    p_rt.add_argument("--cache-only", action="store_true")
    p_rt.add_argument("--write-proposals", action="store_true",
                      help="Persist proposed/auto-added seeds (default: dry run, audit only)")
    p_rt.add_argument("--auto-add-high-confidence", action="store_true",
                      help="Reclassify high-confidence leads to auto_add (default off; still "
                           "requires --write-proposals to persist)")
    p_rt.add_argument("--audit-out", default=_DEFAULT_AUDIT_OUT)
    p_rt.add_argument("--proposals-out", default=_DEFAULT_PROPOSALS_OUT)
    p_rt.add_argument("--format", choices=["text", "json"], default="text")

    args = parser.parse_args(argv)
    {"backtest": _cmd_backtest, "detect": _cmd_detect, "route": _cmd_route}[args.command](args)


if __name__ == "__main__":
    main()

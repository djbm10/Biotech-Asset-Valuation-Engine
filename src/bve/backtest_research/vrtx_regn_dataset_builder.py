"""
vrtx_regn_dataset_builder — main dataset-building CLI entrypoint.

Orchestrates:
  1. Load deals from seed CSV
  2. For each verified deal, compute snapshot dates
  3. For each snapshot, build candidate universe (actual target + hard negatives)
  4. Build acquirer / target / asset snapshots
  5. Assemble feature store
  6. Write curated CSV outputs + rNPV YAML configs
  7. Write research_gaps.csv

Usage::

    python -m bve.backtest_research.vrtx_regn_dataset_builder \\
      --since 2010 \\
      --acquirers VRTX REGN \\
      --snapshot-days 365 180 90 30 \\
      --min-negatives 30 \\
      --output research/backtests/vrtx_regn_2010/curated
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path
from typing import Any, Optional


def build_dataset(
    acquirers: list[str],
    since_year: int,
    snapshot_days: list[int],
    min_negatives: int,
    max_negatives: int,
    output_dir: Path,
    raw_dir: Optional[Path],
    rnpv_config_dir: Optional[Path],
    include_unverified: bool,
    seed_csv: Optional[Path],
    dry_run: bool,
) -> dict[str, Any]:
    """
    Run the full dataset build and return a summary dict.
    """
    from bve.backtest_research.asset_snapshot_builder import AssetSnapshotBuilder
    from bve.backtest_research.candidate_universe_builder import CandidateUniverseBuilder
    from bve.backtest_research.deal_seed_loader import DealSeedLoader
    from bve.backtest_research.feature_store import FeatureStore
    from bve.backtest_research.rnpv_config_builder import RNPVConfigBuilder
    from bve.backtest_research.snapshot_dates import compute_snapshot_dates
    from bve.backtest_research.target_snapshot_builder import TargetSnapshotBuilder

    # 1. Load deals
    if seed_csv:
        loader = DealSeedLoader.from_csv(seed_csv)
    else:
        loader = DealSeedLoader.default()

    deals = loader.scoring_eligible(include_unverified=include_unverified)
    if acquirers:
        deals = [d for d in deals if d.acquirer_ticker.upper() in {a.upper() for a in acquirers}]

    min_date = date(since_year, 1, 1)

    print(f"Dataset builder: {len(deals)} eligible deal(s), {len(snapshot_days)} snapshot window(s)")

    # 2. Build snapshots + candidates
    all_candidates = []
    all_target_meta: dict[str, dict[str, Any]] = {}
    all_target_snapshots = []
    all_asset_snapshots = []
    deals_master: list[dict[str, Any]] = []

    tgt_builder = TargetSnapshotBuilder(raw_dir=raw_dir)
    ast_builder = AssetSnapshotBuilder()
    cand_builder = CandidateUniverseBuilder()
    rnpv_builder = RNPVConfigBuilder(output_dir=rnpv_config_dir)

    for deal in deals:
        snaps = compute_snapshot_dates(
            deal.announced_date,
            lookback_days=snapshot_days,
            deal_id=deal.deal_id,
            acquirer_ticker=deal.acquirer_ticker,
            target_ticker=deal.target_ticker,
            min_date=min_date,
        )

        deals_master.append({
            "deal_id": deal.deal_id,
            "acquirer_ticker": deal.acquirer_ticker,
            "target_ticker": deal.target_ticker,
            "deal_type": deal.deal_type,
            "announced_date": deal.announced_date.isoformat(),
            "deal_value_usd_millions": deal.deal_value_usd_millions,
            "lead_asset": deal.lead_asset,
            "therapeutic_area": deal.therapeutic_area,
            "verified": deal.verified,
            "n_snapshots": len(snaps),
        })

        # Store target metadata for feature store
        all_target_meta[deal.target_ticker] = {
            "lead_asset": deal.lead_asset,
            "therapeutic_area": deal.therapeutic_area,
            "indication": deal.indication,
            "modality": deal.lead_asset_modality,
        }

        for snap in snaps:
            snap_date = snap.snapshot_date

            # Candidate universe
            universe = cand_builder.build(
                deal=deal,
                snapshot_date=snap_date,
                days_before=snap.days_before,
                min_negatives=min_negatives,
                max_negatives=max_negatives,
            )
            all_candidates.extend(universe.candidates)

            # Target snapshot
            tgt_snap = tgt_builder.build(
                ticker=deal.target_ticker,
                lead_asset=deal.lead_asset,
                snapshot_date=snap_date,
                therapeutic_area=deal.therapeutic_area,
                indication=deal.indication,
                modality=deal.lead_asset_modality,
            )
            all_target_snapshots.append(tgt_snap)

            # Asset snapshot
            ast_snap = ast_builder.build(
                asset_name=deal.lead_asset,
                indication=deal.indication,
                snapshot_date=snap_date,
                modality=deal.lead_asset_modality,
                sponsor_ticker=deal.target_ticker,
                therapeutic_area=deal.therapeutic_area,
            )
            all_asset_snapshots.append(ast_snap)

            # rNPV configs (non-dry-run only)
            if not dry_run and rnpv_config_dir:
                try:
                    rnpv_builder.write_config(
                        ticker=deal.target_ticker,
                        snapshot_date=snap_date,
                        days_before=snap.days_before,
                        target_snap=tgt_snap,
                        asset_snap=ast_snap,
                    )
                except Exception as e:
                    print(f"  WARNING: rNPV config for {deal.target_ticker} failed: {e}",
                          file=sys.stderr)

    # 3. Build feature store
    store = FeatureStore(raw_dir=raw_dir)
    feature_rows = store.build_rows(
        candidates=all_candidates,
        target_metadata=all_target_meta,
    )

    # 4. Leakage audit
    audit = store.run_leakage_audit(feature_rows)
    print(f"Leakage audit: {len(audit.violations)} violation(s) across {len(feature_rows)} rows")

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(deals_master, output_dir / "vrtx_regn_deals_master.csv")
        _write_csv([s.to_dict() if hasattr(s, "to_dict") else s
                    for s in all_target_snapshots],
                   output_dir / "vrtx_regn_target_snapshots.csv")
        _write_csv(all_asset_snapshots, output_dir / "vrtx_regn_asset_snapshots.csv")
        _write_csv([vars(c) for c in all_candidates],
                   output_dir / "vrtx_regn_candidate_pairs.csv")
        store.write_csv(feature_rows, output_dir / "vrtx_regn_feature_store.csv")
        gaps = store.collect_gaps(feature_rows)
        _write_csv(gaps, output_dir / "vrtx_regn_research_gaps.csv")
        # Leakage audit CSV
        _write_csv(
            [{"row_index": v.row_index, "column": v.column,
              "violation_type": v.violation_type, "detail": v.detail}
             for v in audit.violations],
            output_dir / "vrtx_regn_leakage_audit_build.csv",
        )
        # CT.gov point-in-time audit
        _write_clinicaltrials_pit_audit(
            all_asset_snapshots, output_dir / "clinicaltrials_point_in_time_audit.csv"
        )
        print(f"Outputs written to: {output_dir}")
    else:
        print("Dry run — no files written.")

    return {
        "n_deals": len(deals),
        "n_snapshots": sum(d["n_snapshots"] for d in deals_master),
        "n_candidates": len(all_candidates),
        "n_feature_rows": len(feature_rows),
        "n_gaps": len(store.collect_gaps(feature_rows)),
        "leakage_violations": len(audit.violations),
    }


def _write_clinicaltrials_pit_audit(
    asset_snapshots: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """
    Apply TrialPhaseResolver to all asset snapshots and write an audit CSV.

    For each snapshot that sourced phase data from CT.gov (extraction_method ==
    ``ct_gov_api``), we create a TrialPhaseSource and call the resolver to
    determine whether the source date was pre-snapshot.

    Rows with ``near_snapshot_update_risk=True`` or ``is_trustworthy=False``
    should be prioritised for manual re-sourcing from SEC filings or press releases.
    """
    from datetime import date as _date

    from bve.backtest_research.trial_phase_resolver import (
        TrialPhaseResolver,
        TrialPhaseSource,
        TrialPhaseSourceType,
        write_clinicaltrials_pit_audit,
    )

    resolver = TrialPhaseResolver()
    results = []

    for snap in asset_snapshots:
        asset_id = f"{snap.get('sponsor_ticker', 'UNK')}:{snap.get('asset_name', 'unknown')}"
        raw_snapshot_date = snap.get("snapshot_date", "")
        raw_source_date = snap.get("source_published_date", "") or snap.get("data_as_of_date", "")
        extraction = snap.get("extraction_method", "")

        try:
            snap_dt = _date.fromisoformat(raw_snapshot_date)
        except (ValueError, TypeError):
            continue

        # Determine source type
        if extraction in ("sec_filing_text", "sec_filing"):
            src_type = TrialPhaseSourceType.SEC_FILING
        elif extraction in ("press_release", "company_website"):
            src_type = TrialPhaseSourceType.PRESS_RELEASE
        elif extraction == "ct_gov_api":
            src_type = TrialPhaseSourceType.CLINICALTRIALS_CURRENT
        else:
            src_type = TrialPhaseSourceType.UNKNOWN

        published_dt = None
        try:
            if raw_source_date:
                published_dt = _date.fromisoformat(raw_source_date)
        except (ValueError, TypeError):
            pass

        source = TrialPhaseSource(
            source_type=src_type,
            phase=snap.get("highest_phase"),
            published_date=published_dt,
            source_url=snap.get("source_url", ""),
            notes=f"extraction_method={extraction}",
        )

        result = resolver.resolve(
            asset_id=asset_id,
            snapshot_date=snap_dt,
            sources=[source],
        )
        results.append(result)

    if results:
        write_clinicaltrials_pit_audit(results, output_path)
        n_risky = sum(1 for r in results if r.near_snapshot_update_risk or not r.is_trustworthy)
        print(f"CT.gov PIT audit: {len(results)} assets checked, "
              f"{n_risky} flagged for re-sourcing → {output_path.name}")
    else:
        output_path.write_text(
            "asset_id,snapshot_date,resolved_phase,source_type,source_url,"
            "published_date,is_pre_snapshot,near_snapshot_update_risk,"
            "point_in_time_status,is_trustworthy\n",
            encoding="utf-8",
        )


def _write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve.backtest_research.vrtx_regn_dataset_builder",
        description="Build VRTX/REGN backtest dataset.",
    )
    parser.add_argument("--since", type=int, default=2010)
    parser.add_argument("--acquirers", nargs="+", default=["VRTX", "REGN"])
    parser.add_argument("--snapshot-days", nargs="+", type=int, default=[365, 180, 90, 30])
    parser.add_argument("--min-negatives", type=int, default=30)
    parser.add_argument("--max-negatives", type=int, default=50)
    parser.add_argument("--output", default="research/backtests/vrtx_regn_2010/curated")
    parser.add_argument("--raw-dir", default="research/backtests/vrtx_regn_2010/raw")
    parser.add_argument("--rnpv-config-dir", default="research/backtests/vrtx_regn_2010/rnpv_configs")
    parser.add_argument("--seed-csv", default=None)
    parser.add_argument("--include-unverified-deals", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    summary = build_dataset(
        acquirers=args.acquirers,
        since_year=args.since,
        snapshot_days=args.snapshot_days,
        min_negatives=args.min_negatives,
        max_negatives=args.max_negatives,
        output_dir=Path(args.output),
        raw_dir=Path(args.raw_dir) if args.raw_dir else None,
        rnpv_config_dir=Path(args.rnpv_config_dir) if args.rnpv_config_dir else None,
        include_unverified=args.include_unverified_deals,
        seed_csv=Path(args.seed_csv) if args.seed_csv else None,
        dry_run=args.dry_run,
    )
    print(f"Deals: {summary['n_deals']}")
    print(f"Snapshots: {summary['n_snapshots']}")
    print(f"Candidate pairs: {summary['n_candidates']}")
    print(f"Feature rows: {summary['n_feature_rows']}")
    print(f"Research gaps: {summary['n_gaps']}")
    if summary["leakage_violations"] > 0:
        print(f"ERROR: {summary['leakage_violations']} leakage violation(s) detected!",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

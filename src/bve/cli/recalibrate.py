"""
bve-recalibrate CLI — Rebuild CalibratedPOSModel from KnowledgeStore (Sprint 21).

Rebuilds the hierarchical Bayesian PoS model monthly (or on demand) from
all pos_predictions + pos_outcomes stored in the KnowledgeStore.

Prints a calibration report: bins, blend weights, base rates vs. industry priors.

Usage
-----
    bve-recalibrate                        # use default DB, print text report
    bve-recalibrate --db outputs/intelligence/ops.db
    bve-recalibrate --format json          # JSON output
    bve-recalibrate --out calibration.json # write to file
    bve-recalibrate --min-blend 0.20       # only show bins with blend_weight ≥ 0.20
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bve-recalibrate",
        description="Rebuild CalibratedPOSModel from KnowledgeStore and report calibration state.",
    )
    p.add_argument(
        "--db",
        default=None,
        metavar="PATH",
        help="KnowledgeStore SQLite path (default: outputs/intelligence/ops.db)",
    )
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    p.add_argument(
        "--out",
        default=None,
        metavar="PATH",
        help="Write output to file instead of stdout",
    )
    p.add_argument(
        "--min-blend",
        type=float,
        default=0.0,
        metavar="0.0-1.0",
        help="Only show bins with blend_weight >= MIN_BLEND (default: 0.0 = all bins)",
    )
    return p


def _render_text(model, min_blend: float = 0.0) -> str:
    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"CalibratedPOS Recalibration Report — {now}")
    lines.append(f"{'=' * 55}")
    lines.append(f"Total outcomes in DB : {model.n_outcomes}")
    lines.append(f"Calibrated bins      : {model.n_bins_calibrated}")
    lines.append("")

    bins = [b for b in model.all_bins() if b.blend_weight >= min_blend]
    if not bins:
        lines.append("No bins meet the minimum blend weight filter.")
        return "\n".join(lines)

    header = f"{'TA':<20} {'PHASE':<12} {'N':>5} {'SUCCESS':>8} {'POST':>7} {'PRIOR':>7} {'BLEND':>7} {'RATE':>7} {'W':>6}"
    lines.append(header)
    lines.append("-" * len(header))

    for b in bins:
        lines.append(
            f"{b.ta:<20} {b.phase:<12} {b.n_total:>5} "
            f"{b.n_success:>8} {b.posterior_mean:>7.3f} "
            f"{b.industry_prior:>7.3f} {b.blend_weight:>7.3f} "
            f"{b.blended_rate:>7.3f} "
            f"[{b.ci_lo:.3f},{b.ci_hi:.3f}]"
        )

    return "\n".join(lines)


def _render_json(model, min_blend: float = 0.0) -> str:
    bins = [b for b in model.all_bins() if b.blend_weight >= min_blend]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_outcomes": model.n_outcomes,
        "n_bins_calibrated": model.n_bins_calibrated,
        "bins": [
            {
                "ta": b.ta,
                "phase": b.phase,
                "n_total": b.n_total,
                "n_success": b.n_success,
                "n_failure": b.n_failure,
                "posterior_mean": b.posterior_mean,
                "industry_prior": b.industry_prior,
                "blend_weight": b.blend_weight,
                "blended_rate": b.blended_rate,
                "ci_lo": b.ci_lo,
                "ci_hi": b.ci_hi,
            }
            for b in bins
        ],
    }
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve DB path
    if args.db:
        db_path = Path(args.db)
    else:
        try:
            from bve.ops.weekly_runner import DB_PATH
            db_path = DB_PATH
        except Exception:
            db_path = Path("outputs/intelligence/ops.db")

    from bve.models.pos_calibrated import CalibratedPOSModel

    model = CalibratedPOSModel.from_store(db_path)

    if args.format == "json":
        output = _render_json(model, min_blend=args.min_blend)
    else:
        output = _render_text(model, min_blend=args.min_blend)

    if args.out:
        Path(args.out).write_text(output)
        print(f"Written to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()

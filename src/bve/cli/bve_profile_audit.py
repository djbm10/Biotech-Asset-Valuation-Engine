"""bve-profile-audit CLI: audit acquirer profile age and staleness.

Usage
-----
    bve-profile-audit
    bve-profile-audit --profiles research/mna/pipeline_gaps.yaml
    bve-profile-audit --output outputs/profile_audit.md
    bve-profile-audit --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bve-profile-audit",
        description="Audit acquirer profile age and staleness.",
    )
    parser.add_argument(
        "--profiles",
        default=None,
        help="Path to pipeline_gaps.yaml. Defaults to research/mna/pipeline_gaps.yaml.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path. If omitted, prints to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output JSON instead of Markdown.",
    )
    args = parser.parse_args(argv)

    print("[bve-profile-audit] Auditing acquirer profiles...", file=sys.stderr)

    from bve.refresh.profile_audit import audit_profiles_from_yaml, render_profile_audit

    result = audit_profiles_from_yaml(args.profiles)

    if result.has_stale_profiles():
        print(
            f"[bve-profile-audit] Warning: {result.n_stale} stale, "
            f"{result.n_critical} critical profiles found.",
            file=sys.stderr,
        )

    if args.as_json:
        rendered = json.dumps(result.to_dict(), indent=2, default=str)
    else:
        rendered = render_profile_audit(result)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[bve-profile-audit] Output written to {out_path}", file=sys.stderr)
    else:
        print(rendered)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

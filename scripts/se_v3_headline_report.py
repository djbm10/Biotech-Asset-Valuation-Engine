"""Score a paired v3 run against ``asset_qualification_tiered_evidence_v3.md`` §5.

Usage: ``python scripts/se_v3_headline_report.py <off_run_dir> <on_run_dir>``

Reports, in the order the acceptance bar asks for them: default-path non-assets, decisional
PASSes held by non-assets, real assets lost, human-PoC movement, comparator classification
counts, the ``qualification_reason`` distribution, and the top-10 shortlist.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

FROZEN_NEGATIVES = [
    "Placebo",
    "choice",
    "paper",
    "frontline",
    "bsAbs",
    "POD24",
    "ASCO 2023",
    "NEJM 2011",
    "WHO 2022",
    "PRISMA 2020",
    "IQR 124",
]

FROZEN_POSITIVES = [
    "HB2198",
    "AMG 420",
    "ALLO-715",
    "ABBV-383",
    "gemcitabine",
    "pomalidomide",
    "teclistamab",
    "pembrolizumab",
    "belantamab mafodotin",
]


class Run:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.result = json.loads((directory / "result.json").read_text())
        self.low_support = set(self.result["low_support_asset_ids"])
        self.assets = {a["asset_id"]: a for a in self.result["candidates"]}
        self.default_path = {
            asset_id: asset
            for asset_id, asset in self.assets.items()
            if asset_id not in self.low_support
        }
        self.poc = {
            fact["subject_id"]
            for fact in self.result.get("facts", [])
            if fact.get("fact_type") == "human_poc_present"
        }
        shortlist = directory / "shortlist.json"
        self.shortlist = (
            json.loads(shortlist.read_text())["entries"] if shortlist.exists() else []
        )

    def names(self, asset_ids) -> set[str]:
        return {(self.assets[i].get("canonical_name") or "").casefold() for i in asset_ids}

    def find(self, name: str):
        folded = name.casefold()
        return [
            asset
            for asset in self.assets.values()
            if (asset.get("canonical_name") or "").casefold() == folded
        ]


def _status(run: Run, name: str) -> str:
    matches = run.find(name)
    if not matches:
        return "absent"
    parts = []
    for asset in matches:
        where = "default" if asset["asset_id"] not in run.low_support else "review"
        reason = asset.get("qualification_reason") or "-"
        poc = " POC" if asset["asset_id"] in run.poc else ""
        parts.append(f"{where}/{reason}{poc}")
    return ", ".join(parts)


def main() -> int:
    off, on = Run(Path(sys.argv[1])), Run(Path(sys.argv[2]))

    print(f"candidates  off={len(off.assets)}  on={len(on.assets)}")
    print(f"default path off={len(off.default_path)}  on={len(on.default_path)}")

    print("\n1/2. frozen negatives (must be neither default-path nor holding a PASS)")
    for name in FROZEN_NEGATIVES:
        print(f"  {name:<16} off: {_status(off, name):<44} on: {_status(on, name)}")

    print("\n3. frozen positives (must survive)")
    for name in FROZEN_POSITIVES:
        print(f"  {name:<22} off: {_status(off, name):<44} on: {_status(on, name)}")

    lost = off.names(off.default_path) - on.names(on.default_path)
    gained = on.names(on.default_path) - off.names(off.default_path)
    print(f"\n3b. default-path names lost: {len(lost)}  gained: {len(gained)}")
    for name in sorted(lost):
        print("   -", name)
    for name in sorted(gained):
        print("   +", name)

    print("\n4. human_poc")
    poc_off, poc_on = off.names(off.poc), on.names(on.poc)
    print(f"  off={len(poc_off)} on={len(poc_on)}")
    for name in sorted(poc_off - poc_on):
        print("   - lost:", name)
    for name in sorted(poc_on - poc_off):
        print("   + gained:", name)

    print("\n5. comparator classification (on)")
    totals = collections.Counter()
    comparator_only = []
    for asset in on.assets.values():
        for key in ("comparator_observations", "therapeutic_observations", "unknown_observations"):
            totals[key] += asset.get(key, 0) or 0
        if (asset.get("comparator_observations") or 0) > 0 and not asset.get(
            "therapeutic_observations"
        ):
            comparator_only.append(asset.get("canonical_name"))
    print(" ", dict(totals))
    print(f"  comparator-only assets: {len(comparator_only)}")
    for name in sorted(filter(None, comparator_only))[:25]:
        print("   ", name)

    print("\n6. qualification_reason distribution (on, default path)")
    reasons = collections.Counter(
        asset.get("qualification_reason") for asset in on.default_path.values()
    )
    for reason, count in reasons.most_common():
        print(f"  {str(reason):<32} {count}")
    anonymous = [r for r in reasons if r is None]
    print(f"  ANONYMOUS ADMISSIONS: {reasons[None] if anonymous else 0}  (bar §5.1 requires 0)")

    print("\n7. top-10 shortlist")
    for index, entry in enumerate(on.shortlist[:10], start=1):
        print(f"  {index:>2}. {entry.get('asset_name') or entry.get('name')}  [{entry.get('section')}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Mechanical target draw for the second blinded S&E benchmark (see PROTOCOL.md here).

    python research/se_blinded_pilot_v1/target_draw_v2/draw_target.py --pool-out pool.json \
        [--seed-hex HEX]

Without --seed-hex it only writes the candidate pool (run before the seed exists).
With it, it draws: sha256(seed_hex + ":" + symbol) is computed for every pool target, and
the target with the smallest digest is selected. Deterministic, no sort-order freedom.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EDGES = REPO / "data/se/ontology/current/edges.jsonl"
MIN_DRUGS = 5
#: Named exclusions: every target evaluated or used as a development example so far.
NAMED_EXCLUSIONS = frozenset({
    "PDCD1", "CD274", "CD19", "TNFRSF17", "SLC6A2", "HRH1", "HTR2A", "CHRM1", "GUCY2C",
    "CD3E", "MS4A1",
})
#: Human-written reports and problem files; bulk JSON ontology surveys are not reports.
REPORT_GLOBS = ("research/**/*.md", "research/**/*.yaml", "research/**/*.yml",
                "docs/**/*.md", "docs/**/*.yaml", "docs/**/*.yml")


def drugs_per_target() -> dict[str, set[str]]:
    drugs: dict[str, set[str]] = defaultdict(set)
    for line in EDGES.read_text().splitlines():
        edge = json.loads(line)
        if edge["relationship_type"] == "DIRECT_TARGET" and edge["status"] == "USABLE":
            drugs[edge["canonical_target_id"].removeprefix("TARGET:")].add(edge["canonical_drug_id"])
    return drugs


def report_text() -> str:
    parts = []
    for pattern in REPORT_GLOBS:
        for path in sorted(REPO.glob(pattern)):
            if "target_draw_v2" in path.parts:
                continue  # this protocol's own files would otherwise exclude everything
            parts.append(path.read_text(errors="replace"))
    return "\n".join(parts)


def resolves(symbol: str) -> bool:
    """The engine's own target resolver accepts the symbol unambiguously."""

    from bve.se.ontology.resolver import ResolutionStatus
    from bve.se.ontology.targets import resolve_target

    resolution = resolve_target(symbol)
    return resolution is not None and resolution.status is ResolutionStatus.RESOLVED


def pool() -> dict:
    drugs = drugs_per_target()
    text = report_text()
    eligible, excluded = {}, {}
    for symbol in sorted(drugs):
        n = len(drugs[symbol])
        if n < MIN_DRUGS:
            continue
        if symbol in NAMED_EXCLUSIONS:
            excluded[symbol] = "named exclusion"
        elif re.search(rf"(?<![A-Za-z0-9]){re.escape(symbol)}(?![A-Za-z0-9])", text):
            excluded[symbol] = "symbol appears in a repository report or problem file"
        elif not resolves(symbol):
            excluded[symbol] = "does not resolve unambiguously in the engine ontology"
        else:
            eligible[symbol] = n
    return {"edges_file_sha256": hashlib.sha256(EDGES.read_bytes()).hexdigest(),
            "min_direct_target_drugs": MIN_DRUGS, "eligible": eligible, "excluded": excluded}


def draw(eligible: dict[str, int], seed_hex: str) -> list[tuple[str, str]]:
    return sorted((hashlib.sha256(f"{seed_hex}:{s}".encode()).hexdigest(), s) for s in eligible)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-out", required=True)
    ap.add_argument("--seed-hex")
    args = ap.parse_args()
    result = pool()
    if args.seed_hex:
        ranking = draw(result["eligible"], args.seed_hex)
        result["seed_hex"] = args.seed_hex
        result["selected"] = ranking[0][1]
        result["first_five"] = [s for _, s in ranking[:5]]
    Path(args.pool_out).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("eligible", "excluded")} |
                     {"eligible": len(result["eligible"]), "excluded": len(result["excluded"])}))


if __name__ == "__main__":
    main()

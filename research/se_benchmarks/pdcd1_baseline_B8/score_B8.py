"""Score a B8-lineage PDCD1 run against the frozen M8 / V1 / V2 benchmark.

The denominators, the subject sets and the adjudication rules are read from the frozen
artifacts and are never recomputed here. What this script adds over the B6-era
``denominator_members.py`` + ``precision_negatives.py`` pair is the distinction B8 exists
to measure: *surfaced* is not *asserted to target PDCD1*. A chemotherapy backbone found in
a PD-1 combination trial is a legitimate discovery result; the same drug carrying a PDCD1
assertion is a real precision failure. Those are counted separately and never summed.

Matching rules are deliberately identical to the B6 scorer so the numbers stay comparable:
a gold entry counts as identified when its canonical name or one of its aliases equals a
normalized identity mention, and as reachable when a word-boundary match for one of those
names occurs in the text of an admitted corpus snapshot.

Usage:
    python score_B8.py RESULT_JSON CUSTODY_ROOT OUT_JSON
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
import sys

B = pathlib.Path("/home/djmann/staging/pdcd1_baseline")
V1 = pathlib.Path("/home/djmann/staging/pdcd1_adjudication_v1")
V2DIR = pathlib.Path(
    "/home/djmann/projects/bve-b8/research/se_benchmarks/pdcd1_annotation_v2"
)
TARGET = "PDCD1"
#: The pipeline namespaces canonical target ids. Both spellings are accepted so the
#: scorer reads the run's own verdict rather than silently scoring every asset as
#: NO_ASSERTION, which is what comparing the bare gene symbol did.
TARGET_IDS = frozenset({TARGET, f"TARGET:{TARGET}"})

#: Same-pathway, different-gene drugs. The sharpest available precision trap: a run that
#: cannot tell PDCD1 from CD274 will assert these.
PDL1 = (
    "durvalumab", "atezolizumab", "avelumab", "adebrelimab", "sugemalimab", "imfinzi",
    "tecentriq", "bavencio", "pumitamig", "bnt327", "socazolimab", "envafolimab",
)


def _jsonl(path: pathlib.Path) -> dict:
    return {json.loads(line)["benchmark_id"]: json.loads(line) for line in open(path)}


def _names(row: dict) -> list[str]:
    return [row["canonical_asset"]] + [
        a for a in (row["aliases"] or "").split("|") if a.strip()
    ]


def load_benchmark() -> dict:
    """The frozen benchmark: 224 canonical candidates, V1 roles, V2 adjudication."""

    gold = {
        row["benchmark_id"]: row
        for row in csv.DictReader(open(B / "pdcd1_reference_universe_m8v2.csv"))
    }
    roles = _jsonl(V1 / "gold_entry_roles.jsonl")
    v2 = _jsonl(V2DIR / "v2_annotation_layer.jsonl")
    assert len(roles) == 224, f"strict M8 denominator moved: {len(roles)}"

    v1_conf = {
        b for b, r in roles.items()
        if r["entity_role"] == "ASSET" and r["target_relevance"] == "PDCD1_MATCH"
    }
    v2_new = {b for b, r in v2.items() if r["target_relevance_v2"] == "PDCD1_MATCH"}
    confirmed = v1_conf | v2_new
    negatives = {
        b for b, r in roles.items()
        if r["entity_role"] == "ASSET" and r["target_relevance"] == "NON_PDCD1"
    } | {b for b, r in v2.items() if r["target_relevance_v2"] == "NON_PDCD1"}
    uncertain = {b for b, r in v2.items() if r["target_relevance_v2"] == "UNCERTAIN_V2"}

    assert len(confirmed) == 40, f"V2 confirmed PDCD1 denominator moved: {len(confirmed)}"
    assert len(negatives) == 133, f"confirmed negative set moved: {len(negatives)}"
    return {
        "gold": gold, "roles": roles, "v2": v2,
        "v1_confirmed": v1_conf, "confirmed": confirmed,
        "negatives": negatives, "uncertain": uncertain,
    }


def corpus_text(custody_root: pathlib.Path) -> dict[str, str]:
    """Admitted snapshot text, keyed by record id, read from the sealed ledger.

    Reachability is measured over what the run was *allowed to see*: withheld
    (cutoff-excluded) records are on disk but were never handed to interpretation, so
    counting them would credit the run with evidence it refused to look at.
    """

    texts: dict[str, str] = {}
    for line in open(custody_root / "acquisition_ledger.jsonl"):
        entry = json.loads(line)
        if not entry.get("admitted", True):
            continue
        path = entry.get("snapshot_path")
        if not path or not pathlib.Path(path).is_file():
            continue
        texts[f"{entry['source']}|{entry['record_id']}"] = (
            pathlib.Path(path).read_text().casefold()
        )
    return texts


def index_assets(result: dict) -> tuple[dict, dict]:
    """Map every normalized name the run produced to the asset(s) carrying it."""

    mentions = {
        m["normalized_asset_name"].casefold()
        for m in result["identity_mentions"]
        if m.get("normalized_asset_name")
    }
    by_name: dict[str, list[dict]] = {}
    for asset in result["candidates"]:
        for name in [asset["canonical_name"], *asset.get("aliases", [])]:
            if name and name.strip():
                by_name.setdefault(name.casefold(), []).append(asset)
    return mentions, by_name


def assertion_status(assets: list[dict]) -> str:
    """The run's own verdict on whether these assets target PDCD1.

    Worst-case folding is deliberate: if any merged spelling carries a confirmed PDCD1
    assertion, the run has asserted PDCD1, and that is what precision must be judged on.
    """

    statuses = []
    for asset in assets:
        for a in asset.get("target_assertions", []):
            if a["canonical_target_id"] in TARGET_IDS:
                statuses.append(a["status"])
        if TARGET_IDS & set(asset.get("target_ids") or []) and not statuses:
            statuses.append("CONFIRMED_TARGET")
    for rank in ("CONFIRMED_TARGET", "CONFLICTING", "CONFIRMED_OTHER_TARGET", "UNRESOLVED"):
        if rank in statuses:
            return rank
    return "NO_ASSERTION"


def score(result_path: str, custody_root: str, out_path: str) -> dict:
    result = json.load(open(result_path))
    bench = load_benchmark()
    gold = bench["gold"]
    texts = corpus_text(pathlib.Path(custody_root))
    mentions, by_name = index_assets(result)

    # B6 measured reachability over CT.gov alone. Both are reported: the full admitted
    # corpus is the honest answer for this run, and the CT.gov-only figure is what the
    # earlier baselines can be compared against without changing their meaning.
    ctgov_texts = {k: v for k, v in texts.items() if k.startswith("clinicaltrials_gov|")}

    reachable: set[str] = set()
    reachable_ctgov: set[str] = set()
    identified: set[str] = set()
    verdict: dict[str, str] = {}
    matched_assets: dict[str, list[dict]] = {}

    for bid, row in gold.items():
        names = [n for n in _names(row) if n.strip()]
        patterns = [re.compile(r"\b" + re.escape(n.casefold()) + r"\b") for n in names]
        if any(p.search(text) for text in texts.values() for p in patterns):
            reachable.add(bid)
        if any(p.search(text) for text in ctgov_texts.values() for p in patterns):
            reachable_ctgov.add(bid)
        hits = [a for n in names for a in by_name.get(n.casefold(), [])]
        if any(n.casefold() in mentions for n in names):
            identified.add(bid)
        if hits:
            matched_assets[bid] = hits
            verdict[bid] = assertion_status(hits)

    confirmed, negatives = bench["confirmed"], bench["negatives"]
    uncertain = bench["uncertain"]

    def rate(num: int, den: int) -> float:
        return num / den if den else float("nan")

    conf_ident = confirmed & identified
    conf_reach = confirmed & reachable
    conf_pdcd1 = {b for b in conf_ident if verdict.get(b) == "CONFIRMED_TARGET"}
    neg_surfaced = negatives & identified
    neg_asserted = {b for b in neg_surfaced if verdict.get(b) == "CONFIRMED_TARGET"}
    neg_other = {b for b in neg_surfaced if verdict.get(b) == "CONFIRMED_OTHER_TARGET"}
    traps = {
        b for b in neg_surfaced
        if any(k in gold[b]["canonical_asset"].casefold() for k in PDL1)
    }

    report = {
        "recall": {
            "strict_M8": {
                "identified": len(identified), "denominator": 224,
                "recall": rate(len(identified), 224),
                "note": "historical continuity only; not the product metric",
            },
            "v2_confirmed_pdcd1_discovery": {
                "identified": len(conf_reach), "denominator": len(confirmed),
                "recall": rate(len(conf_reach), len(confirmed)),
            },
            "v2_confirmed_pdcd1_identification": {
                "identified": len(conf_ident), "denominator": len(confirmed),
                "recall": rate(len(conf_ident), len(confirmed)),
            },
            "v2_confirmed_pdcd1_discovery_ctgov_only": {
                "identified": len(confirmed & reachable_ctgov),
                "denominator": len(confirmed),
                "recall": rate(len(confirmed & reachable_ctgov), len(confirmed)),
                "note": "comparable with the B6-era CT.gov-only reachability figure",
            },
            "reachable_v2_confirmed_pdcd1": {
                "identified": len(conf_ident & reachable), "denominator": len(conf_reach),
                "recall": rate(len(conf_ident & reachable), len(conf_reach)),
            },
            "direct_pdcd1_target_confirmation_coverage": {
                "confirmed_target": len(conf_pdcd1), "denominator": len(confirmed),
                "coverage": rate(len(conf_pdcd1), len(confirmed)),
                "of_identified": rate(len(conf_pdcd1), len(conf_ident)),
            },
        },
        "precision": {
            "confirmed_negatives": len(negatives),
            "surfaced": len(neg_surfaced),
            "surfaced_rate": rate(len(neg_surfaced), len(negatives)),
            "falsely_asserted_pdcd1": len(neg_asserted),
            "false_assertion_rate": rate(len(neg_asserted), len(negatives)),
            "confirmed_other_target": len(neg_other),
            "pdl1_traps_surfaced": sorted(gold[b]["canonical_asset"] for b in traps),
            "pdl1_traps_falsely_asserted": sorted(
                gold[b]["canonical_asset"] for b in traps & neg_asserted
            ),
            "benign_co_occurrence": len(neg_surfaced - neg_asserted),
            "note": (
                "surfaced is not asserted: a backbone or comparator drug appearing in a "
                "PD-1 combination trial is a correct discovery result. Only "
                "falsely_asserted_pdcd1 is a target-attribution error."
            ),
        },
        "uncertainty": {
            "still_uncertain_v2": len(uncertain),
            "uncertain_identified": len(uncertain & identified),
            "unresolved_assertions": sum(
                1 for v in verdict.values() if v == "UNRESOLVED"
            ),
            "conflicting_assertions": sum(
                1 for v in verdict.values() if v == "CONFLICTING"
            ),
            # The queue holds one item per unmet gate requirement, so it is many times
            # longer than the asset list. The reviewable population is the distinct
            # subjects behind those items.
            "review_queue_items": len(result.get("review_queue", [])),
            "review_queue": len(
                {item["subject_id"] for item in result.get("review_queue", [])}
            ),
            "assets_total": len(result["candidates"]),
            "review_fraction": rate(
                len({item["subject_id"] for item in result.get("review_queue", [])}),
                len(result["candidates"]),
            ),
            "residual_interval": [
                rate(len(conf_ident), len(confirmed | uncertain)),
                rate(len(conf_ident), len(confirmed)),
            ],
        },
        "misses": [],
        "sets": {
            "confirmed_identified": sorted(conf_ident),
            "confirmed_missed": sorted(confirmed - conf_ident),
            "confirmed_asserted_pdcd1": sorted(conf_pdcd1),
            "negatives_falsely_asserted": sorted(
                gold[b]["canonical_asset"] for b in neg_asserted
            ),
        },
    }

    for bid in sorted(confirmed - conf_ident):
        row = gold[bid]
        reached = bid in reachable
        report["misses"].append({
            "benchmark_id": bid,
            "asset": row["canonical_asset"],
            "acquisition_reached": reached,
            "document_reached": reached,
            "asset_extracted": bid in matched_assets,
            "identity_resolved": False,
            "target_attribution": verdict.get(bid, "NOT_REACHED"),
            "first_failure_boundary": (
                "ACQUISITION" if not reached
                else "IDENTITY" if bid not in matched_assets
                else "IDENTITY_NORMALIZATION"
            ),
            "reason": (
                "no admitted corpus record names this asset" if not reached
                else "present in the corpus but never extracted as a named asset"
                if bid not in matched_assets
                else "extracted under a spelling that does not normalize to the gold name"
            ),
        })

    manifest = result["run_manifest"]
    report["sources"] = {
        "status": manifest.get("source_status", {}),
        "run_status": manifest.get("status"),
        "fatal_reasons": manifest.get("fatal_reasons", []),
        "incomplete_reasons": manifest.get("incomplete_reasons", []),
    }
    json.dump(report, open(out_path, "w"), indent=1)
    return report


def main() -> None:
    report = score(sys.argv[1], sys.argv[2], sys.argv[3])
    r = report["recall"]
    print(f"{'metric':52} {'n':>7} {'denom':>7} {'rate':>8}")
    for key in (
        "strict_M8", "v2_confirmed_pdcd1_discovery",
        "v2_confirmed_pdcd1_identification", "reachable_v2_confirmed_pdcd1",
    ):
        row = r[key]
        print(f"{key:52} {row['identified']:>7} {row['denominator']:>7} {row['recall']:>8.1%}")
    cov = r["direct_pdcd1_target_confirmation_coverage"]
    print(f"{'direct PDCD1 target confirmation':52} {cov['confirmed_target']:>7} "
          f"{cov['denominator']:>7} {cov['coverage']:>8.1%}")
    p = report["precision"]
    print(f"\nconfirmed negatives: {p['confirmed_negatives']}   surfaced: {p['surfaced']} "
          f"({p['surfaced_rate']:.1%})   falsely asserted PDCD1: "
          f"{p['falsely_asserted_pdcd1']} ({p['false_assertion_rate']:.2%})")
    print(f"PD-L1 traps surfaced: {len(p['pdl1_traps_surfaced'])}   "
          f"falsely asserted: {len(p['pdl1_traps_falsely_asserted'])}")
    u = report["uncertainty"]
    print(f"\nreview queue: {u['review_queue']}/{u['assets_total']} "
          f"({u['review_fraction']:.1%})   UNRESOLVED: {u['unresolved_assertions']}   "
          f"CONFLICTING: {u['conflicting_assertions']}")
    print(f"residual interval: [{u['residual_interval'][0]:.1%}, "
          f"{u['residual_interval'][1]:.1%}]")
    print(f"\nmisses: {len(report['misses'])}")
    for m in report["misses"]:
        print(f"  {m['asset'][:44]:44} {m['first_failure_boundary']:22} {m['reason']}")


if __name__ == "__main__":
    main()

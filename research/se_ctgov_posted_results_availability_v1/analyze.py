"""Offline analysis of frozen census + adjudication (prereg eefd8a2). Verdict derived by `decide`."""

import argparse
import copy
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

STUDY = Path(__file__).resolve().parent
RAW = Path.home() / "se_runs/ctgov_posted_results_availability_v1"
AS_OF = "2026-09-24"
RESOLVED = {"NUMERICAL_OUTCOME_WITH_RESOLVED_PRODUCT", "POTENTIAL_HUMAN_EFFICACY_EVIDENCE"}
POTENTIAL = "POTENTIAL_HUMAN_EFFICACY_EVIDENCE"
EXPECTED_SAMPLE = 36


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def stratum(phases):
    p = set(phases or [])
    return (
        "LATE"
        if p & {"PHASE3", "PHASE4"}
        else "PHASE2"
        if "PHASE2" in p
        else ("EARLY" if p & {"PHASE1", "EARLY_PHASE1"} else "OTHER_NA")
    )


def posted_vs_asof(date):
    if not date:
        return "NO_DATE"
    return "POST_AS_OF" if date[:10] > AS_OF else "POSTED_BEFORE_AS_OF_CONTENT_UNVERIFIED"


def decide(census, labels, packets):
    retrievable = len(census["rows"])
    with_results = sum(r["has_results"] for r in census["rows"].values())
    source = with_results / max(retrievable, 1) >= 0.10 and with_results >= 50
    by_pid = {p["packet_id"]: p for p in packets}
    lab = {x["packet_id"]: x for x in labels}
    assert set(lab) == set(by_pid), "unregistered sample change"
    assert len({p["nct"] for p in packets}) == EXPECTED_SAMPLE, "unregistered sample change"
    resolved_studies = {
        by_pid[i]["nct"]
        for i, x in lab.items()
        if x["class"] in RESOLVED and by_pid[i]["stratum"] != "NEGATIVE_CONTROL"
    }
    potential_studies = {
        by_pid[i]["nct"]
        for i, x in lab.items()
        if x["class"] == POTENTIAL and by_pid[i]["stratum"] != "NEGATIVE_CONTROL"
    }
    neg_potential = [
        i
        for i, x in lab.items()
        if x["class"] == POTENTIAL and by_pid[i]["stratum"] == "NEGATIVE_CONTROL"
    ]
    neg_wrong = [
        i
        for i, x in lab.items()
        if by_pid[i]["stratum"] == "NEGATIVE_CONTROL"
        and not by_pid[i]["results_present"]
        and x["class"] != "NO_POSTED_RESULTS"
    ]
    sampled = {p["nct"] for p in packets if p["stratum"] != "NEGATIVE_CONTROL"}
    attribution = len(resolved_studies) >= 8 and not neg_potential and not neg_wrong
    lo, hi = wilson(len(potential_studies), len(sampled))
    impl = source and attribution and len(potential_studies) >= 5 and lo >= 0.15
    verdict = "JUSTIFIED" if impl else ("LIMITED" if source else "STOP")
    return {
        "SOURCE_AVAILABLE": source,
        "ATTRIBUTION_FEASIBLE": attribution,
        "IMPLEMENTATION_DESIGN_JUSTIFIED": impl,
        "verdict": verdict,
        "retrievable": retrievable,
        "with_results": with_results,
        "resolved_studies": len(resolved_studies),
        "potential_studies": len(potential_studies),
        "sampled_results_studies": len(sampled),
        "potential_wilson95": [lo, hi],
        "negative_control_violations": neg_potential + neg_wrong,
    }


def selftest(census, labels, packets):
    good_l = copy.deepcopy(labels)
    for x in good_l:
        p = next(q for q in packets if q["packet_id"] == x["packet_id"])
        x["class"] = "NO_POSTED_RESULTS" if not p["results_present"] else POTENTIAL
    out = {"valid": decide(census, good_l, packets)["verdict"]}
    neg = copy.deepcopy(good_l)
    nid = next(p["packet_id"] for p in packets if p["stratum"] == "NEGATIVE_CONTROL")
    next(x for x in neg if x["packet_id"] == nid)["class"] = POTENTIAL
    out["false_attribution_on_negative"] = decide(census, neg, packets)["ATTRIBUTION_FEASIBLE"]
    nonef = copy.deepcopy(good_l)
    for x in nonef:
        if x["class"] == POTENTIAL:
            x["class"] = "NON_EFFICACY_OUTCOME"
    out["all_non_efficacy"] = decide(census, nonef, packets)["verdict"]
    missing = copy.deepcopy(census)
    for r in missing["rows"].values():
        r["has_results"] = False
    out["missing_results"] = decide(missing, good_l, packets)["verdict"]
    try:
        decide(census, good_l[:-1], packets)
        out["unregistered_sample_change"] = "NOT_DETECTED"
    except AssertionError:
        out["unregistered_sample_change"] = "DETECTED"
    out["post_as_of_classified"] = posted_vs_asof("2026-10-01")
    assert out == {
        "valid": "JUSTIFIED",
        "false_attribution_on_negative": False,
        "all_non_efficacy": "LIMITED",
        "missing_results": "STOP",
        "unregistered_sample_change": "DETECTED",
        "post_as_of_classified": "POST_AS_OF",
    }, out
    return out


def build(out):
    for line in (STUDY / "raw_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(path) == sha, path
    rows = json.loads((STUDY / "census_rows.json").read_text())
    cohort = json.loads((STUDY / "cohort.json").read_text())
    census = {"rows": rows}
    packets = json.loads((STUDY / "packets.json").read_text())
    labels = json.loads((STUDY / "adjudication.json").read_text())["labels"]
    dec = decide(census, labels, packets)
    missing = sorted(set(cohort["cohort"]) - set(rows))
    withr = [r for r in rows.values() if r["has_results"]]

    def by(f):
        return {
            k: {
                "n": v,
                "with_results": sum(1 for r in rows.values() if f(r) == k and r["has_results"]),
            }
            for k, v in sorted(Counter(f(r) for r in rows.values()).items())
        }

    pools = cohort["source_pools"]
    summary = {
        **dec,
        "selftest": selftest(census, labels, packets),
        "api_version": json.loads((RAW / "census/version.json").read_text()),
        "cohort": len(cohort["cohort"]),
        "missing_from_api": missing,
        "results_fraction": round(len(withr) / max(len(rows), 1), 4),
        "results_wilson95": wilson(len(withr), len(rows)),
        "by_phase_stratum": by(lambda r: stratum(r["phases"])),
        "by_status": by(lambda r: r["status"]),
        "by_source_pool": by(lambda r: "+".join(pools.get(r["nct"], []))),
        "as_of_split": dict(Counter(posted_vs_asof(r["results_first_posted"]) for r in withr)),
        "class_counts": dict(Counter(x["class"] for x in labels)),
        "design_counts": dict(Counter(x.get("design") for x in labels)),
        "flag_counts": dict(Counter(f for x in labels for f in x.get("flags") or [])),
        "potential_items": [
            {
                **x,
                "stratum": next(p["stratum"] for p in packets if p["packet_id"] == x["packet_id"]),
                "results_first_posted": rows.get(x["nct"], {}).get("results_first_posted"),
            }
            for x in labels
            if x["class"] == POTENTIAL
        ],
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(canonical(summary) + "\n")
    (out / "hashes.json").write_text(
        canonical({"summary.json": digest(out / "summary.json")}) + "\n"
    )
    print(
        canonical(
            {
                k: summary[k]
                for k in (
                    "verdict",
                    "SOURCE_AVAILABLE",
                    "ATTRIBUTION_FEASIBLE",
                    "IMPLEMENTATION_DESIGN_JUSTIFIED",
                    "with_results",
                    "retrievable",
                    "resolved_studies",
                    "potential_studies",
                    "potential_wilson95",
                )
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)

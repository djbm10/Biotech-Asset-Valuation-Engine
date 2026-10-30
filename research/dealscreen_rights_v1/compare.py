"""Compare baseline vs after screening.json: AC8 (science unchanged) and AC13 (transaction view). Usage:
python compare.py BASELINE.json AFTER.json OUT.csv"""
import csv
import json
import sys

base = {s["asset_id"]: s for s in json.load(open(sys.argv[1]))["screens"]}
after = {s["asset_id"]: s for s in json.load(open(sys.argv[2]))["screens"]}
sci = ("disposition", "rank", "decisions", "machine_recommendation")
changed = [a for a in base if any(base[a][k] != after[a][k] for k in sci)]
print(f"AC8 scientific fields changed: {len(changed)} of {len(base)}")
with open(sys.argv[3], "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["program", "disposition", "sci_rank", "base_tier", "base_txn_rank", "new_tier", "new_txn_rank",
                "rights_position", "holder_per_evidence", "stale", "reasons", "questions", "evidence_rows"])
    for a, s in sorted(after.items(), key=lambda kv: (kv[1]["disposition"], kv[1]["transaction_rank"] or 99,
                                                       kv[1]["rank"] or 99)):
        t = s["transaction"]
        w.writerow([s["program_name"], s["disposition"], s["rank"], base[a]["transaction"]["tier"],
                    base[a].get("transaction_rank"), t["tier"], s.get("transaction_rank"), t["rights_position"],
                    t["rights_holder_per_evidence"], t["stale"], " | ".join(t["reasons"]),
                    " | ".join(t["diligence_questions"]), ";".join(str(e["row"]) for e in t["evidence"])])

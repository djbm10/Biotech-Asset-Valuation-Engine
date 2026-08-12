"""Builds the Milestone 4 authority_research_subject_ledger and
research-question ledger strictly from the finalized Milestone 3 snapshot's
targeted/forensic review queues.

Pure, deterministic, no network I/O. Does not add any subject outside the
Milestone 3 review-queue universe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

MILESTONE3_SNAPSHOT_ID = "f5dd19d08deb59a75232d3bc"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def build_universe(m3_snapshot_dir: Path) -> dict:
    targeted = load_jsonl(m3_snapshot_dir / "triage" / "targeted_review_queue.jsonl")
    forensic = load_jsonl(m3_snapshot_dir / "triage" / "forensic_review_queue.jsonl")

    occurrence_to_nct: dict[str, str] = {}
    occurrence_to_field_class: dict[str, str] = {}
    with (m3_snapshot_dir / "normalized" / "candidate_bearing_occurrence_ledger.jsonl").open() as f:
        for line in f:
            row = json.loads(line)
            occurrence_to_nct[row["occurrence_id"]] = row["nct_id"]
            occurrence_to_field_class[row["occurrence_id"]] = row["field_class"]

    occurrence_to_frozen_row: dict[str, list[str]] = {}
    for row in load_jsonl(m3_snapshot_dir / "extracted" / "frozen_row_evidence_bindings.jsonl"):
        for occ_id in row["evidence_occurrence_ids"]:
            occurrence_to_frozen_row.setdefault(occ_id, []).append(row["frozen_row_id"])

    # queue_key -> merged queue entry (dedupe across targeted+forensic; a
    # subject appearing in both keeps the union of occurrence_ids/reasons).
    merged: dict[str, dict] = {}
    for source_queue, entries in (("targeted_review_queue", targeted), ("forensic_review_queue", forensic)):
        for entry in entries:
            key = entry["unique_string_key"]
            slot = merged.setdefault(
                key,
                {
                    "unique_string_key": key,
                    "occurrence_ids": set(),
                    "reasons": set(),
                    "categories": set(),
                    "source_queues": set(),
                },
            )
            slot["occurrence_ids"].update(entry["occurrence_ids"])
            slot["reasons"].add(entry["reason"])
            slot["categories"].add(entry["triage_category"])
            slot["source_queues"].add(source_queue)

    subjects = []
    questions = []
    for key in sorted(merged):
        slot = merged[key]
        occurrence_ids = sorted(slot["occurrence_ids"])
        nct_ids = sorted({occurrence_to_nct[o] for o in occurrence_ids if o in occurrence_to_nct})
        frozen_row_ids = sorted(
            {fr for o in occurrence_ids for fr in occurrence_to_frozen_row.get(o, [])}
        )
        reasons = sorted(slot["reasons"])
        categories = sorted(slot["categories"])
        priority = min(
            (lib.REASON_PRIORITY_TIER.get(r, 4) for r in reasons), default=4
        )
        question_types: list[str] = []
        for r in reasons:
            for c in categories:
                for q in lib.research_questions_for(r, c):
                    if q not in question_types:
                        question_types.append(q)

        subject_id = lib.stable_hash({"unique_string_key": key})[:24]
        subject = {
            "subject_id": subject_id,
            "source_strings": [key],
            "associated_nct_ids": nct_ids,
            "frozen_row_ids": frozen_row_ids,
            "milestone3_evidence_bindings": {
                "milestone3_snapshot_id": MILESTONE3_SNAPSHOT_ID,
                "occurrence_ids": occurrence_ids,
            },
            "reasons": reasons,
            "triage_categories": categories,
            "source_review_queues": sorted(slot["source_queues"]),
            "research_question_types": question_types,
            "priority_tier": priority,
        }
        subjects.append(subject)

        for q in question_types:
            questions.append({
                "subject_id": subject_id,
                "question_type": q,
                "unique_string_key": key,
            })

    return {"subjects": subjects, "questions": questions}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    m3_snapshot_dir = (
        root / "artifacts" / "pipeline" / "pdcd1_rebase_v1" / "stages"
        / "03_candidate_bearing_evidence_triage" / MILESTONE3_SNAPSHOT_ID
    )
    universe = build_universe(m3_snapshot_dir)
    print(f"subjects: {len(universe['subjects'])}")
    print(f"questions: {len(universe['questions'])}")

    from collections import Counter
    tier_counts = Counter(s["priority_tier"] for s in universe["subjects"])
    print("priority tier distribution:", dict(sorted(tier_counts.items())))

    out_dir = root / "_m4_scratch"
    out_dir.mkdir(exist_ok=True)
    with (out_dir / "authority_research_subject_ledger.jsonl").open("w") as f:
        for s in universe["subjects"]:
            f.write(json.dumps(s, sort_keys=True) + "\n")
    with (out_dir / "research_question_ledger.jsonl").open("w") as f:
        for q in universe["questions"]:
            f.write(json.dumps(q, sort_keys=True) + "\n")
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()

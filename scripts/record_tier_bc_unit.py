"""Records one Tier B/C research unit (from a real WebSearch/WebFetch
observation made by the agent driving this script) as a resumable
checkpoint, mirroring the Tier A adapter's checkpoint structure. Reads a
single JSON object from stdin describing the unit; writes a checkpoint file
keyed by sha_str(f"{subject_id}:{source_target}")[:32], skipping if a
checkpoint for that (subject_id, source_target) pair already exists (so
re-recording the same subject/source pair is a no-op, matching per-unit
resumability semantics).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_DIR = ROOT / "_m4_scratch" / "_checkpoints" / "tier_bc_research"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def checkpoint_path(subject_id: str, source_target: str) -> Path:
    key = lib.sha_str(f"{subject_id}:{source_target}")[:32]
    return CHECKPOINT_DIR / f"{key}.json"


def main() -> None:
    unit = json.load(sys.stdin)
    required = {"subject_id", "source_target", "query", "assertions", "research_completion_state_contribution"}
    missing = required - unit.keys()
    if missing:
        print(f"REJECTED missing keys: {missing}", file=sys.stderr)
        sys.exit(1)
    for a in unit["assertions"]:
        if a["assertion_type"] not in lib.ASSERTION_TYPES:
            print(f"REJECTED unknown assertion_type {a['assertion_type']}", file=sys.stderr)
            sys.exit(1)
        if not a.get("evidence_hash"):
            print("REJECTED assertion missing evidence_hash", file=sys.stderr)
            sys.exit(1)
    if unit["research_completion_state_contribution"] not in lib.RESEARCH_COMPLETION_STATES:
        print("REJECTED unknown completion state", file=sys.stderr)
        sys.exit(1)

    cp = checkpoint_path(unit["subject_id"], unit["source_target"])
    if cp.is_file():
        print(f"SKIP already-checkpointed {cp.name}")
        return
    cp.write_text(json.dumps(unit, sort_keys=True, indent=2))
    print(f"WROTE {cp.name}")


if __name__ == "__main__":
    main()

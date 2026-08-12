"""Fetches and hashes Tier B/C source URLs identified via prior WebSearch
observations (the agent performs the search/triage; this script performs
the actual byte-level capture, matching the rigor of the Tier A adapter).

Reads _m4_scratch/tier_bc_capture_manifest.jsonl, where each row is a
manifest entry the agent appends after identifying a candidate official
source for a subject:
  {subject_id, source_target, query, url, assertion_type, detail,
   title, publisher}

For each row, fetches the URL (resumable per-unit checkpoint keyed by
sha_str(f"{subject_id}:{source_target}:{url}")[:32]), records full
source-capture metadata, and emits a narrow assertion of the given type. A
non-200 response (e.g. bot-detection 403, matching the Purple Book
pattern) is recorded honestly as ACCESS_BLOCKED with no positive
assertion, not treated as evidence of anything.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "_m4_scratch" / "tier_bc_capture_manifest.jsonl"
CHECKPOINT_DIR = ROOT / "_m4_scratch" / "_checkpoints" / "tier_bc_capture"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


def checkpoint_path(subject_id: str, source_target: str, url: str) -> Path:
    key = lib.sha_str(f"{subject_id}:{source_target}:{url}")[:32]
    return CHECKPOINT_DIR / f"{key}.json"


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) pdcd1-rebase-v1-milestone4/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    started = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read()
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            final_url = resp.geturl()
    except urllib.error.HTTPError as e:
        body = e.read()
        status = e.code
        content_type = e.headers.get("Content-Type", "") if e.headers else ""
        final_url = url
    except Exception as e:
        body = str(e).encode()
        status = 0
        content_type = ""
        final_url = url
    return {
        "requested_url": url,
        "final_url": final_url,
        "retrieval_timestamp": started,
        "http_status": status,
        "content_type": content_type,
        "response_bytes": body,
    }


def process_row(row: dict) -> dict:
    cp = checkpoint_path(row["subject_id"], row["source_target"], row["url"])
    if cp.is_file():
        return json.loads(cp.read_text())

    result = fetch(row["url"])
    body = result["response_bytes"]
    response_sha256 = lib.sha_bytes(body)

    assertions = []
    if result["http_status"] == 200 and len(body) > 200 and row.get("assertion_type"):
        assertions.append({
            "assertion_type": row["assertion_type"],
            "subject_id": row["subject_id"],
            "evidence_location": row.get("evidence_location", "page content"),
            "authority_tier": row.get("authority_tier", "tier_b"),
            "source_date": row.get("source_date"),
            "evidence_hash": response_sha256,
            "confidence_class": row.get("confidence_class", "TIER_BC_OFFICIAL_SOURCE_MATCH"),
            "detail": row.get("detail", {}),
        })
        completion_state = "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED"
    elif result["http_status"] == 200 and len(body) > 200:
        # assertion_type intentionally omitted (e.g. a secondary/aggregator
        # database source, per policy, cannot alone support an explicit
        # linkage assertion): capture the evidence as informational only.
        completion_state = "NO_EXTERNAL_AUTHORITY_FOUND"
    else:
        completion_state = "ACCESS_BLOCKED" if result["http_status"] not in (200,) else "NO_EXTERNAL_AUTHORITY_FOUND"

    source_evidence = {
        "subject_id": row["subject_id"],
        "source_class": row["source_target"],
        "title": row.get("title", ""),
        "publisher": row.get("publisher", ""),
        "requested_url": result["requested_url"],
        "final_url": result["final_url"],
        "retrieval_timestamp": result["retrieval_timestamp"],
        "publication_or_version_date": row.get("source_date"),
        "http_status": result["http_status"],
        "content_type": result["content_type"],
        "response_byte_length": len(body),
        "response_sha256": response_sha256,
        "authority_tier": row.get("authority_tier", "tier_b"),
        "query": row["query"],
    }

    unit = {
        "subject_id": row["subject_id"],
        "source_target": row["source_target"],
        "query": row["query"],
        "source_evidence": source_evidence,
        "assertions": assertions,
        "research_completion_state_contribution": completion_state,
    }
    cp.write_text(json.dumps(unit, sort_keys=True, indent=2))
    return unit


def main() -> None:
    if not MANIFEST.is_file():
        print("no manifest rows to process")
        return
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]

    out_units = ROOT / "_m4_scratch" / "tier_bc_units.jsonl"
    existing = []
    if out_units.is_file():
        existing = [json.loads(l) for l in out_units.read_text().splitlines() if l.strip()]
    seen_keys = {(u["subject_id"], u["source_target"]) for u in existing}

    new_units = []
    fresh = 0
    for row in rows:
        existed = checkpoint_path(row["subject_id"], row["source_target"], row["url"]).is_file()
        unit = process_row(row)
        if (unit["subject_id"], unit["source_target"]) not in seen_keys:
            new_units.append(unit)
            seen_keys.add((unit["subject_id"], unit["source_target"]))
        if not existed:
            fresh += 1
            time.sleep(0.4)

    with out_units.open("a") as f:
        for u in new_units:
            f.write(json.dumps(u, sort_keys=True) + "\n")

    print(f"processed rows={len(rows)} fresh_fetches={fresh} new_units_appended={len(new_units)} total_units={len(existing) + len(new_units)}")


if __name__ == "__main__":
    main()

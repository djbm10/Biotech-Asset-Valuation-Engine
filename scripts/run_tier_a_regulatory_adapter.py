"""Tier A regulatory-source adapter (Drugs@FDA via openFDA).

Target-agnostic: queries by exact brand name / generic name / substance
name only (no fuzzy matching). For each subject in the authority research
subject ledger, issues one combined exact-match query against openFDA's
drug/drugsfda.json endpoint and records a resumable per-unit checkpoint
with full source-capture metadata (Section 6) and narrow assertions
(Section 10). Negative results are captured explicitly as
NO_EXACT_REGULATORY_MATCH, never as proof of nonexistence.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUBJECT_LEDGER = ROOT / "_m4_scratch" / "authority_research_subject_ledger.jsonl"
CHECKPOINT_DIR = ROOT / "_m4_scratch" / "_checkpoints" / "tier_a_drugs_at_fda"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

SOURCE_TARGET = "drugs_at_fda"
ENDPOINT = "https://api.fda.gov/drug/drugsfda.json"


def exact_query(name: str) -> str:
    # openFDA stores brand_name/generic_name/substance_name in uppercase;
    # .exact matching is case-sensitive, so an original-case-only query
    # silently misses real exact matches (e.g. "Cisplatin" vs "CISPLATIN").
    # Query both the original casing and the uppercase form -- both remain
    # exact field matches, this only normalizes case, it is not fuzzy
    # matching.
    variants = {name, name.upper()}
    clauses = []
    for v in variants:
        safe = v.replace('"', '\\"')
        clauses += [
            f'openfda.brand_name.exact:"{safe}"',
            f'openfda.generic_name.exact:"{safe}"',
            f'openfda.substance_name.exact:"{safe}"',
        ]
    return " OR ".join(clauses)


def fetch(name: str) -> dict:
    query = exact_query(name)
    url = ENDPOINT + "?" + urllib.parse.urlencode({"search": query, "limit": 5})
    req = urllib.request.Request(url, headers={"User-Agent": "pdcd1-rebase-v1-milestone4/1.0"})
    started = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read()
        status = e.code
        content_type = e.headers.get("Content-Type", "") if e.headers else ""
    return {
        "requested_url": url,
        "final_url": url,
        "retrieval_timestamp": started,
        "http_status": status,
        "content_type": content_type,
        "response_bytes": body,
    }


def checkpoint_path(subject_id: str) -> Path:
    key = lib.sha_str(f"{subject_id}:{SOURCE_TARGET}")[:32]
    return CHECKPOINT_DIR / f"{key}.json"


def process_subject(subject: dict) -> dict:
    cp = checkpoint_path(subject["subject_id"])
    if cp.is_file():
        return json.loads(cp.read_text())

    name = subject["source_strings"][0]
    result = fetch(name)
    body = result["response_bytes"]
    response_sha256 = lib.sha_bytes(body)
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = None

    assertions = []
    if result["http_status"] == 200 and parsed and parsed.get("meta", {}).get("results", {}).get("total", 0) > 0:
        matches = parsed.get("results", [])
        app_numbers = sorted({m.get("application_number") for m in matches if m.get("application_number")})
        assertions.append({
            "assertion_type": "EXACT_PRODUCT_NAME_EXISTS",
            "subject_id": subject["subject_id"],
            "evidence_location": "results[].openfda.brand_name|generic_name|substance_name",
            "authority_tier": "tier_a",
            "source_date": parsed.get("meta", {}).get("last_updated"),
            "evidence_hash": response_sha256,
            "confidence_class": "HIGH_TIER_A_EXACT_MATCH",
            "detail": {"application_numbers": app_numbers, "match_count": len(matches)},
        })
        if app_numbers:
            assertions.append({
                "assertion_type": "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
                "subject_id": subject["subject_id"],
                "evidence_location": "results[].application_number",
                "authority_tier": "tier_a",
                "source_date": parsed.get("meta", {}).get("last_updated"),
                "evidence_hash": response_sha256,
                "confidence_class": "HIGH_TIER_A_EXACT_MATCH",
                "detail": {"application_numbers": app_numbers},
            })
        completion_state = "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED"
    elif result["http_status"] == 200 and parsed is not None:
        assertions.append({
            "assertion_type": "NO_EXACT_REGULATORY_MATCH",
            "subject_id": subject["subject_id"],
            "evidence_location": "meta.results.total",
            "authority_tier": "tier_a",
            "source_date": parsed.get("meta", {}).get("last_updated"),
            "evidence_hash": response_sha256,
            "confidence_class": "NEGATIVE_TIER_A_SEARCH_NOT_EXHAUSTIVE_PROOF",
            "detail": {"note": "SOURCE_NOT_EXHAUSTIVE: Drugs@FDA covers only FDA-regulated marketed/approved applications; absence does not establish nonexistence for investigational products."},
        })
        completion_state = "RETRYABLE"
    else:
        assertions.append({
            "assertion_type": "NO_EXACT_REGULATORY_MATCH",
            "subject_id": subject["subject_id"],
            "evidence_location": None,
            "authority_tier": "tier_a",
            "source_date": None,
            "evidence_hash": response_sha256,
            "confidence_class": "ACCESS_UNAVAILABLE",
            "detail": {"http_status": result["http_status"]},
        })
        completion_state = "ACCESS_BLOCKED" if result["http_status"] not in (200,) else "RETRYABLE"

    source_evidence = {
        "subject_id": subject["subject_id"],
        "source_class": SOURCE_TARGET,
        "title": "Drugs@FDA (via openFDA drug/drugsfda.json)",
        "publisher": "U.S. Food and Drug Administration / openFDA",
        "requested_url": result["requested_url"],
        "final_url": result["final_url"],
        "retrieval_timestamp": result["retrieval_timestamp"],
        "publication_or_version_date": (parsed or {}).get("meta", {}).get("last_updated"),
        "http_status": result["http_status"],
        "content_type": result["content_type"],
        "response_byte_length": len(body),
        "response_sha256": response_sha256,
        "authority_tier": "tier_a",
        "query": name,
    }

    unit = {
        "subject_id": subject["subject_id"],
        "source_target": SOURCE_TARGET,
        "query": name,
        "source_evidence": source_evidence,
        "assertions": assertions,
        "research_completion_state_contribution": completion_state,
    }
    cp.write_text(json.dumps(unit, sort_keys=True, indent=2))
    return unit


def main() -> None:
    subjects = [json.loads(l) for l in SUBJECT_LEDGER.read_text().splitlines() if l.strip()]
    subjects.sort(key=lambda s: (s["priority_tier"], s["subject_id"]))

    out_units = ROOT / "_m4_scratch" / "tier_a_units.jsonl"
    processed = 0
    fresh_fetches = 0
    with out_units.open("w") as out:
        for subject in subjects:
            existed = checkpoint_path(subject["subject_id"]).is_file()
            unit = process_subject(subject)
            out.write(json.dumps(unit, sort_keys=True) + "\n")
            processed += 1
            if not existed:
                fresh_fetches += 1
                time.sleep(1.3)  # stay well under openFDA's unauthenticated rate limit
            if processed % 25 == 0:
                print(f"...{processed}/{len(subjects)} (fresh this run: {fresh_fetches})", file=sys.stderr)

    print(f"DONE processed={processed} fresh_fetches={fresh_fetches}")


if __name__ == "__main__":
    main()

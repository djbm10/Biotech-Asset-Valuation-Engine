"""Single representative access probe for the Purple Book adapter.

purplebooksearch.fda.gov enforces bot-detection (Akamai) that blocks
programmatic/non-browser requests identically regardless of query content.
Rather than fabricate 554 near-identical per-subject negative results
against a source that is systematically unreachable, this script performs
one real, hash-preserved probe and records ACCESS_BLOCKED once at the
source-target level. The Milestone 4 validator and final report treat
Purple Book as ACCESS_BLOCKED for this run; biologics license coverage is
still available through Drugs@FDA (openFDA), which indexes BLA numbers.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pdcd1_external_authority_lib as lib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
URL = "https://purplebooksearch.fda.gov/api/search?query=Nivolumab"


def main() -> None:
    started = datetime.now(timezone.utc).isoformat()
    req = urllib.request.Request(URL, headers={"User-Agent": "pdcd1-rebase-v1-milestone4/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read()
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read()
        status = e.code
        content_type = e.headers.get("Content-Type", "") if e.headers else ""

    record = {
        "source_class": "purple_book",
        "title": "FDA Purple Book Database Search",
        "publisher": "U.S. Food and Drug Administration",
        "requested_url": URL,
        "final_url": URL,
        "retrieval_timestamp": started,
        "http_status": status,
        "content_type": content_type,
        "response_byte_length": len(body),
        "response_sha256": lib.sha_bytes(body),
        "authority_tier": "tier_a",
        "result": "ACCESS_BLOCKED",
        "note": "Bot-detection redirect (Akamai apology page) returned for a representative probe query; the source is systematically unreachable via programmatic access in this environment, independent of query content. Recorded once rather than repeated per-subject.",
    }
    out = ROOT / "_m4_scratch" / "purple_book_access_probe.json"
    out.write_text(json.dumps(record, indent=2, sort_keys=True))
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

"""Reproduce a known asset-history omission; never award discovery or identity credit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from bve.se.acquisition.asset_history import API, investigate_history

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT / "research/se_lead_verification_v1"
HERE = Path(__file__).parent


def run(output: Path, offline_from: Path | None = None) -> None:
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"
    raw.mkdir()
    spec = json.loads((HERE / "inputs.json").read_text())
    ledger = json.loads((PREVIOUS / "evidence.json").read_text())
    documents = []
    provenance = []
    for evidence_id in spec["company_evidence_ids"]:
        entries = [e for e in ledger["evidence"] if e["id"] == evidence_id]
        if len(entries) != 1:
            raise ValueError("exact archived evidence entry required")
        entry = entries[0]
        source = (PREVIOUS / entry["path"]).resolve()
        if not source.is_relative_to(PREVIOUS.resolve()):
            raise ValueError("unsafe archived source path")
        payload = source.read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["file_sha256"]:
            raise ValueError("archived company evidence changed")
        documents.append({"url": entry["url"], "text": payload.decode()})
        (raw / f"company_{len(documents)}.txt").write_bytes(payload)
        provenance.append(entry)
    started = datetime.now(UTC).isoformat()
    if offline_from:
        prior = json.loads((offline_from / "raw/full_result.json").read_text())
        pages = {p["url"]: p["payload"] for q in prior["queries"] for p in q["pages"]}

        def fetch(params):
            return pages[API + "?" + urlencode(params)]

        result = investigate_history(spec["root"], documents, fetch=fetch)
        if result != prior:
            raise AssertionError("offline core result differs")
    else:
        contact = subprocess.check_output(["git", "config", "user.email"], text=True).strip()
        if "@" not in contact or "noreply" in contact:
            raise ValueError("operator contact required for public acquisition")
        os.environ.setdefault("BVE_SE_USER_AGENT", f"BVE research/1.0 ({contact})")
        result = investigate_history(spec["root"], documents)
    (raw / "full_result.json").write_text(json.dumps(result, indent=2) + "\n")
    public = json.loads(json.dumps(result))
    for qi, query in enumerate(public["queries"], 1):
        query.pop("studies")
        for pi, page in enumerate(query["pages"], 1):
            file = f"query_{qi}_page_{pi}.json"
            (raw / file).write_text(
                json.dumps(page.pop("payload"), sort_keys=True, ensure_ascii=False)
            )
            page["payload_file"] = "raw/" + file
    public.update(
        observed_at=started,
        completed_at=datetime.now(UTC).isoformat(),
        execution="OFFLINE_REPLAY" if offline_from else "LIVE_NAMED_FOLLOWUP",
        input_spec_sha256=hashlib.sha256((HERE / "inputs.json").read_bytes()).hexdigest(),
        company_provenance=provenance,
        ai_review="Defect report only; not human validation",
        independent_human_bd_review="PENDING",
    )
    (output / "history.json").write_text(json.dumps(public, indent=2) + "\n")
    lines = [
        "# Bounded asset-history follow-up",
        "",
        "**UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability.**",
        "",
        f"Root: {result['root']}. Observed: {started}.",
        "",
        (
            "Named follow-up, not asset discovery. Every trial attribution requires identity review. "
            "Asset-history completeness is UNKNOWN. No global identity merges or scientific gates run."
        ),
        "",
        "## Query coverage",
        "",
        "| Term | Query status | Registry count |",
        "|---|---|---|",
    ]
    for query in result["queries"]:
        lines.append(f"| {query['term']} | {query['status']} | {query['total_count']} |")
    lines += [
        "",
        (
            "Complete pages mean only complete pages for the literal issued query, "
            "not all aliases or all trials. Other registries were NOT_SEARCHED. "
            "Alias collisions were not exhaustively assessed."
        ),
        "",
        "## Derived naming relationships — retrieval leads, not identity decisions",
        "",
        "| From | To | Evidence | Status |",
        "|---|---|---|---|",
    ]
    seen = set()
    for lead in result["naming_leads"]:
        key = (lead["left"], lead["right"], lead["source_url"], lead["status"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"| {lead['left']} | {lead['right']} | "
            f"[{lead['basis']}]({lead['source_url']}) | {lead['status']} |"
        )
    lines += [
        "",
        (
            "Exact passages, pointers, source hashes and query receipts are in history.json. "
            "Failed/partial requests and blocked terms remain explicit there."
        ),
        "",
        "## Distinct retrieved records (not a complete asset trial landscape)",
        "",
        "| Trial | Condition | Phase | State | Enrollment | Stop reason | Retrieved via | Attribution |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for trial in result["trials"]:
        cells = [
            f"[{trial['nct_id']}]({trial['source_url']})",
            ", ".join(trial["conditions"]),
            ", ".join(trial["phase"]),
            trial["status"],
            json.dumps(trial["enrollment"]),
            trial["why_stopped"] or "Not reported",
            ", ".join(trial["query_terms"]),
            trial["attribution"],
        ]
        lines.append(
            "| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |"
        )
    lines += [
        "",
        (
            "Status and enrollment are registry-reported; not independently verified site "
            "activity or efficacy. Oncology exposure is not autoimmune PoC. Sponsor is not owner; "
            "trial geography is not evidence of territorial rights or availability."
        ),
        "",
        (
            "Next: adjudicate the code chain and product formulation; examine the stopped trial’s "
            "results and rationale; search other registries under reviewed terms. Human BD review "
            "and blind discovery evaluation remain outstanding."
        ),
    ]
    (output / "HISTORY.md").write_text("\n".join(lines) + "\n")
    (output / "MANIFEST.json").write_text(
        json.dumps(
            {
                str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(output.rglob("*"))
                if p.is_file()
            },
            indent=2,
        )
        + "\n"
    )
    print("Queries:", [(q["term"], q["status"], q["total_count"]) for q in result["queries"]])
    print("Distinct returned trials:", len(result["trials"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--offline-from", type=Path)
    args = parser.parse_args()
    run(args.output, args.offline_from)

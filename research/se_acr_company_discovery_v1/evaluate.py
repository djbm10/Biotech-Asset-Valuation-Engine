"""Score sealed nominations against frozen labels and explicit manual evidence spans."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REQUIRED = {"identity", "target", "antibody_format", "autoimmune_intent", "investigational_context"}


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def verify_seal(run: Path) -> dict:
    seal = json.loads((run / "NOMINATIONS_SEALED.json").read_text())
    for relative, digest in seal["files"].items():
        path = run / relative
        if not path.resolve().is_relative_to(run.resolve()):
            raise ValueError("unsafe seal path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"sealed input changed: {relative}")
    if seal["seeded_names"]:
        raise ValueError("seeded discovery cannot score")
    return seal


def score(run: Path, reference: dict, assessments: list[dict]) -> dict:
    seal = verify_seal(run)
    nominations = json.loads((run / "nominations.json").read_text())
    documents = {
        d["document_id"]: d
        for d in (
            json.loads(line) for line in (run / "corpus/manifest.jsonl").read_text().splitlines()
        )
    }
    fetches = json.loads((run / "fetches.json").read_text())
    fetch_by_url = {r["url"]: r for r in fetches}
    selection = json.loads((run / "selection.json").read_text())
    provenance = {r["url"]: r for r in selection if r["selected"]}
    keys = {norm(n["name"]) for n in nominations}
    reviews = {norm(a["name"]): a for a in assessments}
    if len(reviews) != len(assessments):
        raise ValueError("duplicate manual assessment")
    # A reviewer cannot manufacture a discovery, even from a real page.
    for key, a in reviews.items():
        if key not in keys:
            raise ValueError(f"not nominated: {a['name']}")
        doc = documents[a["document_id"]]
        if not any(
            norm(n["name"]) == key and n["document_id"] == a["document_id"] for n in nominations
        ):
            raise ValueError("assessment document did not nominate the asset")
        for field, span in a.get("evidence_spans", {}).items():
            start, end = span["start"], span["end"]
            text = doc["text"][start:end]
            if start < 0 or end <= start or end > len(doc["text"]):
                raise ValueError(f"invalid evidence span: {field}")
            if hashlib.sha256(text.encode()).hexdigest() != span["sha256"]:
                raise ValueError(f"evidence span mismatch: {field}")
            if field == "identity" and key not in norm(text):
                raise ValueError("identity evidence does not name the candidate")
    rows = []
    for entry in reference["entries"]:
        aliases = {norm(n) for n in [entry["name"], *entry.get("aliases", [])]}
        hits = [n for n in nominations if norm(n["name"]) in aliases]
        a = next((reviews[k] for k in sorted(aliases) if k in reviews), None)
        blockers = []
        if not hits:
            blockers.append("not nominated")
        if entry["label"] != "RELEVANT_INVESTIGATIONAL" or not entry["fully_verified"]:
            blockers.append("not a frozen fully-verified relevant reference")
        if entry["baseline_found"]:
            blockers.append("already nominated by historical baseline")
        if not a or a["classification"] != "NAMED_INVESTIGATIONAL":
            blockers.append("no qualifying manual product identification")
        doc = documents[a["document_id"]] if a else None
        if a:
            missing = sorted(REQUIRED - set(a.get("evidence_spans", {})))
            if missing:
                blockers.append("missing primary evidence: " + ", ".join(missing))
            published = doc["publication_date"]
            if not published or published > reference["baseline_cutoff"]:
                blockers.append("no source publication date at/before baseline cutoff")
            if doc["source_family"] not in {"conference_acr", "company_pipeline_or_presentation"}:
                blockers.append("not an admitted primary publisher")
            if doc["parser_status"] != "OK" or doc["source_url"] not in provenance:
                blockers.append("not a successful selected primary document")
        rows.append(
            {
                **entry,
                "nominated_this_run": bool(hits),
                "primary_success": not blockers,
                "blockers": blockers,
                "review": a,
                "source_url": doc["source_url"] if doc else None,
                "source_publication_date": doc["publication_date"] if doc else None,
                "raw_sha256": fetch_by_url[doc["source_url"]].get("sha256") if doc else None,
                "query_provenance": provenance[doc["source_url"]] if doc else None,
            }
        )
    successes = [r["name"] for r in rows if r["primary_success"]]
    return {
        "validation_badge": {
            "grade": "UNVALIDATED",
            "warning": "This output is UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability.",
        },
        "endpoint": "PASS" if successes else "FAIL",
        "primary_successes": successes,
        "independent_bd_review": "OUTSTANDING",
        "scientific_eligibility": "NOT_EVALUATED",
        "commercial_rights": "UNKNOWN",
        "counts": {
            "search_results": len(selection),
            "selected_documents": len(provenance),
            "attempted_documents": len(fetches),
            "fetched_documents": sum(f["status"] == "OK" for f in fetches),
            "indexed_documents": sum(d["index_status"] == "INDEXED" for d in documents.values()),
            "literal_nominations": len(nominations),
            "normalized_nominated_names": len(keys),
            "manually_identified_investigational_assets": sum(
                a["classification"] == "NAMED_INVESTIGATIONAL" for a in assessments
            ),
            "primary_endpoint_successes": len(successes),
            "scientific_eligibility_evaluated": 0,
            "confirmed_bd_opportunities": 0,
        },
        "seeded_names": seal["seeded_names"],
        "rows": rows,
        "limitations": [
            "Exposed development reference; not a blind holdout.",
            "Current search-index ranking and page bytes do not reconstruct historical search.",
            "Existing gates were not run; manual source adjudication is not eligibility.",
            "Research/clinical development context does not prove worldwide non-approval or availability.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for line in (HERE / "FROZEN.sha256").read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        if hashlib.sha256((HERE / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("preregistration inputs changed")
    result = score(
        args.run,
        json.loads((HERE / "evaluation/reference.json").read_text()),
        json.loads((HERE / "evaluation/adjudication.json").read_text())["assessments"],
    )
    with args.output.open("x") as handle:
        handle.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "endpoint": result["endpoint"],
                "successes": result["primary_successes"],
                "counts": result["counts"],
            }
        )
    )

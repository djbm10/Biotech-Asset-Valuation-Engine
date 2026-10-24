"""Bounded, reference-blind development acquisition using existing BVE components."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import subprocess
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def search_rows(receipt: dict) -> list[dict]:
    """Only top-level ranked result headings, never links embedded inside snippets."""
    matches = re.findall(r"^([^\n]+) \((https?://[^\s]+)\)\n", receipt["response"], re.MULTILINE)
    return [
        {"query_id": receipt["query_id"], "rank": rank, "title": title, "url": urldefrag(url)[0]}
        for rank, (title, url) in enumerate(matches, 1)
    ]


def select(spec: dict, receipts: dict, issuer_hosts: dict[str, str]) -> list[dict]:
    """Apply preregistered rank, publisher and cap rules without reading reference labels."""
    counts = {"acr": 0, "company": 0}
    seen = set()
    rows = []
    for query in spec["queries"]:
        receipt = receipts[query["id"]]
        if receipt["query"] != query["q"]:
            raise ValueError("search receipt differs from frozen query")
        for row in search_rows(receipt):
            family = query["family"]
            parts = urlsplit(row["url"])
            publisher = issuer_hosts.get(parts.hostname or "")
            if family == "acr":
                allowed = parts.hostname == "acrabstracts.org" and parts.path.startswith(
                    "/abstract/"
                )
                reason = "ACR abstract" if allowed else "not an ACR abstract page"
            else:
                pdf = parts.path.lower().endswith((".pdf", "/pdf"))
                allowed = bool(publisher) and not pdf
                reason = (
                    "issuer-controlled HTML page"
                    if allowed
                    else "non-issuer, unclear publisher or PDF"
                )
            included = False
            if allowed:
                if row["url"] in seen:
                    reason = "duplicate URL"
                elif counts[family] >= spec["max_documents_per_family"]:
                    reason = "family cap reached"
                else:
                    included = True
                    counts[family] += 1
                    seen.add(row["url"])
            rows.append(
                {
                    **row,
                    "family": family,
                    "selected": included,
                    "reason": reason,
                    "declared_publisher": publisher if family == "company" else "ACR",
                }
            )
    return rows


def nominate(documents: list) -> list[dict]:
    from bve.se.discovery.adapters import extract_observed_asset_names

    result = []
    for doc in documents:
        if doc.parser_status.value != "OK":
            continue
        # No supplied candidates, reference aliases, title-derived product URLs or name seeds.
        for name in extract_observed_asset_names(doc.text):
            result.append(
                {
                    "name": name,
                    "document_id": doc.document_id,
                    "url": doc.source_url,
                    "source_family": doc.source_family,
                }
            )
    return sorted(result, key=lambda row: (row["url"], row["name"]))


def acquire(spec: dict, rows: list[dict], output: Path, fetch_fn=None) -> None:
    from bve.se.acquisition.connectors import DeclaredUrlConnector
    from bve.se.acquisition.corpus_store import CorpusStore
    from bve.se.acquisition.http import safe_get_public_page, user_agent_receipt
    from bve.se.schemas.contracts import SourceTier, TemporalBasis

    output.mkdir(parents=True, exist_ok=False)
    raw_dir = output / "raw"
    raw_dir.mkdir()
    (output / "selection.json").write_text(json.dumps(rows, indent=2) + "\n")
    fetches = []
    visited = set()

    def fetch(url: str) -> str:
        if url in visited:
            raise ValueError("duplicate fetch refused")
        visited.add(url)
        if len(visited) > 2 * spec["max_documents_per_family"]:
            raise ValueError("fetch budget exceeded")
        receipt = {
            "url": url,
            "observed_at": datetime.now(UTC).isoformat(),
            "redirects": [],
        }
        try:
            raw = (
                fetch_fn(url)
                if fetch_fn
                else safe_get_public_page(
                    url,
                    timeout=(5.0, 20.0),
                    max_bytes=spec["max_page_bytes"],
                    on_redirect=lambda source, target: receipt["redirects"].append(
                        [source, target]
                    ),
                )
            )
            content = raw.encode("utf-8")
            if len(content) > spec["max_page_bytes"]:
                raise ValueError("decoded page exceeds study budget")
            digest = hashlib.sha256(content).hexdigest()
            (raw_dir / f"{digest}.html").write_bytes(content)
            receipt.update({"status": "OK", "sha256": digest, "bytes": len(content)})
            return raw
        except Exception as exc:
            receipt.update({"status": "FAILED", "error_type": type(exc).__name__})
            raise
        finally:
            fetches.append(receipt)
            (output / "fetches.json").write_text(json.dumps(fetches, indent=2) + "\n")

    store = CorpusStore(output / "corpus")
    health = []
    for family in ("acr", "company"):
        chosen = [row for row in rows if row["selected"] and row["family"] == family]
        if not chosen:
            continue
        connector = DeclaredUrlConnector(
            "conference_acr" if family == "acr" else "company_pipeline_or_presentation",
            [r["url"] for r in chosen],
            fetch_fn=fetch,
            source_tier=SourceTier.PRIMARY if family == "acr" else SourceTier.COMPANY_AUTHORED,
            temporal_basis=TemporalBasis.OBSERVED_AT,
            companies_by_url={r["url"]: r["declared_publisher"] for r in chosen}
            if family == "company"
            else {},
        )
        report = connector.acquire(
            store, targets=[], modality_terms=[], as_of_date=date.fromisoformat(spec["as_of"])
        )
        health.append(
            {
                **report.model_dump(mode="json"),
                "withheld_as_of": connector.withheld_as_of,
                "observed_undated": connector.observed_undated,
            }
        )
    (output / "health.json").write_text(json.dumps(health, indent=2) + "\n")
    documents = store.documents()
    store.export_source_index(output / "source_index.yaml")
    nominations = nominate(documents)
    (output / "nominations.json").write_text(json.dumps(nominations, indent=2) + "\n")
    receipt = {
        "stage": "nominations frozen before scoring",
        "code_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "acquisition_code_sha256": sha(Path(__file__)),
        "queries": spec["queries"],
        "seeded_names": [],
        "scientific_eligibility": "NOT_EVALUATED",
        "user_agent": user_agent_receipt() if fetch_fn is None else {"test_double": True},
        "files": {
            str(p.relative_to(output)): sha(p) for p in sorted(output.rglob("*")) if p.is_file()
        },
    }
    (output / "NOMINATIONS_SEALED.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                "fetched": len(fetches),
                "documents": len(documents),
                "nominations": len(nominations),
                "output": str(output),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads((HERE / "search_spec.json").read_text())
    # Only the acquisition spec is read here. Reference labels are evaluation-only.
    resource.setrlimit(resource.RLIMIT_AS, (spec["max_virtual_memory_bytes"],) * 2)
    if not os.environ.get("BVE_SE_USER_AGENT"):
        contact = subprocess.check_output(["git", "config", "user.email"], text=True).strip()
        if "@" not in contact or "noreply" in contact.lower():
            raise ValueError("real operator contact required")
        os.environ["BVE_SE_USER_AGENT"] = f"BVE research/1.0 ({contact})"
    rows = json.loads((HERE / "selection.json").read_text())
    acquire(spec, rows, args.output)

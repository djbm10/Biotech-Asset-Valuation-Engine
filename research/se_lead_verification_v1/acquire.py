"""Named follow-up only: bounded primary retrieval, never discovery scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from bve.se.acquisition.connectors import DeclaredUrlConnector
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.http import get_json, safe_get_public_page
from bve.se.schemas.contracts import SourceTier, TemporalBasis

HERE = Path(__file__).resolve().parent


def main(output: Path, sources: Path) -> None:
    specs = json.loads(sources.read_text())
    if len(specs) > 20:
        raise ValueError("document budget exceeded")
    output.mkdir(exist_ok=False, parents=True)
    contact = subprocess.check_output(["git", "config", "user.email"], text=True).strip()
    if "@" not in contact or "noreply" in contact.lower():
        raise ValueError("real operator contact required")
    os.environ.setdefault("BVE_SE_USER_AGENT", f"BVE research/1.0 ({contact})")
    store = CorpusStore(output / "corpus")
    receipts = []
    for spec in specs:
        receipt = {**spec, "observed_at": datetime.now(UTC).isoformat()}
        try:
            if spec["kind"] == "json":
                payload = get_json(spec["url"], timeout=(5, 20), max_bytes=2 * 1024**2)
                raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
                receipt["serialization"] = "canonical decoded JSON; not wire bytes"
            else:
                raw = safe_get_public_page(spec["url"], timeout=(5, 20), max_bytes=2 * 1024**2)
                receipt["serialization"] = "decoded HTML UTF-8"
            path = output / (spec["id"] + (".json" if spec["kind"] == "json" else ".html"))
            path.write_text(raw)
            receipt.update(status="OK", sha256=hashlib.sha256(raw.encode()).hexdigest())
            if spec["kind"] == "html":
                connector = DeclaredUrlConnector(
                    spec["family"],
                    [spec["url"]],
                    fetch_fn=lambda url, body=raw: body,
                    source_tier=SourceTier.PRIMARY,
                    temporal_basis=TemporalBasis.OBSERVED_AT,
                    companies_by_url={spec["url"]: spec["publisher"]},
                )
                health = connector.acquire(
                    store, targets=[], modality_terms=[], as_of_date=datetime.now(UTC).date()
                )
                receipt["health"] = health.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 — preserve failed-source receipts at HTTP boundary
            receipt.update(status="FAILED", error_type=type(exc).__name__)
        receipts.append(receipt)
        (output / "receipts.json").write_text(json.dumps(receipts, indent=2) + "\n")
        print(spec["id"], receipt["status"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=HERE / "sources.json")
    args = parser.parse_args()
    main(args.output, args.sources)

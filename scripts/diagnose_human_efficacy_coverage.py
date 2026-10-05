"""HUMAN_EFFICACY_COVERAGE_DIAGNOSIS v1: corpus-side evidence for each frozen asset.

Diagnosis only. Reads the sealed mint5 run, never changes a reader. For each target-PASS
asset it reports the documents that mention it, every sentence naming it that carries an
efficacy term (the *current* strict reader's verdict alongside), and registry result flags.

    PYTHONPATH=src python scripts/diagnose_human_efficacy_coverage.py ~/se_runs/mint5_armid_v1
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bve.se.evidence import human_poc as hp


def _text(path: str) -> str:
    try:
        raw = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return ""
    return json.dumps(raw, ensure_ascii=False) if not isinstance(raw, str) else raw


def main(run: Path) -> None:
    result = json.loads((run / "result.json").read_text())
    gates = {
        e["subject_id"]: {d["requirement_id"]: d["status"] for d in e["decisions"]}
        for e in result["gate_evaluations"]
    }
    population = sorted(
        (a for a in result["candidates"] if gates.get(a["asset_id"], {}).get("target.expression") == "PASS"),
        key=lambda a: a["canonical_name"].casefold(),
    )
    docs = {d["document_id"]: d for d in result["source_documents"]}
    mentions: dict[str, set[str]] = {}
    by_key = {}
    for m in result["identity_mentions"]:
        by_key.setdefault(m["normalized_asset_name"], set()).add(m["source_document_id"])
    frozen = []
    for asset in population:
        names = sorted({asset["canonical_name"], *asset["aliases"]})
        doc_ids = set()
        for key in asset.get("identity_keys", []):
            doc_ids |= by_key.get(key, set())
        texts = {d: _text(docs[d]["snapshot_path"]) for d in sorted(doc_ids) if d in docs and docs[d].get("snapshot_path")}
        strict = []
        loose = []
        has_results = []
        for doc_id, text in texts.items():
            plain = re.sub(r"\\[nrt]|[{}\[\]\"]", " ", text)
            strict += [s.sentence for s in hp.efficacy_statements(plain, asset_names=names, document_id=doc_id)]
            for sentence in hp._sentences(plain):
                low = sentence.casefold()
                if any(n.casefold() in low for n in names) and hp._efficacy_term(sentence) and hp._VALUE.search(sentence):
                    loose.append((docs[doc_id]["document_type"], sentence[:300]))
            if '"hasResults": true' in text or '"resultsSection"' in text:
                has_results.append(docs[doc_id]["source_url"])
        frozen.append({
            "asset_id": asset["asset_id"],
            "name": asset["canonical_name"],
            "aliases": names,
            "trial_ids": sorted(asset["trial_ids"]),
            "documents": [docs[d]["source_url"] for d in sorted(texts)],
            "document_types": sorted({docs[d]["document_type"] for d in texts}),
            "strict_statements": strict,
            "loose_efficacy_sentences": loose[:8],
            "registry_results_posted": has_results,
            "human_poc_gate": gates[asset["asset_id"]].get("evidence.human_poc"),
        })
    print(json.dumps(frozen, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]))

"""Frozen scope representation evaluation; no live searches or replays."""

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from bve.se.discovery.adapters import QueryVocabulary
from bve.se.evidence.modality_scope import ScopeSource, scoped_modality_assertions

ROOT = Path("/home/djmann/projects/bve-b8")
STUDY = ROOT / "research/se_modality_assertion_scope_representation_v1"
OLD = ROOT / "research/se_product_vs_component_modality_semantics_v1"


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def verify(records, text):
    for r in records:
        for span in [r.mention, r.product_span, r.component_span, r.relation_span]:
            if span is not None:
                assert text[span.start : span.end] == span.text
        assert not r.legacy_decision_bearing
        if r.scope != "AMBIGUOUS":
            assert r.product_span and r.relation_span and r.relations
    assert len({r.assertion_id for r in records}) == len(records)


def build(output):
    for p, sha in json.loads((STUDY / "inputs.json").read_text()).items():
        assert digest(Path(p)) == sha
    controls = json.loads((STUDY / "controls.json").read_text())
    old = {r["id"]: r for r in json.loads((OLD / "results/scope_table.json").read_text())}
    vocabulary = QueryVocabulary.for_ontology()
    runpath = Path("/home/djmann/se_runs/heldout_h19_v4/result.json")
    run = json.loads(runpath.read_text())
    original_rows = json.loads(gzip.decompress((OLD / "results/h19_rows.json.gz").read_bytes()))
    lifecycle = json.loads((OLD / "results/datopotamab_lifecycle.json").read_text())
    data = []
    counts = Counter()
    for row in controls:
        text = row["text"]
        if row["id"] == "H19_DATO":
            a = old[row["id"]]["artifact"]
            document = a["document"]
            path = Path(document["snapshot_path"])
            raw = json.loads(path.read_text())
            intervention = raw["armsInterventionsModule"]["interventions"][0]
            assert text == intervention["description"]
            source = ScopeSource(
                artifact=str(path),
                artifact_sha256=digest(path),
                record_id="NCT07720284",
                field="/armsInterventionsModule/interventions/0/description",
                product_names=tuple([intervention["name"], *intervention.get("otherNames", [])]),
                product_locator="/armsInterventionsModule/interventions/0/name+otherNames",
            )
            candidate = lifecycle["candidate"]["asset_id"]
            facts = (lifecycle["fact"]["fact_id"],)
            consequence = lifecycle["gates"]
        else:
            source = ScopeSource(
                artifact=str(STUDY / "controls.json"),
                artifact_sha256=digest(STUDY / "controls.json"),
                record_id=row["id"],
                field=f"/{controls.index(row)}/text",
                product_names=("Novel Product",),
                product_locator="explicit fixture subject Novel Product",
            )
            candidate = "fixture:" + row["id"]
            facts = ()
            consequence = "NO_LEGACY_GATE_SYNTHETIC_PROBE"
        records = scoped_modality_assertions(candidate, text, source, legacy_fact_ids=facts)
        verify(records, text)
        offset = text.casefold().index(row["focus_term"].casefold())
        focus = [
            r
            for r in records
            if r.mention.start == offset and r.mention.end == offset + len(row["focus_term"])
        ]
        assert focus and all(r.scope == row["expected_scope"] for r in focus), row["id"]
        winner = vocabulary.modality_in(text)
        if row["id"] in old:
            assert winner == old[row["id"]]["current_lexical_winner"]
        counts.update(r.scope for r in records)
        data.append(
            {
                "id": row["id"],
                "candidate": candidate,
                "source_text": text,
                "assertions": [r.model_dump(mode="json") for r in records],
                "legacy_scalar": winner,
                "legacy_fact": lifecycle["fact"] if facts else None,
                "legacy_gate": consequence,
            }
        )
    selected = {r["candidate"]["asset_id"]: r["candidate"] for r in original_rows if r["candidate"]}
    claims = {c["claim_id"]: c for c in run["claims"]}
    docs = {d["document_id"]: d for d in run["source_documents"]}
    links = []
    h19records = {}
    for fact in run["facts"]:
        if fact["subject_id"] not in selected or fact["fact_type"] != "modality_id":
            continue
        candidate = selected[fact["subject_id"]]
        names = {
            candidate["canonical_name"].casefold(),
            *(n.casefold() for n in candidate["aliases"]),
        }
        records = []
        for cid in fact["supporting_claim_ids"]:
            doc = docs.get(claims[cid]["source_document_id"])
            snapshot = doc.get("snapshot_path") if doc else None
            if not snapshot:
                continue
            path = Path(snapshot)
            raw = json.loads(path.read_text())
            if not isinstance(raw, dict):
                continue
            for index, intervention in enumerate(
                raw.get("armsInterventionsModule", {}).get("interventions", [])
            ):
                source_names = [intervention.get("name", ""), *intervention.get("otherNames", [])]
                if not names.intersection(n.casefold() for n in source_names):
                    continue
                text = intervention.get("description", "")
                source = ScopeSource(
                    artifact=str(path),
                    artifact_sha256=digest(path),
                    record_id=raw.get("identificationModule", {}).get("nctId", "UNKNOWN"),
                    field=f"/armsInterventionsModule/interventions/{index}/description",
                    product_names=tuple(source_names),
                    product_locator=f"/armsInterventionsModule/interventions/{index}/name+otherNames",
                )
                rs = scoped_modality_assertions(
                    candidate["asset_id"], text, source, legacy_fact_ids=(fact["fact_id"],)
                )
                verify(rs, text)
                records.extend(rs)
        ids = sorted({r.assertion_id for r in records})
        h19records.update({r.assertion_id: r.model_dump(mode="json") for r in records})
        links.append(
            {
                "legacy_fact": fact,
                "coexisting_assertion_ids": ids,
                "relationship": "COEXISTING_RAW_FIELD_DIAGNOSTICS_NOT_RETROACTIVE_CAUSAL_LINEAGE",
                "availability": "RAW_INTERVENTION_DESCRIPTION"
                if ids
                else "NO_BOUND_RAW_DESCRIPTION_MENTIONS",
                "legacy_fact_unchanged": True,
            }
        )
    assert lifecycle["fact"]["value"] == "PEPTIDE"
    assert any(
        d["requirement_id"] == "modality.required" and d["status"] == "FAIL"
        for g in lifecycle["gates"]
        for d in g["decisions"]
    )
    assert any(
        r["scope"] == "COMPONENT_LEVEL"
        and r["modality"] == "PEPTIDE"
        and r["legacy_fact_ids"] == [lifecycle["fact"]["fact_id"]]
        for r in h19records.values()
    )
    summary = {
        "controls": len(controls),
        "original_controls": len(old),
        "all_focus_expectations_pass": True,
        "scope_counts_controls": dict(sorted(counts.items())),
        "scope_counts_h19": dict(sorted(Counter(r["scope"] for r in h19records.values()).items())),
        "h19_rows": len(original_rows),
        "h19_modality_facts_linked": len(links),
        "h19_scoped_assertions": len(h19records),
        "h19_facts_without_bound_mentions": sum(not x["coexisting_assertion_ids"] for x in links),
        "legacy_scalar_deltas": 0,
        "saved_candidate_decision_deltas": 0,
        "saved_candidates": len(run["candidates"]),
        "datopotamab_legacy_gate": "FAIL",
        "new_gate_consumers": 0,
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in {
        "witnesses.json": data,
        "h19_legacy_links.json": links,
        "h19_assertions.json": list(h19records.values()),
        "h19_rows_unchanged.json": original_rows,
        "summary.json": summary,
    }.items():
        (output / name).write_text(canonical(value) + "\n")
    (output / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(output.iterdir())}) + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)

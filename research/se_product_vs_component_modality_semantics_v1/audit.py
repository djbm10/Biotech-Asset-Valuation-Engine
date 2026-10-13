"""Offline scope diagnosis, not a production scope classifier."""

import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path

from bve.se.discovery.adapters import QueryVocabulary, _fold
from bve.se.schemas.contracts import ExtractedClaim, NormalizedFact

ROOT = Path("/home/djmann/projects/bve-b8")
STUDY = ROOT / "research/se_product_vs_component_modality_semantics_v1"
# Manual grammatical annotations of the preregistered synthetic population.
# These labels are audit data, never a production recognition algorithm.
SCOPES = {
    "H19_DATO": (
        "COMPONENT_LEVEL",
        "tetrapeptide modifies linker; ADC predicates the whole product",
    ),
    "S01": ("PRODUCT_LEVEL", "predicate nominal describes named product"),
    "S02": ("COMPONENT_LEVEL", "peptide modifies linker possessed by product"),
    "S03": ("PRODUCT_LEVEL", "predicate nominal describes named product"),
    "S04": ("COMPONENT_LEVEL", "antibody-derived modifies binding domain"),
    "S05": ("PRODUCT_LEVEL", "predicate nominal describes named product"),
    "S06": ("COMPONENT_LEVEL", "small molecule modifies payload"),
    "S07": ("PRODUCT_LEVEL", "predicate nominal describes named product"),
    "S08": ("AMBIGUOUS", "assay context does not assert product modality"),
    "S09": ("PRODUCT_LEVEL", "predicate nominal describes named product"),
    "S10": ("AMBIGUOUS", "manufacturing-study context does not assert product modality"),
    "S11": ("PRODUCT_LEVEL", "explicit whole-product composite class ADC"),
    "S12": ("AMBIGUOUS", "comparison object is not the named product"),
    "S13": ("COMPONENT_LEVEL", "tetrapeptide modifies linker; whole product explicitly ADC"),
    "S14": ("COMPONENT_LEVEL", "small molecule modifies payload; whole product explicitly ADC"),
    "S15": ("COMPONENT_LEVEL", "binding domain is constituent of named CAR-T product"),
    "S16": (
        "COMPONENT_LEVEL",
        "delivery vehicle belongs to gene-therapy relationship, not new whole-product virus class",
    ),
    "S17": (
        "RELATIONAL_COMPOSITE",
        "conjugation relates antibody and radionuclide; no constituent inheritance",
    ),
    "S18": (
        "COMPONENT_LEVEL",
        "radionuclide explicitly modifies component; whole modality not stated",
    ),
    "S19": ("AMBIGUOUS", "unbound term list"),
    "S20": ("AMBIGUOUS", "unrelated assay is not product modality"),
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build(output):
    for p, digest in json.loads((STUDY / "inputs.json").read_text()).items():
        assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
    population = json.loads((STUDY / "population.json").read_text())
    vocabulary = QueryVocabulary.for_ontology()
    rows = []
    for row in population["text_controls"]:
        text = row["text"]
        folded = _fold(text)
        matches = []
        for modality, terms in vocabulary.modalities:
            for term in terms:
                start = 0
                while (i := folded.find(term, start)) >= 0:
                    matches.append(
                        {
                            "modality": modality,
                            "term": term,
                            "folded_start": i,
                            "folded_end": i + len(term),
                            "folded_surface": folded[i : i + len(term)],
                            "coordinate_system": "_fold(text); not claimed to be raw offsets",
                        }
                    )
                    start = i + 1
        focus = row["focus_term"]
        pos = text.casefold().find(focus.casefold())
        assert pos >= 0
        scope, reason = SCOPES[row["id"]]
        rows.append(
            {
                **row,
                "focus_span": {
                    "start": pos,
                    "end": pos + len(focus),
                    "surface": text[pos : pos + len(focus)],
                },
                "scope": scope,
                "scope_reason": reason,
                "current_lexical_winner": vocabulary.modality_in(text),
                "all_lexical_hits": sorted(
                    matches, key=lambda x: (x["folded_start"], x["modality"], x["term"])
                ),
                "current_scope_field": None,
                "future_focus_may_gate_product": scope == "PRODUCT_LEVEL",
                "future_requirement": "whole-product subject and predicate relation must be independently preserved; otherwise no product gate fact",
                "production_change": False,
            }
        )
    run = json.loads(Path("/home/djmann/se_runs/heldout_h19_v4/result.json").read_text())
    claim = next(c for c in run["claims"] if c["claim_id"] == "claim:2022030306a59db4acec")
    fact = next(f for f in run["facts"] if f["fact_id"] == "fact:71c28d48f9461eb004d3")
    asset = next(a for a in run["candidates"] if a["asset_id"] == fact["subject_id"])
    gates = [g for g in run["gate_evaluations"] if g["subject_id"] == fact["subject_id"]]
    original = json.loads(
        gzip.decompress(
            (
                ROOT
                / "research/se_h19_candidate_qualification_diagnosis_v1/results/row_audit.json.gz"
            ).read_bytes()
        )
    )
    control_tests = []
    for path in population["existing_controls"]:
        tree = ast.parse((ROOT / path).read_text())
        control_tests.extend(
            {
                "file": path,
                "test": node.name,
                "line": node.lineno,
                "scope_audit": "Existing test expectation retained; see source for structured whole-product or gate/qualification control. Not relabeled by synthetic scope annotations.",
            }
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    summary = {
        "architecture_gate": "STOP_SCOPE_RELATION_ABSENT",
        "production_implementation": "NOT_STARTED",
        "text_controls": len(rows),
        "scope_counts": {
            s: sum(r["scope"] == s for r in rows)
            for s in ["PRODUCT_LEVEL", "COMPONENT_LEVEL", "RELATIONAL_COMPOSITE", "AMBIGUOUS"]
        },
        "existing_test_functions": len(control_tests),
        "h19_rows_preserved": len(original),
        "qualification_and_modality_decision_changes": 0,
        "claim_fields": list(ExtractedClaim.model_fields),
        "fact_fields": list(NormalizedFact.model_fields),
        "contract": "DESIGN_ONLY_NOT_IMPLEMENTATION_READY",
    }
    output.mkdir(parents=True, exist_ok=False)
    for name, value in {
        "scope_table.json": rows,
        "datopotamab_lifecycle.json": {
            "claim": claim,
            "fact": fact,
            "candidate": asset,
            "gates": gates,
        },
        "h19_rows.json.gz": original,
        "existing_control_inventory.json": control_tests,
        "summary.json": summary,
    }.items():
        content = (canonical(value) + "\n").encode()
        (output / name).write_bytes(
            gzip.compress(content, mtime=0) if name.endswith(".gz") else content
        )
    (output / "hashes.json").write_text(
        canonical(
            {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())}
        )
        + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)

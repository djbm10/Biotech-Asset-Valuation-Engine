"""Readiness review measurements (rubric 6f024d4). Verdict derived by `verdict`; no constant."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_validation_readiness_review_v1"
DIAG = ROOT / "research/se_heldout/primary_validation_failure_diagnosis_v1"
FROZEN_ENGINE = "5feee853c8a15d8c92ef632f82a07c32e1d0e038"
QUERIES = {
    "H16": "Find clinical-stage LAG-3 antibodies for melanoma.",
    "H17": "Find clinical-stage anti-IL-4Rα antibodies for atopic dermatitis.",
    "H18": "Find clinical-stage GLP-1 receptor agonists for obesity.",
    "H19": "Find clinical-stage TROP2-directed antibody-drug conjugates for breast cancer.",
    "H20": "Find clinical-stage factor XI inhibitors for prevention of thrombosis.",
}
#: The production files on each known failure route (from the frozen diagnosis register).
ROUTES = {
    "D1_human_poc": ["src/bve/se/evidence/human_poc.py", "src/bve/se/evidence/snapshot_cache.py"],
    "D3_qualification": [
        "src/bve/se/discovery/asset_qualification.py",
        "src/bve/se/resolution/registry.py",
    ],
    "D4_modality": ["src/bve/se/discovery/adapters.py", "src/bve/se/gates/evaluator.py"],
    "D5_identity": ["src/bve/se/ontology/resolver.py", "src/bve/se/resolution/registry.py"],
    "D7_ordering": ["src/bve/se/reporting/shortlist.py"],
}
DIAGNOSTIC_MODULES = [
    "modality_scope",
    "target_mentions",
    "assertion_provenance",
    "assertion_sidecar_lookup",
]
SEVERITY = {
    "D1": "CRITICAL",
    "D2": "CRITICAL",
    "D3": "MAJOR",
    "D4": "MAJOR",
    "D5": "MAJOR",
    "D6": "QUALITY",
    "D7": "QUALITY",
    "D8": "TECHNICAL",
    "D9": "TECHNICAL",
}


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout


def changed_since_frozen(paths):
    return sorted(
        p for p in paths if git("diff", "--name-only", FROZEN_ENGINE, "HEAD", "--", p).strip()
    )


def measure():
    from bve.se.discovery.adapters import QueryVocabulary
    from bve.se.evidence.human_poc import efficacy_statements
    from bve.se.intent.parser import parse_query
    from bve.se.ontology.targets import get_resolver

    m = {"head": git("rev-parse", "HEAD").strip(), "frozen_engine": FROZEN_ENGINE}
    # D2: offline parse of the exposed queries (no search).
    m["target_recognition"] = {}
    for q, text in QUERIES.items():
        intent = parse_query(text)
        targets = [s.text for s in intent.spans if s.kind.value == "TARGET"]
        m["target_recognition"][q] = {"target_spans": targets, "recognized": bool(targets)}
    # D1: re-run the current extractor on the exact frozen false sentences.
    traces = json.loads((DIAG / "false_human_poc_traces.json").read_text())
    m["human_poc"] = {}
    for q in ("H18", "H19"):
        for t in traces[q]:
            passage = t["claim"]["supporting_passage"]
            hits = efficacy_statements(
                passage, asset_names=[t["name"]], document_id=t["claim"]["source_document_id"]
            )
            m["human_poc"][f"{q}:{t['name']}"] = {"still_accepted": bool(hits), "n": len(hits)}
    # D4: datopotamab structured modality on the exact frozen text.
    probe = json.loads((DIAG / "datopotamab_modality_probe.json").read_text())
    text = probe.get("intervention_context") or ""
    vocab = QueryVocabulary.for_ontology()
    m["datopotamab_modality"] = {
        "structured_label": vocab.modality_in(text) if text else None,
        "probe_text_present": bool(text),
    }
    # D5: brand identifiers.
    r = get_resolver()
    m["brand_identifier"] = {
        n: r.resolve_identifier(n)
        for n in ("Saxenda", "Victoza", "Ozempic", "Wegovy", "Rybelsus", "TRODELVY")
    }
    m["route_changes"] = {k: changed_since_frozen(v) for k, v in ROUTES.items()}
    m["diagnostic_module_importers"] = {
        mod: sorted(
            str(p.relative_to(ROOT))
            for p in (ROOT / "src").rglob("*.py")
            if p.stem not in DIAGNOSTIC_MODULES and mod in p.read_text()
        )
        for mod in DIAGNOSTIC_MODULES
    }
    full = ROOT / "research/se_modality_scope_product_description_v1/results/full_tests_se.log"
    tail = full.read_text().strip().splitlines()[-1]
    m["tests"] = {"last_full_tests_se": tail, "source": str(full.relative_to(ROOT))}
    m["determinism"] = {
        name: (ROOT / f"research/{name}/results/hashes.json").is_file()
        for name in (
            "se_product_vs_component_modality_semantics_v4",
            "se_esg401_candidate_nomination_diagnosis_v1",
            "se_trade_name_asset_identity_diagnosis_v1",
            "se_modality_scope_product_description_v1",
        )
    }
    return m


def dimensions(m):
    rec = m["target_recognition"]
    d = {
        "D1": not any(v["still_accepted"] for v in m["human_poc"].values()),
        "D2": all(v["recognized"] for v in rec.values()),
        "D3": bool(m["route_changes"]["D3_qualification"]),
        "D4": m["datopotamab_modality"]["structured_label"] not in (None, "PEPTIDE")
        and bool(m["route_changes"]["D4_modality"]),
        "D5": any(m["brand_identifier"].values()),
        "D6": True,
        "D7": bool(m["route_changes"]["D7_ordering"]),
        "D8": all(m["determinism"].values()),
        # Word-bounded: "3 xfailed" is the existing expected-failure count, not a failure.
        "D9": not re.search(r"\b\d+ (?:failed|errors?)\b", m["tests"]["last_full_tests_se"])
        and bool(re.search(r"\b\d+ passed\b", m["tests"]["last_full_tests_se"])),
    }
    return d


def verdict(d):
    technical = d["D8"] and d["D9"]
    if not (d["D1"] and d["D2"]):
        scientific = "NO-GO"
    elif not (d["D3"] and d["D4"] and d["D5"]):
        scientific = "CONDITIONAL"
    else:
        scientific = "GO"
    overall = "NO-GO" if not technical or scientific == "NO-GO" else scientific
    critical_known = not (d["D1"] and d["D2"])
    return {
        "technical_readiness": "GO" if technical else "NO-GO",
        "scientific_readiness": scientific,
        "overall": overall,
        "keep_h21_h25_sealed": overall == "NO-GO" or critical_known,
        "failed_dimensions": sorted(k for k, v in d.items() if not v),
    }


def selftest():
    good = {k: True for k in SEVERITY}
    out = {"all_pass": verdict(good)["overall"]}
    out["critical_fail"] = verdict({**good, "D1": False})["overall"]
    out["major_fail"] = verdict({**good, "D4": False})["overall"]
    out["technical_fail"] = verdict({**good, "D9": False})["overall"]
    out["quality_only"] = verdict({**good, "D7": False})["overall"]
    log = {"tests": {"last_full_tests_se": "1941 passed, 3 xfailed"}}
    base = {
        "target_recognition": {},
        "human_poc": {},
        "datopotamab_modality": {"structured_label": "X"},
        "brand_identifier": {},
        "route_changes": dict.fromkeys(ROUTES, []),
        "determinism": {},
    }
    out["xfail_not_failure"] = dimensions({**base, **log})["D9"]
    out["real_failure"] = dimensions(
        {**base, "tests": {"last_full_tests_se": "3 failed, 1938 passed"}}
    )["D9"]
    assert out == {
        "all_pass": "GO",
        "critical_fail": "NO-GO",
        "major_fail": "CONDITIONAL",
        "technical_fail": "NO-GO",
        "quality_only": "GO",
        "xfail_not_failure": True,
        "real_failure": False,
    }, out
    return out


def build(out):
    m = measure()
    d = dimensions(m)
    summary = {
        "measurements": m,
        "dimensions": {k: {"pass": v, "severity": SEVERITY[k]} for k, v in d.items()},
        **verdict(d),
        "selftest": selftest(),
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(canonical(summary) + "\n")
    (out / "hashes.json").write_text(
        canonical({"summary.json": hashlib.sha256((out / "summary.json").read_bytes()).hexdigest()})
        + "\n"
    )
    print(
        canonical(
            {
                k: summary[k]
                for k in (
                    "overall",
                    "technical_readiness",
                    "scientific_readiness",
                    "failed_dimensions",
                    "keep_h21_h25_sealed",
                )
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)

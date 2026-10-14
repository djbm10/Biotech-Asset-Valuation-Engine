"""Diagnose source structures for the 293 frozen v3 modality facts. Diagnostic only, not production."""

import argparse
import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from bve.se.ontology.modality import modality_aliases

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_modality_product_description_coverage_v1"
V3 = ROOT / "research/se_product_vs_component_modality_semantics_v3"
RUNS = {
    r: Path.home() / "se_runs" / r / "result.json" for r in ("tac01_protoid_v1", "mint5_protoid_v1")
}
ELIGIBLE = ("COPULA", "APPOSITIVE", "CLASS_OF", "NAME_SELF_DESCRIBING", "STRUCTURED_OTHERNAMES")
OTHER = ("REGISTRY_CATEGORY", "CO_OCCURRENCE", "NAME_ABSENT", "MODALITY_ABSENT", "NO_SOURCE")
GAP = r"(?:[^\s.;\n]+\s+){0,8}?"
PAREN = r"(?:\s*\([^)]*\))?"


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def alias_re(value):
    terms = sorted({a for a in modality_aliases(value) if a != value}, key=len, reverse=True)
    return (
        r"(?:"
        + "|".join(r"[\s_-]+".join(map(re.escape, re.split(r"[\s_-]+", t))) for t in terms)
        + r")\b"
    )


def expand(names):
    out = set()
    for n in names:
        if not n:
            continue
        out.add(n.strip())
        m = re.fullmatch(r"\s*(.+?)\s*\(([^)]+)\)\s*", n)
        if m:
            out.update({m.group(1).strip(), m.group(2).strip()})
    return sorted(x for x in out if len(x) >= 2)


def classify(text, names, value, structured=None):
    """Return the set of structure classes for one fact. structured = CT.gov intervention row."""
    found = set()
    m_re = alias_re(value)
    if structured is not None:
        if re.search(r"\b" + m_re, structured.get("name") or "", re.I):
            found.add("NAME_SELF_DESCRIBING")
        if any(re.search(r"\b" + m_re, o, re.I) for o in structured.get("otherNames") or []):
            found.add("STRUCTURED_OTHERNAMES")
    if text is None:
        return found or {"NO_SOURCE"}
    has_m = re.search(r"\b" + m_re, text, re.I)
    present = [n for n in names if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", text, re.I)]
    for n in present:
        nm = r"(?<!\w)" + re.escape(n) + r"(?!\w)" + PAREN
        if re.search(nm + r"\s+(?:is|are)\s+(?:an?\s+)?" + GAP + m_re, text, re.I):
            found.add("COPULA")
        if re.search(nm + r"\s*,\s+an?\s+" + GAP + m_re, text, re.I):
            found.add("APPOSITIVE")
        if re.search(
            nm
            + r"[^.;\n]*?\b(?:is|are)\b[^.;\n]*?\b(?:in|of)\s+the\s+class\s+of\b[^.;\n]*?"
            + m_re,
            text,
            re.I,
        ):
            found.add("CLASS_OF")
    if has_m and re.search(r"\b[A-Za-z]+/" + m_re + r"\s*:", text, re.I):
        found.add("REGISTRY_CATEGORY")
    if not any(c in found for c in ELIGIBLE):
        if not has_m and not found:
            found.add("MODALITY_ABSENT")
        elif not present and not found:
            found.add("NAME_ABSENT")
        elif "REGISTRY_CATEGORY" not in found:
            found.add("CO_OCCURRENCE")
    return found


def primary(classes):
    return next(c for c in ELIGIBLE + OTHER if c in classes)


def source_for(claim, doc, candidate):
    path = doc.get("snapshot_path")
    if not path or not Path(path).exists():
        return None, [], None
    raw = json.loads(Path(path).read_text())
    if claim["extraction_method"] == "clinicaltrials_structured":
        row = json.loads(claim["supporting_passage"])
        snap = (raw.get("armsInterventionsModule") or {}).get("interventions") or []
        row = next((r for r in snap if r.get("name") == row.get("name")), row)
        names = expand([row.get("name"), *(row.get("otherNames") or [])])
        return row.get("description"), names, row
    return raw.get("text"), expand(candidate.get("aliases") or []), None


def measure():
    rows = []
    for run, path in RUNS.items():
        d = json.loads(path.read_text())
        claims = {c["claim_id"]: c for c in d["claims"]}
        docs = {x["document_id"]: x for x in d["source_documents"]}
        cands = {c["asset_id"]: c for c in d["candidates"]}
        admitted = {
            i
            for g in d["gate_evaluations"]
            for x in g["decisions"]
            if x["requirement_id"] == "modality.required"
            for i in x.get("observed_fact_ids") or []
        }
        for f in (x for x in d["facts"] if x["fact_type"] == "modality_id"):
            classes, routes, fields = set(), set(), set()
            for cid in f["supporting_claim_ids"]:
                c = claims[cid]
                text, names, row = source_for(
                    c, docs[c["source_document_id"]], cands[f["subject_id"]]
                )
                routes.add(c["extraction_method"])
                fields.update(k for k in (row or {}) if row.get(k)) if row else fields.add(
                    "text" if text else "none"
                )
                classes |= classify(text, names, f["value"], row)
            if any(c in classes for c in ELIGIBLE):
                classes -= set(OTHER) - {"REGISTRY_CATEGORY"}
            rows.append(
                {
                    "run": run,
                    "fact_id": f["fact_id"],
                    "value": f["value"],
                    "admitted": f["fact_id"] in admitted,
                    "routes": sorted(routes),
                    "fields": sorted(fields),
                    "classes": sorted(classes),
                    "primary": primary(classes),
                }
            )
    return rows


def criteria(rows, adjudication):
    # Fact ids are content-addressed and recur across runs: key rows by (run, fact_id).
    # Adjudicated facts are the admitted TAC01 rows.
    keys = {(r["run"], r["fact_id"]) for r in rows}
    by = {r["fact_id"]: r for r in rows if r["run"] == "tac01_protoid_v1"}
    elig = lambda fid: [c for c in by[fid]["classes"] if c in ELIGIBLE] if fid in by else None  # noqa: E731
    adj = {k: v for k, v in adjudication.items() if not k.startswith("_")}
    c1 = [k for k, v in adj.items() if not v["whole_product"] and elig(k) != []]
    c2 = [
        k
        for k, v in adj.items()
        if v["whole_product"] and (bool(elig(k)) != (v["support_type"] in ELIGIBLE))
    ]
    c3 = (
        len(rows) == 293
        and len(keys) == 293
        and all(r["primary"] in ELIGIBLE + OTHER for r in rows)
    )
    req = {"C1_safety": not c1, "C2_explicit_recall": not c2, "C3_accounting": c3}
    failing = [k for k, v in req.items() if not v]
    return {
        "requirements": req,
        "first_failing": failing[0] if failing else None,
        "verdict": "JUSTIFIED" if not failing else "STOP",
        "c1_false_with_eligible": c1,
        "c2_mismatch": c2,
    }


def selftest(rows, adjudication):
    adj = {k: v for k, v in adjudication.items() if not k.startswith("_")}
    good = copy.deepcopy(rows)
    for r in good:
        if r["fact_id"] in adj:
            v = adj[r["fact_id"]]
            r["classes"] = (
                [v["support_type"]] if v["support_type"] in ELIGIBLE else ["CO_OCCURRENCE"]
            )
            r["primary"] = r["classes"][0]
    out = {"valid": criteria(good, adjudication)["verdict"]}
    bad = copy.deepcopy(good)
    next(
        r
        for r in bad
        if r["run"] == "tac01_protoid_v1" and r["fact_id"] == "fact:e11600a1b72953fb2aff"
    )["classes"] = ["NAME_SELF_DESCRIBING"]
    out["false_fact_certified"] = criteria(bad, adjudication)["first_failing"]
    over = copy.deepcopy(good)
    next(
        r
        for r in over
        if r["run"] == "tac01_protoid_v1" and r["fact_id"] == "fact:3a4728df3229493747d4"
    )["classes"] = ["COPULA"]
    out["coreference_overreach"] = criteria(over, adjudication)["first_failing"]
    miss = copy.deepcopy(good)
    next(
        r
        for r in miss
        if r["run"] == "tac01_protoid_v1" and r["fact_id"] == "fact:a21e40454f36ee328210"
    )["classes"] = ["CO_OCCURRENCE"]
    out["explicit_true_missed"] = criteria(miss, adjudication)["first_failing"]
    out["unregistered_population"] = criteria(good[:-1], adjudication)["first_failing"]
    assert out == {
        "valid": "JUSTIFIED",
        "false_fact_certified": "C1_safety",
        "coreference_overreach": "C2_explicit_recall",
        "explicit_true_missed": "C2_explicit_recall",
        "unregistered_population": "C3_accounting",
    }, out
    return out


def build(out):
    for line in (V3 / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        if "se_runs" in path:
            assert digest(path) == sha, path
    adjudication = json.loads((STUDY / "adjudication.json").read_text())
    rows = measure()
    crit = criteria(rows, adjudication)
    adm = {r["fact_id"]: r for r in rows if r["admitted"]}
    distinct = {r["fact_id"] for r in rows}
    summary = {
        **crit,
        "selftest": selftest(rows, adjudication),
        "fact_rows": len(rows),
        "distinct_fact_ids": len(distinct),
        "fact_ids_in_both_runs": sum(
            1 for f in distinct if len({r["run"] for r in rows if r["fact_id"] == f}) == 2
        ),
        "primary_distinct_tac01_first": dict(
            sorted(
                Counter(
                    next(r["primary"] for r in rows if r["fact_id"] == f) for f in distinct
                ).items()
            )
        ),
        "primary_all": dict(sorted(Counter(r["primary"] for r in rows).items())),
        "primary_by_route_value": dict(
            sorted(
                Counter(
                    f"{'+'.join(r['routes'])}|{r['value']}|{r['primary']}" for r in rows
                ).items()
            )
        ),
        "any_class_all": dict(sorted(Counter(c for r in rows for c in r["classes"]).items())),
        "eligible_any": sum(any(c in ELIGIBLE for c in r["classes"]) for r in rows),
        "admitted": {
            k: {
                "classes": v["classes"],
                "adjudicated_true": adjudication[k]["whole_product"],
                "support_type": adjudication[k]["support_type"],
            }
            for k, v in sorted(adm.items())
        },
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {"rows.json": rows, "summary.json": summary}.items():
        (out / name).write_text(canonical(value) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(canonical(summary))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)

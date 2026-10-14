"""Target alias authority-source readiness audit (prereg 7d5c7ad). Verdict derived by `decide`."""

import argparse
import copy
import hashlib
import json
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from bve.se.discovery.query import compile_problem_queries
from bve.se.intent.compiler import compile_intent
from bve.se.intent.parser import _tokenize, parse_query
from bve.se.ontology.records import AliasType, EntityType, normalize_lookup_key
from bve.se.ontology.targets import get_resolver
from bve.se.schemas.contracts import BuyerIdentity

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_target_alias_authority_source_v1"
COV = ROOT / "research/se_target_query_alias_coverage_v1"
HGNC = Path.home() / "se_runs/target_component_identity_authority_evidence_v1/raw/hgnc.json"
NCIT_TYPES = ROOT / "data/se/ontology/ncit/ncit_26.08e_entity_types.json"
HGNC_FIELDS = ("name", "alias_symbol", "alias_name", "prev_symbol", "prev_name")
PROTEIN = "Amino Acid, Peptide, or Protein"
BUYER = BuyerIdentity(buyer_id="audit", name="audit", as_of_date=date(2026, 10, 14))
H17 = "Find clinical-stage anti-IL-4Rα antibodies for atopic dermatitis."
H20 = "Find clinical-stage factor XI inhibitors for prevention of thrombosis."


def canonical(x):
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def key(s):
    return normalize_lookup_key(s)


def values(doc, field):
    v = doc.get(field)
    return [v] if isinstance(v, str) else list(v or [])


def load_sources():
    hgnc = json.loads(HGNC.read_text())["response"]["docs"]
    by_ensembl = {d["ensembl_gene_id"]: d for d in hgnc if d.get("ensembl_gene_id")}
    hgnc_claim = defaultdict(set)
    for d in hgnc:
        for f in ("symbol", *HGNC_FIELDS):
            for v in values(d, f):
                hgnc_claim[key(v)].add(d["hgnc_id"])
    ncit = json.loads((COV / "ncit_identifier_records.json").read_text())
    gene_hgnc = {r["code"]: r["P369"] for r in ncit if r["P369"]}
    ncit_gene = {}
    for r in ncit:
        if PROTEIN in r["P106"]:
            ncit_gene[r["code"]] = sorted(
                {h for g in r["encoded_by"] for h in gene_hgnc.get(g, [])}
            )
    ncit_claim = defaultdict(set)
    for r in ncit:
        if PROTEIN in r["P106"]:
            for s in r["P90"]:
                ncit_claim[key(s)].add(tuple(ncit_gene[r["code"]]) or (r["code"],))
    nonproduct = set(json.loads(NCIT_TYPES.read_text())["non_product_names"])
    return {
        "hgnc": hgnc,
        "by_ensembl": by_ensembl,
        "hgnc_claim": hgnc_claim,
        "ncit": ncit,
        "ncit_gene": ncit_gene,
        "ncit_claim": ncit_claim,
        "nonproduct": nonproduct,
    }


def compact(s):
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def candidates_for(entity_row, src, r):
    """All HGNC + NCIt-protein strings for one entity that are not already its runtime keys."""
    out = []
    links = entity_row["identifier_links"]
    cid = r.resolve(
        entity_row["authority_target_symbol"], entity_type=EntityType.TARGET
    ).canonical_id
    hg = next(
        (src["by_ensembl"][e] for e in links.get("ensembl", []) if e in src["by_ensembl"]), None
    )
    if hg:
        for f in HGNC_FIELDS:
            out += [(v, f"hgnc:{f}", hg["hgnc_id"]) for v in values(hg, f)]
        uniprot = set(links.get("uniprot", []))
        for rec in src["ncit"]:
            if PROTEIN in rec["P106"] and (
                hg["hgnc_id"] in src["ncit_gene"][rec["code"]] or set(rec["P93"]) & uniprot
            ):
                out += [(s, f"ncit:{rec['code']}", hg["hgnc_id"]) for s in rec["P90"]]
    existing = (
        {k for (_, k), hits in r._lookup.items() if any(c == cid for _, c in hits)}
        if cid
        else set()
    )
    seen, rows = set(), []
    for text, source, hgnc_id in out:
        k = key(text)
        if not k or k in existing or (k, source) in seen:
            continue
        seen.add((k, source))
        rows.append({"text": text, "source": source, "hgnc_id": hgnc_id, "entity": cid})
    return cid, rows


def classify(row, src, r):
    k = key(row["text"])
    runtime = set(r.claimants_of(row["text"], EntityType.TARGET))
    hg = src["hgnc_claim"].get(k, set())
    nc = src["ncit_claim"].get(k, set())
    nc_genes = {g for t in nc for g in t}
    reasons = []
    if runtime - {row["entity"]}:
        reasons.append("CONFLICT_RUNTIME")
    if len(hg) > 1 or (nc_genes and nc_genes - {row["hgnc_id"]}):
        reasons.append("AMBIGUOUS_AUTHORITY")
    if compact(row["text"]) in src["nonproduct"]:
        reasons.append("CROSS_TYPE")
    status = reasons[0] if reasons else "CERTIFIED"
    tokens = len(_tokenize(row["text"]))
    return {
        **row,
        "status": status,
        "reasons": reasons,
        "runtime_claimants": sorted(runtime),
        "hgnc_claimants": sorted(hg),
        "ncit_claimant_genes": sorted(nc_genes),
        "tokens": tokens,
        "reachable": status == "CERTIFIED" and tokens <= 2,
    }


@contextmanager
def injected(r, aliases):
    """Research-only: add candidate aliases to this process's resolver, then restore it."""
    saved = copy.deepcopy(r._lookup)
    try:
        for text, cid in aliases:
            r._lookup[(EntityType.TARGET, key(text))].append((AliasType.SYNONYM, cid))
        yield
    finally:
        r._lookup.clear()
        r._lookup.update(saved)


def chain(query):
    intent = parse_query(query)
    targets = [s.text for s in intent.spans if s.kind.value == "TARGET"]
    try:
        problem = compile_intent(intent, buyer=BUYER)
        plans = compile_problem_queries(problem)
        dumped = json.dumps(problem.model_dump(mode="json"))
        ids = sorted({x.split('"')[0] for x in dumped.split("TARGET:")[1:]})
        return {"targets": targets, "compiled": True, "plans": len(plans), "target_ids": ids}
    except Exception as e:  # noqa: BLE001 - a refusal is a measured outcome
        return {"targets": targets, "compiled": False, "error": type(e).__name__}


def exact_spelling_in_authorities(text, src):
    k = key(text)
    return {
        "hgnc": k in src["hgnc_claim"],
        "ncit_protein": k in src["ncit_claim"],
        "ncit_nonproduct": compact(text) in src["nonproduct"],
    }


def decide(rows, n_entities, controls_ok, h17, h20, deterministic=True):
    reach_entities = {r["entity"] for r in rows if r["reachable"]}
    j1 = len(reach_entities) / n_entities >= 0.10
    j2 = controls_ok and not any(
        r["status"] == "CERTIFIED" and (r["reasons"] or set(r["runtime_claimants"]) - {r["entity"]})
        for r in rows
    )
    j3 = any(h17["exact_spelling"].values())
    j4 = (
        h20["certified_f11"]
        and h20["fxi_chain"].get("target_ids") == ["F11"]
        and h20["injected_chain"].get("target_ids") == ["F11"]
    )
    req = {
        "J1_coverage": j1,
        "J2_safety": j2,
        "J3_h17_authority_spelling": j3,
        "J4_h20_chain": j4,
        "J5_deterministic": deterministic,
    }
    if all(req.values()):
        v = "JUSTIFIED"
    elif all(v for k, v in req.items() if k != "J3_h17_authority_spelling"):
        v = "JUSTIFIED_EXCLUDING_H17"
    else:
        v = "STOP"
    return {
        "requirements": req,
        "verdict": v,
        "entities_with_reachable_certified": len(reach_entities),
        "coverage_fraction": len(reach_entities) / n_entities,
    }


def selftest(rows, n, h17, h20):
    good_rows = [
        {
            "entity": f"E{i}",
            "status": "CERTIFIED",
            "reasons": [],
            "runtime_claimants": [f"E{i}"],
            "reachable": True,
        }
        for i in range(n)
    ]
    ok17 = {"exact_spelling": {"hgnc": True}}
    ok20 = {
        "certified_f11": True,
        "fxi_chain": {"target_ids": ["F11"]},
        "injected_chain": {"target_ids": ["F11"]},
    }
    out = {"certified_unique_alias": decide(good_rows, n, True, ok17, ok20)["verdict"]}
    false_unique = good_rows + [
        {
            "entity": "E0",
            "status": "CERTIFIED",
            "reasons": [],
            "runtime_claimants": ["E0", "OTHER"],
            "reachable": True,
        }
    ]
    out["false_unique_with_claimants"] = decide(false_unique, n, True, ok17, ok20)["verdict"]
    out["wrong_subunit_control"] = decide(good_rows, n, False, ok17, ok20)["verdict"]
    cross = good_rows + [
        {
            "entity": "E1",
            "status": "CERTIFIED",
            "reasons": ["CROSS_TYPE"],
            "runtime_claimants": ["E1"],
            "reachable": True,
        }
    ]
    out["protein_measurement_error"] = decide(cross, n, True, ok17, ok20)["verdict"]
    lost = {**ok20, "injected_chain": {"target_ids": []}}
    out["downstream_identity_loss"] = decide(good_rows, n, True, ok17, lost)["verdict"]
    out["unregistered_population_change"] = decide(good_rows[: n // 20], n, True, ok17, ok20)[
        "verdict"
    ]
    out["no_h17_spelling"] = decide(good_rows, n, True, {"exact_spelling": {"hgnc": False}}, ok20)[
        "verdict"
    ]
    assert out == {
        "certified_unique_alias": "JUSTIFIED",
        "false_unique_with_claimants": "STOP",
        "wrong_subunit_control": "STOP",
        "protein_measurement_error": "STOP",
        "downstream_identity_loss": "STOP",
        "unregistered_population_change": "STOP",
        "no_h17_spelling": "JUSTIFIED_EXCLUDING_H17",
    }, out
    return out


def build(out):
    for line in (STUDY / "freeze_hashes.txt").read_text().splitlines():
        sha, path = line.split(maxsplit=1)
        assert digest(path) == sha, path
    r = get_resolver()
    src = load_sources()
    pop = json.loads((COV / "survey_population.json").read_text())
    entities = {}
    for p in pop:
        if p["kind"] == "approved_symbol":
            entities.setdefault(p["authority_record_key"], p)
    assert len(entities) == 192, len(entities)
    rows = []
    for row in entities.values():
        cid, cands = candidates_for(row, src, r)
        if cid:
            rows += [classify(c, src, r) for c in cands]
    rows.sort(key=lambda x: (x["entity"], key(x["text"]), x["source"]))
    # Controls: no CERTIFIED candidate on IL4R/F11 equals a frozen negative control spelling.
    controls = json.loads((COV / "survey_controls.json").read_text())
    negatives = {key(c["text"]) for c in controls if "expected_entity" not in c}
    il4r_f11 = []
    for sym in ("IL4R", "F11"):
        seed = (
            next(
                p
                for p in pop
                if p["kind"] == "approved_symbol" and p["authority_target_symbol"] == sym
            )
            if any(p["authority_target_symbol"] == sym for p in pop)
            else None
        )
        if seed is None:
            hg = next(d for d in src["hgnc"] if d["symbol"] == sym)
            seed = {
                "identifier_links": {
                    "ensembl": [hg["ensembl_gene_id"]],
                    "uniprot": hg.get("uniprot_ids") or [],
                },
                "authority_target_symbol": sym,
            }
        cid, cands = candidates_for(seed, src, r)
        il4r_f11 += [classify(c, src, r) for c in cands]
    leaked = [c for c in il4r_f11 if c["status"] == "CERTIFIED" and key(c["text"]) in negatives]
    controls_ok = not leaked
    f11_factor = [c for c in il4r_f11 if key(c["text"]) == key("factor XI")]
    with injected(r, [("factor XI", "TARGET:F11")]):
        injected_chain = chain(H20)
    h20 = {
        "candidates": f11_factor,
        "certified_f11": any(c["status"] == "CERTIFIED" for c in f11_factor),
        "fxi_chain": chain(H20.replace("factor XI", "FXI")),
        "injected_chain": injected_chain,
        "current_chain": chain(H20),
    }
    h17 = {
        "exact_spelling": exact_spelling_in_authorities("IL-4Rα", src),
        "current_chain": chain(H17),
        "il4r_new_certified": [
            c["text"]
            for c in il4r_f11
            if c["entity"] == "TARGET:IL4R" and c["status"] == "CERTIFIED"
        ],
    }
    dec = decide(rows, 192, controls_ok, h17, h20)
    summary = {
        **dec,
        "selftest": selftest(rows, 192, h17, h20),
        "candidate_names": len(rows),
        "status_counts": dict(sorted(Counter(r["status"] for r in rows).items())),
        "reachable_certified": sum(r["reachable"] for r in rows),
        "certified_by_source": dict(
            sorted(
                Counter(
                    r["source"].split(":")[0]
                    + ":"
                    + (r["source"].split(":")[1] if r["source"].startswith("hgnc") else "protein")
                    for r in rows
                    if r["status"] == "CERTIFIED"
                ).items()
            )
        ),
        "certified_token_lengths": dict(
            sorted(Counter(min(r["tokens"], 5) for r in rows if r["status"] == "CERTIFIED").items())
        ),
        "controls_ok": controls_ok,
        "control_leaks": leaked,
        "h17": h17,
        "h20": h20,
        "il4r_f11_candidates": il4r_f11,
        "sources": {
            "hgnc": "2026-10-13 complete (45,277)",
            "ncit_identifier_records": "26.09d",
            "ncit_nonproduct": "26.08e",
            "uniprot": "2026_03 (348 accessions; not used for coverage)",
            "runtime": "chembl_ChEMBL_37__open_targets_26.06__resolver_v2",
        },
        "production_changes": 0,
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in {"candidates.json": rows, "summary.json": summary}.items():
        (out / name).write_text(canonical(value) + "\n")
    (out / "hashes.json").write_text(
        canonical({p.name: digest(p) for p in sorted(out.iterdir())}) + "\n"
    )
    print(
        canonical(
            {
                k: summary[k]
                for k in ("verdict", "requirements", "coverage_fraction", "status_counts")
            }
        )
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    build(p.parse_args().output)

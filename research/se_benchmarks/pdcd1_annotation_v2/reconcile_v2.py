"""Reconcile the blind V2 adjudications under protocol V2.6.

Reconciliation may apply only rules frozen in ANNOTATION_PROTOCOL_V2.md. It may not admit a
source, relax V2.3, revisit V1, or recover an A3.3 withholding. Where the frozen precedence
does not resolve a disagreement, the entry stays UNCERTAIN_V2.
"""
import json, pathlib, collections

W = pathlib.Path("work")
subj = [json.loads(l) for l in open("v2_subject_set.jsonl")]
track = {r["benchmark_id"]: r["track"] for r in subj}
entry = {r["benchmark_id"]: r["gold_entry"] for r in subj}


def load(prefix):
    out = {}
    for p in sorted(W.glob(f"{prefix}_chunk_*.jsonl")):
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[r["benchmark_id"]] = r
    return out


A, B = load("A"), load("B")
missing = [b for b in track if b not in A or b not in B]
if missing:
    raise SystemExit(f"incomplete adjudication for {len(missing)} entries: {missing}")

rank = lambda r: r.get("source_rank") or 99
ledger, counts = [], collections.Counter()

for b in track:
    a, bb = A[b], B[b]
    va, vb = a["target_relevance_v2"], bb["target_relevance_v2"]

    if va == vb:
        basis, verdict, win = "AGREE", va, a if rank(a) <= rank(bb) else bb
    elif {va, vb} == {"UNCERTAIN_V2", "PDCD1_MATCH"} or {va, vb} == {"UNCERTAIN_V2", "NON_PDCD1"}:
        # One adjudicator found an admissible source and the other did not. The protocol's
        # evidence standard is met by the one that did; not finding a source is not evidence
        # against it. The verdict must still rest on a cited, quoted, admissible source.
        win = a if va != "UNCERTAIN_V2" else bb
        if win.get("source_reference") and win.get("evidence_excerpt") and rank(win) <= 5:
            basis, verdict = "SINGLE_ADJUDICATOR_EVIDENCE", win["target_relevance_v2"]
        else:
            basis, verdict, win = "UNSUPPORTED_CLAIM", "UNCERTAIN_V2", win
    else:
        # PDCD1_MATCH vs NON_PDCD1: a real conflict. V2.2 precedence resolves it only when one
        # side cites a strictly higher-ranked admissible source.
        if rank(a) < rank(bb):
            basis, verdict, win = "PRECEDENCE_RESOLVED", va, a
        elif rank(bb) < rank(a):
            basis, verdict, win = "PRECEDENCE_RESOLVED", vb, bb
        else:
            basis, verdict, win = "CONFLICT_UNRESOLVED", "UNCERTAIN_V2", a

    counts[basis] += 1
    counts[f"verdict:{verdict}"] += 1
    ledger.append({
        "benchmark_id": b, "entry": entry[b], "track": track[b],
        "v1_target_relevance": "UNCERTAIN",
        "target_relevance_v2": verdict,
        "reconciliation_basis": basis,
        "A_verdict": va, "A_rank": a.get("source_rank"), "A_reason_code": a.get("reason_code"),
        "B_verdict": vb, "B_rank": bb.get("source_rank"), "B_reason_code": bb.get("reason_code"),
        "source_rank": win.get("source_rank") if verdict != "UNCERTAIN_V2" else None,
        "source_reference": win.get("source_reference") if verdict != "UNCERTAIN_V2" else None,
        "evidence_excerpt": win.get("evidence_excerpt") if verdict != "UNCERTAIN_V2" else None,
        "ctgov_only": bool(win.get("ctgov_only")) and verdict != "UNCERTAIN_V2",
        "unresolved": verdict == "UNCERTAIN_V2",
    })

ledger.sort(key=lambda r: (r["track"], r["entry"].casefold()))
with open("v2_annotation_layer.jsonl", "w") as fh:
    for r in ledger:
        fh.write(json.dumps(r) + "\n")

print(f"{'agreement/basis':30} n")
for k, v in sorted(counts.items()):
    print(f"{k:30} {v}")

# --- Admissibility audit (V2.6: reconciliation applies only already-frozen rules) ---------
# The adjudicators occasionally cited a source the protocol does not admit. Enforcing V2.2,
# V2.3 and V2.5 here is applying the frozen rules, not adding new ones. Every downgrade is
# recorded with the clause it rests on. Downgrades only ever move a verdict to UNCERTAIN_V2.

INADMISSIBLE_DOMAIN = ("prnewswire.com", "businesswire.com", "globenewswire.com",
                       "eqs-news.com", "wikipedia.org", "drugbank", "drugs.com")

audit = []
for r in ledger:
    if r["unresolved"]:
        continue
    src = (r["source_reference"] or "").lower()
    exc = (r["evidence_excerpt"] or "").lower()
    clause = None

    if any(d in src for d in INADMISSIBLE_DOMAIN):
        clause = ("V2.2: cited source is a news/press-wire domain, not a company-controlled "
                  "domain; inadmissible at any rank")
    elif r["track"] == "B" and "biosimilar" in r["entry"].lower() and "clinicaltrials.gov" in src:
        # V2.5 lets a biosimilar inherit only where an admissible source establishes the
        # reference-product relationship. V2.2 admits CT.gov solely where the record states a
        # target or mechanism; a comparator/reference naming is not a target statement, so it
        # cannot carry the inheritance.
        clause = ("V2.5 + V2.2: reference-product relationship rests on a CT.gov record that "
                  "does not state a target or mechanism, so inheritance is not established")
    elif "formulation of" in exc and not any(t in exc for t in ("target", "receptor", "bind",
                                                               "inhibit", "microtubule")):
        clause = ("V2.3: cited excerpt establishes the active moiety but does not state the "
                  "product's molecular target or mechanism")

    if clause:
        audit.append({"benchmark_id": r["benchmark_id"], "entry": r["entry"],
                      "downgraded_from": r["target_relevance_v2"], "clause": clause,
                      "source_reference": r["source_reference"]})
        r.update(target_relevance_v2="UNCERTAIN_V2", reconciliation_basis="INADMISSIBLE_SOURCE",
                 source_rank=None, source_reference=None, evidence_excerpt=None,
                 ctgov_only=False, unresolved=True)

with open("v2_annotation_layer.jsonl", "w") as fh:
    for r in ledger:
        fh.write(json.dumps(r) + "\n")
json.dump(audit, open("v2_admissibility_audit.json", "w"), indent=1)

print(f"\nadmissibility downgrades to UNCERTAIN_V2: {len(audit)}")
for a in audit:
    print(f"  {a['downgraded_from']:12} -> UNCERTAIN_V2  {a['entry']}\n      {a['clause']}")
final = collections.Counter(r["target_relevance_v2"] for r in ledger)
print(f"\nfinal V2 verdicts: {dict(final)}")

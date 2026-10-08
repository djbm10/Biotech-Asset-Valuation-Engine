"""APPROVED_PRODUCT_HUMAN_EFFICACY_DIAGNOSIS v1: trace why approved products lack human_poc.

Diagnosis only. Re-runs the frozen reader (human_poc_v4) filter by filter over every document
the pipeline routed to each frozen asset (via its mentions), plus a corpus-wide scan for the
asset's names, recording the FIRST filter that rejects each candidate sentence.
"""
import json, re, sys, collections
from pathlib import Path
import bve.se.evidence.human_poc as hp
from bve.se.evidence.source_capability import may_establish_human_poc

FROZEN = ["Brexucabtagene Autoleucel", "Breyanzi", "KYMRIAH", "axi-cel", "AUCATZYL", "Abecma", "Carvykti"]

def trace(sentence, names):
    if len(sentence) > hp._MAX_SENTENCE_CHARS: return "too_long"
    if hp._contains(sentence, hp._ELIGIBILITY_TERMS): return "eligibility"
    low = sentence.casefold()
    named = next((n for n in names if n.casefold() in low), None)
    if named is None: return None
    if hp._efficacy_term(sentence) is None: return "no_efficacy_term"
    if hp._contains(sentence, hp._NON_EFFICACY_TERMS) and not hp._reports_efficacy_clear_of_safety(sentence): return "non_efficacy_term"
    if hp._contains(sentence, hp._UNREPORTED_TERMS): return "unreported"
    if hp._contains(sentence, hp._NONHUMAN_TERMS): return "nonhuman"
    if not hp._mentions_humans(sentence): return "no_human_term"
    if hp._VALUE.search(sentence) is None: return "no_value"
    if hp._reports_a_regimen(sentence, named, names): return "regimen"
    if hp._is_regimen_list_item(sentence, named): return "regimen_list"
    return "PASS"

def main(run):
    r = json.load(open(f"{run}/result.json"))
    docs = {d["document_id"]: d for d in r["source_documents"]}
    mention_doc = {m["mention_id"]: m["source_document_id"] for m in r["identity_mentions"]}
    cands = {a["canonical_name"]: a for a in r["candidates"]}
    text_cache = {}
    def text(d):
        if d["document_id"] not in text_cache:
            try: text_cache[d["document_id"]] = Path(d["snapshot_path"]).read_text(errors="ignore")
            except Exception: text_cache[d["document_id"]] = ""
        return text_cache[d["document_id"]]
    for name in FROZEN:
        a = cands[name]
        names = sorted({n for n in [a["canonical_name"], *a["aliases"]] if n.strip()}, key=len, reverse=True)
        routed = {mention_doc[m] for m in a["mention_ids"] if m in mention_doc}
        routed_types = collections.Counter(docs[d]["document_type"] for d in routed if d in docs)
        verdicts = collections.Counter(); passes = []; examples = collections.defaultdict(list)
        for d in routed:
            doc = docs.get(d)
            if not doc or not doc.get("snapshot_path") or doc["document_type"] == "trial_registry_record": continue
            decisional = may_establish_human_poc(doc["document_type"])
            for s in hp._sentences(text(doc)):
                v = trace(s, names)
                if v is None: continue
                if v == "PASS" and not decisional: v = "PASS_but_nondecisional_doc"
                verdicts[v] += 1
                if v == "PASS": passes.append((d, s))
                elif v not in ("no_efficacy_term",) and len(examples[v]) < 2: examples[v].append((d, s[:300]))
        # corpus-wide: publication abstracts naming the asset that were NOT routed to it
        unrouted = collections.Counter(); unrouted_ex = []
        for doc in docs.values():
            if doc["document_id"] in routed or doc["document_type"] in ("trial_registry_record", "ontology_snapshot") or not doc.get("snapshot_path"): continue
            t = text(doc); tl = t.casefold()
            if not any(n.casefold() in tl for n in names): continue
            for s in hp._sentences(t):
                v = trace(s, names)
                if v == "PASS":
                    unrouted[doc["document_type"]] += 1
                    if len(unrouted_ex) < 3: unrouted_ex.append((doc["document_id"], doc.get("source_url"), s[:300]))
        print(f"===== {name} | routed docs {sum(routed_types.values())} {dict(routed_types)}")
        print("  first-rejecting filter (routed, non-registry):", dict(verdicts.most_common()))
        for d, s in passes[:3]: print("  PASS", d, "|", s[:300])
        for v, ex in examples.items():
            for d, s in ex: print(f"  [{v}] {d} | {s}")
        print("  PASS sentences in corpus docs NOT routed to this asset:", dict(unrouted))
        for d, u, s in unrouted_ex: print("   unrouted", d, u, "|", s)

if __name__ == "__main__":
    main(sys.argv[1])

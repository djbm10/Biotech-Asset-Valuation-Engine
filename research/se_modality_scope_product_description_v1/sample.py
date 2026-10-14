"""Reproducible independent acceptance sample (disjoint from the tac01/mint5_protoid_v1 development data).

Unit = one sentence in which a source-declared product name and a modality alias co-occur.
Strata are surface shapes, not the preregistered rules. Order = sha256(unit key); first K per stratum.
"""

import hashlib
import json
import re
from pathlib import Path

from bve.se.ontology.modality import known_modalities, modality_aliases

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "research/se_modality_scope_product_description_v1"
RUNS = Path.home() / "se_runs"
DEV = ("tac01_protoid_v1", "mint5_protoid_v1")
K = 20


def alias_regex():
    terms = sorted(
        {a for m in known_modalities() for a in modality_aliases(m) if a != m},
        key=len,
        reverse=True,
    )
    return re.compile(
        "|".join(r"[\s_-]+".join(map(re.escape, re.split(r"[\s_-]+", t))) for t in terms), re.I
    )


def sentences(text):
    start = 0
    for m in re.finditer(r"[.;\n]|$", text):
        yield start, text[start : m.start()]
        start = m.end()


def dev_keys():
    ncts, hashes = set(), set()
    for run in DEV:
        for p in (RUNS / run / "snapshots").rglob("*.json"):
            hashes.add(p.stem)
            if "clinicaltrials" in str(p):
                ncts.add(json.loads(p.read_text())["identificationModule"]["nctId"])
    return ncts, hashes


def stratum(sentence, at, name):
    rest = sentence[at + len(name) :]
    rest = re.sub(r"^\s*\([^)]*\)", "", rest)
    if re.search(r"\bclass\s+of\b", sentence, re.I):
        return "ST_CLASS"
    if re.match(r"\s*,", rest):
        return "ST_COMMA"
    if re.match(r"\s+(?:is|are)\b", rest, re.I):
        return "ST_COPULA"
    return "ST_OTHER"


def bounded(rx, sentence):
    """A modality alias that is a whole token, not a substring of a drug name ("mab", "til")."""
    return any(
        (m.start() == 0 or not sentence[m.start() - 1].isalnum())
        and (m.end() == len(sentence) or not sentence[m.end()].isalnum())
        for m in rx.finditer(sentence)
    )


def units_from(text, name_sets, base):
    """name_sets: one tuple of names per product; a unit carries one product's names only."""
    rx = alias_regex()
    for off, s in sentences(text or ""):
        if not bounded(rx, s):
            continue
        for names in sorted(name_sets):
            for name in sorted(n for n in names if len(n) >= 3):
                m = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", s)
                if m:
                    yield {
                        **base,
                        "sentence_offset": off,
                        "sentence": s,
                        "product_name": name,
                        "stratum": stratum(s, m.start(), name),
                        "product_names": sorted(names),
                    }
                    break


def ctgov_units(dev_ncts):
    seen = set()
    for p in sorted((RUNS / "tac01_control_r2" / "snapshots").rglob("*.json")):
        d = json.loads(p.read_text())
        nct = d["identificationModule"]["nctId"]
        if nct in dev_ncts or nct in seen:
            continue
        seen.add(nct)
        for i, iv in enumerate((d.get("armsInterventionsModule") or {}).get("interventions") or []):
            names = [iv.get("name"), *(iv.get("otherNames") or [])]
            base = {
                "pool": "ctgov",
                "artifact": str(p),
                "artifact_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "record_id": nct,
                "field": f"/armsInterventionsModule/interventions/{i}/description",
                "text": iv.get("description") or "",
            }
            names = tuple(sorted({n for n in names if n}))
            yield from units_from(iv.get("description"), [names], base)


def public_units(dev_hashes):
    run = json.loads((RUNS / "aacr_safety" / "result.json").read_text())
    cands = {c["asset_id"]: c for c in run["candidates"]}
    names_by_doc = {}
    for c in run["claims"]:
        a = cands.get(c["subject_id"])
        if a:
            names_by_doc.setdefault(c["source_document_id"], set()).add(
                tuple(sorted({n for n in a.get("aliases") or [] if n}))
            )
    for doc in sorted(run["source_documents"], key=lambda x: x["document_id"]):
        p = Path(doc.get("snapshot_path") or "/nonexistent")
        if (
            doc.get("document_type") == "trial_registry_record"
            or not p.exists()
            or p.stem in dev_hashes
        ):
            continue
        raw = json.loads(p.read_text())
        # PubMed snapshots carry title/abstract; conference snapshots carry text.
        field = "/text" if raw.get("text") else "/abstract"
        text = raw.get("text") or raw.get("abstract") or ""
        base = {
            "pool": "public",
            "artifact": str(p),
            "artifact_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "record_id": doc["document_id"],
            "field": field,
            "text": text,
        }
        yield from units_from(text, names_by_doc.get(doc["document_id"], set()), base)


def main():
    dev_ncts, dev_hashes = dev_keys()
    pool = list(ctgov_units(dev_ncts)) + list(public_units(dev_hashes))
    for u in pool:
        u["unit_id"] = hashlib.sha256(
            f"{u['artifact_sha256']}|{u['field']}|{u['sentence_offset']}|{u['product_name']}".encode()
        ).hexdigest()[:16]
    pool = list({u["unit_id"]: u for u in pool}.values())  # first wins
    denominators = {}
    sample = []
    for st in ("ST_COMMA", "ST_COPULA", "ST_CLASS", "ST_OTHER"):
        for pl in ("ctgov", "public"):
            group = sorted(
                (u for u in pool if u["stratum"] == st and u["pool"] == pl),
                key=lambda u: u["unit_id"],
            )
            denominators[f"{st}|{pl}"] = len(group)
            # All rule-shaped units; a fixed hash-ordered negative sample of the rest.
            sample += group if st != "ST_OTHER" else group[:K]
    (STUDY / "sample.json").write_text(
        json.dumps({"denominators": denominators, "units": sample}, indent=1, ensure_ascii=False)
        + "\n"
    )
    print(json.dumps(denominators), len(sample))


if __name__ == "__main__":
    main()

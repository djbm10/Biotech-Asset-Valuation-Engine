"""Stage A of ``docs/se_policies/target_relation_reader_v1.md``, against the pinned ontology.

Reads the two frozen intervention corpora, checks the hashes the preregistration froze,
runs the §4 controls on the real snapshot, and writes:

- the A3 audit list over the diagnosis corpus;
- the A4 old-versus-new diff over the baseline corpus.

Hand classification is recorded in the policy document, not here.

    PYTHONPATH=src python scripts/eval_target_relation_reader.py
"""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from bve.se.evidence import construct_targets as ct
from bve.se.evidence.construct_targets import intervention_construct_targets
from bve.se.evidence.target_relations import first_sentence

ROOT = Path(__file__).resolve().parents[1] / "research" / "se_target_reader"
FROZEN = {
    "lookup_v1_interventions.jsonl.gz": (
        "b1ce7b6cf37c398aa2fee7b3e96c04cab2a31da44ea5e285b8a9b025a32b7bda"
    ),
    "baseline_interventions.jsonl.gz": (
        "532dfcd604bd2621bdcbad800afc0419784774bea247d1056eb947e01168891c"
    ),
}

#: (description, intervention, expected set or None, targets that must never appear)
SYNTHETIC = [
    ("IV route", {"name": "Drug A", "description": "anti-CD19 CAR-T cells given IV"},
     ["TARGET:CD19"], ["TARGET:ST6GALNAC4"]),
    ("LN code", {"name": "LN-145", "description": "autologous TIL therapy"}, None,
     ["TARGET:MLPH"]),
    ("DPP inhibitor", {"name": "Drug B", "description": "a DPP-4 inhibitor"}, None,
     ["TARGET:DSPP"]),
    ("AMG code", {"name": "AMG 103", "description": "Anti-CD19 bispecific antibody",
                  "otherNames": ["AMG-103", "AMG103"]}, ["TARGET:CD19"], ["TARGET:AMELX"]),
    ("cevostamab", {"name": "Cevostamab", "description": (
        "Cevostamab (FcRH5×CD3) demonstrated 30.2% overall response rate in patients "
        "who underwent BCMA-targeted treatment")}, None, ["TARGET:TNFRSF17"]),
    ("armoring", {"name": "Anti-CD19 IL-10/IL15 CAR-NK", "description": ""}, None,
     ["TARGET:IL10", "TARGET:IL15"]),
    ("P450", {"name": "Cytochrome P450 inhibitor", "description": ""}, None, []),
    ("LHRH", {"name": "Leuprolide", "description": "LHRH agonist"}, None,
     ["TARGET:GNRH1"]),
    ("HDAC", {"name": "Entinostat", "description": "HDAC inhibitor"}, None, []),
    ("MEK", {"name": "Trametinib", "description": "MEK Inhibitor"}, None, []),
    # §4.1 freezes only the forbidden set here: MART-1 *is* MLANA, so an anti-MART-1 TCR
    # attributing MLANA is the correct reading.
    ("MART", {"name": "TCR PBL", "description": "anti-MART-1 F5 TCR PBL infusion"},
     ["TARGET:MLANA"], ["TARGET:SEPTIN4", "TARGET:F5"]),
    ("CT053", {"name": "CT053", "description": "CT053 is a fully human BCMA-specific CAR-T"},
     ["TARGET:TNFRSF17"], []),
    ("CLN-978", {"name": "CLN-978", "description": "CD19-directed CD3 bispecific T-cell engager"},
     ["TARGET:CD19"], []),
    ("anti-CD19 CAR-T", {"name": "X", "description": "anti-CD19 CAR-T cells"},
     ["TARGET:CD19"], []),
    ("BCMA/GPRC5D", {"name": "BCMA/GPRC5D CAR-T cells", "description": ""},
     ["TARGET:GPRC5D", "TARGET:TNFRSF17"], []),
    ("teclistamab", {"name": "Teclistamab (BCMAxCD3)", "description": ""},
     ["TARGET:TNFRSF17"], []),
]

#: (nct, name fragment, expected set or None, targets that must never appear)
CORPUS = [
    ("NCT06875063", "GB5005", None, ["TARGET:CARTPT"]),
    ("NCT04833504", "CCL19", ["TARGET:CD19"], ["TARGET:IL7", "TARGET:CCL19"]),
    ("NCT01467986", "asatinib", None, ["TARGET:ATM"]),
    ("NCT02596828", "asatinib", None, ["TARGET:ATM"]),
    ("NCT00293085", "ocetaxel", None, ["TARGET:OR2AG1"]),
    ("NCT00863837", "antoprazole", None, ["TARGET:EVL"]),
    ("NCT04997551", "olch", None, ["TARGET:CYP3A4"]),
    ("NCT04093596", "ALLO-715", ["TARGET:TNFRSF17"], []),
    ("NCT07752264", "Equecabtagene", ["TARGET:TNFRSF17"], []),
    ("NCT06316791", "CNCT19", ["TARGET:CD19"], []),
]


def _load(name: str) -> list[dict]:
    path = ROOT / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != FROZEN[name]:
        raise SystemExit(f"{name}: hash {digest} != frozen {FROZEN[name]}")
    with gzip.open(path, "rt") as handle:
        return [json.loads(line) for line in handle]


def _new(record: dict) -> list[str] | None:
    return intervention_construct_targets(record, intervention_type=record["type"])


def _old(record: dict) -> list[str] | None:
    """The reader as it stood at ``7b6d45c``, for the A4 diff."""

    from bve.se.discovery.adapters import extract_observed_asset_names

    name = record["name"]
    if len(extract_observed_asset_names(name)) > 1 or ct.denotes_more_than_one_product(name):
        return None
    text = " ".join([name, record["description"], " ".join(record["otherNames"])])
    targets = ct.attributed_targets_in(text)
    return ct.canonical_construct_targets(targets) if targets else None


def _check(label: str, got, expected, forbidden, lines: list[str]) -> bool:
    ok = (got == expected) and not set(forbidden) & set(got or [])
    lines.append(f"{'PASS' if ok else 'FAIL'}  {label}: got={got} expected={expected}")
    return ok


def main() -> None:
    lines: list[str] = ["# TARGET_RELATION_READER v1 -- Stage A", ""]
    dev = _load("lookup_v1_interventions.jsonl.gz")
    base = _load("baseline_interventions.jsonl.gz")

    lines.append("## A1/A2 controls")
    passed = True
    for label, record, expected, forbidden in SYNTHETIC:
        got = intervention_construct_targets(record, intervention_type=None)
        passed &= _check(label, got, expected, forbidden, lines)
    by_nct: dict[str, list[dict]] = {}
    for record in dev:
        by_nct.setdefault(record["nct"], []).append(record)
    for nct, fragment, expected, forbidden in CORPUS:
        for record in by_nct.get(nct, []):
            if fragment.casefold() in record["name"].casefold():
                got = _new(record)
                passed &= _check(f"{nct} {record['name'][:40]}", got, expected, forbidden, lines)
    lines.append(f"controls: {'ALL PASS' if passed else 'FAILURES'}")

    lines += ["", "## A3 diagnosis-corpus audit list"]
    emitted = [(record, _new(record)) for record in dev]
    emitted = [(record, got) for record, got in emitted if got]
    common = [{"TARGET:CD19"}, {"TARGET:TNFRSF17"}]
    other = [(r, g) for r, g in emitted if set(g) not in common]
    sample = sorted(
        ((r, g) for r, g in emitted if set(g) in common), key=lambda item: item[0]["key"]
    )[:60]
    lines.append(f"emitted={len(emitted)} non_cd19_bcma={len(other)} sampled_common=60")
    for record, got in [*other, *sample]:
        reading = ct.intervention_target_reading(record, intervention_type=record["type"])
        prov = ";".join(relation.locator() for relation in reading.relations) if reading else ""
        lines.append(f"{record['key']} {record['nct']} {got} | {record['name'][:50]} | {prov}")

    lines += ["", "## A4 baseline-corpus diff (old -> new)"]
    gained = lost = 0
    for record in base:
        old, new = set(_old(record) or []), set(_new(record) or [])
        if old == new:
            continue
        gained += len(new - old)
        lost += len(old - new)
        lines.append(
            f"{record['key']} {record['nct']} {record['benchmarks']} | {record['name'][:50]} | "
            f"old={sorted(old)} new={sorted(new)} | desc0={first_sentence(record['description'])[:140]!r}"
        )
    lines.append(f"gained={gained} lost={lost}")
    (ROOT / "eval_v1.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:60]))


if __name__ == "__main__":
    main()

"""Stage H of ``docs/se_policies/ncit_target_sidecar_v1.md``.

    PYTHONPATH=src python scripts/eval_ncit_target_sidecar.py <Thesaurus.txt>

Writes ``research/se_ncit/eval_v1.txt``: controls (H1), parity with the frozen reference
reader (H2), and every held-out emitted fact with its full definition for hand audit (H3).
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from bve.se.ontology.ncit_targets import CLASS_MAP, decide, mechanism_antigens, ncit_authority

ROOT = Path(__file__).resolve().parents[1] / "research" / "se_ncit"
FROZEN = {
    "reader_frozen_v1.py": "3e7960d04aee4a9f6205e9703bf12ccde7e23d582a7740aed6d9ca0f998ba553",
    "split_v1.json": "0abea2bf5e6e3c67e6dbb473743ed7ddfffe90e2f04f860b7cb40d4a09d3eb1f",
}
POSITIVE = {
    "C165779": ["TARGET:TNFRSF17"], "C180584": ["TARGET:CD19"], "C199003": ["TARGET:TNFRSF17"],
    "C165507": ["TARGET:TNFRSF17"], "C185123": ["TARGET:TNFRSF17"], "C147523": ["TARGET:TNFRSF17"],
    "C179725": ["TARGET:CD19"],
    "C175471": ["TARGET:CD19", "TARGET:TNFRSF17"], "C150906": ["TARGET:CD19"],
}
NEGATIVE = {
    "C155897": None, "C151954": None, "C143140": "no_antigen_class",
    "C120552": "no_antigen_class", "C150382": None,
    # Amendment 1 (oracle correction): NCIt lacks one of the two required statements.
    "C211706": "no_mechanism_sentence", "C203060": "no_antigen_class",
}


def _check_frozen() -> None:
    for name, expected in FROZEN.items():
        digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if digest != expected:
            raise SystemExit(f"{name}: {digest} != frozen {expected}")


def _reference():
    spec = importlib.util.spec_from_file_location("ncit_ref", ROOT / "reader_frozen_v1.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    _check_frozen()
    authority = ncit_authority()
    if authority is None:
        raise SystemExit("sidecar not installed")
    products = authority.products
    lines = ["# NCIT_TARGET_SIDECAR v1 -- Stage H", f"sidecar {authority.version_token}", ""]

    lines.append("## H1 controls")
    ok = True
    for code, expected in POSITIVE.items():
        got = products[code]["targets"]
        ok &= got == expected
        lines.append(f"{'PASS' if got == expected else 'FAIL'} {code} {got} expected {expected}")
    for code, reason in NEGATIVE.items():
        got = products[code]
        good = not got["targets"] and (reason is None or got["reason"] == reason)
        ok &= good
        lines.append(f"{'PASS' if good else 'FAIL'} {code} {got['targets']} {got['reason']}")
    gd2 = [c for c, p in products.items() if "C201491" in p["classes"]]
    good = all(not products[c]["targets"] for c in gd2)
    ok &= good
    lines.append(f"{'PASS' if good else 'FAIL'} GD2 class products ({len(gd2)}) emit nothing")
    lines.append(f"H1: {'ALL PASS' if ok else 'FAILURES'}")

    lines += ["", "## H2 parity with the frozen reference"]
    ref = _reference()
    csv.field_size_limit(1 << 30)
    definitions = {}
    with open(argv[0], encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row[0] in products:
                definitions[row[0]] = row[4]
    mismatches = 0
    assert {k: v[0] for k, v in CLASS_MAP.items()} == {k: v[0] for k, v in ref.CLASS_MAP.items()}
    for code, product in products.items():
        mine, _ = mechanism_antigens(definitions[code])
        theirs, _ = ref.mech_antigens(definitions[code])
        decision = decide(set(product["classes"]), definitions[code])
        if (mine != theirs) or list(decision.targets) != product["targets"]:
            mismatches += 1
            lines.append(f"MISMATCH {code} prod={mine} ref={theirs}")
    lines.append(f"H2: {len(products)} concepts, {mismatches} mismatches")

    lines += ["", "## H3 held-out emitted facts (hand audit)"]
    held = json.loads((ROOT / "split_v1.json").read_text())["held"]
    counts: dict[str, int] = {}
    for code in held:
        product = products.get(code)
        if product is None:
            continue
        counts[product["reason"]] = counts.get(product["reason"], 0) + 1
        if product["targets"]:
            lines.append(
                f"\n{code} {product['targets']} | {product['name']}\n  DEF: {definitions[code]}"
            )
    lines.append(f"\nH3 held-out reasons: {counts}")
    (ROOT / "eval_v1.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(line for line in lines if not line.startswith("\n") and "DEF:" not in line))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

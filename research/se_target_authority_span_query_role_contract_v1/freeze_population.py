"""Freeze structural intent labels before measuring or deriving a contract."""

import hashlib
import json
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path("/tmp/span_role_v1")
OUT.mkdir(exist_ok=True)
rows = []


def add(query, spans, category, reason, operator="ANY", outcome=None):
    rows.append(
        {
            "id": f"S{len(rows) + 1:03}",
            "query": query,
            "expected_target_spans": [
                {"text": text, "entity_id": entity} for text, entity in spans
            ],
            "expected_operator": operator,
            "role_category": category,
            "expected_outcome": outcome or ("TARGET" if spans else "NO_TARGET"),
            "reason": reason,
        }
    )


add(
    "Find clinical-stage CD19 therapies.",
    [("CD19", "TARGET:CD19")],
    "target",
    "Exact symbol in therapeutic target slot.",
)
add(
    "Find PD-1 antibodies.",
    [("PD-1", "TARGET:PDCD1")],
    "target",
    "Existing explicit alias, not an invented synonym.",
)
add(
    "Find clinical-stage Hemoglobin beta chain therapies.",
    [("Hemoglobin beta chain", "TARGET:HBB")],
    "target",
    "Existing frozen whole protein name.",
)
add(
    "Find clinical-stage interleukin 2 receptor, alpha therapies.",
    [("interleukin 2 receptor, alpha", "TARGET:IL2RA")],
    "target",
    "The ligand token is internal to the complete receptor name.",
)
add(
    "Find therapies targeting GDNF receptor alpha 1e.",
    [("GDNF receptor alpha 1e", "TARGET:GFRA1")],
    "target",
    "Complete source alias, not GDNF ligand.",
)
add(
    "Find therapies targeting CD8 beta opposite.",
    [("CD8 beta opposite", "TARGET:SMYD1")],
    "target",
    "Complete authoritative name; embedded CD8 cannot own the span.",
)
add(
    "Find clinical-stage C3 and PZP-like alpha-2-macroglobulin domain-containing protein 4 therapies.",
    [("C3 and PZP-like alpha-2-macroglobulin domain-containing protein 4", "TARGET:C5")],
    "target",
    "The name-internal and is not a target conjunction.",
)
add(
    "Find clinical-stage (R)-beta-hydroxybutyrate dehydrogenase therapies.",
    [("(R)-beta-hydroxybutyrate dehydrogenase", "TARGET:BDH2")],
    "target",
    "Scientific parentheses belong to the name.",
)
add(
    "Find clinical-stage Thymopoietin-related peptide isoform alpha therapies.",
    [("Thymopoietin-related peptide isoform alpha", "TARGET:TMPO")],
    "target",
    "Name-internal peptide is not a requested therapeutic modality.",
)
for wrapper in [
    "anti-{}",
    "{}-directed",
    "{}-targeting",
    "{}-blocking",
    "{}-binding",
    "{}-specific",
]:
    add(
        f"Find clinical-stage {wrapper.format('CD19')} antibodies.",
        [("CD19", "TARGET:CD19")],
        "affix",
        "Existing adopted wrapper around an independently supported target.",
    )
add(
    "Find antibodies targeting CD19.",
    [("CD19", "TARGET:CD19")],
    "target",
    "Object of explicit targeting predicate.",
)
add(
    "Find antibodies against CD19.",
    [("CD19", "TARGET:CD19")],
    "target",
    "Object of explicit against complement.",
)
add(
    "Find antibodies for CD19-positive leukemia.",
    [],
    "biomarker",
    "Patient disease modifier is not a therapeutic target request.",
)
add(
    "Find antibodies targeting CD19 for BCMA-positive leukemia.",
    [("CD19", "TARGET:CD19")],
    "mixed",
    "Separate target object and patient biomarker; no BCMA target inheritance.",
)
add(
    "Find therapies for interleukin 2 receptor deficiency.",
    [],
    "disease",
    "Condition complement does not assert target or ligand.",
)
add(
    "Find therapies for Parkinson disease.",
    [],
    "disease",
    "Disease role is distinct from protein/gene identity.",
)
add("Find therapies with CD19 as a biomarker.", [], "biomarker", "Explicit biomarker role.")
add(
    "Find therapies measuring CD19 expression.",
    [],
    "assay",
    "Measurement object is not a therapeutic target.",
)
add(
    "Find therapies evaluated in a CD19 binding assay.",
    [],
    "assay",
    "Assay context cannot establish the target requirement.",
)
add(
    "Find therapies for BRAF V600E-mutant melanoma.",
    [],
    "mutation",
    "Mutation-specific patient criterion must not become a wild-type target.",
)
add(
    "Find therapies targeting BRAF V600E.",
    [],
    "mutation",
    "Existing target model cannot express mutant-specific scope.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting CD19 for BRAF V600E-mutant melanoma.",
    [("CD19", "TARGET:CD19")],
    "mixed",
    "Mutation is in the indication clause, not a second target.",
)
add(
    "Find therapies targeting the MAPK pathway.",
    [],
    "pathway",
    "Pathway membership is not a single gene.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting the CD19 family.",
    [],
    "family",
    "A family requirement must not silently collapse to a gene.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting a complex containing CD19.",
    [],
    "complex",
    "Complex membership does not identify the whole complex.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting the receptor of GDNF.",
    [],
    "relationship",
    "No inversion of ligand-to-receptor relation.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting the ligand of PDCD1.",
    [],
    "relationship",
    "No inversion of receptor-to-ligand relation.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting CD19-associated protein.",
    [],
    "scientific_phrase",
    "A name with an unsupported head cannot promote its embedded alias.",
    outcome="UNRESOLVED_SCIENTIFIC",
)
add(
    "Find therapies targeting CD19 or BCMA.",
    [("CD19", "TARGET:CD19"), ("BCMA", "TARGET:TNFRSF17")],
    "multi_target",
    "Explicit disjunction of independent target objects.",
)
add(
    "Find therapies targeting CD19 and BCMA.",
    [("CD19", "TARGET:CD19"), ("BCMA", "TARGET:TNFRSF17")],
    "multi_target",
    "Explicit conjunction of independent target objects.",
    operator="ALL",
)
for separator in ["/", "x", "×"]:
    add(
        f"Find clinical-stage CD19{separator}BCMA CAR-T therapies for lupus.",
        [("CD19", "TARGET:CD19"), ("BCMA", "TARGET:TNFRSF17")],
        "separator",
        "Existing adopted dual-target separator control.",
        operator="ALL",
    )
add(
    "Find clinical-stage AK/ATPase therapies for cancer.",
    [("AK/ATPase", "TARGET:AK6")],
    "separator",
    "Whole authority name owns the separator; do not emit ADK.",
)
add(
    "Find clinical-stage TaxREB107 therapies for cancer.",
    [("TaxREB107", "TARGET:RPL6")],
    "separator",
    "Whole authority name takes precedence over accidental x separator.",
)
add(
    "Find clinical-stage anti-ABP/ZF therapies.",
    [],
    "separator",
    "Unconfirmed separator fragment must not assert CREBZF.",
)
add(
    "Find clinical-stage CD19/CAR therapies.",
    [],
    "separator",
    "An unresolved dual-target component cannot be discarded.",
)
add(
    "Find clinical-stage p150 therapies.",
    [],
    "ambiguity",
    "Ambiguous authority identity remains ambiguous.",
    outcome="AMBIGUOUS",
)
add(
    "Find clinical-stage IL-4Rα therapies.",
    [],
    "unsupported_alias",
    "Greek expansion remains reverted.",
    outcome="UNKNOWN",
)
add(
    "Find clinical-stage IL-4R-alpha therapies.",
    [("IL-4R-alpha", "TARGET:IL4R")],
    "target",
    "Existing independently supported English alias.",
)
add(
    "Find clinical-stage CD19xyz therapies.",
    [],
    "unsupported_alias",
    "No substring inference from CD19.",
    outcome="UNKNOWN",
)
add(
    "Find clinical-stage CD19 therapies for CD19-positive leukemia.",
    [("CD19", "TARGET:CD19")],
    "mixed",
    "Same identity occurs once as target and once as patient biomarker.",
)
add(
    "Find clinical-stage CD19 therapies for CD8 beta opposite expression.",
    [("CD19", "TARGET:CD19")],
    "mixed",
    "Even a whole target authority name is non-target in an expression criterion.",
)
assert len({r["query"] for r in rows}) == len(rows)
for r in rows:
    for span in r["expected_target_spans"]:
        assert span["text"] in r["query"]
(OUT / "structural_controls.json").write_text(
    json.dumps(
        {
            "note": "Constructed grammar probes; not assertions that these are real diseases, biomarkers or feasible therapies. No synthetic biological aliases.",
            "rows": rows,
        },
        indent=2,
        ensure_ascii=False,
    )
    + "\n"
)
paths = [
    "research/se_target_query_authority_span_boundary_diagnosis_v1/trace.json",
    "research/se_target_query_greek_orthography_v2/query_reference.json",
    "research/se_target_query_alias_coverage_v1/survey_baseline.json",
    "research/se_target_query_alias_coverage_v1/survey_population.json",
    "research/target_reference_identity_surface_diagnosis_v1/current_scientific_baseline.json",
    "tests/se/test_dual_target_separator_safety.py",
    "src/bve/se/intent/intent.py",
    "src/bve/se/intent/parser.py",
    "src/bve/se/intent/indication_compilation.py",
]
manifest = {
    "baseline": "04b184b",
    "structural_controls": len(rows),
    "input_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
    "controls_sha256": hashlib.sha256((OUT / "structural_controls.json").read_bytes()).hexdigest(),
}
(OUT / "population_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(len(rows))

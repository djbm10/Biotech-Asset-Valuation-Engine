"""Manual scope annotations and lifecycle report over frozen diagnostic data."""

import ast
import json
from pathlib import Path

ROOT = Path("/home/djmann/projects/bve-b8")
OUT = Path("/tmp/modality_scope_report")
OUT.mkdir(exist_ok=True)
rows = json.loads(Path("/tmp/modality_scope_seed0/scope_table.json").read_text())
mentions = []
for row in rows:
    for hit in row["all_lexical_hits"]:
        scope = row["scope"]
        reason = row["scope_reason"]
        if hit["term"] == "trap":
            scope = "AMBIGUOUS"
            reason = (
                "Lexical artifact inside tetrapeptide, not an independent fusion-protein assertion."
            )
        elif (
            row["id"] in {"H19_DATO", "S13", "S14"} and hit["modality"] == "ANTIBODY_DRUG_CONJUGATE"
        ):
            scope = "PRODUCT_LEVEL"
            reason = "ADC is explicitly predicated of the whole product."
        elif row["id"] == "S15" and hit["modality"] == "CAR_T":
            scope = "PRODUCT_LEVEL"
            reason = "CAR-T explicitly predicates the whole product."
        elif row["id"] == "S16" and hit["modality"] == "GENE_THERAPY":
            scope = "PRODUCT_LEVEL"
            reason = "Gene therapy predicates whole product; vector is delivery relationship."
        elif row["id"] == "S17":
            scope = "RELATIONAL_COMPOSITE"
            reason = "Antibody conjugation to radionuclide; alias match does not establish ADC payload class."
        elif row["id"] == "H19_DATO" and hit["modality"] == "MONOCLONAL_ANTIBODY":
            scope = "COMPONENT_LEVEL"
            reason = "IgG1/mAb is antibody constituent of described ADC."
        mentions.append(
            {
                "case": row["id"],
                **hit,
                "scope": scope,
                "reason": reason,
                "annotation_method": "manual grammatical diagnosis; not executable scope recognition",
            }
        )
(OUT / "all_mention_scopes.json").write_text(json.dumps(mentions, sort_keys=True, indent=2) + "\n")
tree = ast.parse((ROOT / "tests/se/test_authority_modality.py").read_text())
fixture = next(
    ast.literal_eval(n.value)
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "_MOLECULE_TYPES" for t in n.targets)
)
(OUT / "structured_control_scopes.json").write_text(
    json.dumps(
        [
            {
                "fixture_id": k,
                "raw_molecule_type": v,
                "scope": "AMBIGUOUS" if v == "Unknown" else "PRODUCT_LEVEL",
                "provenance": "tests/se/test_authority_modality.py::_MOLECULE_TYPES",
                "qualification": "synthetic existing fixture; scope denotes field subject, not validation of source category or adopted INN refinements",
            }
            for k, v in fixture.items()
        ],
        indent=2,
    )
    + "\n"
)
lines = [
    "# Frozen focus-scope table",
    "",
    "Scope annotations are diagnosis data, not a production parser. Every lexical match is separately annotated in all_mention_scopes.json. Folded hit coordinates are explicitly distinguished from exact raw focus spans.",
    "",
    "| Case | Text | Raw focus span | Scope | Current scalar | Reason |",
    "|---|---|---|---|---|---|",
]
for r in rows:
    span = r["focus_span"]
    lines.append(
        f"| {r['id']} | {r['text']} | {span['start']}:{span['end']} `{span['surface']}` | {r['scope']} | {r['current_lexical_winner']} | {r['scope_reason']} |"
    )
(OUT / "scope_table.md").write_text("\n".join(lines) + "\n")

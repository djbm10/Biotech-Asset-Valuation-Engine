# TARGET_COMPONENT_IDENTITY_CERTIFICATE v2 — ADOPTED

Preregistration `a9bf585`; implementation `b17f9da`. All C1–C12 pass under their preregistered applicability. This is an independently adopted offline certificate layer. Production parser, aliases, requirements and diligence behavior do not consume it.

## Frozen result

| Status | All 234 certificates | 86 blocked proposals |
|---|---:|---:|
| CERTIFIED_SINGLE_ENTITY | 55 | 0 |
| CERTIFIED_MULTI_ENTITY | 3 | 0 |
| CERTIFIED_RELATIONAL_ENTITY | 15 | 0 |
| CONFLICT | 35 | 35 |
| AMBIGUOUS | 126 | 51 |
| UNRESOLVED | 0 | 0 |

The 55 permitting controls comprise 52 exact primary gene assertions and three exact protein components. They do not certify the entire alias inventory of their record/group. The 48 resolver groups remain ambiguous as aggregate ingestion objects. A scoped gene assertion certificate is not transferable to synonyms, proteins, or a merged group. Typed relational/multi-entity certificates explicitly do not permit equivalence to a constituent.

All nine implicated groups and all 86 proposals are preserved. The ALK/EML4 primary gene-ID disagreement remains CONFLICT. The 51 ambiguous proposals have no certified alias/component-to-canonical equivalence. No source priority, normalized spelling, shared accession or benchmark expectation was used to repair them. Gene/protein encoding edges are not same-entity edges.

## Validation and provenance

- All 234 statuses equal the frozen independent expectations.
- Independent seed-0/seed-42 builds produce byte-identical certificates, evidence registries, collision artifacts and summaries.
- 495 contributing source records and 11,806 selected structured fields are retained with their actual adopted assertion IDs. All 3,534 original sidecar origins round-trip exactly. Each certificate exposes raw components, proposed identity, component IDs, evidence references, typed premises, claim/agreement matrix, rule and status.
- Both canonical-ID collision families remain visible: seven SNORA62 components and two CDC42BPA components. `collision_scope_audit.json` separates component-level collisions from recoverable-origin collisions. Missing historical ChEMBL origins are not invented; independent release evidence is explicitly separate. All normalized-key origins remain distinct.
- All 6,199 frozen parser/compiler/trial/buyer decision hashes are unchanged. No changes under `src`, `tests`, `scripts`, or `data/se/ontology` against `d968f30`.
- Eleven red-first certificate tests plus four adopted mention-representation controls pass (15 total). Ruff passes for `src/bve/se`, `tests/se`, and this study. Full `tests/se` was not run: C12 requires it if production code changes, and none changed.

`results/adoption.json` is the gate ledger. `results/certificates.json.gz` is the complete per-certificate audit. `results/evidence_registry.json.gz` resolves every referenced field/origin to raw text/value, artifact hash, source release and field/record locator. `results/certificate_table.md` is a readable status index. Exact input hashes are in `inputs.json`; output hashes are retained in `results/`.

## Offline reproduction

Use only the frozen paths in `inputs.json`; changed inputs fail closed. No acquisition is performed. Each output directory must be new.

```bash
PYTHONHASHSEED=0 python research/se_target_component_identity_certificate_v2/certificates.py --output /tmp/cert-v2-fresh-0
PYTHONHASHSEED=42 python research/se_target_component_identity_certificate_v2/certificates.py --output /tmp/cert-v2-fresh-42
python research/se_target_component_identity_certificate_v2/validate.py --first /tmp/cert-v2-fresh-0 --second /tmp/cert-v2-fresh-42 --output /tmp/cert-v2-validation.json
```

The preregistration and frozen population are immutable scientific expectations. `freeze.py` records how the population was selected; do not regenerate its expectations after scoring. `finish_results.py` only records post-score summaries and does not change certificates or acceptance criteria.

## Decision and roadmap

**This repair path is evidence-blocked: 0/86 proposals permit single-entity equivalence. Stop work on recovering these 86 cases.** Do not add another authority, weaken certification, or start a target-role implementation for them.

The next independent priority to consider is diagnosis of the known H19 non-asset/PEPTIDE candidate-qualification defects. Excluding non-products improves scientific precision and is independent of this blocked identity path. It requires a separate first-boundary diagnosis and preregistration before behavior changes; no qualification, ranking or duplicate work occurs in this milestone.

H21–H25 remain untouched; H6–H10 remain unrun; H17/H20 remain development diagnostics only. Human-PoC recovery remains stopped.

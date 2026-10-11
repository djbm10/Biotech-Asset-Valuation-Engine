# INDICATION_REQUIREMENT_SEMANTICS v1

Status: PREREGISTERED, 2026-10-11. Baseline c70461e (engine f0e90e6).
Ranking is frozen. No live acquisition or replay is authorized for this evaluation.

## Diagnosis and hypothesis

The existing compiler emits residual word literals except for B-cell lymphoma. Exact
whole-condition IN comparison falsely excludes 33/38 reference products. Missing
indication evidence remains UNKNOWN, creating shortlist fill. Disease concept compilation
and conservative ontology comparison should recover these false FAILs without inventing
compatibility. No qualification, target, identity, modality, efficacy or routing change.

## Frozen population and source

`research/se_indication_semantics_v1/population.json` freezes the six existing diagnostic
results, their SHA256s, problems, decisions, all 38 reference asset IDs, and all 655 assets
whose sole FAIL is strategy.indication (444/2/27/62/33/87 for H2/H4/H11/H12/H13/H14).
It also freezes TAC01/mint5 protoid_v1 results. Existing evidence only; no discovery rerun.
`controls.json` freezes 16 semantic cases and 18 non-disease terms, including independent
same/synonym/subtype, explicit incompatible, broader, unrecognized and B-cell controls.
`manifest.json` seals these files and the disease vocabulary.

NCIt 26.08e flat source is already locally available. The committed source-derived
`ncit_diseases.json` includes ALL Disease or Syndrome/Neoplastic Process records, names
and disease parent edges, with source SHA256. This is a typed view of the existing NCIt
authority, not a diagnostic-specific vocabulary. No names added manually. No use of H16–H20.

## Exact rule

Normalize case/punctuation into space-separated alphanumeric words. Recognize only
whole-word disease aliases in the frozen NCIt typed vocabulary; multiple codes for a name
are ambiguous. Query compilation consumes maximal, non-overlapping unique disease aliases
within existing adjacent RESIDUAL spans. A disease alias embedded in a longer residual
phrase stays one concept. Other residual words are not indication requirements. Retrieval
residuals and parser spans are unchanged. Caller-supplied indication names are resolved
by the same evaluator; unrecognized requests return UNKNOWN, even for identical text.

Concept IDs are NCIt codes with INDICATION:NCIT: prefix. Existing B-cell request surfaces,
positive subtype terms, explicit disjoint terms and broader terms keep their priority.
Unrecognized B-cell conditions become UNKNOWN rather than the old default NO.

For NCIt requests, a unique observed disease alias names the same code or a descendant:
PASS. An ancestor, ambiguous alias, missing or unrecognized evidence, or relationship
that cannot be established: UNKNOWN. A fully recognized whole-condition diagnosis can
be incompatible (FAIL) only if neither concept is ancestor of the other and no disease
descendant in the frozen graph belongs to both. An embedded alias can establish a
positive match, but cannot establish incompatibility for unexplained surrounding text.
Conditions containing explicit negation tokens `not`, `without`, `excluding`, `negative`
are incomparable (UNKNOWN). No unrestricted substring or fuzzy matching.
Across requested alternatives and observed conditions: any PASS wins; otherwise any
UNKNOWN yields UNKNOWN; FAIL only if all comparisons are positively incompatible.
Non-string evidence is UNKNOWN. Preserve gate missing/conflict precedence.

Explainability retains requested concept ID, authoritative source/version, observed fact
IDs and original condition facts. Rationale states the semantic comparison and status.

## Acceptance and measurement (all mandatory)

I1: All 33 previously excluded frozen reference asset IDs receive PASS or UNKNOWN for
indication, and remain visible/rankable (no other FAIL or low-support change).
I2: All four explicit incompatible controls remain FAIL (NSCLC/UC both directions and
B-cell/Hodgkin and B-cell/T-cell). This forbids blanket FAIL-to-UNKNOWN conversion.
I3: All five same/synonym/subtype positive controls are PASS.
I4: All seven uncertainty controls are UNKNOWN, including unrecognized identical text.
I5: None of the 18 frozen non-disease terms compile an indication requirement. Each of
the six diagnostic disease phrases compiles at least one coherent disease concept,
never residual word literals; query residuals/trial retrieval remain unchanged.
I6: TAC01 keeps all accepted indication PASSes, broader UNKNOWNs and explicit disjoint
FAILs; no new scientifically false PASS. TAC01 and mint5 top-20 asset IDs/order unchanged.
mint5 requirements, all decisions and dispositions identical. No benchmark tuning.
I7: Offline evaluation replaces only indication decisions against identical frozen facts;
every other decision and all candidates, qualification, identity, target, modality, efficacy,
trial attribution, low-support IDs and search attempts remain byte-identical. Source diff
is limited to indication ontology, compiler, evaluator and indication evaluator dispatch.
Ranking and shortlist code unchanged. No new positive match without authoritative
same/subtype or existing B-cell match evidence. Review every newly PASS condition string.
I8: Targeted regression tests pass; PYTHONPATH=src python3 -m pytest tests/se -q passes
except existing expected xfails; ruff check src/ is clean.

Offline scorer checks input hashes, re-evaluates ONLY indication against frozen evidence,
recalculates dispositions from unchanged other decisions and builds the frozen shortlist.
It emits every criterion, decision transitions, reference visibility and top-20 diagnostics.
Do not infer generalization from these development queries. Report TARGET_UNKNOWN_FILL
and NON_PRODUCT remaining using frozen row labels for old rows; newly entering rows are
classified from evidence, and ambiguous product types are reported unresolved rather than
invented. Record all newly PASS condition strings with authoritative code/relationship.

## Stop/revert

Any failed criterion: record FAILED_ACCEPTANCE; revert implementation with normal git
revert; retain preregistration, frozen source/population, scorer and results in history.
No patches after acceptance results, threshold changes or history rewriting. Revised
approach needs a new preregistration. Adopt only after every criterion passes, then update
handoff and report diagnostics. H16–H20 remain untouched until finalization; operator runs
any subsequent long live validation, using exact frozen commands only after adoption.

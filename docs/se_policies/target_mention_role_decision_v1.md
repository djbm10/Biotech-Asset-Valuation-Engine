# TARGET_MENTION_ROLE_DECISION v1 — pre-implementation boundary

Status: **DESIGN BLOCKED / NOT IMPLEMENTED / NOT ADOPTED**. Starting HEAD `1c78cd6`.
This is diagnosis before an implementation preregistration, not a failed scored
implementation and not a retrospective preregistration. No candidate production
code, red tests, or behavioral acceptance run exists. There is nothing to revert.

## Proposed rule examined

The existing span/query-role contract permits a complete authority-supported target
atom in the modifier position of a therapeutic request, or the object of an explicit
therapeutic targeting predicate. The diagnostic probe examines that bounded grammar,
with the existing six affix forms. It does not add an alias or use a substring resolver.

A. A full-slot native RESOLVED mention with recoverable raw assertion provenance and
one matching `(canonical identity, resolver component)` would own the target slot.
B. Contained TARGET/AMBIGUOUS_TARGET/residual/operator claims would be replaced by
that atomic target; independent claims outside its slot would be retained.
C. In the absence of a whole-slot certificate the probe proposes no override. Existing
Greek/component/separator interpretations remain baseline observations, not newly
certified target-role facts.
D. Competing identities, intersecting non-target claims and an unsupported role cannot
supply a new positive certificate. A final fail-closed projection for these cases is
**not implemented or validated** by this probe.
E. Missing raw lineage cannot supply stronger authority. All 14 known missing-lineage
mention occurrences remain subject to the adopted representation's unchanged status.

The checked grammar is in `probe_whole_role.py`. `proposed_rule_observations.json.gz`
records all 6,199 cases, including exact candidate mention, raw assertion IDs, baseline
hash, and spans proposed for removal. These are proposed operations, **not frozen
expected parser outputs**: the identity precondition below invalidates the proposal.
No narrower selection of benchmark rows was implemented after discovering the issue.

## Observed design results

| Diagnostic measure | Count |
|---|---:|
| Frozen baseline decisions inspected | 6,199 |
| Proposed whole-slot operations | 2,276 |
| Already selected complete name | 2,231 |
| No complete authority mention | 1,382 |
| Uncertified whole identity under the probe | 199 |
| Outside the bounded grammar | 93 |
| Conflicting existing semantic ownership | 18 |
| Proposed-operation source components | 235 |
| Proposed operations in multi-source-gene components | 86 |
| Such components | 9 |
| English mismatch frames covered by the proposal | 224/224 (32 names) |
| Protected Greek frames receiving no proposed override | 21/21 (3 names) |

The English cases and Greek cases alone would conceal the unsafe broader boundary.
None of the 224 English proposed operations is among the 86 multi-source cases.
This is not a reason to admit only those 224 cases: that would replace a general
identity certificate with benchmark selection.

## First missing boundary: match lineage is not identity equivalence

The v2 mention contains `authority_evidence.source_record_keys` for assertions
**matching this label**, plus a resolver `component_id` and the elected canonical ID.
A single matching source record does not imply a single source gene in that component.
The adopted raw sidecar retains the larger `resolver_components[].record_keys` list.
The new audit joins to that list and the exact `approvedSymbol` assertions. No raw
lineage is missing or reconstructed here; the provenance sidecar works as designed.

Concrete evidence, with full assertion IDs, source artifact hashes and field paths in
`source_examples.json.gz` and `multiple_source_components.json`:

- `ALK receptor tyrosine kinase`: exact approved-name assertion from
  `open_targets:ENSG00000171094`; current native ID `TARGET:EML4`. The component includes
  both ALK and EML4 source gene records, despite one matching name-source record.
- `bolA family member 2`: approved-name assertion from
  `open_targets:ENSG00000183336`; current native ID `TARGET:BOLA2B`. The component includes
  BOLA2, BOLA2B and BOLA2-SMG1P6 source records. This query has no existing target span;
  blindly accepting the whole name would create a new canonical-ID assertion.
- `L-lysine (3S)-hydroxylase JMJD7`: four exact synonym assertions from
  `open_targets:ENSG00000243789`; current native ID `TARGET:PLA2G4B`. The component includes
  JMJD7 and PLA2G4B source records.

The nine elected IDs are TUBA1B, IFNA1, CALM2, H4C8, BOLA2B, SYNCRIP, RPS27A, EML4,
and PLA2G4B. Multiple source genes do not by themselves establish either equivalence
or non-equivalence of every possible protein-level target. This audit deliberately
makes neither inference. The earlier source-identity checks already denied single-gene
alias equivalence for the tubulin, interferon and calmodulin groups; those findings stand.

Thus `native RESOLVED + one matching source component + exact raw lineage` is not a
sufficient identity certificate. Promoting it would strengthen source-grouping history
into biological identity authority. Provenance adoption never authorized that inference.

## Why implementation stops

The requested decision rule must operate on the adopted mention representation and
cannot add unsupported identity merges. A general safe gate needs the full source
component membership and an explicit identity-eligibility status, not just the member
whose label matched. The current mention has opaque pointers to that information but
no adjudicated component identity certificate. Dereferencing the sidecar can expose the
membership; it cannot manufacture an equivalence finding. We must freeze that interface
and conservative eligibility semantics before consuming it in a target decision.

Do not use a nine-ID blacklist, choose a preferred member, discard inconvenient source
records, or infer equivalence from a shared symbol, sequence, cross-reference or component.
Do not silently preserve an embedded legacy target while claiming the full-slot role
was certified. Full fail-closed behavior and exact expected deltas remain unpreregistered.

Minimum next extension, separately preregistered and decision-neutral:
**TARGET_COMPONENT_IDENTITY_ELIGIBILITY v1**. Expose for each referenced component its
complete authority source-record membership, exact canonical-symbol assertions and
provenance, elected canonical linkage, and explicit certification status. Distinguish
single-source identity from unresolved multi-source grouping; any equivalence certificate
must name its valid authority relation and scope. Missing or uncertified information
remains UNKNOWN. Existing graph components and elected IDs stay unchanged. This can use
the adopted sidecar; it requires no new source acquisition or alias inventory.

Then freeze a new complete decision-delta proposal, including how uncertified whole
names prevent embedded fallback. Preserve the three Greek interpretations through their
independent grammar certificates; do not assume old parser output is itself a certificate.

## Acceptance status and validation

D1/D2 have promising **design coverage**, not implementation PASS results. D3–D9 are not
scored: the broad identity certificate and ambiguous-role projection are not ready.
D10's implementation quality gate is not claimed. Full tests/se was not rerun because
no production, test, ingestion or snapshot file changed. Four existing representation
unit tests pass with `PYTHONPATH=src`; the first invocation without that setting failed
collection against the other installed checkout, then was corrected. Diagnostic scripts
pass Ruff. The complete 6,199 parser/compiler/trial/buyer baseline hashes were recomputed:
**6,199 identical; zero changed**. No aliases, source snapshots or decisions changed.

The two known separator oracle defects remain frozen. H21–H25 were not inspected or run;
H6–H10 remain unrun. Human-PoC recovery remains stopped. All other semantic work remains
outside scope.

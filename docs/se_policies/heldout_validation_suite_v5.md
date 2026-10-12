# HELDOUT_VALIDATION_SUITE v5 — H21–H25 primary validation

**Status: FROZEN / UNRUN, 2026-10-12.** Frozen before TARGET_QUERY_ALIAS_COVERAGE v1
diagnosis or implementation, from clean baseline `048b941`. No query below has
been compiled, resolved, searched, replayed or compared with engine output.
References and intended targets are selected from public product knowledge,
not from engine results. No authority/resolver lookup of these targets was used
to choose this suite. A case-insensitive exposure check found no occurrences of
the selected target concepts in existing policies, tests or scripts.

H1–H5 and H11–H20 are exposed development data. H6–H10 remain unrun, partially
exposed to earlier resolver diagnosis, and secondary only. H17/H20 improvements
are diagnostic, never generalization evidence. This suite is the new primary
validation. **Do not run it during the alias milestone.** A later explicit run
decision must declare one engine commit before the first query. No code or
configuration change between runs.

## Frozen queries and intended recognition

| ID | Exact query | Therapeutic-area flag | Intended sole target |
|---|---|---|---|
| H21 | Find clinical-stage antibodies against thymic stromal lymphopoietin for asthma. | omitted / UNSPECIFIED | TSLP |
| H22 | Find clinical-stage plasma kallikrein inhibitors for hereditary angioedema. | omitted / UNSPECIFIED | KLKB1 |
| H23 | Find clinical-stage anti-interleukin-36 receptor antibodies for generalized pustular psoriasis. | AUTOIMMUNE | IL1RL2 |
| H24 | Find clinical-stage myostatin inhibitors for spinal muscular atrophy. | omitted / UNSPECIFIED | MSTN |
| H25 | Find clinical-stage complement factor D inhibitors for paroxysmal nocturnal hemoglobinuria. | omitted / UNSPECIFIED | CFD |

Recognition must identify exactly the intended biological entity, with no
additional target. Canonical authority identifiers may be used to demonstrate
equivalence to the frozen symbols; formatting an identifier differently is not
a biological mismatch. A different subunit, family, complex or extra target is
a failure. No resolver probing is permitted to decide whether a query stays in
the suite. The reference set and query wording cannot be revised after exposure.

## Frozen reference sets

These are fixed reference panels, not a claim to enumerate every clinical
product. Approved products count as clinical-stage as in earlier suites.

- **H21:** tezepelumab (Tezspire, AMG 157, MEDI9929); ecleralimab (CSJ117).
- **H22:** lanadelumab (Takhzyro, DX-2930); berotralstat (Orladeyo, BCX7353);
  sebetralstat (KVD900); ecallantide (Kalbitor, DX-88); donidalorsen (IONIS-PKK-LRx).
- **H23:** spesolimab (Spevigo, BI 655130); imsidolimab (ANB019).
- **H24:** apitegromab (SRK-015); taldefgrobep alfa (BMS-986089, RG6206).
- **H25:** danicopan (Voydeya, ACH-4471, ALXN2040); vemircopan (ALXN2050, ACH-5228).

Matching retains the v2–v4 rule: casefolded alphanumeric equality of any listed
reference name with a row's canonical name or alias. Do not invent suffix
stripping, inferred trade-name equivalence or extra aliases after the run.

## Frozen procedure and metrics

Use exact queries above, `--allow-incomplete`, and `--as-of` equal to the run
date. Store results under `/home/djmann/se_runs/heldout_h21_v5` through
`heldout_h25_v5`, sequentially, at one declared commit and configuration.
Preserve result.json, logs, refusal evidence and source-coverage artifacts.
An INCOMPLETE result caused by missing source configuration is scoreable under
the same rubric; report the limitation prominently, never discard it solely
for that status. An actual interruption has no completed observation and must
remain separately marked; never silently substitute it for a completed result.

For a refusal, preserve the exact query and reason. Do not rephrase or rerun
with alternate target names; do not synthesize a shortlist. Target recognition
and query-level decision are FAIL. Shortlist metrics are N/A because there are
no rows; the query still contributes a failure to the suite denominator.

For each non-refused result, freeze the blind emitted top 20 exactly in order.
Commit labels before computing metrics. Labels retain the existing rubric:
RELEVANT (real distinct target-directed product), WRONG_TARGET (including
background/comparator products), DUPLICATE (same product as another row),
NON_ASSET (word/class/procedure/regimen/field label), UNVERIFIABLE (not judgeable
from public information). Do not make indication, approval status or the new
alias implementation an unregistered additional row-label criterion.

Query PASS requires exact target recognition and every existing threshold:

- P@20 >= 0.70; UNVERIFIABLE excluded from denominator. If that denominator is
  zero, P@20 is N/A and the query fails rather than passing vacuously.
- Recall@all >= 0.60; Recall@20 reported without a threshold.
- At most one NON_ASSET and at most two DUPLICATE rows in the top 20.
- Zero false human-PoC rows in the top 20: a row has `human_poc_present`, but its
  cited sentence is not numerical human efficacy attributable to that product.

The overall decision retains the existing suite rule: PASS if at least 4/5
queries pass and no query has false human-PoC; PASS_WITH_LIMITATIONS if exactly
3/5 pass; FAIL otherwise. Report target recognition separately from shortlist
quality, all five query decisions, metrics and source coverage. Do not claim
engine validation from target recognition alone. No thresholds may be changed
after exposure.

## Contamination controls

Exclude these five biological target concepts, their aliases, their reference
products and these query texts from manual alias-survey selection, development
fixtures, resolver probes and milestone acceptance tests. The future alias
authority may naturally contain their entries in a complete bulk snapshot;
bulk inclusion is not permission to inspect or exercise their rows. Exclusion
applies to evaluation/tuning, not to deleting legitimate authority data from
production. Store this suite separately from the development population.

No H21–H25 result exists in this milestone. This freeze does not authorize runs.

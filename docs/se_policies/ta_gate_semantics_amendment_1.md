# Therapeutic-area gate semantics — Amendment 1

Status: **FROZEN**, 2026-09-26. Append-only. The declaration `ta_gate_semantics.md` (commit
`3a015b3`, sha256 `5dfb8cac…fc34`) is not edited. Approved by the operator after the first
replay. Written and committed before any code change.

## Record of the first attempt: FAILED_ACCEPTANCE on A4

- Code: commit `8286f37`.
- Replay: sealed replay of `tac01_control_a1` into `se_runs/tac01_ta_fix`.
- Raw scorer output: `se_runs/tac01_ta_fix/ta_compare.txt`, preserved unedited.
- Scored results: A1 PASS, A3 PASS, A4 **FAIL**, A5 PASS.
- A4: 2 assets lost their ONCOLOGY classification (`Wilcoxon`, `suberoylanilide`).

**Cause: an implementation defect.** The declared semantics are not at fault.

- One document's areas were emitted as a single list-valued fact.
- The public-document extractor classifies areas over the whole document text. Every area claim,
  however, cited the same generic first-2,000-character passage.
- In both documents, the only AUTOIMMUNE term lay outside that passage. The AUTOIMMUNE claim
  therefore failed structured entailment.
- The pipeline drops a fact when any of its supporting claims is unentailed (`pipeline.py:384`).
  This dropped the independently supported ONCOLOGY area along with it.
- The `mint5_on` arm was not run, because it would carry the same defect.

## The amendment (representation only)

1. **One `therapeutic_area` fact per area.** Each fact holds one canonical area and is supported
   by exactly one claim, for that area.
2. **Area-specific evidence span.** Each area claim cites a span of the source text that contains
   a lexicon term for that area:
   - Public documents: a window around the first occurrence of one of the area's terms.
   - Registry records: the condition strings that classify to that area.

   The generic first-2,000-character passage is no longer used for area claims.
3. **Independence.** An unentailed claim for one area cannot remove the fact for another area.

## Unchanged

The following are all exactly as declared:

- the TA vocabulary and lexicon
- canonicalisation and aliases
- union gate semantics and the handling of UNKNOWN and UNSPECIFIED
- the parser
- criteria A1–A5 and the predictions
- the scorer `scripts/se_ta_gate_compare.py`

It must still hold that the candidate set and every non-TA gate decision are invariant (A3).

## Test added before replay

A document with both ONCOLOGY and AUTOIMMUNE evidence, where exactly one area's claim is
unsupported. The supported area's fact must survive the pipeline's entailment filter on its own.

## Evaluation order (binding)

1. Replay TAC01 (sealed) into a new directory. **If A4, or any other criterion, fails: stop.**
2. Only if every TAC01 criterion passes, replay `mint5_on` (sealed) and score it with
   `AUTOIMMUNE` against the same frozen criteria.

No ranking work until both arms are scored.

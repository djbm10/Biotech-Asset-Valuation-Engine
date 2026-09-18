# Productization step 4 — source and review visibility

## What already existed

Step 5 (review visibility) was largely done by the shortlist renderer built in steps 2+3:
sections are labelled, every review entry carries `review_reasons`, low-support nominations
are shown in their own held-back block rather than dropped, and the counts describe the whole
run (`eligible / review / excluded / low_support / total_candidates / shown`) so a truncated
view cannot read as a small landscape.

What did not exist was anything about **the run**. `Shortlist` carried `problem_id`, `run_id`
and `as_of_date` and nothing else, so a shortlist produced by an INCOMPLETE run — or by a run
that lost a mandatory source mid-acquisition — was typographically identical to one produced
by a clean sweep. The distinction had been recorded in `RunManifest` since B6 and printed by
the audit memo; the reader's view simply never asked for it.

That matters in one specific way: absence. A present asset is evidenced by its own records
whatever else failed, but an *absent* asset means "not in the market" only if the corpus was
complete. Without the run's status the reader cannot tell which reading applies.

## What was added

`SourceCoverage` (one row per source family) and six fields on `Shortlist`:

| field | source |
| --- | --- |
| `run_status` | `run_manifest.status` |
| `sources` | `run_manifest.source_status` joined to `search_attempts` by `source` |
| `blind_spots` | `run_manifest.known_blind_spots` |
| `incomplete_reasons` | `run_manifest.incomplete_reasons` |
| `fatal_reasons` | `run_manifest.fatal_reasons` |
| `documents_by_publisher` | `source_documents[].publisher` |

Per family: `outcome`, `queries`, `candidates_found`, `unique_candidates_added`,
`retried_queries` (attempts whose `attempts_made > 1`, so a limping acquisition is
distinguishable from a clean one), and the distinct `errors`.

Two things are deliberate:

- **`NOT_CONFIGURED` is never merged into `FAILED`.** A declared blind spot is a waivable
  scope decision; a failed source is a hole in the corpus. Collapsing them would let a broken
  run read as a scoped one.
- **`SourceCoverage.documents` is always `None`.** `SourceDocument` has a `publisher` but no
  source-family field, and the run records no attempt→document mapping. Counting documents
  per family would require inventing that mapping, so documents are counted by publisher —
  the only attribution the records actually support — and the null field is left in place so
  a consumer finds an explicit "not recorded" rather than a plausible wrong number.

A family that was declared but never queried still gets a row (zero queries), because that is
exactly the fact worth knowing.

## Rendering

`_render_corpus` emits the block **before the assets**, not in a footer: a reader who stops
after the first entry must still have seen that the corpus was unsound. Order is
warning → per-family table → documents by publisher → blind spots.

- fatal reasons → a loud `!! UNSCOREABLE` line naming each reason;
- otherwise incomplete reasons → a plain status line stating that present assets are still
  evidenced but absent ones may simply be unseen — not dressed up as fatal;
- a CONVERGED run raises no alarm at all, but still prints its sources, so a reader never has
  to ask where the corpus came from.

## Tests

`tests/se/test_shortlist_source_visibility.py` (9 tests): every declared family listed with
its outcome; per-family counts aggregated from the attempts made; a failed source carries the
error that explains it; documents counted by publisher with no invented family mapping; a
fatal failure stated before the assets; an incomplete run says so without claiming to be
fatal; a clean run raises no alarm; and the JSON view carries everything the human view
asserts, for both statuses.

Verified non-vacuous: removing the `_render_corpus` call fails exactly the three rendering
tests and no others.

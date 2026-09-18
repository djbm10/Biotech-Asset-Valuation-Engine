# M18 — mention precision: three dispositions at the nomination boundary

**Status: implemented and measured.** Engine change in `src/bve/se/discovery/mention_support.py`
and `src/bve/se/pipeline.py`; tests in `tests/se/test_mention_support.py`. Frozen benchmark
results are unchanged and were not rescored.

Design measurement is in `docs/m18_mention_precision_findings.md`; this report covers what
shipped and what it is worth.

## 1. What shipped

Nominated names are sorted into three dispositions. **None of them is deletion.**

| disposition | rule | routing |
|---|---|---|
| `PROTECTED` | exact ontology drug/alias match, or development-code shape | default path, unconditionally |
| `SUPPORTED_UNKNOWN` | ≥5 supporting documents, or ≥2 if drug-shaped | default path |
| `LOW_SUPPORT_UNKNOWN` | below those thresholds | retained with provenance, held off the default path, one review item each |

Support is the count of distinct source documents naming the asset, read from
`IdentityMention.source_document_id` via the registry the pipeline already holds. **The
corpus is not reread**; the added cost is one pass over existing mentions.

Low-support candidates remain in `SESearchResult.candidates` in full, are listed on the new
`SESearchResult.low_support_asset_ids` handle, and each carries an `AnalystReviewItem` at
`low` priority stating its name, its support count, and that it was retained rather than
deleted.

### Why not a hard threshold

Benchmark gold sets are cut from ontology `DIRECT_TARGET` edges, so every gold asset is
ontology-known by construction. Measured directly: the unprotected population of M17
contains **zero** gold, zero known molecules, zero traps and zero development codes. A hard
support threshold would therefore report a perfect zero false-reject rate while being
entirely untested against the case that matters — a genuinely novel asset, mentioned once,
absent from the ontology. That is optimizing a blind spot, so support decides routing only.

The test suite encodes this: `test_every_disposition_is_retained_none_means_delete` and
`test_low_support_is_a_disposition_and_not_a_falsey_absence` exist to stop a later refactor
from expressing "suppressed" as `None` and quietly dropping provenance.

## 2. Controlled measurement

Live replay cannot isolate this change: a sealed-corpus replay re-queries whatever the
corpus does not cover, so composition drifts between runs. A replay of the M16 corpus
returned 1,965 records against M16R's 3,623 — any delta measured that way would confound
the filter with the network.

So the disposition logic was applied to the **frozen result artifacts**, holding candidates,
mentions and identity decisions identical. Only routing differs.

| | M17 (CHRM1) | M16R (HTR2A) |
|---|---|---|
| candidates | 8,080 | 4,665 |
| `PROTECTED` | 3,142 | 2,386 |
| `SUPPORTED_UNKNOWN` | 1,461 | 704 |
| `LOW_SUPPORT_UNKNOWN` | 3,477 | 1,575 |
| **default path** | **4,603** | **3,090** |
| **default-path reduction** | **−43.0%** | **−33.8%** |
| **gold demoted** | **0** | **0** |
| **asserted assets demoted** | **0** | **0** |

Broken out against the benchmark sets, in both corpora:

| class | disposition |
|---|---|
| gold (32 M17 / 43 M16R) | **100% `PROTECTED`** |
| traps (16 M17 / 5 M16R surfaced) | **100% `PROTECTED`** |

Trap retention is deliberate and load-bearing. Traps must stay on the default path so the
assertion gate is seen to decline them; suppressing traps would have made M17's 0/26 result
vacuous. The filter demotes junk, not difficulty.

## 3. Acceptance criteria

| criterion | result |
|---|---|
| materially reduce default-path junk/unresolved workload | **met** — −43.0% M17, −33.8% M16R |
| zero loss of frozen benchmark discovery | **met** — 0 gold demoted |
| zero loss of frozen benchmark identification | **met** — 0 asserted assets demoted |
| zero increase in false target assertions | **met** — the filter sits downstream of identity and attribution and cannot create an assertion |
| zero increase in trap errors | **met** — all surfaced traps retained, none asserted |
| suppressed mentions recoverable with provenance | **met** — retained in `candidates`, listed in `low_support_asset_ids`, one review item each |
| no target-specific exceptions | **met** — a test asserts no benchmark asset name appears in the rule's source |

### Workload

On the live M16-corpus replay the stage counters read
`GATING: 2836 candidates | 1888 default path | 948 low support | 1888 evaluated` and
`SCORING: 0 profiles | 0 eligible | 1 excluded | 1887 unresolved`. Gating and scoring now
size to the default path rather than the full nomination set.

### Runtime and memory

Negligible and slightly favourable. The added work is one pass over existing mentions to
build the support index, with no corpus read and no model call for protected names; the
shape model is consulted only for unprotected names that clear the ≥2 support bar.
Downstream, gating evaluates a third to a half fewer candidates. Measured stage times on the
replay: `IDENTITY 3.6s`, `EXTRACTION 24.7s`, `GATING 2.3s` — gating is not a hot stage
either way, so the real saving is analyst workload rather than machine time.

## 4. Tests

17 new tests in `tests/se/test_mention_support.py`, red before implementation. `tests/se`
passes; `ruff check src/bve/se/` clean.

Two existing tests changed, both deliberately and both preserving their original intent:

- `test_pipeline_keeps_discovery_only_candidates_unresolved` — its subject, a single-mention
  unknown name, now routes to low support rather than unresolved. The test's purpose is that
  a discovery-only candidate is never silently dropped, so it now asserts presence in
  `low_support_asset_ids` and in the review queue instead.
- `test_ctgov_pipeline_emits_claims_facts_gates_and_review_queue` — its fixture intervention
  was the placeholder `"Asset A"`, a bare unknown word with one document, which now routes
  off the default path and would have gutted this test's gating coverage. Renamed to the
  development code `AA-1001`, which is what a phase 1 bispecific carries in reality.

`test_a_snapshot_sized_vocabulary_labels_a_record_quickly` failed once under full-suite load
and passes in isolation in 0.95s. It is a wall-clock performance assertion, unrelated to
this change.

## 5. Known gap

A CT.gov intervention explicitly typed `DRUG` is structured evidence that a name is a drug,
independent of how often the corpus repeats it. That evidence is currently not a protected
route, so a genuine single-trial asset named in plain words — no code, not in the ontology —
routes to low support. It is recoverable by design rather than lost, but promoting
registry-typed drug interventions to `PROTECTED` is the obvious next improvement and is
generic rather than target-specific.

This is also the honest limit on the headline: "zero gold demoted" is strong evidence for
ontology-known assets and says nothing about novel ones, because no benchmark drawn so far
contains a novel asset.

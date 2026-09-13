# M12 — source expansion, and what it cost the identity model

**Milestone question.** M11 established that the engine could hold an identity line under one
narrow corpus: `co-occurrence is not identity`, `otherNames is not identity`, `lack of
contradictory authority is not identity`, `identity requires positive evidence`. M12 asks
whether that line survives contact with more sources — and whether the extra sources are worth
having.

Both answers are in. The line holds. The sources are worth a little, and the report says how
little where that is the honest finding.

Frozen inputs throughout: M8 strict n=224, V2 confirmed PDCD1 n=40, confirmed negatives n=133,
`as_of_date` 2026-08-20, sealed corpus `B8_custody`. None was altered after observing any
result.

---

## Result

Eight of eleven declared source families deliver. The combined run over all eight preserves the
M11 identity graph exactly while adding half again as many assets.

| Metric | M11 baseline | M12 combined | Verdict |
|---|---|---|---|
| PDCD1 discovery | 40/40 | 40/40 | floor held |
| PDCD1 identification | 35/40 | 35/40 | floor held |
| False PDCD1 assertions | 0/133 | 0/133 | floor held |
| PD-L1 traps falsely asserted | 0 | 0 | floor held |
| Denominators | — | unchanged | comparison valid |
| M11 identity edges | 1096 | 1096 (0 missing, 0 new) | graph preserved |
| M11 assets lost | — | 0 | none lost |
| Identity aliases minted by any new family | — | 0 | see below |
| strict_M8 | 81/224 | 84/224 | +3 |
| Candidate assets | 1082 | 1623 | +541 |

Four new assets assert the run target: `IBI308`, `Pidilizumab`, `retifanlimab-dlwr`, and
`Lambrolizumab`.

### The identity result is the point

Six added families, two of them carrying full abstract and press-release prose, minted **zero**
identity aliases between them. Every per-family audit reports `m11_decisions_preserved: true`.

This matters more than the recall numbers. The Crossref conference tranches carry titles only,
so they could not have reached the identity path even in principle — a zero there is structural
and proves nothing. The AACR bulk proceedings and the SEC-filed press releases carry full text
and *could* legitimately have minted aliases. They did not. That is an empirical finding about
how M11 behaves under rich text, and it should be read as evidence rather than as a guarantee:
a future corpus could still supply admissible `IDENTITY_EVIDENCE`, and the system is supposed
to mint an alias when it does.

`Lambrolizumab` is the clearest illustration. It is historically the same molecule as
`Pembrolizumab`, it appears asserting PDCD1, and it remains a **separate asset**, because
nothing in the corpus positively establishes the identity. A system optimising for a tidy asset
list would merge them. This one is not allowed to, and did not.

## Per-family findings

| Family | Status | Docs | Incremental value |
|---|---|---|---|
| `conference_asco` / `ash` / `aacr` (Crossref) | ENABLED_FROZEN | 600 records | titles only; cannot reach identity |
| `conference_aacr_bulk` | PUBLIC_BULK_PARTIAL | 406 records | +300 assets, `retifanlimab-dlwr` newly asserts the target |
| `sec_edgar` | ENABLED_FROZEN | 23 records | modest |
| `company_press_release_sec_filed` | PARTIAL | 2 documents | benchmark unmoved in either direction |

### `company_press_release_sec_filed`: a negative result, reported as one

239 raw EDGAR hits, 2 admitted. The obvious move is to loosen the classifier until the yield
looks respectable. That was not done, and the audit explains why it should not be: of the 361
unique refused hits, 327 were filed on forms that do not carry issuer press releases at all,
and of the EX-99 exhibits on eligible forms, 14 of 15 sampled were investor decks and corporate
presentations. Those decks mention press releases in body text — at character offsets 2491,
7356, 11346, 19861 — so widening the 2000-character header window would admit presentations as
releases. The yield is genuine scarcity.

The family contributed 43 assets, no new target assertions, and moved no benchmark metric in
either direction. It is recommended for enablement because it is cheap, mechanically
well-attested and costs the floor nothing — **not** because it proved useful. A source family
adding little is an acceptable scientific result.

One real defect did surface during the audit: eligibility was restricted to 8-K, which excluded
6-K, the current report for foreign private issuers. That filtered by the registrant's
nationality rather than by document genre, silently excluding every non-US issuer from a family
whose purpose is issuer-authored news. Widened to `{8-K, 6-K}` in `db6a2e2`. The frozen v1
tranche predates the fix and its narrower coverage is recorded rather than papered over.

## Two silent-failure defects, and why they are the real output

Both defects found in M12 share a shape: **the run completes, reports success, and produces
scores that are plausible and comparable but do not mean what they appear to mean.** That is
strictly worse than a crash.

**1. Silently dropped source families (`5932b8c`).** The CLI built indexed adapters by iterating
the mandatory-source tuple, so any newly built family was dropped with no error. The tranche
under test contributed nothing and the run looked fine. Caught because a bulk replay reported
exactly CT.gov + PubMed records and no more. The mandatory tuple is the completeness contract —
which sources a run must have *reached* — not the list it is permitted to read.

**2. A shared query budget masquerading as an identity regression (`683930c`).** The first
combined evaluation showed 78 missing M11 edges and 119 lost assets. Read naively, that is the
headline finding of M12: adding sources corrupts the identity graph. It was false.
`max_queries` (5000) was a pool shared across all sources, with the adapter loop nested inside
the query loop, so exhausting it truncated every source to the same prefix of the query plan.
Three delivering sources needed 2872 queries and never hit the cap, each receiving 955. Eight
needed ~7700, hit it, and each received 625. PubMed returned 6923 records instead of 10691, and
those 3768 absent records *were* the missing edges.

Rerunning with identical families and the identical sealed corpus, changing only the budget
semantics, produced 0 missing edges and 0 lost assets. That isolates the cause conclusively.
The confounded run is retained on disk, labelled, as evidence — never as a result.

Per-source is also the reading that leaves every frozen result untouched, since no frozen run
ever issued more than 955 queries to a single source. The alternative, a scaled global pool,
would have required inventing a scaling factor.

## Coverage boundaries that remain

Stated because a coverage claim is only as good as its exclusions.

- **`conference_eha`** and the full **ASCO / AACR / ASH proceedings** need authorized or paid
  access. Not purchased, not requested; public mechanical routes were exhausted first.
- **AACR bulk** served Part-1; Parts 2–5 return 404 from the publisher. Clinical and
  late-breaking proceedings remain licensed and are not claimed as covered.
- **`company_press_release` / `company_pipeline_or_presentation`** are blocked by publisher
  403s — anti-bot controls, not a code problem. They stay NOT_CONFIGURED rather than being made
  to look configured.
- **SEC registrant status is not a definition of "company."** The press-release family reaches
  issuer news only through the SEC, so private, foreign-unlisted and pre-IPO companies are
  structurally invisible to it. That is a boundary of the route, not of the world, and must not
  silently become the working definition.

## What M12 does not establish

M12 shows the identity model holds under source expansion **for PDCD1**. It does not show the
engine generalises: every number here is computed against a target the system has been iterated
on since B6. Whether this is a general biotech discovery engine or a well-tuned PDCD1 system is
exactly what M13 exists to find out, on an untouched target chosen at arm's length.

## Provenance

Sealed artifacts, decision log (26 entries) and recovery state:
`/home/djmann/staging/pdcd1_baseline/`, outside the repo by design.
`M12_combined_evaluation_seal_v1.json` (`76328d92345929e3…`) hashes the authoritative combined
result and its gates; `M12_source_coverage_v2.json` carries per-family status with real reasons.
`M12_HANDOFF.md` is the recovery entry point.

Nothing was reacquired during M12 verification, and no sealed artifact was mutated.

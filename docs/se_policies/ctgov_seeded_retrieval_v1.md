# ClinicalTrials.gov asset-seeded retrieval (v1)

Status: **DECLARED**, 2026-10-25, before any code change. Development work. It follows the
second blinded pilot, `chek1_clinical_any_v1`, whose preregistration, seal, reference and
scores stay unchanged. No result here re-scores that pilot.

## Root cause (read from the code; to be pinned by a failing test first)

`QueryVocabulary.for_query()` correctly stores an authority-seeded query's *drug* aliases as
that query's terms. It avoids the target vocabulary on purpose, so that a drug can be found
in trials that never name its target. But `QueryVocabulary.query_facets()`, which
`ClinicalTrialsGovAdapter._acquire()` uses to build the request, ignores those stored terms
and rebuilds the facet from `_retrieval_aliases(canonical)`, i.e. the **target's** aliases.

So every seeded CT.gov query sends the target search:
- in `chek1_clinical_any_v1`, all 30 CT.gov attempts (10 queries × 3 passes) mapped to one
  identical 27-record set;
- the same reconstruction applies to depth-1 follow-up queries, whose lead name is likewise
  dropped. The GUCY2C live diagnostic logged the PF-07062119 follow-up URL carrying the
  GUCY2C alias list.

PubMed is not affected, because it sends the compiled query string itself.

## Change

- **S1. Retrieval terms follow the query's kind.**
  - An `AUTHORITY_SEEDED_ASSET` query retrieves with the drug's own names (the query's
    aliases, which the compiler took from the authority).
  - A depth-1 follow-up retrieves with its lead name.
  - A target-vocabulary query is unchanged: target aliases, ANDed with any requested
    modality facet.
  - Seeded queries carry no modality, and follow-ups keep their inherited modality facet as
    today.
- **S2. Nothing else changes.**
  - Retrieval by a drug name is **retrieval context only**. Relevance and nomination still
    go through the existing per-intervention scan, which uses the seeded query's drug
    aliases as terms. Its target observations still land only in
    `discovery_target_context`.
  - Target evidence still comes only from authority edges and construct-target attribution.
  - Trial attribution and identity are unchanged. A record retrieved by a code becomes a
    candidate only for the intervention whose own text names the code.
  - Identity (aliases, merges, `otherNames` policy), gates, the ontology, the query compiler
    and the custody key (compiled query text) are all unchanged. Sealed corpora replay
    exactly as before, because replay serves records by query text.

## Acceptance criteria (frozen before implementation)

| | Criterion |
|---|---|
| T0 | A test fails on the current code showing a seeded query's CT.gov request carries target aliases, not the drug's names; and the same for a follow-up |
| T1 | Two seeded drugs produce different request expressions and different record sets (fake provider) |
| T2 | A historical alias in the query (an older code) is sent, and a record naming only that alias is retrieved and nominated for it |
| T3 | Overlapping record: a combination trial retrieved by two seeded queries is materialized once (one snapshot) and nominated for each drug only via its own intervention |
| T4 | Empty result → `NO_EVIDENCE_FOUND`, not FAILED; no candidates |
| T5 | Ambiguous or unrelated: a retrieved record's other interventions (a chemotherapy partner, an unrelated drug sharing the trial) are not nominated as the seeded drug and get no target from the seed |
| T6 | Retrieval context establishes nothing: a candidate found only through a seeded record has its target asserted by the authority edge, never by `discovery_target_context`; no `target_action_type`, human PoC or ELIGIBLE follows from retrieval alone |
| T7 | The as-of cutoff still withholds records updated after the as-of date |
| T8 | Determinism: replaying the sealed `chek1_clinical_any_v1` custody with the new code yields the same candidates, routes and trials as the sealed run (DEVELOPMENT check, not a re-score) |
| T9 | The target-vocabulary query's request is byte-identical to before |
| L1 | Bounded live diagnostic (≤ 25 CT.gov requests, free API): each seeded query's HTTP request differs from the target query's, and at least half of the seeded queries return a record set that differs from the target-term set |
| L2 | Live: the main target query's record set is unchanged in size, give or take day-to-day registry drift (reported) |
| Q | S&E suite, Ruff and mypy show no new failures or errors |

The live diagnostic reports request URLs, record counts and record-set overlap, labelled
DEVELOPMENT. It does not read the CHEK1 hidden reference, and it does not compute any score.

## Amendment 1 (after the first live diagnostic, before acceptance is assessed)

The first live diagnostic (15 requests) showed S1 working: 9/9 CHEK1 and 4/4 GUCY2C seeded
requests differ from the target request and return their own records. It also exposed a
**T5 violation that the old target-only universe had hidden**: when a trial has a single
therapeutic intervention, that intervention inherits the protocol's "targets", which for
a seeded query are only the drug's name appearing somewhere in the protocol. Linaclotide's
60 records nominated:
- arm descriptors ("Assessment of Responsiveness to Treatment by Experience Sampling Method");
- a device ("HygiPrep");
- another drug's regimen ("2 mg Prucalopride plus 2 L Polyethylene Glycol regimen").

That is retrieval context turning an unrelated intervention into a candidate.

Change: for an `AUTHORITY_SEEDED_ASSET` query, the single-intervention and backbone (C4)
inheritance are switched off. An intervention is nominated for the seed only when its own
text (name, description, otherNames) names the drug. Target-vocabulary and follow-up
queries are unchanged. Test: `TestAmendment1`, which fails with the amendment disabled.

Acceptance (L1/L2 and the nomination check) is assessed by re-reading the **same records**
the first live run saved, per query, through the amended code. No further live requests are
made, so the 25-request bound holds.

## Test changes

- `tests/se/test_study_identifier_boundary.py::_StubVocabulary` gains
  `identity_seeded = False`, the vocabulary attribute Amendment 1 reads. The test's
  assertions are unchanged.

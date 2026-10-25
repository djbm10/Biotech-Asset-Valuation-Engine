# CT.gov asset-seeded retrieval fix: development report

**Grade: DEVELOPMENT.** These are retrieval diagnostics on the CHEK1 pilot problem and the
GUCY2C development problem. Neither is validation. The `chek1_clinical_any_v1`
preregistration, seal, hidden reference and official scores are unchanged. Nothing here
re-scores that pilot.

Policy, frozen criteria, amendment and test changes: `docs/se_policies/ctgov_seeded_retrieval_v1.md`
(declared at `9df0a34`, before code).

## Root cause (pinned by tests that failed on the old code)

`QueryVocabulary.for_query()` stored an authority-seeded query's own drug names as its
terms. `QueryVocabulary.query_facets()`, which `ClinicalTrialsGovAdapter._acquire()` uses to
build the CT.gov request, then rebuilt the facet from `_retrieval_aliases(canonical)`, the
**target's** aliases. Every seeded query, and every depth-1 follow-up, therefore sent the
target search.

In the CHEK1 pilot, all 30 CT.gov attempts mapped to one 27-record set. A trial registered
under a drug code that never writes the target's name could not be acquired. PubMed was not
affected, because it sends the compiled query text.

Old-code failures: T0 (seeded and follow-up facets were `{cd19}`), T1, T2, T3, T4 and T7.

## Fix

- **S1:** an `AUTHORITY_SEEDED_ASSET` query sends its drug's names, a follow-up sends its
  lead, and a target-vocabulary query is unchanged (T9).
- **Amendment 1:** for a seeded query, an intervention is nominated only when its own name,
  description or otherNames names the drug. The single-intervention and backbone
  inheritance is off. This enforces preregistered T5, which the first live check showed
  being violated.

Unchanged:
- target evidence: authority edges and construct targets only, with retrieval context kept
  in `discovery_target_context` (T6);
- identity rules, gates, ontology and compiler;
- the custody key (query text).

## Tests

`tests/se/test_ctgov_seeded_retrieval.py`, 13 cases, against a fake registry that serves a
protocol only when the request names it:
- different drugs → different requests and record sets;
- a historical code;
- an overlapping trial, materialized once and nominated per drug;
- an empty result, which is NO_EVIDENCE_FOUND;
- partner and unrelated interventions not nominated;
- context, not target assertions;
- the as-of cutoff withholds later records;
- the target query unchanged;
- Amendment 1, in both directions.

**T8 determinism:** replaying the sealed CHEK1 custody with the new code reproduces the
sealed run exactly: 701 candidates, every route and every trial attachment. The candidate
export differs only in `run_id` and `run_started_at`. This held both before and after
Amendment 1.

## Bounded live diagnostic (2026-10-25; 15 CT.gov requests, 29 s, 1.76 GB)

`live_seeded.py` ran through the production `rest` provider, logging every HTTP URL. It
covered the target query plus every seeded query, for two problems. Nomination after
Amendment 1 was re-read from the same saved records with no new requests
(`reread_saved.py`). Outputs: `results/live_requests.json`, `results/reread_amended.json`.

| | CHEK1 pilot problem | GUCY2C dev problem |
|---|---:|---:|
| Seeded queries | 9 | 4 |
| Seeded HTTP requests that differ from the target request | **9/9** | **4/4** |
| Seeded record sets that differ from the target set | **9/9** | **4/4** |
| Target-query records (same as the sealed pilot: 27) | 27 | 73 |
| Records reached only by seeded queries | **51** | 75 |
| CT.gov records in total (target ∪ seeded) | 27 → **78** | 73 → 148 |

Example request (rabusertib):
`query.intr=("RABUSERTIB" OR "IC-83" OR "LY-2603618" OR "LY2603618" OR "Ly-2603618" OR
"Rabusertib")` returns 7 records, none of them in the 27-record target set. Under the old
code this query sent the CHEK1 alias expression.

CHEK1 records per seeded query (target-set overlap in brackets):

| Seed | Records | Nominated (after Amendment 1) |
|---|---:|---|
| prexasertib | 20 (9) | Prexasertib, prexasertib, LY2606368, ACR-368, "Drug 1: LY3023414; Drug 2: Prexasertib" |
| UCN-01 | 22 (0) | three spellings: "UCN-01 (7-hydroxystaurosporine)", "7-hydroxystaurosporine (UCN-01)", "hydroxystaurosporine" |
| rabusertib | 7 (0) | LY2603618, "IC83/LY2603618" |
| MK-8776 | 4 (1) | MK-8776, SCH 900776 |
| AZD7762 | 3 (0) | AZD7762 |
| XL-844 | 2 (0) | **none** (see below) |
| PF-00477736, GDC-0425, GDC-0575 | 1 each (0) | the code itself |

**Count-level comparison, development only.** The CHEK1 pilot's committed per-asset table
(`chek1_clinical_any_v1/results/score_detail.json`) lists the reference's trial counts.
The seeded record counts equal them for prexasertib (20), rabusertib (7), MK-8776 (4),
AZD7762 (3), XL844 (2), PF-00477736, GDC-0425 and GDC-0575 (1 each). That is 39 of the
reference's 48 trials, against 15 in the sealed run. This compares counts only. It is not a
re-score: no trial was matched to the reference, the hidden key was not read, and the
pilot's numbers stand. **It also does not mean the engine would attach these trials.**
XL-844's 2 records nominate nothing, and attachment goes through identity resolution.

GUCY2C (disclosed development example):
- the one in-scope seeded drug, indusatumab vedotin, already had all 4 of its trials in the
  target set;
- the 75 new records belong to the three agonist negative controls (linaclotide 59 new,
  plecanatide 14, dolcanatide 2).

So on GUCY2C the fix adds **no in-scope trials**, and it adds control trials that the
agonist gate must still exclude. Amendment 1 removed 2 nominations there, the HygiPrep
device and "Polyethylene Glycol". It changed nothing on CHEK1.

## Remaining identity problems (not fixed here)

1. **Hyphenation.** CT.gov retrieves `XL844` records for `"XL-844"`, but nomination needs a
   whole-word match of the seeded alias, so 2 retrieved trials yield no candidate.
2. **Composite and variant intervention names become separate strings**:
   - "Drug 1: LY3023414; Drug 2: Prexasertib";
   - "IC83/LY2603618";
   - three UCN-01 spellings;
   - ACR-368 vs prexasertib;
   - SCH 900776 vs MK-8776.

   These are the CHEK1 pilot's split class, and more retrieval means more of them.
3. **"Names the drug" is not "is the drug".** Interventions whose text mentions the seed are
   still nominated:
   - "Placebo" (matching plecanatide);
   - linaclotide arm descriptors ("Functional Constipation (FC) participants …").

   Whether such a string is an asset is left to qualification (comparator and descriptor
   vetoes), and that is not measured here.
4. **Retrieval breadth now follows the authority's seed list.** A drug with no authority
   edge (LY2880070) still has no seeded query, and its trials are found only if they name
   the target.

## Readiness

The retrieval defect is fixed and shown live. CHEK1 CT.gov records went from 27 to 78, and
every seeded request is distinct. **Retrieval alone does not make the engine ready for a
fresh benchmark.** The new records flow into identity, and items 1–3 above will turn
recovered trials into splits and descriptor candidates. A fresh benchmark now would
measure identity errors more than retrieval. The honest next step is the CT.gov
code-normalization and composite-name problems (1–2), measured on development data. After
that comes a new drawn target.

# Therapeutic-area gate semantics — declaration

Status: **DECLARED**, 2026-09-26. Written and committed before any code change or replay.
Scope ruling (operator, 2026-09-26): a small, isolated gate milestone with **exactly two
changes**, no parser work bundled. It follows `docs/se_ranking_audit.md` §3 items 1–2.

## The two changes

1. **Canonical comparison.** Requested areas (`StrategicGap.therapeutic_areas`) and observed
   areas (`therapeutic_area` facts) are compared in one canonical space, not as case-sensitive
   strings. Canonicalisation: strip, casefold, collapse whitespace and hyphens to `_`,
   uppercase, then apply a declared alias table:
   - `ONCOLOGY` ← `CANCER`
   - `AUTOIMMUNE` ← `AUTOIMMUNITY`, `AUTOIMMUNE_DISEASE`

   No other aliases. `IMMUNOLOGY` is broader than autoimmune and is **not** an alias.
2. **Multi-valued evidence.** A source document can support more than one area. Each document
   emits one `therapeutic_area` fact whose value is the sorted list of canonical areas it
   supports. Each area gets its own claim, citing the same passage. The hard-coded `"oncology"`
   is removed from `evidence/clinicaltrials.py`, `evidence/generic.py` and the
   `evidence/entailment.py` special case.

The vocabulary lives in `bve.se.ontology.therapeutic_areas`. `gates` may import `ontology`,
and `ontology` is where the modality vocabulary already lives.

## Frozen lexicon (substring match on casefolded text, as today)

- **ONCOLOGY**: `cancer`, `leukemia`, `lymphoma`, `malignancy`, `myeloma`, `oncology`, `tumor`.
  - This is the existing `generic.py` list unchanged.
  - For ClinicalTrials.gov conditions it adds the single term `oncology`, which the registry
    list lacked. No other oncology behaviour changes.
- **AUTOIMMUNE**: `autoimmun`, `lupus`, `rheumatoid arthritis`, `multiple sclerosis`,
  `systemic sclerosis`, `scleroderma`, `myasthenia gravis`, `neuromyelitis optica`, `nmosd`,
  `sjogren`, `sjögren`, `vasculitis`, `myositis`, `immune thrombocytopeni`, `pemphig`,
  `igg4-related`, `antiphospholipid`, `chronic inflammatory demyelinating`, `cidp`,
  `psoriasis`, `psoriatic`, `ankylosing spondylitis`, `crohn`, `ulcerative colitis`,
  `type 1 diabetes`, `graves`, `hashimoto`, `celiac`, `vitiligo`, `alopecia areata`.
  - Deliberately excluded: `sclerosis` alone (ALS, tuberous sclerosis), `sle`/`itp`/`ms`/`anca`
    as bare substrings, GvHD (alloimmune), atopic and allergic disease, IgA nephropathy.

The lexicon is a taxonomy of disease classes. It names no target, programme or company.

## Gate semantics that the two changes force

The existing `IN` evaluation is per fact: all facts pass → PASS; none pass → FAIL; mixed →
UNKNOWN ("facts disagree"). Once evidence is multi-valued, an asset with one oncology trial and
one lupus trial does not have disagreeing facts. It supports both areas. So the TA requirement
gets its own evaluator, with **union** semantics:

- **PASS** — the union of observed areas intersects the requested areas.
- **FAIL** — observed areas exist and are disjoint from the requested areas, *and every
  requested area is one the lexicon classifies*.
- **UNKNOWN** — no TA fact; any existing conflict or staleness guard (unchanged); or disjoint
  when a requested area is outside the lexicon. The evidence layer cannot see an area it does
  not classify, so its absence is not a negative.
- **Not evaluated** — the requested areas are only `UNSPECIFIED`, the compiler's placeholder
  for "none stated". Today that placeholder FAILs every oncology-classified asset. With change 2
  it would FAIL every classified asset. `UNSPECIFIED` is the absence of a constraint, not an
  area, so no TA requirement is emitted. This follows the precedent that empty indications
  mean landscape-wide discovery.

The last two bullets are consequences of the two changes, not new features. They are recorded
here so they are not mistaken for scope creep.

## Explicitly not changed

- The query parser: `large → LARGE1`, `CD19-directed` unrecognised, and query residue compiled
  into `strategy.indication`. These are logged as a separate parser milestone.
- The `strategy.indication` gate.
- The ONCOLOGY term list, apart from the single ctgov addition above, and the known
  `tumor` ⊂ `tumor necrosis factor` false match. That match is logged, not fixed.
- Document-level attribution in `generic.py`: an abstract's areas still attach to every asset
  it names.
- FAIL for a disjoint area inside the lexicon. For example, an oncology-only asset on an
  AUTOIMMUNE request still FAILs, as it does today.
- Ranking and shortlist order.

## Evaluation

This change is downstream of acquisition. Under the binding rule in `docs/se_handoff_state.md`
it may be evaluated by **sealed replay**. The two arms:

- `mint5_on` (AUTOIMMUNE)
- `tac01_control_a1` (ONCOLOGY)

Each arm is replayed from its own `custody/` at the fix commit and compared with the frozen
`result.json`.

### Acceptance criteria (all must hold)

- **A1 — ONCOLOGY PASS.** In `tac01_control_a1`, no asset with an ONCOLOGY-classified fact
  FAILs `strategy.therapeutic_area`.
- **A2 — AUTOIMMUNE PASS.** In `mint5_on`, no asset with an AUTOIMMUNE-classified fact FAILs
  `strategy.therapeutic_area`, and the PASS count is > 0 (it was 0).
- **A3 — isolation.** For every asset present in both the frozen and the replayed result, every
  gate decision other than `strategy.therapeutic_area` has the same status. Both runs have the
  same candidate set and the same low-support set. If replay drift makes the candidate set
  differ, the drift is reported and A3 is judged on the intersection.
- **A4 — oncology conservation.** The ONCOLOGY-classified asset set is a superset of the frozen
  `"oncology"` asset set. Every addition is listed and attributed to the `oncology` term.
- **A5 — no disposition change without a TA decision change.** Every EXCLUDED ↔ non-EXCLUDED
  movement coincides with a changed `strategy.therapeutic_area` status.

### Declared predictions (reported, not criteria)

- **`tac01_control_a1`: the visible population will barely move.** Most trial-backed assets
  also FAIL `strategy.indication` because of query residue (parser defect 3: 607 FAILs). Fixing
  TA alone does not surface them. The benchmark therefore needs a query whose parser
  interpretation is already known to be clean.
- **`mint5_on`:** TA PASS rises from 0. Some assets excluded only by TA (for example,
  cyclophosphamide with an NMOSD trial) leave EXCLUDED. Assets that FAIL the dual-target gate
  stay excluded.

Reported per arm, before → after:

- TA PASS/FAIL/UNKNOWN
- EXCLUDED → UNRESOLVED/ELIGIBLE movements
- visible (not excluded, not low-support) count
- human-PoC passers on the visible path

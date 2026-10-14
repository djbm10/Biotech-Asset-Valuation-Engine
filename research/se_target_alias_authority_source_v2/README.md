# TARGET_ALIAS_AUTHORITY_SOURCE v2 — STOP. Target-alias work PARKED.

Prereg `42b94f7`; universe/sample/packet frozen `1413e32`; independent reviewer labels frozen before verdicts (next commit). Design only; no production change. Reproduce: `python research/se_target_alias_authority_source_v2/universe.py` then `audit.py --output <dir>` (both with `PYTHONPATH=src`). Source hashes are verified, the universe has no drift, and two builds are byte-identical. Self-test: a valid fixture is JUSTIFIED; an admitted negative, reviewer-unsafe, EC, `statin` regression, H20 identity loss and a too-easy population each give STOP; safe-but-small gives LIMITED.

## Population

Candidate universe across all 78,378 runtime targets: **26,230 names** (A 8,212; A-unchained 248; B-current 468; B-hist 17,302). Rejections: over 2-token cap 21,378; EC 1,994; other NCIt protein claimant 1,740; runtime target claimant 446; no single consistent chain 248; other HGNC claimant 170; ordinary-word shape 23. Admitted: A 2,227; B-current 96; B-hist 320. **Independent negatives:** 113 universe keys collide with runtime DRUG aliases or NCIt non-product names, so the overlap requirement (≥ 20) is met. **Independent positives:** 400 hash-sampled targets disjoint from v1 and heldout symbols; 27 admitted reachable names reviewed blind by a separate agent context (9 SAFE, 18 UNSAFE; low confidence on 3).

## Results

| Policy | S1 independent negatives | S2 reviewer | S3 EC | S4 regression | S5 H20 | Coverage (≥10%) | Verdict |
|---|---|---|---|---|---|---|---|
| **A** NCIt protein, single chain | **FAIL: 20** (`angiotensin`, `vasopressin`, `procalcitonin`, `c peptide`, `human albumin`, `pancreozymin`, `vegf165`, `mage a3` …) | **FAIL: 14 unsafe** (isoforms `PlGF-1`/`PlGF-131`, precursor `ProEGF`, family `MEK Kinase`, `G(q) Alpha`, non-human `P450 PB-1`, clone id `MGC5172`) | pass | **FAIL** (`statin-like`, title case on NCIt C38583) | pass | 1.5% | **STOP** |
| **B** HGNC current | **FAIL: 1** (`athena`) | pass (0 reviewed) | pass | pass | **FAIL** (not in HGNC current names) | 0% | **STOP** |
| B-hist (diagnostic only) | FAIL: 29, mostly **disease names** stored as previous gene names (`rett syndrome`, `werner syndrome`, `friedreich ataxia`) | FAIL: 4 | pass | FAIL | FAIL | 0.5% | STOP |

**First failing boundary:**
- **Policy A:** claimant-unique, identifier-chained NCIt protein synonyms are still dominated by peptide hormones and drug substances (`angiotensin`, `vasopressin`, `human albumin` are also drugs), isoforms and precursors, and family names. NCIt synonym typing does not distinguish whole-gene identity from isoform, precursor or family. That is the missing source semantics.
- **Policy B:** safe but useless; it adds essentially nothing and does not contain `factor XI`.
- **Historical names:** disease and phenotype names stored as previous gene names make them unsafe by default.

## H20 / H17

- **H20 `factor XI`:** admitted under A via NCIt C201572 → HGNC:3529. Injected offline chain: compiles **5 plans carrying TARGET:F11**; bare `F11` stays ambiguous (F11, ZNF160). The H20 path works, but the policy that admits it is unsafe in general, so it cannot be adopted. A single-alias exception is forbidden.
- **H17 `IL-4Rα`:** unchanged known refusal; not attempted.

## Disposition

No production coverage is scientifically justified, and implementation is **not authorized**. Per the stopping rule, target-alias work is parked; no v3 is started. A future attempt would need a source that types names at the isoform/precursor/family level (e.g. UniProt name categories, full coverage, not 348 accessions) plus a drug-substance disambiguation layer. Next workstream: the **CT.gov posted-results source-availability survey**.

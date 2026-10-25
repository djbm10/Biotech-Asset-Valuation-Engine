# Intervention naming and identity (v1): development report

**Grade: DEVELOPMENT.** The CHEK1 and GUCY2C data are disclosed development examples, and
CHEK1 is scored here against its AI reference with the pilot scorer's own definitions. **Not
validation.** The `chek1_clinical_any_v1` seal, reference and official scores are unchanged.
Policy, frozen criteria and implementation clarifications:
`docs/se_policies/intervention_identity_v1.md` (declared at `042ccb1`, before code).

## What was fixed

| | Defect | Fix (general; no product names) |
|---|---|---|
| N1 | `XL844`, `IC83`, `MK8776`, `SCH900776` and `UCN01` resolved to nothing, while `XL 844` / `XL-844` resolved | drug lookups retry a compact development code (1–6 letters + 2–8 digits) once with a separator; accepted only if that form resolves unambiguously. Never targets |
| N2 | a seeded `XL-844` query could not nominate an intervention written `XL844` | that query's code-shaped aliases also match their compact/separated spelling |
| N3 | `Drug 1: LY3023414; Drug 2: Prexasertib` was one candidate; `IC83/LY2603618` and `UCN-01 (7-hydroxystaurosporine)` were whole-string candidates | composite labels are expanded for extraction only. Enumerated labels become constituents, each nominated only on its own evidence. A pair becomes name + related name, and the **existing** ingest classification decides alias, partner or uncertain. The original label is kept as an UNCERTAIN edge, and the snapshot is unchanged |
| N4 | seeded queries nominated a placebo, arm descriptors and trial titles because their description or the record mentioned the seed | seeded nomination reads the name and otherNames only, and seeded queries have no title fallback |

Unchanged:
- retrieval;
- target evidence (authority edges and construct targets);
- the otherNames corroboration rule;
- authority consolidation (identifier names only);
- qualification, gates, as-of filtering and the custody key.

## Measurement

One bounded live CHEK1 run on `e72ad34`, before any code change (4:09, 2.08 GB, INCOMPLETE
for the same 7 unconfigured families; CT.gov 43 queries). Then a replay of **those
identical bytes** with the new code (3:48, 2.00 GB).

In the replay, 3 new follow-up queries (`IC83`, `UCN-01`, `XL844`, names the new code now
nominates) had no sealed record and failed as divergences, as declared. Their own trials
were already in hand.

| Measure (CHEK1 AI reference, disclosed) | e72ad34 live | new code, same bytes |
|---|---:|---:|
| Candidates | 712 | 707 |
| Analyst-visible (eligible + review) | 100 (7 + 93) | 97 (9 + 88) |
| Recall, all / visible | 12/14 / 12/14 | 12/14 / 12/14 |
| Strict precision, visible | 12/100 = 12.0% | 12/97 = 12.4% |
| Adjudicated precision, visible | 85.7% | 85.7% |
| Scorer merge errors | 0 | 0 |
| Engine merges joining two different authority drugs | 0 of 12 | 0 of 12 |
| Scorer split errors | 2 (R-001 ACR-368, R-005 PF477736) | 2 (same) |
| **Reference trials attached, overall** | 39/48 = 81.2% | **43/48 = 89.6%** |
| Reference trials attached, recovered assets | 86.7% | 95.6% |
| Negative-control hits, visible | 0 | 0 |
| ELIGIBLE | 7 | 9 (+XL844, which is in scope; +UCN-01, the reference's own judgement-call exclusion; both with authority-confirmed CHEK1 targets) |
| Target accuracy, stated / incl. UNKNOWN | 1.00 / 0.67 | 1.00 / 0.67 |

For context only (no claim): the sealed pilot attached 15/48 trials (31.3%). The e72ad34
run's 81.2% comes from the seeded-retrieval fix, and the further gain here from these
identity fixes. Both are development runs on later live data, so the pilot's official 31.3%
stands.

Per identity (new code, same bytes):

| Identity | e72ad34 | New code |
|---|---|---|
| XL-844 | `XL-844` (0 trials); records written `XL844` not nominated | **`XL844`, 2 trials**, merged with XL-844 |
| rabusertib | `rabusertib` (6) + `IC83/LY2603618` (1) | **`rabusertib`, 7 trials** (IC83 and LY2603618 as aliases) |
| prexasertib | `Prexasertib` (17) + `Drug 1: LY3023414; Drug 2: Prexasertib` (1) | **`Prexasertib`, 18 trials**. The LY3023414 constituent is not nominated: no evidence of its own |
| SCH 900776 / MK-8776 | one candidate (3) | unchanged, one candidate |
| ACR-368 | separate (2), UNCERTAIN edge to prexasertib | unchanged: no authority record corroborates it |
| UCN-01 | `UCN-01 (7-hydroxystaurosporine)` (1) + `7-hydroxystaurosporine (UCN-01)` (2) + `hydroxystaurosporine` (19) + `UCN-01` (0) | `UCN-01` (1) + `hydroxystaurosporine` (21): **still split** |

Seeded nominations re-read from the saved live records (`~/se_runs/ctgov_seeded_live`, no
new requests):
- **linaclotide:** 7 descriptor, placebo and title nominations removed. "Lactose placebo
  pill", "Optimized Medical treatment", "Evaluate the Safety of Linaclotide in IBS-C
  Patients in China", two cohort descriptors, a regimen of another drug, and "Assessment of
  Responsiveness to Treatment…". Trials attached through the seed drop from 58 to 53; the 5
  lost trials were attached only through those strings.
- **CHEK1 seeds:** composites resolved, and XL844 gained 2 trials. Nothing else changed.
- **plecanatide:** `Placebo` is still nominated, because one record's otherNames say
  "Trulance placebo", which contains a seeded trade name. N4 still reads otherNames, and
  comparators are left to the downstream comparator veto.

Old-universe determinism (D7): replaying the sealed pilot custody with the new code gives
the same recall (12/14), the same splits (R-001, R-003, R-005 all; R-003, R-005 visible),
the same 31.3% coverage and the same 94 visible candidates. There are 704 candidates, +3
low-support.

## Acceptance

| | Result |
|---|---|
| I1–I5 (unit) | PASS (17 tests; 10 failed on the old code, and the 7 that passed are the negative and preservation cases) |
| D1 recall | PASS (unchanged) |
| D2 no false merges | PASS (0 scorer merges; 0 cross-drug engine merges) |
| D3 splits | PASS (no rise). Consolidated: SCH 900776/MK-8776, prexasertib/LY2606368, rabusertib/LY2603618/IC83. ACR-368 stays separate by rule. **UCN-01 is not one candidate**; see below |
| D4 trial attachment | PASS (39 → 43; XL844 attached) |
| D5 junk seeded nominations | PASS (7 removed, 0 added; 1 placebo remains via otherNames) |
| D6 no unsupported assertions | PASS (no new target except via authority; both new ELIGIBLE have authority-confirmed targets) |
| D7 sealed replay | PASS |
| Q | PASS: S&E suite 2188 passed, 3 xfailed; Ruff and mypy show nothing new (mypy at its pre-existing 102) |

## Remaining identity problems (development stops here)

1. **Synonym-only names do not consolidate.** `7-hydroxystaurosporine` is an authority
   *synonym* of UCN-01, and authority consolidation merges on identifier names only
   (`authority_identity_merge_v1`). So 21 trials sit on `hydroxystaurosporine`, apart from
   `UCN-01`. Widening that rule is a separate, declared decision.
2. **A code's leading zeros are a different string**, so `PF477736` and `PF-00477736` stay
   split. Treating them as one would be a new spelling equivalence.
3. **There is no authority record for a new code** (ACR-368), so it stays separate with an
   UNCERTAIN edge, as required.
4. **A placebo whose otherNames contain the seed** is still nominated at the adapter.
5. **Visible precision is still low (12.4%).** PubMed name-minting is untouched.

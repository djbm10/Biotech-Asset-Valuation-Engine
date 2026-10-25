# Intervention naming and identity after seeded retrieval (v1)

Status: **DECLARED**, 2026-10-25, before any code change. Development work. The examples are
the disclosed CHEK1 pilot and GUCY2C development data. The `chek1_clinical_any_v1` seal,
reference and official scores are unchanged.

## Diagnosis (saved live records `~/se_runs/ctgov_seeded_live`; authority probes)

| Case | What the records say | Why it fails |
|---|---|---|
| XL844 | both trials write `XL844` | Folding treats a hyphen as a space, so the seed alias `XL-844` becomes `xl 844`, not a substring of `xl844`. Nomination misses it. The authority also misses it: `resolve_drug("XL844")` returns None while `resolve_drug("XL 844")` returns DRUG:XL-844. The same holds for `IC83`, `MK8776`, `SCH900776` and `UCN01` |
| Enumerated composite | one COMBINATION_PRODUCT intervention named `Drug 1: LY3023414; Drug 2: Prexasertib` | One intervention string is nominated as one fictional identity |
| Slash / parenthetical pair | `IC83/LY2603618`; `UCN-01 (7-hydroxystaurosporine)`, `7-hydroxystaurosporine (UCN-01)` | The whole string resolves to nothing, though each part resolves |
| Cross-code | `MK-8776` with otherNames `SCH 900776`; `ACR-368` with otherNames `prexasertib` | Already handled by ingest. otherNames merge only when **both** names resolve to the same authority drug (MK-8776 ↔ SCH-900776 does). ACR-368 is unknown to the authority, so it stays a separate candidate with an UNCERTAIN edge. That is the required behaviour; it is measured, not changed |
| Seed-mention nomination | "Placebo" (described as matching plecanatide), linaclotide arm descriptors | For a seeded query the intervention's *description* counts as its own text, so a description that mentions the seed nominates the intervention |

## Changes (all general; none names a product)

- **N1. Development-code spelling (identity layer, drugs only).**
  - In `OntologyTargetAttribution.resolve_asset`, `resolve_drug` and `identifies_drug`, a
    name that fails to resolve gets one retry. That applies when the name is exactly a
    compact development code: 1–6 letters immediately followed by 2–8 digits, optionally one
    trailing letter. The retry inserts one separator between the letters and the digits.
  - The retry is accepted only if the separated form resolves (RESOLVED, unambiguous).
  - Never for targets. No other spelling axis changes, and no fuzzy or edit-distance
    equivalence is introduced.
- **N2. Development-code spelling (seeded nomination).** A seeded query's code-shaped
  aliases also match their compact/separated counterpart. The match stays word-bounded,
  and it applies to that query's vocabulary only.
- **N3. Composite intervention labels** are expanded for extraction only. The stored
  snapshot and custody keep the original record.
  - **Enumerated:** `Drug 1: A; Drug 2: B` (labels `Drug|Agent|Treatment` + number + colon,
    separated by `;`) becomes one constituent per label. Each constituent is an ordinary
    intervention (same type) and is nominated only on its own evidence, so a partner with
    no evidence of its own is not nominated. The trial attaches only to nominated
    constituents. The original string is kept on each constituent as an offered related
    name, and the registry records it as an UNCERTAIN edge.
  - **Pair:** `A/B` or `A (B)`, with exactly two non-empty parts and no further separator,
    becomes name `A` with `B` offered as a related name, as if `B` were in otherNames. The
    **existing** ingest classification then decides:
    - same authority drug → IDENTITY_ALIAS (merged, reversible);
    - two different authority drugs → COMBINATION_PARTNER (not merged);
    - otherwise → UNCERTAIN (not merged).

    The original string is kept as a related name too.
- **N4. Seeded nomination reads the intervention's name and otherNames only**, never its
  description. A placebo "matching X" and a descriptor whose free text mentions X are not
  nominated for X. Target-vocabulary queries are unchanged.

Unchanged:
- retrieval;
- target evidence (authority edges and construct targets);
- the otherNames corroboration rule;
- authority consolidation;
- qualification, gates, as-of filtering and the custody key.

## Acceptance criteria (frozen before implementation)

Unit tests (synthetic):

| | Criterion |
|---|---|
| I1 | Compact codes resolve to the same drug as their separated form. A compact string whose separated form is unknown or ambiguous stays None. Targets are unaffected. A seeded `XL-844` query nominates an intervention named `XL844`, and a different code (`XL845`) is not matched |
| I2 | `Drug 1: A; Drug 2: B` yields constituents A and B. No candidate name contains `Drug 1:`. A constituent with no evidence of its own is not nominated |
| I3 | `A/B` with both parts resolving to one drug → one asset with both names. With two different drugs → two different drugs, never merged, with a COMBINATION_PARTNER edge. With unresolved parts → no merge |
| I4 | A seeded query does not nominate a placebo or descriptor whose description (but not name or otherNames) mentions the seed; it still nominates an intervention whose otherNames contain the seed |
| I5 | Original source strings stay recoverable (snapshot unchanged; composite string kept as a related name/edge); NCT ids unchanged |

Development measurement: one bounded live CHEK1 run on `e72ad34`, acquired before any
code change (`~/se_runs/identity_dev_v1/live_e72ad34`), then replayed on **identical bytes**
with the new code. Scored with the pilot scorer against the CHEK1 reference, which is now a
**disclosed development example**. The pilot's official scores are not touched.

| | Criterion |
|---|---|
| D1 | Named recall (all and analyst-visible) does not fall |
| D2 | Scorer merge errors stay 0, and no engine merge joins names resolving to two different authority drugs |
| D3 | Scorer split errors do not rise. SCH 900776/MK-8776, prexasertib/LY2606368, rabusertib/LY2603618/IC83 and the UCN-01 spellings are each one candidate. ACR-368 may stay separate (no authority corroboration) |
| D4 | Reference trials attached to recovered assets do not fall. XL844's trials attach to an XL-844 candidate |
| D5 | Seeded-query nominations of placebo, device or descriptor interventions do not rise (counted from the saved live records and the replay) |
| D6 | No new target assertion except through an authority edge; no new ELIGIBLE without an authority-confirmed target |
| D7 | The sealed `chek1_clinical_any_v1` custody replays with the same recall and no new splits (old-universe determinism check) |
| Q | S&E suite, Ruff and mypy show no new failures |

**Declared costs.**
- N4 drops seeded nominations from description-only mentions.
- N3 names an `A/B` combination after `A`, and records `B` as a partner rather than
  nominating it from that string.
- Replay of the new code on the e72ad34 corpus may issue follow-up queries the corpus never
  sealed (new nominated names). Those fail as replay divergences, and they are reported.

After this measurement, development stops.

## Implementation clarifications (before measurement)

- **N4 also covers the title fallback.** A CT.gov record with no qualifying intervention
  falls back to its `briefTitle` as the candidate name. For a seeded query that fallback
  nominated trial titles ("Evaluate the Safety of Linaclotide in IBS-C Patients in China")
  on the seed's name appearing anywhere in the protocol. For seeded queries the fallback is
  off. Target-vocabulary queries keep it.
- **N3's original label is provenance, not text.** It is carried on each constituent under
  a separate key, which the alias reader records as a related name (an UNCERTAIN edge) and
  nomination never reads. Placing it in `otherNames` made a combination partner's own text
  "name" the seed, which the first implementation's test caught.

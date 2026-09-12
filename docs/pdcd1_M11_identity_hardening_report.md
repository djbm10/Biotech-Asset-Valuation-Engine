# M11 — Identity Graph Hardening

Offline rerun against the sealed B8 corpus. Nothing was reacquired: the same custody seal
`4101a28f595e3a455c686eef829041098438d6b720d0446c054f73f45a8bc46d` (13,608 records, 1,928
attempts, 0 orphans) was replayed, and every file hash it claims was recomputed and
verified before the baseline was frozen.

**Principle:** co-occurrence is not identity, `otherNames` is not identity, and lack of
contradictory authority is not identity. Identity requires positive evidence.

## Result against the acceptance criteria

| Criterion | B8 | M11 | Met |
|---|---|---|---|
| Discovery of confirmed PDCD1 assets | 40/40 (100%) | 40/40 (100%) | yes, unchanged |
| Identification | 35/40 (87.5%) | 35/40 (87.5%) | yes, ≥ 35 |
| Falsely asserted PDCD1 among confirmed negatives | 7/133 (5.26%) | **0/133 (0.00%)** | yes |
| PD-L1 traps falsely asserted | 2 (Atezolizumab, Durvalumab) | **0** | yes |
| Direct PDCD1 target confirmation | 26/40 (65%) | 25/40 (62.5%) | see below |
| Strict M8 (continuity only) | 81/224 (36.2%) | 81/224 (36.2%) | unchanged |
| Assets | 1,068 | 1,082 | +14 |
| UNRESOLVED / CONFLICTING | 44 / 0 | 46 / 0 | — |
| Residual interval | [71.4%, 87.5%] | [71.4%, 87.5%] | unchanged |

All seven false assertions are gone, and no legitimate identification was lost. Asset count
rose by 14, not by hundreds: the rule removed specific merges rather than splitting the
graph apart, which is the failure mode the differential audit exists to detect.

## The one lost confirmation is itself a contamination artifact

Direct confirmation fell 26 → 25. The lost subject is `cand_148207468a222a051ffd`,
**JS207 (PD-1/VEGF bispecific antibody)**. B8 did not confirm it through JS207 at all:

- B8's own `JS207` asset was `UNRESOLVED` for PDCD1, in B8 and in M11 alike — JS207 is a
  novel bispecific absent from ChEMBL_37 and Open Targets 26.06.
- The confirmation came from the asset `WJB001 Capsules+JS207/JS001`, a combination-regimen
  string whose aliases had absorbed **Toripalimab** from `otherNames`. The
  `CONFIRMED_TARGET` on that asset is Toripalimab's, not JS207's.

So B8's 26th confirmation was right by accident, produced by the same defect that produced
the seven wrong ones. Removing it lowers the number and raises the truthfulness of it. The
honest reading of B8 is 25/40, not 26/40, and M11 does not lose measured ability.

## Differential merge audit

`B8_M11_differential_merge_audit.json`, both directions, over 1,096 edges.

| Category | Count |
|---|---|
| MERGE_RETAINED_WITH_CHANGED_EVIDENCE | 752 |
| RELATIONSHIP_DOWNGRADED_TO_UNCERTAIN | 328 |
| MERGE_REMOVED | 16 |
| MERGE_ADDED | 0 |
| PRODUCT_COMPONENT_CREATED | 0 |

Relationships: B8 `{IDENTITY_ALIAS: 1096}` → M11 `{IDENTITY_ALIAS: 752,
UNCERTAIN_RELATIONSHIP: 328, COMBINATION_PARTNER: 16}`. Every retained merge is reported as
changed-evidence because its basis is now a stated reason ("both names resolve to the same
canonical drug DRUG:X") rather than "merged unconditionally". 752 of 1,096 edges are
corroborated true synonyms, which is why identification held.

Each changed edge keeps its originating `otherNames` field, trial, hit and document
alongside the new disposition, so a removed merge is explainable rather than absent. The 16
removals include the whole B8 contamination cluster: `Hiltonol` ← Nivolumab, Pembrolizumab,
Atezolizumab, Cemiplimab, Durvalumab (all NCT02423863), plus `ADG116` ← Pembrolizumab,
`ISA101b` ← Cemiplimab, `Toripalimab` ← Cetuximab.

## Two weaknesses in the new model, stated rather than hidden

1. **`COMBINATION_PARTNER` is used for some pairs that are not combinations.** `Dato-DXd` ←
   `Datopotamab` and `T-DM1` ← `Trastuzumab` resolve to different canonical drugs, which is
   defensible — a naked antibody and its ADC are different molecules — but calling them
   combination partners misdescribes the relationship. They are conjugate/parent pairs. The
   identity decision is right (the canonical ids must stay distinct); the label is not.
   No category in the current five covers it.
2. **Real development codes are now held as uncertain.** `Pembrolizumab` ← `SCH900475` and
   `Ipilimumab` ← `NSC 732442` are genuine synonyms, downgraded because no authority maps
   the code. This costs nothing measurable here only because the primary name already
   resolves. Where the *primary* is the unresolved one — `SDREGN2810` ← `cemiplimab`,
   `Single agent, adjuvant anti-PD1 therapy` ← `Pembrolizumab` — the asset stays
   unidentified. This is the deliberate conservative direction, and it is the reason the
   B8 identification misses remain open rather than being fixed by this change.

## Still open (improvement targets, not delivered)

Recorded as strict `xfail` in `tests/se/test_identity_evidence_model.py` so they cannot be
quietly claimed: SMT112/AK112, Budigalimab/ABBV-181, and subcutaneous
pembrolizumab/berahyaluronidase. Each needs an authority this run does not have — a
development-code mapping or a product registration. Merging them on the evidence available
would mean merging unresolved strings, which is exactly what the regression guards forbid.
`PRODUCT_COMPONENT_CREATED` is 0 for the same reason: the category is implemented and
tested, but no co-formulated pair in this corpus has both components resolvable.

## Provenance

- Baseline: `B8_IDENTITY_GRAPH_BASELINE_V1`, artifact `1a3ff5ba…`, exact six-dimensional
  parity with B8 (asset count, asset ids, alias/name sets, member hit ids, trial ids,
  target assertions, merge-group membership), edge graph `b5f34680…`, code `13b5f42`.
- Hardened run: code `038af1f`, result `B8_m11_result.json`, score `B8_M11_score.json`.
- Sources unchanged from B8: clinicaltrials_gov SUCCESS, pubmed PARTIAL, 7 NOT_CONFIGURED;
  run status INCOMPLETE with no fatal reasons. The 7 unconfigured families remain M12.

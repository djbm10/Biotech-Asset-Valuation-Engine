# M13 — the zero-shot generalization result

**Target: `SLC6A2` (norepinephrine transporter). Drawn mechanically, never touched by the engine
before the run. Discovery 5/41. Identification 0/41.**

M13 asked whether the system is a generalized biotech discovery engine or a PDCD1-specific one.
The answer, on this evidence, is that it is not yet generalized — and the reason is specific,
mechanical, and fixable rather than diffuse.

## How the target was chosen, and why that matters

The selection had to be made by a procedure, not by me: I have seen how the engine behaves on
PDCD1, so any target I named would have been shaded by that and the zero-shot property would
have been gone before the first query.

Thresholds were declared in `m13_pool_rules.json` **before** the pool was computed. The funnel,
run once:

| Stage | Remaining |
|---|---|
| Targets with a USABLE `DIRECT_TARGET` edge in the frozen ontology | 888 |
| ≥40 distinct drugs (proxy for the rule-4 floor of 25 clinical-stage assets) | 17 |
| Monoclonal-antibody fraction <0.30 (rule 2: a different modality class) | 17 |
| Not in the PDCD1 checkpoint pathway (rule 1) | 17 |
| No prior contact anywhere in the repo or staging (rule 6) | **12** |

`EGFR`, `ERBB2`, `FLT3`, `AR` and `MET` were discarded on prior contact. The draw was seeded by
the SHA-256 of the frozen pool file itself, so the seed is a function of the pool and cannot be
shopped for after the pool is known; anyone can recompute it. It returned `SLC6A2`.

Rules 2 and 3 were satisfied as a *consequence* of the mechanical filters, not by choice: the
surviving pool was entirely non-oncology small-molecule receptors and transporters.

The benchmark was then built by rules that never name the target — gold is every parent molecule
with a direct-target edge; traps are molecules binding a sibling in the same `SLC6A` family but
not the target; negatives are everything else — and frozen **before** the run. 48 gold molecules,
41 of them registry-reachable (rule 4 floor: 25), 21 traps, 3134 negatives.

## The result

| Metric | PDCD1 (M12) | SLC6A2 (M13, zero-shot) |
|---|---|---|
| Discovery | 40/40 | **5/41** |
| Identification | 35/40 | **0/41** |
| Assets asserting the target | 4 new | **0** |
| Traps falsely asserted | 0/133 | 0/21 |
| Candidates produced | 1623 | 72 |

**The zero false positives are vacuous and must not be read as a precision success.** The run
asserted the target for zero assets, so there was nothing to be wrong about. A metric that can
be passed by asserting nothing has not been tested.

## Why — three generic defects, none target-specific

### D1 — the problem contract cannot express a curated target vocabulary *(generic architecture defect)*

The frozen ontology offers SLC6A2 seventeen aliases. Four of them — `NET`, `NET1`, `NAT1`,
`SLC6A5` — belong to entirely different genes. A generic ambiguity rule (admit an alias only if
no other canonical target claims it) refused all four, and the problem YAML declared only the
seven clean ones.

**Every issued query contained all four refused aliases anyway.** The query compiler re-expands
target aliases from the ontology and discards the problem-level list. `NET` matches 3079 CT.gov
trials, nearly all *Neutrophil Extracellular Traps*, and 67 of the 72 candidates the run produced
are NETosis trials. The benchmark excluded that vocabulary; the engine used it regardless.

This was invisible on PDCD1 because its ambiguous alias (`PD-1`, also a legacy alias of RPL17)
was already handled upstream in the resolver, so the gap in the contract never showed.

### D2 — discovery has no drug-to-target reverse seeding *(missing generic source capability)*

This is the largest contributor, and the most interesting finding in the milestone.

| Query | CT.gov trials |
|---|---|
| `PD-1` | 5827 |
| `PDCD1` | 521 |
| `norepinephrine transporter` | 62 |
| `SLC6A2` | 37 |
| `atomoxetine` (one single gold asset) | 223 |
| `atomoxetine` **and** `SLC6A2` | **3** |

Atomoxetine has 223 trials and three of them name the target. The engine only ever searches
*target* vocabulary, so an asset whose trials do not name the target is structurally unreachable
no matter how good the rest of the pipeline is.

The frozen ontology already holds USABLE `DIRECT_TARGET` edges for 96 SLC6A2 drugs — the very
edges this benchmark's gold set was built from — and discovery never turns them into drug-name
queries.

The buried assumption is: **the target is named in the documents describing its assets.** That is
true for immuno-oncology and false for a CNS transporter. No amount of work on M8–M12 could have
surfaced it, because PDCD1 satisfies it.

### D3 — target vocabulary is ANDed with a biologics-shaped modality vocabulary *(generic architecture defect)*

All 17 modality-conjunct queries returned zero records. The modality expansions are `antibody`,
`CAR T`, `kinase inhibitor`, `ADC` and similar; CT.gov records for CNS small molecules describe
drug and indication, not molecular class, so the conjunct cannot match.

### D4 — pre-registry agents *(genuine benchmark miss)*

7 of 48 gold molecules (bretylium, guanethidine, debrisoquin) predate the trial registry. Real
binders, genuinely absent from CT.gov. Excluded from the primary denominator by construction and
reported rather than scored — scoring them would measure the registry.

### D5 — 5 reachable, 0 identified *(unsupported evidence)*

Five gold assets occur in admitted corpus text but none surfaces as a named asset. Their host
documents are D1's NETosis trials, where the gold drug is incidental prose rather than an
intervention. **This is not evidence that identification is broken** — it is evidence that the
question cannot be answered from this run. It is blocked behind D1 and D2.

## What M13 does and does not license anyone to say

**Supported:** the discovery layer encodes a PDCD1-shaped assumption and fails without it. The
headline M8–M12 numbers are not, on this evidence, transferable to an arbitrary target.

**Not supported:** any claim about the identity model, the custody machinery, or the M11
evidence contract. The run never reached them in earnest — with 72 mostly-irrelevant candidates
and zero target assertions, the identity layer had nothing to do. M13 is silent on the part of
the system M11 and M12 were about.

## No fixes were applied before reporting

D1–D3 are all fixable, and fixing them would produce a better number. It would not produce a
*zero-shot* number. The first run against an untouched target is the measurement; remediation
belongs to a separate, named milestone and must never be substituted for this result.

For the record, what was not done: no hand-mapped assets, no target-specific synonyms, no
target-specific code changes (`git status` on `src/` is clean, and the engine was pointed at a
new target purely through the problem YAML), no denominator changed after seeing results, and no
redraw.

## Suggested M14 scope

1. Honour the problem's declared alias list in the query compiler, or state explicitly that
   ontology expansion overrides it (D1).
2. Seed discovery from drug→target edges as well as target vocabulary (D2) — the data is already
   in the frozen snapshot.
3. Make the modality conjunct a boost rather than a filter (D3).
4. Re-run **this frozen benchmark** unchanged, and report both numbers. The zero-shot 5/41 stands
   permanently as the zero-shot result.
5. Then draw a second target from the same frozen 12-target pool, which still contains 11
   untouched candidates.

## Provenance

`M13_seal_v1.json` (16 artifacts) in `/home/djmann/staging/pdcd1_baseline/`; selection chain
`m13_pool_rules.json` → `m13_candidate_pool.json` → `m13_selection.json`, all committed under
`docs/provenance/`. Classification: `M13_defect_classification_v1.json`.

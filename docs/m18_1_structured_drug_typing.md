# M18.1 — structured source typing as a protected nomination route

**Status: implemented and measured.** Closes the known gap named in §5 of
`docs/m18_mention_precision_report.md`. Frozen benchmark results are unchanged and were not
rescored.

## 1. What shipped

A source that types an intervention `DRUG` in a structured field of its own schema has
stated that the string names a drug. That is evidence about the *name*, from outside the
corpus, and it does not get stronger by repetition — so one document is enough. It is now a
third protected route alongside an exact ontology match and development-code shape.

| where | change |
|---|---|
| `CanonicalAsset.structurally_typed_drug` | new flag, default `False` |
| `AssetRegistry.ingest_hit` | sets it from `CandidateHit.intervention_type` |
| `_STRUCTURED_DRUG_TYPES` | `{"DRUG"}` — exactly that, nothing else |
| `mention_support.is_protected` / `classify_mention_support` | accept `structurally_typed_drug` |
| `pipeline.py` nomination boundary | passes `asset.structurally_typed_drug` |

The flag is **monotonic**: a later untyped observation of the same asset is weaker evidence,
not a retraction, so it is OR-ed on update and OR-ed across a merge.

### What it deliberately does not do

It buys the default path and nothing else. It mints no alias — `otherNames` remains an
identity *claim* that must still clear corroboration. It asserts no target. It does not
bypass identity resolution, and a typed and an untyped observation of the same name are
still one asset. It is never inferred from prose: a sentence calling something a drug is an
extraction judgement, and extraction is the thing this module exists to be sceptical of.

`COMBINATION_PRODUCT` is excluded on purpose — it is the type sponsors also give single
agents, which is why `_COFORMULATED_TYPES` already treats it as weak. `BIOLOGICAL` is
excluded because it names a class of product rather than a molecule.

## 2. Measurement

The frozen result artifacts predate the flag, so it was re-derived from the sealed CT.gov
snapshots each run actually read (`m181_typed_drug_eval.py`, read-only, nothing re-queried).

| | M17 (CHRM1) | M16R (HTR2A) |
|---|---|---|
| typed-`DRUG` names in corpus | 275 | 75 |
| candidates | 8,080 | 4,665 |
| default path before | 4,603 | 3,090 |
| default path after | **4,639** | **3,096** |
| promoted from low support | **36** | **6** |
| demoted | **0** (structural) | **0** (structural) |
| gold affected | 0 | 0 |
| traps affected | 0 | 0 |

Demotion is structurally impossible: typing adds a protected route and removes none, so no
candidate can leave the default path because of this change. Every M18 acceptance criterion
therefore holds by construction rather than by measurement — discovery and identification
cannot fall, and a routing decision downstream of identity and attribution cannot create an
assertion.

### What the promoted names actually are

Honest reading of the 36: they are mostly **decorated forms of known molecules and
non-assets**, not novel single-trial assets — `Gemcitabine Hydrochloride`,
`Ketamine Hydrochloride`, `Cisplatin, Gemzar, Docetaxel, Alimta`, `FOLFOX regimen`,
`Pembrolizumab plus Lenvatinib`, `Chemotherapy`, and six placebo arms
(`Single Dose Placebo`, `SHAM injection`, …).

Two things follow, and neither is fixed here:

- The salt/regimen/combination decoration defect already on the open list is what produces
  most of this population. Structured typing is faithful to the source; the source types the
  arm, not the molecule.
- Sponsors type placebo arms `DRUG`. Six placebos on the default path is a small analyst
  cost, visible rather than hidden, and filtering them is a separate generic change.

The measurement cannot show the thing the feature was built for — a genuinely novel,
plainly-named, single-trial asset — because no benchmark drawn so far contains one. That is
the same blind spot M18 named: gold is cut from ontology `DIRECT_TARGET` edges, so it is
ontology-known by construction and was already protected. The case for this route is that
the evidence is structured and from outside the corpus, not that it moved a benchmark number.

## 3. Tests

8 new tests in `tests/se/test_structured_drug_typing.py`, red before implementation, kept
separate from the gating fixture so a future fixture edit cannot hide the routing behaviour:

- a single-document plain-language intervention typed `DRUG` stays on the default path
- the same string with no structured typing stays `LOW_SUPPORT_UNKNOWN`
- typed `DRUG` mints no identity alias
- typed `DRUG` asserts no target
- typed `DRUG` still goes through identity resolution, and the flag survives a later
  untyped observation
- existing M18 routing is unchanged, and typing can only promote, never demote

`tests/se`: **747 passed, 2 xfailed**. `ruff check src/bve/se/` clean. The `Asset A` gating
fixture was not revisited; it did not need to be.

An incidental observation, unrelated and unchanged: when an intervention's `otherNames`
contains an ontology-known drug, that name replaces the primary name as the candidate. It is
pre-existing extraction behaviour, noted here only because it shaped a test fixture.

## 4. Status

Mention-precision remediation is **frozen** here. Next work is user-facing productization.

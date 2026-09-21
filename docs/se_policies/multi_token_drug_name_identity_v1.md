# Preregistration — a two-word drug name is one asset (v1)

Written and committed **before** the artifact is built, before the code changes, and before any
measurement, 2026-09-21.

Baseline: run `aacr_safety` / `aacr_design` on the sealed AACR corpus.
Extractor: `src/bve/se/discovery/adapters.py::extract_observed_asset_names`.

---

## 1. The defect

`drug_name_lexicon.drug_name_pattern()` matches **one token at a time**. A two-word
International Nonproprietary Name therefore cannot survive it: *belantamab mafodotin* is read as
`belantamab` and `mafodotin`, and the engine mints **two assets out of one drug**.

On the live shortlist this is not a rare edge. Five of the ten displayed entries are halves of
ADC names — `belantamab`, `mafodotin`, `vedotin`, `ozogamicin`, `tesirine` — plus `Vicleucel`, the
tail of a cell-therapy name. The defect contaminates identity, the evidence counts that hang off
identity, and the shortlist a reader actually sees, all at once.

## 2. The rule

**Longest match against the ontology, per occurrence.**

When two candidate mentions occur adjacent in the text, separated by a single space, and their
joined string is a name the frozen ontology holds as a single `DRUG`, the pair is emitted as one
mention and neither fragment is emitted **for that occurrence**.

Three properties follow from the design rather than from a curated list, and they are the four
constraints this milestone was given:

- **Authority-gated.** The pair must be a name the ontology already knows. Two genuinely separate
  drugs that happen to sit next to each other are not a record in ChEMBL/Open Targets, so they
  cannot merge. *"rituximab cyclophosphamide"* is not a drug and will not merge.
- **Per occurrence, never per token.** This is the rule `study_identifier.frames_a_study` already
  establishes in this same function. `vedotin` is suppressed *where it is the tail of
  polatuzumab vedotin*, and remains a mention anywhere it stands alone. No token is globally
  banned.
- **Scoped to the defect.** Only strings the extractor would otherwise have emitted as two
  fragments can merge. Salt and formulation forms — *gonadorelin acetate*, *X hydrochloride* —
  are untouched, because `acetate` and `hydrochloride` are not candidate mentions to begin with.
  The rule cannot reach anything that was not already broken.

Not a hand-written list of payload suffixes. `drug_name_lexicon` exists precisely because a list
chosen after seeing which names a benchmark missed is "hand-mapping wearing a lexicon's clothes",
and that reasoning applies here unchanged.

### The artifact

A new frozen lexicon `multi_token_drug_names_v1.json`, derived mechanically from the same
ontology snapshot as its siblings and carrying the same provenance fields (`records_sha256`,
`derived_from`, `generated_at`, `selection`). Selection, declared now: `DRUG` labels and aliases
that are exactly **two alphabetic tokens**, each of length ≥ 5, lowercased. No filtering by
suffix, class, or anything observed in a run.

## 3. Controls

Verified against the ontology **before** the rule was written: all twelve of
*belantamab mafodotin*, *loncastuximab tesirine*, *inotuzumab ozogamicin*,
*idecabtagene vicleucel*, *brentuximab vedotin*, *polatuzumab vedotin*,
*trastuzumab deruxtecan*, *sacituzumab govitecan*, *ciltacabtagene autoleucel*,
*tisagenlecleucel*, *axicabtagene ciloleucel* and *gemtuzumab ozogamicin* are present as single
`DRUG` records.

Also verified, and the reason a simpler rule will not work: `mafodotin`, `vedotin`, `ozogamicin`,
`belantamab` and `loncastuximab` are **each independently present as standalone ontology
records**. "Is this token a known drug?" therefore cannot detect fragmentation; only "is the
*pair* a known drug?" can.

| id | text | must yield |
|---|---|---|
| adc-pair | *"Patients received belantamab mafodotin."* | one mention `belantamab mafodotin`; neither fragment |
| adc-pair-2 | *"…loncastuximab tesirine…"* | one mention; neither fragment |
| adc-pair-3 | *"…inotuzumab ozogamicin…"* | one mention; neither fragment |
| cell-therapy | *"…idecabtagene vicleucel…"* | one mention; `Vicleucel` does not survive alone |
| payload-alone | *"The vedotin payload was released intracellularly."* | `vedotin` **still a mention** — no global ban |
| separate-drugs | *"Patients received rituximab cyclophosphamide vincristine."* | three mentions, unmerged |
| single-token | *"…blinatumomab…"* | unchanged, one mention |
| salt-form | *"…gonadorelin acetate…"* | unchanged; the rule does not reach it |

## 4. Predicted outcome

Replay of the sealed corpus, same argv, new output directory.

The acceptance bar is **identity correctness, not a preserved headline count.** If two fragments
each carried evidence and collapse into one real asset, `human_poc` may *fall* while the science
improves. A drop is not a regression here; losing a legitimate standalone asset is.

Adoption bar, fixed now:

1. `belantamab mafodotin`, `loncastuximab tesirine`, `inotuzumab ozogamicin` and
   `idecabtagene vicleucel` each appear as **one** asset where their fragments appeared before.
2. Those fragments cease to exist as independent assets **unless independently supported
   elsewhere in the corpus**, which must be checked per fragment rather than assumed.
3. **No legitimate standalone asset is lost.** Every asset present in `aacr_design` and absent
   afterwards is enumerated and read individually, not counted.
4. Evidence transfers only to the surviving canonical asset; no fact is duplicated across a
   fragment and its parent.
5. `human_poc`, `target.expression`, `identity.distinct_asset` and the top-10 shortlist are all
   **reported with reasons**, not required to hold a particular value.

Anything unexplained — an asset lost that nobody can account for, or a merge the ontology does
not back — is a failure and is reported as one.

## 5. Not to be done

Banning any token globally; hand-listing payload suffixes; merging on adjacency alone without the
ontology gate; touching sentence-scoped attribution; touching the ordinary-word minting problem,
which is the *next* milestone and is deliberately measured only after this noise is gone;
reordering the shortlist.

---

## 6. Amendments made before any measurement

Both were forced by preregistered controls failing during implementation, and both are recorded
here rather than applied silently. No replay had been run at this point.

### 6a. One half being a mention is enough to look (a widening)

§2 declared that only spans the extractor already emitted could join. The **cell-therapy control
failed under that rule**: `idecabtagene vicleucel` yielded only `vicleucel`. `idecabtagene` is
nominated by *no* route — no stem, unknown to the ontology as a single token, below the shape
threshold — so the pair could never form, and this is exactly why `Vicleucel` was reaching the
live shortlist as a fragment. Requiring both halves would have left every `-cabtagene` cell
therapy fragmented, which is the opposite of what this milestone is for.

Amended: **one** half must already be a mention; the ontology still decides the pair. This is a
widening, and widening after seeing a failure is the shape of benchmark-fitting, so it is stated
plainly: the authority gate is untouched, the per-occurrence rule is untouched, and the
alternative was failing a control the milestone was commissioned to satisfy.

### 6b. The anchoring half must itself be plausible (a narrowing, forced by 6a)

The widening promptly broke the **salt-form control**: `gonadorelin acetate` became a mention
where nothing had been one. `gonadorelin` is refused by `_plausible_asset_name` because it is in
the prose-word set — it is a TARGET label — but the joined string is in no prose list, so the
pair re-entered through a door the filter had deliberately shut.

Amended: the anchoring span must satisfy `_plausible_asset_name` before a join is attempted. A
rejected token does not get a second chance under a longer name.

**This is the same lesson as the veto-narrowing milestone**, from the other direction: a guard
also refuses things for reasons nobody enumerated, and a change that routes around the guard
inherits all of them at once. Both amendments were caught by controls declared in advance.

With both in place, all eight controls in §3 behave exactly as §3 declares.

# BD_SEARCH_EVALUATION_DEMO v1 — assessment

**Development demonstration only.** It is built from frozen non-holdout runs (as of 2026-09-24).
H21–H25 stay sealed and H6–H10 unrun. There is no engine, gate or label change, and no score.

## What was built

`bve-se-bd-brief` (`src/bve/se/reporting/bd_brief.py`, `src/bve/cli/se_bd_brief.py`) reads an
existing run directory and writes `brief.html`, `brief.md` and `checks.json`. Usage is in
`docs/se_bd_brief_usage.md`. It reuses the shortlist's evidence projection and the gate
evaluations already in the run; it does not search again.

| Demo | Run | Question |
|---|---|---|
| [`cd19_cell_therapy_bcl/brief.html`](cd19_cell_therapy_bcl/brief.html) | `tac01_protoid_v1` | CD19 cell therapy, B-cell lymphoma, Phase 1+ |
| [`cd19_bcma_dual_autoimmune/brief.html`](cd19_bcma_dual_autoimmune/brief.html) | `mint5_protoid_v1` | CD19 **and** BCMA, autoimmune disease, Phase 1+, human PoC |

Both regenerate byte-identically. Input SHA-256 hashes are printed at the foot of each brief.

## Usefulness evaluation (development only)

**1. Mechanical checks.** `checks.json` passes 7/7 for both demos. These checks confirm only
that the structure is present: a question is stated, candidates are named, sources are linked,
every fact carries a status, reasons are given, questions exist, and nothing is marked
SUPPORTED without a value.

**2. Independent cold read.** A separate agent read only `brief.md`, acting as a BD analyst. It
judged the first draft; the issues marked *fixed* were corrected afterwards in presentation
only.

| Question | CD19 / BCL | CD19+BCMA / autoimmune |
|---|---|---|
| Understand the strategic question | YES | YES |
| Identify actual candidates | PARTLY | PARTLY |
| Open supporting sources | PARTLY (authority records have no link) | PARTLY |
| Confirmed vs unverified | PARTLY → gate/label disagreements now flagged (*fixed*) | NO → "Meets" now labelled as relying on unverified PoC, and disagreements are flagged (*fixed*) |
| Why included/excluded | PARTLY | PARTLY |
| Most important follow-up | PARTLY (templated) | PARTLY |
| Avoids unsupported conclusions | PARTLY | PARTLY |

Fixed after the review, all in presentation:
- an executive summary;
- per-card **engine disagreement** flags;
- human-PoC listed as enforced when the problem required it;
- ClinicalTrials.gov field headers stripped from displayed names;
- clearer hold-back wording;
- questions about indication match and approved/partnered status.

Not fixed, because these are engine findings and outside this milestone:

**CD19 / BCL demo**
- 4 of the top 5 are **approved, big-pharma-owned products** (Tecartus, Breyanzi, Kymriah,
  Yescarta). They appear at Phase 2/3 because approval is not represented.
- **axi-cel's target is Unknown** even though ChEMBL names it, because the alias is not
  attributed.
- **Wrong-indication efficacy quotes**: brexu-cel's second quote is B-ALL, and CNCT19's quotes
  are B-ALL.
- **AUTO3's discovery hint is "MONOCLONAL_ANTIBODY"**, which is wrong; AUTO3 is a CAR-T. The
  hint is displayed only as a hint.
- **Every card disagrees with at least one gate.** The modality gate is UNKNOWN for all 10, even
  where the authority class is CELL_THERAPY.

**CD19+BCMA / autoimmune demo**
- **ICG318 passes every gate**, yet its target and modality are unconfirmed and its PoC rests
  on one prose abstract.
- **0 of 10 have an authority-confirmed target.**
- **7 of 10 are unnamed investigator-initiated constructs.**
- **AZD0120's "Phase 3" is probably a myeloma trial.**
- **No T-cell engagers appear.**

The independent reviewer's verdict on the five-minute test was **PARTLY**. A BD reader gets the
question and a rough list of names, but not a trustworthy shortlist. The reviewer's
candidate-fit judgements were from memory and were not verified.

## What works

- **Gap framing.** Requirements are split into what the engine enforced and what it could not
  enforce: format, manufacturing, rights, effect bar.
- **One row per candidate,** with clickable ClinicalTrials.gov and PubMed sources for stage,
  sponsors and efficacy passages.
- **Honest status labels.** Search-context targets and modality hints are never shown as
  supported. Prose efficacy is quoted and marked unverified. When the engine disagrees with
  itself, the brief says so instead of picking one side.
- **Diligence questions follow the actual gaps,** in Harvey's order: target, then
  format/engagement, then clinical readout, then safety/dosing. Cell therapies also get
  manufacturing/scale-up and rights questions.
- **Deterministic and cheap.** About 2 s per brief from an existing run, with no network.

## What remains scientifically unreliable

- **Target attribution:** 7/10 (TAC01) and 10/10 (MINT5) shown targets are unknown; alias and
  identity work is parked.
- **Human-PoC** has no validated route. The MINT5 gate passes on prose.
- **Approval status, ownership and rights** are not modelled. Sponsors are not owners.
- **Candidate identity:** trade names and INNs are not consolidated, and descriptive
  intervention text still becomes "assets".
- **Indication of evidence:** quotes and stage can come from a different disease than the one
  requested.
- **Coverage:** company, press-release, ASCO/ASH/EHA and SEC sources were never searched.

## Single largest obstacle

**The engine cannot tell an external, partnerable development asset from an approved or
big-pharma-owned product, or from an unnamed academic construct.** Both demos' top 10 are
dominated by one of those two groups. The underlying causes are three missing pieces: an
approval/ownership layer, product-level identity consolidation, and target attribution for
named constructs.

The highest-impact next step for BD usefulness is a **structured approval-and-ownership fact**
for each candidate, such as FDA/EMA approval status and sponsor/licensee from a public
structured source. It would need its own preregistration. With it, the brief could separate
"already marketed" and "academic" candidates from genuine external opportunities.

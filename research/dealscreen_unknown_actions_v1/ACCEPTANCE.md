# Cycle U1: a concrete next action for every tool UNKNOWN (acceptance criteria, frozen before code)

INTERNAL DEVELOPMENT. AI-simulated measurement only; no human validation is claimed.

Revised 2026-10-30, before any U1 code: the modality class `SOURCE_MODALITY_NOT_ALLOWED` is dropped (a readable
modality outside the allowed set FAILs the gate, so it never reaches UNKNOWN); `READS_AS_REQUESTED` and target
`CONFLICTING` are added; site words and the order of checks are defined exactly. The baseline counts were
re-measured on R1 revision 3 (science unchanged).

## Problem (reproduced, comparison cycle C1)

The C1 critic found that analysts anchor on the tool's UNKNOWN decisions (`research/dealscreen_comparison_v1/CRITIC_FINAL.md`, section 2).
- On all 7 reference-IN programs that the DealScreen analyst left unresolved, the tool was also UNRESOLVED or EXCLUDED.
- The analyst's 7 reasons were one templated string, "gastric not stated".
- RC118 is a real recall miss: the supplied evidence names gastric cancer.
- General Claude, with no tool, resolved all 7.
- Separately, "noise" rows not directed at the target sit high in the UNRESOLVED queue: rilvegostomig is rank 2, because the source text "PD-1; TIGIT" cannot be read.

Measured at R1 revision 3, on the CLDN18.2 landscape:
- 38 UNKNOWN decisions on non-excluded programs: indication 24, modality 8, target 4, phase 2.
- Every one carries one of 4 generic next actions: "Obtain specific, authority-comparable indication evidence.", "Research fact type 'modality_id'.", "Resolve the asset's construct-level target set." and "Research fact type 'development_stage_order'."
- 0 of 38 say what the record contains, how it relates to the requirement, or which fact would decide the gate.

The generic text comes from the S&E gate evaluator (`src/bve/se/gates/evaluator.py`). That code is S&E-governed and is not changed here.

## What changes

DealScreen adds a diagnostic to each UNKNOWN decision. It does not change the gate.
- **Class:** one value from a closed list. It describes the relation between what the record says and the buyer's requirement.
- **Observed:** the source values as written, or "nothing on record".
- **Action:** the one cited fact that would decide the gate, and how to enter it (`assert` with a URL and a verbatim quote, or reject the claim).

Actions describe the evidence. They never say a program is in or out of scope, and they never change ranks. A vendor cell can be wrong: in C1, IBI343, a top reference candidate, carries the modality cell "Imaging agent".

### Classes

**Indication.** The requested concepts are the buyer's `strategic_gap.indications`. Relations come only from the frozen NCIt authority and from the requested concepts' own names (label and synonyms in the authority).
- `READS_AS_REQUESTED`: the name resolves to exactly one concept that is a requested concept or a subtype of one, but only after a disclosed clean-up the gate does not apply (an inner acronym such as "(GEJ)" removed, or a leading extent qualifier such as "advanced" removed). The action shows the clean-up.
- `BROADER_THAN_REQUESTED`: an observed name resolves, directly or by a disclosed DealScreen reading, to an ancestor of a requested concept.
- `AMBIGUOUS_NAME_ALL_BROADER`: the name matches several authority concepts, and every one is an ancestor of a requested concept.
- `AMBIGUOUS_NAME`: the name matches several concepts, but not all of them are broader.
- `NAMES_REQUESTED_SITE`: the name is not read as a requested concept, but contains a site word. Site words are words of the requested concept's own names that also occur in the names of its ancestors under an NCIt "... by Site" concept, minus words that occur in its other ancestors (histology, generic tumour words) and minus extent qualifiers. For "gastric adenocarcinoma" that leaves "gastric" (and its synonyms' site words), never "adenocarcinoma". A site word that appears only after an exclusion word ("other than", "excluding", "non-", "except") does not count.
- `BASKET`: once extent qualifiers, population words and generic tumour words are removed, nothing is left. Examples: "Advanced Solid Tumors", "Solid Tumor, Adult", "Neoplasms".
- `DIFFERENT_DISEASE`: the name resolves to a concept that is neither an ancestor nor a descendant of a requested concept, and has no site word.
- `UNREADABLE`: none of the above.
- `NO_RECORD`: the record has no indication.

Order of checks for one name: `BASKET` first (a basket name can resolve to an unrelated NCIt concept, e.g. "Advanced Solid Tumor"), then the authority lookup, then site words. When a record has several names, the program's class is the first present in this order: `READS_AS_REQUESTED`, `NAMES_REQUESTED_SITE`, `AMBIGUOUS_NAME`, `AMBIGUOUS_NAME_ALL_BROADER`, `BROADER_THAN_REQUESTED`, `BASKET`, `DIFFERENT_DISEASE`, `UNREADABLE`, `NO_RECORD`. Every name's own class is shown too.

**Target.** The required targets are the buyer's `target_expression` canonical ids and labels.
- `SOURCE_NAMES_REQUIRED_TARGET`: the target text contains a required symbol or label, but no target set was built from it (pair notation, isoform, unreadable partner).
- `SOURCE_NAMES_OTHER_TARGETS`: the text names targets, and none is a required target by symbol or label.
- `CONFLICTING`: several target values disagree (the values are shown).
- `NO_RECORD`.

**Modality.** The allowed modalities are the buyer's `modalities`.
- `SOURCE_MODALITY_UNREADABLE`: the text names no modality the authority can type (for example "Imaging agent" or "Protein").
- `COMBINATION_PRODUCT`: one modality is stated for several components.
- `CONFLICTING`: several values.
- `NO_RECORD`.

**Phase.**
- `NO_RECORD`.
- `CONFLICTING`: the values are shown.
- `UNREADABLE`: the text is shown.

**Any other gate:** `OTHER`. The observed values are shown, with the generic action kept.

## Acceptance criteria

| AC | Criterion | Measure |
|---|---|---|
| U1-1 | Every UNKNOWN decision on a non-excluded program carries a DealScreen diagnostic (class, observed values, action). The action names the observed value or "nothing on record", and the fact that decides the gate. | CLDN18.2: 38 of 38, baseline 0. FcRn v1/v2 and the synthetic landscape: 100% |
| U1-2 | Classes are derived only from the authorities (NCIt, target, modality) and the buyer's own requirement. No program, company, disease or target word from any test landscape appears in `src/` logic. | grep, code review |
| U1-3 | No gate status, disposition, scientific rank, machine recommendation or transaction field changes. | `compare`: 0 changed on CLDN18.2 and on the 4 equivalence workspaces; equivalence byte-identical |
| U1-4 | Held-back unit tests cover every class with fictional or other-therapy-area strings. They include adversarial cases: a different site sharing a histology word ("pancreatic adenocarcinoma" for a gastric-adenocarcinoma request) → `DIFFERENT_DISEASE`; a requested site only after an exclusion ("solid tumors other than gastric") → not `NAMES_REQUESTED_SITE`; a requested concept's subtype is never `BROADER`; an ambiguous name with a non-broader reading → `AMBIGUOUS_NAME`. | tests |
| U1-5 | Surfaces: the Diligence sheet "Next action" shows the DealScreen action, with the S&E rationale kept beside it. The Screening sheet shows the class per open gate. The memo's "Investigate next" lists the programs with a single open gate and that gate's action, with no in-scope or out-of-scope wording. | regenerated outputs |
| U1-6 | On CLDN18.2, measured against the frozen reference (`reference_calls.csv`), reported per UNRESOLVED program: none of the 16 reference-IN programs gets an indication action that calls its gastric/GEJ indication a different disease. RC118 and the other basket programs get a basket action naming the requested indications. The three PD-1 combination-partner rows (rilvegostomig, volrustomig, RC148) get a target action naming the other targets. Any reference-IN program whose action points away from it is reported, not hidden. | measurement table |
| U1-7 | An adversarial AI review of code and outputs finds no action that misstates the record or the authority, no hidden UNKNOWN, and no change to science. | `REVIEW.md` |

## Not in this cycle

- Changing any gate, the S&E authority or the rank.
- An agent question that proposes indications from documents (it would surface RC118's orphan-designation title). This is the next candidate.
- Reading INN names to flag contradictory vendor modality cells (IBI343 "Imaging agent" vs "arcotatug tavatecan").


## Revision note (after code, disclosed)

Two changes were made during implementation. Neither loosens a criterion.

- **Class `OVERLAPS_REQUESTED` added (indication).** NCIt gives a concept several parents, so a name can resolve
  to exactly one concept that is neither an ancestor nor a descendant of a requested concept, yet shares a subtype
  with it. Held-out example: "colon carcinoma" against a "colorectal adenocarcinoma" request; both are parents of
  "colon adenocarcinoma". The frozen list would have called it `DIFFERENT_DISEASE`, which misstates the authority
  (U1-7). The action says: "reads as ... (NCIt), which is neither broader nor narrower than requested but shares
  subtypes with it". Its place in the order is after `AMBIGUOUS_NAME` and before `AMBIGUOUS_NAME_ALL_BROADER`.
  No CLDN18.2 record falls in this class.
- **U1-6 count.** The criterion says "the 16 reference-IN programs". Measured on R1 final, 15 reference-IN
  programs are UNRESOLVED. The 16th reference-IN program that is not ELIGIBLE, LCB02A, is EXCLUDED by a modality
  FAIL; U1 covers only programs that are not excluded, so it gets no diagnostic. This is reported in
  `MEASUREMENT.md`, not hidden.
- **After the U1 review (revision 2), disclosed.** (1) An ambiguous name whose readings are all neither requested
  nor broader is `DIFFERENT_DISEASE`, not `AMBIGUOUS_NAME`; the sentence lists every reading (review D13).
  (2) A name the authority resolves to one concept that is not requested is `DIFFERENT_DISEASE` even when it names
  a requested site; `NAMES_REQUESTED_SITE` is kept for names the authority cannot read (review J1). (3) A request
  the authority does not resolve to one concept gets a request-level diagnostic, and no record is classed against
  it (review D1). None of these changes a gate, disposition, rank or transaction field.
- **After the second U1 review (revision 3), disclosed.** (1) Class `UNDER_REQUESTED_PARENT` added (indication):
  a concept under a direct by-site parent of a requested concept, whose own names name one of the request's sites
  (a "Stage IV <site> Cancer" concept beside a "<site> adenocarcinoma" request). The frozen list called it
  `DIFFERENT_DISEASE`, which misstates the authority (review N1). It is ordered after `BROADER_THAN_REQUESTED` and
  before `BASKET`. (2) Class `SOURCE_STATES_NOT_REQUIRED_TARGET` added (target): the record's only mention of the
  required target is negated ("X-negative", "not X", "X knockout"); the frozen list called it "may name the
  required target", the opposite of the record (review N6). (3) An empty requested-indication list gets an `OTHER`
  diagnostic saying nothing is compared (review N12; not reachable through `screen`). (4) A suggested restatement
  of an unresolvable request is given only for the concept whose label is the request; otherwise the readings are
  listed for the buyer to choose (review N2). None of these changes a gate, disposition, rank or transaction field.
- **After the third U1 review (revision 4), disclosed.** `UNDER_REQUESTED_PARENT` is narrowed to NCIt stage concepts
  (a label starting "Stage", or a "... by AJCC vN Stage" grouping) that share a by-site ancestor with a requested
  concept, add no non-site category the request lacks, and whose record name itself names a requested site. Revision
  3 gave it to lymphomas, sarcomas and other organs' cancers under a shared parent (review D1). Expression levels
  ("low", "high") name the target; only explicit absence is a negation (review D2). None of these changes a gate,
  disposition, rank or transaction field.
- **After the fourth U1 review (revision 5), disclosed.** A stage concept is `UNDER_REQUESTED_PARENT` only when every
  ancestor the request lacks is a stage grouping, so neuroendocrine, small-cell and sarcoma stage concepts filed
  under the request's site are different diseases (review D2). Cost: FIGO endometrial, adult liver and anal canal
  stage concepts are different diseases too. A capitalised acronym is a basket word only before a basket word
  ("ALL COMERS"; review D1). None of these changes a gate, disposition, rank or transaction field.
- **After the fifth U1 review (revision 6), disclosed.** A capitalised acronym is the word "all" only before a tumour
  head, "solid" or "comers", so "ALL relapsed" and "ALL in adults" are the acronym (review N1). A required target's
  negation is cancelled only by a second state in its own part or written directly after it, never by another
  target's "negative or positive" (review N2). None of these changes a gate, disposition, rank or transaction field.

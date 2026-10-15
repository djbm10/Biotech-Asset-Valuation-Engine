# BD_OPPORTUNITY_TRIAGE v1: preregistration

This is a presentation-layer milestone. It makes no change to identity, target attribution,
modality, qualification, human-PoC, ranking, acquisition, gates or validation labels. H21–H25
stay sealed and H6–H10 unrun. Parked experiments stay parked.

## Reference population (frozen before any triage logic)

`research/se_bd_opportunity_triage_v1/sample.py` selects the sample mechanically. For each demo
run it takes the first 15 reviewable shortlist entries (in practice 10 exist) and the first 10
deferred entries, in declared order. That gives **40 rows** in `sample.json`.

## Expected categories (independent adjudication, frozen before implementation)

An independent agent context sees only `sample.json` and this document. It may use public
primary sources: FDA labels, the Purple Book, Drugs@FDA, EMA/NMPA/MFDS notices, company press
releases and SEC filings, and registry records. It records the following for each row:

- `product_identity`: the actual product, or `UNKNOWN`.
- `name_kind`: `NAMED_PRODUCT`, `DESCRIPTIVE_CONSTRUCT` or `NON_PRODUCT`. `NON_PRODUCT` covers
  procedures, specimen collection and class labels.
- `us_approval`: `APPROVED` (with an FDA source URL, approved indication and year),
  `NOT_APPROVED_EVIDENCE` (an affirmative source shows it is investigational or was
  discontinued) or `UNKNOWN`.
- `other_approval`: the jurisdiction and source URL, or `UNKNOWN`.
- `owner_evidence`: the company and source URL, or `UNKNOWN`. Registry sponsorship is not
  ownership.
- `requested_target`: `YES`, `NO`, `PARTIAL` or `UNKNOWN`, with a source.
- `expected_category`, exactly one of:
  1. `NAMED_INVESTIGATIONAL`: a named investigational product (code, INN or trade name) not
     approved anywhere for any indication.
  2. `APPROVED_REFERENCE`: approved or marketed in at least one major jurisdiction, for any
     indication.
  3. `ACADEMIC_CONSTRUCT`: a descriptive or unnamed construct from an academic or hospital
     sponsor.
  4. `INSUFFICIENTLY_IDENTIFIED`: the name does not identify one product (a class label,
     procedure or fragment), or the product cannot be identified.
  5. `UNKNOWN_OR_CONFLICTING`: it identifies a product, but its status cannot be settled or
     sources conflict.
- `worth_external_research`: `YES`, `NO` or `UNCERTAIN`, with a reason.

Missing information is `UNKNOWN`, never negative. Nothing is labelled available for licensing.

## Implementation constraints

- **Approval evidence** comes only from a frozen openFDA label snapshot (FDA SPL), matched by
  exact normalized equality between the candidate's displayed name or ChEMBL authority record
  name and the label's `brand_name` or `generic_name`.
  - Several distinct application numbers for one key make the match **conflicting**.
  - No match is **unknown**, not "not approved".
  - Approval is shown as US, with the label application number and label version date. The
    approval date and other jurisdictions are not established.
- **Ownership** is never asserted. Sponsors are shown as registry sponsors.
- **Rules are generic.** Name shape and sponsor organisation type are decided without drug- or
  target-specific lists.
- **Engine "Meets"** that relies on prose human-PoC is presented as unverified, not as
  confirmed eligibility. The gate output is preserved.

## Measures (computed against the frozen expected categories)

- **Category accuracy**, overall and per category.
- **Unsupported approval claims**: rows the system calls approved where the reference says
  `UNKNOWN` or `NOT_APPROVED_EVIDENCE`.
- **Ownership claims**: must be 0.
- **Genuine named opportunities surfaced**: reference `NAMED_INVESTIGATIONAL` with
  `worth_external_research=YES` that the system places in category 1.
- **Wrong products promoted**: system category 1 where the reference is not
  `NAMED_INVESTIGATIONAL`.
- **Academic constructs called commercial products**: reference `ACADEMIC_CONSTRUCT` placed in
  category 1 or 2.
- **Independent cold read** of the final before and after briefs, including the time taken to
  identify the candidates worth investigating.
- **Discovery check for CD19+BCMA T-cell engagers.** Count the candidates in the frozen MINT5
  result whose authority modality is an antibody class and that the engine attributes to CD19
  or TNFRSF17. If none are named engagers, report a discovery gap.

No threshold makes this a GO for production. It is a development usefulness comparison.

# BD_OPPORTUNITY_TRIAGE v1: results (development only)

- **Prereg:** `db04327` (`docs/se_policies/bd_opportunity_triage_v1.md`).
- **Frozen inputs:** adjudication and openFDA snapshot `2053cf9`.
- **Implementation:** `5a2a753` plus the final wording commit.
- **Demos:** before in `docs/demos/bd_search_evaluation_v1/`, after in
  `docs/demos/bd_opportunity_triage_v1/`. Both regenerate byte-identically.
- **Scope:** presentation only. No change to gates, identity, target, modality, ranking,
  human-PoC or acquisition. H21–H25 stay sealed and H6–H10 unrun.

## What changed in the brief

- **BD opportunity overview** with five research categories:
  1. Named product, no US FDA label found (research), each tagged `[target confirmed: X]` or
     `[target unconfirmed]`.
  2. Approved / marketed reference product.
  3. Academic / unnamed construct.
  4. Insufficiently identified.
  5. Unknown or conflicting.
- **Other overview content:** target-confirmed candidates (and which target), candidates needing
  verification, missing source categories and next research actions.
- **Triage of held-back candidates.** The engine routes low-support names away from the
  shortlist; they are now triaged and shown separately.
- **US approval** comes only from a frozen openFDA label snapshot. Matching is exact normalized
  equality on the displayed or ChEMBL record name, with the FDA four-letter biologic suffix
  stripped on the label side. Results are:
  - no match is shown as UNKNOWN;
  - several products answering one name are shown as CONFLICTING;
  - a match shows the BLA/NDA number and DailyMed link.
- **Ownership** is never asserted. Sponsors are shown as an organisation type, with the note
  "not ownership".
- **Partial-target matches.** These are candidates the engine excluded under a requirement for
  *all* requested targets, where an authority record confirms *one*. The exclusion is
  unchanged.
- **Engine "Meets" relying on prose human-PoC** now reads "Engine gates pass; human-PoC
  unverified (not confirmed eligibility)".

## Measured against the frozen independent reference (40 rows)

The reference adjudicator used mostly its own memory. It fetched sources for only 4 rows, which
is disclosed in `adjudication.json`.

| Measure | Result |
|---|---|
| Category accuracy | **36/40** |
| Named investigational | 12/12 correct |
| Academic construct | 10/11 correct |
| Insufficiently identified | 9/9 correct |
| Approved reference | 5/8 correct |
| Unsupported approval claims | **0** |
| US approvals in the reference that the system missed | 0 |
| Ownership claims | **0** |
| Genuine named opportunities (reference YES) placed in category 1 | **7/7** |
| Wrong products promoted to category 1 | 4 (below) |
| Academic constructs called commercial products | 1 (NKCARCD19) |

The four wrong promotions are CNCT19 (NMPA-approved), anbal-cel (MFDS-approved), CT103A
(NMPA-approved) and NKCARCD19 (an academic product with a code-shaped name). The first three
come from a US-only approval check; the category label now says exactly that.

## Independent cold read of the FINAL before and after briefs

The reviewer read only the four `brief.md` files. The version it read had two overreaching
phrases and no target tags; both were then fixed in wording only.

| | Before | After |
|---|---|---|
| Five-minute test | **NO** | **PARTLY** |
| Time to a candidate list (BCL) | about 15 min (expert), 25–40 min (junior) | 5–8 min |
| Time to a candidate list (autoimmune) | about 10 min | 5–7 min |
| Key follow-up identifiable | PARTLY | YES |
| Approved products separated | no (3 approved products were "review first") | yes, with FDA label links |

Problems the reviewer still found:

- **Off-target products in the CD19 lymphoma held-back list.** CD70, BCMA and NKG2D products
  appear as "named" there. These are now tagged `[target unconfirmed]`, but are not removed.
- **A CD19-only product in the dual-target brief.** CABA-201 is filed under the CD19+BCMA
  question.
- **Uplizna/inebilizumab shown as unknown approval.** Its openFDA record has an empty `openfda`
  block, so no exact-name match is possible. This is a disclosed miss.
- **Non-US approvals are not visible.** NMPA and MFDS approvals do not show up in the brief.
- **Duplicate trade-name/INN rows** in the partial-target table.
- **Dead legacy programmes shown as named products.** The brief has no "discontinued" status.

## CD19 + BCMA T-cell engagers: diagnosis

The previous demo showed no T-cell engagers, and **this was not a retrieval failure**. In the
frozen MINT5 run (`results/engager_discovery.json`):

- 24 candidates are authority-confirmed on CD19 or BCMA.
- **0 are confirmed on both.**
- Blinatumomab, teclistamab and elranatamab were found and excluded only because the question
  was parsed as CD19 **AND** BCMA (`operator: ALL`).

The brief now lists these 23 partial-target matches. However:

- **All of the engagers surfaced are approved oncology products.** They are comparators, not
  opportunities.
- **No investigational CD19 or BCMA T-cell engager was surfaced.** According to the reviewer,
  from memory: AZD0486, CLN-978 and cizutamig.
- **Only about one genuinely new external opportunity** (obexelimab) appears, again by the
  reviewer's memory.

This is a real discovery and coverage gap. Investigational engagers in autoimmune disease are
mostly disclosed through company pipelines, press releases and conferences, and those sources
were never searched in these runs.

## Verdict

The triage improves usefulness: the five-minute test moves from NO to PARTLY, there are no
unsupported approval or ownership claims, and 7/7 genuine named opportunities are surfaced. It
does not make the shortlist actionable on its own.

## Next biggest limitation

**Source coverage.** The opportunities BD most needs are investigational, unpartnered assets
such as engagers in autoimmune disease. They appear first in company pipelines, press releases
and ASH/EHA/ACR abstracts, none of which these runs searched. After that come non-US approval
status and target confirmation for named products.

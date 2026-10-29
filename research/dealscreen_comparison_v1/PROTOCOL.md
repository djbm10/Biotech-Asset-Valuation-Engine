# DealScreen vs general AI vs spreadsheet: comparison protocol (cycle C1)

**INTERNAL DEVELOPMENT / AI-SIMULATED.** All three "analysts", the reference curator and the critic
are AI agents. Nothing here is human validation; Gates H and B stay open. Simulated timings are never
a human time-saving claim.

Frozen before any workflow ran (commit recorded in `FREEZE.md`). Changes after the freeze are dated
amendments at the bottom, never edits.

## Question

Does DealScreen give a meaningful advantage over (A) a structured spreadsheet workflow and (B) a
capable general-purpose Claude analyst, on a new, different public landscape?

## Challenge

- **Target / indication:** Claudin 18.2 (CLDN18.2) in gastric / gastro-oesophageal junction
  adenocarcinoma. Different from FcRn / C5 in myasthenia gravis and from the frozen S&E zero-shot
  targets (PDCD1, SLC6A2, HRH1, HTR2A, CHRM1, GUCY2C, CHEK1). CLDN18 appears incidentally in older
  S&E alias surveys and one zolbetuximab review packet; it was never a DealScreen fixture or a frozen
  benchmark population. No DealScreen fix was designed against it.
- **Landscape:** `inputs/landscape_cldn18.csv` (62 rows, `programs.yaml`), built mechanically by
  `build_landscape.py` from `sources/ctgov_cldn18_snapshot.json` (ClinicalTrials.gov API v2,
  2026-10-29), `sources/public_evidence.json` (verbatim quotes from fetched public pages, AI curator)
  and openFDA. Field provenance: `inputs/field_provenance.csv`. Rows that may be the same molecule
  under different codes are separate records, as in a vendor export. Includes deliberate noise
  (non-CLDN18.2 drugs registered in the same trials; imaging agents).
- **Buyer:** `inputs/buyer_cldn18_gastric.yaml` (hypothetical). Its `statement` carries the
  transaction preferences (U.S./ex-China rights, not held by large pharma unless returned, not
  marketed, Phase 2+, active, ADC capability, availability must be evidenced).
- **Valuation:** the analyst supplies hypothetical assumptions, labelled as such. Shared
  hypothetical market inputs: `inputs/valuation_market_inputs_hypothetical.yaml`.

## Reference (frozen before workflows)

A separate AI curator, given the same inputs and web access but not DealScreen, writes
`reference/REFERENCE.md` + `reference/reference_calls.csv`: per row, scientific call (IN / OUT /
UNRESOLVED with reason), identity group, rights holder and evidence, availability (EVIDENCED /
NOT EVIDENCED / RIGHTS HELD BY OTHERS), marketing status, and a transaction-attractiveness note; plus
the top candidates. It is same-environment AI work, not an independent human reference. Workflows
never see it.

## Workflows (same inputs, same budget)

All three get exactly: the landscape CSV, field provenance, `sources/`, the buyer YAML, the shared
hypothetical market inputs, the task list below, and web access (WebSearch/WebFetch), with a budget
of about 120 tool calls. None may see the reference, `src/`, `tests/`, or other `research/` folders.
None may claim to be a human or approve as one; human-only steps are recorded as NOT COMPLETED BY HUMAN.

- **A. Spreadsheet SOP.** Works only by building a spreadsheet tracker (Python/openpyxl or pandas
  to emulate Excel), following `SOP_SPREADSHEET.md`, a typical BD analyst's manual process. No DealScreen.
- **B. General Claude.** Free-form, any method except DealScreen.
- **C. DealScreen.** Uses `bve-dealscreen` / `bve-dealscreen-value` as documented in
  `docs/dealscreen/README.md`, plus the same web access.

**Tasks (all workflows):** A identify distinct assets and identity issues; B screen against the
buyer's scientific requirements; C diligence on the most interesting; D ownership, rights,
partnerships, marketing, availability; E shortlist of up to 10 with rationale, risks and open
questions; F preliminary valuation of up to 3 (or why not), reproducible; G deliverable (workbook +
memo) for a Head of BD.

## Metrics (fixed now)

Scored by the critic against the reference, with evidence for every point:

1. **Scientific screening:** reference-IN programs called IN (found), called OUT (wrong exclusion),
   left unresolved; reference-OUT programs called IN (wrong inclusion).
2. **Identity:** same-molecule records given contradictory calls; wrong merges.
3. **Commercial:** availability asserted without evidence (critical); holder / licensee errors;
   conflation of labeler, owner, licensee, marketing and availability.
4. **Shortlist:** critical errors on the shortlist (ineligible, marketed, rights held by large pharma
   without evidence of return, same molecule twice); overlap with the reference's top candidates.
5. **Evidence:** share of shortlist claims with a checkable citation (critic samples).
6. **Finance:** each reported valuation number reproducible from disclosed inputs; assumptions labelled.
7. **Effort:** tool calls and actions (AI-simulated; not a human time claim).

**Critical errors** = wrong exclusions of reference-IN + wrong inclusions in the shortlist +
unsupported availability claims + identity contradictions on the shortlist + unreproducible
valuation numbers presented as results.

**Pre-registered decision rule.** DealScreen shows a *meaningful advantage* over B only if (i) it has
fewer critical errors than B, (ii) it finds no fewer than B minus one of the reference-IN programs, and
(iii) the critic finds its shortlist evidence more checkable. If B ties or wins on (i), the result is
reported as "no demonstrated advantage" on that dimension, whatever else DealScreen does. The same
rule is applied to A.

## Procedure

1. Freeze inputs, reference, SOP and this protocol (commit; `FREEZE.md`).
2. Run A, B and C in separate agent contexts; freeze their outputs (commit) before any code change.
3. Critic compares all three against the reference, evidence required for every claimed advantage or error.
4. Engineering diagnoses DealScreen failures; fix only failures observed here, criteria before code;
   no tuning to the reference (no CLDN18-specific rules).
5. Re-run C (fresh agent) and the critic; regression-check the FcRn and C5 landscapes.

## Amendments

(none)

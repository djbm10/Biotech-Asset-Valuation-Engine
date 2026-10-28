# Gate H: real analyst session protocol (prepared, not yet run)

**Purpose.** The first measurement of DealScreen by a real pharmaceutical BD, diligence or BD
Finance professional. Until this has been run with a person, no claim about usefulness, accuracy
or time saved may be made.

**Participant.** One person with BD, search-and-evaluation or BD Finance experience. Record their
role and years of experience, but not their name in the repository.

**Duration.** About 90 minutes: 40 minutes with DealScreen, 40 minutes on the baseline, and
10 minutes for feedback. Alternate which comes first across participants.

## Disclosure (read to the participant)

- The landscape is 40 real programs built from public sources: ClinicalTrials.gov, FDA labels
  and ChEMBL. It is not a vendor export.
- The buyer is hypothetical.
- Financial inputs are hypothetical, and the deal-terms valuation path is a prototype awaiting
  sign-off.
- Nothing has been validated. The participant's corrections are the point of the session.

## Tasks (DealScreen arm)

Setup (by the facilitator, before the clock starts): a fresh workspace from
`examples/dealscreen_real/landscape_fcrn_gmg_v2.csv` with
`profile_public_landscape_v2.yaml` and `buyer_fcrn_gmg.yaml`.

| # | Task | What to record |
|---|---|---|
| T1 | Read the buyer spec; say in your own words what qualifies | Misreadings of the spec |
| T2 | Open the workbook *Screening* sheet; pick 3 EXCLUDED programs and judge whether each exclusion is right | Agree / disagree per program, with reason |
| T3 | Resolve 3 UNRESOLVED programs (suggested: batoclimab, IMVT-1402, efgartigimod IV) using any public source, entering cited assertions (`bve-dealscreen assert`) or recording why not | Actions, time per program, refusals by the tool, errors |
| T4 | Review U.S. rights for the eligible programs; say which you would treat as available | Any program the participant reads as available, and why |
| T5 | Build a candidate list of up to 10 and approve finalists as a HUMAN reviewer | Number approved, overrides of the machine rank |
| T6 | Request a valuation readiness check for up to 3 finalists; read the result | Whether NOT READY reasons are understood |
| T7 | Export the workbook and memo; name the 3 most and least useful parts | Free text |

## Baseline arm

Same questions (T2-T5), using a spreadsheet copy of the landscape CSV, the provenance file and
any public web sources, with no DealScreen. Record time per task and the answers.

## Metrics (fixed in advance)

- Task completion per task (yes / partial / no).
- Elapsed time per task, in each arm.
- Number of manual corrections the participant makes to DealScreen's output, and which ones.
- Agreement of the participant's final in/out calls with DealScreen's dispositions, and with the
  pre-committed reference (`examples/dealscreen_real/reference_manual_assessment.csv`).
- Errors the participant makes that the tool would have caught, and vice versa.
- Feedback: the free-text answers to T7, plus "would you use this on a real search? why or why not".

## Recording

Use `session_log_template.csv`, one row per task and arm. Store the completed logs under
`research/dealscreen_product_program/gate_h_session/runs/<date>_<role>/`, without personal names
or company-confidential content.

## After the session

Update `SCORECARD.md` dimension 15 and Gate H with the measured results, including any results
that are unfavourable. No time-saving claim may be made from a single session without stating
n = 1.

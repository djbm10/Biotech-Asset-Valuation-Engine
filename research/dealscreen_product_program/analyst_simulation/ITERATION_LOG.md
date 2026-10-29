# Analyst-simulation iteration log (AI-SIMULATED / INTERNAL DEVELOPMENT)

## Cycle A1 (2026-10-28)

- Setup finding (engineering side, before the analyst started): `bve-dealscreen` was declared in
  `pyproject.toml` but not installed in the worktree venv; an editable reinstall registered it.
  An analyst following the README would see "command not found".
- Blind analyst subagent launched with the reference answers, prior results and code withheld
  (see `ANALYST_ASSIGNMENT.md`). Its output is `ANALYST_FINDINGS.md`, frozen at commit before
  any fix.
- Adversarial critic (separate AI context) verified the analyst's 8 headline defects: 6 confirmed,
  1 overstated (#4: the analyst's keys were misplaced; the real defect is silent acceptance), 1
  policy-correct (#8). See `ADVERSARIAL_REVIEW.md`.
- Ranked fixes F1-F8 with criteria committed before code (8d57b27). F8 (vendor area label alone
  excluding a program) was found while testing F2 with a test-only landscape copy.
- Independent code review of the fixes (separate AI context) found 3 HIGH issues in my own
  changes, all fixed with regression tests:
  1. F8 compared raw against canonical area names and treated the "no area requirement" sentinel
     as a requirement (could demote matching assets).
  2. F2 read vague names ("Chronic Disease", "Severe Cancer") as root concepts, and included
     population terms (adult, pediatric) and "active". Now: severity/extent qualifiers only,
     concept depth ≥ 6, generic remainders refused.
  3. F2 readings were missing from the memo, and assertion validation refused a value import
     accepted. Both fixed.
  Also: "No longer active" / "Active - not developed" read as ACTIVE (fixed); workbook holder
  column renamed "U.S. labeler/holder named in source (not owner, not availability)".
- Results: `BEFORE_AFTER_RESULTS.md`. DealScreen tests 119 → 169; fast-path equivalence
  byte-identical on 4 workspaces; ruff and mypy clean on DealScreen.

### What the simulated analyst tried, what happened, what changed (cycle A1 summary)
1. **Tried:** the full A-G assignment on the real FcRn/gMG landscape.
2. **Happened:** funnel 4/14/22 understated the FcRn set; batoclimab counted as three
   programs; dormant codes ranked as active; the deal CLI ran on silent defaults; the workbook
   said "7 approved" for AI candidates; `value` crashed.
3. **What a BD professional would object to:** a ranked list that is wrong in ways not visible
   on the page.
4. **Changed:** F1-F8 (see `PRIORITIZED_FIXES.md`).
5. **Measured:** in-scope ELIGIBLE 4/9 → 6/9 with 0 wrong vs reference; 5 false ACTIVE → 0;
   silent valuation defaults now refused; mislabels removed.
6. **Still difficult:** efgartigimod (buyer modality vocabulary), IMVT-1402 (needs a
   human-entered cited fact; AI cannot even propose one), identity merges not applicable,
   terminated programs not demoted, Phase 4 vs marketed, no efficacy evidence.

## Cycle A2 (2026-10-28)

- Ranked G1-G3 from A1 deferrals; criteria before code. Built `propose` (AI cited fact → human
  confirmation), identity resolution vocabulary and human-confirmed groups, activity disclosure.
- Independent AI code review: no governance break; 7 issues fixed before commit (bad dates crashed
  and could poison later screens; the proposer could confirm its own proposal; confirmation did not
  snapshot content; activity wording overstated; group keys could collapse; "at most"; silent
  re-proposal). Commit bca8b72. README documented (6a03a89).
- Held-out buyer spec (C5 in MG) committed before the re-test.
- Fresh blind analyst re-test (frozen bada391): no wrong in/out gate calls on either buyer; found
  the combination-modality defect, invisible rank reasons, the Finance reproduction gap, and README
  / queue friction.

## Cycle A3 (2026-10-28)

1. **Tried:** the A2 analyst's FcRn regression and held-out C5 shortlist and valuation.
2. **Happened:** Pozelimab + Cemdisiran (contains an siRNA) ranked #1 for an antibody/peptide
   buyer; marketed products' ranks were unexplained; Finance could not see or reproduce a config.
3. **BD objection:** a #1 candidate the buyer's own modality rule should not admit.
4. **Changed:** H1 combination modality → UNKNOWN with reason; H2 rank reasons; H3 `value-config`
   preview; H4/H5 identity subject and queue fixes. The ranking rule was not changed: whether a
   marketed product counts as "active development" is a buyer decision.
5. **Measured:** C5 funnel 5/11/24 → 4/12/24 with the one wrong eligibility removed; FcRn unchanged.
6. **Still hard:** valuation needs a human approval (by design) and hypothetical inputs; no
   partnerability concept; CT.gov research noise; approval-statement stage extraction; blank-target
   rows need human-confirmed facts; Gate H not run.
- A3 independent AI code review: 2 HIGH issues in my fixes, fixed before commit: (1) the combination
  regex missed "A+B" spacing and fired on procedures/placebo ("+ Thymectomy", "+ placebo"); (2) the
  preview config carried its "not approved" label only as a file comment, accepted EXCLUDED assets
  and dropped the stage-mismatch warning. Also found: unused-source-value reasons (A1 F8, A3 H1) were
  visible only in `show`; the workbook now has a "Source values not used, and why" column.
  Disputed: the reviewer called "T-DXd + pembrolizumab" a false positive; it is two drugs, so it
  stays a combination. Unconfirmed agent findings never enter the claims, so a source + finding mix
  occurs only after a human confirms, which is meant to apply. DealScreen tests 209.

## Cycle A4 (2026-10-29)

1. **Tried (A3 re-test, frozen c589367):** S&E regression on both buyers, then a thorough BD Finance
   attempt to obtain, reproduce and challenge valuations for up to 3 programs.
2. **Happened:** screening held (no wrong in/out calls on either buyer; ranks explainable). Valuation:
   only IMVT-1402 had complete inputs; P(approval) and cost PV reproduced by hand; peak sales did not
   (320 vs 400); setting `compliance_rate: 1.0` changed nothing; revenue-PV labels and the assumption
   source table misled; marketed programs (4 of 6 FcRn eligibles) cannot be valued at all.
3. **BD Finance objection:** a number whose bridge from inputs cannot be reproduced cannot go to a
   Finance Director.
4. **Changed (DealScreen only):** J1 unread `market_model` keys refused on DealScreen paths; the
   engine's compliance default disclosed (value read from the engine, not hard-coded) in memo,
   workbook, preview configs and the perspective line. J3 funnel line warns when eligible records
   share open identity flags. J4 cosmetic fixes. **Engine findings P1-P7 written up as a Lane 1
   proposal** (`docs/change_requests/proposed/valuation_transparency_from_analyst_simulation.md`); the
   protected loader and engine were not changed.
5. **Measured:** the 320-vs-400 gap is now explained on every DealScreen display; a config that tries to
   set compliance is refused instead of silently ignored (test). DealScreen tests 212.
6. **Still unsupported:** reproducible revenue bridge and honest assumption-source table (protected,
   proposal), valuation of marketed programs (no model), partnerability, Gate H.

## Cycle A5 (2026-10-29)

1. **Tried:** recurring findings from the A1 critic and A2/A3 analysts: "Phase 4" read as marketed;
   UCB's FDA-approval sentence for rozanolixizumab in the library but no stage finding.
2. **Changed:** K1 display-only market status (U.S.-marketed per source / marketed with no U.S. statement /
   Phase 4 study only), used in memo, workbook and the commercial-block reason; K2 the agent proposes a
   "Marketed in U.S." finding from a clause that names the asset and states its FDA approval.
3. **Independent AI code review:** both first versions were wrong in ways that recreate the danger they
   addressed ("US-based company; approved in EU" read as U.S.-marketed; hedge words anywhere suppressed
   true statements; a name elsewhere in the sentence matched someone else's approval). Both rewritten
   clause by clause, 30+ adversarial cases pinned. A disclosed consequence: a human-confirmed U.S.
   approval makes activity MARKETED, which the buyer's "active development" preference does not count.
4. **Measured:** real landscape stage-6 rows: 8 U.S.-marketed per source, 2 Phase 4 study only
   (rozanolixizumab, telitacicept), where all 10 previously read "Phase 4 or marketed". The library
   yields exactly one approval proposal (RW-03, UCB release). No gate, disposition or rank changed
   (equivalence byte-identical; pins unchanged). DealScreen tests 248.
5. **Still open:** confirming the RW-03 finding needs a human; ex-U.S. approvals are not extracted.

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

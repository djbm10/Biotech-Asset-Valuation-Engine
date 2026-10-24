# Change request: laptop pilot and cloud handoff

Date: 2026-10-23. Requestor: user, autonomous S&E continuation.

```yaml
lane: "4"
cross_lane: false
affected_modules:
  - src/bve/se/reporting/bd_brief.py
  - src/bve/cli/se_bd_brief.py
  - research/se_pilot_handoff_v1
core_output_changed: false
backward_compatible: true
requires_migration: false
feature_flag: null
tests_required:
  - unit: true
  - integration: true
  - backtest_regression: false
```

Problem: unfinished coverage arms exceed local RAM; handoff lacks pinned environment,
transfer verification and bounded orchestration. Brief stage labels can imply indication
specificity without evidence. Restored laptop lacks original TAC01/MINT5 run inputs.

Solution: standalone migration manifest and sequential cloud wrapper; conservative stage
wording; separate analyst worklist exposing the already-frozen reference with source links,
per-field quotation support and explicit unknown rights/PoC. No new acquisition or discovery
experiment. This is a reference-assisted workflow, not engine discovery or a recall claim.

All rNPV, POS, M&A, watchlist and replay decisions remain unchanged. Tests cover transfer
integrity/path traversal, orchestration refusal, unsupported stage, and reference projection.
No gate, identity, modality, alias, qualification, human-PoC or validation threshold changes.
H21–H25 sealed; H6–H10 unrun. No frozen files changed.

Rollback: revert only this change; retain generated artifacts. Engineering implementation
review under user's explicit authorization; no grade promotion or scientific sign-off implied.

## Preregistered development acceptance (before generating outputs)

This is software/workflow verification, not a scientific discovery evaluation. All frozen
reference entries must appear exactly once, keyed by ref_id, with original labels and A/B
membership; a field without quotation support must not be represented as verified. Quote
support is not primary-source adjudication or confirmation of current status. Rights and
human efficacy remain unverified. Engine recovery counts must be labelled historical A_base
only. Generate twice and require byte-identical output. Preserve old demo files byte-for-byte.
Independent expert usefulness/time-to-candidate assessment remains unmeasured unless a
separate reviewer actually evaluates the final output. No fabricated before/after improvement.

# Change request and prospective reviewer protocol

Base: 5eb941d. User-authorized bounded reviewer package and reporting integration.

lane: 4; cross_lane: false; core_output_changed: false; backward_compatible: true;
requires_migration: false; feature_flag: optional research_followup on CandidateCard.
Affected: bd_brief reporting types/renderers, focused tests, new research/se_reviewer_pilot_v1.
All rNPV/POS/M&A/watchlist/eligibility/ranking/identity/historical replay outputs unchanged.
Engineering review under explicit user authorization; no clinical grade promotion or external contact.
Rollback: revert optional display integration/new package; retain historical artifacts.

## Bounded implementation

Reuse Assessed/Source and candidate renderers. Attach only with explicit matching card ID/name;
no aliases, fuzzy joins or product-specific exceptions. Preserve all existing fields, ordering,
gates, human-efficacy assessment and triage. Missing/unsupported source support stays UNKNOWN.
Manual clinical evidence cannot establish confirmed human PoC. Acquisitions cannot populate rights
or availability. Separate engine date, follow-up observation, manual verification and display date.
Reject a follow-up newer than its requested display date; never backdate later verification.
Preserve source URLs, evidence pointers/hashes, record/ledger hashes and manual-review provenance.
A cited source or hash is not proof of entailment; display inherits the completed manual audit.
No new acquisition, studies, corpus scoring, identity experiments or expensive replays.

Tests: explicit binding, no-op backwards compatibility, unchanged original card data and engine
outputs, dates, unknowns, acquisition/rights independence, efficacy conservatism, deterministic
HTML/Markdown and package custody. Focused reporting tests, full tests/se, changed-file Ruff and
repository Ruff report. Do not rerun previous scientific evaluations.

## Independent review plan — fixed before any responses

Prepare a self-contained, versioned public-source package for the user to share. No agent or
implementer response counts as independent BD review. Collect role/independence, prior familiarity,
per-asset time to a concrete next action, action/reason, missing information, exact misleading claim
and severity, usefulness 1–5, confidence 1–5, and reuse intention (yes/conditional/no).
Time source-checking separately; an unfinished task is censored/not-completed, never zero seconds.
Record null until actual response. Do not infer missing answers or turn subjective ratings into
scientific validation. One reviewer gives case-level feedback, not generalization or precision.

Usefulness anchors: 1 unusable; 2 substantial rework; 3 useful starting point with major gaps;
4 useful after routine checks; 5 ready for research triage (never decision-grade).
Critical misleading identity, clinical efficacy, approval or availability claims block further
pilot distribution until reviewed/corrected. Prioritize the reviewer's most consequential blocker;
no new feature cycle before feedback. No fixed time improvement claim without a valid comparison.
The before/after demo is a presentation/invariance check, not an autonomous qualification evaluation.

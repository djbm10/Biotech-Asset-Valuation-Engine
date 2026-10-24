# Reviewer handoff and optional research display

**UNVALIDATED-grade only. Do not use for trade sizing or acquisition probability.**
Base commit: `5eb941d`. This is a reporting/reviewer-readiness milestone, not a new scientific study.

The reviewer-ready folder is **[package_v3/](package_v3/)**. Share that folder intact. Start with
[START_HERE.md](package_v3/START_HERE.md), then [BRIEF.md](package_v3/BRIEF.md). The optional integrated
cards are [after.html](package_v3/after.html) and [after.md](package_v3/after.md). Return the blank
[REVIEW_FORM.md](package_v3/REVIEW_FORM.md) privately. No outside reviewer has been contacted;
usefulness, time-to-action and reuse remain unmeasured.

## Reproduce offline

From the repository root, with the existing environment:

```bash
.venv/bin/python research/se_reviewer_pilot_v1/generate.py --output-dir /tmp/bve-reviewer-reproduction-01
.venv/bin/python -m pytest tests/se/test_research_followup.py tests/se/test_bd_brief.py -q
.venv/bin/python -m pytest tests/se -q
.venv/bin/ruff check src/bve/se/reporting/bd_brief.py src/bve/se/reporting/research_followup.py tests/se/test_research_followup.py research/se_reviewer_pilot_v1/generate.py
```

The output directory must not exist. Each regeneration requires a new directory. No API calls,
scientific replay, source refresh, credentials or cloud resources are used. Source observations and
manual verification are fixed at 2026-10-24 UTC; generation is not new verification. Outputs are
byte-identical across fresh directories. `MANIFEST.json` contains file hashes, excluding itself.
The inherited raw evidence is not redistributed; primary URLs and original pointer/hash metadata
are retained. Prior research records/brief/trial table are copied byte-for-byte.

## Optional integration with an existing card

`load_followup(records_path, ledger_path, asset_id=..., name=..., verified_on=...,
display_as_of=..., verification=...)` selects one exact manual record and preserves its provenance.
`attach_followup(card, followup)` returns a validated copy. The caller must establish the intended
binding; this is not an identity resolver. There is no automatic discovery-to-record join.

Existing `render_html`/`render_markdown` brief renderers show the added section only when explicitly
attached. All original card fields, engine gate results, ordering, ranking, triage and human-efficacy
assessment remain unchanged. Old cards omit the absent field from serialized JSON and render as
before. No database migration or new CLI is required. The adapter is bounded by the supplied manual
record files; do not feed it a large discovery corpus.

The manual section retains separate observation, verification and display dates. It carries identity,
target/format, development, human evidence, approval, company relationship, territorial rights and
availability independently. Missing/unlinked assertions become UNKNOWN; human observations cannot
become confirmed engine PoC. Pointer presence is not entailment validation. This route requires
previous manual source auditing and cannot independently establish that a source supports a claim.
The original record hash/ledger preserve the audit route, including assertions not displayed.

## What changed and what did not

See [BEFORE_AFTER.md](BEFORE_AFTER.md) for the valid comparison. There are no newly discovered assets,
new source verifications or improved autonomous eligibility results. The meaningful engineering
change is optional dated manual context on a candidate card, with a reviewer protocol capable of
measuring whether that helps. The before/after card scaffolds are explicitly NOT_EVALUATED; they are
not a scientific baseline. Cizutamig's frozen name-shape issue remains unchanged and documented.

Local drafts `package_v1/` and `package_v2/` were retained but excluded from publication. The final
`package_v3/` removed misleading run-summary framing and includes the required validation warning.
No frozen reference population, threshold, gate, holdout, historical run or cloud handoff was changed.

Next milestone: obtain a real BD professional's completed rubric. Address their largest actionable
workflow failure before another feature cycle. Critical misleading claims require review/correction
before further package distribution. Do not publish completed responses without explicit consent.

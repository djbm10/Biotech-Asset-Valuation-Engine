# DealScreen product goal (stable end state)

This file defines success. It changes only by an explicit, dated amendment, never to fit a result.

## The product

A pharmaceutical BD team supplies its existing asset landscape (a vendor or internal export)
and its strategic requirements. DealScreen turns that landscape into a scientifically
defensible, commercially informed, analyst-approved shortlist. It connects the selected
assets to auditable valuation scenarios in BVE's existing engine, and produces decision-ready
Excel and memo deliverables.

It is an opportunity evaluation and underwriting workbench, not a drug finder.

## Workflow the finished product supports

| | Capability |
|---|---|
| A | Import ~200 programs with source IDs, original values, dates and provenance. Detect duplicates, alternative codes, contradictions and gaps. Distinguish products, formulations, molecules, programs and territorial licensees. Never drop or wrongly merge. Vendor-neutral |
| B | Evaluate each asset against the buyer's area, indication, target, mechanism, modality, stage, evidence, safety/efficacy, manufacturing/delivery, geographic rights and capabilities. Hard requirements, preferences and financial attractiveness stay separate |
| C | ELIGIBLE / EXCLUDED / UNRESOLVED with evidence links. The analyst resolves, corrects or rejects facts and reruns without rebuilding the landscape |
| D | AI-assisted diligence through approved sources. It proposes facts, shows contradictions and states uncertainty. It never acts as a human or invents facts |
| E | A prioritized candidate list. Science, rights and financial attractiveness are separate. A human approves up to 10, with no quota |
| F | Analyst-approved assumptions go to BVE's valuation engine: rNPV, bear/base/bull, acquisition vs license, sensitivities. Missing inputs block. Commercial-stage products are not valued with pre-approval development models |
| G | Workbook, ranked comparison, diligence queue, approval history, assumption sheets, scenarios, deal comparison and memo. Reproducible, with no prior work lost |

## Acceptance gates

These are the gates of the 2026-10-28 mandate, restated without change. They are passed
only when demonstrated as written.

- **A. Reliable imports:**
  - a realistic 200-program landscape;
  - exact row accounting, stable identities, detected conflicts;
  - complete provenance and reproducible exports.
- **B. Reliable scientific screening:**
  - an independently curated, sufficiently broad evaluation;
  - preregistered thresholds;
  - never passed on same-author AI references;
  - zero false exclusions by marking everything UNKNOWN is not success.
- **C. Effective diligence resolution:**
  - supported UNKNOWNs are resolved inside the tool without editing the source file;
  - original evidence is preserved and decisions are recalculated;
  - time and number of actions are measured.
- **D. Commercial intelligence:** the tool keeps apart suitability, development or marketing status, owner or licensor, territorial rights, encumbrances, actual availability, and unknown availability.
- **E. Analyst-controlled shortlist:** a compared, revised and explicitly human-approved list of at most 10, with every important claim traceable.
- **F. Reliable financial handoff:**
  - three appropriate programs valued from analyst-owned assumptions;
  - results reconcile with the canonical engine;
  - unknown inputs block valuation, and anomalies are explained or blocked;
  - no protected model changes without sign-off.
- **G. Practical deliverables:** a readable workbook and memo, with no Python editing by the analyst.
- **H. Real analyst validation:** at least one real BD, diligence or BD Finance professional completes a representative workflow, with recorded feedback and measured completion, accuracy, corrections and time.
- **I. Integration readiness:** vendor-style exports and refresh diffs are demonstrated, and the architecture for licensed connectors is documented. No integration is claimed without approved access.

## Governance (referenced, not copied)

`AGENTS.md`, `ROADMAP_LOCK.md` (lanes and sign-offs), `ARCHITECTURE_BOUNDARIES.md` (Lane 4
must not compute valuations in process), `VALIDATION_STANDARD.md` (grades),
`DATA_SOURCE_POLICY.md`, `CHANGE_REQUEST_TEMPLATE.md`. The DealScreen change request is
`docs/change_requests/CR-2026-10-26-dealscreen-mvp.md` (with amendments).

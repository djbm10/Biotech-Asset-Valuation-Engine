# BVE DealScreen: buyer-specific BD screening and valuation workbench (MVP)

**Grade: UNVALIDATED. Synthetic-data demonstration.**
- Every program, company, code, trial ID and financial input in the demo is invented.
- Nothing here measures real-world precision, analyst time saved or product-market fit.
- Change request: `docs/change_requests/CR-2026-10-26-dealscreen-mvp.md`. No sign-off has been given.

## What it does

A BD team brings the landscape it already has (a CSV or XLSX export from its data provider,
or an analyst spreadsheet). DealScreen then:
1. **Imports it** through a YAML column-mapping profile:
   - keeps every raw row verbatim;
   - explains every rejected row;
   - writes a reproducible manifest.
2. **Screens it** against the buyer's declared hard requirements, using BVE's existing S&E
   gate engine (`bve.se.gates.GateEngine`), with PASS / FAIL / UNKNOWN per requirement.
   Missing or conflicting evidence is UNKNOWN, never PASS or FAIL.
3. **Keeps commercial rights separate.** U.S. rights are AVAILABLE only on an explicit
   source statement; silence is UNKNOWN.
4. **Queues** unknowns, conflicts, shared codes and agent proposals for an analyst.
5. **Records** analyst decisions in a hash-chained, append-only log. Finalists exist only
   through explicit, attributable approvals.
6. **Hands up to three selected finalists to valuation** through BVE's own CLI and reads back
   the saved `valuation.json`. Missing financial inputs give NOT READY FOR VALUATION.
7. **Writes** an 8-sheet companion workbook and a one-page memo.

## Architecture

```
vendor CSV/XLSX ──► importer (mapping profile) ──► LandscapeAsset + SourceClaim (row, column, dataset)
                                                   │
                         identity flags ◄──────────┤  (SHARED_CODE / PROPOSED_MERGE: never applied)
                                                   ▼
                    FactBuilder ──► NormalizedFact ──► bve.se GateEngine (unchanged)
                         ▲                              │ ELIGIBLE / UNRESOLVED / EXCLUDED
   decision log ─────────┘ (confirm/reject claims,      ├─► preference ranking (never changes a gate)
   (hash-chained)            confirm agent findings)    └─► commercial assessment (independent)
        ▲
        │ explicit actions (HUMAN or labelled SYNTHETIC_FIXTURE)
        │
   diligence agent (offline library | public ClinicalTrials.gov) ─► proposed findings only
        │
   finalists (≤10) ─► selected (≤3) ─► bve-asset / bve-dealscreen-value (subprocess) ─► valuation.json
                                                                   │
                                     workbook (8 sheets) + memo ◄──┘ (numbers copied, never recomputed)
```

| Module | Role |
|---|---|
| `bve.dealscreen.mapping` / `importer` | Profiles, CSV/XLSX import, row accounting, manifest |
| `bve.dealscreen.identity` | Shared-code and proposed-merge flags (the IL3RA MB-102 regression lives here) |
| `bve.dealscreen.facts` | Claims → `NormalizedFact`; unreadable → no fact; disagreement → contradicting claims |
| `bve.dealscreen.screening` | Runs `GateEngine`, declared lexicographic preference ranking, funnel |
| `bve.dealscreen.commercial` | Rights status, kept independent of science |
| `bve.dealscreen.review` | Decision log, approval rules (≤10 finalists, ≤3 valuations, EXCLUDED blocked) |
| `bve.dealscreen.agent` | Diligence provider protocol: offline evidence library, public CT.gov |
| `bve.dealscreen.valuation_handoff` | Readiness checklist, config writer, subprocess runner, output reader |
| `bve.cli.dealscreen_value` | **PROTOTYPE** CLI: `bve-asset` plus a `deal_economics:` block (Lane 1 sign-off pending) |
| `bve.dealscreen.workbook` / `memo` | Deliverables |
| `bve.dealscreen.synthetic` / `evaluate` | Seeded demo data; ground-truth scoring (evaluation only) |

DealScreen never imports `ValuationEngine`. The architecture boundary forbids Lane 4 from
triggering valuation in process, so valuations run as subprocesses of the CLI.

## Reproduce the demo

```bash
# one-time: Excel support
pip install -e ".[dev,dealscreen]"

# regenerate the synthetic inputs (deterministic; the committed copies are identical)
python -m bve.dealscreen.synthetic examples/dealscreen

# full walkthrough with the real S&E ontology (~75 s, ~1.9 GB peak, no network)
bve-dealscreen demo --workspace outputs/dealscreen_demo --n-sims 5000

# fast/offline variant (same results on this landscape; no ontology load)
bve-dealscreen demo --workspace outputs/dealscreen_fast \
    --target-map examples/dealscreen/target_map.yaml --n-sims 1000
```

Step-by-step, as an analyst would run it:

```bash
W=outputs/my_screen
bve-dealscreen import   --workspace $W --landscape examples/dealscreen/landscape_200.xlsx \
    --profile examples/dealscreen/profile_synthetic_vendor.yaml --buyer examples/dealscreen/buyer_tl1a_ibd.yaml
bve-dealscreen screen   --workspace $W
bve-dealscreen show     --workspace $W --asset SYN-0040        # decisions, evidence, raw rows
bve-dealscreen research --workspace $W --provider offline:examples/dealscreen/evidence_library.json --unresolved
bve-dealscreen decide   --workspace $W --action CONFIRM_FINDING --subject SYN-0040 --field target \
    --new-state CONFIRMED --reviewer jdoe --rationale "Press release names TL1A"
bve-dealscreen screen   --workspace $W                           # re-screen with the confirmed finding
bve-dealscreen decide   --workspace $W --action APPROVE_FINALIST --subject SYN-0020 \
    --new-state APPROVED --reviewer jdoe --rationale "Phase 3, antagonist, fits mAb capability"
bve-dealscreen decide   --workspace $W --action SELECT_FOR_VALUATION --subject SYN-0020 \
    --new-state SELECTED --reviewer jdoe --rationale "Preliminary valuation"
bve-dealscreen value    --workspace $W --assumptions examples/dealscreen/valuation_assumptions.yaml
bve-dealscreen export   --workspace $W --out $W/deliverables/dealscreen.xlsx
bve-dealscreen memo     --workspace $W --out $W/deliverables/bd_memo.md
```

Entering facts you found yourself, and identity decisions:

```bash
# a human analyst enters a cited fact (URL + verbatim quote); re-screen to apply it
bve-dealscreen assert  --workspace $W --asset RW-08 --field target --value FCGRT \
    --source-url https://... --quote "verbatim sentence" --reviewer jdoe --rationale "10-Q"
# an AI assistant cannot assert; it proposes, and a different human confirms
bve-dealscreen propose --workspace $W --asset RW-08 --field target --value FCGRT \
    --source-url https://... --quote "verbatim sentence" --reviewer ai-assistant
bve-dealscreen decide  --workspace $W --action CONFIRM_FINDING --subject <prop:... id printed above> \
    --new-state CONFIRMED --reviewer jdoe --rationale "checked the quote at the URL"
# identity flags (printed at import and by `queue`): SAME_MOLECULE, DIFFERENT_MOLECULE or UNSURE.
# A human SAME_MOLECULE groups records for counting in the memo; records are never merged.
bve-dealscreen decide  --workspace $W --action RESOLVE_IDENTITY_FLAG --subject batoclimab \
    --new-state SAME_MOLECULE --reviewer jdoe --rationale "RVT-1401 is the former code"
```

Valuation configs for `bve-dealscreen-value` put `discount_rate` under `asset:` and deal terms
under `deal_economics:`; unknown top-level keys are refused rather than ignored.

`research --provider ctgov` queries public ClinicalTrials.gov for an asset's own registered
`NCT` IDs, at most 5 per question. The synthetic landscape uses `SYNTRIAL-` IDs, so the
demo never reaches a real record.

## Files

| Path | What |
|---|---|
| `examples/dealscreen/landscape_200.{csv,xlsx}` | Synthetic 200-row landscape: the only application input |
| `examples/dealscreen/profile_synthetic_vendor.yaml` | Column-mapping profile with license metadata |
| `examples/dealscreen/buyer_tl1a_ibd.yaml` | Hard requirements (`BuyerProblemV2`), preferences and commercial questions, kept separate |
| `examples/dealscreen/ground_truth.json` | Correct answers. **Evaluation only, never read by the application** |
| `examples/dealscreen/reviewer_fixture.csv` | Decisions of a **labelled synthetic reviewer** (`SYNTHETIC_FIXTURE`) |
| `examples/dealscreen/evidence_library.json` | Synthetic public-style documents for the offline agent |
| `examples/dealscreen/valuation_assumptions.yaml` | **Hypothetical** analyst-owned financial inputs |
| `outputs/dealscreen_demo/` (not committed) | Workspace: decision log, screening, valuations, `demo_report.json` |
| `outputs/dealscreen_demo/deliverables/dealscreen_companion.xlsx` | Workbook |
| `outputs/dealscreen_demo/deliverables/bd_memo.{md,docx}` | Memo |

## Demo results (actual run, 2026-10-27, real ontology, 5,000 simulations)

**Import:**
- 200 rows read: 195 imported, 2 rejected, 3 exact duplicates.
- The 2 rejected rows: an empty Drug ID, and the date "31/02/2025".
- 195 imported rows make 192 programs: 3 programs appear twice with conflicting values.

**Funnel:**

| | Initial screen | After review of agent findings |
|---|---:|---:|
| Eligible | 27 | 31 |
| Unresolved | 20 | 16 |
| Excluded | 145 | 145 |

**Excluded by first failed gate:**
- target: 133;
- phase: 6;
- modality: 4;
- mechanism (DR3 agonists): 2.

**U.S. rights among the 31 eligible:**
- available per source: 3;
- encumbered: 5 (one moved from available after a confirmed news finding);
- unknown: 23.

**Against the synthetic ground truth:**
- 184/192 dispositions agree, before and after review.
- 0 false exclusions, 0 false eligibles, 0 identity merges and 0 AVAILABLE rights without an explicit statement.
- The 8 disagreements are expected-EXCLUDED programs the engine leaves UNRESOLVED:
  - 5 whose target is written "IL-23", which is not a resolvable symbol;
  - 3 TL1A programs outside IBD. By design, the gate engine never asserts indication incompatibility from registry text.

**Review and agent:**
- The agent proposed 8 findings.
- The synthetic reviewer confirmed 5, resolved the XB-102 shared-code flag as KEEP_SEPARATE, and requested 1 diligence item.
- It approved 10 finalists (9 ELIGIBLE, 1 APPROVED_WITH_OPEN_QUESTIONS) and selected 3 for valuation.
- The log refused its deliberate attempt to approve an excluded DR3 agonist.

**Valuations** ($M rNPV; hypothetical inputs; read from `valuation.json`):

| Finalist | Bear | Base | Bull | P(approval) | Acquisition (buyer) | U.S. license (buyer) |
|---|---:|---:|---:|---:|---:|---:|
| Rosemab (Phase 3) | −171 | 253 | 1,052 | 54% | −758 | −105 |
| Torlimab (Phase 2) | −112 | −51 | 166 | 22% | −613 | −181 |
| Selimab (Phase 2, rare subgroup) | −120 | −127 | −108 | 22% | −1,063 | −319 |

The other 7 finalists are NOT READY FOR VALUATION:
- 6 have no inputs;
- 1 has a partial block missing price, patent life and trial cost.

**Performance:**
- 66 s in total, 1.84 GB peak resident memory. Import took 21 s, screening 3 s, review and
  re-screening 1 s, nine valuation subprocesses 40 s, and the exports 2 s.
- The memory and the import time are the S&E ontology load. The gate engine loads it even in
  `--target-map` mode, so that mode is not lighter.
- Manual review actions: 20 logged.

## Limitations

- **Synthetic only.** The archetype mix was chosen by the generator author. Agreement with
  ground truth that the same author wrote is a regression check, not an accuracy measure.
- **Indications are never FAILed.** The existing gate engine reserves indication FAIL for a
  future negative-evidence contract, so out-of-indication programs land in UNRESOLVED.
- **Vendor text quality limits screening.** Targets must resolve to an approved symbol;
  "IL-23", "Undisclosed", "Biologic" and "Humanized IgG1 antibody" stay UNKNOWN.
- **Identity flags are resolved but not applied.** A merge decision is recorded, but this MVP
  does not merge records; one program reported under two external IDs stays two rows.
- **The diligence agent is pattern-based** (sentence-level). No LLM provider is bundled.
- **Valuation findings (2026-10-27 audit, `research/dealscreen_hardening_v1/FINANCIAL_AUDIT.md`):**
  - Selimab's bear-above-base ordering is real arithmetic for a cost-dominated program, not an
    engine error. DealScreen now explains such cases and BLOCKS any out-of-order result it cannot
    explain.
  - The RLAY `bve-asset` crash was a stale console line plus silently ignored legacy design keys.
    The CLI now fails closed. The RLAY config migration is a proposed patch awaiting Lane 1 sign-off.
- **The deal-terms path is a PROTOTYPE** awaiting Lane 1 quant + clinical sign-off. With no
  deal block it reproduces `bve-asset` exactly (tested).
- **Workbook.** The export writes a separate companion file. It refuses to touch any existing
  workbook it did not create, and so cannot update an analyst's own workbook in place.

## Real public landscape (INTERNAL DEVELOPMENT)

A second demo runs DealScreen on 40 real FcRn / myasthenia gravis programs built only from
public sources. Results, every source, the asset-by-asset assessment and a five-minute script
using real assets: `research/dealscreen_real_v1/REPORT.md`.

```bash
python research/dealscreen_real_v1/build_landscape.py   # rebuild from saved snapshots (offline)
W=outputs/dealscreen_real; E=examples/dealscreen_real
bve-dealscreen import --workspace $W --landscape $E/landscape_fcrn_gmg.csv \
    --profile $E/profile_public_landscape.yaml --buyer $E/buyer_fcrn_gmg.yaml --identity-authority
bve-dealscreen screen --workspace $W
bve-dealscreen research --workspace $W --provider offline:$E/evidence_library_public.json
```

## Five-minute walkthrough script (synthetic)

1. **(0:00) The problem.** "Your team already has a 200-program landscape from its data provider.
   The bottleneck is not finding programs; it's deciding, defensibly, which ones fit *this* buyer."
2. **(0:40) Import.**
   - Run `bve-dealscreen demo`. Open the workbook's *Landscape* sheet: every row is there verbatim.
   - Two are rejected with reasons, three are exact duplicates. Nothing disappears.
3. **(1:20) Buyer spec.** Open `buyer_tl1a_ibd.yaml`. Three separate blocks:
   - hard science (target, modality, mechanism, indication, phase);
   - preferences (Phase 2+, active, mAb capability);
   - commercial questions.
   "Preferences can only reorder candidates. They can't let anything through a gate."
4. **(2:00) Screening.** The *Screening* sheet:
   - 27 eligible, 20 unresolved and 145 excluded at first;
   - each gate shows PASS / FAIL / UNKNOWN with the cited row and column;
   - the DR3 agonist antibody fails on mechanism, the CAR-T fails on modality;
   - a program with a blank target is UNKNOWN, not excluded.
5. **(2:50) Rights are separate.**
   - Of the eligible programs, most have UNKNOWN U.S. rights.
   - "No license recorded" never becomes "available".
   - XB-102 shows the identity guard: two companies' molecules share a code and are kept apart (the MB-102 failure).
6. **(3:30) Review.** The *Diligence* sheet:
   - the agent proposed a target from a dated press release, with the sentence quoted;
   - nothing changed until the reviewer confirmed it, and then four programs became eligible;
   - the reviewer's attempt to approve an excluded program was refused.
   "Every approval has a name, a time and a reason, and the log is tamper-evident."
7. **(4:15) Valuation.** *Valuation Scenarios* and *Deal Comparison*:
   - three finalists run through BVE's own engine, with bear, base and bull, plus acquisition versus license;
   - seven finalists are NOT READY because nobody owns their price or cost assumptions, and the tool will not invent them.
8. **(4:45) Close.**
   - "It doesn't replace scientific judgment or your database. It turns your existing landscape into a defensible, auditable shortlist and a first valuation, in Excel."
   - The memo is the one-page summary. Caveat: synthetic data, UNVALIDATED.

## Next three improvements for a real BD team

1. **Licensed-provider mapping profiles and an incremental refresh.** Map real Citeline or
   Cortellis export layouts, which still need no API, and diff successive exports so analysts
   review only what changed.
2. **An indication-level negative-evidence contract and a reviewed synonym layer for vendor
   target and modality text.** Today these are the two largest sources of avoidable UNRESOLVED.
3. **A rights and ownership evidence workflow.** Structured capture of license and option terms
   from filings and press releases, with the analyst confirmation already built. U.S. rights
   are the question BD most needs answered and the one the landscape data least often has.

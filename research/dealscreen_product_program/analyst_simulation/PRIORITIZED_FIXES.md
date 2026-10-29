# Prioritized fixes (AI-SIMULATED / INTERNAL DEVELOPMENT)

Ranked by: wrong-decision potential, BD importance, assets affected, analyst effort,
recurrence across landscapes, fix risk. Criteria were written before any code.

## Cycle A1 — ranked list (from frozen ANALYST_FINDINGS.md, reproduced by engineering)

| Rank | Id | Problem (finding #) | Root cause class | Decision |
|---|---|---|---|---|
| 1 | F1 | "Registry: no recruiting gMG trial (COMPLETED)" read as ACTIVE; feeds the "active development" rank (#3; 5 rows) | software defect (negation) | FIX |
| 2 | F2 | "Generalized Myasthenia Gravis" → indication UNKNOWN (#1; 5 rows; recurs in any landscape using severity/extent qualifiers) | weak normalization: frozen NCIt 26.08e has no gMG concept | FIX in DealScreen, disclosed; S&E authority unchanged |
| 3 | F3 | `bve-dealscreen-value` silently drops unknown config keys (`discount_rate`, `deal_options` at top level) (#4) | software defect (fail-open input) | FIX: fail closed |
| 4 | F4 | Workbook Finalists note "7 approved finalist(s)" for AI_PREPARED candidates (#5) | software defect (labelling) | FIX |
| 5 | F5 | Memo: "U.S. rights holder is evidenced" counts an FDA labeler (#6); empty "Preliminary valuations" heading (#14) | labelling defect | FIX |
| 6 | F6 | `bve-dealscreen value` crashes with FileNotFoundError when nothing ran (#7) | software defect | FIX |
| 7 | F7 | Identity flags not shown at import or in the memo candidate list (#2, surfacing part) | workflow / UX | FIX (surface only; merges still not applied) |
| — | D1 | Efgartigimod modality "Protein" (Fc fragment) UNRESOLVED (#9) | unclear buyer requirement + S&E modality vocabulary | DEFER: needs buyer/S&E governance; not assumed |
| — | D2 | AI cannot record cited evidence even as a proposal (#8) | workflow | NEXT CYCLE candidate (AI proposal → human confirm) |
| — | D3 | Identity merges cannot be applied (#2, decision part) | workflow | NEXT CYCLE candidate |
| — | D4 | No human-efficacy evidence field (#12) | missing capability | BACKLOG |
| — | D5 | CT.gov research returns phase-only findings; title labelled "mechanism" (#10) | weak extraction | BACKLOG |
| — | D6 | Peak-sales haircut (gross-to-net) not explained (#15) | valuation disclosure; protected engine | PROPOSAL only |
| — | D7 | `bve-asset` (protected) also ignores unknown top-level keys such as `market:` in 10 example configs | protected code | PROPOSAL only (Lane 1) |

## Acceptance criteria (written before code)

- **F1.** `activity_status` never returns ACTIVE when the activity word is negated
  ("no recruiting", "not recruiting", "no active", "not active", "no ongoing"). "Marketed" is its own
  value MARKETED (not counted as active development, so ranks do not change for marketed rows).
  On the real landscape: RW-06, RW-07, RW-25, RW-28, RW-29 are no longer ACTIVE; every
  "Active trial in registry" row stays ACTIVE. Ranking rule unchanged.
- **F2.** An indication string the NCIt authority cannot identify, written as
  `<qualifier> <disease>` with a qualifier from a closed list (generalized, refractory, relapsed,
  relapsing, recurrent, chronic, severe, moderate, mild, moderate to severe, active, adult,
  pediatric) where `<disease>` identifies exactly one NCIt concept, is also read as that concept.
  Every such reading is listed on the asset (observed text, read as, rule) and appears in `show`
  and the workbook. Never applied when the full name already resolves. Adversarial: "non-small
  cell lung cancer", "anti-…", "ocular …", "AChR+ …", "acute …" are not stripped; a buyer asking for a
  subtype is not satisfied by its parent. No S&E file changes. Real landscape: the gMG-only rows
  move only on the indication gate; no row moves to ELIGIBLE unless all other gates PASS.
- **F3.** Unknown top-level keys fail with exit code 2 and a message naming each key and, for
  known misplacements (`discount_rate` → `asset.discount_rate`, `deal_options` → `deal_economics`),
  the correct location. Results with valid configs unchanged (the bve-asset parity test still passes).
- **F4.** The Finalists note counts by reviewer kind; "approved" is said only of HUMAN decisions in
  APPROVED state.
- **F5.** The memo calls the holder "U.S. labeler/holder per cited source (not a rights or
  availability statement)"; when no valuation ran, the memo says why (no human-selected finalist,
  or not ready).
- **F6.** `value` with nothing to run exits 0 with a plain message and writes an empty results file.
- **F7.** `import` prints the identity flags (kind, records); the memo marks candidates that share
  an identity flag.

## Additions after the adversarial review (still before code)

- **F2 extended.** Also read the inverted form `<disease>, <qualifier>` (e.g. "Myasthenia Gravis,
  Generalized") and a trailing parenthetical acronym (e.g. "… (gMG)", letters only, ≤6 chars).
  The same disclosure applies.
- **F3 corrected.** The critic showed finding #4 was overstated: the analyst's keys were misplaced.
  The defect is that misplaced keys are accepted silently and the default 12% is applied without
  notice. F3 stands as written. **F3b:** the prototype prints, with every result, the discount
  rate used and the economic perspective (asset-holder rNPV, not a buyer deal NPV, unless
  `deal_economics` is given, in which case the terms are listed).
- Reviewer notes "IMVT-1402 is blocked on four gates, not one", "rozanolixizumab curated as
  Phase 4" (stage semantics, backlog) and "coverage limited to CT.gov" are recorded; none is
  in this cycle.

Baseline per asset: `measure/baseline_A1.json` (from the analyst's own workspace).

## F8 (found during F2 testing; criteria before code)

**Problem.** A vendor therapeutic-area label is not exclusive: myasthenia gravis is both
neurological and autoimmune. When the indication text is unreadable, the vendor label
"Neurology" alone becomes the whole area fact and the AUTOIMMUNE requirement FAILs, which
EXCLUDES the program. Analyst finding #13 (belimumab RW-29) is this defect. It is masked on the
real landscape only because belimumab also fails on target. A test-only copy with RW-05's
indication written "gMG" reproduces a wrongful exclusion of an in-scope FcRn antibody.

**Rank.** First by severity: it causes wrongful exclusions, which an analyst never sees in the
review queue.

**Criteria.**
- When the only area evidence is a vendor TA label (no indication-derived area), and that label
  does not include a requested area, the area fact is not emitted, so the gate is UNKNOWN, not FAIL.
  The asset lists the reason ("vendor area label alone cannot exclude").
- When an indication-derived area exists, behaviour is unchanged (FAIL is still possible when the
  indication-derived areas and labels exclude all requested areas).
- A vendor label that matches a requested area still PASSes.
- Real landscape: no disposition changes except RW-29 (stays EXCLUDED on target); its TA gate goes
  FAIL → UNKNOWN. Synthetic demo funnel unchanged, or every change explained.
- S&E gate code unchanged.

## Cycle A2 — ranked list and criteria (written before code, 2026-10-28)

| Rank | Id | Problem | Decision |
|---|---|---|---|
| 1 | G1 (was D2) | The AI assistant finds cited evidence (e.g. the Immunovant 10-Q for IMVT-1402) but cannot hand it to a human: the human must redo the research. Analyst finding #8. | FIX: AI proposal → human confirmation |
| 2 | G2 (was D3, partial) | Identity resolution takes any free-text state and changes nothing downstream; batoclimab still counts as three programs in the funnel and memo. | FIX: closed vocabulary; human-confirmed same-molecule groups shown and counted; records are not merged |
| 3 | G3 | A terminated program (orilanolimab) is ELIGIBLE and its memo line does not say development stopped. | FIX: disclose source activity on candidate lines; ranking rule unchanged (a ranking change is a buyer-preference decision) |

**G1 criteria.**
- New command `bve-dealscreen propose` records a cited proposal (field, value, http(s) URL,
  title, date, verbatim quote) as an agent finding with provider `ai_proposal:<reviewer>`.
- Same checks as a human assertion: assertable field, readable value, http(s) URL, non-empty
  quote, and a rights value must be stated by its quote. Refused proposals write nothing.
- A proposal changes nothing until a HUMAN confirms it (`decide --action CONFIRM_FINDING`); an
  AI_PREPARED confirmation stays refused. The screen before confirmation is byte-identical to
  the screen without the proposal.
- The finding carries the limitation "proposed by an AI assistant; re-check the quote at the URL
  before confirming". The memo lists the number of proposals awaiting a human.

**G2 criteria.**
- `RESOLVE_IDENTITY_FLAG` accepts only SAME_MOLECULE, DIFFERENT_MOLECULE or UNSURE. Others are
  refused.
- Only a HUMAN SAME_MOLECULE resolution groups records. Grouping never merges claims or changes
  any gate decision.
- The memo states distinct-molecule counts for eligible programs ("6 eligible records = N
  distinct molecules after human-confirmed identity"), and each candidate line names its group.
  Unresolved flags keep the existing "may be the same molecule" warning.
- The workbook Screening sheet has an "Identity group (human-confirmed)" column.

**G3 criteria.**
- Memo candidate lines say "development stopped per source" for INACTIVE and "no active trial per
  source" when no activity is evidenced. Ranking is unchanged.
- **G3 amendment (during build, before testing).** UNKNOWN activity is worded "development activity
  not evidenced in source", not "no active trial per source": UNKNOWN also covers a blank status, and
  silence is not evidence of no trial.
- **A2 review amendments (after the independent AI code review, before commit).** INACTIVE is worded
  "source status suggests development stopped (verify)" (trigger words such as "terminated" can
  describe one trial, not the program); MARKETED gets "marketed per source"; activity from several
  status claims ignores UNKNOWN and treats ACTIVE + MARKETED as ACTIVE; the distinct-molecule count is
  "at most N". Added: bad dates refused for assertions and proposals; the proposer cannot confirm
  its own proposal; a confirmation snapshots the finding's content hash, and a finding edited after
  confirmation is not applied; group keys are unique per group.

## Cycle A3 — from the frozen A2 re-test (ANALYST_FINDINGS_A2.md, bada391); criteria before code

| Rank | Id | Problem (A2 defect #) | Class | Decision |
|---|---|---|---|---|
| 1 | H1 | A combination ("Pozelimab + Cemdisiran": antibody + siRNA) passes the modality gate on the single vendor modality "Antibody", and ranks #1 for the held-out C5 buyer (#2, #1) | weak normalization: one modality value for a multi-component product | FIX |
| 2 | H2 | Ranking reasons are invisible; marketed products rank below active-trial programs (#1) | unclear buyer requirement (whether marketed counts as "active development" is the buyer's call) | Do NOT change the rule; show each candidate's rank reasons in memo and workbook |
| 3 | H3 | BD Finance cannot reproduce or challenge a valuation config without a human approval or invented company data (#3) | workflow | FIX: export the exact handoff config as a labelled, unapproved preview |
| 4 | H4 | README identity example refused; `queue` never prints flag ids (#5) | doc + UX defect | FIX |
| 5 | H5 | `queue` not in rank order (#11); candidate listing says "re-run screen" (#12); README says 8 sheets (#13) | cosmetic | FIX |
| — | — | ctgov phase-only noise (#6), approval-statement stage extraction (#7), propose does not fetch the URL (#8), modality vocabulary hint (#9), blank-target rows (#10) | backlog | DEFER (recorded) |

**H1 criteria.** When the program name joins components with " + " (or " plus "), and the
modality evidence is a single value, the modality fact is not emitted: the gate is UNKNOWN, with
the reason "combination product: one modality stated for several components". The target and
other gates are unchanged. No other row on the real landscape changes. Analyst-asserted modality
still applies (a human can state the combination's modality).

**H2 criteria.** Memo candidate lines and a workbook "Rank reasons" column state the ranking key
in words (meets preferred phase yes/no, development activity, stage, registered trials, buyer
capability modality). The ranking rule and every rank are unchanged.

**H3 criteria.** `bve-dealscreen value-config --asset <id> --assumptions <file> --out <yaml>
[--deal <name>]` writes exactly the config the handoff would run (`build_config`), headed
"PREVIEW — not human-approved; not a DealScreen valuation". It refuses when readiness fails
(listing what is missing) or for commercial-stage programs. It does not run the engine and
writes nothing to the decision log. `bve-dealscreen-value` accepts the file unchanged.

**H4 criteria.** `queue` prints each flag's id. `RESOLVE_IDENTITY_FLAG --subject <name>` resolves a
drug name or `DRUG:` value when it matches exactly one flag; when it matches several, it is refused
with the matching flag ids listed. README example uses a flag id.

**H5 criteria.** `queue` lists unresolved assets by rank; a candidate listing prints no
"re-run screen" hint; README sheet count corrected.
- **H2 amendment (during build).** Rank reasons per program appear in the workbook only; the memo
  has a one-page budget (600 words, an existing test) and points to the workbook column instead.

## Cycle A4 — from the frozen A3 re-test (ANALYST_FINDINGS_A3.md, c589367); criteria before code

**Diagnosis of the valuation findings (engineering, after the freeze).**
- D1 (peak sales 320 vs 400): `MarketModel.compliance_rate` defaults to 0.80
  (`src/bve/models/market_model.py`), and the shared `bve-asset` loader
  (`src/bve/cli/run_asset.py::_build_objects`) builds `MarketModel` from a fixed list of 13 keys that
  excludes `compliance_rate`, `gross_to_net_rate` and `price_basis`. A user's value is dropped silently.
  The analyst's "setting it to 1.0 changes nothing" is therefore a loader defect, not a formula error.
- D2, D3, D4, D6 (revenue-PV labels, authoritative-looking sources attached to hypothetical inputs,
  redundant or mislabelled tornado rows, an undisclosed post-patent tail) are all in the protected
  valuation engine and its reporting. **Not changed here.** They need Lane 1 sign-off and go into a
  written proposal.

| Rank | Id | Problem (A3 #) | Decision |
|---|---|---|---|
| 1 | J1 | Market inputs silently dropped by the loader; the 0.80 compliance default is invisible (D1) | FIX in DealScreen: refuse unread `market_model` keys; disclose the 0.80 default wherever DealScreen shows a valuation or config. Engine and loader unchanged; proposal written |
| 2 | J2 | Engine output labelling and sources (D2-D6) | PROPOSAL only (protected) |
| 3 | J3 | Headline "6 eligible" counts one molecule three times (D8) | FIX: funnel line states how many eligible records sit in open identity flags |
| 4 | J4 | Memo "Finalists: 0 ( reviewers)" (D11); workbook says "synthetic demo" on real data (D12) | FIX |
| — | — | Zilucoplan "Protein" and gefurulimab blank target (D7): source-data gaps with an in-tool path (`propose` → human confirmation) | No code change |
| — | — | Marketed programs cannot be valued (D10): no commercial-stage model exists | BACKLOG (scope; Lane 1) |
| — | — | Unresolved queue order (D9), pydantic warning (D13) | BACKLOG |

**J1 criteria.** `bve-dealscreen-value` and the handoff refuse `market_model` keys the loader does not
read (exit 2, naming the key and noting that `bve-asset` would ignore it). Every DealScreen valuation
display (memo driver line, perspective line, preview config limitations) states "peak sales include a
0.80 compliance factor (engine default; not settable through the bve-asset loader)". Results unchanged
for valid configs.

**J3 criteria.** When eligible records share an open identity flag, the memo funnel line adds "(N of
these records may be the same molecule; see identity flags)". Counts and dispositions unchanged.

**J4 criteria.** No "( reviewers)" text with zero finalists; Valuation Inputs header names the
landscape's data source.

## Cycle A5 — stage semantics and approval statements (criteria before code)

Raised independently by the A1 critic ("rozanolixizumab curated as Phase 4"), the A2 analyst (#7: the
offline library holds UCB's FDA-approval sentence but no stage finding is raised) and the A3 analyst
(memo omits "marketed per source" for RW-03). Today stage order 6 is labelled "Phase 4 or marketed"
for any of: a Phase 4 study, an ex-U.S. approval, or U.S. marketing.

**K1 criteria (market status, display only).**
- Each asset gets `market_status`: `US_MARKETED` when a status claim says marketed in the U.S. (or an FDA
  label/approval); `MARKETED_NO_US_STATEMENT` when it says marketed/approved without a
  jurisdiction; `PHASE4_STUDY_ONLY` when the phase is Phase 4 and no marketing claim exists; otherwise
  none. Negated wording ("not approved", "not marketed") never sets a marketed status.
- Memo and workbook show this instead of "Phase 4 or marketed". The commercial-stage valuation block
  stays (stage order 6 still means approved somewhere), but its reason names the evidence: "U.S.-marketed
  per source" vs "Phase 4 study; approval jurisdiction not stated".
- No gate, disposition or rank changes (verified with the equivalence check and real-landscape pins).

**K2 criteria (agent reads approval statements).**
- The STAGE question proposes `development_status = "Marketed in U.S. (FDA approval stated in source)"`
  when a sentence naming the asset says it was approved by the U.S. FDA. Not for: "submitted",
  "accepted for review", "seeking approval", "not approved", "approval of [another drug]", or approval by
  another agency only.
- It is a finding: nothing changes until a human confirms it.
- Real library: rozanolixizumab (RW-03) gets one such finding from UCB's release; no other asset does.
- **K1 amendment (during build).** The value is named MARKETED_NO_US_STATEMENT: 'Approved in China' states a jurisdiction, just not the U.S.
- **A5 review amendments (independent AI code review, before commit).** K1 rewritten clause by clause:
  the U.S. must be named in the same clause as a product approval; IND, designation, protocol and
  trial approvals do not count; negation and hedges are per clause; lowercase "us" is not the U.S.
  K2 rewritten clause by clause with more phrasings ("received FDA approval", "U.S. approval of X",
  "approved in the U.S.", "approved by the EMA and FDA"); hedges checked only inside the approval
  clause; "expected", supplemental and sBLA/sNDA approvals excluded. Disclosed consequence (criteria
  correction): once a human confirms a K2 finding, the asset's activity becomes MARKETED, which no
  longer counts as "active development" in the buyer's ranking preference; this follows the buyer's
  declared rule and is pinned by a test. Stage 6 without market evidence reads "Phase 4 or marketed
  (no market evidence in source)".

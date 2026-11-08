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
   source statement; silence is UNKNOWN. An imported deals/rights export gives each program a
   cited rights position in the buyer territory (licensed, optioned, shared, returned,
   conflicting, ...) with diligence questions; absence of a deal is never availability.
4. **Queues** unknowns, conflicts, shared codes and agent proposals for an analyst. Each UNKNOWN
   gate on a program that is not excluded carries a diagnostic (cycle U1): what the record holds,
   as written, and the one cited fact that would decide the gate. It never changes a gate.
5. **Records** analyst decisions in a hash-chained, append-only log. Finalists exist only
   through explicit, attributable approvals.
6. **Hands up to three selected finalists to valuation** through BVE's own CLI and reads back
   the saved `valuation.json`. Missing financial inputs give NOT READY FOR VALUATION.
7. **Writes** a 9-sheet companion workbook and a one-page memo.

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
                                     workbook (9 sheets) + memo ◄──┘ (numbers copied, never recomputed)
```

| Module | Role |
|---|---|
| `bve.dealscreen.mapping` / `importer` | Profiles, CSV/XLSX import, row accounting, manifest |
| `bve.dealscreen.identity` | Shared-code and proposed-merge flags (the IL3RA MB-102 regression lives here) |
| `bve.dealscreen.facts` | Claims → `NormalizedFact`; unreadable → no fact; disagreement → contradicting claims |
| `bve.dealscreen.screening` | Runs `GateEngine`, declared lexicographic preference ranking, funnel |
| `bve.dealscreen.commercial` | Rights status, kept independent of science |
| `bve.dealscreen.rights` / `rights_territory` | Deals/rights export import (profile, rejected rows, dates with precision); territory and party-name reading |
| `bve.dealscreen.rights_ledger` / `rights_position` / `rights_model` / `rights_checks` / `rights_words` | Event replay per program; rights position; company, completeness and staleness checks; wording |
| `bve.dealscreen.rights_gate` / `rights_reader` | The top-tier gate on both paths: every U.S.-rights statement and holder read, rights rows not applied guard the programs they may concern; the strict text reader |
| `bve.dealscreen.transaction` | Buyer-declared transaction tiers (separate from science) |
| `bve.dealscreen.indication_relations` / `diagnostics` | Cycle U1: a class per UNKNOWN gate from the NCIt authority, the target and modality readers and the buyer's requirement; the record as written; the deciding fact |
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
bve-dealscreen decide  --workspace $W --action RESOLVE_IDENTITY_FLAG --subject idflag:<id from queue> \
    --new-state SAME_MOLECULE --reviewer jdoe --rationale "RVT-1401 is the former code"
```

Rights evidence and the transaction view (cycle R1). Rights come from a separate deals/rights export.
They are never read from the landscape's sponsor, labeler or collaborator columns:

```bash
bve-dealscreen import-rights --workspace $W --rights deals.csv --profile rights_profile.yaml
bve-dealscreen screen        --workspace $W      # re-screen to apply
# a quote the template reader does not accept blocks a clear position; the workbook's rights evidence lists the
# row's event id. A human who has read the source confirms the row and must state --reviewer-kind HUMAN (an
# AI-prepared decision is rejected, and so is any confirmation from a shell an AI agent runs). DealScreen cannot
# verify that the reviewer is a person. A re-import of the unchanged row keeps the confirmation; a change voids it
bve-dealscreen decide        --workspace $W --action CONFIRM_RIGHTS_ROW --subject rx:<event id> \
    --new-state CONFIRMED --reviewer jdoe --reviewer-kind HUMAN \
    --rationale "read the release; it restates the license"
```

The profile maps the vendor's columns to `deal_id`, `external_id`, `event_type`, `exclusivity`, `grantee`,
`grantor`, `territory`, `event_date`, `status`, `related_deal_id`, `source_reference`, `evidence_quote` and
`source_date`; `deal_id`, `external_id`, `event_type` and `source_reference` are required. It also maps the
vendor's labels to canonical event types (`LICENSE`, `OPTION`, `OPTION_EXERCISED`, `OPTION_LAPSED`,
`CO_DEVELOPMENT`, `CO_PROMOTION_OPTION`, `ACQUISITION`, `TERMINATION`, `RIGHTS_RETURNED`,
`AVAILABILITY_STATED`), statuses and exclusivity. An unknown label rejects the row; it is never guessed.
Every event keeps the file hash, row, URL, quote and dates, with their precision ("2024" is a year, not
1 January). Example: `research/dealscreen_rights_v1/inputs/`.

Per program and buyer territory, the events are replayed in date order into a rights position:

| Position | Meaning |
|---|---|
| `CONFLICTING_EVIDENCE` | Records disagree: two exclusive holders, availability beside an active grant, an outcome that matches no grant, an outcome and grant the dates cannot order, or an option both exercised and lapsed |
| `LICENSED_IN_TERRITORY_PER_EVIDENCE`, `OPTION_HELD_IN_TERRITORY_PER_EVIDENCE` | A third party holds a license or option over the territory. Every other grant over it is named too |
| `RIGHTS_SHARED_IN_TERRITORY_PER_EVIDENCE` | Co-development, exercised co-promotion or non-exclusive rights; both partners named |
| `GRANT_TERRITORY_UNSTATED` | An active grant whose territory text cannot be read with confidence (a possible encumbrance) |
| `AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED` | A dated, current source states availability or a partner search |
| `RIGHTS_RETURNED_PER_EVIDENCE` | The grant ended per source, including a return or termination recorded without its grant (no territory written means the whole deal). Not availability |
| `NOT_AVAILABLE_PER_SOURCE` | No rights record; the landscape or an analyst says the rights are not available. Treated like an encumbrance by `encumbered_rights` |
| `OWNER_ACQUIRED_PER_EVIDENCE` | The owner was acquired; no third-party grant recorded |
| `NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE` | Recorded grants cover other territories only. Not availability |
| `NO_RIGHTS_EVIDENCE` | No record. The registry sponsor is shown only as a first contact, never as the owner |

Optional buyer-declared preferences (a separate view; never changes a scientific gate, disposition or
scientific rank):

```yaml
transaction:
  marketed: exclude                 # exclude | deprioritize | ignore (U.S.-marketed per source)
  deprioritized_holders: [Example Pharma Inc]   # whole-word match on holders/owner per evidence, else the sponsor (flagged)
  encumbered_rights: deprioritize   # a license or option over the territory per evidence
  shared_rights: ignore             # co-development / co-promotion / non-exclusive
  returned_rights: prefer           # prefer | neutral: sort returned rights first within their tier
  territory: [US]                   # region codes (US, CA, EU, UK, JP, CN, HK, MO, TW, KR, ROW); anything else is refused
  max_evidence_age_days: 730        # older evidence (before the buyer's as-of date) is flagged stale
```

Transaction tiers, in rank order: `AVAILABILITY_STATED_UNVERIFIED`, `NO_THIRD_PARTY_GRANT_IN_EVIDENCE`,
`RIGHTS_UNRESOLVED`, `DEPRIORITIZED`, `EXCLUDED_BY_BUYER_PREFERENCE`. There is no `OPEN` tier, and no tier
says rights are available. Only the four clear positions (returned, not encumbered, owner acquired,
availability stated) can reach the first two tiers, and only when four checks pass on the records the position
rests on and on everything else in the program's record (`transaction.top_tier_blockers` lists each failure as
`check: detail`). The same gate (`rights_gate.reconcile`) runs whether the position comes from the rights file or
from the landscape's and analysts' U.S.-rights fields, and anything it cannot read blocks:

- **complete**: every outcome is attached to its grant and explained; no rights row for the program was rejected
  at import; no rejected row names a program id that matches no program (such a row keeps every program out); no
  row, applied or not, has a program id close to this program's ("AB 24", "AB-024", "AB-24 (ADC)", "AB-24A" or
  "ABDN-24" beside "AB-24"); no unattached row whose id is close to no program names this program's company as a
  party; an acquisition alone is not enough;
- **specific**: the grants name licensor and licensee; an ending that names only the licensor is linked to its deal
  by id; a return or termination recorded without its grant names both parties and a territory covering the
  buyer's. The licensor the position rests on, the party that states availability and the recipient of a return
  must be the program's company per the landscape, or a party linked to it by an acquisition in the rights file
  (its acquirer, a company it acquired, or another company of the same acquirer); otherwise the question is "Does
  X own this program, or hold it under a license from Y?";
- **current**: each record has a date of its own (event date, else report date, read as the start of its period)
  within `max_evidence_age_days` of the buyer's `as_of_date`; acquisitions and later reports never refresh it;
  records and statements dated after the as-of date are not applied, nor is a status ("terminated", "expired")
  reported in a source dated after it; a status with no source date blocks, because nothing places it before the
  as-of date. An ending or acquisition dated only to a year or month that contains the as-of date is not applied
  and blocks, with a question asking for the day. A company's deal row for another program guards this program only when its territory is unreadable
  or overlaps the buyer territory. When an availability statement decides the position, every grant that ever
  covered the territory must have ended, by a dated record of its own, before the statement; an ending stated only
  by a status flag does not qualify. An acquisition with no date of its own is not applied;
- **uncontested**: every landscape and analyst U.S.-rights statement, every named U.S. holder, and every
  Partnerships and Geographic Notes value is read, for every buyer territory. A contrary statement, or a holder who
  is neither the company nor the owner per evidence, makes the position `CONFLICTING_EVIDENCE` and is cited. Any
  other rights text passes only if every clause is a plain form (`rights_allow`): a placeholder or no-grant phrase
  ("unpartnered", "not licensed in the U.S."); a plain offer by the company, with no digits, no "to …" and no other
  party ("U.S. rights available", "Ex-China rights available", "seeking a co-development partner"); the company
  keeping the rights ("rights retained", "wholly owned by Acme Bio", "Acme Bio retains all rights outside Greater
  China"); a return to the company dated by the as-of date; a grant over named places none of which is in the
  buyer territory ("licensed in Greater China" for a U.S. buyer, but not "licensed in Europe" for an EU buyer).
  Places are read as written, so "U.S." inside a party's name counts. A clause with a note in parentheses or
  brackets, or (in a text of several clauses) a pronoun as its subject, is not a plain form; nor is a text the
  reader cannot read, unless it says the company keeps its rights. Anything else blocks, quoted, with a question. A
  Partnerships value that only names organisations is not rights evidence; one with ownership words ("owned by",
  "bought by", "subsidiary of") is. In a grant over other places the party must be a name and nothing else
  (capitalised words and corporate punctuation, with no joining, place, area, condition or rights word in any letter
  case, and only legal forms after the last company word; "… to Acme Pharma and in the Americas to Beta Bio",
  "… TO ACME PHARMA AND ELSEWHERE TO BETA BIO" and "… Beta Bio Everywhere Else" are not names). An offer that names
  places must cover the buyer territory. A rights row's own quote is read: a leading "Name:" is dropped only when the
  name is the row's grantor or the company; an availability row's quote must be a plain form. Beside a clear
  position every applied rights row of the program is cited and its quote read, whatever the row's own territory.
  Every character of the quote is read: typographic quotes, dashes, spaces and marks are written in ASCII, and any
  other non-ASCII text (Chinese, full-width letters) blocks, quoted, and so does a question mark. A leading dateline
  (a city on the first line, of one word or from a list of multi-word cities, region parts that are U.S. states,
  provinces or countries, a full date and a known wire), an exchange
  note "(Nasdaq: ACME)", a "said <person>, <title> of <known party>" attribution, an adviser clause of a known party
  and a closing "<Name> has learned" are removed first; a removed name may not contain a rights, template or place
  word. A clause then passes only when it is one of a few fixed sentences for its row's type, read as a whole
  (`rights_template`, `rights_quote`); the plain-form reader is not used on quotes:
  - the row's own parties in their own roles (the grantor grants or regains, the grantee receives, returns or lets
    an option lapse). A party name may carry legal and business words ("Acme Pharma Co., Ltd."), never "Holdings",
    "Group", "International" or a place word: "Acme Holdings" is another company. Any other name blocks;
  - the program by one of its own names, optionally with a description made only of drug-development words and
    lower-case or symbol words from its own target, mechanism, modality, therapeutic area and indication fields
    ("NB-7, an anti-CLDN18.2 ADC for gastric cancer"). A capitalised word is never a description, and a field cannot
    add a connective, a place, a rights word, a condition ("after", "following", "prior") or a holder word
    ("co-owned", "licensee"), in any hyphen part;
  - the row type's verb: a grant in the past or present ("licensed", "grants", "obtained"); an ending or return
    ("terminated", "returned", "reverted", "regained"); a lapse ("lapsed unexercised", "did not exercise"); an
    acquisition only when completed ("acquired", "completed its acquisition of"). No modal ("may", "will"), no "has"
    as a holding verb, no negation, no sale or transfer, no condition ("after", "following", "upon");
  - a place, inside the row's own territory. A grant, an option or an exercise must name one unless the row covers
    the buyer territory ("the sole rights to NB-7" alone reads as the whole program); "an option to acquire NB-7"
    is no option sentence. "all rights" only when the row covers the buyer territory. Only a license ends a license:
    "terminated the option agreement" does not;
  - the one sentence that keeps rights with a party: "<grantor> retains (all) rights (to NB-7) (outside mainland
    China)", with the grantor named; never "it", "we" or "the company". It counts only when the grantor is the
    program's company and the places it names include the buyer territory ("outside the United States" blocks);
    with no place only as "all other rights"; never "will retain" or only development or commercial rights;
  - payment sentences between the row's parties ("will pay … an upfront payment of $20 million", "is eligible to
    receive up to $200 million in milestones");
  - an optional date with a year (a capitalised month, so "may" is never a month), whose period ends on or before
    the as-of date or holds the row's own date; an optional amount.
  Anything else blocks, quoting the clause, with a question. A human analyst who has read the source can then record
  `CONFIRM_RIGHTS_ROW` for the row's event id (listed in the workbook's rights evidence) with `decide
  --reviewer-kind HUMAN`. An AI-prepared or synthetic decision is rejected, and the decision log refuses a
  confirmation in a shell run by a known AI agent (`CLAUDECODE` and similar are set, even to an empty string), from
  the CLI or the Python API. DealScreen cannot verify that the reviewer is a
  person; the output says who confirmed and that the kind is as recorded. The confirmation is tied to a hash of the
  row's program, deal, fields and quote, so a re-import of the unchanged row keeps it and a change voids it;
  `WITHDRAWN` removes it and every earlier version of it; a withdrawal with nothing to withdraw is refused. Most real press wording still blocks before confirmation (15 of 17 real CLDN18.2 quotes,
  read directly).

  A grant in the buyer territory
  dated after the as-of date, including an option exercise, blocks unless its source date shows it was reported after
  the as-of date. An acquisition counts for the owner only when the acquired party is the same legal entity as a
  party to a recorded grant, the acquirer of one, or the company itself ("Acme Holdings", "Acme Bio Group", "Acme Bio
  US" and the company buying another company do not count); otherwise it blocks. Two different acquirers of one
  party are contested: neither row is applied, and both are cited with a question. An availability
  statement dated only to a year or month that contains the as-of date blocks. When rights rows are recorded but none
  gives a position on the as-of date, the position says so (`RIGHTS_ROWS_NOT_APPLIED`, never "no rights evidence"). A note in parentheses
  or brackets beside the company name, a rights row's grantor or grantee, or a holder blocks, the note is quoted,
  and the noted name is not shown as holder or owner (a place inside a legal name before its corporate form, as in
  "Acme Bio (Basel) Co., Ltd." or "Acme Bio (Hong Kong) Limited", is not a note). An analyst availability statement counts only with a source date within
  the age limit, and is cited. A landscape "available" cell is never counted.

Statements are read by a strict reader (`rights_reader`). The text is split into clauses (";", sentence ends,
"but", "however", "whereas", "although"); each clause is an offer, a contest (not available, licensed, optioned,
returned), consistent text, or not read. A statement reads as available only when every clause is read and one
offers rights in a place that covers the U.S. Negations ("No U.S. rights available", "Available - no"), other
places ("Available in Latin America"), hedges, future and questions ("May be available", "Available from 2027",
"Available?"), dates ("Available 2H26", "post-2026") and offers by or to another party ("The licensee is seeking
a partner", "Available to licensee") never read as available. `assert` prints how it read a U.S.-rights,
Partnerships or Geographic Notes value and whether the gate accepts it as a plain form, so an analyst can reword one
that is not read as meant; the verdict is the gate's own, for the workspace's buyer territory and as-of date. The
landscape's U.S.-rights fields are read for any buyer territory that contains the U.S.; for a wider territory a
clear U.S. position is not a clear position there, while a U.S. encumbrance keeps its effect.

A failed check keeps the program in `RIGHTS_UNRESOLVED`, with "not counted for the top tiers: …" and a question
naming what record would settle it. Program ids in the rights file match the landscape without regard to case or
surrounding spaces. Rows that attach to no program, and rejected rows whose id matches no program, are listed with
their type, date, parties and territory in the memo, the Diligence sheet (`RIGHTS_ROW_NOT_ATTACHED`,
`RIGHTS_ROW_REJECTED_NO_PROGRAM`) and `screening.json` (`rights_import_issues`); each program they hold back lists
them under `rights_rows_not_applied`. Party names are compared by company: corporate suffixes, business-line and
country words ("Acme Pharma US, Inc.") and notes in parentheses are ignored, and so is an address written after the
corporate form when each part of it is one word and the last is a country ("Acme Bio Co., Ltd., Lakeside, China");
any other word ("Acme KGaA") makes a different company. The Screening sheet shows, per program: the position, the
holder and owner per evidence, each cited event (rights row, date, type, parties, territory, URL, quote up to 1,000
characters, event id), the stale flag, the blockers and the diligence questions. The memo shows the top ten in words,
with up to three cited events each (rights row and quote) and their questions, and gives every other program with
evidence its position, holder, newest evidence date, the first reason for the position, the first check that keeps
it out of the top tiers, how many more reasons the workbook holds, and its rights rows. Its rights summary is
computed: positions and tiers in words with counts, and how many programs have availability stated and how many of
those pass every check.

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
3. **A rights and ownership evidence workflow.** Cycle R1 added the import and the rights
   ledger. What remains: a licensed deals export as the source (the R1 test file is a hand
   transcription of 27 public quotes, so its recall is limited), analyst confirmation of
   individual rights events, and a re-check when evidence turns stale.

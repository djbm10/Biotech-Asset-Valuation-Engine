# Response to the R1 adversarial review (REVIEW.md)

Cycle R1, revision 2. The fixes are on `dealscreen-mvp` after e805f0b. Every fix has a regression test in
`tests/dealscreen/test_rights_evidence.py`; the test name is given per row. Outputs regenerated in
`after_v2/` (CLDN18.2 screening, CSV, workbook, memo). Science unchanged: 0 of 62 scientific fields
changed versus the frozen baseline (`compare.py`), and the cycle-4 equivalence harness is byte-identical
on all four workspaces.

This file is written by the implementer, not by the reviewer. It claims nothing about whether the fixes
are adequate; a fresh adversarial re-review checks that (`REREVIEW.md`).

## 1. Ranked issues

| # | Finding | Response | Test |
|---|---|---|---|
| 1 | `parse_territory` subtracts every region on any exclusion word (T1–T4) | **Fixed.** An exclusion subtracts only from its own base (the words before it); a base with no region (`ex-Greater China`) is the world; any unknown word (`Mexico`, `Puerto Rico`, `Asia`, `co-promotion retained`) makes the whole text unreadable (`None`), which the ledger treats as a possible encumbrance (`GRANT_TERRITORY_UNSTATED`), never as "not covered". Lowercase `us` is not the U.S.; a second `;` clause makes the text unreadable. Module: `rights_territory.py`. | `test_territory_phrasings`, `test_unreadable_territory_is_none`, `test_unreadable_territory_is_a_possible_encumbrance_not_no_obstacle` |
| 2 | Clearing events ignore date order and territory (L1–L3) | **Fixed.** Events replay in date order; an outcome must match exactly one live grant (by deal id, then named party, then licensor) or nothing is cleared; a territorial termination subtracts only its regions; exercise + lapse on one option is a conflict. | `test_l1_…`, `test_l2_…`, `test_l3_…`, `test_termination_linked_by_deal_id_clears_regardless_of_name` |
| 3 | Registry sponsor used as `originator` inside `rights_position` | **Fixed.** The parameter is gone. The sponsor appears only as "first contact: registry sponsor '…' (not evidence of ownership)" in a question. Owner = root licensor of the recorded grants, or the acquirer in a recorded acquisition. | `test_sponsor_is_never_an_input_to_the_position`, `test_acquisition_of_the_owner_changes_the_owner_and_is_not_a_third_party_grant` |
| 4a | Givastomig drops I-Mab (R12 roles invented) | **Fixed.** R12 now records the two partners of a co-development, not licensor and licensee; a co-development names both holders ("I-Mab and ABL Bio (shared)") and asks whether a transaction needs both. Evidence lines word it "partners I-Mab and ABL Bio". | `test_co_development_names_both_partners` |
| 4b | LM-302 (#1) names defunct Turning Point | **Not fixed, labelled.** No quote in the frozen library states that Bristol Myers Squibb succeeded Turning Point, so the BMS termination and return cannot be linked to the Turning Point grant without inventing a fact. The holder now reads "Turning Point Therapeutics (recorded; conflicting)", the position is `CONFLICTING_EVIDENCE`, and the question is "Is Bristol Myers Squibb the successor of Turning Point Therapeutics? If so, the grant has ended: record the acquisition or link the deal id." One recorded acquisition row would resolve it to `RIGHTS_RETURNED` (tested: `test_recorded_acquisition_of_licensee_links_the_return`). AC13's "LM-302 returned" is **not met**. | — |
| 5 | Recall capped by the library (SKB315 return missed) | **Not fixed.** The return is not in the frozen library. DealScreen reads rights only from an imported rights file; adding it would need a new sourced row. SKB315 stays `NO_RIGHTS_EVIDENCE` with a first-contact question. This is the main measured gap versus general Claude. | — |
| 6a | Memo summary contradicts the evidence | **Fixed.** The summary counts positions from the rights evidence when any was imported. | memo regenerated |
| 6b | Duplicate Diligence rows (old `us_rights UNKNOWN` + new `RIGHTS`) | **Fixed.** One `COMMERCIAL / rights` row per program; its status reads "landscape rights field: … \| rights position per evidence: …"; the column is "Question state" so "OPEN" cannot be read as a rights state. | workbook regenerated |
| 6c | Duplicated memo reasons | **Fixed.** | `test_reasons_not_duplicated_when_deprioritized` |
| 6d | Staleness anchored to the rights file's latest date | **Fixed.** Measured from the buyer's analysis date. Revision 2 also measures evidence age from the source date (when the evidence was stated), else the event date. | `test_staleness_is_measured_from_the_analysis_date`, `test_staleness_uses_the_source_date_when_given` |
| 6e | IBI343's correction visible only in CSV/workbook | **Fixed.** The memo lists rights evidence for every program not in the top-10 transaction list, including eligible programs ranked lower (XNW27011) and unresolved ones (IBI343). | memo regenerated |

## 2. Adversarial inputs (section 3 of the review)

| Case | Before | Now |
|---|---|---|
| T1 `North America excluding Mexico` | NOT_ENCUMBERED (false no-obstacle) | GRANT_TERRITORY_UNSTATED, asks which territories |
| T2 `US, excluding Puerto Rico` | NOT_ENCUMBERED | GRANT_TERRITORY_UNSTATED |
| T3 `worldwide, including the US but excluding China` | US not covered | all but CN → LICENSED |
| T4 `Worldwide other than Japan; US co-promotion retained…` | US not covered | unreadable → GRANT_TERRITORY_UNSTATED |
| T5 `Asia ex-Japan` | US covered | unreadable → GRANT_TERRITORY_UNSTATED |
| T6 `Europe and Japan, excluding the UK` | US covered | {EU, JP} → NOT_ENCUMBERED for a U.S. buyer |
| T7 `rights for use by us in China` | {CN, US} | unreadable → GRANT_TERRITORY_UNSTATED |
| T8 `EU5` | {EU, UK} | **kept** {EU, UK}: EU5 is France, Germany, Italy, Spain and the UK |
| L1 undated termination vs later re-license | RIGHTS_RETURNED | LICENSED; "Which of the grants to A did the termination end?" |
| L2 Japan-only termination | RIGHTS_RETURNED | LICENSED (US still held) |
| L3 undated exercise + dated lapse | RIGHTS_RETURNED | CONFLICTING |
| L4 undated acquisition of a China-only licensee | encumbered | NOT_ENCUMBERED |
| L5 licensor acquired | CONFLICTING | LICENSED to A; owner BigCo |
| L6 sublicense A→B | CONFLICTING | LICENSED; holder B "holds a sublicense from A" |
| L7 termination naming only the licensor | CONFLICTING | RIGHTS_RETURNED (single grant from that licensor) |
| P1 declared `Merck` | matched Merck KGaA silently | still matches by name; a note reports "declared counterparty 'Merck' matches different companies (…); declare the full name if only one is meant" |
| P2 `Bristol-Myers Squibb` vs `Bristol Myers Squibb Company` | no match | match (punctuation and corporate suffixes ignored) |
| Non-exclusive worldwide license | LICENSED | RIGHTS_SHARED (holder and licensor) |

## 3. Additional defects found by the implementer before re-review (revision 2)

Found by re-running the adversarial script and reading the regenerated outputs. Same class of failure as
L1–L3 (event order) and section 4 (output honesty).

| # | Defect | Fix | Test |
|---|---|---|---|
| S1 | "2024" was stored as 2024-01-01 and shown as a precise day | Dates keep their precision (day, month, year) from the profile's format; evidence shows the date as written plus the source date | `test_coarse_dates_are_shown_as_written_not_as_the_first_day`, import test |
| S2 | A grant and an outcome in the same period were ordered by their first day, so a same-year termination could clear a later grant | A grant applies at the start of its period, an outcome at the end; when their periods overlap the grant is kept and the evidence is CONFLICTING with "the dates cannot order them" | `test_outcome_and_grant_in_the_same_period_cannot_be_ordered` (both directions), `test_coarse_outcome_after_the_grant_period_still_clears` |
| S3 | A termination dated before every grant to the same party asked "Is A the successor of A?" | Read as ending an earlier deal: reported with "Which deal did … end?", the later grant stands | `test_outcome_dated_before_every_grant_to_that_party_ended_an_earlier_deal` |
| S4 | An outcome linked by deal id to a deal dated after it was silently unmatched | CONFLICTING: "Which date is wrong?" | `test_outcome_linked_to_a_later_deal_is_a_conflict` |
| S5 | An availability statement made before a later license was a "conflict" | Superseded by the later grant (reported); a statement after the grant still conflicts | `test_availability_statement_superseded_by_a_later_grant` |
| S6 | One undated availability statement voided a dated, current one | Availability counts when at least one statement is dated and current | `test_one_fresh_dated_statement_counts_even_with_an_undated_one` |
| S7 | Availability with no territory was shown without comment | Reason "the statement does not name a territory" + "Which territories are offered?" | `test_availability_without_a_territory_asks_which` |
| S8 | A second grant over the territory (e.g. an option to a large pharma beside a license to a small biotech) was hidden behind the deciding grant | Every grant over the territory is named with its holder; its holders count for the buyer's deprioritized-holder preference; each option gets its own exercise question | `test_every_grant_over_the_territory_is_reported` |
| S9 | Option holders were asked whether they would "sublicense or transfer" | Options get only the exercise/lapse question | `test_option_questions_ask_about_the_outcome_not_a_sublicense` |
| S10 | Reasons printed codes ("rights_returned") and "X from Y" for terminations and acquisitions | Event words ("rights return"); parties worded per type ("licensee …, licensor …", "X acquired Y", "partners X and Y") | `test_reasons_use_words_not_codes` |
| S11 | Landscape AVAILABLE + evidence encumbrance → CONFLICTING with no question | Holder "… (recorded; conflicting)" and "Which is current: the landscape's availability statement or the grant to …?" | screening |
| S12 | Memo repeated one long no-record question 7 times; "0 of 0 listed programs (none is analyst-confirmed)" was contradictory when some were confirmed | One compact line per no-record program with its first contact; one shared explanation; "Investigate next" names programs with conflicting evidence | memo regenerated (1,142 words, was 1,380) |

## 4. Measured CLDN18.2 outcome (15 programs with a recorded deal or ownership event)

Scored by the implementer against `research/dealscreen_comparison_v1/reference/reference_calls.csv`, with the
reviewer's categories. Not an independent score; the re-review re-scores it.

| Program | Reference | R1 (e805f0b) | R1 revision 2 |
|---|---|---|---|
| CL-01 Zolbetuximab | Astellas owns (Ganymed acquisition) | "acquired by third party" label | OWNER_ACQUIRED, Astellas — right |
| CL-02 IMAB362 | Astellas | same label error | OWNER_ACQUIRED, Astellas — right |
| CL-03 AZD0901 | AZ global | LICENSED AZ, stale | same — right |
| CL-04 CMG901 | AZ global | LICENSED AZ, stale | same — right |
| CL-05 Sonesitatug vedotin | AZ global | sponsor-matched DEPRIORITIZED, no record | same; identity flag to AZD0901 — partial |
| CL-06 IBI343 | Takeda ex-Greater China | LICENSED Takeda | same — right |
| CL-07 LM-302 | returned by BMS; LaNova / Sino Biopharm | CONFLICTING, holder Turning Point | CONFLICTING, "(recorded; conflicting)", owner LaNova, successor question — partial |
| CL-08 SHR-A1904 | Merck KGaA option, outcome unknown | OPTION_HELD, stale | same, exercise question — right |
| CL-11 XNW27011 | Astellas ex-Greater China | LICENSED Astellas | same, now also in the memo — right |
| CL-13 Givastomig | I-Mab + ABL Bio equally | ABL Bio only | SHARED, I-Mab and ABL Bio — **right (was partial)** |
| CL-14 EO-3021 | Elevation licensed; status unclear | LICENSED, stale | same — partial |
| CL-15 SYSA1801 | same | LICENSED, stale | same — partial |
| CL-26 RC148 | AbbVie ex-Greater China | LICENSED AbbVie | same — right |
| CL-27 SKB315 | MSD returned global rights to Kelun | NO_RIGHTS_EVIDENCE | same — **missed** |
| CL-30 FL-301 | Flame/Leap ex-China, status unclear | wrong territory reading | LICENSED to Leap (via recorded acquisition of Flame) over "territories excluding China", stale — right |

| | R1 (reviewer's count) | R1 revision 2 (implementer's count) | General Claude B (reviewer's count) |
|---|---|---|---|
| Right | 9 | 10 | 14 |
| Partial | 5 | 4 | 1 |
| Missed | 1 | 1 | 0 |
| False "unobstructed" | 0 (baseline 4) | 0 | — |
| Wrong holder | 3 | 0 definite; LM-302 holder shown as "recorded; conflicting" | — |
| Wrong territory reading | 1 | 0 | — |

General Claude B still makes more correct rights calls (14 v 10). It searched beyond the 27-quote library.
DealScreen's calls are only as complete as the imported rights file. Its advantages are auditability
(every call cites a row, quote, URL and date), explicit staleness, specific questions, and never turning
"no record found" into "unencumbered". None of this is a validation or a claim of competitive advantage.

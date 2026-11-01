# Adversarial review: cycle R1 rights evidence (CLDN18.2)

AI-SIMULATED INTERNAL REVIEW. I play a skeptical pharma BD analyst and auditor. I am not a human approver and
approve nothing. I review commit e805f0b on `dealscreen-mvp`. I did not edit `src/` or `tests/`. The adversarial
script is `/tmp/claude-1000/rr/adv.py`; every output quoted under §3 comes from running it.

## 1. Transcription fidelity (`inputs/rights_cldn18.csv` vs quotes)

The skip list is sound. All 11 skipped library items (4, 9, 15, 20, 36, 43, 56, 57, 59, 71, 77) are payment terms
or a duplicate (item 57 duplicates 58). None states a rights event. The `assert lic == covered` in
`build_rights_file.py` guarantees no licensing item was silently dropped.

| Row | Finding | Severity |
|---|---|---|
| R01/R02 | The quote says Astellas acquires Ganymed's *equity*. Linking IMAB362 to Ganymed relies on library item 4, not on this quote. The Deal Date is blank and only the Source Date (2016-10) is used. | low |
| R05 | Exclusivity is left blank, which is correct: the Takeda quote does not say "exclusive". Faithful. | ok |
| R07 | The quote names BMS, which is right. But the row has no date and no `Related Deal` link to R06 (Turning Point). The BMS–Turning Point succession is not in any quote, so the engine cannot connect the two (see §2). | medium (consequence) |
| R08 | Source 2025-07 says "handed back rights **last year**". Deal Date is blank, so the event is dated 2025-07 when the return happened in about 2024. The URL headline ("LaNova bought [by] Sino Biopharm") describes an acquisition of the licensor, which is **not transcribed**. Only the URL slug supports it, not the quote, so skipping it is defensible. But the current owner of the returned rights is then lost. | medium |
| R10 | The quote says "an option to **co-promote** … in mainland China". It is coded `Option`, which reads as an option on rights, with Territory = mainland China. Co-promotion is not a rights option. No effect for a US buyer. | low |
| R12 | Coded `Co-development` with Licensee = ABL Bio and Licensor = I-Mab. The quote says neither party licenses to the other: "I-Mab is the lead party and shares worldwide rights … equally with ABL Bio". The licensor/licensee roles are **added**. The output then names ABL Bio as sole holder and drops I-Mab, the lead party. | **high (wrong holder)** |
| R16 | Deal Date blank (the exhibit is 2023-01). The territory "territories excluding China" is verbatim. | low |
| R03/R04, R13/R14 | The same deal is duplicated across alias records (AZD0901/CMG901, EO-3021/SYSA1801). Faithful. | ok |

Net: 0 invented deals, 0 licensing quotes wrongly skipped, 1 role assignment the quote does not support (R12),
1 event-type stretch (R10) and 2 date fields that lose information (R07, R08).

## 2. Were the misleading rankings corrected? (baseline vs after)

| Program | Baseline | After | Reference (`reference_calls.csv`) | Verdict |
|---|---|---|---|---|
| IBI343 | OPEN, unresolved #1 | DEPRIORITIZED, LICENSED, Takeda | Takeda ex-Greater China | **fixed** |
| SHR-A1904 | OPEN, txn #3 | DEPRIORITIZED #10, OPTION_HELD, Merck KGaA, stale | Merck KGaA option | **fixed** |
| RC148 | OPEN | DEPRIORITIZED, LICENSED, AbbVie | AbbVie ex-Greater China | fixed |
| XNW27011 | DEPRIORITIZED (sponsor match) | DEPRIORITIZED, LICENSED, Astellas per evidence | Astellas | now evidence-based |
| FL-301 | OPEN | DEPRIORITIZED, ACQUIRED, Leap, stale | Flame/Leap ex-China | right holder, **wrong territory reading** (see below) |
| Givastomig | OPEN | DEPRIORITIZED, SHARED, "ABL Bio" | I-Mab + ABL Bio equally | **wrong holder** (I-Mab omitted) |
| LM-302 | OPEN #1 | RIGHTS_UNRESOLVED #1, CONFLICTING, holder "Turning Point Therapeutics" | returned; LaNova/Sino Biopharm | not false availability, but **wrong holder**; AC13 "returned" not met |
| EO-3021 / SYSA1801 | OPEN | DEPRIORITIZED, LICENSED, Elevation, stale | returned, unclear (discontinued) | **possible false encumbrance**; stale flag mitigates |
| AZD0901 / CMG901 | DEPRIORITIZED (sponsor) | DEPRIORITIZED, LICENSED AZ, stale | AZ global | ok |
| Zolbetuximab / IMAB362 | EXCLUDED / DEPRIORITIZED | same, `ACQUIRED_BY_THIRD_PARTY`, Astellas | Astellas owns | label error: Astellas *is* the sponsor ("Astellas Pharma US, Inc." ≠ "Astellas" in `party_key`) |
| SKB315 | OPEN #7 | RIGHTS_UNRESOLVED #6, NO_RIGHTS_EVIDENCE | **MSD returned global rights to Kelun (2024)**; reference #1 | missed (not in the library) |
| Sonesitatug, ASP2138, ASP546C, AZD5863, AMG 910, rilvegostomig, volrustomig | DEPRIORITIZED (sponsor) | same, NO_RIGHTS_EVIDENCE + "not a rights statement" | large pharma | ok, honestly labelled |
| Zanidatamab | OPEN | RIGHTS_UNRESOLVED, NO_RIGHTS_EVIDENCE | Jazz (US) | third-party-held but no evidence; scientifically excluded |
| 34 other no-deal programs | OPEN | RIGHTS_UNRESOLVED, NO_RIGHTS_EVIDENCE | mostly unknown | correct honesty |

Counts against the reference:

| Error class | Baseline | After |
|---|---|---|
| False "unobstructed" (active third-party US rights shown OPEN or non-deprioritized) | 4 definite (IBI343, SHR-A1904, RC148, FL-301), plus Zanidatamab | **0 shown as available**. Zanidatamab sits in RIGHTS_UNRESOLVED for lack of a record, which is honest. |
| False encumbrance | 0 (no evidence was used) | 0 definite; 2 likely outdated (EO-3021/SYSA1801, flagged stale) |
| Wrong holder | n/a | 3: LM-302 (defunct Turning Point), givastomig (I-Mab dropped), zolbetuximab labelled "third party" |
| Wrong territory reading | n/a | 1: FL-301. Leap holds Flame's **ex-China** license. Because the registry sponsor Flame is treated as `originator`, the acquisition is read as "everything held, territory not stated", which includes China, where NovaRock holds rights. |

## 3. New errors (adversarial inputs to `parse_territory` / `rights_position`)

Buyer territory is {US}. The "Actual" column is copied from script output.

| # | Input | Actual | Expected | Impact |
|---|---|---|---|---|
| T1 | `"North America excluding Mexico"` | US **not** covered → `NOT_ENCUMBERED_IN_TERRITORY` | US, CA | **false no-obstacle**. The tier becomes NO_OBSTACLE_IN_RIGHTS_EVIDENCE and ranks *above* unresolved programs. |
| T2 | `"US, excluding Puerto Rico"` and `"United States (excluding its territories)"` | US not covered → NOT_ENCUMBERED | US | **false no-obstacle** |
| T3 | `"worldwide, including the US but excluding China"` | US not covered | all but CN | **false no-obstacle** |
| T4 | `"Worldwide other than Japan; US co-promotion retained by licensor"` | US not covered | all but JP; US shared | false no-obstacle |
| T5 | `"Asia ex-Japan"` | US covered | unstated or Asia | false encumbrance |
| T6 | `"Europe and Japan, excluding the UK"` | US covered, EU not | EU, JP | false encumbrance |
| T7 | `"rights for use by us in China"` | {CN, **US**} | CN | false encumbrance ("us" read as a word) |
| T8 | `"EU5"` | {EU, UK} | EU | minor |
| L1 | License to A (2020) → **undated** termination by A → re-license to A (2026) | `RIGHTS_RETURNED` | LICENSED to A | **false no-obstacle**. `_order` sorts undated clears last, so they clear later grants. |
| L2 | Worldwide license to A, then termination by A for **Japan only** | `RIGHTS_RETURNED` | LICENSED (US still held) | **false no-obstacle**: a clearing event's territory is ignored. |
| L3 | Option to A (2024) → **undated** OPTION_EXERCISED → OPTION_LAPSED (2025) | `RIGHTS_RETURNED` | LICENSED (the exercise preceded the lapse notice) | false no-obstacle. The output even says "option_exercised … matches no recorded grant". |
| L4 | China-only license to ChinaCo, then **undated** acquisition of ChinaCo by BigCo | `ACQUIRED_BY_THIRD_PARTY`, BigCo, covers US | NOT_ENCUMBERED (BigCo inherits CN only) | false encumbrance (an undated acquisition sorts first, so succession is missed) |
| L5 | Ex-China license to A, then acquisition of the licensor by BigCo | `CONFLICTING` (A vs BigCo) | LICENSED to A; BigCo is the new licensor | noisy |
| L6 | Licensee A sublicenses US to B | `CONFLICTING` | LICENSED (B, under A) | noisy; sublicensing is not modelled |
| L7 | Termination recorded with only the licensor named | `CONFLICTING` | RETURNED | conservative |
| P1 | Buyer lists `Merck` (meaning MSD) as a deprioritized holder | matches "Merck KGaA, Darmstadt, Germany" | no match | wrong counterparty |
| P2 | Buyer lists `Bristol-Myers Squibb`; the holder is "Bristol Myers Squibb Company" | no match | match | the C3 buyer worked around this by listing both spellings |
| OK | Non-exclusive worldwide license → LICENSED, which counts as encumbered (conservative). China-only option → NOT_ENCUMBERED. Termination by "Merck & Co" does not clear a "Merck KGaA" grant (it gives CONFLICTING). Availability statement plus a China-only license → AVAILABILITY_STATED_UNVERIFIED. | as designed | | |

Root cause of T1–T4: `parse_territory` treats *any* exclusion word as "REGIONS minus every region mentioned". It
does this even when there is no worldwide anchor, and even for regions the text explicitly includes. Unit tests
cover only "Rest of world excluding Japan" and "North America" (`tests/dealscreen/test_rights_evidence.py:42-43`).
No test combines a positive region with an exclusion. All 37 tests pass, so they do not detect T1–T4 or L1–L4.

## 4. Never implying availability; evidence and diligence questions (AC2, AC10, AC11)

- The `OPEN` tier is gone. None of the 62 rows in `after_transaction.csv` says open or available. 43 rows read
  "availability not evidenced". In the memo, "available" appears only in disclaimers.
- Every non-NONE position cites its rights row (`evidence_rows`), a quote, a URL and a date. This holds in the CSV,
  the Screening sheet (rights evidence column, e.g. the LM-302 three-event cell) and the memo bullets.
- Every row has at least one diligence question. IBI343 asks "Is the license to Takeda exclusive? The source does
  not say." SHR-A1904 asks whether Merck KGaA has exercised, declined or let the option lapse.
- **Inconsistencies remain**:
  - (a) The memo's "Rights are a separate question" paragraph still says "U.S. rights status is: unknown 14 … holder
    named for 0 of them". Two paragraphs later it names AstraZeneca, Merck KGaA and Turning Point from evidence.
  - (b) The Diligence sheet keeps the old `COMMERCIAL us_rights UNKNOWN "no rights record"` row next to the new
    `RIGHTS LICENSED_IN_TERRITORY … rx:…:5` row for the same program (IBI343, givastomig).
  - (c) Memo reasons are duplicated (the AZD0901 and SHR-A1904 reasons are printed twice).
  - (d) Staleness is measured against the rights file's latest date (2026-01-12), not the analysis date. AC7 says
    "relative to the analysis date" (`screening.py:258-259`).
  - (e) The memo lists only the ELIGIBLE transaction ranks, so IBI343's correction is visible only in the CSV and
    workbook.

## 5. Usefulness vs general Claude (run B)

I scored the 15 programs where the reference records a deal or ownership event: CL-01–08, 11, 13, 14, 15, 26, 27
and 30.

| | DealScreen R1 | B (`runs/B_general/calls.csv`) |
|---|---|---|
| Right | 9 (CL-01, 02, 03, 04, 06, 08, 11, 26, 30 holder) | 14 (all except CL-15, which is partial) |
| Partial | 5 (CL-05: tier right, no holder; CL-07: conflict flagged, wrong holder; CL-13: I-Mab dropped; CL-14/15: stale license shown, discontinuation unknown) | 1 |
| Wrong or missed | 1 (CL-27 SKB315, return missed) | 0 |

Where B is still better:
- **SKB315.** B: "Kelun-Biotech (Merck returned global rights Aug 2024)", shortlist #5. Reference #1. DealScreen has
  no evidence, so SKB315 sits at RIGHTS_UNRESOLVED #6.
- **LM-302.** B: "LaNova (acquired by Sino Biopharm 2025); BMS ex-China license terminated/returned". DealScreen
  names defunct Turning Point and calls the evidence a conflict.
- **Givastomig.** B: "I-Mab + ABL Bio share … equally". DealScreen names ABL Bio only.
- B also gives an owner for every no-deal program (e.g. "Junshi (no ex-China licence found)"). DealScreen says only
  NO_RIGHTS_EVIDENCE, which is honest but adds no BD value.

Where DealScreen is better:
- Every rights claim is tied to a verbatim quote, row, file hash and date. CRITIC_FINAL §4 found B had 2/8
  unsupported and 2/8 weak rights citations, including a paraphrase via search for SKB315.
- Staleness is flagged explicitly.
- Option status and exclusivity gaps become specific questions.
- Absence of a record is never turned into "found no licence ⇒ unencumbered". B's ATG-022 "unencumbered by search"
  is exactly that inference.
- DealScreen is reproducible, and it deprioritizes through the buyer's declared policy.

Net: on *correctness* of rights calls, B still leads, because it searched more widely than the 27-quote library.
On *auditability* and on not overclaiming, DealScreen leads. Its recall is capped by what is in the rights file.

## 6. Verdict per acceptance criterion

| AC | Verdict | Evidence |
|---|---|---|
| AC1 | PASS | Profile `inputs/rights_profile_cldn18.yaml`. `import_rights` rejects unknown type, status and exclusivity labels (`rights.py` import loop). Each event carries hash, row, URL, quote and date. |
| AC2 | PASS | No OPEN tier. NO_RIGHTS_EVIDENCE on all 49 no-record rows. Grep finds no availability claim. |
| AC3 | **PARTIAL** | Correct on the CLDN18.2 phrasings. **Fails held-out phrasings** T1–T4 (false NOT_ENCUMBERED) and T5–T7 (false encumbrance). Non-exclusive is shown as LICENSED, not "shared, flagged". |
| AC4 | PARTIAL | Works in a fixture. Gives a false RETURNED for an undated termination followed by a later re-license (L1) and for a partial-territory termination (L2). LM-302 is not RETURNED. |
| AC5 | PARTIAL | An exercise followed by a lapse resolves to RETURNED when the exercise is undated (L3). |
| AC6 | PASS (noisy) | Conflicts cite both events (LM-302). Over-fires on licensor acquisition and sublicensing (L5, L6). |
| AC7 | PARTIAL | Flags are present, but measured against the rights file's max date, not the analysis date (`screening.py:258`). |
| AC8 | NOT CHECKED | I did not re-run the equivalence harness. |
| AC9 | PASS | `TransactionPreferences` fields. The defaults return RIGHTS_UNRESOLVED, never availability. |
| AC10 | PARTIAL | Evidence is present in CSV, xlsx and memo. The memo's summary paragraph and the Diligence sheet's old `us_rights UNKNOWN` rows contradict it. |
| AC11 | PASS | Every row has a party- and territory-specific question where known. |
| AC12 | PASS | Grep of `rights.py` and `transaction.py` for CLDN18.2 company and program names finds none. |
| AC13 | **PARTIAL** | IBI343 and SHR-A1904 fixed. RC148, FL-301 and XNW27011 encumbered. **LM-302 is CONFLICTING, not returned.** |
| AC14 | FAIL as written | I found new error modes: L4 and T5–T7 give false encumbrance, and T1–T4 and L1–L3 give false no-obstacle. None occurs in the CLDN18.2 output. The CLDN18.2 output also has 3 wrong holders and 1 wrong territory reading. |

## Ranked remaining issues

1. **`parse_territory` subtracts regions on any exclusion word** (T1–T4). It produces NOT_ENCUMBERED, which ranks
   *ahead* of unresolved programs. That is the false-availability shape this cycle was meant to kill, now waiting
   for a vendor export phrased "US excluding Puerto Rico".
2. **Clearing events ignore date order and territory** (L1–L3). An undated termination or a partial return clears
   every grant to that party and gives RIGHTS_RETURNED (a no-obstacle tier).
3. **The registry sponsor is used as `originator` inside `rights_position`** (`screening.py:266`). This produces the
   FL-301 "all territories" reading and the "Astellas acquired by third party" label. It contradicts the stated rule
   that nothing is inferred from sponsors.
4. **Wrong holders on the top-ranked program.** LM-302, ranked #1, shows "Turning Point Therapeutics": there is no
   succession record and the R07/R08 dates are lost. Givastomig drops I-Mab, because R12 invents licensor/licensee
   roles.
5. **Recall is capped by the library.** SKB315's return (the reference's #1 asset) is invisible. B finds it.
6. Output inconsistencies: the stale memo summary, duplicate Diligence rows, duplicated reasons, and the staleness
   anchor.

**Single highest-value next fix:** rewrite `parse_territory` so that exclusions subtract only from an explicit
anchor ("worldwide", "global", "rest of world", or a named positive region such as North America or US). An
exclusion with no anchor, and any unknown residue such as "Puerto Rico" or "Mexico", should return `None` (unstated),
not a computed complement. Add held-out tests for T1–T7. This closes the only path found by which R1 can still
emit a no-obstacle tier for a program that is actually licensed in the US.

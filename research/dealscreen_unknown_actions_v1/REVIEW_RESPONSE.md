# Response to the U1 adversarial review (REVIEW.md): U1 revision 2

U1 revision 2 is the implementer's answer to `REVIEW.md`, measured on top of R1 revision 7. Nobody has reviewed it
yet. This is the implementer's account, not a review; every claim below should be checked by running code. The
reviewer's own scripts (`verify_claims.py`, `verify_targets.py`) were re-run unchanged against revision 2; the
outputs quoted below are copied from those runs.

## The single highest-value fix (D1)

A requested indication that the authority does not resolve to exactly one NCIt concept is now detected before any
relation is computed (`diagnostics._request_diagnostic`). Records are then never called a "different disease"
against it. The diagnostic says the request cannot be read, why ("matches 3 NCIt concepts" or "is not a name the
NCIt authority can read"), and that no record can pass the gate until the buyer file is restated. When the
authority's own name index offers a reading that is exactly one concept, it is suggested, checked first
(`indication_relations.restatement`: the label must resolve back to the same concept, otherwise the shortest name
that does; population-specific concepts are avoided unless the request states a population). `screen` prints the
same warning on stderr. Concept requests ("INDICATION:B_CELL_LYMPHOMA") and requests the S&E rule matches are
described as the S&E rule, which DealScreen does not read, and DealScreen no longer compares names against them.

## The findings

| Id | Severity | U1 revision 2 | Evidence |
|---|---|---|---|
| D1 unresolvable request | critical | Request-level diagnostic; no per-record class; `screen` warning with a verified restatement ("glioblastoma" → "gbm", read as Glioblastoma alone) | `test_unknown_actions.py` request tests; `verify_claims.py` "D1" |
| D2 non-site "site words" | high | Sites come only from NCIt's own by-site ancestors and from names of the form "<histology> of the <site>"; cell words are never sites; abbreviations must be initials of the site phrase. "Hodgkin Lymphoma" against follicular lymphoma, "Type 1 Diabetes Mellitus", "Hemophilia B", "Bladder Small Cell Carcinoma" are DIFFERENT_DISEASE | `verify_claims.py` "D2 table" |
| D3 acronym clean-up | high | Removed from the diagnostic: a parenthetical is dropped only when it is the initials of the adjacent words. "Lung Cancer (NSCLC)", "Gastrointestinal Cancer (CRC)", "Carcinoma (breast)", "Tumor (brain)" no longer read as broader | `verify_claims.py` "D3 table" |
| D4 variant spelling, placeholders | medium-high | "CLDN 18.2" → names the required target, no target set built; "CLDN18A2", "Claudin 18 isoform A2" → may name it, in a form neither reader reads; "Undisclosed Target", "PROPRIETARY", "TAA" → a placeholder, names no target | `verify_targets.py` |
| D5 isoform pairs, negations | medium | "QRX7.1xZPL4" names isoform 1, not isoform 2; "not QRX7.2", "QRX7.2-negative", "formerly QRX7.2" → may name it, not read | `verify_targets.py` |
| D6 exclusions | medium | "excl.", "excluded", "no", "ex-", "w/o", "apart from", "besides" are exclusions: UNREADABLE, never NAMES_REQUESTED_SITE. "not previously treated gastric cancer" and "(not amenable to surgery)" are no longer cut at "not" | `verify_claims.py` "D6" |
| D7 index artefacts | medium | When the index maps a name only to a population-specific concept, the action says so: "'Gastric (Stomach) Cancer' reads as Gastric Carcinoma (NCIt) ('Childhood Gastric Carcinoma' read as 'Gastric Carcinoma' (the record states no population))" | `verify_claims.py` "D7"; CLDN18.2 DA-3501 |
| D8 understatements | low-medium | "GEJ adenocarcinoma", "GEJ Cancer" → NAMES_REQUESTED_SITE ("GEJ (gastroesophageal junction)"); "Gastro-oesophageal junction adenocarcinoma" → reads as requested once British spelling is read. Kept UNREADABLE: "Oesophagogastric adenocarcinoma" and biomarker baskets (understatement, the safe direction) | `verify_claims.py` "D8" |
| D9 lead name | low | The lead name is the record's first name in record order ("'Stomach Neoplasm' reads as Gastric Neoplasm" for EO-3021) | CLDN18.2 `unknown_actions.csv` |
| D10 no assertable field | low | "DealScreen maps no landscape field to this gate's fact (…)" instead of "Nothing on record." | `diagnostics.other_diagnostic` |
| D11 wording | low | No "a clean-up the gate does not apply" on readings the gate applies; steps in words, no list repr | `verify_claims.py` "D11 / D13" |
| D12 over-promise | low | "or reject a wrong claim" removed; "What would pass the gate: a cited source naming …"; "The gate never fails on this evidence, so a program for another indication stays open" | CLDN18.2 actions |
| D13 spec deviation | spec | Disclosed in the ACCEPTANCE revision note: an ambiguous name whose readings are all "not requested" is DIFFERENT_DISEASE, and the sentence lists each reading ("reads as Pancreatic Carcinoma; Malignant Pancreatic Neoplasm") | ACCEPTANCE revision note |
| J1 site outranks a resolved reading | judgement, adopted | A name the authority resolves to one concept that is not requested is DIFFERENT_DISEASE, with "although it names gastric, a requested site". NAMES_REQUESTED_SITE is kept for names the authority cannot read | `verify_claims.py` "J1/J2" |
| J2 site word's role | judgement, adopted | "with liver metastases", "metastatic to the liver", "gastric type", "Gastric Outlet Obstruction" no longer give NAMES_REQUESTED_SITE | `verify_claims.py` "J1/J2" |
| J3 excluded programs | judgement | Kept by design; MEASUREMENT now states the total (17 UNKNOWN decisions on 16 excluded programs) | MEASUREMENT |
| J4 "none is X" for unread targets | judgement, adopted | "It also names 'PD-1', which the target authority does not read; it is not written as CLDN18 or its name" | CLDN18.2 RC148, Volrustomig, Rilvegostomig |

## Measured result

See `MEASUREMENT.md`. Coverage 38/38 on CLDN18.2 and 104/104 on four held-out landscapes; 0 of 62 and 0 of 312
programs with a changed scientific or transaction field; equivalence byte-identical; DealScreen suite 922 passed
(106 U1 cases). On CLDN18.2 two programs changed class: AZD5863 (NAMES_REQUESTED_SITE → AMBIGUOUS_NAME_ALL_BROADER,
J1) and DA-3501 (→ BROADER_THAN_REQUESTED, with the artefact stated, D7). SOT102 still points away, reported.

## Open

- U1 revision 2 needs its own adversarial review; AC U1-7 cannot be self-certified.
- The requested-indication warning helps only if the buyer file is restated; DealScreen does not restate it.

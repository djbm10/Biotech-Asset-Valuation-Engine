# Response to the second U1 review (REVIEW2.md): revision 3

Revision 3 is U1 on top of R1 revision 8 (beecfcd), on `dealscreen-mvp`, as of 2026-11-01. Nobody has reviewed it
yet. This file is the implementer's account, not a review: every claim below should be checked by running code. The
reviewer and the implementer are both AI. Neither is a human approval, and nothing here is validation. U1-7 is not
claimed.

## 1. The two high findings

- **N1, a stage concept for the requested site called a different disease.** The relation function now has a
  fourth outcome, besides requested, broader and overlapping. A concept is "under a broader parent of a requested
  concept" when two things hold. First, it sits under a direct parent of a requested concept, and that parent is a
  by-site concept (never a morphology parent). Second, its own label or names name one of that request's sites. The
  class is `UNDER_REQUESTED_PARENT`, ordered with the broader classes, before `BASKET`. "Stage IV gastric cancer"
  and "Stage III gastric cancer" against the CLDN18.2 request, and the held-out "Stage IV colorectal cancer"
  against a colorectal-adenocarcinoma request, are now in that class. A sibling that names another site stays a
  different disease ("Pancreatic adenocarcinoma" under the same digestive-system parent). When NCIt's label carries
  an AJCC edition that the record does not state, the action says "'AJCC v7' is part of NCIt's label; the record
  states no edition".
- **N2, a restatement that picks a different disease.** A restatement is now suggested only for the concept whose
  label is the request itself, and only with a name that resolves to that concept alone. Otherwise no example is
  given. If the request has several readings, the action and the `screen` warning list them all ("for 'pnh', the
  buyer chooses among Periventricular Nodular Heterotopia; Paroxysmal Nocturnal Hemoglobinuria"). "astrocytoma",
  "mesothelioma", "endometrial cancer" and "gastric cancer" now get no example. "glioblastoma" still gets "GBM".

## 2. The other findings

| Id | Revision 3 | Tests |
|---|---|---|
| N3 multi-word sites, spelling | A phrase is no longer dropped as its own abbreviation. British spellings change only at a word start or after "o", so "Gastroesophageal" is kept and "gastro-oesophageal" becomes "gastro-esophageal". "Gastroesophageal Junction Cancer", "Gastro-esophageal Junction Cancer", "Esophagogastric junction cancer" and the head-and-neck example now give NAMES_REQUESTED_SITE | `test_n3_…` (8) |
| N4 acronym as basket | A name with a word in capitals that the authority reads is not a basket. "Relapsed/refractory ALL" and "ALL, children" are UNREADABLE; "ALL" and "Adult ALL" read as requested. "All solid tumors" is still a basket | `test_n4_…` (5) |
| N5 non-site words | A site phrase must be named by a by-site "<site> Neoplasm" node and contain no lineage or state word (a closed list of generic biology words: neuroendocrine, myoepithelial, stromal, histiocytic, related, associated, …). A site followed by a therapy, toxicity or state word ("endocrine therapy-resistant", "hematologic toxicity") is not the disease site, in either hyphen spelling. All seven review rows no longer say "a requested site"; ten anatomical sites are still sites | `test_n5_…` (30) |
| N6 negated mention | New class `SOURCE_STATES_NOT_REQUIRED_TARGET`, summary "states it is not the required target". A parenthesised note is its own part, so "KLX9 (X negative)" lists KLX9 and says "'X negative' states it is not X" | `test_n6_…` (5) |
| N7 isoform, suffix, negation after the symbol | "X, isoform 2" reads the isoform. "X-AS1" (a capitalised annotation suffix) is at most "may name". "non-expressing", "knockout", "deficient", "deleted" and "(formerly)" after the symbol are negations. "X-positive" still names the target | `test_n7_…` (3) |
| N8 placeholder variants | "Novel ADC target", "Proprietary antigen X", "Target 1" and "Unnamed candidate" are placeholders (UNREADABLE) | `test_n8_…` (4) |
| N9 misquoted fragments | " and/or " is a list separator. "/" splits only between two names that start with a letter, so "CLDN6/9" and "N/A" are quoted as written | `test_n9_…` (3) |
| N10 "metastases of" | Removed from the metastatic-site prefixes: "Peritoneal metastases of gastric cancer" names gastric | `test_n10_…` |
| N11 wording | The request-level sentence says the diagnostic classes no name and the gate still compares. Restatements are a label, an acronym in capitals, or a clean name, never an index key ("burkitt s lymphoma", "medulloblastomas"). Repeated labels are listed once. A bare disease-state step reads "'relapsed' set aside as a disease-state word" | `test_n11_…` (2) |
| N12 empty request | An `OTHER` diagnostic: "The buyer file requests no indication, so no record name is compared" | `test_n12_…` |
| N13 memo "3 more" | Every record phrase is shown on each single-gate line; the number of names per phrase is still capped ("(+N more)"). SOT102 and Givastomig now appear | `test_n13_…` |

Edited existing tests, each for a stated rule:
- The negation cases in `test_target_forms_from_the_review` now expect the new class (N6).
- The restatement test keeps only the requests with an exact-label concept (N2).
- The CLI warning expects "'GBM'" (N11).
- The partly resolved request expects the new sentence (N11).
- The memo-size test allows 800 words for the 6,000-program case, because all phrases are now shown (N13).

## 3. Measured result

| Check | Result |
|---|---|
| Tests | `tests/dealscreen`: 1,052 pass (876 at R1 revision 8; `test_unknown_actions.py` 176 cases). `ruff` and `mypy` clean on `bve.dealscreen` and the CLI |
| U1-1 coverage | CLDN18.2 38 of 38; held-out (FcRn v1, FcRn v2, C5, synthetic) 104 of 104; no diagnostic on a decision that is not UNKNOWN or on an excluded program |
| U1-3 science | CLDN18.2: 0 of 62 programs changed (disposition, rank, decisions, machine recommendation, transaction, transaction rank) against R1 revision 8. Cross-version: 0 of 312. Cycle-4 equivalence: byte-identical, fast path, 4 of 4 |
| CLDN18.2 classes against revision 2 | AZD5863: AMBIGUOUS_NAME_ALL_BROADER → NAMES_REQUESTED_SITE. IBI343: NAMES_REQUESTED_SITE → READS_AS_REQUESTED (reads as Gastroesophageal Junction Adenocarcinoma after a clean-up the gate does not apply). CMG901, AMG 910 and SYSA1801 now name the junction. No other change |
| U1-6 | No reference-IN program has a gastric or junction name called a different disease (0 of 15). SOT102 still points away; its record names only pancreatic cancer |

## 4. Costs and open issues

1. **Site words come from NCIt's "<site> Neoplasm" nodes**, plus a closed word list. A real site that only a
   disorder node names ("biliary" on its own) is no longer reported: an understatement.
2. **The sibling rule needs the record's name to name a requested site.** A stage concept whose names give only an
   organ synonym the request's site phrases do not include stays DIFFERENT_DISEASE.
3. **"Relapsed/refractory ALL"** is UNREADABLE, not READS_AS_REQUESTED. The gate does not read the slash either,
   so this is an understatement.
4. **Negation words are a closed list.** A negation written another way ("lacking X expression") is still "may
   name" at worst, never "names the required target".
5. **U1-7 is open** until a fresh adversarial review of revision 3.

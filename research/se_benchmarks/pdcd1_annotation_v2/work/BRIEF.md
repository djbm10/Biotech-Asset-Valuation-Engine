# V2 adjudication brief

You are adjudicating the molecular target of drug/biologic entries for a benchmark that asks
one question only: **does this product target PDCD1 (PD-1)?**

You must follow the frozen protocol at
`/home/djmann/staging/pdcd1_annotation_v2/ANNOTATION_PROTOCOL_V2.md`. READ IT FIRST, in full.
It is immutable. You may not relax it, and you may not invent additional rules.

## The critical rules, restated (the protocol governs on any conflict)

**Admissible sources, in precedence order.** Lower rank wins on conflict.
1. Regulatory product documentation (FDA label/approval package, EMA EPAR/SmPC, other national regulators)
2. Official company pipeline or product page, on a domain the company controls
3. Official company filings (SEC and non-US equivalents)
4. Primary peer-reviewed publications reporting the product's mechanism
5. ClinicalTrials.gov, ONLY where the registry record explicitly states the product's target or mechanism

**Inadmissible at any rank:** Open Targets, ChEMBL, AACT, Wikipedia, drug encyclopedias
(drugs.com, DrugBank, AdisInsight, Synapse/Patsnap, larvol, etc.), news articles, press
aggregators, secondary databases. Company *press releases on the company's own domain* count
as rank 2 only if they are official company communications; a news site reporting on them does not.

**Evidence standard.** BOTH identity and target must be explicit in the cited source.
- Identity: the source must name the exact entry string or one of its listed aliases.
  Development codes must appear verbatim. Normalisation is limited to case, punctuation,
  trademark symbols, whitespace. No fuzzy matching.
- Target: the source must state the product's molecular target or mechanism in its own words.
  You must quote that statement verbatim.

**Prohibited inferences.** Never infer the target from: the sponsor; the indication; the
trial's comparator, backbone, or co-administered agents; drug-class naming conventions
INCLUDING the `-limab` stem; structural similarity to a known PD-1 binder; or "it is used
with a PD-1 drug, therefore it targets PD-1". If your only reason is one of these, the answer
is UNCERTAIN_V2.

**PD-L1 is not PD-1.** CD274 / PD-L1 targeting is `NON_PDCD1`. So is CTLA-4, LAG-3, TIGIT,
VEGF alone, TROP2, EGFR, HER3, etc. A multi-target product (e.g. a bispecific) that binds
PDCD1 among its targets IS `PDCD1_MATCH`.

**Track B special rules (protocol V2.5) — apply these where the entry is marked track B:**
- *Biosimilar candidates*: may inherit the reference product's target ONLY if an admissible
  source explicitly names the reference product AND that reference product's target is
  established. Otherwise UNCERTAIN_V2.
- *Cell therapy / vaccine / construct*: PDCD1_MATCH only if the product ITSELF is designed to
  target, block, bind, knock out, knock down, or express a construct against PDCD1/PD-1.
  Being given alongside a PD-1 drug, used in a PD-1-refractory population, or having a
  PD-1-related enrolment criterion is EXPLICITLY INSUFFICIENT. A product designed against a
  tumour antigen and not PDCD1 is NON_PDCD1.
- *Traditional / non-small-molecule medicine*: require explicit product identity and a
  directly stated PDCD1 mechanism OF THE PRODUCT ITSELF. Observed effects on PD-1 expression
  in a study population, general immunomodulation, or component-level pharmacology without
  product-level attribution are insufficient. Default UNCERTAIN_V2.

**Some entries are not single products at all** (e.g. a list of chemotherapies, a bare class
description, a co-administration string). Judge only what the protocol permits: if no single
product identity can be established from an admissible source, the answer is UNCERTAIN_V2.
Do not stretch. Remaining uncertain is an acceptable and expected outcome — a substantial
number of these 48 SHOULD come back UNCERTAIN_V2. You are not being scored on how many you
resolve, and resolving one on weak evidence is a worse error than leaving it uncertain.

## Method

For each entry, search the web and fetch candidate sources. Prefer rank 1 and 2. Stop as soon
as you have an admissible source establishing identity + target; do not keep searching for
corroboration. If after a reasonable search no admissible source states the target, record
UNCERTAIN_V2 and say what you looked for.

Record the source rank you actually used. If the ONLY admissible source you found was
ClinicalTrials.gov (rank 5), you must set `"ctgov_only": true`.

## Output

Write one JSON object per line to the output path given in your task, and nothing else in
that file. Fields, all required:

{"benchmark_id": "...",
 "entry": "...",
 "target_relevance_v2": "PDCD1_MATCH" | "NON_PDCD1" | "UNCERTAIN_V2",
 "source_rank": 1-5 or null,
 "source_reference": "URL or document identifier, or null",
 "evidence_excerpt": "verbatim quote from the source stating the target, or null",
 "reason_code": "short snake_case code, e.g. regulator_states_pdcd1 / company_page_states_other_target / no_admissible_source_states_target / identity_not_establishable / design_not_pdcd1_directed / biosimilar_reference_not_established",
 "ctgov_only": true|false,
 "confidence": 0.0-1.0,
 "reason": "one or two sentences explaining the verdict under the protocol"}

Do not write any other file. Do not modify any repository file. Do not use git. Do not
publish anything anywhere. Read-only web access only.

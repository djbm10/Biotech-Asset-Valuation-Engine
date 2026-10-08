# APPROVED_PRODUCT_HUMAN_EFFICACY_DIAGNOSIS v1 — why approved CAR-Ts lack human_poc (diagnosis)

**Status:** CLOSED 2026-10-08, **no behaviour change**.
**Baseline:** `~/se_runs/tac01_protoid_v1` (mint5 was checked for scope).
**Reader:** frozen `human_poc_v4`. Approval is not efficacy evidence, and no rule was
loosened for this diagnosis.

**Artifacts** (all in `research/se_approved_efficacy/`):
- `trace_v1.py` → `trace_tac01_v1.txt`: the first filter that rejects each sentence, over
  every document routed to each frozen product, plus a corpus-wide scan;
- `scope_v1.py` → `scope_v1.txt`: both candidate mechanisms across every qualified asset;
- `routing_population_v1.py` → `routing_population_v1.txt`: what a candidate routing fix
  would change.

## 1. Frozen population

The population is the approved CAR-T products present in TAC01:
- brexucabtagene autoleucel (has human_poc);
- Breyanzi / liso-cel;
- KYMRIAH / tisagenlecleucel;
- axi-cel / YESCARTA;
- AUCATZYL / obe-cel;
- Abecma and Carvykti (BCMA products, off-query for TAC01, included for completeness).

## 2. Classification

| Product | Cause | Evidence |
|---|---|---|
| Breyanzi | **A**: attribution failed on a routed document | PMID 42462111 (TRANSCEND FL 3-year): "A total of 107 patients received liso-cel and 103 were efficacy evaluable, with overall and complete response rates … of 97% … and 94%". `_reports_a_regimen` reads the clause-joining " and " after "liso-cel" as product coordination. |
| KYMRIAH | **D**: routing | PMID 30670684: "tisagenlecleucel resulted in a remission rate of 81% in pediatric and adolescent patients". The document is in the sealed corpus, but the PubMed adapter's follow-up literal-term gate (`_matches_follow_up`) kept the **document** and emitted **no hits**, so it never reached any asset. Routed documents give only **C**, for example "FDA registration … was based on a CR rate of 81%", which has no human term. |
| axi-cel | **D**: routing | PMIDs 30518502 (ZUMA-1: "89 (82%) of 108 assessable patients …"), 34599413 and 39968186. All three are orphaned by the same gate. |
| AUCATZYL | **B/C** | Routed evidence is only qualitative ("favourable safety and efficacy"). No numerical pivotal (FELIX) abstract is in the corpus. |
| Abecma, Carvykti | **B/C**, off-query | No numerical sentence in the corpus. Their pivotal data was not acquired by a CD19 query, which is expected. |

## 3. Is either mechanism a safe general fix? No.

**Routing (D).**
- 1,458 TAC01 and 440 mint5 abstracts are orphans: kept as documents, with no hits.
- I simulated the narrowest routing rule: route an orphan only to an **existing** qualified
  asset, and only by an **exact** link-key match on a name the adapter's own extractor
  observes. No substring matching, no new assets.
- In TAC01 it gives human_poc to 8 assets. The genuine gains are KYMRIAH, axi-cel and the two
  inotuzumab assets. The rest are **false**:
  - fludarabine, cyclophosphamide and bendamustine, from "lymphodepletion with … before
    tisagenlecleucel" and "treated … with cyclophosphamide and fludarabine lymphodepletion";
  - in mint5, belimumab and cyclophosphamide, from an RNA-seq sentence.
- The routed population is currently protected from those reader weaknesses only because
  these documents never reach those assets. Routing them would trade 2 approved-product
  recoveries for at least 3 false human-PoC facts. **Rejected.**

**Clause-"and" (A).**
- Across both benchmarks, the regimen guard fires on "<name> and <numeral>" twice:
  - Breyanzi, which is wrong;
  - "HMA plus lenalidomide and 3 patients", which is correctly a regimen, through the
    preceding "plus".
- A narrowing would recover 1 sentence for 1 asset. A digit-led guard would also misread
  real co-products such as "gemcitabine and 5-fluorouracil".
- This is a population of one on the tuning benchmarks. **Not preregistered**, in keeping
  with the instruction not to loosen precision rules to make approved products PASS.

## 4. Decision

- **No behaviour change.** The remaining UNKNOWNs are explained.
- The UNKNOWN for KYMRIAH and axi-cel is a **known coverage gap**: evidence that is in the
  corpus but not routed. It is not a truthful absence, and the shortlist should not be read
  as "no human efficacy" for approved products.
- Recorded for the held-out phase:
  - **R-1.** Orphaned abstracts. Any future fix needs the reader's lymphodepletion and
    background-agent weakness addressed first.
  - **R-2.** The clause-"and" regimen false positive.
  - **R-3.** Approved-product efficacy needs an authoritative source family (label or
    pivotal-publication acquisition). That is source coverage, not a reader threshold.
  - **R-4.** KYMRIAH carries `CART19` and `CART-19` as aliases (from ChEMBL synonymy). A
    corpus-wide name scan would attribute Penn and humanized CART19 data (for example
    "hCART19s") to Kymriah. The current mention routing does not, but any scan-based
    routing must not use those aliases.

## 5. Benchmarks frozen

**TAC01 and mint5 are FROZEN as of this milestone.** The baselines are
`~/se_runs/{tac01,mint5}_protoid_v1`. They may not be used to tune semantic-search behaviour,
except to confirm a fix for an independently discovered correctness bug. Further changes are
evaluated first on the held-out suite (`heldout_validation_suite_v1.md`).

# BD screening brief — CD19 + BCMA dual-targeting assets in autoimmune disease (development demo)

> Development demonstration. Run `se:9ff16f18-052b-48ec-b9aa-f01df1f0c4fa`, as of 2026-09-24, run status **INCOMPLETE**. Not a validated product; no scores.

## Summary

- The engine found 3137 candidate names; 1 passed every gate. 10 reviewable candidates are shown.
- Of those, 0 have the requested target confirmed by an authority record; 10 are on the list only because they were found while searching for it.
- No human efficacy is confirmed for any candidate: efficacy passages are unverified quotations.
- 10 candidates have an engine gate that disagrees with the displayed evidence status (flagged on each card).
- Approval status and rights holders are not represented; check whether each candidate is already marketed or partnered before treating it as an external opportunity.

## A. Strategic gap

**Question:** Which external assets engage both CD19 and BCMA for autoimmune disease, at Phase 1 or later, with some human proof-of-concept?

**Why:** Illustrative public scenario inspired by a gap-led BD search ("find companies developing T-cell engagers targeting CD19 and BCMA"): deep B-cell and plasma-cell depletion is being explored as an immune reset in autoimmune disease, and a buyer wants to map who is pursuing dual CD19/BCMA approaches and what human evidence exists.

**What the engine enforced:**

- target (ALL of CD19, TNFRSF17)
- modality: none
- therapeutic area: AUTOIMMUNE
- indication: none
- minimum stage: PHASE_1
- human proof-of-concept required — but the gate reads prose efficacy statements and has no validated confirmation route, so a PASS is an unverified claim

**What the engine could not understand or enforce:**

- T-cell-engager format specifically — the run did not restrict modality; cell therapies dominate.
- Autologous vs allogeneic, and construct design — not enforced.
- Which autoimmune indication (lupus, myasthenia, etc.) — the run asked only for the therapeutic area.
- Manufacturing scalability for a chronic-disease market — not enforced.
- Rights, partnering availability and territory — not enforced.
- No manufacturing, delivery or commercial constraint was expressible in this run.
- No clinical effect bar (endpoint, effect size, comparator) was enforced.
- Deal route, rights and geography were not enforced.

## B. Asset landscape

3137 candidates found; 1 passed every gate, 243 need review, 708 excluded, 2185 held back for low support. Showing the first 10 reviewable candidates in the engine's declared order.

| # | Asset | Eligibility | Target | Modality (authority) | Stage | Human efficacy | Sponsors (registry) |
|---|---|---|---|---|---|---|---|
| 1 | **ICG318** | Meets (relies on unverified human-PoC) ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_2<br>✅ Supported | ⚠️ Unverified | iCell Gene Therapeutics |
| 2 | **AZD0120** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_3<br>✅ Supported | ❔ Unknown | Tongji Hospital, AstraZeneca +7 |
| 3 | **FKC289** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_2<br>✅ Supported | ❔ Unknown | Shenzhen Fosun Kairos Biotechnology Co., Ltd. +1 |
| 4 | **umbilical cord blood CD19-BCMA CAR-T cells infusion** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_2<br>✅ Supported | ❔ Unknown | Beijing GoBroad Hospital |
| 5 | **CD19-BCMA dual nanobody based CAR-T Cells** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_2<br>✅ Supported | ❔ Unknown | Chang Yingjun |
| 6 | **Allogeneic CD19/BCMA-targeted CAR-γδT cell injection** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_1<br>✅ Supported | ❔ Unknown | Institute of Hematology & Blood Diseases Hospital, China |
| 7 | **allogeneic umbilical cord blood-derived CAR-T targeting CD19 and BCMA** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_1<br>✅ Supported | ❔ Unknown | Chengdu Ucello Biotechnology Co., Ltd. |
| 8 | **allogenic anti-CD19/BCMA CAR-T** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_1<br>✅ Supported | ❔ Unknown | Shanghai Zhongshan Hospital |
| 9 | **anti-CD19/BCMA U CAR T cells** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_1<br>✅ Supported | ❔ Unknown | Changhai Hospital |
| 10 | **CD19/BCMA CAR T-cells** | Unknown ⚠️ | —<br>❔ Unknown | —<br>❔ Unknown | PHASE_1<br>✅ Supported | ❔ Unknown | Zhejiang University |

## C–D. Evidence, uncertainty and technical diligence

### 1. ICG318 — Meets (relies on unverified human-PoC)

*Why it appeared:* found while searching CD19, TNFRSF17; named in 4 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Human efficacy: shown UNVERIFIED, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 10 registry/publication records; individual trials may be earlier | [NCT06794008 (development_stage_order)](https://clinicaltrials.gov/study/NCT06794008), [NCT06794008 (development_status)](https://clinicaltrials.gov/study/NCT06794008), [NCT07544160 (development_stage_order)](https://clinicaltrials.gov/study/NCT07544160) |
| Sponsors | iCell Gene Therapeutics | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07544160 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07544160), [NCT07328581 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07328581), [NCT07715136 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07715136) |
| Human efficacy | efficacy statement in public text | ⚠️ Unverified | legacy prose-derived human_poc_present; there is no validated confirmation route, so this is an unverified public claim for analyst reading, not established clinical proof | [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/41612420/) |

*Modality hint from trial text (not evidence):* CAR_T

*Efficacy passages for analyst reading (unverified):*

> Herein, we present 12 patients with refractory SLE, including 10 with lupus nephritis (LN), who received ICG318 CAR T-cells resulting in 10 of 12 achieving stringent complete remission (sCR) defined by medication-free DORIS CR and complete renal response (CRR). — [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/41612420/)

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc PASS

*10 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — Do the quoted efficacy passages hold up: is the disease the requested indication, and which population, line of therapy, n, endpoint and comparator? Is the result attributable to this product rather than a regimen? _(because: unverified prose efficacy statement)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* target: an authority record or product description naming the antigen

### 2. AZD0120 — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 23 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of NCIt:C175471 (Cell); no modality was requested | — |
| Stage | PHASE_3 | ✅ Supported | most advanced stage across 38 registry/publication records; individual trials may be earlier | [NCT04935580 (development_stage_order)](https://clinicaltrials.gov/study/NCT04935580), [NCT04935580 (development_status)](https://clinicaltrials.gov/study/NCT04935580), [NCT07350837 (development_stage_order)](https://clinicaltrials.gov/study/NCT07350837) |
| Sponsors | Tongji Hospital, AstraZeneca, Alexion Pharmaceuticals, Inc., Shanghai Changzheng Hospital, RenJi Hospital, Gracell Biote | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07350837 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07350837), [NCT07735637 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07735637), [NCT07295847 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07295847) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*38 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT04935580 declare, and has any result been posted or presented? _(because: registered PHASE_3 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 3. FKC289 — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 3 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 6 registry/publication records; individual trials may be earlier | [NCT07765537 (development_stage_order)](https://clinicaltrials.gov/study/NCT07765537), [NCT07765537 (development_status)](https://clinicaltrials.gov/study/NCT07765537), [NCT06285279 (development_stage_order)](https://clinicaltrials.gov/study/NCT06285279) |
| Sponsors | Shenzhen Fosun Kairos Biotechnology Co., Ltd., Nanjing University School of Medicine | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07765537 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07765537), [NCT06285279 (lead_sponsor)](https://clinicaltrials.gov/study/NCT06285279), [NCT07765524 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07765524) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*6 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT07765537 declare, and has any result been posted or presented? _(because: registered PHASE_2 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 4. umbilical cord blood CD19-BCMA CAR-T cells infusion — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT06947473 (development_stage_order)](https://clinicaltrials.gov/study/NCT06947473), [NCT06947473 (development_status)](https://clinicaltrials.gov/study/NCT06947473) |
| Sponsors | Beijing GoBroad Hospital | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT06947473 (lead_sponsor)](https://clinicaltrials.gov/study/NCT06947473) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT06947473 declare, and has any result been posted or presented? _(because: registered PHASE_2 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 5. CD19-BCMA dual nanobody based CAR-T Cells — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT07451236 (development_stage_order)](https://clinicaltrials.gov/study/NCT07451236), [NCT07451236 (development_status)](https://clinicaltrials.gov/study/NCT07451236) |
| Sponsors | Chang Yingjun | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07451236 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07451236) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area UNKNOWN; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT07451236 declare, and has any result been posted or presented? _(because: registered PHASE_2 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* strategy.therapeutic_area: a source that settles this would move the candidate from Unknown; evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 6. Allogeneic CD19/BCMA-targeted CAR-γδT cell injection — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_1 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT07490275 (development_stage_order)](https://clinicaltrials.gov/study/NCT07490275), [NCT07490275 (development_status)](https://clinicaltrials.gov/study/NCT07490275) |
| Sponsors | Institute of Hematology & Blood Diseases Hospital, China | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07490275 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07490275) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*1 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT07490275 declare, and has any result been posted or presented? _(because: registered PHASE_1 activity, no extracted efficacy data)_
4. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 7. allogeneic umbilical cord blood-derived CAR-T targeting CD19 and BCMA — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_1 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT07274059 (development_stage_order)](https://clinicaltrials.gov/study/NCT07274059), [NCT07274059 (development_status)](https://clinicaltrials.gov/study/NCT07274059) |
| Sponsors | Chengdu Ucello Biotechnology Co., Ltd. | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07274059 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07274059) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT07274059 declare, and has any result been posted or presented? _(because: registered PHASE_1 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 8. allogenic anti-CD19/BCMA CAR-T — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_1 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT07261345 (development_stage_order)](https://clinicaltrials.gov/study/NCT07261345), [NCT07261345 (development_status)](https://clinicaltrials.gov/study/NCT07261345) |
| Sponsors | Shanghai Zhongshan Hospital | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07261345 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07261345) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT07261345 declare, and has any result been posted or presented? _(because: registered PHASE_1 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 9. anti-CD19/BCMA U CAR T cells — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_1 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT07246096 (development_stage_order)](https://clinicaltrials.gov/study/NCT07246096), [NCT07246096 (development_status)](https://clinicaltrials.gov/study/NCT07246096) |
| Sponsors | Changhai Hospital | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07246096 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07246096) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT07246096 declare, and has any result been posted or presented? _(because: registered PHASE_1 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 10. CD19/BCMA CAR T-cells — Unknown

*Why it appeared:* found while searching CD19, TNFRSF17; named in 4 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, TNFRSF17, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | — | ❔ Unknown | no authority record of this asset's drug; the trial-text modality hint is not evidence | — |
| Stage | PHASE_1 | ✅ Supported | most advanced stage across 8 registry/publication records; individual trials may be earlier | [NCT05085444 (development_stage_order)](https://clinicaltrials.gov/study/NCT05085444), [NCT05085444 (development_status)](https://clinicaltrials.gov/study/NCT05085444), [NCT05085431 (development_stage_order)](https://clinicaltrials.gov/study/NCT05085431) |
| Sponsors | Zhejiang University | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT05085444 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05085444), [NCT05085431 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05085431), [NCT05085418 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05085418) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; strategy.therapeutic_area PASS; evidence.minimum_stage PASS; evidence.human_poc UNKNOWN

*8 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19 and TNFRSF17, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Target engagement / format** — What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or antibody format)? _(because: no authority modality record)_
3. **Clinical readout** — What primary endpoint and readout timing does NCT05085444 declare, and has any result been posted or presented? _(because: registered PHASE_1 activity, no extracted efficacy data)_
4. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
5. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
6. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* evidence.human_poc: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

## E. Analyst conclusion

**Passed every engine gate** (read the gate basis before relying on it):

- ICG318

**Review first** (target authority-supported, modality not contradicted; still Unknown on at least one gate):

- _None._

**Unresolved** (target or modality not established):

- AZD0120
- FKC289
- umbilical cord blood CD19-BCMA CAR-T cells infusion
- CD19-BCMA dual nanobody based CAR-T Cells
- Allogeneic CD19/BCMA-targeted CAR-γδT cell injection
- allogeneic umbilical cord blood-derived CAR-T targeting CD19 and BCMA
- allogenic anti-CD19/BCMA CAR-T
- anti-CD19/BCMA U CAR T cells
- CD19/BCMA CAR T-cells

**Excluded by the engine** (708; first 10 shown, alphabetical):

- 19(T2)28z1xx CAR T cells — strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.
- 19-28z/IL-18 CAR T cells — target.expression: Canonical construct targets do not satisfy the configured expression.; strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.
- 20-19 Tan BB06oz CAR T — target.expression: Canonical construct targets do not satisfy the configured expression.
- 4SCAR-CD22/CD123/CD38/CD10/CD20/TSLPR — target.expression: Canonical construct targets do not satisfy the configured expression.; strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.
- 4SCAR19/22 T cells — target.expression: Canonical construct targets do not satisfy the configured expression.; strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.
- 7×19-THEMIS CAR-T cells — target.expression: Canonical construct targets do not satisfy the configured expression.; strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.
- [18F]Fluoropropyl-Trimethoprim — strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.
- Abaloparatide — target.expression: Canonical construct targets do not satisfy the configured expression.
- abatacept — target.expression: Canonical construct targets do not satisfy the configured expression.
- Abecma — target.expression: Canonical construct targets do not satisfy the configured expression.; strategy.therapeutic_area: Observed therapeutic_area conflicts with buyer requirement strategy.therapeutic_area.

**Held back for low support but authority-confirmed on at least one requested target** (check manually):

- CART19

**Next research action:** Resolve `evidence.human_poc` by reading the cited sources: it is UNKNOWN for 9 of 10 shown candidates and is what keeps them out of the eligible set. Human-PoC has no validated automatic route, so this is manual reading of the cited passages and registry results.

## Limitations

- Development demonstration on a frozen non-holdout run; not a validated scientific product.
- Run status INCOMPLETE: sources marked as blind spots were never searched; absent assets may simply be unseen.
- Eligibility is the engine's gate disposition. 'Review first' only means the target is authority-supported and the modality is not contradicted; it is not a recommendation or score.
- Human-PoC has no validated automatic confirmation route; efficacy passages are shown for reading only.
- Company lists are registry sponsors and collaborators, not rights holders.
- Stage is the most advanced trial phase seen in registry/publication records; marketing approval is not represented, so approved products appear at their latest trial phase.
- Trade names and INNs are not consolidated; the same product can appear twice (same authority record is flagged).
- 2185 low-support nominations were held back by the engine and are not shown.

**Sources never searched:** company_pipeline_or_presentation; company_press_release; conference_asco; conference_ash; conference_eha; sec_edgar

**Inputs:**

- `cd19_bcma_dual_autoimmune.yaml` sha256 `3675f5dd6619fac50dddb3e537f31d6d0d1fbee377e5655280eb80e4f8ee0cdc`
- `problem.yaml` sha256 `a53d5eda56c0216826f972cf18f74658dcca23499790454ed768178a1a7f88f2`
- `result.json` sha256 `085fd4f4c9078e8711d945a9f64570cd861cd7636f7471678bf5f7f033fae0f0`
- `shortlist.json` sha256 `b8c2cf6fc2d324e263d82530a98cb40f0bcd37d559859c3e42bb71b2a6a4b4dd`

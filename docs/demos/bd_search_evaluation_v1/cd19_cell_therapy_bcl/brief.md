# BD screening brief — CD19-directed cell therapy for B-cell lymphoma (development demo)

> Development demonstration. Run `se:8e9d96fc-5f25-4590-9d16-aa5b308a0d99`, as of 2026-09-24, run status **INCOMPLETE**. Not a validated product; no scores.

## Summary

- The engine found 5123 candidate names; 0 passed every gate. 10 reviewable candidates are shown.
- Of those, 3 have the requested target confirmed by an authority record; 7 are on the list only because they were found while searching for it.
- No human efficacy is confirmed for any candidate: efficacy passages are unverified quotations.
- 10 candidates have an engine gate that disagrees with the displayed evidence status (flagged on each card).
- Approval status and rights holders are not represented; check whether each candidate is already marketed or partnered before treating it as an external opportunity.

## A. Strategic gap

**Question:** Which external CD19-directed cell-therapy assets in B-cell lymphoma, at Phase 1 or later, could fill a gap in a B-cell-depletion oncology portfolio?

**Why:** Illustrative public scenario: a buyer with no CD19 cell therapy wants to know who is developing one, how far each programme has progressed, what evidence is public, and which technical questions to put to the asset owner before a first call. Modelled on a BD gap-led search (start from the capability needed, not from "promising biotechs").

**What the engine enforced:**

- target (ANY of CD19)
- modality: CELL_THERAPY
- therapeutic area: ONCOLOGY
- indication: INDICATION:B_CELL_LYMPHOMA
- minimum stage: PHASE_1

**What the engine could not understand or enforce:**

- Autologous vs allogeneic preference — not expressible as an engine requirement.
- CAR construct details (co-stimulatory domain, dual targeting) — not enforced.
- Manufacturing capacity, vein-to-vein time and CMC readiness — not enforced.
- Availability for partnering, rights holder and territory — not enforced.
- No manufacturing, delivery or commercial constraint was expressible in this run.
- No clinical effect bar (endpoint, effect size, comparator) was enforced.
- Human proof-of-concept was not required (and has no validated confirmation route).
- Deal route, rights and geography were not enforced.

## B. Asset landscape

5123 candidates found; 0 passed every gate, 545 need review, 810 excluded, 3768 held back for low support. Showing the first 10 reviewable candidates in the engine's declared order.

| # | Asset | Eligibility | Target | Modality (authority) | Stage | Human efficacy | Sponsors (registry) |
|---|---|---|---|---|---|---|---|
| 1 | **Brexucabtagene Autoleucel** | Unknown ⚠️ | TARGET:CD19<br>✅ Supported | CELL_THERAPY<br>✅ Supported | PHASE_2<br>✅ Supported | ⚠️ Unverified | H. Lee Moffitt Cancer Center and Research Institute, Kite +3 |
| 2 | **CNCT19** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_2<br>✅ Supported | ⚠️ Unverified | Juventas Cell Therapy Ltd., Shandong University +2 |
| 3 | **Breyanzi** | Unknown ⚠️ | TARGET:CD19<br>✅ Supported | CELL_THERAPY<br>✅ Supported | PHASE_3<br>✅ Supported | ❔ Unknown | Masonic Cancer Center, University of Minnesota +12 |
| 4 | **KYMRIAH** | Unknown ⚠️ | TARGET:CD19<br>✅ Supported | CELL_THERAPY<br>✅ Supported | PHASE_3<br>✅ Supported | ❔ Unknown | Masonic Cancer Center, University of Minnesota +8 |
| 5 | **axi-cel** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_3<br>✅ Supported | ❔ Unknown | Ruijin Hospital, Zhejiang Cancer Hospital +15 |
| 6 | **KITE-753** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_3<br>✅ Supported | ❔ Unknown | Kite, A Gilead Company |
| 7 | **CC-97540** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_3<br>✅ Supported | ❔ Unknown | Marcela V. Maus, M.D.,Ph.D. +5 |
| 8 | **ALLO-501A** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_2<br>✅ Supported | ❔ Unknown | Allogene Therapeutics |
| 9 | **Anbalcabtagene Autoleucel** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_2<br>✅ Supported | ❔ Unknown | Curocell Inc. |
| 10 | **AUTO3** | Unknown ⚠️ | —<br>❔ Unknown | CELL_THERAPY<br>✅ Supported | PHASE_2<br>✅ Supported | ❔ Unknown | Autolus Limited |

## C–D. Evidence, uncertainty and technical diligence

### 1. Brexucabtagene Autoleucel — Unknown

*Why it appeared:* found while searching CD19; named in 57 source documents

**⚠️ Engine disagreement:** Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | TARGET:CD19 | ✅ Supported | drug-to-target authority records (ChEMBL / Open Targets) name the requested target | open_targets 26.06 (DIRECT_TARGET -> TARGET:CD19), chembl ChEMBL_37 record 7686 (DIRECT_TARGET -> TARGET:CD19) |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:BREXUCABTAGENE AUTOLEUCEL (CHEMBL4594618: Gene). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 18 registry/publication records; individual trials may be earlier | [NCT06553872 (development_stage_order)](https://clinicaltrials.gov/study/NCT06553872), [NCT06553872 (development_status)](https://clinicaltrials.gov/study/NCT06553872), [NCT03642626 (development_stage_order)](https://clinicaltrials.gov/study/NCT03642626) |
| Sponsors | H. Lee Moffitt Cancer Center and Research Institute, Kite, A Gilead Company, Masonic Cancer Center, University of Minnes | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT06553872 (lead_sponsor)](https://clinicaltrials.gov/study/NCT06553872), [NCT05537766 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05537766), [NCT04880434 (lead_sponsor)](https://clinicaltrials.gov/study/NCT04880434) |
| Human efficacy | efficacy statement in public text | ⚠️ Unverified | legacy prose-derived human_poc_present; there is no validated confirmation route, so this is an unverified public claim for analyst reading, not established clinical proof | [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/42036693/), [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/41643192/) |

*Modality hint from trial text (not evidence):* CAR_T

*Efficacy passages for analyst reading (unverified):*

> Treatment with brexucabtagene autoleucel (brexu-cel), an autologous anti-CD19 chimeric antigen receptor (CAR) T-cell therapy, demonstrated a high objective response rate (93%) and complete response rate (67%) in 60 patients with relapsed/refractory mantle cell lymphoma (R/R MCL) treated in the pivotal ZUMA-2 Cohort 1 study. — [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/42036693/)
> In a real-world analysis of brexucabtagene autoleucel recipients with relapsed/refractory B-cell acute lymphoblastic leukemia (N = 278), lack of response to prior blinatumomab correlates with significantly worse following chimeric antigen receptor T-cell therapy outcomes. — [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/41643192/)

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*14 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Clinical readout** — Do the quoted efficacy passages hold up: is the disease the requested indication, and which population, line of therapy, n, endpoint and comparator? Is the result attributable to this product rather than a regimen? _(because: unverified prose efficacy statement)_
2. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
3. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
4. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown

### 2. CNCT19 — Unknown

*Why it appeared:* found while searching CD19; named in 10 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of NCIt:C175465 (Cell). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 14 registry/publication records; individual trials may be earlier | [NCT04684147 (development_stage_order)](https://clinicaltrials.gov/study/NCT04684147), [NCT04684147 (development_status)](https://clinicaltrials.gov/study/NCT04684147), [NCT05667506 (development_stage_order)](https://clinicaltrials.gov/study/NCT05667506) |
| Sponsors | Juventas Cell Therapy Ltd., Shandong University, Institute of Hematology & Blood Diseases Hospital, China | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT04684147 (lead_sponsor)](https://clinicaltrials.gov/study/NCT04684147), [NCT05667506 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05667506), [NCT04011293 (lead_sponsor)](https://clinicaltrials.gov/study/NCT04011293) |
| Human efficacy | efficacy statement in public text | ⚠️ Unverified | legacy prose-derived human_poc_present; there is no validated confirmation route, so this is an unverified public claim for analyst reading, not established clinical proof | [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/32894185/), [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/32894185/) |

*Modality hint from trial text (not evidence):* CAR_T

*Efficacy passages for analyst reading (unverified):*

> Data from our study suggested that 90% of the 20 patients treated with infusions of CNCT19 cells reached complete remission or complete remission with incomplete count recovery (CR/CRi) within 28 days. — [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/32894185/)
> After a median follow-up of 10.09 months (range, 0.49-24.02 months), the median overall survival and relapse-free survival for the 20 patients treated with CNCT19 cells was 12.91 months (95% confidence interval [CI], 7.74-18.08 months) and 6.93 months (95% CI, 3.13-10.73 months), respectively. — [PubMed (abstract)](https://pubmed.ncbi.nlm.nih.gov/32894185/)

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*13 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — Do the quoted efficacy passages hold up: is the disease the requested indication, and which population, line of therapy, n, endpoint and comparator? Is the result attributable to this product rather than a regimen? _(because: unverified prose efficacy statement)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 3. Breyanzi — Unknown

*Why it appeared:* found while searching CD19; named in 85 source documents

**⚠️ Engine disagreement:** Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | TARGET:CD19 | ✅ Supported | drug-to-target authority records (ChEMBL / Open Targets) name the requested target | open_targets 26.06 (DIRECT_TARGET -> TARGET:CD19), chembl ChEMBL_37 record 7987 (DIRECT_TARGET -> TARGET:CD19) |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:LISOCABTAGENE MARALEUCEL (CHEMBL4297236: Gene). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_3 | ✅ Supported | most advanced stage across 24 registry/publication records; individual trials may be earlier | [NCT05873712 (development_stage_order)](https://clinicaltrials.gov/study/NCT05873712), [NCT05873712 (development_status)](https://clinicaltrials.gov/study/NCT05873712), [NCT05633615 (development_stage_order)](https://clinicaltrials.gov/study/NCT05633615) |
| Sponsors | Masonic Cancer Center, University of Minnesota, Juno Therapeutics, Inc., a Bristol-Myers Squibb Company, Aseel Alsouqi,  | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT03642626 (lead_sponsor)](https://clinicaltrials.gov/study/NCT03642626), [NCT06205290 (lead_sponsor)](https://clinicaltrials.gov/study/NCT06205290), [NCT05873712 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05873712) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*14 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Clinical readout** — What primary endpoint and readout timing does NCT05873712 declare, and has any result been posted or presented? _(because: registered PHASE_3 activity, no extracted efficacy data)_
2. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
3. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
4. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown

### 4. KYMRIAH — Unknown

*Why it appeared:* found while searching CD19; named in 103 source documents

**⚠️ Engine disagreement:** Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | TARGET:CD19 | ✅ Supported | drug-to-target authority records (ChEMBL / Open Targets) name the requested target | open_targets 26.06 (DIRECT_TARGET -> TARGET:CD19), chembl ChEMBL_37 record 7492 (DIRECT_TARGET -> TARGET:CD19) |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:TISAGENLECLEUCEL (CHEMBL3301574: Cell). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_3 | ✅ Supported | most advanced stage across 18 registry/publication records; individual trials may be earlier | [NCT03570892 (development_stage_order)](https://clinicaltrials.gov/study/NCT03570892), [NCT03570892 (development_status)](https://clinicaltrials.gov/study/NCT03570892), [NCT03642626 (development_stage_order)](https://clinicaltrials.gov/study/NCT03642626) |
| Sponsors | Masonic Cancer Center, University of Minnesota, Novartis Pharmaceuticals, Memorial Sloan Kettering Cancer Center, Matthe | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT03642626 (lead_sponsor)](https://clinicaltrials.gov/study/NCT03642626), [NCT03570892 (lead_sponsor)](https://clinicaltrials.gov/study/NCT03570892), [NCT05460533 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05460533) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*14 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Clinical readout** — What primary endpoint and readout timing does NCT03570892 declare, and has any result been posted or presented? _(because: registered PHASE_3 activity, no extracted efficacy data)_
2. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
3. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
4. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown

### 5. axi-cel — Unknown

*Why it appeared:* found while searching CD19; named in 119 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:AXICABTAGENE CILOLEUCEL (CHEMBL3989989: Gene). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_3 | ✅ Supported | most advanced stage across 45 registry/publication records; individual trials may be earlier | [NCT07538635 (development_stage_order)](https://clinicaltrials.gov/study/NCT07538635), [NCT07538635 (development_status)](https://clinicaltrials.gov/study/NCT07538635), [NCT02348216 (development_stage_order)](https://clinicaltrials.gov/study/NCT02348216) |
| Sponsors | Ruijin Hospital, Zhejiang Cancer Hospital, Kite, A Gilead Company, The First Affiliated Hospital of Xiamen University, W | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT05800067 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05800067), [NCT07538635 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07538635), [NCT02348216 (lead_sponsor)](https://clinicaltrials.gov/study/NCT02348216) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CELL_THERAPY

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*37 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT07538635 declare, and has any result been posted or presented? _(because: registered PHASE_3 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 6. KITE-753 — Unknown

*Why it appeared:* found while searching CD19; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of NCIt:C227826 (Cell). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_3 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT07479797 (development_stage_order)](https://clinicaltrials.gov/study/NCT07479797), [NCT07479797 (development_status)](https://clinicaltrials.gov/study/NCT07479797) |
| Sponsors | Kite, A Gilead Company | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07479797 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07479797) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT07479797 declare, and has any result been posted or presented? _(because: registered PHASE_3 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 7. CC-97540 — Unknown

*Why it appeared:* found while searching CD19; named in 8 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:ZOLACABTAGENE AUTOLEUCEL (CHEMBL6068475: Gene). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_3 | ✅ Supported | most advanced stage across 14 registry/publication records; individual trials may be earlier | [NCT07388277 (development_stage_order)](https://clinicaltrials.gov/study/NCT07388277), [NCT07388277 (development_status)](https://clinicaltrials.gov/study/NCT07388277), [NCT04231747 (development_stage_order)](https://clinicaltrials.gov/study/NCT04231747) |
| Sponsors | Marcela V. Maus, M.D.,Ph.D., Juno Therapeutics, a Subsidiary of Celgene, Juno Therapeutics, Inc., a Bristol-Myers Squibb | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT07388277 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07388277), [NCT04231747 (lead_sponsor)](https://clinicaltrials.gov/study/NCT04231747), [NCT07015983 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07015983) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication UNKNOWN; evidence.minimum_stage PASS

*9 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT07388277 declare, and has any result been posted or presented? _(because: registered PHASE_3 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; strategy.indication: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 8. ALLO-501A — Unknown

*Why it appeared:* found while searching CD19; named in 5 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:CEMACABTAGENE ANSEGEDLEUCEL (CHEMBL5314816: Gene). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 6 registry/publication records; individual trials may be earlier | [NCT06500273 (development_stage_order)](https://clinicaltrials.gov/study/NCT06500273), [NCT06500273 (development_status)](https://clinicaltrials.gov/study/NCT06500273), [NCT04416984 (development_stage_order)](https://clinicaltrials.gov/study/NCT04416984) |
| Sponsors | Allogene Therapeutics | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT04416984 (lead_sponsor)](https://clinicaltrials.gov/study/NCT04416984), [NCT05714345 (lead_sponsor)](https://clinicaltrials.gov/study/NCT05714345), [NCT06500273 (lead_sponsor)](https://clinicaltrials.gov/study/NCT06500273) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*6 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT06500273 declare, and has any result been posted or presented? _(because: registered PHASE_2 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 9. Anbalcabtagene Autoleucel — Unknown

*Why it appeared:* found while searching CD19; named in 14 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of DRUG:ANBALCABTAGENE AUTOLEUCEL (CHEMBL5314655: Gene). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 4 registry/publication records; individual trials may be earlier | [NCT04836507 (development_stage_order)](https://clinicaltrials.gov/study/NCT04836507), [NCT04836507 (development_status)](https://clinicaltrials.gov/study/NCT04836507), [NCT07364396 (development_stage_order)](https://clinicaltrials.gov/study/NCT07364396) |
| Sponsors | Curocell Inc. | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT04836507 (lead_sponsor)](https://clinicaltrials.gov/study/NCT04836507), [NCT07364396 (lead_sponsor)](https://clinicaltrials.gov/study/NCT07364396) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* CAR_T

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*4 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT04836507 declare, and has any result been posted or presented? _(because: registered PHASE_2 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

### 10. AUTO3 — Unknown

*Why it appeared:* found while searching CD19; named in 1 source documents

**⚠️ Engine disagreement:** Target: shown UNKNOWN, engine gate PASS; Modality: shown SUPPORTED, engine gate UNKNOWN. Do not rely on either signal alone.

| Fact | Value | Status | Basis | Sources |
|---|---|---|---|---|
| Target | — | ❔ Unknown | found while searching CD19, but no authority record names its target; the search context is not evidence. The target gate nevertheless PASSED on a construct-level fact read from text; treat as unconfirmed until an authority or product source names it | — |
| Modality | CELL_THERAPY | ✅ Supported | ChEMBL_37 molecule type of NCIt:C162620 (Cell). The modality gate is nevertheless UNKNOWN (it reads a different, text-derived fact); the authority class is shown, the gate is unchanged | — |
| Stage | PHASE_2 | ✅ Supported | most advanced stage across 2 registry/publication records; individual trials may be earlier | [NCT03287817 (development_stage_order)](https://clinicaltrials.gov/study/NCT03287817), [NCT03287817 (development_status)](https://clinicaltrials.gov/study/NCT03287817) |
| Sponsors | Autolus Limited | ⚠️ Unverified | trial sponsors/collaborators named in registry records; the rights holder is not established | [NCT03287817 (lead_sponsor)](https://clinicaltrials.gov/study/NCT03287817) |
| Human efficacy | — | ❔ Unknown | no human efficacy statement was extracted; absence of extraction is not absence of data | — |

*Modality hint from trial text (not evidence):* MONOCLONAL_ANTIBODY

*Gate results:* identity.distinct_asset PASS; target.expression PASS; modality.required UNKNOWN; strategy.therapeutic_area PASS; strategy.indication PASS; evidence.minimum_stage PASS

*2 extracted claims failed the citation-entailment check and are not relied on.*

**Diligence questions** (most value-changing first):

1. **Biology / target** — Does the construct bind CD19, and is it the only antigen it binds? Confirm from a product description, label or company disclosure. _(because: target is known only from the search context)_
2. **Clinical readout** — What primary endpoint and readout timing does NCT03287817 declare, and has any result been posted or presented? _(because: registered PHASE_2 activity, no extracted efficacy data)_
3. **Safety / dosing** — What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the cited trials? (not extracted by the engine) _(because: cell-therapy product class)_
4. **Manufacturing / scale-up** — Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and capacity to supply a commercial launch. _(because: cell-therapy product class)_
5. **Rights** — Is it already approved, marketed or partnered, and who holds development and commercial rights by territory? Registry sponsors are not owners, and approval is not represented in this brief. _(because: ownership not established)_

*What would change the assessment:* modality.required: a source that settles this would move the candidate from Unknown; target: an authority record or product description naming the antigen

## E. Analyst conclusion

**Passed every engine gate** (read the gate basis before relying on it):

- _None._

**Review first** (target authority-supported, modality not contradicted; still Unknown on at least one gate):

- Brexucabtagene Autoleucel
- Breyanzi
- KYMRIAH

**Unresolved** (target or modality not established):

- CNCT19
- axi-cel
- KITE-753
- CC-97540
- ALLO-501A
- Anbalcabtagene Autoleucel
- AUTO3

**Excluded by the engine** (810; first 10 shown, alphabetical):

- 19-28z/IL-18 CAR T cells — target.expression: Canonical construct targets do not satisfy the configured expression.; strategy.indication: Observed indication conflicts with buyer requirement strategy.indication.
- 1A46 Drug Substance — strategy.indication: Observed indication conflicts with buyer requirement strategy.indication.
- 20-19 Tan BB06oz CAR T — strategy.indication: Observed indication conflicts with buyer requirement strategy.indication.
- 4SCAR-CD22/CD123/CD38/CD10/CD20/TSLPR — strategy.indication: Observed indication conflicts with buyer requirement strategy.indication.
- 4SCAR19/22 T cells — strategy.indication: Observed indication conflicts with buyer requirement strategy.indication.
- abatacept — target.expression: Canonical construct targets do not satisfy the configured expression.
- abemaciclib — target.expression: Canonical construct targets do not satisfy the configured expression.
- ABI-H0731 — strategy.indication: Observed indication conflicts with buyer requirement strategy.indication.
- abiraterone — target.expression: Canonical construct targets do not satisfy the configured expression.
- acalabrutinib — target.expression: Canonical construct targets do not satisfy the configured expression.

**Held back for low support but authority-confirmed on at least one requested target** (check manually):

- CART19

**Next research action:** Resolve `modality.required` by reading the cited sources: it is UNKNOWN for 10 of 10 shown candidates and is what keeps them out of the eligible set. Start with the candidates under 'review first'.

## Limitations

- Development demonstration on a frozen non-holdout run; not a validated scientific product.
- Run status INCOMPLETE: sources marked as blind spots were never searched; absent assets may simply be unseen.
- Eligibility is the engine's gate disposition. 'Review first' only means the target is authority-supported and the modality is not contradicted; it is not a recommendation or score.
- Human-PoC has no validated automatic confirmation route; efficacy passages are shown for reading only.
- Company lists are registry sponsors and collaborators, not rights holders.
- Stage is the most advanced trial phase seen in registry/publication records; marketing approval is not represented, so approved products appear at their latest trial phase.
- Trade names and INNs are not consolidated; the same product can appear twice (same authority record is flagged).
- 3768 low-support nominations were held back by the engine and are not shown.

**Sources never searched:** company_pipeline_or_presentation; company_press_release; conference_asco; conference_ash; conference_eha; sec_edgar

**Inputs:**

- `cd19_cell_therapy_bcl.yaml` sha256 `c897ed42a86d41b161a720f2f425ba26955e7de2ffb1c91c7c4ec7526256334e`
- `problem.yaml` sha256 `ccb91b7d9dc555edce49353deaa3757b38350221d5324d803444e811b1e54e92`
- `result.json` sha256 `2a423fb414d470cdfcb0677957f094c71fa6772ede90c43e51b6a0b2fa1df369`
- `shortlist.json` sha256 `f1af5ab469861873d2ebc2676e93a45222cda163e726cb6987b0e062d02566e7`

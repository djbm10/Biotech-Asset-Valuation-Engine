# CLDN18.2 gastric/GEJ: reference assessment (INTERNAL DEVELOPMENT)

The AI that wrote this ran in the same environment as the workflows it will score. It is not an independent human validation. As of 2026-10-29.

## Method
- I read the buyer YAML, `landscape_cldn18.csv` (62 rows), `field_provenance.csv`, `public_evidence.json`, the ClinicalTrials.gov snapshot and the openFDA snapshot.
- I judged every row from the evidence and treated the vendor cells only as claims to check. Most target and modality facts come from NCIt definitions and the trial intervention text.
- I ran about 10 web searches to check rights for ATG-022, SKB315, JS107, BL-M05D1, SHR-A1904, RC118, TORL-2-307, LM-302 and QLS31905/ANO31905.
- Facts I could not source are marked "(memory, unverified)" in the CSV.
- The scientific call and the transaction call are kept separate. A program can be scientifically IN and still rate LOW for this buyer.

## Identity groups
| Group | Rows |
|---|---|
| zolbetuximab | CL-01, CL-02 (IMAB362) |
| sonesitatug vedotin | CL-03 (AZD0901), CL-04 (CMG901), CL-05 |
| XNW27011 / ASP546C | CL-11, CL-12 |
| SYSA1801 / EO-3021 | CL-14, CL-15 |
| QLS31905 / ANO31905 (possible) | CL-20, CL-21. The match rests only on the shared code number; it is unverified. |

## Counts
- **IN: 30 rows, which is 25 distinct molecules after collapsing duplicates.**
- **OUT: 28.**
- **UNRESOLVED: 4.**
  - ANO31905: modality unknown; pancreatic trial only.
  - BDC-4182: an immune-stimulating antibody conjugate (ISAC, TLR7/8 payload). It is neither a cytotoxic ADC nor a bispecific, so it sits on the edge of the buyer's scope.
  - DR30303: the antibody format is not confirmed.
  - Bio-008: no target is disclosed.

**IN molecules:** sonesitatug vedotin, IBI343, LM-302, SHR-A1904, ASP2138, XNW27011, givastomig, EO-3021/SYSA1801, ATG-022, AZD5863, QLS31905, JS107, RC118, SKB315, BL-M05D1, spevatamig, SOT102, AMG 910, TORL-2-307-ADC, LCB02A, Q-1802, TQB2103, SG1906, VBC108, AK132 and DA-3501.

I applied the gastric criterion leniently:
- Pan-tumour CLDN18.2 trials count as gastric-relevant.
- Discontinued programs (EO-3021, SOT102, AMG 910) are still scientifically IN. Their discontinuation shows up only in the transaction fields.

## Top transaction candidates for this buyer
Selection criteria: ADC preferred, Phase 2 or later, active, not held by large pharma.

1. **SKB315 (Kelun-Biotech), ADC.** MSD returned the global rights in August 2024, and Kelun says it will explore international markets. Programs: Phase 1, plus a Phase 2 first-line gastric/GEJ combination study.
   - *Uncertainty:* whether Kelun wants a partner for ex-China rights or plans to go alone; the Phase 2 is not yet recruiting.
2. **ATG-022 (Antengene), ADC.** Phase 3 versus investigator's choice in gastric/GEJ, FDA orphan drug designation for gastric cancer, and no licence found. The MSD agreement is only a pembrolizumab clinical collaboration. Antengene has out-licensed another asset (ATG-201 to UCB).
   - *Uncertainty:* the upstream origin of the asset, and whether Antengene really holds global rights. That is inferred from finding no deal.
3. **LM-302 (LaNova / Sino Biopharm), ADC.** Phase 3 in China. BMS (via its Turning Point acquisition) gave back the ex-Greater China and Korea rights.
   - *Uncertainty:* LaNova now sits inside Sino Biopharm, which is a large Chinese pharma, and it is not known whether it wants an ex-China partner.
4. **JS107 (Junshi), ADC.** Two Phase 3 trials in gastric/GEJ (second-line or later, and first-line combination). A secondary report gives a Phase 1 ORR of about 31%. No ex-China licence found.
   - *Uncertainty:* availability is not evidenced. Junshi out-licenses selectively.
5. **BL-M05D1 (Baili/SystImmune), ADC.** Phase 3 in second-line gastric/GEJ. The BMS deal covers iza-bren only.
   - *Uncertainty:* whether BMS holds any right of first negotiation or similar on Baili's other assets (unknown), and how rights split between Baili and SystImmune.
6. **QLS31905 (Qilu), CLDN18.2×CD3 T-cell engager.** Phase 3 (n=602) in first-line gastric/GEJ. It is not an ADC, so it scores lower on manufacturing fit.
   - *Uncertainty:* the relationship to Anova/ANO31905. It may already be spun out to a NewCo.
7. **SHR-A1904 (Hengrui), ADC.** Phase 3.
   - *Uncertainty:* Merck KGaA holds an option on ex-mainland-China rights, and I could not establish whether it was exercised, declined or lapsed. Rate it MEDIUM only after diligence.
8. **RC118 (RemeGen), ADC.** Phase 1/2 gastric data presented at ESMO 2024, FDA orphan designations, and no ex-China partner found.
   - *Uncertainty:* the registry records have been stale since early 2025, so development may have slowed.
9. **Givastomig (I-Mab / ABL Bio), CLDN18.2×4-1BB bispecific.** Phase 2 in first-line gastric. Ex-China rights sit with two small biotechs.
   - *Uncertainty:* the co-ownership complicates a deal, and it is not an ADC.
10. **Early ADCs, as a watch list:** DA-3501, LCB02A, TORL-2-307-ADC (whose status conflicts between sources) and VBC108 (a bispecific ADC). All are Phase 1 with thin human data.

**Deliberately excluded:** sonesitatug vedotin (AstraZeneca), IBI343 (Takeda ex-China), XNW27011 (Astellas), ASP2138 (Astellas) and AZD5863 (AstraZeneca). All have strong science but are held by large pharma.

## Traps
- **Duplicate rows for one molecule:** sonesitatug vedotin appears three times; zolbetuximab, XNW27011 and EO-3021 twice each. Counting each row as a separate program is wrong.
- **Wrong vendor cells:**
  - IBI343 is labelled "Imaging agent" but is an ADC.
  - LCB02A and BDC-4182 are labelled "Monoclonal antibody".
  - Zolbetuximab's target cell lists HER2.
  - ASKB589's target cell lists PD-1.
  - FG-B901, RC148, rilvegostomig, volrustomig, QL1706 and zanidatamab are combination partners or non-CLDN18.2 agents. They are in the list only because they share trials.
  - Zanidatamab's company is given as AACR.
- **Mistaking a trial collaborator for a rights holder:** the "Partnerships" column lists MSD for ATG-022 and spevatamig, BMS for TST001, and Lilly/GSK for EO-3021. None of these is a licence.
- **Rights returns the export does not show:** the vendor rows for LM-302 (BMS terminated) and SKB315 (MSD returned) say nothing about the returns. A naive analyst would wrongly mark them as large-pharma-held, or as free with no history.
- **Rights held by large pharma that the Company column hides:** IBI343 shows "Innovent" but Takeda holds ex-China rights. XNW27011 is held by Astellas and CMG901 by AstraZeneca.
- **Marketed or approved products:**
  - Zolbetuximab (Vyloy) is approved in the US and EU, and the vendor also lists it as "Phase 4".
  - CT041 is conditionally approved in China, but the vendor row says "Phase 2".
- **Terminated programs:** EO-3021 was discontinued in 2025; also SOT102, AMG 910, BNT141, FL-301, LM-102, SPX-101, LB4330 and DR30303. "UNKNOWN" registry status (SYSA1801, Q-1802, AK132, TQB2103) does not mean the program is active.
- **Modality scope:** the radioligand, the ISAC, the IL-10 fusion and the mRNA-encoded antibody are not ADC or bispecific programs.

## Uncertainty list
- Whether Merck KGaA exercised its SHR-A1904 option.
- Whether ATG-022's global rights sit with Antengene, and what its upstream licensor obligations are.
- The current position of LM-302 inside Sino Biopharm.
- The relationship between QLS31905 and ANO31905.
- The status of TORL-2-307: active-not-recruiting in the registry versus discontinued in one database.
- What happened to EO-3021 / SYSA1801 rights after Elevation stopped development.
- Whether RC118 development is still active.
- The originator of AZD5863 (Harbour BioMed is from memory, unverified), the originator of ATG-022, and whether ASP2138 was developed in-house (memory, unverified).
- **No program has public evidence that its owner is seeking a partner**, apart from Kelun's general statement about international expansion. Under the buyer's rule ("availability must be evidenced"), no candidate is EVIDENCED_AVAILABLE.
- The rights searches were capped at about 10 queries. Deals reported only in Chinese-language sources may have been missed.

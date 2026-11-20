# BD Finance Learnings, Investment-Research Analogues, and BVE Future Vision

**Date:** 2026-11-19  
**Status:** Research notes / hypotheses / future ideas only; **NOT** an approved implementation plan or evidence of validated model performance.  
**Location:** Beside `docs/vision_reports/future_fixes.md`.  
**Scope:** Public information and generalized, non-confidential workflow discussion only. Do not put private advice, internal deal details, or nonpublic Vertex data into this repository.

## 1. The core question

Could BVE improve an acquirer's deal decisions by giving BD & Strategic Finance better-supported, more timely, and/or more accurately calibrated inputs to valuation — **without assuming** existing finance, clinical, commercial, and R&D teams are unsophisticated?

**Current conclusion:** The existence of an internal Excel valuation process does **not** imply that the valuation or its inputs are weak. Most obvious features (clinical diligence, revenue forecasts, development budgets, transaction comparisons, scenario models) likely exist already. A BVE feature has value only if it proves incremental accuracy, integration/speed, or independently relevant new insight.

## 2. Reconstructed Vertex BD Finance workflow (public evidence vs inference)

### Supported by public descriptions

Vertex's BD & Strategic Finance job posting explicitly describes:
- Partnering with BD and finance on transactions aligned with strategy;
- Building financial valuation models for M&A, licensing, collaborations, and investments;
- Valuing assets/businesses, scenario analysis, outside-in research, and finance leadership input.

Other Vertex finance/forecasting job descriptions describe financial modeling, investment cases, gross-to-net/access forecasts, budget versus actuals, cross-functional analysis, and sensitivity analysis.

**Source:** [Vertex Associate Director BD & Strategic Finance](https://vrtx.wd501.myworkdayjobs.com/en-US/Vertex_Careers/job/Associate-Director-BD-and-Strategic-Finance_REQ-29546); [Vertex FP&A senior analyst](https://vrtx.wd501.myworkdayjobs.com/en-US/Vertex_Careers/job/Financial-Planning---Analysis-Senior-Analyst_REQ-30317); [Vertex FP&A finance partner](https://vrtx.wd501.myworkdayjobs.com/vertex_careers/job/Financial-Planning---Analysis-Associate-Director_REQ-29310).

### Simplified hypothetical workflow

1. **Strategy / BD / external innovation:** Identify opportunity and strategic rationale.
2. **Scientists / clinical / regulatory:** Assess target biology, evidence, safety, development risks, approval path; might provide phase-specific approval probabilities.
3. **Commercial / forecasting / market access:** Estimate eligible patients, net price, uptake, competition, annual sales; likely have their own sophisticated models and primary/proprietary data.
4. **Clinical operations / CMC / R&D / finance:** Estimate remaining trial expenses, commercial/manufacturing costs, launch timing, and execution risk; likely sophisticated internal budgets.
5. **BD Transactions:** Develop actual deal alternatives and negotiated terms (upfront, milestones, royalties, profit shares, control, rights).
6. **BD & Strategic Finance:** Reconcile cross-functional assumptions; model risk-adjusted cash flows, financial impact, synergies, option/acquisition/license alternatives, sensitivities and appropriate price/terms; explain financial trade-offs to decision-makers.
7. **Leadership / governance:** Make approval/negotiation decision, considering financial, strategic, legal, scientific, and other considerations.

**This is a reconstruction, not confirmed internal handoff sequence or a copy of a Vertex workbook.** Not all deals use all steps, and financial teams may originate, challenge, or refine inputs themselves rather than simply receiving finished numbers.

### What the likely workbook contains (inferred)

| Likely worksheet | Illustrative contents |
|---|---|
| Assumptions | Valuation date, territory, deal perimeter, ownership, scenario choices |
| Clinical/timing | Approval probabilities, development gates, launch timing, indication scenarios |
| Patient/revenue | Patient funnel; pricing/gross-to-net; penetration; commercial curves; LOE |
| Costs | Trial spend, CMC, COGS, SG&A, capex, taxes, working capital |
| Risk-adjusted valuation | Discounted cash flows and development costs; rNPV |
| Deal structure | Acquisition price / cash balance / debt, license upfront, milestones, royalties, profit splits |
| Sensitivities | Base/bear/bull; breakeven economics; value-at-risk and price ceiling |
| Consolidated effects | Cash needs, earnings/cash-flow impact, financing constraints and potential synergies |
| Decision summary | Offer-price range, key financial value drivers, investment rationale and conditions |

**Ultimate finance goal:** Recommend whether and at what terms an opportunity creates sufficient economic value for Vertex. **rNPV is central, but not sufficient on its own.** An acquisition also includes company cash/debt, multiple assets, liabilities, synergies, financing, optionality and governance. A royalty/license deal is not equivalent to an all-cash purchase. The apparent spread between asset rNPV and deal consideration is not by itself a complete deal recommendation.

### What we do NOT know

- Exactly which proprietary datasets, statistical models, algorithms, Excel templates, or external vendors Vertex uses;
- Whether their PoS assumptions are data-trained, clinician-elicited, or hybrid;
- Whether upstream forecasts, competitive alerts, and evidence-to-valuation updates are automated;
- Whether any purported BVE capabilities would be novel or better than Vertex's current workflow.

**Avoid the false premise that adding historical trials, revenue analogs, deal comps or richer Excel visuals is an unmet need; Vertex may already have each.**

## 3. What leading biotech investors and vendors do publicly

| Example | Verified public description | What to learn, not claim |
|---|---|---|
| **RA Capital / TechAtlas** | Scientists map therapeutic/competitive landscapes and connect biological evidence, patient needs, target programs and investment conviction | Structured cross-program science, transparent comparisons, expert contextualization |
| **OrbiMed public equities** | Investment approach spans clinical development, regulatory catalysts, product launches, company fundamentals and biotech M&A | Valuation in context of milestones and changing competitive facts |
| **MIT / Novartis PoS challenge** | Cross-disciplinary teams applied machine learning to historical drug-indication outcomes using scientific, sponsor and trial information | Combining disciplined labels, feature engineering, expert judgment and held-out evaluation can improve PoS |
| **BIO / QLS / Informa (Citeline)** | Analyzed thousands of drug-program phase transitions; QLS examined 200+ drug, indication, sponsor and trial features | Outcome-linked datasets and calibrated, interpretable risk estimates |
| **Citeline Trialtrove / Pharmaprojects** | Expert-curated clinical and pipeline datasets, benchmarks, cross-program relationships | Public registry data alone lacks fully curated program outcomes and intervention identity |

Public sources:
- https://www.racap.com/techatlas
- https://www.biotechgt.com/about-us/how-the-team-invests/
- https://pmc.ncbi.nlm.nih.gov/articles/PMC8369231/
- https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020
- https://citeline.com/products-services/trialtrove/
- https://citeline.com/products-services/pharmaprojects/

**Do not claim access to their private alpha, proprietary model internals, detailed analyst procedures or decision logs.**

## 4. Three credible BVE value hypotheses (not established gaps)

### A. Measurably better predictive accuracy

**Illustration:** An asset has an expert-assigned 50% probability of eventual approval. A properly trained and externally validated program-level historical model estimates 35%, using as-of-date clinical evidence and matched analogs.

**Why it matters:** If independent future holdouts show better calibrated probabilities than phase/TA and human baseline forecasts, downstream rNPV improves.

**Proof needed:** Out-of-time Brier/log loss and calibration gains, confidence intervals, comparable prediction horizon, valid population, clinical review. AUC alone is insufficient. If not better: retain expert estimate, use model as secondary evidence. PoS improvement is a separate current priority.

### B. Cross-functional intelligence, faster

**Illustration:** A competitor announces a negative pivotal trial. A research agent detects it, resolves the compound/target/MoA/indication, identifies which asset and assumption might be affected, cites the original source, proposes an *unapplied* change and shows delta in rNPV. Scientific and finance owners approve or reject.

**Why it matters:** Potentially shortens handoffs across diligence, forecasting and finance without replacing expert models.

**Proof needed:** Compare to established workflow: hours saved, coverage, false positives, missed material events, reviewer burden, auditability. If Vertex already has an effective pipeline, little incremental value.

### C. Genuinely independent relevant insight

**Illustration:** A historical launch cohort or competitor mechanism reveals an overlooked limitation to eligible patient share. BVE links a dated source, explains relevance and shows its impact on a forecast assumption — **not** an unsupported assertion that the existing commercial team missed it.

**Proof needed:** Blind expert review documenting novel, correct, material findings vs existing diligence; measure false positives and repeatability.

### Product vision — optional, not committed

**Evidence → assumption provenance/change proposal → expert review → controlled finance-model integration → scenario/delta report → decisions/outcome feedback.**

Keep **Excel compatibility**, human-owned assumptions and version history. Do not automate deal approval, invent financial facts, put confidential data in external systems, or assert an AI-generated point estimate is more accurate than human diligence without a real head-to-head test.

## 5. More speculative ideas (may already exist elsewhere)

- Historically matched clinical success/launch/timeline analogs with match rationale, counts and uncertainty.
- Program-level rather than trial-row success labels; same molecule across several trials is not independent evidence.
- Evidence-to-dollar explanations and independent value gap decomposition.
- Commercial model inputs backed by patient funnel and launches **where legally sourced**.
- Deal structure comparison and value-of-information: license now vs wait for next trial data.
- Analyst-editable assumptions with source dates and approvals.
- Repeated retrospective replay (what would BVE have known on a specific historical date?).
- Guardrails for correlated assumptions, double-counting PoS/discount risks and uncertainty.

## 6. Current PoS reality in committed BVE (snapshot at writing)

- `src/bve/models/pos_model.py`: heuristic log-odds adjustments around published phase/therapeutic-area priors.
- `src/bve/models/pos_statistical.py`: **synthetic heuristic-mirror training**, explicitly `IS_EMPIRICALLY_CALIBRATED=False`; not independent outcome calibration.
- `src/bve/empirical/pos_outcome.py`: real phase-transition outcome schema and provenance fields.
- `src/bve/empirical/features.py`: 11 binary overlay indicators (MoA, biomarker, endpoint, safety, competition).
- `src/bve/empirical/overlay_model.py`: trainable L2 logistic overlay with time split, sparse-feature guards, and optional sign gates.
- `research/overlay_hardening_report.md`: **historical Sprint 9 experiment**, 135 oncology records (59 training, 76 test), fitted overlay Brier 0.1940 vs heuristic-adjusted empirical 0.1995; AUC 0.7695 vs 0.7082; **ECE worse: 0.1742 vs 0.1062**. Its own promotion verdict was **NOT PROMOTABLE**. This tiny, curated sample is not an institutional-grade external validation.
- `docs/Tool Updates/accuracy-and-calibration.md`: a later claim-ledger report states 37 programs had source-draft packets but **zero approved/promotable claims** at that snapshot; do not conflate with deployed/scored evidence.
- `src/bve/models/probability_stack.py`: broader layered technical/regulatory/commercial heuristic weighting; not evidence that composite weights have been empirically optimized.
- `src/bve/empirical/pos_mode.py`: heuristic remains default per module comment. Exact live runtime settings require configuration verification.

**Important code-audit question:** `fit_overlay_time_split` splits by **outcome date**, not necessarily a simulated prediction-as-of date, and permits records with missing outcome dates into training. Audit *all* training base rates, derived features, input availability and hyperparameter tuning for time leakage before claiming a genuinely prospective test.

## 7. Proposed PoS research pathway (Lane 1 candidate; do not modify live parameters)

**Goal definition first:** Distinguish:
1. Probability an individual trial meets predefined efficacy/safety endpoints;
2. Probability a **drug–indication program** advances to next phase;
3. Probability of **eventual FDA approval conditional on reaching a stage and available evidence**;
4. Probability of success of a *planned future study* given uncertain treatment effect (Bayesian 'assurance').

These are different labels and should not share 'accuracy' claims.

### Historical dataset assembly

1. Registry foundation: ClinicalTrials.gov API v2 or CTTI **AACT**, with study ID, intervention, sponsor, condition, phase, trial protocol, start/completion dates, status, enrollment, design, eligibility, outcomes, results and locations.
2. Longitudinal history: AACT dated snapshots (not just latest snapshot), trial record version histories, dated archived regulatory/pipeline sources. Access to AACT full downloads currently requires free account; snapshots are not a complete substitute for all historical field revisions.
3. Approval truth: FDA Drugs@FDA / Orange Book / biologic approvals / FDA reviews; map drug synonyms to actual ingredient and **indication/label**, with original approval dates. Regulatory approval is not the same as trial COMPLETED.
4. Cross-study program resolution: Normalize molecule (synonyms, investigational codes, combinations, formulation), sponsor, disease, biomarker, line of therapy; group NCT studies into **drug × indication × development path**; track transfer and expansion.
5. Program endpoints: Define advances, terminates, rejected, approved; adjudicate ambiguous/stale/suspended cases; treat still-ongoing programs as right-censored or run a survival/competing-risk model, never automatically label as failures.
6. Dated features: phase, indication, modality, molecular target/MoA, human genetic/clinical target precedent, prior same-drug data, biomarker enrichment, trial endpoints, controls, randomization, masking, planned enrollment, eligibility restrictiveness, sponsor previous track record, FDA designations *if known then*, safety/efficacy signals that predate the prediction date, and competitor landscape.
7. Provenance: Store raw record, snapshot, source ID/URL, `known_at`, extraction date, intervention match confidence, label adjudication/reviewer, missingness and licenses. No result/status after the prediction date in inputs.

### Modeling, evaluation and safeguards

1. Build **simple honest baselines first**: BIO-type phase/therapy-area historical rates with hierarchical smoothing; BVE's current heuristic; logistic regression with shrinkage.
2. Fit interpretable coefficients on historical outcomes: `logit(P)=logit(P_phase+TA)+β1*biomarker+β2*validated_MoA+β3*endpoint_design+... `. Estimate beta via penalized likelihood **only on past data**; use regularization and/or hierarchical partial pooling.
3. Compare gradient boosted trees (LightGBM/XGBoost/CatBoost) for nonlinearities and interactions; consider HINT/deep multimodal and Bayesian clinical endpoint models later, only if corpus quality and size justify them.
4. Require train/validation/test **chronological** folds by decision date, last fold untouched for final proof; group repeated trials/programs by drug–indication and check shared active ingredients/sponsors for leakage. Nested tuning and post-hoc calibration **inside training/validation**, never test.
5. Fix incomplete follow-up with right-censoring or maturity rules. Clinical failures resolve earlier than approvals: naive recent-year cohorts are dangerously biased.
6. Evaluate **Brier score**, log loss, calibration slope/intercept and reliability curves **first** for finance use; ROC-AUC/PR-AUC second for ranking. Report by phase/therapy area/modality, prevalence, missingness, horizon, time period and bootstrap CIs. Include predictions-per-bin and rates.
7. Ablation studies: baseline; +trial design; +mechanism/clinical precedent; +sponsor history; +regulatory; +clinical effect data. Count marginal improvement **over** the best previous model, not anecdotes.
8. Audit domain shifts, sponsor duplicates, reverse-causality (e.g., 'terminated' status), leakage via any post-readout claims, data license, coverage of unseen classes, stale targets, and false precision.
9. Shadow-test with one or more entirely new annual cohorts; require predefined promotion gates and external clinical reviewer approvals. Under `ROADMAP_LOCK.md`, no new Lane 1 parameters or industry base-rate modifications absent Brier/AUC holdout evidence and appropriate signoff.

**Recommended first concrete deliverable:** A dated, reproducible **Phase II drug–indication → eventual FDA approval** corpus and frozen prospective-style split, plus phase/TA baseline and a regularized 15–25 feature model. Also build separately a Phase II → Phase III transition model for quicker labels. Do not promise to harvest *all* historic clinical trials: the registry is neither a complete drug-development universe nor a ready-made approval-labeled ML dataset.

## 8. External PoS research to reproduce / critique

- [BIO / QLS / Informa 2011–2020](https://go.bio.org/rs/490-EHZ-999/images/ClinicalDevelopmentSuccessRates2011_2020.pdf): 12,728 phase transitions / 9,704 programs; QLS 200+ features; uses more-recent holdout, reports broadly plausible calibration. Proprietary program data; PDF not raw training dataset.
- [Lo / Siah / Wong (2019) MIT, statistical imputation](https://hdsr.mitpress.mit.edu/pub/ct67j043/release/5): over 140 predictors; reported AUC 0.78 Phase II→approval, 0.81 Phase III→approval with proprietary data.
- [Novartis–MIT prediction challenge (2021)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8369231/): winning Phase II→approval AUC **0.88** (95% CI 0.85–0.90) using engineered features / XGBoost / Bayesian logistic regression; **not** proof that a public-only model can replicate. Critically reports censoring/late-period outcome artifact.
- [HINT/TOP benchmark (2022)](https://pmc.ncbi.nlm.nih.gov/articles/PMC9024011/): 17,538 labeled trials, multimodal features and chronological split; trial endpoint success is **not** program FDA approval.
- [Howard et al., Scientific Reports (2026)](https://www.nature.com/articles/s41598-026-64883-0): 35,662 transitions / 27,900 drugs; adding trial design improved discrimination modestly in phase-specific models (Phase III AUC improvement about 0.024 in their comparison); proprietary dataset and different prediction endpoint.
- [Clinical trial termination model (2026)](https://link.springer.com/article/10.1007/s44163-026-01965-y): temporal test AUC ~0.80 for **termination**, not approval; recalibration materially changed probability quality.
- [PoS / assurance scoping review (2025)](https://onlinelibrary.wiley.com/doi/full/10.1002/cpt.3571): Bayesian design-prior-based trial success conditional on plausible treatment effects; different from development-to-approval PoS.
- [AACT](https://aact.ctti-clinicaltrials.org/landing) and [ClinicalTrials.gov data download](https://clinicaltrials.gov/data-api/how-download-study-records): public data foundation.

## 9. Decision rule for future work

**Near term:** Validate PoS in a research branch, protect the live valuation model, and produce an auditable holdout comparison.  
**Later:** Test BVE's cross-functional evidence-to-model integration and independent insight hypotheses against real users' established workflows.  
**Do not** infer a Vertex product-market fit or claim stronger predictions until the improvement is demonstrated against appropriate baselines.

Related: `docs/vision_reports/future_fixes.md`, `TASKS.md`, `ROADMAP_LOCK.md`, `CHANGE_REQUEST_TEMPLATE.md`.

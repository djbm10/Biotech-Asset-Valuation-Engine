Scoring System — Detailed Technical Explanation

  Part 1: Single Asset Valuation

  The valuation engine runs six sequential models. Each model produces a structured result object that feeds the next. No
  model re-derives what a prior model already computed.

  ---
  Step 1 — POS Layer 1: Qualitative Log-Odds Adjusters

  What it does: Takes an industry base rate for the phase/TA combination and shifts it up or down based on eight
  trial-specific signals.

  Base rates (from industry_assumptions.yaml):
┌──────────────────────────────┬─────────┬─────────┬─────────┬─────────┐
│       Therapeutic Area       │ Phase 1 │ Phase 2 │ Phase 3 │ NDA/BLA │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ All                          │ 64.0%   │ 37.0%   │ 60.0%   │ 87.0%   │
│ Other                        │ 64.0%   │ 37.0%   │ 60.0%   │ 87.0%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Oncology                     │ 48.9%   │ 24.8%   │ 49.5%   │ 91.6%   │
│ Oncology — Solid Tumors      │ 48.9%   │ 23.4%   │ 42.9%   │ 92.9%   │
│ Hematology                   │ 50.1%   │ 27.8%   │ 60.0%   │ 90.0%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Rare Disease                 │ 67.4%   │ 44.6%   │ 60.4%   │ 93.6%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ CNS                          │ 47.7%   │ 26.8%   │ 53.1%   │ 86.7%   │
│ Psychiatry                   │ 52.7%   │ 26.8%   │ 56.3%   │ 91.2%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Cardiovascular               │ 50.0%   │ 29.0%   │ 55.2%   │ 82.5%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Immunology                   │ 55.2%   │ 34.6%   │ 65.3%   │ 94.1%   │
│ Dermatology                  │ 63.6%   │ 38.6%   │ 60.0%   │ 88.4%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Metabolic                    │ 61.8%   │ 45.0%   │ 63.6%   │ 87.5%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Gastroenterology             │ 46.7%   │ 34.2%   │ 57.1%   │ 90.9%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Infectious Disease           │ 57.8%   │ 38.4%   │ 64.0%   │ 92.9%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Ophthalmology                │ 71.6%   │ 35.5%   │ 62.2%   │ 91.1%   │
├──────────────────────────────┼─────────┼─────────┼─────────┼─────────┤
│ Pulmonary                    │ 55.9%   │ 25.2%   │ 64.5%   │ 88.6%   │
│ Renal                        │ 63.6%   │ 38.6%   │ 60.0%   │ 88.4%   │
└──────────────────────────────┴─────────┴─────────┴─────────┴─────────┘

  Why log-odds: If you adjust probabilities by multiplying or adding directly, results can exceed 1.0 or go below 0.0, and
   compound adjustments behave inconsistently near the extremes. Log-odds space maps (0,1) → (−∞, +∞), so adjusters add
  linearly and the final result always converts back to a valid probability. A +0.35 log-odds shift on a 32% base rate
  (oncology Phase 2) produces:

  base log-odds = log(0.32 / 0.68) = −0.754
  adjusted = −0.754 + 0.35 = −0.404
  final POS = 1 / (1 + e^0.404) = 40.0%

  Eight adjusters with exact values:

  Endpoint Type — what outcome is being measured:
 ┌─────────────────────────────────────────────┬────────────────┬─────────────────────────────────────────────┐
│                    Value                    │ Log-Odds Shift │                   Reason                    │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ ONCOLOGY — SOLID TUMORS                     │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ OS                                          │ +0.45          │ Strongest; direct survival benefit          │
│ EFS / DFS                                   │ +0.30          │ Strong, especially curative settings        │
│ PFS                                         │ +0.15          │ Accepted often, but not always OS-linked    │
│ ORR                                         │ −0.05 to 0.00  │ Useful for accelerated approval             │
│ DoR                                         │ 0.00           │ Strong support if ORR is high               │
│ CR / PR                                     │ −0.05          │ Response depth, not enough alone            │
│ ctDNA / molecular response                  │ −0.25 to −0.10 │ Promising, context-specific                 │
│ QoL / symptom improvement                   │ 0.00 to +0.15  │ Strong if validated and meaningful          │
│ PD biomarker only                           │ −0.55          │ Shows biology, not patient benefit          │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ ONCOLOGY — HEMATOLOGY                       │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ OS                                          │ +0.45          │ Strongest                                   │
│ EFS / PFS                                   │ +0.25 to +0.35 │ Often very meaningful                       │
│ CR / CRi                                    │ +0.15 to +0.25 │ Very important in blood cancers             │
│ MRD negativity                              │ 0.00 to +0.25  │ Strong in some settings                     │
│ DoR                                         │ +0.10          │ Durability matters a lot                    │
│ Transfusion independence                    │ +0.10 to +0.25 │ Strong in MDS/blood disorders               │
│ Hematologic response only                   │ −0.05 to +0.10 │ Depends on disease                          │
│ Biomarker only                              │ −0.40 to −0.55 │ Weak unless tightly validated               │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ RARE DISEASE                                │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Survival / ventilator-free survival         │ +0.45          │ Direct clinical benefit                     │
│ Functional improvement                      │ +0.25 to +0.40 │ Very important if validated                 │
│ Event reduction                             │ +0.20 to +0.35 │ Fewer crises, attacks, hospitalizations     │
│ Disease-specific scale                      │ +0.10 to +0.30 │ Depends on validation                       │
│ Caregiver / patient-reported outcome        │ 0.00 to +0.20  │ Strong if validated and meaningful          │
│ Biomarker correction                        │ −0.20 to +0.20 │ Depends on biomarker validation             │
│ Protein expression only                     │ −0.30 to 0.00  │ Better if directly disease-causal           │
│ PD biomarker only                           │ −0.55          │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ CARDIOVASCULAR                              │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ All-cause mortality                         │ +0.45          │ Strongest                                   │
│ CV death                                    │ +0.45          │ Direct hard outcome                         │
│ MACE                                        │ +0.40          │ Death/MI/stroke composite                   │
│ Hospitalization reduction                   │ +0.25 to +0.35 │ Strong, especially heart failure            │
│ Stroke / MI reduction                       │ +0.35 to +0.45 │ Hard clinical events                        │
│ LDL-C reduction                             │ +0.10 to +0.25 │ Validated surrogate                         │
│ Blood pressure reduction                    │ +0.10 to +0.20 │ Validated surrogate                         │
│ Imaging/plaque regression                   │ −0.10 to 0.00  │ Weaker unless tied to outcomes              │
│ Biomarker only                              │ −0.40 to −0.55 │ Usually weak alone                          │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ METABOLIC / ENDOCRINE                       │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Hard outcomes: CV events, mortality         │ +0.40 to +0.45 │ Strongest                                   │
│ HbA1c                                       │ +0.15 to +0.25 │ Validated diabetes endpoint                 │
│ Weight loss %                               │ +0.15 to +0.30 │ Strong in obesity if meaningful             │
│ MASH fibrosis improvement                   │ +0.20 to +0.35 │ Important regulatory/commercial endpoint    │
│ MASH resolution                             │ +0.10 to +0.25 │ Useful but context-dependent                │
│ Liver enzymes                               │ −0.25 to −0.10 │ Weak surrogate                              │
│ Insulin sensitivity markers                 │ −0.25 to −0.10 │ Usually supportive                          │
│ Biomarker only                              │ −0.55          │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ IMMUNOLOGY / INFLAMMATION                   │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Clinical remission                          │ +0.30 to +0.40 │ Strong patient-relevant endpoint            │
│ Steroid-free remission                      │ +0.35          │ Very meaningful                             │
│ Endoscopic remission / healing              │ +0.20 to +0.35 │ Strong in IBD                               │
│ ACR50/70                                    │ +0.20 to +0.30 │ Stronger than ACR20                         │
│ ACR20                                       │ +0.05 to +0.15 │ Accepted but modest bar                     │
│ PASI90/100                                  │ +0.25 to +0.35 │ Strong psoriasis endpoint                   │
│ PASI75                                      │ +0.10 to +0.20 │ Accepted but lower bar                      │
│ EASI75/90                                   │ +0.10 to +0.30 │ Strong in atopic dermatitis                 │
│ Flare reduction                             │ +0.15 to +0.30 │ Important in lupus/vasculitis               │
│ Biomarkers only                             │ −0.40 to −0.55 │ Usually weak alone                          │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ CNS / NEUROLOGY                             │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Mortality / survival                        │ +0.45          │ Strongest                                   │
│ Disability progression                      │ +0.30 to +0.40 │ Strong if objective                         │
│ Relapse reduction                           │ +0.25 to +0.35 │ Strong in MS                                │
│ Seizure frequency reduction                 │ +0.25 to +0.35 │ Strong in epilepsy                          │
│ Functional scales: ALSFRS-R, UPDRS, CDR-SB  │ +0.05 to +0.25 │ Important but noisy                         │
│ ADAS-Cog / cognitive scales                 │ 0.00 to +0.15  │ Accepted but variable                       │
│ MRI lesions in MS                           │ +0.05 to +0.20 │ Useful surrogate                            │
│ Amyloid/tau/NfL biomarkers                  │ −0.30 to +0.05 │ Disease/context-specific                    │
│ Biomarker only                              │ −0.55          │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ PSYCHIATRY                                  │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Relapse prevention                          │ +0.25 to +0.35 │ Stronger than short-term symptoms           │
│ Remission rate                              │ +0.15 to +0.25 │ Clinically meaningful                       │
│ Response rate                               │ +0.05 to +0.15 │ Useful but threshold-dependent              │
│ MADRS / HAM-D / PANSS / Y-BOCS              │ 0.00 to +0.15  │ Accepted but noisy                          │
│ Functional improvement                      │ +0.10 to +0.25 │ Important if validated                      │
│ Digital/behavioral biomarkers               │ −0.30 to −0.10 │ Emerging                                    │
│ Biomarker only                              │ −0.55          │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ INFECTIOUS DISEASE — ANTIVIRALS/ANTIBIOTICS │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Mortality reduction                         │ +0.45          │ Strongest                                   │
│ Hospitalization reduction                   │ +0.35 to +0.45 │ Strong                                      │
│ Clinical cure                               │ +0.25 to +0.40 │ Accepted and meaningful                     │
│ Microbiological eradication                 │ +0.10 to +0.25 │ Stronger when tied to cure                  │
│ Viral load reduction                        │ 0.00 to +0.25  │ Validated in some viruses                   │
│ Time to symptom resolution                  │ 0.00 to +0.15  │ Useful but softer                           │
│ Resistance prevention                       │ 0.00 to +0.15  │ Supportive                                  │
│ Biomarker only                              │ −0.40 to −0.55 │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ VACCINES                                    │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Disease prevention                          │ +0.45          │ Strongest                                   │
│ Severe disease prevention                   │ +0.45          │ Very strong                                 │
│ Hospitalization/death reduction             │ +0.45          │ Hard clinical benefit                       │
│ Infection prevention                        │ +0.25 to +0.35 │ Strong, depending disease                   │
│ Immunobridging antibody titers              │ 0.00 to +0.20  │ Accepted in some settings                   │
│ Neutralizing antibody response              │ −0.10 to +0.15 │ Context-dependent                           │
│ T-cell response only                        │ −0.30 to −0.10 │ Usually supportive                          │
│ Biomarker only                              │ −0.55          │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ PULMONARY                                   │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Mortality / transplant-free survival        │ +0.45          │ Strongest                                   │
│ Hospitalization reduction                   │ +0.35          │ Strong                                      │
│ Exacerbation reduction                      │ +0.25 to +0.35 │ Very important in asthma/COPD               │
│ FEV1                                        │ +0.10 to +0.25 │ Validated, but not always sufficient        │
│ 6-minute walk distance                      │ +0.10 to +0.25 │ Useful in pulmonary hypertension            │
│ PVR / hemodynamics                          │ 0.00 to +0.20  │ Stronger in pulmonary hypertension          │
│ PRO breathing scores                        │ 0.00 to +0.15  │ Supportive                                  │
│ Biomarker only                              │ −0.55          │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ RENAL                                       │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Kidney failure / dialysis / transplant      │ +0.45          │ Strongest                                   │
│ Mortality                                   │ +0.45          │ Strongest                                   │
│ Composite renal endpoint                    │ +0.30 to +0.40 │ Strong if well-defined                      │
│ eGFR slope                                  │ +0.10 to +0.30 │ Increasingly accepted                       │
│ Proteinuria / albuminuria                   │ 0.00 to +0.20  │ Validated in some settings                  │
│ Blood pressure effect                       │ 0.00 to +0.10  │ Supportive unless primary disease driver    │
│ Biomarker only                              │ −0.40 to −0.55 │ Weak alone                                  │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ OPHTHALMOLOGY                               │                │                                             │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Visual acuity gain/loss                     │ +0.40 to +0.45 │ Direct function                             │
│ BCVA letters gained                         │ +0.35 to +0.45 │ Core regulatory endpoint                    │
│ Avoided vision loss                         │ +0.35 to +0.45 │ Strong                                      │
│ Injection burden reduction                  │ +0.10 to +0.25 │ Meaningful if efficacy preserved            │
│ Retinal thickness / OCT                     │ 0.00 to +0.15  │ Useful but weaker than vision               │
│ Durability interval                         │ 0.00 to +0.20  │ Strong if efficacy maintained               │
│ Anatomic biomarker only                     │ −0.30 to −0.10 │ Weak without visual benefit                 │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ GENE THERAPY / CELL THERAPY OVERLAY         │                │ Apply on top of TA endpoint score           │
├─────────────────────────────────────────────┼────────────────┼─────────────────────────────────────────────┤
│ Durable functional correction               │ +0.20 to +0.35 │ Biggest positive signal                     │
│ Durable biomarker/protein correction        │ +0.10 to +0.25 │ Meaningful if causal link is known          │
│ Short follow-up only                        │ −0.10 to −0.25 │ Durability unknown                          │
│ Redosing impossible and waning effect risk  │ −0.15 to −0.30 │ Major risk                                  │
│ Serious vector/cell safety concern          │ −0.25 to −0.60 │ Major penalty                               │
│ Manufacturing inconsistency                 │ −0.20 to −0.40 │ Especially important for cell/gene therapy  │
│ Biomarker expression only                   │ −0.20 to −0.40 │ Biology shown, benefit not proven           │
└─────────────────────────────────────────────┴────────────────┴─────────────────────────────────────────────┘


  MoA Precedent — how established is this mechanism:

  ┌─────────────────────────────┬──────────┬─────────────────────────────────────────────────────┐
│            Value            │ Log-Odds │                       Meaning                       │
├─────────────────────────────┼──────────┼─────────────────────────────────────────────────────┤
│ validated / validated_class │ +0.35    │ Multiple approved drugs, same target/MoA            │
│ clinically_validated_target │ +0.20    │ Human efficacy shown; few/no approved drugs         │
│ pathway_validated           │ +0.05    │ Same pathway valid; exact target not                │
│ partial                     │ 0.00     │ Early human signal / strong translational rationale │
│ preclinical_only            │ −0.20    │ Animal/in vitro only; no human efficacy data        │
│ novel                       │ −0.35    │ FIC target; no human validation                     │
│ prior_failures              │ −0.50    │ Prior class/target failures in same indication      │
│ known_liability             │ −0.60    │ Known translational or safety liability             │
└─────────────────────────────┴──────────┴─────────────────────────────────────────────────────┘
MoAExceptionFlag — 4 additive rescue signals (on POSAdjusters.moa_exception_flags):
┌────────────────────────────────┬───────┬─────────────────────────────────────────────────────────┐
│              Flag              │ Shift │                          Rule                           │
├────────────────────────────────┼───────┼─────────────────────────────────────────────────────────┤
│ prior_failures_due_to_bad_drug │ +0.25 │ Prior failures = drug quality problem, not target biology │
│ genetically_validated_target   │ +0.20 │ Strong human genetics support: GWAS, Mendelian            │
│ human_proof_of_mechanism       │ +0.15 │ Human POM demonstrated in biomarker/PK-PD                 │
│ strong_biomarker_response      │ +0.10 │ Clear dose-dependent biomarker signal                     │
└────────────────────────────────┴───────┴─────────────────────────────────────────────────────────┘


Sample Size Adequacy — is the trial large enough and statistically designed well enough to test its primary endpoint?

┌──────────────────────────────────────────────────────────────────────┬────────────────┬──────────────────────────────────────────────┐
│                                Value                                 │ Log-Odds Shift │                   Meaning                    │
├──────────────────────────────────────────────────────────────────────┼────────────────┼──────────────────────────────────────────────┤
│ Well-powered: ≥90% power with realistic effect-size assumptions       │ +0.20          │ Strong design; lower risk of false negative  │
│ Adequate: 80–89% power with reasonable assumptions — baseline         │ 0.00           │ Standard registrational-quality design       │
│ Borderline: 70–79% power or aggressive effect-size assumptions        │ −0.20          │ Higher risk the trial misses a real effect   │
│ Underpowered: <70% power                                              │ −0.45          │ Trial may be too small to prove the claim    │
│ Unverifiable: no disclosed power calculation or unclear stat plan     │ −0.25          │ Cannot confirm whether N is adequate         │
│ Exploratory only: tiny / open-label / signal-seeking study            │ −0.50          │ Hypothesis-generating, not confirmatory      │
└──────────────────────────────────────────────────────────────────────┴────────────────┴──────────────────────────────────────────────┘
Scoring Rule

Do not score by raw patient count alone.

A trial with 80 patients can be strong in rare disease but useless in cardiovascular outcomes.

sample_size_score = function(
  planned_sample_size,
  statistical_power,
  expected_effect_size,
  endpoint_variability,
  control_rate_or_placebo_response,
  dropout_rate,
  trial_design,
  phase,
  indication_rarity
)
Therapeutic-Area Context

┌────────────────────────────┬──────────────────────────────────────────────────────┐
│      Therapeutic Area      │                Sample Size Interpretation            │
├────────────────────────────┼──────────────────────────────────────────────────────┤
│ Oncology                   │ 50–300 may be meaningful, depending on endpoint      │
│ Rare disease               │ 20–100 may be acceptable if effect size is large     │
│ Cardiovascular outcomes    │ Often requires thousands to detect event reduction   │
│ Psychiatry / CNS           │ Often requires larger N due to placebo/noise         │
│ Immunology / inflammation  │ Usually needs moderate-to-large controlled trials    │
│ Infectious disease/vaccines│ Can range from hundreds to tens of thousands         │
│ Ophthalmology              │ Smaller N can work if paired-eye/design is efficient │
│ Renal / metabolic outcomes │ Often needs large N for hard outcomes                │
└────────────────────────────┴──────────────────────────────────────────────────────┘


  Safety Profile — based on prior phase data:

\                                                                                                                         
  ┌─────────────────────────────────────┬──────────┐
  │                Value                │ Log-odds │                                                                      
  ├─────────────────────────────────────┼──────────┤                                     
  │ clean                               │ +0.10    │                                                                      
  ├─────────────────────────────────────┼──────────┤                                     
  │ manageable                          │ 0.00     │
  ├─────────────────────────────────────┼──────────┤        
  │ monitorable_concern                 │ −0.20    │
  ├─────────────────────────────────────┼──────────┤                                                                      
  │ dose_limiting                       │ −0.40    │
  ├─────────────────────────────────────┼──────────┤                                                                      
  │ serious                             │ −0.65    │                                     
  ├─────────────────────────────────────┼──────────┤
  │ mechanism_linked_severe             │ −0.80    │        
  ├─────────────────────────────────────┼──────────┤
  │ minor (legacy → manageable)         │ 0.00     │                                                                      
  ├─────────────────────────────────────┼──────────┤
  │ concerning (legacy → dose_limiting) │ −0.40    │                                                                      
  └─────────────────────────────────────┴──────────┘                                     

  score_safety(SafetyParams) — applies 7 modifiers with guardrail cap [−0.90, +0.15]. SafetyParams exposes all 11 fields
  from your spec. Positive modifiers (reversible, monitorable, comparable_to_control) are True by default, so a bare
  SafetyParams(category=manageable) yields +0.15 as the adjustment — correctly encoding a normal drug with no safety
  flags.         


  Competitive Pressure — how crowded is the approved landscape:
Keep a small regulatory-bar modifier in POS only if competition changes the approval standard.
Example:
Existing drugs are very effective, so new drug must show superiority or clear differentiation.
Non-inferiority trial vs standard of care has narrow margin.
FDA may require head-to-head data because placebo comparison is no longer acceptable.

  ┌──────────────────────────────────────────────────────────────┬────────────────┐
│ Value                                                        │ Log-Odds Shift │
├──────────────────────────────────────────────────────────────┼────────────────┤
│ Low bar: high unmet need; weak/no standard of care            │ +0.10          │
│ Normal bar: accepted endpoint/design for current landscape    │ 0.00           │
│ Elevated bar: effective standard exists; differentiation needed│ −0.15         │
│ High bar: head-to-head/superiority likely required            │ −0.30          │
└──────────────────────────────────────────────────────────────┴────────────────┘


 Structured Layer 1 adjusters:

- Biomarker selection: scored by strength of enrichment.
  Validated predictive biomarker = +0.40; strong biologic enrichment = +0.25; exploratory biomarker = +0.10; no selection = 0.00; weak/post-hoc biomarker = −0.10.

- Prior-phase data strength: scored by quality of human evidence.
  Replicated strong efficacy = +0.30; strong single-study efficacy = +0.20; clear dose/exposure-response = +0.15; mixed/immature signal = 0.00; weak signal = −0.20; failed/inconsistent prior data = −0.35.

- Breakthrough Therapy Designation: +0.05 if kept in Layer 1. This remains deliberately small because BTD is mainly a regulatory/process signal, not direct proof of efficacy.

Cap on total Layer 1 adjustment:
The combined Layer 1 delta is capped at ±0.80 log-odds. The cap applies only to the adjustment, not the base TA/phase prior, preserving the historical base rate while preventing qualitative inputs from over-driving POS.

At a 32% base POS, a +0.80 capped adjustment increases POS to ~47%. This prevents stacked positive signals from pushing a Phase 2 program to an implausibly high POS without extraordinary evidence.

Special case — Accelerated Approval at NDA/BLA:
When approval_pathway = ACCELERATED, the NDA/BLA base rate is reduced before log-odds conversion to reflect confirmatory-trial and post-marketing risk. Keep this adjustment in the regulatory/trial-design layer if possible to avoid double-counting endpoint quality.


  ---
Step 2 — POS Layer 2: Trial Design / Regulatory Evidence Quality

What it does: Applies a second, orthogonal adjustment to the Layer 1 POS output based on whether the clinical evidence
package is designed well enough to support approval.

Layer 1 scores what evidence is being generated.

Layer 2 scores how trustworthy and regulator-acceptable that evidence is.

The three dimensions:

Evidence Design Quality (HOW credible the trial design is):
- randomized_double_blind_controlled: randomized, double-blind, active/placebo-controlled → strongest bias control
- randomized_open_label_controlled: randomized controlled, open-label → good design, some bias risk
- randomized_weak_comparator: randomized but weak/non-standard comparator → comparator may limit interpretability
- single_arm_objective_endpoint: single-arm with objective endpoint → acceptable in some oncology/rare disease settings
- single_arm_subjective_endpoint: single-arm with subjective endpoint → high bias risk
- registry_external_observational: registry / external control / observational → weakest confirmatory evidence

Comparator / Standard-of-Care Fit (WHETHER the comparison is clinically and regulatorily acceptable):
- soc_matched: comparator matches current standard of care → clean regulatory comparison
- placebo_acceptable_unmet_need: placebo acceptable due to no good standard therapy → acceptable in high unmet need
- acceptable_not_ideal: comparator acceptable but not ideal — baseline
- outdated_or_weak_comparator: comparator outdated or clinically weak → regulators/KOLs may question results
- no_valid_comparator_when_expected: no valid comparator where one is expected → major interpretability risk

Regulatory Pathway Risk (WHETHER the approval route is established and credible):
- standard_accepted_precedent: standard approval path, accepted precedent — baseline
- orphan_rare_disease_flexibility: orphan / rare disease flexibility with strong rationale → some regulatory flexibility
- accelerated_validated_surrogate: accelerated approval with validated surrogate → some confirmatory risk
- accelerated_uncertain_surrogate: accelerated approval with novel/uncertain surrogate → higher post-approval/confirmatory risk
- no_clear_regulatory_precedent: no clear regulatory precedent → path uncertain

Phase-dependent scaling (critical design principle): The same trial design feature has a very different implication at
Phase 1 vs. Phase 3. A single-arm or less controlled design at Phase 1 may be acceptable because the study is often
signal-seeking. At Phase 3, weak design, poor comparator choice, or unclear regulatory precedent can seriously damage
interpretability and approval odds. The system applies a phase-conditional multiplier to the combined raw Layer 2
log-odds adjustment:

┌─────────┬────────────────────────────┐
│  Phase  │ Layer 2 Scaling Multiplier │
├─────────┼────────────────────────────┤
│ Phase 1 │ 0.20                       │
├─────────┼────────────────────────────┤
│ Phase 2 │ 0.50                       │
├─────────┼────────────────────────────┤
│ Phase 3 │ 1.00                       │
├─────────┼────────────────────────────┤
│ NDA/BLA │ 0.90                       │
└─────────┴────────────────────────────┘

Reason: trial design matters more as the drug moves closer to approval.

The combined Layer 2 adjustment is capped at +0.30 / −0.60 log-odds.

Cap logic: Good design helps, but bad design can kill interpretability. A perfect design should not massively boost POS,
but a bad design can seriously hurt it.

Anti-double-counting enforcement: Layer 2 should not re-score endpoint strength, biology, or raw clinical signal quality.
Those belong in Layer 1.

Layer 1: Biological / clinical evidence strength
1. Endpoint strength
2. MoA precedent
3. Sample size / power
4. Safety
5. Biomarker selection
6. Prior-phase data
7. Regulatory/SOC bar

Layer 2: Trial design / regulatory evidence quality
1. Evidence design quality
2. Comparator quality
3. Regulatory pathway risk
4. Phase-dependent scaling

Two signals require overlap checks:
1. Endpoint quality should not be scored in both Layer 1 and Layer 2. Layer 1 handles endpoint strength; Layer 2 handles
whether the design credibly tests that endpoint.
2. Regulatory/SOC bar in Layer 1 should not duplicate Comparator / Standard-of-Care Fit in Layer 2. Layer 1 scores the
difficulty of the approval/commercial bar; Layer 2 scores whether the chosen comparator and regulatory path are credible.

If overlapping non-default values are detected, check_pos_layer_overlap() should raise a ValueError by default.
Estimated double-count magnitude should be calculated and reported.

Bottom line: Layer 2 is useful because two drugs can have the same endpoint and same biology, but very different approval
odds because one has a clean randomized controlled trial and the other has a messy single-arm study.


  ---
  Step 3 — Cumulative Approval Probability

  After both POS layers assign a per-phase probability, cumulative P(approval) is computed by multiplying across all
  phases:

  P(approval) = P(pass Ph1) × P(pass Ph2 | passed Ph1) × P(pass Ph3) × P(pass NDA/BLA)

  This is the number that feeds both the rNPV formula and the implied-probability back-solve.

  ---
  Step 4 — Revenue Model
The Revenue Model projects annual drug sales from launch through patent expiry and post-LOE erosion, then converts revenue into EBIT.
It supports multiple market-sizing approaches:
Lines-of-therapy segmentation — preferred for oncology; each line such as 1L, 2L, and 3L has its own patient pool, penetration ceiling, and uptake curve.
Patient-based sizing — eligible patients × net price × treatment duration.
TAM-based sizing — total addressable market × expected penetration.
CommercialInputs hybrid mode — combines patient funnel, pricing, penetration, gross-to-net, price erosion, ex-US/geography, and uptake assumptions.
The model now includes:
Gross-to-net pricing: supports WAC/list price to net price conversion.
Pre-LOE net price erosion: annual net price decline before patent expiry.
Patient funnel: prevalence or incidence × diagnosed × eligible × treated.
Disease model modes:
prevalent
incident_chronic
incident_one_time
Launch archetypes:
rapid orphan
oncology specialist
primary care slow
competitive late entrant
step-edit restricted
gene therapy bolus
Geography split: US, EU5, Japan, China, and ROW can each have separate revenue fractions, launch delays, and penetration assumptions.
Fractional launch-delay interpolation: 1.5-year or 2.5-year delays are interpolated instead of snapped to whole years.
Regional patent/LOE horizon extension: delayed ex-US launches are not silently truncated.
Payer access adjustment: access probability, coverage delay, prior authorization burden, and step-edit risk modify effective uptake.
Competition model: adjusts available market share over time and adds competition-driven price erosion.
COGS by modality: small molecule, biologic, gene therapy, cell therapy, ADC, RNA therapy, and other.
SG&A by commercial model: self-commercialized specialty, rare disease KOL, partnered, royalty-only, primary care, and hospital specialty.
LOE erosion by modality: post-patent erosion curves are YAML-driven, not hardcoded.
EBIT formula:
EBIT(year) = revenue(year) × [1 − COGS_rate − SG&A_rate(year)]
Plain English: the model now forecasts revenue by patient population, launch shape, geography, payer access, competition, pricing erosion, patent life, modality-specific COGS, and commercialization strategy

  ---
   Cost Model Layer — Complete Documentation                                              
                                                                          
  The cost model is a stateless engine (CostModel.compute()) that converts all outgoing cash obligations into a single    
  probability-weighted present value. It consumes ProbabilityResult for phase timing and probabilities, and returns
  CostStream. Five cost categories are computed independently and summed into total_pv_weighted_millions, which RNPVModel 
  subtracts from revenue value.                                                          
                                                                                                                          
  ---                                                                                   
  Category 1 — Trial R&D Phase Costs                                                                                      
                                                                                                                          
  The core calculation. Each clinical phase has a nominal cost that must be (a) shared per co-development terms, (b) grown
   by inflation to its incurrence date, (c) discounted back to present value, and (d) weighted by the probability of ever 
  reaching that phase.                                                                                                    
                                                                                         
  UNIFORM spend profile (default):                                     
                                                                                     
  PV(cost_i) = cost_i × cdev_share × (1+π)^t_mid / (1+r)^t_mid × prob_reaching_i
                                                                                                                          
  where t_mid = (year_start + year_end) / 2 and π is cost_inflation_rate.
                                                                                                                          
  ANNUAL_UNIFORM spend profile — for phases that span multiple calendar years, spending is distributed uniformly and each
  segment is discounted at its own midpoint:                                                                              
                                                                                                                          
  PV(cost_i) = cost_i × cdev_share × Σ_k [ frac_k × (1+π)^{t_k} / (1+r)^{t_k} ] × prob_reaching_i
                                                                                                                          
  frac_k is the fraction of phase duration in segment k, t_k is the midpoint of that segment. The                         
  _spend_fraction_weights() helper splits [year_start, year_end) at every integer year boundary.                          
                                                                                                                          
  Setting π = 0 (default) collapses the formula to plain discounting — bit-for-bit backward compatible. Setting π = r     
  makes the inflation and discount factors cancel, returning costs at face value.        
                                                                                                                          
  ---                                                                                    
  Category 2 — CMC / Manufacturing Costs (CMCCosts)                                                                       
                                                                                                                          
  Chemistry, Manufacturing, and Controls costs are separate from trial R&D because they follow a different commitment     
  logic: the company does not commit to manufacturing scale-up until Phase 2 data is in hand, so the probability weight is
   prob_reaching_phase_3, not prob_reaching_phase_1.                                                                      
                                                             
  Four components sum to a single total_millions:                                                                         
                                                                                         
  ┌─────────────────────────────────┬───────────────────────────────────────────────────────────────┐
  │            Component            │                        What it covers                         │                     
  ├─────────────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ api_development_millions        │ Synthesis routes, analytical methods, IND-enabling batches    │                     
  ├─────────────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ formulation_millions            │ Dosage form, stability studies, fill-finish                   │                     
  ├─────────────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ manufacturing_scale_up_millions │ Tech transfer, PPQ batches, facility qualification            │
  ├─────────────────────────────────┼───────────────────────────────────────────────────────────────┤                     
  │ regulatory_cmc_millions         │ NDA/BLA Module 3, site inspections, post-approval commitments │
  └─────────────────────────────────┴───────────────────────────────────────────────────────────────┘                     
                                                                                         
  The discount anchor year is determined by CMCTimingMode:
                                                                                                                          
  ┌───────────────────────────────┬──────────────────────────────┐                   
  │             Mode              │            Anchor            │                                                        
  ├───────────────────────────────┼──────────────────────────────┤                                                        
  │ PARALLEL_TO_PHASE_3 (default) │ Phase 3 midpoint             │     
  ├───────────────────────────────┼──────────────────────────────┤                                                        
  │ POST_PHASE_2                  │ Phase 2 year_end             │                       
  ├───────────────────────────────┼──────────────────────────────┤                                                        
  │ PRE_PHASE_3_START             │ Phase 3 year_start           │
  ├───────────────────────────────┼──────────────────────────────┤                                                        
  │ CUSTOM_YEAR                   │ Analyst-supplied custom_year │                       
  └───────────────────────────────┴──────────────────────────────┘     
                                                                                     
  PV(CMC) = total_millions / (1+r)^anchor × prob_reaching_phase_3
                                                                                                                          
  ---                                                                                
  Category 3 — Deal Milestones (DealEconomics.payable_milestones)                                                         
                                                                                                                          
  Contingent payments to a deal partner, probability-weighted at the event that triggers each one. The milestone_pv()
  helper is purely mechanical — it contains no business logic, only timing lookups from ProbabilityResult.                
                                                                                         
  Five trigger types:                                        
                                                                                                                          
  ┌─────────────────┬────────────────────────────────────────┬─────────────────────────────────────┐
  │     Trigger     │                  Year                  │         Probability weight          │                      
  ├─────────────────┼────────────────────────────────────────┼─────────────────────────────────────┤                      
  │ PHASE_START     │ phase.year_start                       │ prob_reaching                       │
  ├─────────────────┼────────────────────────────────────────┼─────────────────────────────────────┤                      
  │ PHASE_SUCCESS   │ phase.year_end                         │ prob_reaching × success_probability │
  ├─────────────────┼────────────────────────────────────────┼─────────────────────────────────────┤                      
  │ APPROVAL        │ prob.years_to_approval                 │ cumulative_approval_probability     │
  ├─────────────────┼────────────────────────────────────────┼─────────────────────────────────────┤
  │ FIRST_SALE      │ years_to_approval + launch_year_offset │ cumulative_approval_probability     │
  ├─────────────────┼────────────────────────────────────────┼─────────────────────────────────────┤
  │ SALES_THRESHOLD │ First year revenue ≥ threshold         │ cumulative_approval_probability     │
  └─────────────────┴────────────────────────────────────────┴─────────────────────────────────────┘
                                                                                                                          
  PV(milestone_i) = amount_i / (1+r)^year_i × prob_payment_i                                                              
                                                                                                                          
  SALES_THRESHOLD requires a RevenueStream — when not available in CostModel (which has no revenue dependency), it returns
   0.0 and is resolved by RNPVModel instead.                                             
                                                                                                                          
  ---                                                                                    
  Category 4 — Upfront Cost                                                                                               
                                                                                         
  A single time-0 cash outflow — no discounting, no probability weighting. Added at face value:                           
                                                                                         
  PV(upfront) = upfront_cost_millions    (t = 0)                                                                          
                                                             
  ---                                                                                                                     
  Category 5 — Post-Approval R&D                                                         
                                                                       
  Phase 4 commitments, REMS programs, pharmacovigilance obligations. These are incurred after approval, so they are       
  discounted to years_to_approval (when they begin) and then probability-weighted by cumulative_approval_probability:
                                                                                                                          
  PV(post_approval) = post_approval_rd_millions / (1+r)^years_to_approval × P(approval)  
                                                                                                                          
  ---                                                                                    
  Aggregation                                                                                                             
                                                                                                                          
  total_pv_weighted_millions =                     
      Σ PV(trial_phase_costs)          [after cdev_share + inflation + discounting]                                       
    + Σ PV(payable_milestones)                                                           
    + upfront_cost_millions            [face value, t=0]                                                                  
    + PV(post_approval_rd)                                                                                                
    + PV(CMC)                                                          
                                                                                                                          
  CostStream exposes this decomposition via fields so RNPVModel and callers can inspect each component separately.
  trial_rd_pv_millions is a computed property that sums only the phase cost rows.    
                                                                                                                          
  ---                                                                                                                     
  Boundary — What Cost Model Does Not Own                                                                                 
                                                                                                                          
  RevenueModel has no deal parameter. Revenue is gross commercial revenue; the royalty reduction that results from
  deal.royalty_rate is an ownership split applied in RNPVModel, not a cost. This boundary is explicit: CostModel sees only
   outflows (costs we pay); RNPVModel sees inflows reduced by royalty and ownership fractions.    

Step 6 — rNPV Formula (Updated)   
                                                                
  The core equation:                                                      
                                                      
  rNPV = P(approval) × Σ_yr [ FCF_yr × net_ownership / (1 + WACC)^(years_to_approval + yr) ]
         − total_pv_weighted_development_costs                                          
         + PV(receivable milestones)                                                       
         + upfront_receipt                           

  Where FCF_yr = after_tax_EBIT_yr − maintenance_capex_yr − working_capital_yr − launch_capex_yr                          
                                 
    after_tax_EBIT_yr = adjusted_EBIT_yr × (1 − effective_tax_yr)                                                         
    adjusted_EBIT_yr  = EBIT_yr − royalty_yr − profit_share_yr                           
    royalty_yr        = revenue_yr × deal.royalty_rate
    profit_share_yr   = EBIT_yr   × deal.profit_share_rate             
                                                                                     
  Tax — two paths:                                                                      
                                                             
  ┌──────┬────────────────────┬───────────────────────────────────────────────────────────────────────────────────────┐
  │ Path │        When        │                                       Behavior                                        │   
  ├──────┼────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤
  │ A    │ No TaxProfile      │ tax = 0 for yr ≤ nol_benefit_years, then asset.effective_tax_rate                     │   
  │      │ (backward compat)  │                                                                                       │
  ├──────┼────────────────────┼───────────────────────────────────────────────────────────────────────────────────────┤   
  │      │ TaxProfile         │ Per-year NOL balance consumed up to nol_utilization_limit_rate (default 80%,          │
  │ B    │ provided           │ post-TCJA US §172(a)(2)) of taxable income; explicit dollar NOL carryforward          │   
  │      │                    │ exhausted over time                                                                   │   
  └──────┴────────────────────┴───────────────────────────────────────────────────────────────────────────────────────┘   
                                                                                                                          
  Path B — per-year computation order:                                                   
                                                                                        
  1. taxable_income_yr  = max(adjusted_EBIT_yr, 0)                                      
  2. usable_NOL_yr      = min(remaining_NOL, taxable_income_yr × nol_utilization_limit_rate)
  3. cash_tax_yr        = (taxable_income_yr − usable_NOL_yr) × blended_tax_rate                                          
  4. after_tax_EBIT_yr  = adjusted_EBIT_yr − cash_tax_yr                                                                  
  5. FCF_yr             = after_tax_EBIT_yr − maintenance_capex_yr − working_capital_yr − launch_capex_yr                 
  6. remaining_NOL     -= usable_NOL_yr                                                                                   
                                                                                         
  FCF adjustments (TaxProfile fields):                                               
                                                                                        
  - maintenance_capex_yr = revenue_yr × annual_maintenance_capex_rate — ongoing plant/IT maintenance
  - working_capital_yr = revenue_yr × working_capital_rate — net AR + inventory build at each revenue level
  - launch_capex_yr — one-time manufacturing scale-up/field force cost in USD millions, incurred in commercial year       
  int(launch_capex_year_offset) + 1 (offset=0 → year 1; offset=1.5 → year 2)                                              
                                                                                                                          
  Jurisdiction modes (TaxProfile):                                                                                        
                                                                                                                          
  - "blended" (default): blended_tax_rate = effective_tax_rate                                                            
  - "us_ex_us": blended_tax_rate = us_tax_rate × us_revenue_fraction + ex_us_tax_rate × (1 − us_revenue_fraction)         
                                                                                                                          
  Key mechanics (unchanged from prior version):                                                                           
                                                                                         
  - Absolute discounting anchor: t = years_to_approval + yr — all FCF cash flows discounted from today, not from launch   
  - EBIT basis: global revenue, post-gross-to-net (payer access × net price), post-COGS, post-SG&A, pre-deal-deductions.  
  The Revenue Model outputs gross commercial EBIT; royalty and profit_share deductions happen inside the rNPV loop        
  - Deal deduction ordering per year: royalty (top-line) → profit_share (EBIT-level) → adjusted_EBIT → tax → FCF          
  adjustments → net_ownership capture                                                    
  - net_ownership = asset.net_ownership = 1 − asset.royalty_rate — the equity stake; invariant to deal terms.             
  deal.royalty_rate and deal.profit_share_rate reduce EBIT and are tracked separately in royalty_deductions_pv_millions
  and profit_share_deductions_pv_millions                                                                                 
  - total_pv_weighted_development_costs = trial R&D (probability-weighted, inflation-adjusted) + CMC/manufacturing +      
  payable milestones + upfront cost + post-approval R&D obligations — computed by CostModel, passed in as                 
  cost.total_pv_weighted_millions                                                                                         
  - NAV: NAV = rNPV + net_cash_on_balance_sheet; NAV/share = NAV / diluted_shares_outstanding
                                                                                                                          
  Audit trail: When a TaxProfile is supplied, RNPVResult.tax_audit is populated with 9 per-year lists
  (pre_tax_adjusted_ebit, taxable_income, nol_used, remaining_nol, cash_tax, after_tax_ebit, capex, working_capital,      
  after_tax_fcf) for BD/M&A memo disclosure. None otherwise.                             
                                                                                                                          
  Out of scope (explicit exclusions): deferred tax assets/liabilities, BEAT/AMT, country-by-country transfer pricing,
  Section 382 NOL limitations, purchase accounting amortization or tax step-up mechanics.                                 
                                                                                           



  ---
Step 7 — Scenario Analysis (Six-Category Shock Model)           
                                                                                                                          
  Each scenario is a ScenarioShock — a composite of six orthogonal input categories, all zero-effect by default so the
  base case requires no explicit inputs.                                                                                  
                                                                  
  ScenarioShock                                                                                                           
    ├─ Clinical       pos_mult, per_phase_pos_mult, safety_profile_override,
    │                 biomarker_selection_override, breakthrough_designation_override,                                    
    │                 prior_phase_data_logodds_delta                                                                      
    │                                                                                                                     
    ├─ Regulatory     duration_add_years, approval_pathway_override,                                                      
    │                 label_breadth_mult, confirmatory_trial_cost_millions,                                               
    │                 crl_delay_add_years                                                                                 
    │                                                                                                                     
    ├─ Commercial     addressable_patients_mult, peak_penetration_mult,                                                   
    │                 net_price_mult, gross_to_net_rate_delta,                                                            
    │                 annual_price_erosion_delta, years_to_peak_add,                                                      
    │                 launch_archetype_override, ex_us_launch_delay_add_years,                                            
    │                 payer_access_probability_mult, prior_auth_burden_delta,                                             
    │                 reimbursement_probability_mult                                                                      
    │                                                                                                                     
    ├─ Competition    competitor_approval_prob_mult, competitor_launch_timing_add_years,                                  
    │                 competitor_market_share_mult, competition_price_pressure_delta                                      
    │                                                                                                                     
    ├─ Costs / FCF    rd_cost_mult, cmc_cost_mult, cost_inflation_delta,                                                  
    │                 cogs_rate_delta, sgna_rate_delta,                                                                   
    │                 maintenance_capex_rate_delta, working_capital_rate_delta,                                           
    │                 tax_rate_delta, discount_rate_delta                                                                 
    │                                                                                                                     
    └─ Deal Economics royalty_rate_override, profit_share_rate_override,                                                  
                      cdev_cost_share_override, milestone_payment_mult,                                                   
                      milestone_receipt_mult                                                                              
                                                                                                                          
  Pre-built Bull / Base / Bear shocks (built-in defaults):                                                                
                                                                  
  ┌──────────┬───────────────────────────────────────────────────────────────────────┐                                    
  │ Scenario │ Key shocks                                                            │                                    
  ├──────────┼───────────────────────────────────────────────────────────────────────┤
  │ Bull     │ pos_mult ×1.15, duration −0.5 yr, label_breadth ×1.20,               │                                     
  │          │ peak_penetration ×1.25, net_price ×1.10, delayed competition          │                                    
  ├──────────┼───────────────────────────────────────────────────────────────────────┤                                    
  │ Base     │ All categories at zero-effect (model assumptions as-entered)          │                                    
  ├──────────┼───────────────────────────────────────────────────────────────────────┤                                    
  │ Bear     │ pos_mult ×0.80, duration +1.0 yr, label_breadth ×0.75,               │
  │          │ peak_penetration ×0.70, net_price ×0.85,                              │                                    
  │          │ price_pressure_delta +0.03, competitor_share ×1.30                   │
  └──────────┴───────────────────────────────────────────────────────────────────────┘                                    
                                                                  
  Each scenario runs the full rNPV engine with shocked inputs (no shortcuts). The ScenarioResult carries eight fields:    
                                                                  
  ┌────────────────────────────────┬──────────────────────────────────────────────┐                                       
  │             Field              │                 Description                  │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ label                          │ Scenario name (Bull / Base / Bear / custom)  │
  ├────────────────────────────────┼──────────────────────────────────────────────┤
  │ rnpv_millions                  │ Scenario rNPV in USD millions                │                                       
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ cumulative_success_probability │ Composite P(approval) under shocked POS      │                                       
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ scenario_nav_millions          │ rNPV + net cash under scenario               │
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ scenario_nav_per_share         │ NAV/share when shares outstanding provided   │
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ delta_vs_base                  │ rNPV difference vs base case (None for base) │
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ kill_criteria_triggered        │ True when rNPV < 0 or P(approval) < 5%       │
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ key_assumption_changes         │ Human-readable list of non-default inputs    │
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ top_value_drivers              │ Inputs most responsible for delta_vs_base    │
  ├────────────────────────────────┼──────────────────────────────────────────────┤                                       
  │ memo_interpretation            │ 1–3 sentence plain-English explanation       │
  └────────────────────────────────┴──────────────────────────────────────────────┘                                       
                                                                  
  Scenario-tree mode decomposes a scenario across three independent outcome axes — Clinical (failure / mixed_result /     
  success / strong_success) × Regulatory (standard_approval / accelerated_approval / narrow_label / delay_crl /
  confirmatory_required) × Commercial (strong_launch / normal_launch / payer_restricted_launch /                          
  competitor_disrupted_launch). Each axis branch carries its own ScenarioShock; ScenarioTree.to_shock() merges the three
  into a single composite shock for the engine.

  ---
  Step 8 — Monte Carlo (N Simulations, Dual-Mode Engine)
                                                                                                                          
  8A — Two operating modes
                                                                                                                          
  MCMode.SIMPLE        sample_peak_sales=True                     
    → Peak sales drawn directly from a log-normal (backward-compatible)                                                   
                                                                                                                          
  MCMode.DRIVER_BASED  sample_peak_sales=False                                                                            
    → eligible_patients × net_price × peak_penetration × payer_access × geography                                         
    → Each driver drawn independently; product is peak sales for that trial                                               
    → Prevents double-counting (enforced at construction and via validate_mc_params)                                      
                                                                                                                          
  8B — 23-variable registry (7 categories)                                                                                
                                                                                                                          
  ┌────────────────────┬───┬──────────────────────────────────────────────────────────┐                                   
  │ Category           │ N │ Variables                                                 │
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Clinical           │ 4 │ phase_1_success_prob, phase_2_success_prob,              │
  │                    │   │ phase_3_success_prob (Beta), nda_approval_prob (Bern.)   │                                   
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Regulatory         │ 5 │ label_breadth_mult (LogNormal), approval_timing_std      │                                   
  │                    │   │ (Normal), breakthrough_granted, crl_issued,              │                                   
  │                    │   │ confirmatory_trial_required (Bernoulli×3)                │                                   
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Commercial         │ 5 │ eligible_patients_mult, net_price_mult,                  │                                   
  │                    │   │ peak_penetration_mult (LogNormal×3),                     │                                   
  │                    │   │ years_to_peak (Triangular), patent_life_years (Triang.)  │                                   
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Payer              │ 2 │ payer_access_fraction, prior_auth_burden_delta (Beta×2)  │                                   
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Competition        │ 2 │ competitor_share_mult (LogNormal),                       │                                   
  │                    │   │ competitor_timing_delta (Beta)                           │                                   
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Costs / macro      │ 4 │ rd_cost_mult (LogNormal), cogs_rate (Beta),              │                                   
  │                    │   │ sgna_rate (Beta), discount_rate / WACC (Normal)          │                                   
  ├────────────────────┼───┼──────────────────────────────────────────────────────────┤                                   
  │ Tax                │ 1 │ effective_tax_rate (Beta)                                │                                   
  └────────────────────┴───┴──────────────────────────────────────────────────────────┘                                   
                                                                  
  8C — Gaussian copula correlation structure (ENHANCED_CORRELATION)                                                       
                                                                  
  Nine variables enter the copula; pairwise correlations encode two chains:                                               
                                                                  
  Positive chain (clinical data quality):                                                                                 
    phase_3_success_prob → label_breadth_mult    ρ = +0.40                                                                
    phase_3_success_prob → peak_penetration_mult ρ = +0.30                                                                
    phase_3_success_prob → payer_access_fraction ρ = +0.25                                                                
    label_breadth_mult   → eligible_patients_mult ρ = +0.50                                                               
    label_breadth_mult   → peak_penetration_mult  ρ = +0.30       
    eligible_patients_mult → peak_penetration_mult ρ = +0.20                                                              
    peak_penetration_mult → payer_access_fraction ρ = +0.35       
                                                                                                                          
  Negative chain (competitive and payer friction):                
    competitor_share_mult → peak_penetration_mult  ρ = −0.40                                                              
    competitor_share_mult → payer_access_fraction  ρ = −0.25                                                              
    prior_auth_burden_delta → peak_penetration_mult ρ = −0.35                                                             
    prior_auth_burden_delta → payer_access_fraction ρ = −0.50                                                             
                                                                                                                          
  Independent (macroeconomic):                                    
    discount_rate, rd_cost_mult — no pairs, ρ = 0 with all others                                                         
                                                                                                                          
  8D — Pipeline competitor Bernoulli sampling                                                                             
                                                                                                                          
  Each pipeline competitor (status ≠ "approved") is Bernoulli-included with probability = approval_probability. Approved  
  competitors enter every simulation without sampling. Sampled pipeline competitors have their approval_probability set to
   1.0 (no double-counting). Optional launch_timing_std_years > 0 adds Gaussian jitter to launch_year_relative (clipped to
   ≥ 0) for timing uncertainty. This makes MC standard deviation measurably wider for uncertain pipeline competition than
  for certain competition.

  8E — 12-step canonical simulation path                                                                                  
   
  Every trial follows the identical path through _run_single_trial(SimulationDraws) → SimulationOutput. rNPV is never     
  computed from shocked summary statistics — the full engine always reruns:
                                                                                                                          
   1  Clinical draw     → per-phase success probabilities (Beta)  
   2  Cumulative POS    → P(approval) from phase chain                                                                    
   3  Commercial draw   → peak sales (SIMPLE) or driver product (DRIVER_BASED)
   4  Uptake shape      → years_to_peak, patent_life_years (Triangular)                                                   
   5  Competition draw  → Bernoulli-sample pipeline competitors + timing jitter
   6  Revenue model     → annual revenue curve with sampled competition model                                             
   7  Cost draw         → rd_cost_mult, WACC (Normal); phase costs re-discounted
   8  WACC draw         → discount rate from Normal distribution
   9  Tax draw          → effective_tax_rate (Beta)                                                                       
  10  FCF model         → EBIT → FCF → PV(FCF) using drawn WACC and tax
  11  rNPV recompute    → full engine run (engine_rerun=True, always)                                                     
  12  NAV / share       → rNPV + net_cash; ÷ shares if provided                                                           
                                                                                                                          
  8F — Enhanced outputs                                                                                                   
                                                                                                                          
  ┌─────────────────────────────────┬──────────────────────────────────────────────────────┐
  │ Output field                    │ Description                                          │                              
  ├─────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ simulated_values_millions       │ Full sorted distribution (ascending)                 │                              
  │ percentile_5/25/75/95_millions  │ Distribution percentiles                             │                              
  │ mean_rnpv_millions              │ Arithmetic mean across all trials                    │                              
  │ expected_upside                 │ E[rNPV | rNPV > 0] — conditional mean of winners     │                              
  │ expected_downside               │ E[rNPV | rNPV < 0] — conditional mean of losers      │                              
  │ downside_value_at_risk          │ |P5| when P5 < 0; else 0                             │                              
  │ top_variance_drivers            │ Up to 5 variable names ranked by Spearman |r|        │                              
  │                                 │ with rNPV outcome                                    │                              
  │ clinical_failure_rate           │ Fraction of trials where P(approval) ≤ 10%           │                              
  │ competitor_disruption_rate      │ Fraction where ≥1 pipeline competitor was sampled in │                              
  │ payer_restriction_rate          │ Fraction where payer_access draw < 0.50              │                              
  │ probability_nav_above_ev        │ P(NAV > EV) — optional; requires enterprise_value    │                              
  │ probability_nav_above_price     │ P(NAV > market price) — optional; requires price +   │                              
  │                                 │ shares_outstanding                                   │                              
  │ audit_trail                     │ Exactly 3 SimulationAuditRecord objects (P5/P50/P95) │                              
  │ mode_used                       │ MCMode.SIMPLE or MCMode.DRIVER_BASED                 │                              
  └─────────────────────────────────┴──────────────────────────────────────────────────────┘
                                                                                                                          
  Compact audit trail — full per-trial traces are not stored. Only the P5, P50, and P95 simulations are retained as       
  SimulationAuditRecord, each carrying: simulation_id, percentile_label, clinical_draw, commercial_draw, cost_draw,       
  competition_draw, rnpv_millions, nav_per_share, main_value_driver, failure_reason.                                      
                                                                  
  8G — Input validation (Sprint 33)                                                                                       
   
  validate_mc_params(params, *, market_model, trials, asset) enforces six rules before any simulation runs:               
                                                                  
  Rule 1 [ERROR]   sample_peak_sales=True + any driver flag — double-counting                                             
  Rule 2 [WARNING] LaunchArchetype.STEP_EDIT_RESTRICTED without acknowledgement                                           
  Rule 3 [ERROR]   Probability values outside [0, 1] (per-phase POS, tax rate, royalty)                                   
  Rule 4 [ERROR]   Negative patient counts, prices, trial costs, or durations ≤ 0                                         
  Rule 5 [WARNING] Global revenue implied > 5× US revenue without explicit fraction                                       
  Rule 6 [WARNING] Ex-US geography launch year earlier than US launch year                                                
                                                                                                                          
  Errors raise ValueError (hard block). Warnings emit UserWarning (advisory). Both are independently suppressible via     
  raise_on_errors=False / emit_warnings=False.          


  ---
  Step 9 — Variant Perception Back-Solve

  The Variant Perception module back-solves from the company's current valuation to estimate what the market is implicitly
   assuming about the asset. It answers: "What must the market believe for today's price to be fair?"

  Step 9A — Asset EV Isolation

  Before back-solving, the module strips non-modeled value from the company enterprise value:

  asset_implied_EV =
      company_EV                     (market_cap − net_cash)
    − other_pipeline_value           (other programs not in this model)
    − royalty_stream_value           (PV of existing out-licensed income)
    − platform_value                 (technology platform beyond programs)
    − non_core_value                 (non-pipeline assets not in net cash)

  Because other-pipeline value is uncertain, the module reports three allocation cases:

  ┌──────────────────┬────────────────────────────────────────────────────────────┐
  │ Case             │ Interpretation                                             │
  ├──────────────────┼────────────────────────────────────────────────────────────┤
  │ Conservative     │ High deduction to other assets → least EV to this asset   │
  │ Base             │ Central estimate of other-asset value                      │
  │ Aggressive       │ Low deduction to other assets → most EV to this asset      │
  └──────────────────┴────────────────────────────────────────────────────────────┘

  AssetAllocationSpec carries the three other_pipeline values plus fixed deductions (royalty_stream_value, platform_value,
   non_core_value). Defaults to zero — appropriate for single-asset companies.

  Step 9B — Core Back-Solve Formula

  market_implied_POS =
      ( asset_implied_EV
      + PV_expected_remaining_dev_costs
      − PV_expected_receivable_milestones
      − upfront_receipts )
      / PV_full_success_after_tax_FCF

  Where:

  - PV_full_success_after_tax_FCF = RNPVResult.gross_revenue_pv_millions — the model's full-success PV already including
  geography, payer access, competition, gross-to-net, COGS, SG&A, royalties, profit share, taxes, capex, working capital,
  and net ownership
  - PV_expected_remaining_dev_costs = RNPVResult.trial_costs_pv_millions — probability-weighted PV of all remaining phase
  R&D costs
  - upfront_receipts and PV_receivable_milestones from DealEconomics (zero when no deal)

  Step 9C — Five Back-Solves

  All five back-solves are computed for each of the three allocation cases. Back-solves 2–5 share a single revenue scale
  factor:

  revenue_scale = (asset_implied_EV + PV_costs − PV_milestones − upfront)
                  / (model_POS × PV_full_success_FCF)

  ┌─────┬─────────────────────────────────┬───────────────────────────────────┐
  │  #  │           Back-Solve            │              Formula              │
  ├─────┼─────────────────────────────────┼───────────────────────────────────┤
  │ 1   │ Implied probability of approval │ numerator / PV_full_success_FCF   │
  ├─────┼─────────────────────────────────┼───────────────────────────────────┤
  │ 2   │ Implied peak sales              │ model_peak_sales × revenue_scale  │
  ├─────┼─────────────────────────────────┼───────────────────────────────────┤
  │ 3   │ Implied peak penetration        │ model_penetration × revenue_scale │
  ├─────┼─────────────────────────────────┼───────────────────────────────────┤
  │ 4   │ Implied net price per patient   │ model_net_price × revenue_scale   │
  ├─────┼─────────────────────────────────┼───────────────────────────────────┤
  │ 5   │ Implied eligible patient pool   │ model_patients × revenue_scale    │
  └─────┴─────────────────────────────────┴───────────────────────────────────┘

  Back-solves 3–5 are None when the model uses LOT-segment or TAM mode (no single patient/price/penetration input to
  scale).

  Step 9D — Output Table

  ┌─────────────────────────────┬──────────────┬───────────────┬──────────────┐
  │ Metric                      │ Market-Implied│ Model Estimate│ Gap          │
  ├─────────────────────────────┼──────────────┼───────────────┼──────────────┤
  │ Probability of approval     │ 29%          │ 52%           │ +23 pp       │
  │ Peak sales                  │ $480M        │ $900M         │ +$420M       │
  │ Peak penetration            │ 12%          │ 22%           │ +10 pp       │
  │ Net price per patient       │ $105K        │ $180K         │ +$75K        │
  │ Eligible patients           │ 9,000        │ 17,000        │ +8,000       │
  └─────────────────────────────┴──────────────┴───────────────┴──────────────┘

  Positive gap = model more bullish than market. Negative gap = model more bearish.

  Step 9E — Guardrails

  ┌───────────────────────┬───────────────────────────┬───────────────────────────────────────────────────────────────┐
  │         Code          │         Condition         │                            Meaning                            │
  ├───────────────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ ev_below_cost         │ implied_pos < 0           │ Asset-implied EV is less than remaining dev costs;            │
  │                       │                           │ other-asset deductions may be overstated                      │
  ├───────────────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ ev_above_full_success │ implied_pos > 1           │ Market pricing more than full-success FCF; full-success       │
  │                       │                           │ assumptions too conservative or allocation too aggressive     │
  ├───────────────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ pv_fcf_invalid        │ PV_full_success_FCF ≤ 0   │ Denominator invalid; back-solve not meaningful                │
  ├───────────────────────┼───────────────────────────┼───────────────────────────────────────────────────────────────┤
  │ multi_asset_required  │ Multiple asset_ids, no    │ AssetAllocationSpec.other_pipeline_base must be set to avoid  │
  │                       │ explicit allocation       │ assigning 100% of company EV to this asset                    │
  └───────────────────────┴───────────────────────────┴───────────────────────────────────────────────────────────────┘

  Each guardrail emits a UserWarning (suppressible via emit_guardrail_warnings=False). Raw implied_pos is always preserved
   regardless of clamping.

  Step 9F — Variant Perception Classification

  The module classifies the primary source of disagreement between model and market:

  ┌─────────────────┬──────────────────────────────────────────────────────────────┐
  │ Category        │ Trigger condition                                            │
  ├─────────────────┼──────────────────────────────────────────────────────────────┤
  │ clinical        │ POS gap ≥ 15pp and dominant over commercial gap              │
  │ commercial      │ Peak-sales gap ≥ 30% and POS gap < 15pp                      │
  │ pricing         │ Same as commercial, with price identified as the driver      │
  │ mixed           │ Both POS gap ≥ 15pp AND peak-sales gap ≥ 30%                 │
  │ allocation      │ Implied POS changes sign between conservative and aggressive │
  │ indeterminate   │ Neither gap exceeds threshold                                │
  └─────────────────┴──────────────────────────────────────────────────────────────┘

  The classification drives the memo interpretation, e.g.:

  ▎ Variant perception appears primarily clinical: the market is pricing a 29% approval probability vs. the model's 52%
  (+23pp gap). The commercial assumptions (peak sales ~$480M) are broadly consistent with the model's $900M.

  ▎ Variant perception appears sensitive to asset value allocation. The market-implied POS ranges widely across allocation
   assumptions, suggesting the key uncertainty is how much of the $250M asset-implied EV reflects this specific program.



  ---
 Step 10 — Sensitivity / Tornado Analysis

  Each of 8 key assumptions is independently shocked ±X while all others hold at base. The full rNPV engine reruns for    
  each shocked value — no proxy or shortcut. Results are ranked by absolute swing and plotted as a tornado chart.
                                                                                                                          
  Parameters shocked (default set)                                                                                      

  ┌────────────────────────────────┬──────────────────┬─────────────────────────────────────────┐
  │ Parameter                      │ Shock            │ Applied as                              │                         
  ├────────────────────────────────┼──────────────────┼─────────────────────────────────────────┤                         
  │ Phase POS                      │ ±20% relative    │ per-phase success_probability × (1±0.20)│                         
  │ Peak Sales                     │ ±30% relative    │ TAM or net_price × (1±0.30)             │                         
  │ Peak Penetration               │ ±30% relative    │ peak_penetration × (1±0.30)             │                         
  │ Discount Rate (WACC)           │ ±200 bps         │ discount_rate ± 0.02                    │                         
  │ Patent Life                    │ ±3 years         │ patent_life_years ± 3                   │                         
  │ Gross-to-Net Rate              │ ±10pp            │ net price × (1±0.10) proxy              │                       
  │ Effective Tax Rate             │ ±5pp             │ effective_tax_rate ± 0.05               │                         
  │ Competition (+1 / +2 entrants) │ 15% haircut/entry│ peak_penetration × (1 − n × 0.15)      │                        
  └────────────────────────────────┴──────────────────┴─────────────────────────────────────────┘                         
                                                                                                                          
  Shock set is configurable via SensitivitySpec — individual specs can be deactivated or replaced without changing the    
  function signature.                                                                                                     
                                                                                                                          
  Ranking and output                                                                                                    

  Points are sorted descending by |swing| = |high_rnpv − low_rnpv|. low_rnpv ≤ high_rnpv is always enforced regardless of 
  shock direction (e.g. a higher discount rate produces the low rNPV, so values are swapped before storage).
                                                                                                                          
  SensitivityResult                                                                                                     
    base_rnpv              Unshocked base rNPV — anchors all tornado bars                                                 
    points[]               Ranked SensitivityPoint list (rank 1 = largest swing)
      .parameter           Human-readable label ("Phase POS (±20%)")                                                      
      .low_rnpv            rNPV at the adverse shock                                                                      
      .high_rnpv           rNPV at the favourable shock                                                                   
      .base_rnpv           Repeated per-point for chart anchoring                                                         
      .shock_pct           Shock magnitude                                                                                
      .rank                1 = widest bar                                                                                 
      .abs_swing           |high_rnpv − low_rnpv|                                                                         
    dominant_driver        Label of rank-1 parameter                                                                      
    dominant_is_clinical   True when Phase POS holds rank 1
    memo_interpretation    One-sentence plain-English summary                                                             
                                                                                                                        
  Interpretation signal                                                                                                   
                                                                                                                        
  dominant_is_clinical is the primary signal for how to frame the investment thesis:                                      
   
  dominant_is_clinical = True                                                                                             
    → Early/mid-stage asset; approval uncertainty drives most value                                                     
    → "Value is primarily driven by Phase POS (±$180M swing). Clinical risk dominates."                                   
                                                                                                                          
  dominant_is_clinical = False                                                                                            
    → Late-stage or NDA-ready; commercial assumptions drive most value                                                    
    → "Value is primarily driven by Peak Sales (±$250M swing). Commercial risk dominates."    

















  ---
  Part 2: M&A Probability Scanner

0A. Hard Exclusion Rules
Purpose: Remove companies that should not enter the live M&A target ranking.

1. Entity Validity Exclusions
Filter
Rule
Output
Non-biotech / non-pharma entity
Not a therapeutics, diagnostics, tools, platform, or life-science company
Hard fail
SPAC / shell / blank-check company
No operating drug, diagnostic, platform, or commercial asset
Hard fail
Holding company / investment vehicle
Value comes from ownership stakes, not operating life-science assets
Hard fail
Royalty company / passive IP vehicle
Value is primarily royalty streams, not controllable operating assets
Exclude unless using royalty-acquisition model
Service-only company
CRO, CDMO, consulting, staffing, or services company with no proprietary asset/platform
Exclude unless using services M&A model
Research nonprofit / academic entity
Not a standalone acquirable public/private company
Hard fail
Government-controlled / restricted entity
Ownership/control makes acquisition structurally infeasible
Hard fail or legal-review queue


2. Standalone Status Exclusions
Filter
Rule
Output
Already acquired
Company has been acquired and no longer trades independently
Remove from live ranking; keep for historical training
Merged into another entity
Legacy ticker/company no longer represents standalone target
Remove from live ranking
Delisted after takeout
Company no longer independently acquirable
Remove from live ranking
Pending definitive acquisition agreement
Signed merger agreement already announced
Remove from live ranking; track as announced deal
Post-spin entity mismatch
Ticker refers to spun-out stub, not original acquired company
Resolve entity before scoring
Ticker/entity mismatch
Ticker maps to wrong company, old name, renamed company, or stale entity
Hard fail until corrected
Duplicate entity
Same company appears under multiple tickers/entities
Deduplicate before scoring


3. Target-Universe Exclusions
Filter
Rule
Output
Known acquirer profile
Company is one of the modeled acquirers, not intended target universe
Move to buyer universe or hard fail












































4. Asset Visibility Exclusions
Filter
Rule
Output
No identifiable lead asset
Cannot identify what drug/product drives value
Hard fail
No identifiable platform
Platform company has no clear technological basis or repeatable engine
Hard fail
No active pipeline
No active clinical, preclinical, platform, diagnostic, or commercial program
Hard fail
No commercial product
Commercial-stage company has no meaningful approved product or revenue driver
Hard fail or route to pipeline model
No underwritable value driver
Cannot map value to asset, pipeline, platform, rights, or revenue stream
Hard fail
Pipeline too vague
Company descriptions are promotional but lack asset names, stages, targets, or indications
Diligence queue
Unclear therapeutic area
Cannot map company into relevant buyer strategy or disease market
Diligence queue
Unclear modality
Cannot classify as small molecule, biologic, RNA, gene therapy, cell therapy, radiopharma, etc.
Diligence queue


5. Asset Viability Exclusions
Filter
Rule
Output
Lead asset discontinued
Main asset formally discontinued
Hard fail
Lead asset failed pivotal trial
Primary value driver failed and no credible salvage path exists
Hard fail or severe cap
Fatal safety signal
Safety issue likely blocks development or approval
Hard fail
Unresolved clinical hold
FDA/regulator hold blocks asset with no clear resolution path
Hard fail or severe cap
Regulatory rejection with no path forward
CRL/negative opinion without credible fix
Hard fail or severe cap
Mechanism invalidated
Target/MoA has been materially discredited by clinical evidence
Severe cap
No dose window
Efficacy requires dose level that creates unacceptable toxicity
Severe cap
Non-replicated weak signal
Asset rests on one weak, small, or non-controlled dataset
Cap score; not necessarily hard fail
Development abandoned
No recent evidence that company is still advancing the asset
Hard fail or stale-data queue


6. Rights, IP, and Ownership Exclusions
Filter
Rule
Output
No ownable rights
Company does not control meaningful rights to lead asset/platform
Hard fail for acquisition model
Lead asset fully licensed away
Most economics already sold or licensed to another company
Route to licensing model or severe cap
Territory unavailable
Key commercial geography already partnered away
Target-level cap or route to licensing model
IP not durable
No meaningful patent/exclusivity runway
Severe cap
IP ownership dispute
Material litigation or unclear ownership over core asset
Diligence queue or severe cap
Short remaining exclusivity
Too little patent/regulatory life to support acquisition premium
Severe cap
Blocking third-party rights
Another party has consent rights, opt-ins, ROFR, or change-of-control rights
Record fact in Layer 0; buyer-specific impact handled in Layer 3B
Complex royalty stack
Economics are too burdened by royalties/milestones
Severe cap


7. Financial / Going-Concern Exclusions
Filter
Rule
Output
Bankrupt / liquidating
Chapter 7, liquidation, wind-down, or no going-concern value
Hard fail
Severe going-concern warning
Cash runway too short with no credible financing path
Route to distressed optionality model
Negative enterprise value trap
Cheap due to asset failure, not mispricing
Distress model only; cap standard M&A score
No cash/debt data
Cannot assess runway, affordability, or deal feasibility
Diligence queue
No market cap / valuation data
Cannot size transaction
Diligence queue
Unreliable financials
Restatements, missing filings, or major accounting uncertainty
Exclude or diligence queue
Sub-scale target
Asset/company is very small and may lack strategic relevance
Flag for sub-scale review
Large / mega target
Target may require large-cap acquirer universe
Flag for Layer 3 affordability review


8. Market Data and Liquidity Exclusions
Filter
Rule
Output
Stale market data
Market cap, price, cash, debt, or pipeline data older than threshold
Refresh required
Extremely illiquid stock
Trading volume too low for reliable market signal
Cap score or diligence queue
Microcap data-quality trap
Very small company with unreliable coverage/data
Cap or exclude
OTC / pink sheet risk
Limited disclosure, poor liquidity, or weak reporting standards
Exclude or distress-only model
Foreign listing data gap
Cannot reliably obtain financials, ownership, or pipeline data
Diligence queue
Corporate action confusion
Reverse split, ticker change, merger, spin, or reorganization makes data unreliable
Refresh/entity resolution required


9. Legal, Compliance, and Integrity Exclusions
Filter
Rule
Output
Sanctions / restricted ownership
Deal legally restricted by sanctions or national-security rules
Hard fail
Material fraud allegation
Serious fraud, falsified clinical data, or management integrity issue
Hard fail or severe cap
Clinical data-integrity issue
Trial conduct, site integrity, or data reliability is questionable
Severe cap
SEC/enforcement cloud
Major unresolved regulatory or accounting investigation
Severe cap
Major litigation over core asset
Litigation threatens ownership, launch, or economics
Diligence queue or severe cap
Manufacturing compliance failure
Serious GMP/CMC issue blocks approval or supply
Severe cap
Ethics/reputational blocker
Target creates unacceptable reputational risk
Severe cap or legal-review queue


10. Commercial Relevance Exclusions
Filter
Rule
Output
Market too small
Addressable market cannot justify acquisition premium
Severe cap
No unmet need
Product offers limited clinical or commercial reason to exist
Severe cap
Undifferentiated me-too asset
No clear efficacy, safety, dosing, pricing, or access advantage
Severe cap
Generic/biosimilar pressure
Commercial life is too short or exposed to erosion
Cap commercial-franchise score
Reimbursement impossible
Payer story is too weak for realistic adoption
Severe cap
Adoption barriers too high
Product requires unrealistic behavior change, infrastructure, or testing pathway
Severe cap
Commercially irrelevant geography
Value sits in markets unlikely to matter for most strategic buyers
Flag for buyer-specific geography review


11. Model-Scope Exclusions
Filter
Rule
Output
Wrong deal type for model
Company fits royalty, services, diagnostics, device, or tools M&A rather than therapeutics M&A
Route to correct model
Licensing-only case
Full acquisition unlikely because rights, economics, or strategy favor partnership
Route to licensing model
Distress-only case
Company is cheap mainly because of financing distress or failed sentiment
Route to distressed optionality model
Commercial-only case
Value is mostly approved-product sales, not pipeline
Route to commercial-franchise model
Platform-only case
Value depends mostly on technology engine, not lead rNPV
Route to platform model
Historical training case
Already-acquired company should train/validate the model, not appear in live ranking
Historical dataset only


Cleaner Implementation Format
I’d implement it as gates, not one giant flat list.
Gate Structure
Gate
Name
Gate 0
Entity Validity
Gate 1
Standalone / Corporate Status
Gate 2
Target-Universe Eligibility
Gate 3
Asset Visibility
Gate 4
Asset Viability
Gate 5
Rights / IP / Ownership
Gate 6
Financial / Going-Concern
Gate 7
Market Data Quality
Gate 8
Legal / Integrity
Gate 9
Commercial Relevance
Gate 10
Model Routing

Each gate outputs one of five statuses:
Status
PASS
HARD_FAIL
SEVERE_CAP
DILIGENCE_QUEUE
ROUTE_TO_OTHER_MODEL



Layer 0C -Target Size / Buyer Universe Pre-Screen
Purpose: Estimate the target’s expected acquisition size and flag what type of buyer universe could realistically acquire it.
Layer 0C does not calculate final affordability for a specific acquirer.

expected_acquisition_cost =
enterprise_value × (1 + expected_takeout_premium)
Default expected_takeout_premium = 35%

Output:
target_size_bucket
expected_acquisition_cost
minimum_buyer_capacity_needed
requires_large_cap_buyer
mega_deal_flag
sub_scale_flag
data_gaps

Target Size Buckets
Target size bucket
EV / market cap range
Likely buyer universe
Sub-scale
< $100M
Small specialty buyer, licensing, distressed optionality, or PE-style transaction
Small-cap
$100M–$500M
Mid-cap specialty pharma or large-cap bolt-on
Mid-cap
$500M–$5B
Core biotech M&A universe
Large-cap
$5B–$25B
Large pharma / top specialty pharma
Mega-deal
> $25B
Top pharma only

True pair-specific affordability, including stock-deal realism, is calculated later in Layer 3A.



Layer 0D - Target-Level Asset-Control / Encumbrance Profile
Purpose: Measure whether the target controls enough of the asset’s rights, economics, IP, manufacturing readiness, and diligence package to make a full acquisition structurally possible.

Layer 0D is target-level only.

It does not decide whether a specific buyer is blocked or advantaged. Buyer-specific ROFR, opt-in, consent rights, existing-partner advantages, regional rights fit, and acquirer manufacturing capability are handled later in Layer 3B.
Step 3 — Bucket Scoring Formulas with Actual Penalty Amounts

  1. Rights Control Score

  rights_control_score =
    0.40 × global_rights_control
  + 0.25 × key_geography_control
  + 0.20 × indication_control
  + 0.15 × change_of_control_freedom

  ┌───────────────────────┬─────────────────────────────┬───────────────────────────────────────────┐
  │         Issue         │     Sub-score assigned      │            Rights score impact            │
  ├───────────────────────┼─────────────────────────────┼───────────────────────────────────────────┤
  │ Target owns global    │ global=0.95, key_geo=0.90   │ Score ≈ 0.89 (clean)                      │
  │ rights                │                             │                                           │
  ├───────────────────────┼─────────────────────────────┼───────────────────────────────────────────┤
  │ Regional rights split │ global=0.50, key_geo=0.50   │ Score ≈ 0.58 (meaningful encumbrance);    │
  │                       │                             │ −0.31 vs global                           │
  ├───────────────────────┼─────────────────────────────┼───────────────────────────────────────────┤
  │ Fully licensed-in (no │ global=0.25, key_geo=0.45   │ Score ≈ 0.43 (severe); −0.46 vs global    │
  │  owned rights)        │                             │                                           │
  ├───────────────────────┼─────────────────────────────┼───────────────────────────────────────────┤
  │ Rights scope unknown  │ global=0.65, key_geo=0.65   │ Score ≈ 0.71 (minor penalty)              │
  ├───────────────────────┼─────────────────────────────┼───────────────────────────────────────────┤
  │ Major geography (US   │ key_geography_control <     │ Flags                                     │
  │ or EU) unavailable    │ 0.55                        │ key_geography:major_market_unavailable    │
  ├───────────────────────┼─────────────────────────────┼───────────────────────────────────────────┤
  │ Change-of-control     │ change_of_control_freedom   │ Contributes −0.045 vs fully clean (1.0)   │
  │ consent needed        │ default = 0.70              │                                           │
  └───────────────────────┴─────────────────────────────┴───────────────────────────────────────────┘

  Impact on asset_control_score (rights weight = 25%):
  - Regional split: −0.077 on composite vs global
  - Licensed-in: −0.115 on composite vs global

  ---
  2. Economic Control Score

  economic_control_score =
    0.35 × royalty_cleanliness
  + 0.25 × milestone_burden
  + 0.20 × profit_share_cleanliness
  + 0.20 × cost_obligation_cleanliness

  Royalty cleanliness formula:
  royalty_cleanliness = max(0.10, 1.0 − royalty_rate × 2.5)

  ┌──────────────────────┬─────────────────────┬────────────────────────────────────┐
  │  Royalty stack rate  │ royalty_cleanliness │       Economic score impact        │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ 0% (none)            │ 1.00                │ Baseline (no penalty)              │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ 5%                   │ 0.875               │ −0.044 on economic score           │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ 10%                  │ 0.750               │ −0.088 on economic score           │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ 15% (high threshold) │ 0.625               │ −0.131 on economic score           │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ 20%                  │ 0.500               │ −0.175 on economic score           │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ 30%                  │ 0.250               │ −0.263 on economic score           │
  ├──────────────────────┼─────────────────────┼────────────────────────────────────┤
  │ ≥ 40%                │ 0.100 (floor)       │ −0.315 on economic score (maximum) │
  └──────────────────────┴─────────────────────┴────────────────────────────────────┘

  ┌──────────────────────┬─────────────────────────────────────┬────────────────────────────────────┐
  │     Other issue      │              Sub-score              │       Economic score impact        │
  ├──────────────────────┼─────────────────────────────────────┼────────────────────────────────────┤
  │ No milestones        │ milestone_burden = 1.00             │ Baseline                           │
  │ outstanding          │                                     │                                    │
  ├──────────────────────┼─────────────────────────────────────┼────────────────────────────────────┤
  │ Large remaining      │ milestone_burden < 0.50             │ Flags large_milestone_burden       │
  │ milestones           │                                     │                                    │
  ├──────────────────────┼─────────────────────────────────────┼────────────────────────────────────┤
  │ No profit share      │ profit_share_cleanliness = 0.87     │ Baseline                           │
  │                      │ (default)                           │                                    │
  ├──────────────────────┼─────────────────────────────────────┼────────────────────────────────────┤
  │ Co-development       │ cost_obligation_cleanliness = 0.45  │ −0.084 on economic score; −0.017   │
  │ obligation           │ vs 0.87                             │ on composite                       │
  └──────────────────────┴─────────────────────────────────────┴────────────────────────────────────┘

  ---
 3. Partner Encumbrance Facts Score

partner_encumbrance_facts_score =
  0.40 × no_blocking_rights
+ 0.30 × partner_governance_complexity
+ 0.30 × partner_encumbrance_severity

Layer 0D records the existence and severity of partner encumbrances.

It does not decide whether a specific buyer is blocked or advantaged.

Buyer-specific ROFR, opt-in, consent rights, and existing-partner advantages are handled later in Layer 3B.


Issue
Layer 0D treatment
Impact
No partner restrictions
High partner encumbrance facts score
Clean / minor issue
Existing partnership
Records partnership fact and governance complexity
May require Layer 3B review
ROFR / opt-in exists
Records target-level fact
Buyer-specific impact handled in Layer 3B
Consent right exists
Records target-level fact
Buyer-specific impact handled in Layer 3B
Complex partner governance
Lower partner encumbrance facts score
Target-level penalty / diligence flag




  ---
  4. IP Control Score

  ip_control_score =
    0.35 × patent_strength
  + 0.25 × exclusivity_runway
  + 0.20 × freedom_to_operate
  + 0.20 × ownership_cleanliness

  
Issue
Sub-score assigned
IP score impact
Clean IP, no disputes
ownership=0.90, FTO=0.85, patent=0.75, runway=0.75
Score ≈ 0.80
IP dispute present
ownership_cleanliness = 0.15, FTO = 0.45
IP score −0.23; composite −0.035
Ownership fatally contested
ownership_cleanliness < 0.30
Flags ownership_fatally_contested
FTO issue
freedom_to_operate < 0.40
Flags FTO issue
Weak patent position
patent_strength < 0.50
Flags weak patent position
Fatal IP dispute
Boolean hard blocker
Composite capped at 0.30 regardless of score



  ---
  5. Manufacturing Readiness Score 

manufacturing_readiness_score =
  0.35 × process_transferability
+ 0.30 × supply_redundancy
+ 0.20 × GMP_quality_readiness
+ 0.15 × scale_capacity

Layer 0D measures target-level manufacturing readiness only.

Acquirer manufacturing capability is evaluated later in Layer 3B.

 
Issue
Sub-scores assigned
Manufacturing score impact
Standard low-complexity manufacturing
process=0.85, supply=0.80, GMP=0.80
Score ≈ 0.79 baseline
Medium complexity
process=0.72, supply=0.70
Score ≈ 0.73
High complexity, such as cell/gene or radiopharma
process=0.55, supply=0.60, GMP=0.62
Score ≈ 0.62
Single CDMO dependency
supply_redundancy < 0.40
Flags single-CDMO dependency
Manufacturing dependency
process=0.40, supply=0.45
Meaningful penalty
GMP issue / inspection finding
GMP_quality_readiness < 0.40
Flags GMP issue


  ---
  6. Diligence Readiness Score

  diligence_readiness_score =
    0.30 × clinical_data_completeness
  + 0.25 × CMC_package_completeness
  + 0.20 × regulatory_file_completeness
  + 0.15 × safety_database_quality
  + 0.10 × data_room_readiness

  
Issue
Sub-score assigned
Diligence score impact
Clinical data available
clinical_data_completeness = 0.75
Baseline
Clinical data missing
clinical_data_completeness = 0.55
Lower diligence score
Patent/regulatory data available
CMC = 0.70
Baseline
No patent data / CMC proxy missing
CMC = 0.55
Lower diligence score
Incomplete safety database
safety_database_quality < 0.35
Flags incomplete safety database
Missing trial data
clinical_data_completeness < 0.40
Flags missing trial data
Missing CMC data
CMC < 0.40
Flags missing CMC data
Diligence score < 0.65
—
Flags incomplete data package
Diligence score ≥ 0.80
—
asset_control_confidence = high
Diligence score 0.60–0.79
—
asset_control_confidence = medium
Diligence score < 0.60
—
asset_control_confidence = low



  ---
  Step 4 — Final Asset-Control Score

asset_control_score =
  0.25 × rights_control_score
+ 0.20 × economic_control_score
+ 0.20 × partner_encumbrance_facts_score
+ 0.15 × ip_control_score
+ 0.10 × manufacturing_readiness_score
+ 0.10 × diligence_readiness_score


Structurally clean global target with confirmed ownership and partner-rights data:

composite ≈ 0.85 → CLEAN

Clean target with partial data:

may still receive MILD_PENALTY

Reason: the tool does not assume unknown diligence items are fully clean.

  ---
  Step 5 — Convert Score Into Gate Treatment

  ┌─────────────────────┬───────────────────────────┬──────────────────┬─────────────────────┐
  │ Asset-control score │      Gate treatment       │ Score multiplier │  Max M&A score cap  │
  ├─────────────────────┼───────────────────────────┼──────────────────┼─────────────────────┤
  │ ≥ 0.85              │ CLEAN                     │ ×1.00            │ None                │
  ├─────────────────────┼───────────────────────────┼──────────────────┼─────────────────────┤
  │ 0.70–0.84           │ MILD PENALTY              │ ×0.95            │ None                │
  ├─────────────────────┼───────────────────────────┼──────────────────┼─────────────────────┤
  │ 0.50–0.69           │ MEANINGFUL PENALTY        │ ×0.80            │ None (flag in memo) │
  ├─────────────────────┼───────────────────────────┼──────────────────┼─────────────────────┤
  │ 0.35–0.49           │ SEVERE CAP                │ ×0.60            │ 0.55                │
  ├─────────────────────┼───────────────────────────┼──────────────────┼─────────────────────┤
  │ < 0.35              │ ROUTE TO LICENSING / FAIL │ ×0.40            │ 0.40                │
  └─────────────────────┴───────────────────────────┴──────────────────┴─────────────────────┘

  Hard blockers (not numeric — override score):

  
Condition
Treatment
no_ownable_rights = True
Hard fail; multiplier = 0.20, cap = 0.40
fatal_ip_dispute = True
Composite capped at 0.30; route to licensing
fully_licensed_away = True
Composite capped at 0.30; route to licensing
blocking consent / ROFR / opt-in right exists
Layer 0D records the fact only; Layer 3B determines whether it blocks or caps a specific buyer


  ---
  Step 6 — Pair-Specific Rules

  Layer 0D records target-level facts.
Layer 3B applies pair-specific adjustments for:
ROFR impact on a specific buyer
Existing partner waiver or advantage
Consent rights for a specific change-of-control
Regional rights fit for the buyer
Acquirer manufacturing fit

EXample:
A ROFR may be manageable for the existing partner but restrictive for a non-partner acquirer.

Layer 0D records that the ROFR exists.
Layer 3B determines how it affects each buyer.

  ---
  Step 7 — Encumbrance-Adjusted Valuation Multiplier

  encumbrance_valuation_multiplier =
    r_mult × e_mult × i_mult × m_mult

  where:
    r_mult = 0.50 + 0.50 × rights_score     (floor 0.50)
    e_mult = 0.55 + 0.45 × economic_score   (floor 0.55)
    i_mult = 0.60 + 0.40 × ip_score         (floor 0.60)
   m_mult = 0.70 + 0.30 × manufacturing_readiness_score        (floor 0.70)

This valuation multiplier is target-level. Buyer-specific manufacturing capability is handled separately in Layer 3B.

  ┌────────────────────────────────────────────┬───────┬────────────────────────┐
  │                  Scenario                  │ Score │  Dimension multiplier  │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Clean rights (score = 0.89)                │ 0.89  │ r_mult = 0.945         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Regional split (score = 0.58)              │ 0.58  │ r_mult = 0.790         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Licensed-in (score = 0.43)                 │ 0.43  │ r_mult = 0.715         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Zero rights                                │ 0.00  │ r_mult = 0.500 (floor) │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Clean economics (score = 0.90)             │ 0.90  │ e_mult = 0.955         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ 20% royalty stack (score ≈ 0.72)           │ 0.72  │ e_mult = 0.874         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ 30% royalty stack (score ≈ 0.64)           │ 0.64  │ e_mult = 0.838         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Zero economics                             │ 0.00  │ e_mult = 0.550 (floor) │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Clean IP (score = 0.80)                    │ 0.80  │ i_mult = 0.920         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ IP dispute (score ≈ 0.57)                  │ 0.57  │ i_mult = 0.828         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Zero IP                                    │ 0.00  │ i_mult = 0.600 (floor) │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Clean manufacturing readiness (score=0.79) │ 0.79  │ m_mult = 0.937         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Manufacturing dependency (score ≈ 0.58)    │ 0.58  │ m_mult = 0.874         │
  ├────────────────────────────────────────────┼───────┼────────────────────────┤
  │ Zero manufacturing readiness               │ 0.00  │ m_mult = 0.700 (floor) │
  └────────────────────────────────────────────┴───────┴────────────────────────┘

  Worst case (all floors): 0.50 × 0.55 × 0.60 × 0.70 = 0.116 (88% value reduction)

  Worked example:
  Base rNPV = $3B
  Regional rights split:          rights_score = 0.58 → r_mult = 0.790
  20% royalty stack:              economic_score = 0.72 → e_mult = 0.874
  IP dispute:                     ip_score = 0.57 → i_mult = 0.828
  Clean manufacturing readiness:  manufacturing_readiness_score = 0.79 → m_mult = 0.937

  encumbrance_adjusted_rNPV = $3B × 0.790 × 0.874 × 0.828 × 0.937
                             = $3B × 0.535
                             = ~$1.61B

  ---
  Step 8 — Output Format

  asset_control_score:              0.62
  gate_treatment:                   MEANINGFUL_PENALTY
  penalty_multiplier:               0.80
  max_mna_score_cap:                None
  encumbrance_valuation_multiplier: 0.72

  rights_control_score:             0.58  (regional split)
  economic_control_score:           0.72  (moderate royalty)
  partner_encumbrance_facts_score:  0.87  (clean)
  ip_control_score:                 0.80  (clean)
  manufacturing_readiness_score:    0.79  (clean)
  diligence_readiness_score:        0.69  (partial data)

  asset_control_confidence:         medium

  triggered_encumbrances:
    - regional_rights_split
    - economic_control:heavy_royalty_burden
    - diligence_readiness:incomplete_safety_database

  required_downstream_checks:
    - pair_asset_control_adjustment, if ROFR / partner / consent / manufacturing-complexity facts require buyer-specific review

  hard_blockers:                    []

  recommended_action:
    Apply 0.80 multiplier; flag encumbrances prominently in memo

  rationale:
    - rights_control=0.580  economic=0.720  partner_encumbrance=0.870
    - ip_control=0.800  manufacturing_readiness=0.790  diligence=0.690
    - composite=0.620  treatment=meaningful_penalty

  data_gaps:
    - diligence_readiness: incomplete data package





Layer 0E — Commercial Complexity / Integration Flag
Purpose: Identify whether the target has commercial or operational complexity that may make post-acquisition integration difficult.

Layer 0E does not apply a final buyer-specific penalty.

Layer 0E does not reward commercial synergy.

Layer 0E does not decide whether the target is attractive.  
raw_integration_complexity =
  0.15 × product_complexity
+ 0.10 × indication_complexity
+ 0.15 × salesforce_burden
+ 0.15 × manufacturing_transfer_complexity
+ 0.15 × geographic_complexity
+ 0.15 × payer_access_complexity
+ 0.10 × channel_complexity
+ 0.05 × systems_and_compliance_transfer_risk

Layer 0E identifies the problem.
Layer 3C decides whether each buyer can handle the problem.









Layer 3

	A. Pair-Specific Affordability Gate
Purpose: Determine whether a specific acquirer can realistically afford a specific target.
expected_acquisition_cost =
enterprise_value × (1 + expected_takeout_premium)

affordability_ratio =
expected_acquisition_cost / acquirer_deal_capacity

Where:
acquirer_deal_capacity =
cash_available
+ estimated_debt_capacity
+ realistic_stock_component
- minimum_balance_sheet_buffer

Stock-Deal Realism

realistic_stock_component =
acquirer_market_cap_millions
× max_stock_issuance_pct
× stock_quality_multiplier

Default:
max_stock_issuance_pct = 10%

Stock Quality Multiplier

Signal
Effect
investor_dilution_tolerance
Base default = 0.50
P/B ≥ 4.0
+0.15; premium acquirer = strong currency
P/B < 1.5
−0.20; depressed acquirer = poor currency
Volatility < 20%
+0.10; stable stock more acceptable
Volatility 20–40%
−0.10; moderate biotech penalty
Volatility > 40%
−0.25; speculative stock, targets demand cash


Affordability Treatment

Affordability ratio
Treatment
Score multiplier
≤0.50
No penalty
1.00
0.50–0.85
Mild penalty
0.90
0.85–1.10
Severe penalty / score cap
0.60
>1.10
Pair-level hard fail
0.00


If target EV is missing:
Do not zero the score.
Flag affordability_data_required.
Use existing data-confidence / missing-valuation penalties instead.
Layer 3B — Pair-Specific Asset-Control / Partner-Control Adjustment
Purpose: Apply buyer-specific penalties or caps for rights, partner, ROFR, consent, regional rights, and manufacturing fit issues.
Layer 0D records the target-level facts.
Layer 3B decides how those facts affect each specific acquirer.

Pair-Specific Rules

Issue
Layer 3B treatment
Self-acquisition
Pair-level hard fail
Parent-subsidiary conflict
Pair-level hard fail or special-case model
Existing majority owner
Pair-level fail or control-premium adjustment
Affordability impossible
Pair-level hard fail
Strategic conflict
Pair-level fail or severe cap
Antitrust impossibility
Pair-level hard fail


Partner / ROFR / Consent Examples

Scenario
Treatment
Existing partner acquirer
ROFR / consent impact may be waived or mitigated
Non-partner acquirer with ROFR blocking right
Pair-level cap or severe penalty
Consent required for change-of-control
Pair-specific penalty or cap
Exclusivity conflict for this buyer
Pair-specific penalty
Regional rights mismatch
Pair-specific penalty


Example:
Target has a ROFR with Novartis.

For Novartis:
existing partner
ROFR may be waived or helpful
lower penalty

For Pfizer:
non-partner
ROFR may restrict or cap the deal
higher penalty

Manufacturing Fit Examples

Scenario
Treatment
Buyer has strong relevant manufacturing capability
Reduces manufacturing mismatch penalty
Buyer lacks relevant manufacturing capability
Applies pair-specific penalty
High manufacturing complexity + weak buyer fit
Meaningful penalty or cap
Medium manufacturing complexity + weak buyer fit
Mild / meaningful penalty


Example:
Radiopharma target.

Buyer with radiopharma infrastructure:
lower pair-specific manufacturing penalty

Buyer with no radiopharma capability:
higher pair-specific manufacturing penalty

Layer 3C — Pair-Specific Integration Capability Adjustment
Purpose: Determine whether a specific acquirer can absorb the target’s commercial and operational complexity.
Layer 0E identifies raw complexity.
Layer 3C decides whether the buyer can handle it.
buyer_integration_capability =
  0.25 × commercial_infrastructure_fit
+ 0.20 × manufacturing_capability_fit
+ 0.20 × payer_access_capability_fit
+ 0.15 × geographic_footprint_fit
+ 0.10 × systems_compliance_capability_fit
+ 0.10 × prior_integration_experience
adjusted_integration_penalty =
raw_integration_complexity_score × (1 - buyer_integration_capability)
Treatment

Adjusted integration penalty
Treatment
0.00–0.15
No penalty
0.15–0.30
Mild penalty
0.30–0.50
Meaningful penalty
0.50–0.70
Severe penalty / cap
>0.70
Pair-level cap or fail



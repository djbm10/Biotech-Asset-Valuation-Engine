"""Expanded acquirer registry — Phases 1 and 2.

Phase 1 — Missing mega-cap pharma (9 companies):
  Vertex, Regeneron, Bayer, Boehringer Ingelheim, Astellas, Eisai,
  Otsuka, Chugai, CSL

Phase 2a — Large biotech / specialty pharma (11 companies):
  Biogen, Moderna, Alnylam, Sarepta, BioMarin, United Therapeutics,
  Jazz Pharma, Ipsen, Galapagos, Ascendis, Legend Biotech

Phase 2b — China pharma acquirers / active licensors (7 companies):
  BeiGene, Hengrui, Innovent, Akeso, Hansoh, CSPC, Sino Biopharm

Financial figures sourced from Q1-Q2 2026 earnings releases and public filings.
Refresh against current 10-Q / annual report before use in live deal analysis.
"""
from __future__ import annotations

from bve.entities.acquirer import (
    AcquirerProfile, BDStyle, DealCapacity, ModalityCapabilities,
    BDHistoryDetailed, AcquisitionRecord, LicenseRecord,
    AntitrustProfile, LOECliff,
)
from bve.entities.acquirer_registry_specialty import SPECIALTY_ACQUIRERS

# ===========================================================================
# Phase 1 — Missing mega-cap pharma acquirers
# ===========================================================================

MEGA_CAP_ACQUIRERS_V2: list[AcquirerProfile] = [

    AcquirerProfile(
        company_id="vertex", name="Vertex Pharmaceuticals", ticker="VRTX",
        country="United States",
        cash_millions=15_000, annual_fcf_millions=4_500, market_cap_millions=110_000,
        strategic_areas=["rare_disease", "pain", "kidney_disease", "genetic_medicines", "diabetes_cell_therapy"],
        preferred_modalities=["small_molecule", "cell_therapy", "gene_editing"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=20_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=15_000, max_comfortable_deal_size_millions=20_000,
            debt_capacity_millions=10_000,
        ),
        ta_priorities={"rare_disease": 1.0, "pain": 0.8, "kidney_disease": 0.8,
                       "genetic_medicines": 0.75, "diabetes_cell_therapy": 0.70},
        modality_capabilities=ModalityCapabilities(small_molecule=0.95, cell_therapy=0.75, gene_therapy=0.65),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Alpine Immune Sciences", year=2024,
                              therapeutic_area="immunology", deal_size_millions=4_900,
                              modality="bispecific_antibody"),
            AcquisitionRecord(target="Semma Therapeutics", year=2019,
                              therapeutic_area="diabetes_cell_therapy", deal_size_millions=950),
        ]),
        notes=(
            "CF monopoly (Trikafta LOE ~2037) generates $15B+ cash; zero debt. "
            "Next wave: FSGS (inaxaplin Phase 3), Journavx (VX-548 pain approved 2024), "
            "islet cell therapy (VX-880, VX-264), Casgevy (SCD/TDT with CRSP). "
            "Acquisitive in rare disease, precision medicine, genetic medicines. "
            "Data confidence: high (0.85)."
        ),
    ),

    AcquirerProfile(
        company_id="regeneron", name="Regeneron Pharmaceuticals", ticker="REGN",
        country="United States",
        cash_millions=14_000, annual_fcf_millions=3_000, market_cap_millions=45_000,
        strategic_areas=["immunology", "ophthalmology", "oncology", "genetic_medicines"],
        preferred_modalities=["biologic", "monoclonal_antibody", "bispecific"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=15_000,
        loe_cliffs=[
            LOECliff(product_name="Eylea", indication="wet AMD/DR",
                     peak_sales_millions=6_000, loe_year=2025, revenue_at_risk_millions=3_500),
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=14_000, max_comfortable_deal_size_millions=15_000,
        ),
        ta_priorities={"immunology": 1.0, "ophthalmology": 0.75, "oncology": 0.70,
                       "genetic_medicines": 0.65, "cardiovascular": 0.50},
        modality_capabilities=ModalityCapabilities(monoclonal_antibody=1.0, bispecific=0.85,
                                                   small_molecule=0.5),
        bd_history_detailed=BDHistoryDetailed(
            acquisitions=[
                AcquisitionRecord(target="Checkmate Pharmaceuticals", year=2021,
                                  therapeutic_area="oncology", deal_size_millions=250),
            ],
            licenses=[
                LicenseRecord(partner="Sanofi", direction="out", year=2003,
                              therapeutic_area="immunology", asset="Dupixent/Kevzara"),
                LicenseRecord(partner="Bayer", direction="out", year=2012,
                              therapeutic_area="ophthalmology", asset="Eylea ex-US"),
            ],
        ),
        antitrust=AntitrustProfile(
            recent_ftc_scrutiny=False,
            market_share_risk_areas=["ophthalmology"],
        ),
        notes=(
            "Cash-rich despite lower market cap post-Eylea biosimilar erosion. "
            "Dupixent (with Sanofi) $14B+ revenue; LOE ~2031+. "
            "Strong in-house R&D culture; targeted acquisitions supplement pipeline. "
            "REGN7075 (MUC16/CD3 bispecific), REGN5458, cemiplimab lifecycle. "
            "Data confidence: medium-high (0.78)."
        ),
    ),

    AcquirerProfile(
        company_id="bayer", name="Bayer AG", ticker="BAYRY",
        country="Germany",
        cash_millions=5_000, debt_millions=35_000, annual_fcf_millions=3_000,
        market_cap_millions=25_000,
        strategic_areas=["cardiovascular", "oncology", "womens_health", "radiology"],
        preferred_modalities=["small_molecule", "biologic"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 3", max_deal_size_millions=8_000,
        loe_cliffs=[
            LOECliff(product_name="Xarelto", indication="AF/VTE",
                     peak_sales_millions=4_500, loe_year=2024, revenue_at_risk_millions=3_000),
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=5_000, max_comfortable_deal_size_millions=8_000,
        ),
        ta_priorities={"cardiovascular": 0.9, "oncology": 0.75, "womens_health": 0.65,
                       "radiology": 0.60},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, monoclonal_antibody=0.65),
        notes=(
            "Heavily burdened by Roundup glyphosate litigation (~$16B+ liability). "
            "Net debt ~$35B severely limits deal capacity. BD focus: small bolt-ons. "
            "Nubeqa (darolutamide) + Kerendia + Eylea (US profit share with Regeneron). "
            "Xarelto LOE creating urgency but balance sheet limits options. "
            "Data confidence: medium (0.55)."
        ),
    ),

    AcquirerProfile(
        company_id="boehringer", name="Boehringer Ingelheim", ticker=None,
        country="Germany",
        cash_millions=8_000, annual_fcf_millions=5_000, market_cap_millions=None,
        ebitda_millions=7_000, credit_rating="AA (private, estimated)",
        strategic_areas=["cardiometabolic", "respiratory", "oncology", "animal_health",
                         "immunology"],
        preferred_modalities=["small_molecule", "biologic", "antibody"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=15_000,
        loe_cliffs=[
            LOECliff(product_name="Jardiance (empagliflozin) — BI share", indication="T2D/HFrEF/HFpEF/CKD",
                     peak_sales_millions=2_750, loe_year=2027, revenue_at_risk_millions=1_900,
                     replacement_urgency="high",
                     percent_of_company_revenue=0.11),
            # Note: Total Jardiance sales ~$5.5B but co-promoted 50/50 with Eli Lilly.
            # BI receives roughly half the economics. US composition-of-matter patents ~2025-2027.
            LOECliff(product_name="Spiriva (tiotropium)", indication="COPD/asthma",
                     peak_sales_millions=1_500, loe_year=2022, revenue_at_risk_millions=600,
                     replacement_urgency="low"),  # erosion substantially complete
        ],
        deal_capacity=DealCapacity(
            max_comfortable_deal_size_millions=15_000,
        ),
        ta_priorities={"cardiometabolic": 0.9, "respiratory": 0.85, "oncology": 0.70,
                       "immunology": 0.65, "animal_health": 0.70},
        modality_capabilities=ModalityCapabilities(small_molecule=0.90, monoclonal_antibody=0.75,
                                                   bispecific=0.65),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Aimmune Therapeutics", year=2020,
                              therapeutic_area="allergy", deal_size_millions=1_400),
        ]),
        notes=(
            "Family-owned (Liebrecht family); ~€24B revenue, no public equity constraint. "
            "Jardiance (empagliflozin, shared with Lilly) is blockbuster cardiometabolic anchor. "
            "Respiratory: Ofev (nintedanib), Spiriva (LOE), Giotrif. "
            "Oncology: afatinib, volasertib programs. Very acquisitive. "
            "Deal capacity estimated; private financials not fully disclosed. "
            "Data confidence: low-medium (0.40)."
        ),
    ),

    AcquirerProfile(
        company_id="astellas", name="Astellas Pharma", ticker="ALPMY",
        country="Japan",
        cash_millions=2_000, annual_fcf_millions=1_200, market_cap_millions=10_000,
        strategic_areas=["oncology", "urology", "gene_therapy", "rare_disease", "immunology"],
        preferred_modalities=["small_molecule", "biologic", "gene_therapy", "antibody_drug_conjugate"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=8_000,
        loe_cliffs=[
            LOECliff(product_name="Xtandi (enzalutamide)", indication="prostate cancer",
                     peak_sales_millions=5_000, loe_year=2027, revenue_at_risk_millions=3_500),
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_000, max_comfortable_deal_size_millions=8_000,
        ),
        ta_priorities={"oncology": 1.0, "urology": 0.85, "gene_therapy": 0.80,
                       "rare_disease": 0.75, "immunology": 0.60},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, monoclonal_antibody=0.75,
                                                   gene_therapy=0.80, antibody_drug_conjugate=0.70),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Audentes Therapeutics", year=2020,
                              therapeutic_area="neuromuscular_rare", deal_size_millions=3_000,
                              modality="gene_therapy"),
            AcquisitionRecord(target="Iveric Bio", year=2023,
                              therapeutic_area="ophthalmology", deal_size_millions=5_900),
        ]),
        notes=(
            "PADCEV (enfortumab vedotin, ADC with Seagen/Pfizer) + Xtandi key revenue. "
            "Xtandi LOE ~2027-2028 creates urgent need to replenish. "
            "Gene therapy capability via Audentes (AT132 for XLMTM). "
            "Iveric acquisition ($5.9B, 2023) for avacincaptad pegol (GA ophthalmology). "
            "Data confidence: medium (0.62)."
        ),
    ),

    AcquirerProfile(
        company_id="eisai", name="Eisai Co., Ltd.", ticker="ESALY",
        country="Japan",
        cash_millions=2_000, annual_fcf_millions=500, market_cap_millions=7_000,
        strategic_areas=["neuroscience", "oncology"],
        preferred_modalities=["small_molecule", "biologic"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_000, max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={"neuroscience": 1.0, "oncology": 0.80},
        modality_capabilities=ModalityCapabilities(small_molecule=0.80, monoclonal_antibody=0.75),
        bd_history_detailed=BDHistoryDetailed(
            licenses=[
                LicenseRecord(partner="Biogen", direction="out", year=2014,
                              therapeutic_area="neuroscience", asset="Leqembi (lecanemab) co-dev"),
                LicenseRecord(partner="Merck", direction="out", year=2018,
                              therapeutic_area="oncology", asset="Lenvima (lenvatinib) co-dev"),
            ],
        ),
        notes=(
            "Leqembi (lecanemab, anti-amyloid) with Biogen: key Alzheimer's commercial ramp. "
            "Lenvima (lenvatinib) with Merck in multiple oncology settings. "
            "Halaven (eribulin) for breast cancer. "
            "Moderate deal capacity; primarily strategic licensing vs. large acquisitions. "
            "Data confidence: medium (0.58)."
        ),
    ),

    AcquirerProfile(
        company_id="otsuka", name="Otsuka Pharmaceutical", ticker="OTSKY",
        country="Japan",
        cash_millions=3_000, annual_fcf_millions=1_000, market_cap_millions=10_000,
        strategic_areas=["cns", "nephrology", "oncology", "cardiometabolic"],
        preferred_modalities=["small_molecule", "biologic"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=6_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_000, max_comfortable_deal_size_millions=6_000,
        ),
        ta_priorities={"cns": 1.0, "nephrology": 0.80, "oncology": 0.65, "cardiometabolic": 0.60},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, monoclonal_antibody=0.65),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Astex Pharmaceuticals", year=2013,
                              therapeutic_area="oncology_epigenetics", deal_size_millions=886),
        ]),
        notes=(
            "CNS anchor: Abilify Maintena (long-acting aripiprazole), Rexulti (brexpiprazole). "
            "Nephrology: Jynarque (tolvaptan for ADPKD). "
            "Astex acquisition provides epigenetic oncology capability. "
            "Data confidence: medium (0.55)."
        ),
    ),

    AcquirerProfile(
        company_id="chugai", name="Chugai Pharmaceutical", ticker="CHGCY",
        country="Japan",
        cash_millions=3_000, annual_fcf_millions=1_500, market_cap_millions=25_000,
        strategic_areas=["oncology", "immunology", "rare_disease"],
        preferred_modalities=["biologic", "monoclonal_antibody", "bispecific"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=10_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_000, max_comfortable_deal_size_millions=10_000,
        ),
        ta_priorities={"oncology": 1.0, "immunology": 0.80, "rare_disease": 0.70},
        modality_capabilities=ModalityCapabilities(monoclonal_antibody=1.0, bispecific=0.85,
                                                   small_molecule=0.60),
        notes=(
            "~60% owned by Roche; operates as Roche's Japan/Asia R&D hub. "
            "Key products: Hemlibra (emicizumab, hemophilia A), Alecensa (alectinib). "
            "Strong bispecific antibody engineering capability (Recycling Antibody platform). "
            "Most deals flow through Roche relationship; some independent BD. "
            "Data confidence: medium (0.60)."
        ),
    ),

    AcquirerProfile(
        company_id="csl", name="CSL Limited", ticker="CSLLY",
        country="Australia",
        cash_millions=2_000, debt_millions=9_000, annual_fcf_millions=2_500,
        market_cap_millions=55_000,
        strategic_areas=["plasma_derived", "vaccines", "rare_disease", "kidney_disease",
                         "immunology", "hematology"],
        preferred_modalities=["biologic", "plasma_derived", "small_molecule", "gene_therapy"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=12_000,
        loe_cliffs=[
            LOECliff(product_name="Haegarda (C1-INH)", indication="HAE prophylaxis",
                     peak_sales_millions=800, loe_year=2030, revenue_at_risk_millions=500),
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_000, max_comfortable_deal_size_millions=12_000,
            debt_capacity_millions=5_000,
        ),
        ta_priorities={"plasma_derived": 1.0, "rare_disease": 0.85, "vaccines": 0.80,
                       "kidney_disease": 0.75, "hematology": 0.80},
        modality_capabilities=ModalityCapabilities(small_molecule=0.70, monoclonal_antibody=0.75,
                                                   gene_therapy=0.60),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Vifor Pharma", year=2022,
                              therapeutic_area="kidney_disease_iron", deal_size_millions=11_700),
            AcquisitionRecord(target="Seqirus (from Novartis)", year=2015,
                              therapeutic_area="vaccines", deal_size_millions=275),
        ]),
        notes=(
            "Global plasma leader (CSL Behring); vaccine expertise (CSL Seqirus); "
            "kidney/iron disease platform (CSL Vifor: ferinject, Rika). "
            "Post-Vifor net debt ~$9B constrains near-term megadeals; bolt-ons preferred. "
            "Looking for plasma, rare hematology, iron deficiency, kidney adjacencies. "
            "Data confidence: medium-high (0.70)."
        ),
    ),
]

# ===========================================================================
# Phase 2a — Large biotech / specialty pharma acquirers
# ===========================================================================

LARGE_BIOTECH_ACQUIRERS: list[AcquirerProfile] = [

    AcquirerProfile(
        company_id="biogen", name="Biogen", ticker="BIIB",
        country="United States",
        cash_millions=2_000, debt_millions=6_000, annual_fcf_millions=1_500,
        market_cap_millions=12_000, ebitda_millions=4_500, credit_rating="Baa2/BBB",
        strategic_areas=["neuroscience", "rare_disease", "neurodegeneration"],
        preferred_modalities=["biologic", "small_molecule", "antisense"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=5_000,
        loe_cliffs=[
            LOECliff(product_name="Tecfidera (dimethyl fumarate)", indication="relapsing MS",
                     peak_sales_millions=4_000, loe_year=2020, revenue_at_risk_millions=2_500,
                     replacement_urgency="low"),  # biosimilar erosion substantially complete
            LOECliff(product_name="Spinraza (nusinersen)", indication="spinal muscular atrophy",
                     peak_sales_millions=1_900, loe_year=2029, revenue_at_risk_millions=1_200,
                     replacement_urgency="medium"),  # competition from Zolgensma/risdiplam
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_000, max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={"neuroscience": 1.0, "neurodegeneration": 0.90, "rare_disease": 0.80},
        modality_capabilities=ModalityCapabilities(monoclonal_antibody=0.90, small_molecule=0.75,
                                                   antisense=0.65),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Reata Pharmaceuticals", year=2023,
                              therapeutic_area="rare_neurological", deal_size_millions=7_300,
                              modality="small_molecule"),
            AcquisitionRecord(target="Nightstar Therapeutics", year=2019,
                              therapeutic_area="ophthalmology_gene_therapy", deal_size_millions=800),
        ]),
        notes=(
            "Leqembi (lecanemab, with Eisai) commercial ramp; Tysabri, Spinraza. "
            "Skyclarys (omaveloxolone, from Reata) for Friedreich ataxia. "
            "Strained balance sheet post-Reata ($7.3B). Selective bolt-ons only. "
            "Data confidence: medium (0.65)."
        ),
    ),

    AcquirerProfile(
        company_id="moderna", name="Moderna", ticker="MRNA",
        country="United States",
        cash_millions=9_000, debt_millions=500, annual_fcf_millions=-1_500,
        market_cap_millions=12_000,
        strategic_areas=["infectious_disease", "oncology", "rare_disease", "autoimmune"],
        preferred_modalities=["mrna", "biologic", "gene_therapy"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=10_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=9_000, max_comfortable_deal_size_millions=10_000,
        ),
        ta_priorities={"infectious_disease": 0.9, "oncology": 0.85, "rare_disease": 0.70,
                       "autoimmune": 0.60},
        modality_capabilities=ModalityCapabilities(mrna=1.0, gene_therapy=0.75,
                                                   monoclonal_antibody=0.50),
        bd_history_detailed=BDHistoryDetailed(
            licenses=[
                LicenseRecord(partner="Merck", direction="in", year=2016,
                              therapeutic_area="oncology", asset="mRNA-4157 personalized cancer vaccine"),
            ],
        ),
        notes=(
            "Cash-rich despite revenue decline post-COVID. mResvia (RSV) approved 2024. "
            "Personalized cancer vaccine (mRNA-4157, with Merck) Phase 3 melanoma. "
            "Rare disease mRNA pipeline (PA, MMA, liver diseases). "
            "FCF negative; burning cash. BD focus: mRNA-enabling technology, oncology targets. "
            "Data confidence: medium-high (0.72)."
        ),
    ),

    AcquirerProfile(
        company_id="alnylam", name="Alnylam Pharmaceuticals", ticker="ALNY",
        country="United States",
        cash_millions=3_000, debt_millions=1_000, annual_fcf_millions=1_000,
        market_cap_millions=25_000,
        strategic_areas=["rare_disease", "cardiometabolic", "hepatic"],
        preferred_modalities=["rnai", "mrna", "antisense"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 1", max_deal_size_millions=8_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_000, max_comfortable_deal_size_millions=8_000,
        ),
        ta_priorities={"rare_disease": 1.0, "cardiometabolic": 0.85, "hepatic": 0.80},
        modality_capabilities=ModalityCapabilities(rnai=1.0, antisense=0.60),
        bd_history_detailed=BDHistoryDetailed(
            licenses=[
                LicenseRecord(partner="Novartis", direction="out", year=2013,
                              therapeutic_area="cardiometabolic", asset="Leqvio (inclisiran)"),
                LicenseRecord(partner="Regeneron", direction="in", year=2019,
                              therapeutic_area="cardiometabolic", asset="ALN-HBV collaboration"),
            ],
        ),
        notes=(
            "RNAi pioneer: Amvuttra (vutrisiran ATTR), Onpattro, Givlaari, Oxlumo. "
            "Recently profitable; high royalty from Leqvio (via Novartis). "
            "More likely to be acquired by big pharma than to do platform acquisitions itself. "
            "Core BD: RNAi licensing out; selective in-licensing for complementary delivery. "
            "Data confidence: medium-high (0.75)."
        ),
    ),

    AcquirerProfile(
        company_id="sarepta", name="Sarepta Therapeutics", ticker="SRPT",
        country="United States",
        cash_millions=2_000, debt_millions=500, annual_fcf_millions=500,
        market_cap_millions=10_000,
        strategic_areas=["neuromuscular", "rare_disease", "gene_therapy"],
        preferred_modalities=["gene_therapy", "antisense", "biologic"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=4_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_000, max_comfortable_deal_size_millions=4_000,
        ),
        ta_priorities={"neuromuscular": 1.0, "rare_disease": 0.90, "gene_therapy": 0.85},
        modality_capabilities=ModalityCapabilities(gene_therapy=0.90, antisense=0.90,
                                                   small_molecule=0.60),
        notes=(
            "Elevidys (delandistrogene moxeparvovec) DMD gene therapy approved 2023. "
            "Exon-skipping portfolio: Amondys 45, Vyondys 53, Exondys 51. "
            "Roche partnership for Elevidys global commercialization outside US. "
            "Looking for additional neuromuscular / rare disease gene therapy targets. "
            "Data confidence: medium (0.68)."
        ),
    ),

    AcquirerProfile(
        company_id="biomarin", name="BioMarin Pharmaceutical", ticker="BMRN",
        country="United States",
        cash_millions=1_700, debt_millions=1_000, annual_fcf_millions=700,
        market_cap_millions=12_000,
        strategic_areas=["rare_disease", "hematology", "skeletal"],
        preferred_modalities=["biologic", "gene_therapy", "small_molecule"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_700, max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={"rare_disease": 1.0, "hematology": 0.75, "skeletal": 0.80},
        modality_capabilities=ModalityCapabilities(biologic=0.90, gene_therapy=0.75,
                                                   small_molecule=0.70),
        notes=(
            "Commercial rare disease franchise: Voxzogo (achondroplasia, GHR antagonist), "
            "enzyme replacement therapies (Naglazyme, Aldurazyme), Palynziq. "
            "Roctavian (hemophilia A gene therapy) commercial underperformance. "
            "Balance sheet improving as commercial ramp continues. "
            "Data confidence: medium (0.65)."
        ),
    ),

    AcquirerProfile(
        company_id="united_therapeutics", name="United Therapeutics", ticker="UTHR",
        country="United States",
        cash_millions=3_000, debt_millions=200, annual_fcf_millions=1_500,
        market_cap_millions=15_000,
        strategic_areas=["pulmonary_hypertension", "organ_manufacturing", "rare_disease"],
        preferred_modalities=["biologic", "small_molecule", "gene_therapy", "xenotransplantation"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=8_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_000, max_comfortable_deal_size_millions=8_000,
        ),
        ta_priorities={"pulmonary_hypertension": 1.0, "organ_manufacturing": 0.90,
                       "rare_disease": 0.75},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, biologic=0.75,
                                                   gene_therapy=0.65),
        notes=(
            "PAH dominant: Tyvaso DPI (inhaled treprostinil), Remodulin, Orenitram. "
            "Xenotransplantation program (genetically-engineered pig kidneys/hearts) is unique. "
            "Cash generative; no meaningful debt. Selectively acquisitive. "
            "Data confidence: medium (0.62)."
        ),
    ),

    AcquirerProfile(
        company_id="jazz_pharma", name="Jazz Pharmaceuticals", ticker="JAZZ",
        country="Ireland",
        cash_millions=800, debt_millions=3_500, annual_fcf_millions=800,
        market_cap_millions=4_000, ebitda_millions=1_200, credit_rating="B1/BB-",
        strategic_areas=["neuroscience", "oncology"],
        preferred_modalities=["small_molecule", "biologic"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 3", max_deal_size_millions=3_000,
        loe_cliffs=[
            LOECliff(product_name="Xyrem (sodium oxybate)", indication="narcolepsy (cataplexy/EDS)",
                     peak_sales_millions=1_600, loe_year=2023, revenue_at_risk_millions=800,
                     replacement_urgency="medium"),  # managed via Xywav (low-sodium oxybate) switch
        ],
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=800, max_comfortable_deal_size_millions=3_000,
        ),
        ta_priorities={"neuroscience": 0.9, "oncology": 0.65},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, biologic=0.65),
        notes=(
            "Levered post-GW Pharma acquisition ($7.2B, 2021). Net debt ~$2.7B. "
            "Xywav/Xyrem (oxybate) narcolepsy franchise, Rylaze (asparaginase, oncology). "
            "Limited deal capacity; focus on Xywav vs Xyrem switch and pipeline. "
            "Data confidence: medium (0.60)."
        ),
    ),

    AcquirerProfile(
        company_id="ipsen", name="Ipsen S.A.", ticker="IPN.PA",
        country="France",
        cash_millions=1_200, annual_fcf_millions=700, market_cap_millions=7_500,
        strategic_areas=["oncology", "rare_disease", "neuroscience"],
        preferred_modalities=["small_molecule", "biologic", "peptide"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_200, max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={"oncology": 0.90, "rare_disease": 0.80, "neuroscience": 0.65},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, biologic=0.70,
                                                   peptide=0.80),
        loe_cliffs=[
            LOECliff(product_name="Somatuline (lanreotide)", indication="acromegaly/NETs",
                     peak_sales_millions=1_200, loe_year=2025, revenue_at_risk_millions=700),
        ],
        notes=(
            "Cabometyx (cabozantinib, licensed from Exelixis for Europe/ex-US), Onivyde, Dysport. "
            "Somatuline facing biosimilar erosion. Active BD to diversify. "
            "European mid-cap pharma with strong oncology/rare disease focus. "
            "Data confidence: medium (0.60)."
        ),
    ),

    AcquirerProfile(
        company_id="galapagos", name="Galapagos NV", ticker="GLPG",
        country="Belgium",
        cash_millions=3_000, debt_millions=100, annual_fcf_millions=-500,
        market_cap_millions=2_000,
        strategic_areas=["inflammation", "oncology", "cell_therapy", "fibrosis"],
        preferred_modalities=["small_molecule", "cell_therapy", "biologic"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 1", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_000, max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={"inflammation": 0.80, "oncology": 0.75, "cell_therapy": 0.75,
                       "fibrosis": 0.70},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, cell_therapy=0.70,
                                                   biologic=0.65),
        notes=(
            "Cash-heavy ($3B+) relative to market cap after Gilead deal unwinding. "
            "Filgotinib (JAK1) commercial failure forced strategy pivot. "
            "Now: acquired CellPoint (CAR-T manufacturing), acquired AbCellera partial stake. "
            "Rebuilding as oncology/cell therapy platform; burning cash. "
            "Unusual: buyer with very high cash/market cap ratio (~1.5x). "
            "Data confidence: medium-low (0.50)."
        ),
    ),

    AcquirerProfile(
        company_id="ascendis", name="Ascendis Pharma", ticker="ASND",
        country="Denmark",
        cash_millions=1_500, debt_millions=300, annual_fcf_millions=200,
        market_cap_millions=8_000,
        strategic_areas=["endocrinology", "rare_disease", "oncology"],
        preferred_modalities=["biologic", "small_molecule", "prodrug_platform"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=4_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_500, max_comfortable_deal_size_millions=4_000,
        ),
        ta_priorities={"endocrinology": 1.0, "rare_disease": 0.85, "oncology": 0.60},
        modality_capabilities=ModalityCapabilities(biologic=0.85, small_molecule=0.70),
        notes=(
            "TransCon prodrug platform: sustained-release via transient conjugation. "
            "Skytrofa (lonapegsomatropin, GHD) commercial; TransCon PTH (hypoparathyroidism Phase 3). "
            "TransCon TLR7/8 agonist oncology program. "
            "Balance sheet building as commercial ramp accelerates. "
            "Data confidence: medium (0.65)."
        ),
    ),

    AcquirerProfile(
        company_id="legend_biotech", name="Legend Biotech", ticker="LEGN",
        country="China/United States",
        cash_millions=1_000, debt_millions=200, annual_fcf_millions=-300,
        market_cap_millions=4_000,
        strategic_areas=["hematology", "oncology", "cell_therapy"],
        preferred_modalities=["cell_therapy", "bispecific"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=3_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_000, max_comfortable_deal_size_millions=3_000,
        ),
        ta_priorities={"hematology": 0.90, "oncology": 0.80, "cell_therapy": 1.0},
        modality_capabilities=ModalityCapabilities(cell_therapy=0.90, biologic=0.65),
        notes=(
            "Carvykti (ciltacabtagene autoleucel, BCMA CAR-T) for myeloma, partnered with JNJ. "
            "JNJ owns significant commercial rights; Legend retains China + milestone economics. "
            "CAR-T commercial ramp underway. Looking for next-gen cell therapy programs. "
            "Data confidence: medium (0.60)."
        ),
    ),
]

# ===========================================================================
# Phase 2b — China pharma: active licensors / regional acquirers
# ===========================================================================

CHINA_PHARMA_ACQUIRERS: list[AcquirerProfile] = [

    AcquirerProfile(
        company_id="beigene", name="BeiGene / Oncobiologics", ticker="ONC",
        country="China",
        cash_millions=5_000, debt_millions=500, annual_fcf_millions=-300,
        market_cap_millions=10_000,
        strategic_areas=["oncology", "hematology", "immunology"],
        preferred_modalities=["small_molecule", "biologic", "antibody"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=5_000, max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={"oncology": 1.0, "hematology": 0.85, "immunology": 0.70},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, monoclonal_antibody=0.80,
                                                   bispecific=0.70),
        notes=(
            "Brukinsa (zanubrutinib, BTK inhibitor) global approval — major revenue driver. "
            "Tislelizumab (anti-PD-1) China commercial + global licensing. "
            "US commercial infrastructure built. In-licensing from global biotech; "
            "also licenses out China-developed assets. "
            "Data confidence: medium (0.60)."
        ),
    ),

    AcquirerProfile(
        company_id="hengrui", name="Jiangsu Hengrui Pharmaceuticals", ticker="600276.SS",
        country="China",
        cash_millions=4_000, annual_fcf_millions=1_000, market_cap_millions=28_000,
        strategic_areas=["oncology", "immunology", "cardiometabolic", "anesthesia"],
        preferred_modalities=["small_molecule", "biologic", "antibody_drug_conjugate"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=3_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=4_000, max_comfortable_deal_size_millions=3_000,
        ),
        ta_priorities={"oncology": 1.0, "immunology": 0.80, "cardiometabolic": 0.65},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, monoclonal_antibody=0.80,
                                                   antibody_drug_conjugate=0.75),
        notes=(
            "China's largest pharma R&D spender. Camrelizumab (anti-PD-1), famitinib. "
            "Active out-licensor to global pharma — BMS deal for SHR-1210 derivatives. "
            "Increasing cross-border deal flow; target for global pharma licensing. "
            "Data confidence: medium-low (0.45); financials in CNY, partial disclosure."
        ),
    ),

    AcquirerProfile(
        company_id="innovent", name="Innovent Biologics", ticker="1801.HK",
        country="China",
        cash_millions=1_500, annual_fcf_millions=-200, market_cap_millions=3_500,
        strategic_areas=["oncology", "immunology", "ophthalmology", "cardiometabolic"],
        preferred_modalities=["biologic", "antibody", "bispecific"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=1_500,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_500, max_comfortable_deal_size_millions=1_500,
        ),
        ta_priorities={"oncology": 1.0, "immunology": 0.80, "ophthalmology": 0.60},
        modality_capabilities=ModalityCapabilities(monoclonal_antibody=0.85, bispecific=0.75),
        notes=(
            "Sintilimab (anti-PD-1); Lilly ended global collab — Innovent pivoting to self-commercialize. "
            "IBI310 (anti-CTLA-4), IBI326 (BCMA CAR-T). "
            "Primarily a licensor to global pharma; potential licensing target not M&A target. "
            "Data confidence: medium-low (0.48)."
        ),
    ),

    AcquirerProfile(
        company_id="akeso", name="Akeso Biopharma", ticker="9926.HK",
        country="China",
        cash_millions=1_000, annual_fcf_millions=-100, market_cap_millions=4_000,
        strategic_areas=["oncology", "immunology", "autoimmune"],
        preferred_modalities=["bispecific", "monoclonal_antibody"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=1_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_000, max_comfortable_deal_size_millions=1_000,
        ),
        ta_priorities={"oncology": 1.0, "immunology": 0.80, "autoimmune": 0.70},
        modality_capabilities=ModalityCapabilities(bispecific=0.90, monoclonal_antibody=0.85),
        notes=(
            "Ivonescimab (AK112, PD-1/VEGF bispecific): landmark Summit Therapeutics license "
            "(~$500M deal); superior OS data vs Keytruda in NSCLC (HARMONi-2). "
            "Cadonilimab (PD-1/CTLA-4 bispecific). Strong bispecific antibody platform. "
            "Primarily a licensor — assets licensed to global pharma, not acquirer. "
            "Data confidence: medium (0.55)."
        ),
    ),

    AcquirerProfile(
        company_id="hansoh", name="Hansoh Pharmaceutical Group", ticker="3692.HK",
        country="China",
        cash_millions=800, annual_fcf_millions=300, market_cap_millions=4_500,
        strategic_areas=["oncology", "cns", "metabolic"],
        preferred_modalities=["small_molecule", "antibody_drug_conjugate", "biologic"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=1_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=800, max_comfortable_deal_size_millions=1_000,
        ),
        ta_priorities={"oncology": 1.0, "cns": 0.75, "metabolic": 0.70},
        modality_capabilities=ModalityCapabilities(small_molecule=0.80, antibody_drug_conjugate=0.75),
        notes=(
            "HS-20093 (B7-H3 ADC) licensed to GSK for >$1B+ (global rights) — "
            "landmark China-to-global ADC licensing deal. "
            "CNS portfolio, metabolic pipeline. Growing out-licensor. "
            "Data confidence: medium-low (0.45)."
        ),
    ),

    AcquirerProfile(
        company_id="cspc", name="CSPC Pharmaceutical Group", ticker="1093.HK",
        country="China",
        cash_millions=1_200, annual_fcf_millions=500, market_cap_millions=5_500,
        strategic_areas=["oncology", "cns", "cardiometabolic", "anti_infective"],
        preferred_modalities=["small_molecule", "biologic", "antibody_drug_conjugate"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=1_500,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_200, max_comfortable_deal_size_millions=1_500,
        ),
        ta_priorities={"oncology": 0.85, "cns": 0.70, "cardiometabolic": 0.65},
        modality_capabilities=ModalityCapabilities(small_molecule=0.85, biologic=0.70,
                                                   antibody_drug_conjugate=0.65),
        notes=(
            "One of China's largest diversified pharma companies. "
            "Oncology, CNS, and metabolic focus. Increasing licensing out to global partners. "
            "Data confidence: low (0.40)."
        ),
    ),

    AcquirerProfile(
        company_id="sino_biopharm", name="Sino Biopharmaceutical", ticker="1177.HK",
        country="China/Hong Kong",
        cash_millions=1_000, annual_fcf_millions=400, market_cap_millions=3_500,
        strategic_areas=["oncology", "liver_disease", "respiratory", "autoimmune"],
        preferred_modalities=["biologic", "small_molecule"],
        bd_style=BDStyle.MIXED, preferred_phase="Phase 2", max_deal_size_millions=1_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=1_000, max_comfortable_deal_size_millions=1_000,
        ),
        ta_priorities={"oncology": 0.80, "liver_disease": 0.80, "autoimmune": 0.65},
        modality_capabilities=ModalityCapabilities(biologic=0.75, small_molecule=0.80),
        notes=(
            "Broad China pharma portfolio; increasingly active licensor to global pharma. "
            "GSK deals for hepatitis B assets. Liver disease + oncology China commercial strength. "
            "Data confidence: low (0.38)."
        ),
    ),
]

# ===========================================================================
# Lookup helpers
# ===========================================================================

ALL_NEW_ACQUIRERS: list[AcquirerProfile] = (
    MEGA_CAP_ACQUIRERS_V2 + LARGE_BIOTECH_ACQUIRERS + CHINA_PHARMA_ACQUIRERS
    + SPECIALTY_ACQUIRERS
)

ACQUIRER_REGISTRY_BY_ID: dict[str, AcquirerProfile] = {
    a.company_id: a for a in ALL_NEW_ACQUIRERS
}

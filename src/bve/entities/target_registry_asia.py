"""Target registry — Asia/China biotech licensing targets and regional acquisition candidates.

Section J: China / Asia biotech — licensing targets, partnership candidates, regional targets.

Classification note:
  Many China/Asia companies are more likely to be:
    - License-out targets (global pharma licenses a specific asset)
    - Partnership targets (co-development or co-commercialization)
    - Full-company acquisition (rare; only where CoC risk is low and strategic fit is high)

  Model accordingly — most are NOT normal full-company acquisition targets.
  The primary deal mechanism is asset-level licensing, NOT whole-company M&A.

Includes: China, Korea, Japan, India, Australia companies.
WuXi entities are CDMO/CRO infrastructure — not therapeutic targets.
"""
from __future__ import annotations

from bve.entities.target import (
    WatchlistTarget, TargetType, DataConfidence,
)

# ===========================================================================
# Section J — China biotech
# ===========================================================================

CHINA_BIOTECH_TARGETS: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="ZLAB", company_id="zai_lab", asset_id="a-zlab",
        company_name="Zai Lab",
        indication="Oncology, immunology (commercial + licensing in China/Asia-Pacific)",
        ranking_score=0.60, opportunity_score=0.55, conviction="medium",
        catalyst="Zejula (niraparib), Optune, Nuzyra China commercial; new in-licensing deals",
        therapeutic_area="oncology", modality="small_molecule", stage="approved",
        lead_asset="Zejula (niraparib, PARP inhibitor) + Optune (TTF) + pipeline",
        market_cap_millions=1_500, cash_millions=500,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="partnered",
        key_partner="GSK (niraparib), Novocure (Optune), multiple global pharma",
        mna_relevance_score=0.62, strategic_scarcity_score=0.65,
        asset_quality_quick_score=0.62, financing_pressure_score=0.38,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="HCM", company_id="hutchmed", asset_id="a-hcm",
        company_name="HUTCHMED (China) Limited",
        indication="Oncology: fruquintinib, surufatinib, savolitinib (China/global rights)",
        ranking_score=0.58, opportunity_score=0.52, conviction="medium",
        catalyst="Fruzaqla (fruquintinib) global commercial ramp; savolitinib label expansion",
        therapeutic_area="oncology", modality="small_molecule", stage="approved",
        lead_asset="Fruzaqla (fruquintinib, VEGFR1-3 inhibitor — global FDA approved)",
        market_cap_millions=1_200, cash_millions=400,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="partnered",
        key_partner="AstraZeneca (savolitinib); Takeda (fruquintinib ex-China)",
        mna_relevance_score=0.62, strategic_scarcity_score=0.65,
        asset_quality_quick_score=0.60, financing_pressure_score=0.38,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="9995.HK", company_id="remegen", asset_id="a-remegen",
        company_name="RemeGen Co., Ltd.",
        indication="ADCs, autoimmune (RC48 — disitamab vedotin; telitacicept for SLE)",
        ranking_score=0.60, opportunity_score=0.55, conviction="medium",
        catalyst="RC48 (disitamab vedotin) US NDA for urothelial/gastric; SEZAN-01 data",
        therapeutic_area="oncology", modality="antibody_drug_conjugate", stage="approved",
        lead_asset="RC48 (disitamab vedotin, HER2 ADC — approved in China; US NDA filed)",
        market_cap_millions=800, cash_millions=300,
        target_type=TargetType.PIPELINE_PORTFOLIO,
        ownership_status="clean",
        mna_relevance_score=0.65, strategic_scarcity_score=0.68,
        asset_quality_quick_score=0.65, financing_pressure_score=0.40,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="6990.HK", company_id="kelun_biotech", asset_id="a-kelun",
        company_name="Kelun-Biotech",
        indication="ADCs (TROP2, HER2, claudin18.2 — multiple global deals)",
        ranking_score=0.62, opportunity_score=0.58, conviction="medium",
        catalyst="SKB264 (TROP2 ADC, global rights licensed to Merck) Phase 3 data",
        therapeutic_area="oncology", modality="antibody_drug_conjugate", stage="phase_3",
        lead_asset="SKB264 (sacituzumab tirumotecan, TROP2 ADC — Merck global license)",
        market_cap_millions=1_500, cash_millions=400,
        target_type=TargetType.PLATFORM,
        ownership_status="partnered",
        key_partner="Merck (SKB264 global rights ~$1.4B deal); Pfizer (HER2 ADC)",
        mna_relevance_score=0.68, strategic_scarcity_score=0.72,
        asset_quality_quick_score=0.68, financing_pressure_score=0.35,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="1877.HK", company_id="junshi_biosciences", asset_id="a-junshi",
        company_name="Junshi Biosciences",
        indication="Oncology, autoimmune (toripalimab anti-PD-1; multiple programs)",
        ranking_score=0.52, opportunity_score=0.45, conviction="low",
        catalyst="Loqtorzi (toripalimab) US commercial ramp; new licensing deals",
        therapeutic_area="oncology", modality="monoclonal_antibody", stage="approved",
        lead_asset="Loqtorzi (toripalimab, anti-PD-1 — FDA approved nasopharyngeal carcinoma)",
        market_cap_millions=600, cash_millions=200,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="partnered",
        key_partner="Coherus BioSciences (US commercialization for toripalimab)",
        mna_relevance_score=0.55, strategic_scarcity_score=0.58,
        asset_quality_quick_score=0.55, financing_pressure_score=0.48,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="2105.HK", company_id="laekna", asset_id="a-laekna",
        company_name="Laekna Therapeutics",
        indication="Oncology (CDK4/6, KRAS, HER2 — precision oncology China/global licensing)",
        ranking_score=0.50, opportunity_score=0.45, conviction="low",
        catalyst="ATG-010 (selinexor follow-on) Phase 2 data; new licensing partnerships",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_2",
        lead_asset="ATG-010 (selinexor derivative, XPO1 inhibitor)",
        market_cap_millions=400, cash_millions=150,
        target_type=TargetType.PIPELINE_PORTFOLIO,
        ownership_status="clean",
        mna_relevance_score=0.52, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.50, financing_pressure_score=0.50,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="AAPG", company_id="ascentage_pharma", asset_id="a-ascentage",
        company_name="Ascentage Pharma Group",
        indication="Oncology: BCL-2 inhibitors, MDM2/MDMX dual inhibitors, Bcr-Abl TKIs",
        ranking_score=0.55, opportunity_score=0.50, conviction="low",
        catalyst="Lisaftoclax (BCL-2 inhibitor) Phase 3 CLL data; olverembatinib data",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_3",
        lead_asset="lisaftoclax (APG-2575, BCL-2 inhibitor for CLL/SLL)",
        market_cap_millions=500, cash_millions=200,
        target_type=TargetType.PIPELINE_PORTFOLIO,
        ownership_status="clean",
        mna_relevance_score=0.58, strategic_scarcity_score=0.62,
        asset_quality_quick_score=0.58, financing_pressure_score=0.45,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="1952.HK", company_id="everest_medicines", asset_id="a-everest",
        company_name="Everest Medicines",
        indication="Asia-Pacific commercialization rights for global assets (IgAN, oncology, ID)",
        ranking_score=0.48, opportunity_score=0.42, conviction="low",
        catalyst="Sparsentan (IgAN, licensed from Travere) China NDA; new licensing deals",
        therapeutic_area="immunology", modality="small_molecule", stage="approved",
        lead_asset="Sparsentan (China rights, IgA nephropathy) + antibiotic/ID portfolio",
        market_cap_millions=300, cash_millions=150,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="partnered",
        key_partner="Travere (sparsentan China rights); multiple global pharma",
        mna_relevance_score=0.50, strategic_scarcity_score=0.52,
        asset_quality_quick_score=0.50, financing_pressure_score=0.50,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="6185.HK", company_id="cansino_biologics", asset_id="a-cansino",
        company_name="CanSino Biologics",
        indication="Vaccines: meningococcal, COVID-19, pneumococcal, tuberculosis",
        ranking_score=0.45, opportunity_score=0.38, conviction="low",
        catalyst="MCV4 (meningococcal), pneumococcal PCV13i commercial; partnership",
        therapeutic_area="infectious_disease", modality="vaccine", stage="approved",
        lead_asset="MCV4 (tetravalent meningococcal conjugate vaccine)",
        market_cap_millions=400, cash_millions=150,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.45, strategic_scarcity_score=0.50,
        asset_quality_quick_score=0.48, financing_pressure_score=0.50,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="1548.HK", company_id="genscript", asset_id="a-genscript",
        company_name="GenScript Biotech",
        indication="Research tools + Legend Biotech stake (CAR-T); Probio (CAR-T products)",
        ranking_score=0.52, opportunity_score=0.48, conviction="low",
        catalyst="Legend Biotech (Carvykti) commercial ramp impact on GenScript value",
        therapeutic_area="platform", modality="cell_therapy", stage="approved",
        lead_asset="GenScript tools business + Legend Biotech majority stake",
        market_cap_millions=1_000, cash_millions=300,
        target_type=TargetType.PLATFORM,
        ownership_status="clean",
        mna_relevance_score=0.52, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.52, financing_pressure_score=0.42,
        data_confidence=DataConfidence.MEDIUM,
    ),
]

# ===========================================================================
# Korea biotech targets
# ===========================================================================

KOREA_BIOTECH_TARGETS: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="207940.KS", company_id="samsung_biologics", asset_id="a-samsung-bio",
        company_name="Samsung Biologics",
        indication="CDMO / biomanufacturing infrastructure (not therapeutics target)",
        ranking_score=0.50, opportunity_score=0.45, conviction="low",
        catalyst="CDMO capacity expansion; new manufacturing partnerships with global pharma",
        therapeutic_area="platform", modality="biomanufacturing", stage="approved",
        lead_asset="Samsung Biologics CDMO platform (largest single-site biomanufacturing capacity)",
        market_cap_millions=30_000, cash_millions=2_000,
        target_type=TargetType.PLATFORM,
        ownership_status="clean",
        mna_relevance_score=0.45, strategic_scarcity_score=0.70,
        asset_quality_quick_score=0.80, financing_pressure_score=0.15,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="068270.KS", company_id="celltrion", asset_id="a-celltrion",
        company_name="Celltrion",
        indication="Biosimilars + innovator biologics (infliximab, trastuzumab, rituximab)",
        ranking_score=0.48, opportunity_score=0.40, conviction="low",
        catalyst="CT-P59 (regdanvimab) lifecycle; new biosimilar launches; Zymfentra commercial",
        therapeutic_area="immunology", modality="biologic", stage="approved",
        lead_asset="Zymfentra (subcutaneous infliximab) + biosimilar portfolio",
        market_cap_millions=8_000, cash_millions=1_000,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.45, strategic_scarcity_score=0.52,
        asset_quality_quick_score=0.55, financing_pressure_score=0.30,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="326030.KS", company_id="sk_biopharm", asset_id="a-sk-biopharm",
        company_name="SK Biopharmaceuticals",
        indication="CNS, sleep disorders (cenobamate, solriamfetol)",
        ranking_score=0.52, opportunity_score=0.45, conviction="low",
        catalyst="Xcopri (cenobamate) US commercial ramp expansion; Sunosi licensing",
        therapeutic_area="neuroscience", modality="small_molecule", stage="approved",
        lead_asset="Xcopri (cenobamate, novel sodium channel for epilepsy)",
        market_cap_millions=2_000, cash_millions=500,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.52, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.55, financing_pressure_score=0.35,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="028300.KQ", company_id="hlb_life_science", asset_id="a-hlb",
        company_name="HLB Life Science",
        indication="Oncology (rivoceranib/apatinib: HCC, gastric cancer)",
        ranking_score=0.50, opportunity_score=0.45, conviction="low",
        catalyst="Rivoceranib US NDA for HCC; combination trial data",
        therapeutic_area="oncology", modality="small_molecule", stage="approved",
        lead_asset="rivoceranib (apatinib, VEGFR2 inhibitor — HCC approved Korea)",
        market_cap_millions=600, cash_millions=100,
        target_type=TargetType.SINGLE_ASSET,
        ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.52,
        asset_quality_quick_score=0.50, financing_pressure_score=0.48,
        data_confidence=DataConfidence.LOW,
    ),
]

# ===========================================================================
# Japan biotech targets (smaller/specialty)
# ===========================================================================

JAPAN_BIOTECH_TARGETS: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="4587.T", company_id="peptidream", asset_id="a-peptidream",
        company_name="PeptiDream",
        indication="Peptide discovery platform: radiopharmaceuticals, constrained peptides",
        ranking_score=0.58, opportunity_score=0.55, conviction="medium",
        catalyst="Radiopeptide program Phase 1/2 data; new global pharma partnerships",
        therapeutic_area="platform", modality="peptide", stage="phase_1",
        lead_asset="Constrained peptide discovery platform + radiopharmaceutical programs",
        market_cap_millions=1_500, cash_millions=300,
        target_type=TargetType.PLATFORM,
        ownership_status="partnered",
        key_partner="BMS, Novartis, Ono Pharmaceutical (peptide discovery)",
        mna_relevance_score=0.62, strategic_scarcity_score=0.68,
        asset_quality_quick_score=0.62, financing_pressure_score=0.30,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="4565.T", company_id="sosei_heptares", asset_id="a-sosei",
        company_name="Sosei Heptares",
        indication="GPCR structure-based drug design platform (CNS, respiratory, oncology)",
        ranking_score=0.55, opportunity_score=0.48, conviction="low",
        catalyst="HTL0016878 (M1 PAM, Alzheimer's) Phase 2 data; new GPCR licensing deals",
        therapeutic_area="platform", modality="small_molecule", stage="phase_2",
        lead_asset="StaR GPCR platform + HTL0016878 (M1 muscarinic PAM)",
        market_cap_millions=800, cash_millions=200,
        target_type=TargetType.PLATFORM,
        ownership_status="partnered",
        key_partner="AbbVie, Pfizer, Daiichi Sankyo (GPCR collaborations)",
        mna_relevance_score=0.58, strategic_scarcity_score=0.62,
        asset_quality_quick_score=0.58, financing_pressure_score=0.38,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="4506.T", company_id="sumitomo_pharma", asset_id="a-sumitomo",
        company_name="Sumitomo Pharma",
        indication="CNS, oncology, rare disease (Japan/global diverse portfolio)",
        ranking_score=0.48, opportunity_score=0.40, conviction="low",
        catalyst="Orgovyx (relugolix) global commercial; ulotaront Phase 3 schizophrenia data",
        therapeutic_area="neuroscience", modality="small_molecule", stage="approved",
        lead_asset="Orgovyx (relugolix, GnRH antagonist) + ulotaront (TAAR1 agonist schizophrenia)",
        market_cap_millions=1_500, cash_millions=400,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.52,
        asset_quality_quick_score=0.52, financing_pressure_score=0.45,
        data_confidence=DataConfidence.MEDIUM,
    ),
]

# ===========================================================================
# India pharma (specialty and generics; limited M&A relevance for biotech)
# ===========================================================================

INDIA_PHARMA_TARGETS: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="BIOCON.NS", company_id="biocon", asset_id="a-biocon",
        company_name="Biocon",
        indication="Biosimilars (trastuzumab, bevacizumab, insulin, adalimumab), generics, Syngene CRO",
        ranking_score=0.45, opportunity_score=0.38, conviction="low",
        catalyst="Biosimilar launches in US/EU; Biocon Biologics scale-up; Syngene growth",
        therapeutic_area="platform", modality="biologic", stage="approved",
        lead_asset="Biosimilar portfolio (Fulphila, Ogivri, Hulio) + Biocon Biologics platform",
        market_cap_millions=3_000, cash_millions=500,
        target_type=TargetType.PLATFORM,
        ownership_status="clean",
        mna_relevance_score=0.42, strategic_scarcity_score=0.48,
        asset_quality_quick_score=0.48, financing_pressure_score=0.42,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="RDY", company_id="dr_reddys", asset_id="a-rdy",
        company_name="Dr. Reddy's Laboratories",
        indication="Specialty generics, biosimilars, NCE pipeline (oncology, neurology)",
        ranking_score=0.42, opportunity_score=0.35, conviction="low",
        catalyst="Branded specialty US launch; biosimilar approvals; licensing-out deals",
        therapeutic_area="platform", modality="small_molecule", stage="approved",
        lead_asset="Specialty generics + novated pharma pipeline (DRL-2020, etc.)",
        market_cap_millions=6_000, cash_millions=700,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.38, strategic_scarcity_score=0.42,
        asset_quality_quick_score=0.45, financing_pressure_score=0.32,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="CIPLA.NS", company_id="cipla", asset_id="a-cipla",
        company_name="Cipla",
        indication="Respiratory, HIV, oncology generics + branded specialty",
        ranking_score=0.40, opportunity_score=0.32, conviction="low",
        catalyst="US specialty launches; respiratory generic ANDA pipeline; Africa HIV growth",
        therapeutic_area="platform", modality="small_molecule", stage="approved",
        lead_asset="India/global respiratory + HIV + oncology generics",
        market_cap_millions=5_000, cash_millions=600,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.35, strategic_scarcity_score=0.40,
        asset_quality_quick_score=0.42, financing_pressure_score=0.30,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="SUNPHARMA.NS", company_id="sun_pharma", asset_id="a-sunpharma",
        company_name="Sun Pharmaceutical Industries",
        indication="Specialty dermatology, ophthalmology, oncology (US + India)",
        ranking_score=0.42, opportunity_score=0.35, conviction="low",
        catalyst="Ilumya/Cequa US commercial ramp; specialty pipeline NDA filings",
        therapeutic_area="platform", modality="small_molecule", stage="approved",
        lead_asset="Ilumya (tildrakizumab) + Cequa (cyclosporine) + specialty US pipeline",
        market_cap_millions=8_000, cash_millions=900,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.38, strategic_scarcity_score=0.42,
        asset_quality_quick_score=0.45, financing_pressure_score=0.28,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="GLENMARK.NS", company_id="glenmark", asset_id="a-glenmark",
        company_name="Glenmark Pharmaceuticals",
        indication="Dermatology, respiratory, oncology (specialty generics + biologics)",
        ranking_score=0.38, opportunity_score=0.30, conviction="very-low",
        catalyst="Ryaltris (olopatadine/mometasone) US ramp; Ristova biologic launch",
        therapeutic_area="platform", modality="small_molecule", stage="approved",
        lead_asset="Ryaltris (FDC nasal spray) + Glenmark Biosciences",
        market_cap_millions=1_500, cash_millions=200,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.32, strategic_scarcity_score=0.35,
        asset_quality_quick_score=0.38, financing_pressure_score=0.52,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="LUPIN.NS", company_id="lupin", asset_id="a-lupin",
        company_name="Lupin Limited",
        indication="Respiratory, CNS, cardiovascular generics + specialty",
        ranking_score=0.38, opportunity_score=0.30, conviction="very-low",
        catalyst="US generic approvals; Spiriva generic; specialty US launches",
        therapeutic_area="platform", modality="small_molecule", stage="approved",
        lead_asset="Respiratory inhalation generics + US specialty pipeline",
        market_cap_millions=4_000, cash_millions=400,
        target_type=TargetType.COMMERCIAL_FRANCHISE,
        ownership_status="clean",
        mna_relevance_score=0.30, strategic_scarcity_score=0.35,
        asset_quality_quick_score=0.38, financing_pressure_score=0.40,
        data_confidence=DataConfidence.LOW,
    ),
]

# Combined for registry import
ASIA_TARGETS: list[WatchlistTarget] = (
    CHINA_BIOTECH_TARGETS + KOREA_BIOTECH_TARGETS
    + JAPAN_BIOTECH_TARGETS + INDIA_PHARMA_TARGETS
)

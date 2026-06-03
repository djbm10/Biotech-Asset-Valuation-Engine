"""Additional target registry — lower-tier and remaining entries from the full spec.

Supplements the four primary sub-registries with companies that were missing,
including lower-conviction watch entries and cross-TA assets.

Sections
--------
  A2: Additional Oncology (10 companies)
  B2: Additional Immunology / FcRn (4 companies)
  C2: Additional Rare Disease (5 companies)
  D2: Additional CNS (3 companies)
  E2: Additional Cardiometabolic / Respiratory (4 companies)
  F2: Additional Hematology (3 companies)
  G2: Additional Ophthalmology (2 companies)
  H2: Additional Infectious Disease (2 companies)
  I2: Additional Platform / Diagnostics (4 companies)
"""
from __future__ import annotations

from bve.entities.target import WatchlistTarget, TargetType, DataConfidence

# ===========================================================================
# Section A2 — Additional oncology targets
# ===========================================================================

ONCOLOGY_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="ARVN", company_id="arvinas", asset_id="a-arvn",
        company_name="Arvinas",
        indication="Prostate cancer, breast cancer (PROTAC targeted protein degraders)",
        ranking_score=0.72, opportunity_score=0.65, conviction="medium",
        catalyst="ARV-766 Phase 3 MAIA-like mCRPC readout; ARV-471 (vepdegestrant) Phase 3 BC",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_3",
        lead_asset="ARV-766 (AR PROTAC mCRPC), ARV-471 (ERα PROTAC BC)",
        market_cap_millions=2_200, cash_millions=600,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.72, strategic_scarcity_score=0.82,
        asset_quality_quick_score=0.68, financing_pressure_score=0.38,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="IDYA", company_id="ideaya_biosciences", asset_id="a-idya",
        company_name="Ideaya Biosciences",
        indication="NSCLC, uveal melanoma (synthetic lethality: MAT2A, POLQ, PARG inhibition)",
        ranking_score=0.68, opportunity_score=0.62, conviction="medium",
        catalyst="IDE397 (MAT2A inhib) Phase 2 MTAP-deleted NSCLC data; IDE161 (POLQ)",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_2",
        lead_asset="IDE397 (MAT2A inhibitor), IDE161 (POLQ inhibitor)",
        market_cap_millions=1_400, cash_millions=450,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.72, strategic_scarcity_score=0.80,
        asset_quality_quick_score=0.70, financing_pressure_score=0.30,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="RCUS", company_id="arcus_biosciences", asset_id="a-rcus",
        company_name="Arcus Biosciences",
        indication="NSCLC, GI cancers (IO combos: TIGIT + CD73/A2aR + anti-PD-1)",
        ranking_score=0.62, opportunity_score=0.58, conviction="medium-low",
        catalyst="domvanalimab (TIGIT) + zimberelimab Phase 3 NSCLC ARC-7 readout",
        therapeutic_area="oncology", modality="biologic", stage="phase_3",
        lead_asset="domvanalimab (anti-TIGIT), AB928 (A2aR/A2bR dual inhib)",
        market_cap_millions=1_200, cash_millions=700,
        target_type=TargetType.PLATFORM, ownership_status="partnered",
        mna_relevance_score=0.65, strategic_scarcity_score=0.70,
        asset_quality_quick_score=0.62, financing_pressure_score=0.28,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="ENLV", company_id="enliven_therapeutics", asset_id="a-enlv",
        company_name="Enliven Therapeutics",
        indication="CML, Ph+ ALL (BCR-ABL1 T315I-inclusive inhibitor)",
        ranking_score=0.62, opportunity_score=0.55, conviction="medium-low",
        catalyst="ELVN-001 Phase 2 BCR-ABL1 pan-inhibitor CML/Ph+ ALL dose escalation",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_2",
        lead_asset="ELVN-001 (BCR-ABL1 inhibitor)",
        market_cap_millions=900, cash_millions=350,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.62, strategic_scarcity_score=0.68,
        asset_quality_quick_score=0.62, financing_pressure_score=0.35,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="NVCR", company_id="novocure", asset_id="a-nvcr",
        company_name="NovoCure",
        indication="GBM (commercial), NSCLC/ovarian/GBM adj (Phase 3 LUNAR/ENGOT-OV50)",
        ranking_score=0.62, opportunity_score=0.55, conviction="medium-low",
        catalyst="LUNAR-1 NSCLC OS data; ENGOT-OV50 ovarian Phase 3 readout",
        therapeutic_area="oncology", modality="device_based_therapy", stage="commercial",
        lead_asset="TTFields (tumor treating electric fields) Optune system",
        market_cap_millions=2_500, cash_millions=800,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.55, strategic_scarcity_score=0.75,
        asset_quality_quick_score=0.60, financing_pressure_score=0.30,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="TGTX", company_id="tg_therapeutics", asset_id="a-tgtx",
        company_name="TG Therapeutics",
        indication="MS, CLL (ublituximab CD20 mAb commercial; umbralisib PI3Kδ/CK1ε)",
        ranking_score=0.50, opportunity_score=0.45, conviction="low",
        catalyst="Briumvi (ublituximab) MS commercial ramp; UNITY-CLL update",
        therapeutic_area="oncology", modality="biologic", stage="commercial",
        lead_asset="Briumvi (ublituximab-xiiy; CD20 mAb for RMS)",
        market_cap_millions=2_200, cash_millions=350,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.55, financing_pressure_score=0.40,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="AGEN", company_id="agenus", asset_id="a-agen",
        company_name="Agenus",
        indication="Colorectal cancer, solid tumors (botensilimab CTLA-4 + balstilimab PD-1)",
        ranking_score=0.52, opportunity_score=0.48, conviction="low",
        catalyst="botensilimab (CTLA-4 IgG1 Fc-enhanced) Phase 2/3 mCRC data; NDA/BLA filing",
        therapeutic_area="oncology", modality="biologic", stage="phase_3",
        lead_asset="botensilimab (anti-CTLA-4) + balstilimab (anti-PD-1)",
        market_cap_millions=900, cash_millions=250,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.55, strategic_scarcity_score=0.60,
        asset_quality_quick_score=0.55, financing_pressure_score=0.55,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="IMCR", company_id="immunocore", asset_id="a-imcr",
        company_name="Immunocore",
        indication="Uveal melanoma (commercial), NSCLC, melanoma (ImmTAC bispecific TCR)",
        ranking_score=0.60, opportunity_score=0.55, conviction="medium-low",
        catalyst="KIMMTRAK commercial ramp; IMC-F106C (PRAME TCR-HLA) Phase 2/3 melanoma",
        therapeutic_area="oncology", modality="bispecific", stage="commercial",
        lead_asset="KIMMTRAK (tebentafusp; gp100 ImmTAC for uveal melanoma)",
        market_cap_millions=2_800, cash_millions=600,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.65, strategic_scarcity_score=0.80,
        asset_quality_quick_score=0.65, financing_pressure_score=0.30,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="VTAK", company_id="tango_therapeutics", asset_id="a-vtak",
        company_name="Tango Therapeutics",
        indication="Solid tumors (PRMT5 + USP1 synthetic lethality)",
        ranking_score=0.48, opportunity_score=0.42, conviction="low",
        catalyst="TNG348 (USP1 MTAP-del) Phase 1/2 dose expansion; TNG260 (PRMT5) Phase 1",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_1",
        lead_asset="TNG348 (USP1 inhibitor), TNG260 (PRMT5 inhibitor)",
        market_cap_millions=400, cash_millions=180,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.55, strategic_scarcity_score=0.70,
        asset_quality_quick_score=0.55, financing_pressure_score=0.50,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="KPTI", company_id="karyopharm", asset_id="a-kpti",
        company_name="Karyopharm Therapeutics",
        indication="Multiple myeloma, MDS (selinexor XPO1 inhibitor commercial)",
        ranking_score=0.40, opportunity_score=0.35, conviction="low",
        catalyst="XPOVIO label expansion; generic competition dynamics",
        therapeutic_area="oncology", modality="small_molecule", stage="commercial",
        lead_asset="XPOVIO (selinexor; XPO1 inhibitor) MM/MDS",
        market_cap_millions=250, cash_millions=120,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.40, strategic_scarcity_score=0.45,
        asset_quality_quick_score=0.42, financing_pressure_score=0.65,
        data_confidence=DataConfidence.MEDIUM,
    ),

    # --- Previously missing, now added ---

    WatchlistTarget(
        ticker="RLAY", company_id="relay_therapeutics", asset_id="a-rlay",
        company_name="Relay Therapeutics",
        indication="Breast cancer, solid tumors (PI3Kα mutant-selective RLY-2608)",
        ranking_score=0.70, opportunity_score=0.65, conviction="medium",
        catalyst="RLY-2608 (PI3Kα-mut selective) Phase 3 INAVO360-like trial; INAVO combo data",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_3",
        lead_asset="RLY-2608 (PI3Kα mutation-selective inhibitor; HR+/HER2- BC)",
        market_cap_millions=1_800, cash_millions=550,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.72, strategic_scarcity_score=0.82,
        asset_quality_quick_score=0.70, financing_pressure_score=0.32,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="SWTX", company_id="springworks_therapeutics", asset_id="a-swtx",
        company_name="SpringWorks Therapeutics",
        indication="Desmoid tumors (nirogacestat commercial), NF1-PN (mirdametinib Phase 3)",
        ranking_score=0.65, opportunity_score=0.60, conviction="medium-low",
        catalyst="Ogsiveo (nirogacestat) desmoid commercial ramp; mirdametinib NDA filing ~2026",
        therapeutic_area="oncology", modality="small_molecule", stage="commercial",
        lead_asset="Ogsiveo (nirogacestat; γ-secretase inhib) desmoid tumors",
        market_cap_millions=2_200, cash_millions=600,
        target_type=TargetType.PIPELINE_PORTFOLIO, ownership_status="clean",
        mna_relevance_score=0.68, strategic_scarcity_score=0.72,
        asset_quality_quick_score=0.68, financing_pressure_score=0.28,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="ITOS", company_id="iteos_therapeutics", asset_id="a-itos",
        company_name="iTeos Therapeutics",
        indication="NSCLC, solid tumors (TIGIT EOS-448 + adenosine A2aR inupadenant)",
        ranking_score=0.58, opportunity_score=0.52, conviction="medium-low",
        catalyst="EOS-448 (anti-TIGIT) Phase 2/3 with pembrolizumab NSCLC; AZ partnership",
        therapeutic_area="oncology", modality="biologic", stage="phase_2",
        lead_asset="EOS-448 (anti-TIGIT mAb), inupadenant (adenosine A2aR inhib)",
        market_cap_millions=800, cash_millions=350,
        target_type=TargetType.PLATFORM, ownership_status="partnered",
        mna_relevance_score=0.60, strategic_scarcity_score=0.65,
        asset_quality_quick_score=0.58, financing_pressure_score=0.32,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="MRUS", company_id="merus_nv", asset_id="a-mrus",
        company_name="Merus N.V.",
        indication="NRG1 fusion cancers, HER2+ tumors (zenocutuzumab bispecific)",
        ranking_score=0.65, opportunity_score=0.60, conviction="medium-low",
        catalyst="Bizengri (zenocutuzumab) FDA approval 2024 NRG1+ NSCLC/pancreatic; Petosemtamab Phase 3",
        therapeutic_area="oncology", modality="bispecific", stage="commercial",
        lead_asset="Bizengri (zenocutuzumab-zbco; HER2xHER3 bispecific; NRG1+ cancers)",
        market_cap_millions=2_000, cash_millions=500,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.68, strategic_scarcity_score=0.75,
        asset_quality_quick_score=0.68, financing_pressure_score=0.28,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="VSTM", company_id="verastem_oncology", asset_id="a-vstm",
        company_name="Verastem Oncology",
        indication="KRAS-mutant NSCLC, NF1, low-grade serous ovarian (VS-6766 + defactinib)",
        ranking_score=0.55, opportunity_score=0.50, conviction="medium-low",
        catalyst="VS-6766 (RAF/MEK clamp) + defactinib (FAK inhib) Phase 2 LGSOC/KRAS NSCLC data",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_2",
        lead_asset="VS-6766 (RAF/MEK clamp inhibitor), defactinib (FAK inhibitor)",
        market_cap_millions=350, cash_millions=150,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.58, strategic_scarcity_score=0.65,
        asset_quality_quick_score=0.55, financing_pressure_score=0.50,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="PTGX", company_id="protagonist_therapeutics", asset_id="a-ptgx",
        company_name="Protagonist Therapeutics",
        indication="Polycythemia vera, IBD (rusfertide hepcidin mimetic; PN-943 oral IL-17)",
        ranking_score=0.68, opportunity_score=0.62, conviction="medium",
        catalyst="rusfertide Phase 3 VERIFY PV readout; PN-943 Phase 2 UC data; JNJ partnership",
        therapeutic_area="oncology", modality="peptide", stage="phase_3",
        lead_asset="rusfertide (hepcidin mimetic peptide; PV hematocrit control)",
        market_cap_millions=2_500, cash_millions=700,
        target_type=TargetType.PLATFORM, ownership_status="partnered",
        mna_relevance_score=0.70, strategic_scarcity_score=0.75,
        asset_quality_quick_score=0.68, financing_pressure_score=0.25,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="COGT", company_id="cogent_biosciences", asset_id="a-cogt",
        company_name="Cogent Biosciences",
        indication="Mastocytosis, GIST, AML (bezuclastinib KIT D816V inhibitor)",
        ranking_score=0.72, opportunity_score=0.68, conviction="medium",
        catalyst="bezuclastinib Phase 3 SUMMIT advanced SM readout; NDA filing 2026",
        therapeutic_area="oncology", modality="small_molecule", stage="phase_3",
        lead_asset="bezuclastinib (highly selective KIT D816V inhibitor; mastocytosis/GIST)",
        market_cap_millions=3_000, cash_millions=900,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.74, strategic_scarcity_score=0.80,
        asset_quality_quick_score=0.72, financing_pressure_score=0.22,
        data_confidence=DataConfidence.MEDIUM,
    ),
]


# ===========================================================================
# Section B2 — Additional Immunology targets
# ===========================================================================

IMMUNOLOGY_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="IMVT", company_id="immunovant", asset_id="a-imvt",
        company_name="Immunovant",
        indication="Myasthenia gravis, CIDP, thyroid eye disease (FcRn mAb)",
        ranking_score=0.72, opportunity_score=0.68, conviction="medium",
        catalyst="batoclimab Phase 3 MG, TED, CIDP data readouts; NDA/BLA filing 2026",
        therapeutic_area="immunology", modality="biologic", stage="phase_3",
        lead_asset="batoclimab (anti-FcRn; IgG reduction in autoimmune)",
        market_cap_millions=3_500, cash_millions=900,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.74, strategic_scarcity_score=0.78,
        asset_quality_quick_score=0.72, financing_pressure_score=0.25,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="ARDX", company_id="ardelyx", asset_id="a-ardx",
        company_name="Ardelyx",
        indication="IBS-C (commercial), CKD hyperphosphatemia (Phase 3 TAILOR-CKD)",
        ranking_score=0.50, opportunity_score=0.45, conviction="low",
        catalyst="Ibsrela (tenapanor) IBS-C commercial ramp; Xphozah (tenapanor) CKD-aP",
        therapeutic_area="immunology", modality="small_molecule", stage="commercial",
        lead_asset="tenapanor (NHE3 inhibitor); Ibsrela + Xphozah approved",
        market_cap_millions=900, cash_millions=220,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.48, strategic_scarcity_score=0.50,
        asset_quality_quick_score=0.52, financing_pressure_score=0.45,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="CHRS", company_id="coherus_biosciences", asset_id="a-chrs",
        company_name="Coherus BioSciences",
        indication="Oncology/immunology (casdozokitug IL-2/IL-10 fusion; biosimilars)",
        ranking_score=0.38, opportunity_score=0.32, conviction="very-low",
        catalyst="casdozokitug (CASPIAN-1) Phase 2 HCC/mCRC; biosimilar Yusimry, Cimerli",
        therapeutic_area="immunology", modality="biologic", stage="phase_2",
        lead_asset="casdozokitug (IL-2/IL-10 ortho-fusion protein)",
        market_cap_millions=300, cash_millions=100,
        target_type=TargetType.PIPELINE_PORTFOLIO, ownership_status="clean",
        mna_relevance_score=0.38, strategic_scarcity_score=0.42,
        asset_quality_quick_score=0.40, financing_pressure_score=0.70,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="PRMD", company_id="prometheus_biosciences", asset_id="a-prmd-precedent",
        company_name="Prometheus Biosciences (Acquired by Merck 2023 — PRECEDENT)",
        indication="IBD (tulisokibart anti-TL1A; Crohn's disease, UC)",
        ranking_score=0.0, opportunity_score=0.0, conviction="precedent",
        catalyst="PRECEDENT: acquired Merck 2023 ~$10.8B; tulisokibart pivotal Phase 3",
        therapeutic_area="immunology", modality="biologic", stage="phase_3",
        lead_asset="tulisokibart (anti-TL1A mAb for IBD)",
        market_cap_millions=0, cash_millions=0,
        target_type=TargetType.SINGLE_ASSET, ownership_status="acquired",
        mna_relevance_score=0.0, strategic_scarcity_score=0.90,
        asset_quality_quick_score=0.90, financing_pressure_score=0.0,
        data_confidence=DataConfidence.HIGH,
    ),
]


# ===========================================================================
# Section C2 — Additional Rare Disease targets
# ===========================================================================

RARE_DISEASE_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="FOLD", company_id="amicus_therapeutics", asset_id="a-fold",
        company_name="Amicus Therapeutics",
        indication="Fabry disease (migalastat commercial), Pompe (AT-GAA Phase 3)",
        ranking_score=0.58, opportunity_score=0.52, conviction="medium-low",
        catalyst="AT-GAA (cipaglucosidase alfa + miglustat) Pompe Phase 3 PROPEL-2; Galafold ramp",
        therapeutic_area="rare_disease", modality="small_molecule", stage="commercial",
        lead_asset="Galafold (migalastat; Fabry), cipaglucosidase alfa (Pompe)",
        market_cap_millions=2_200, cash_millions=500,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.60, strategic_scarcity_score=0.65,
        asset_quality_quick_score=0.60, financing_pressure_score=0.40,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="PTCT", company_id="ptc_therapeutics", asset_id="a-ptct",
        company_name="PTC Therapeutics",
        indication="DMD (Translarna ataluren, SRP-9001 gene therapy), Friedreich's ataxia",
        ranking_score=0.55, opportunity_score=0.48, conviction="low",
        catalyst="omaveloxolone (Skyclarys FA) commercial; SRP-9001 DMD gene therapy label",
        therapeutic_area="rare_disease", modality="small_molecule", stage="commercial",
        lead_asset="Skyclarys (omaveloxolone; Friedreich's ataxia, commercial 2023)",
        market_cap_millions=1_600, cash_millions=300,
        target_type=TargetType.PIPELINE_PORTFOLIO, ownership_status="clean",
        mna_relevance_score=0.55, strategic_scarcity_score=0.62,
        asset_quality_quick_score=0.55, financing_pressure_score=0.50,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="MIRM", company_id="mirum_pharmaceuticals", asset_id="a-mirm",
        company_name="Mirum Pharmaceuticals",
        indication="PFIC, Alagille syndrome, PSC (IBAT inhibitors — volixibat, maralixibat)",
        ranking_score=0.62, opportunity_score=0.58, conviction="medium-low",
        catalyst="volixibat Phase 3 PFIC/PSC; maralixibat (Livmarli) Alagille commercial",
        therapeutic_area="rare_disease", modality="small_molecule", stage="commercial",
        lead_asset="Livmarli (maralixibat; IBAT inhibitor) Alagille; volixibat PFIC/PSC",
        market_cap_millions=1_100, cash_millions=320,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.65, strategic_scarcity_score=0.72,
        asset_quality_quick_score=0.65, financing_pressure_score=0.35,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="INBR", company_id="inhibrx", asset_id="a-inbr",
        company_name="Inhibrx",
        indication="Alpha-1 antitrypsin deficiency (INBRX-101), oncology (OX40L x GITRL)",
        ranking_score=0.60, opportunity_score=0.55, conviction="medium-low",
        catalyst="INBRX-101 (recombinant AAT) Phase 2 AATD; INBRX-106 Phase 1/2 IO",
        therapeutic_area="rare_disease", modality="biologic", stage="phase_2",
        lead_asset="INBRX-101 (recombinant alpha-1 antitrypsin for AATD)",
        market_cap_millions=1_200, cash_millions=380,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.62, strategic_scarcity_score=0.70,
        asset_quality_quick_score=0.62, financing_pressure_score=0.32,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="DSGN", company_id="design_therapeutics", asset_id="a-dsgn",
        company_name="Design Therapeutics",
        indication="Friedreich's ataxia, myotonic dystrophy (repeat expansion diseases)",
        ranking_score=0.42, opportunity_score=0.38, conviction="low",
        catalyst="DT-168 (GAA repeat) Friedreich's Phase 1/2; DM1 small molecule",
        therapeutic_area="rare_disease", modality="small_molecule", stage="phase_1",
        lead_asset="DT-168 (GAA CGG repeat targeting, Friedreich's ataxia)",
        market_cap_millions=280, cash_millions=150,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.68,
        asset_quality_quick_score=0.48, financing_pressure_score=0.55,
        data_confidence=DataConfidence.LOW,
    ),
]


# ===========================================================================
# Section D2 — Additional CNS targets
# ===========================================================================

CNS_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="ACMR", company_id="ac_immune", asset_id="a-acmr",
        company_name="AC Immune",
        indication="Alzheimer's disease, Parkinson's (tau / alpha-syn immunotherapy)",
        ranking_score=0.42, opportunity_score=0.38, conviction="low",
        catalyst="semorinemab (anti-tau) Phase 2 prodromal AD; ACI-35.030 pS396-tau vaccine",
        therapeutic_area="cns", modality="biologic", stage="phase_2",
        lead_asset="semorinemab (anti-tau mAb), ACI-35.030 (tau phospho-vaccine)",
        market_cap_millions=350, cash_millions=150,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.45, strategic_scarcity_score=0.60,
        asset_quality_quick_score=0.45, financing_pressure_score=0.55,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="RVNC", company_id="revance_therapeutics", asset_id="a-rvnc",
        company_name="Revance Therapeutics",
        indication="Cervical dystonia, spasticity, aesthetics (daxibotulinumtoxinA)",
        ranking_score=0.45, opportunity_score=0.40, conviction="low",
        catalyst="DAXXIFY (daxibotulinumtoxinA-lanm) commercial cervical dystonia + aesthetics",
        therapeutic_area="cns", modality="biologic", stage="commercial",
        lead_asset="DAXXIFY (daxibotulinumtoxinA-lanm; long-acting BoNT)",
        market_cap_millions=600, cash_millions=200,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.45, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.50, financing_pressure_score=0.58,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="ALDX", company_id="aldeyra_therapeutics_cns", asset_id="a-aldx-cns",
        company_name="Aldeyra Therapeutics",
        indication="Dry eye disease, SJögren's, neuroinflammation (ADX-2191 vitreoretinal)",
        ranking_score=0.38, opportunity_score=0.32, conviction="very-low",
        catalyst="reproxalap NDA re-submission dry eye; ADX-2191 Phase 3 vitreoretinal lymphoma",
        therapeutic_area="cns", modality="small_molecule", stage="phase_3",
        lead_asset="reproxalap (RASP modulator) dry eye; ADX-2191 vitreoretinal lymphoma",
        market_cap_millions=200, cash_millions=80,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.40, strategic_scarcity_score=0.48,
        asset_quality_quick_score=0.40, financing_pressure_score=0.68,
        data_confidence=DataConfidence.LOW,
    ),
]


# ===========================================================================
# Section E2 — Additional Cardiometabolic / Respiratory targets
# ===========================================================================

CARDIOMETABOLIC_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="ESPR", company_id="esperion_therapeutics", asset_id="a-espr",
        company_name="Esperion Therapeutics",
        indication="LDL cholesterol lowering (bempedoic acid commercial; CLEAR outcomes data)",
        ranking_score=0.50, opportunity_score=0.45, conviction="low",
        catalyst="Nexletol/Nexlizet CLEAR outcomes label update; commercial acceleration",
        therapeutic_area="cardiometabolic", modality="small_molecule", stage="commercial",
        lead_asset="Nexletol (bempedoic acid), Nexlizet (bempedoic acid + ezetimibe)",
        market_cap_millions=500, cash_millions=150,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.52, financing_pressure_score=0.55,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="VRNA", company_id="verona_pharma", asset_id="a-vrna",
        company_name="Verona Pharma",
        indication="COPD (ensifentrine PDE3/PDE4 dual inhib; first new MOA in COPD ~20 yrs)",
        ranking_score=0.62, opportunity_score=0.58, conviction="medium-low",
        catalyst="Ohtuvayre (ensifentrine) FDA approved 2024; commercial launch COPD",
        therapeutic_area="cardiometabolic", modality="small_molecule", stage="commercial",
        lead_asset="Ohtuvayre (ensifentrine; inhaled PDE3/4 dual inhibitor)",
        market_cap_millions=3_000, cash_millions=550,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.65, strategic_scarcity_score=0.72,
        asset_quality_quick_score=0.65, financing_pressure_score=0.25,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="LPCN", company_id="lipocine", asset_id="a-lpcn",
        company_name="Lipocine",
        indication="NASH/MASH (LPCN 1144 oral bioavailable testosterone prodrug Phase 2)",
        ranking_score=0.32, opportunity_score=0.28, conviction="very-low",
        catalyst="LPCN 1144 Phase 2 MASH proof-of-concept data",
        therapeutic_area="cardiometabolic", modality="small_molecule", stage="phase_2",
        lead_asset="LPCN 1144 (oral testosterone undecanoate for MASH)",
        market_cap_millions=80, cash_millions=30,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.32, strategic_scarcity_score=0.38,
        asset_quality_quick_score=0.32, financing_pressure_score=0.75,
        data_confidence=DataConfidence.LOW,
    ),
]


# ===========================================================================
# Section F2 — Additional Hematology targets
# ===========================================================================

HEMATOLOGY_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="IMAB", company_id="i_mab", asset_id="a-imab",
        company_name="I-Mab",
        indication="Hematologic malignancies (lemzoparlimab anti-CD47; givastomig PD-1/CD47)",
        ranking_score=0.45, opportunity_score=0.40, conviction="low",
        catalyst="lemzoparlimab (CD47) Phase 2 AML/MDS; AbbVie partnership status",
        therapeutic_area="hematology", modality="biologic", stage="phase_2",
        lead_asset="lemzoparlimab (anti-CD47; AML/MDS), givastomig (PD-1xCD47)",
        market_cap_millions=350, cash_millions=150,
        target_type=TargetType.PLATFORM, ownership_status="partnered",
        mna_relevance_score=0.48, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.48, financing_pressure_score=0.58,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="RUBY", company_id="rubius_therapeutics", asset_id="a-ruby",
        company_name="Rubius Therapeutics (dissolved 2023 — PRECEDENT)",
        indication="PRECEDENT: RCT (red cell therapeutics) platform — PKU, solid tumors",
        ranking_score=0.0, opportunity_score=0.0, conviction="precedent",
        catalyst="PRECEDENT: dissolved 2023; technology assets auctioned; PKU RCT Phase 1",
        therapeutic_area="hematology", modality="cell_therapy", stage="other",
        lead_asset="RTX-240, RTX-134 (engineered red blood cell therapeutics)",
        market_cap_millions=0, cash_millions=0,
        target_type=TargetType.DISTRESSED, ownership_status="acquired",
        mna_relevance_score=0.0, strategic_scarcity_score=0.0,
        asset_quality_quick_score=0.0, financing_pressure_score=0.0,
        data_confidence=DataConfidence.LOW,
    ),

    WatchlistTarget(
        ticker="AGIO", company_id="agios_heme_addl", asset_id="a-agio-addl",
        company_name="Agios Pharmaceuticals (IDH + thalassemia pipeline note)",
        indication="Thalassemia (mitapivat PK activation commercial + SCD Phase 3 RISE UP)",
        ranking_score=0.65, opportunity_score=0.60, conviction="medium-low",
        catalyst="Pyrukynd (mitapivat) thalassemia approval; SCD Phase 3 RISE UP readout",
        therapeutic_area="hematology", modality="small_molecule", stage="commercial",
        lead_asset="Pyrukynd (mitapivat; PKR activator for PK deficiency/thalassemia/SCD)",
        market_cap_millions=2_500, cash_millions=700,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.68, strategic_scarcity_score=0.72,
        asset_quality_quick_score=0.68, financing_pressure_score=0.28,
        data_confidence=DataConfidence.MEDIUM,
    ),
]


# ===========================================================================
# Section G2 — Additional Ophthalmology targets
# ===========================================================================

OPHTHALMOLOGY_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="EYPT", company_id="eyepoint_pharma", asset_id="a-eypt",
        company_name="EyePoint Pharmaceuticals",
        indication="Wet AMD, diabetic retinopathy (EYP-1901 vorolanib sustained-release)",
        ranking_score=0.55, opportunity_score=0.50, conviction="medium-low",
        catalyst="EYP-1901 (intravitreal vorolanib insert) Phase 2 DAVIO-2 wet AMD data",
        therapeutic_area="ophthalmology", modality="small_molecule", stage="phase_2",
        lead_asset="EYP-1901 (tyrosine kinase inhibitor intravitreal insert, 6-month dosing)",
        market_cap_millions=600, cash_millions=200,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.55, strategic_scarcity_score=0.62,
        asset_quality_quick_score=0.55, financing_pressure_score=0.45,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="RXRX2", company_id="regenxbio_ophtho", asset_id="a-rgnx-retina",
        company_name="REGENXBIO (Retina/AAV gene therapy — see rare_disease for full entry)",
        indication="Wet AMD (RGX-314 AAV anti-VEGF subretinal + suprachoroidal)",
        ranking_score=0.60, opportunity_score=0.55, conviction="medium-low",
        catalyst="RGX-314 ALTITUDE suprachoroidal Phase 2/3 wet AMD; ABBV-RGX-314 AbbVie deal",
        therapeutic_area="ophthalmology", modality="gene_therapy", stage="phase_3",
        lead_asset="RGX-314 (AAV8 anti-VEGF fab for wet AMD)",
        market_cap_millions=900, cash_millions=350,
        target_type=TargetType.SINGLE_ASSET, ownership_status="partnered",
        mna_relevance_score=0.60, strategic_scarcity_score=0.68,
        asset_quality_quick_score=0.60, financing_pressure_score=0.38,
        data_confidence=DataConfidence.MEDIUM,
    ),
]


# ===========================================================================
# Section H2 — Additional Infectious Disease targets
# ===========================================================================

INFECTIOUS_DISEASE_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="SIGA", company_id="siga_technologies", asset_id="a-siga",
        company_name="SIGA Technologies",
        indication="Smallpox/mpox (TPOXX tecovirimat; US government stockpile contract)",
        ranking_score=0.40, opportunity_score=0.35, conviction="low",
        catalyst="TPOXX mpox expanded access + stockpile procurement; FDA data package",
        therapeutic_area="infectious_disease", modality="small_molecule", stage="commercial",
        lead_asset="TPOXX (tecovirimat; TPOXV/VARV orthopoxvirus antiviral)",
        market_cap_millions=600, cash_millions=150,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.38, strategic_scarcity_score=0.55,
        asset_quality_quick_score=0.45, financing_pressure_score=0.45,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="ATEA", company_id="atea_pharmaceuticals", asset_id="a-atea",
        company_name="Atea Pharmaceuticals",
        indication="HCV, COVID-19, dengue (nucleoside/nucleotide polymerase inhibitor)",
        ranking_score=0.38, opportunity_score=0.32, conviction="very-low",
        catalyst="bemnifosbuvir (AT-527) dengue Phase 2; COVID antiviral positioning",
        therapeutic_area="infectious_disease", modality="small_molecule", stage="phase_2",
        lead_asset="bemnifosbuvir (AT-527; RNA polymerase inhib) dengue/HCV",
        market_cap_millions=350, cash_millions=400,
        target_type=TargetType.SINGLE_ASSET, ownership_status="clean",
        mna_relevance_score=0.40, strategic_scarcity_score=0.48,
        asset_quality_quick_score=0.42, financing_pressure_score=0.35,
        data_confidence=DataConfidence.LOW,
    ),
]


# ===========================================================================
# Section I2 — Additional Platform / AI Drug Discovery targets
# ===========================================================================

PLATFORM_ADDL: list[WatchlistTarget] = [

    WatchlistTarget(
        ticker="ABCL", company_id="abcellera_biologics", asset_id="a-abcl",
        company_name="AbCellera Biologics",
        indication="Antibody discovery platform; partnered with >100 companies",
        ranking_score=0.55, opportunity_score=0.50, conviction="medium-low",
        catalyst="ABCL-167 (anti-VEGF) Phase 2; barnlanivimab COVID precedent royalties",
        therapeutic_area="platform", modality="monoclonal_antibody", stage="phase_2",
        lead_asset="AbCellera AI-antibody discovery platform + own pipeline",
        market_cap_millions=1_800, cash_millions=600,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.58, strategic_scarcity_score=0.72,
        asset_quality_quick_score=0.58, financing_pressure_score=0.35,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="BEAM2", company_id="beam_therapeutics_platform", asset_id="a-beam-platform",
        company_name="Beam Therapeutics (Platform note — see rare_disease for full entry)",
        indication="Base editing platform — oncology (BEAM-201 CAR-T) + rare disease",
        ranking_score=0.70, opportunity_score=0.65, conviction="medium",
        catalyst="BEAM-201 (CD7 CAR-T via base editing) Phase 1 T-ALL; BEAM-302 AAT",
        therapeutic_area="platform", modality="gene_editing", stage="phase_1",
        lead_asset="Base editing platform + BEAM-201 (allogeneic CAR-T) + BEAM-302 (AATD)",
        market_cap_millions=2_800, cash_millions=1_000,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.75, strategic_scarcity_score=0.85,
        asset_quality_quick_score=0.72, financing_pressure_score=0.28,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="VRTV", company_id="veracyte", asset_id="a-vrtv",
        company_name="Veracyte",
        indication="Thyroid, lung, prostate cancer genomic diagnostics (Afirma, Decipher)",
        ranking_score=0.52, opportunity_score=0.48, conviction="low",
        catalyst="Decipher Prostate integration; Prosigna commercial expansion; pipeline dx",
        therapeutic_area="platform", modality="diagnostics", stage="commercial",
        lead_asset="Afirma (thyroid), Decipher Prostate, Prosigna (breast cancer)",
        market_cap_millions=2_200, cash_millions=400,
        target_type=TargetType.COMMERCIAL_FRANCHISE, ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.60,
        asset_quality_quick_score=0.55, financing_pressure_score=0.30,
        data_confidence=DataConfidence.MEDIUM,
    ),

    WatchlistTarget(
        ticker="EXAI", company_id="exai_bio", asset_id="a-exai",
        company_name="Exai Bio",
        indication="cfRNA multi-cancer early detection (liquid biopsy platform)",
        ranking_score=0.48, opportunity_score=0.42, conviction="low",
        catalyst="Multi-cancer cfRNA validation study data; commercial partnership",
        therapeutic_area="platform", modality="diagnostics", stage="phase_2",
        lead_asset="cfRNA liquid biopsy platform (cell-free RNA for cancer detection)",
        market_cap_millions=500, cash_millions=200,
        target_type=TargetType.PLATFORM, ownership_status="clean",
        mna_relevance_score=0.50, strategic_scarcity_score=0.65,
        asset_quality_quick_score=0.50, financing_pressure_score=0.45,
        data_confidence=DataConfidence.LOW,
    ),
]


# ===========================================================================
# Combined additional targets
# ===========================================================================

ALL_ADDL_TARGETS: list[WatchlistTarget] = (
    ONCOLOGY_ADDL
    + IMMUNOLOGY_ADDL
    + RARE_DISEASE_ADDL
    + CNS_ADDL
    + CARDIOMETABOLIC_ADDL
    + HEMATOLOGY_ADDL
    + OPHTHALMOLOGY_ADDL
    + INFECTIOUS_DISEASE_ADDL
    + PLATFORM_ADDL
)

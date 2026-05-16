"""Specialty pharma / large-biotech acquirer registry — missing 1B companies.

Eight large-cap companies from Section 1B of the institutional M&A spec that
were not included in acquirer_registry.py Phase 2a/2b:

  BioNTech, Ionis, Incyte, Neurocrine, Sobi, Grifols, argenx, Genmab

Financial figures from Q1 2026 earnings / public filings.
"""
from __future__ import annotations

from bve.entities.acquirer import (
    AcquirerProfile, BDStyle, DealCapacity, ModalityCapabilities,
    BDHistoryDetailed, AcquisitionRecord, LicenseRecord,
    LOECliff,
)

SPECIALTY_ACQUIRERS: list[AcquirerProfile] = [

    # -----------------------------------------------------------------------
    # BioNTech — oncology mRNA + TCE platform; Pfizer partnership for COVID
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="biontech", name="BioNTech", ticker="BNTX",
        country="Germany",
        cash_millions=17_500, annual_fcf_millions=2_000, market_cap_millions=28_000,
        strategic_areas=["oncology", "mrna_vaccines", "cell_therapy", "immunotherapy"],
        preferred_modalities=["mrna", "bispecific", "cell_therapy", "antibody"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 1", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=10_000,
            max_comfortable_deal_size_millions=5_000,
            debt_capacity_millions=3_000,
        ),
        ta_priorities={"oncology": 1.0, "mrna_vaccines": 0.85, "cell_therapy": 0.75,
                       "immunotherapy": 0.80},
        modality_capabilities=ModalityCapabilities(
            mrna=0.98, bispecific=0.80, cell_therapy=0.70, monoclonal_antibody=0.75,
        ),
        bd_history_detailed=BDHistoryDetailed(licenses=[
            LicenseRecord(partner="Pfizer", direction="out-license",
                          therapeutic_area="vaccine", year=2020),
            LicenseRecord(partner="Genentech/Roche", direction="in-license",
                          therapeutic_area="oncology", year=2016),
        ]),
        notes=(
            "~€17B cash post-COVID windfall; pivoting to oncology mRNA pipeline (BNT111-323). "
            "BNT323 (ADC), BNT222 (mRNA TCE bispecific), BNT311 (PD-L1). "
            "Acquires oncology assets < Phase 2 with mRNA/TCE fit; prefers platform deals. "
            "Data confidence: medium (0.70)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Ionis Pharmaceuticals — ASO/oligonucleotide platform; >35 partnered drugs
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="ionis", name="Ionis Pharmaceuticals", ticker="IONS",
        country="United States",
        cash_millions=2_800, annual_fcf_millions=800, market_cap_millions=9_500,
        strategic_areas=["neurodegeneration", "cardiovascular", "rare_disease",
                         "cardiometabolic"],
        preferred_modalities=["antisense_oligonucleotide", "rna_interference"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=3_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_800,
            max_comfortable_deal_size_millions=3_000,
            debt_capacity_millions=1_500,
        ),
        ta_priorities={"neurodegeneration": 1.0, "cardiovascular": 0.90,
                       "rare_disease": 0.85, "cardiometabolic": 0.80},
        modality_capabilities=ModalityCapabilities(
            oligonucleotide=0.99, rna_interference=0.80, small_molecule=0.30,
        ),
        bd_history_detailed=BDHistoryDetailed(licenses=[
            LicenseRecord(partner="AstraZeneca", direction="out-license",
                          therapeutic_area="cardiovascular", year=2021),
            LicenseRecord(partner="Biogen", direction="co-develop",
                          therapeutic_area="neurodegeneration", year=2018),
        ], acquisitions=[
            AcquisitionRecord(target="Akcea Therapeutics", year=2020,
                              therapeutic_area="cardiovascular", deal_size_millions=500),
        ]),
        notes=(
            "ASO pioneer; 8+ approved drugs (nusinersen, tofersen, eplontersen, etc.). "
            "Royalty streams from AZ (eplontersen), Biogen. Prefers acquiring ASO/RNAi "
            "platform assets or early-stage RNA programs. Not a large M&A buyer by history. "
            "Data confidence: high (0.85)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Incyte Corporation — JAK franchise (ruxolitinib) + oncology/immuno
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="incyte", name="Incyte Corporation", ticker="INCY",
        country="United States",
        cash_millions=3_200, annual_fcf_millions=900, market_cap_millions=16_000,
        strategic_areas=["oncology", "immunology", "gvhd", "dermatology"],
        preferred_modalities=["small_molecule", "biologic", "antibody"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=4_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_200,
            max_comfortable_deal_size_millions=4_000,
            debt_capacity_millions=2_000,
        ),
        ta_priorities={"oncology": 1.0, "immunology": 0.85, "gvhd": 0.90,
                       "dermatology": 0.75},
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.92, monoclonal_antibody=0.70, bispecific=0.60,
        ),
        bd_history_detailed=BDHistoryDetailed(licenses=[
            LicenseRecord(partner="Novartis", direction="out-license",
                          therapeutic_area="hematology", year=2009),
            LicenseRecord(partner="Syndax Pharmaceuticals", direction="in-license",
                          therapeutic_area="oncology", year=2023),
        ], acquisitions=[
            AcquisitionRecord(target="Escient Pharmaceuticals", year=2023,
                              therapeutic_area="immunology", deal_size_millions=750),
            AcquisitionRecord(target="Villaris Therapeutics", year=2023,
                              therapeutic_area="dermatology", deal_size_millions=70),
        ]),
        loe_cliff=LOECliff(
            product_name="Jakafi (ruxolitinib)", indication="myelofibrosis/PV/GvHD",
            peak_sales_millions=2_800, loe_year=2028,
            revenue_at_risk_millions=1_800, replacement_urgency="high",
        ),
        notes=(
            "Jakafi (ruxolitinib) LOE ~2028 drives urgency. Niktimvo (axatilimab-csfr) "
            "for cGVHD approved 2024. Zynyz (retifanlimab PD-1) oncology. "
            "Actively acquires Phase 2 oncology/immunology assets. "
            "Data confidence: high (0.88)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Neurocrine Biosciences — CNS + neuroendocrinology franchise
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="neurocrine", name="Neurocrine Biosciences", ticker="NBIX",
        country="United States",
        cash_millions=2_200, annual_fcf_millions=900, market_cap_millions=15_000,
        strategic_areas=["cns", "neuroendocrinology", "psychiatry", "movement_disorders"],
        preferred_modalities=["small_molecule", "peptide"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=3_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=2_200,
            max_comfortable_deal_size_millions=3_000,
            debt_capacity_millions=1_500,
        ),
        ta_priorities={"movement_disorders": 1.0, "psychiatry": 0.90,
                       "neuroendocrinology": 0.85, "cns": 0.80},
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.95, peptide=0.70, gene_therapy=0.40,
        ),
        bd_history_detailed=BDHistoryDetailed(licenses=[
            LicenseRecord(partner="AbbVie", direction="co-promote",
                          therapeutic_area="endocrinology", year=2010),
            LicenseRecord(partner="Xenon Pharmaceuticals", direction="in-license",
                          therapeutic_area="cns", year=2023),
        ], acquisitions=[
            AcquisitionRecord(target="Xenon Pharmaceuticals (license)", year=2023,
                              therapeutic_area="epilepsy", deal_size_millions=1_700),
        ]),
        notes=(
            "Ingrezza (valbenazine) tardive dyskinesia commercial ($2B+ revenue). "
            "Crinecerfont (CAH) approved 2024. Gene therapy partnership with AbbVie "
            "for NBIb-1817 (AADC deficiency). Prefers CNS/neuroendocrine Phase 2+ assets. "
            "Data confidence: high (0.85)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Sobi (Swedish Orphan Biovitrum) — rare disease, hematology, immunology
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="sobi", name="Swedish Orphan Biovitrum (Sobi)", ticker="SOBI.ST",
        country="Sweden",
        cash_millions=700, annual_fcf_millions=400, market_cap_millions=6_000,
        strategic_areas=["rare_disease", "hematology", "immunology", "neuroscience"],
        preferred_modalities=["biologic", "enzyme_replacement", "small_molecule"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 2", max_deal_size_millions=2_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=700,
            max_comfortable_deal_size_millions=2_000,
            debt_capacity_millions=1_500,
        ),
        ta_priorities={"rare_hematology": 1.0, "rare_immunology": 0.90,
                       "rare_neuroscience": 0.80},
        modality_capabilities=ModalityCapabilities(
            biologic=0.85, enzyme_replacement=0.80, small_molecule=0.65,
        ),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Dova Pharmaceuticals", year=2021,
                              therapeutic_area="hematology", deal_size_millions=915),
            AcquisitionRecord(target="Apellis Pharmaceuticals (EU rights)", year=2021,
                              therapeutic_area="complement", deal_size_millions=250),
        ]),
        notes=(
            "Eplontersen (AZ partnership), Kineret (IL-1Ra), Alprolix/Elocta (hemophilia). "
            "EU-centric rare disease / hematology acquirer. Preferred targets: "
            "European commercial rights or Phase 2+ rare hematology/immunology. "
            "Data confidence: medium (0.70)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Grifols — plasma-derived therapies; alpha-1 antitrypsin, IG products
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="grifols", name="Grifols", ticker="GRFS",
        country="Spain",
        cash_millions=400, annual_fcf_millions=300, market_cap_millions=4_500,
        strategic_areas=["plasma_derived", "rare_disease", "immunology"],
        preferred_modalities=["plasma_derived_protein", "biologic"],
        bd_style=BDStyle.BOLT_ON, preferred_phase="Phase 3", max_deal_size_millions=1_500,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=400,
            max_comfortable_deal_size_millions=1_500,
            debt_capacity_millions=1_000,
        ),
        ta_priorities={"plasma_derived": 1.0, "rare_immunology": 0.85,
                       "neurology": 0.70},
        modality_capabilities=ModalityCapabilities(
            biologic=0.75, plasma_derived=0.98, small_molecule=0.30,
        ),
        bd_history_detailed=BDHistoryDetailed(acquisitions=[
            AcquisitionRecord(target="Biotest AG", year=2022,
                              therapeutic_area="immunology", deal_size_millions=1_100),
            AcquisitionRecord(target="GigaGen", year=2020,
                              therapeutic_area="immunology", deal_size_millions=1_400),
        ]),
        notes=(
            "World's second-largest plasma products company. High leverage (~$9B debt). "
            "Albumin, IVIG, SCIG, alpha-1 antitrypsin (Prolastin). "
            "M&A appetite constrained by debt; focused on plasma collection expansion "
            "and bolt-on specialty biologics. Data confidence: medium (0.65)."
        ),
    ),

    # -----------------------------------------------------------------------
    # argenx — FcRn antibody platform; efgartigimod + ARGX-117/ARGX-119
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="argenx", name="argenx", ticker="ARGX",
        country="Netherlands",
        cash_millions=5_500, annual_fcf_millions=1_200, market_cap_millions=30_000,
        strategic_areas=["immunology", "rare_autoimmune", "neuromuscular", "hematology"],
        preferred_modalities=["monoclonal_antibody", "bispecific"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 2", max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=5_500,
            max_comfortable_deal_size_millions=5_000,
            debt_capacity_millions=2_000,
        ),
        ta_priorities={"rare_autoimmune": 1.0, "neuromuscular": 0.90,
                       "hematology": 0.85, "immunology": 0.80},
        modality_capabilities=ModalityCapabilities(
            monoclonal_antibody=0.95, bispecific=0.80, antibody_drug_conjugate=0.50,
        ),
        bd_history_detailed=BDHistoryDetailed(licenses=[
            LicenseRecord(partner="AbbVie", direction="out-license",
                          therapeutic_area="immunology", year=2022),
            LicenseRecord(partner="Zymeworks", direction="in-license",
                          therapeutic_area="oncology", year=2021),
        ]),
        notes=(
            "Vyvgart/efgartigimod (FcRn; MG, ITP, CIDP, PV) — $3B+ revenue run rate. "
            "ARGX-117 (C2 complement) and ARGX-119 (MuSK antibody) in Phase 2/3. "
            "Cash-rich; prefers rare autoimmune Phase 2+ assets with FcRn/IgG biology. "
            "Data confidence: high (0.85)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Genmab — antibody engineering platform; DuoBody bispecific technology
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="genmab", name="Genmab", ticker="GMAB",
        country="Denmark",
        cash_millions=4_500, annual_fcf_millions=1_500, market_cap_millions=18_000,
        strategic_areas=["oncology", "hematology", "immunology"],
        preferred_modalities=["monoclonal_antibody", "bispecific", "antibody_drug_conjugate"],
        bd_style=BDStyle.PLATFORM, preferred_phase="Phase 1", max_deal_size_millions=4_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=4_500,
            max_comfortable_deal_size_millions=4_000,
            debt_capacity_millions=2_000,
        ),
        ta_priorities={"hematology": 1.0, "oncology": 0.95, "immunology": 0.75},
        modality_capabilities=ModalityCapabilities(
            monoclonal_antibody=0.99, bispecific=0.95, antibody_drug_conjugate=0.80,
        ),
        bd_history_detailed=BDHistoryDetailed(licenses=[
            LicenseRecord(partner="AbbVie", direction="out-license",
                          therapeutic_area="hematology", year=2020),
            LicenseRecord(partner="Janssen/J&J", direction="co-develop",
                          therapeutic_area="hematology", year=2012),
        ], acquisitions=[
            AcquisitionRecord(target="ProfoundBio", year=2024,
                              therapeutic_area="oncology", deal_size_millions=1_800,
                              modality="antibody_drug_conjugate"),
        ]),
        notes=(
            "DuoBody® bispecific platform licenses to >40 partners. "
            "Approved: daratumumab (Darzalex w/ J&J), ofatumumab (Kesimpta), "
            "tisotumab vedotin (Tivdak ADC). EPKINLY (epcoritamab) bispecific. "
            "Strong cash; prefers early antibody/bispecific/ADC platform acquisitions. "
            "Data confidence: high (0.90)."
        ),
    ),

]


SPECIALTY_ACQUIRERS_BY_ID: dict[str, AcquirerProfile] = {
    a.company_id: a for a in SPECIALTY_ACQUIRERS
}

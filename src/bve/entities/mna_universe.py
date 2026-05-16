"""Institutional-Grade Expanded Pharma M&A Universe — v2.

Three linked datasets (not a flat watchlist):
  1. COMPANY_MASTER  — all companies tagged by class (acquirer/hybrid/target/asia/tools/precedent)
  2. ASSET_MASTER    — target profiles with rights, IP, CMC, catalyst, seller willingness
  3. PAIR_TABLE      — buyer × target records with full institutional PairScore

Design rules
------------
- Not every company is a target. CompanyClass tags role explicitly.
- Rights/economics are a normalized table, NOT free-text notes.
- Pair records are the unit of M&A analysis; watchlist rank alone is insufficient.
- Precedent entries (Akero → Novo) stay in the model for calibration.
- Asia innovators and Tools/CDMO companies are lightweight nodes for scoring
  CMC bottlenecks, buyer capability, and asset sourcing — not full targets.

Data confidence notes
---------------------
All figures sourced from public filings, earnings releases, and press releases
as of May 2026. Refresh against current 10-Q/annual report before use in
live deal analysis. Fields not confirmed from public sources are left None
rather than estimated.

Usage
-----
    from bve.entities.mna_universe import (
        NEW_ACQUIRERS, HYBRID_UNIVERSE, TARGET_UNIVERSE_V2,
        PRECEDENT_REGISTRY, ASIA_REGISTRY, TOOLS_CDMO_REGISTRY,
        PAIR_TABLE, get_pairs_for_target, get_pairs_for_acquirer,
        FULL_ACQUIRER_UNIVERSE,
    )
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bve.entities.acquirer import (
    AcquirerProfile, BDStyle, DealCapacity, ModalityCapabilities,
    CMCCapability,
    BDHistoryDetailed, AcquisitionRecord, LicenseRecord,
    AcquirerRelationships, AntitrustProfile, LOECliff, PipelineGap,
    ACQUIRER_UNIVERSE,
)
from bve.entities.target import (
    AcquirableTarget, CompanyClass, CompanyIdentity, CompanyType, TargetType,
    RightsAndEconomics,
    ClinicalAssetDetail, RegulatoryProfile, RegulatoryDesignations,
    CMCProfile, ManufacturingComplexity,
    FinancingProfile, SellerWillingness, SellerStrategy,
    IPExclusivity, DataQuality, DataConfidence,
)
from bve.entities.pair_score import AcquirerTargetPair, PairScore, PairOutputs
from bve.entities.acquirer_registry import (
    ALL_NEW_ACQUIRERS,
    MEGA_CAP_ACQUIRERS_V2,
    LARGE_BIOTECH_ACQUIRERS,
    CHINA_PHARMA_ACQUIRERS,
    SPECIALTY_ACQUIRERS,
)
from bve.entities.target_registry import (
    TARGET_UNIVERSE_V3,
    ALL_TARGETS,
    TARGET_BY_TICKER,
    TARGET_BY_ASSET_ID as TARGET_BY_ASSET_ID_V3,
    STRATEGIC_BIOTECH_HYBRIDS,
    category_summary,
    top_mna_targets,
)


# ===========================================================================
# Part 1 — NEW ACQUIRERS (7 institutional-grade buyers not in v1)
# ===========================================================================

NEW_ACQUIRERS: list[AcquirerProfile] = [

    # -----------------------------------------------------------------------
    # Johnson & Johnson — global mega-cap; immunology + oncology + medtech
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="jnj",
        name="Johnson & Johnson",
        ticker="JNJ",
        country="United States",
        cash_millions=24_000,
        debt_millions=30_000,
        annual_fcf_millions=18_000,
        market_cap_millions=380_000,
        net_debt_millions=6_000,
        ebitda_millions=22_000,
        credit_rating="Aaa/AAA",
        strategic_areas=["immunology", "oncology", "neuroscience", "cardiovascular"],
        preferred_modalities=["biologic", "small_molecule", "bispecific", "antibody_drug_conjugate"],
        bd_style=BDStyle.BLOCKBUSTER,
        preferred_phase="Phase 3",
        max_deal_size_millions=25_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=24_000,
            estimated_debt_capacity_millions=30_000,
            max_comfortable_deal_size_millions=25_000,
        ),
        ta_priorities={
            "immunology": 1.0, "oncology": 0.95, "neuroscience": 0.60,
            "rare_disease": 0.70, "cardiovascular": 0.50,
        },
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.95, monoclonal_antibody=0.95, bispecific=0.80,
            antibody_drug_conjugate=0.75, cell_therapy=0.60,
        ),
        cmc_capability=CMCCapability(
            biologics=0.95, small_molecule=0.95, sterile_fill_finish=0.90,
            adc=0.70, supply_chain_strength=0.95,
        ),
        bd_history_detailed=BDHistoryDetailed(
            acquisitions=[
                AcquisitionRecord(
                    target="Momenta Pharmaceuticals", year=2020,
                    deal_value_millions=6_500, therapeutic_area="immunology",
                    modality="biologic", stage="Phase 3",
                    notes="Added nipocalimab (FcRn); leads to Imaavy launch",
                ),
                AcquisitionRecord(
                    target="Halda Therapeutics", year=2025,
                    therapeutic_area="oncology", modality="small_molecule",
                    stage="Phase 1", notes="Precision oncology; deepens targeted degradation",
                ),
            ],
            preferred_deal_size="$3B–$25B",
            preferred_stage="Phase 2 / Phase 3",
            typical_premium_range="40–65%",
        ),
        antitrust=AntitrustProfile(
            ftc_risk="medium", eu_commission_risk="medium",
            divestiture_likelihood="low",
        ),
        notes=(
            "Top-tier immunology buyer post-Momenta. Imaavy approved; deepening "
            "FcRn franchise. Halda deal signals precision-oncology appetite. "
            "Best fits: late-stage immunology (autoimmune, IgG-mediated), oncology platforms. "
            "Data confidence: high (0.85)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Sanofi — immunology + vaccines; top global BD appetite
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="sanofi",
        name="Sanofi",
        ticker="SNY",
        country="France",
        cash_millions=10_500,
        debt_millions=15_000,
        annual_fcf_millions=9_000,
        market_cap_millions=130_000,
        ebitda_millions=12_000,
        credit_rating="A2/A",
        strategic_areas=["immunology", "vaccines", "rare_disease", "oncology"],
        preferred_modalities=["biologic", "small_molecule", "monoclonal_antibody", "mrna"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        max_deal_size_millions=20_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=10_500,
            max_comfortable_deal_size_millions=20_000,
        ),
        ta_priorities={
            "immunology": 1.0, "vaccines": 0.95, "rare_disease": 0.80,
            "oncology": 0.55, "inflammation": 0.90,
        },
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.85, monoclonal_antibody=0.90, vaccine=0.95, mrna=0.75,
        ),
        cmc_capability=CMCCapability(
            biologics=0.90, small_molecule=0.85, sterile_fill_finish=0.90,
            mrna_lnp=0.70, supply_chain_strength=0.90,
        ),
        bd_history_detailed=BDHistoryDetailed(
            acquisitions=[
                AcquisitionRecord(
                    target="Dren Bio (immunology unit)", year=2025,
                    therapeutic_area="immunology", modality="biologic",
                    notes="Deepens innate immune / FcγR pathway",
                ),
                AcquisitionRecord(
                    target="Dynavax Technologies", year=2025,
                    therapeutic_area="vaccines", modality="vaccine",
                    notes="TLR9 adjuvant platform; adult vaccines franchise",
                ),
            ],
            preferred_deal_size="$2B–$20B",
            preferred_stage="Phase 2",
            typical_premium_range="40–70%",
        ),
        notes=(
            "Active deployer: Dren Bio immunology + Dynavax vaccines both 2025. "
            "Dupixent LOE pressure mid-2030s motivates platform diversification now. "
            "Best fits: late-stage immunology (atopic, eosinophilic, autoimmune), "
            "adult vaccines, specialty inflammation. Data confidence: high (0.82)."
        ),
    ),

    # -----------------------------------------------------------------------
    # GSK — respiratory + immunology + vaccines + China-origin assets
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="gsk",
        name="GSK",
        ticker="GSK",
        country="United Kingdom",
        cash_millions=9_200,
        debt_millions=16_000,
        annual_fcf_millions=7_500,
        market_cap_millions=82_000,
        ebitda_millions=9_000,
        credit_rating="Baa1/BBB+",
        strategic_areas=["respiratory", "immunology", "vaccines", "oncology", "infectious_disease"],
        preferred_modalities=["biologic", "small_molecule", "vaccine"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
        max_deal_size_millions=15_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=9_200,
            max_comfortable_deal_size_millions=15_000,
        ),
        ta_priorities={
            "respiratory": 1.0, "vaccines": 0.95, "immunology": 0.85,
            "oncology": 0.70, "infectious_disease": 0.80,
        },
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.90, monoclonal_antibody=0.85, vaccine=0.95,
        ),
        cmc_capability=CMCCapability(
            biologics=0.85, small_molecule=0.90, sterile_fill_finish=0.90,
            supply_chain_strength=0.85,
        ),
        bd_history_detailed=BDHistoryDetailed(
            licenses=[
                LicenseRecord(
                    partner="Sino Biopharm", year=2025,
                    therapeutic_area="respiratory/immunology/oncology",
                    geography="ex-China",
                    notes="bepirovirsen commercialization collaboration",
                ),
                LicenseRecord(
                    partner="Hengrui", year=2025,
                    therapeutic_area="respiratory/immunology/oncology",
                    geography="ex-China",
                    notes="Broad multi-program China-sourced licensing package",
                ),
            ],
            preferred_deal_size="$1B–$10B",
            preferred_stage="Phase 2–3",
        ),
        notes=(
            "Active acquirer of China-origin assets (Hengrui, Sino Biopharm 2025). "
            "Shingrix and Arexvy established vaccine commercial franchise. "
            "Best fits: respiratory/inflammation, vaccines, externally-sourced Asia assets. "
            "Data confidence: medium-high (0.74)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Novo Nordisk — cardiometabolic + obesity super-acquirer
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="novo_nordisk",
        name="Novo Nordisk",
        ticker="NVO",
        country="Denmark",
        cash_millions=8_000,
        debt_millions=5_000,
        annual_fcf_millions=16_000,
        market_cap_millions=320_000,
        ebitda_millions=20_000,
        credit_rating="Aa3/AA-",
        strategic_areas=["obesity", "diabetes", "cardiometabolic", "mash", "rare_disease"],
        preferred_modalities=["biologic", "small_molecule", "peptide", "gene_therapy"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        max_deal_size_millions=15_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=8_000,
            estimated_debt_capacity_millions=20_000,
            max_comfortable_deal_size_millions=15_000,
        ),
        ta_priorities={
            "obesity": 1.0, "diabetes": 0.95, "cardiometabolic": 0.90,
            "mash": 0.85, "rare_disease": 0.60,
        },
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.85, monoclonal_antibody=0.80, peptide=0.95,
            gene_therapy=0.40,
        ),
        cmc_capability=CMCCapability(
            biologics=0.90, small_molecule=0.85, sterile_fill_finish=0.90,
            peptides=0.95, supply_chain_strength=0.90,
        ),
        bd_history_detailed=BDHistoryDetailed(
            acquisitions=[
                AcquisitionRecord(
                    target="Akero Therapeutics", year=2025,
                    deal_value_millions=5_200,
                    therapeutic_area="mash", modality="biologic",
                    stage="Phase 3",
                    notes="Secures efruxifermin; MASH franchise anchor",
                ),
            ],
            preferred_deal_size="$2B–$15B",
            preferred_stage="Phase 2–3",
            typical_premium_range="50–80%",
        ),
        loe_cliffs=[
            LOECliff(
                product_name="Ozempic/Wegovy", indication="GLP-1 franchise",
                peak_sales_millions=35_000, loe_year=2033,
                revenue_at_risk_millions=20_000, replacement_urgency="high",
            ),
        ],
        notes=(
            "Cardiometabolic super-acquirer post-Akero. Ozempic/Wegovy franchise dominance "
            "funds major external deals but also raises antitrust attention in obesity space. "
            "Best fits: obesity, MASH, cardiometabolic, diabetes adjacencies. "
            "Out of lane: oncology, immunology, CNS. Data confidence: high (0.84)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Takeda — rare disease + GI/inflammation + neuroscience + oncology
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="takeda",
        name="Takeda Pharmaceutical",
        ticker="TAK",
        country="Japan",
        cash_millions=6_500,
        debt_millions=30_000,
        annual_fcf_millions=5_000,
        market_cap_millions=48_000,
        net_debt_millions=23_500,
        ebitda_millions=8_000,
        credit_rating="Baa2/BBB",
        strategic_areas=["rare_disease", "gastrointestinal", "neuroscience", "oncology", "plasma_derived"],
        preferred_modalities=["biologic", "small_molecule", "plasma_derived"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
        max_deal_size_millions=12_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=6_500,
            max_comfortable_deal_size_millions=10_000,
            leverage_limit_net_debt_ebitda=3.5,
            rating_sensitivity="deal >$8B risks Baa2 downgrade",
        ),
        ta_priorities={
            "rare_disease": 1.0, "gastrointestinal": 0.90,
            "neuroscience": 0.80, "oncology": 0.75,
            "hematology": 0.70, "plasma_derived": 0.85,
        },
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.85, monoclonal_antibody=0.80,
        ),
        cmc_capability=CMCCapability(
            biologics=0.80, small_molecule=0.85, supply_chain_strength=0.80,
        ),
        pipeline_gaps=[
            PipelineGap(
                therapeutic_area="oncology", priority="high",
                rationale="Thin Phase 3 oncology pipeline post-Millennium integration",
                stage_needed="Phase 2-3",
            ),
            PipelineGap(
                therapeutic_area="rare_disease", priority="high",
                rationale="Shire acquisition integrated; need next rare-disease anchor",
                stage_needed="Phase 2",
            ),
        ],
        notes=(
            "Levered post-Shire/Ariad; active restructuring limits deal size. "
            "Focus: rare disease, GI/inflammation, hematology, plasma, specialty neuro. "
            "Less natural for primary-care deals or high-CMC modalities. "
            "Best fits: rare disease, GI, AML/MDS, plasma-derived. Data confidence: medium (0.65)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Daiichi Sankyo — ADC-focused oncology acquirer / partner
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="daiichi_sankyo",
        name="Daiichi Sankyo",
        ticker="DSNKY",
        country="Japan",
        cash_millions=8_000,
        debt_millions=4_000,
        annual_fcf_millions=3_500,
        market_cap_millions=70_000,
        ebitda_millions=5_000,
        strategic_areas=["oncology", "hematology"],
        preferred_modalities=["antibody_drug_conjugate", "biologic", "bispecific"],
        bd_style=BDStyle.PLATFORM,
        preferred_phase="Phase 2",
        max_deal_size_millions=10_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=8_000,
            max_comfortable_deal_size_millions=10_000,
        ),
        ta_priorities={
            "oncology": 1.0, "hematology": 0.90,
        },
        modality_capabilities=ModalityCapabilities(
            monoclonal_antibody=0.90, antibody_drug_conjugate=1.0,
            bispecific=0.75, small_molecule=0.65,
        ),
        cmc_capability=CMCCapability(
            biologics=0.90, adc=1.0, supply_chain_strength=0.85,
        ),
        relationships=AcquirerRelationships(
            existing_partnerships=["Merck & Co (DXd ADC multi-program collaboration)"],
        ),
        notes=(
            "ADC platform leader via DXd portfolio (trastuzumab deruxtecan, etc.). "
            "Merck collaboration de-risks but also constrains oncology partnership space. "
            "Best fits: oncology assets with ADC compatibility, NSCLC/breast/gastric targets. "
            "Less relevant outside oncology. Data confidence: medium-high (0.72)."
        ),
    ),

    # -----------------------------------------------------------------------
    # UCB — specialty neurology + immunology; growing acquisitive posture
    # -----------------------------------------------------------------------
    AcquirerProfile(
        company_id="ucb",
        name="UCB",
        ticker="UCB",
        country="Belgium",
        cash_millions=3_500,
        debt_millions=7_000,
        annual_fcf_millions=2_500,
        market_cap_millions=25_000,
        ebitda_millions=3_000,
        credit_rating="Baa3/BBB-",
        strategic_areas=["neurology", "immunology", "oncology"],
        preferred_modalities=["biologic", "small_molecule", "monoclonal_antibody"],
        bd_style=BDStyle.BOLT_ON,
        preferred_phase="Phase 2",
        max_deal_size_millions=5_000,
        deal_capacity=DealCapacity(
            cash_available_for_deals_millions=3_500,
            max_comfortable_deal_size_millions=5_000,
        ),
        ta_priorities={
            "neurology": 1.0, "immunology": 0.90, "rare_disease": 0.75,
            "oncology": 0.40,
        },
        modality_capabilities=ModalityCapabilities(
            small_molecule=0.85, monoclonal_antibody=0.90, bispecific=0.60,
        ),
        cmc_capability=CMCCapability(
            biologics=0.80, small_molecule=0.85, supply_chain_strength=0.75,
        ),
        bd_history_detailed=BDHistoryDetailed(
            acquisitions=[
                AcquisitionRecord(
                    target="Candid Therapeutics", year=2026,
                    deal_value_millions=2_900, therapeutic_area="immunology",
                    modality="biologic", stage="Phase 2",
                ),
            ],
        ),
        notes=(
            "Growing acquirer: Candid acquisition May 2026 ($2.9B cash). "
            "BIMZELX, FINTEPLA, RYSTIGGO, ZILBRYSQ commercial launches drive BD funding. "
            "Best fits: specialty neurology, targeted immunology, rare CNS/neuro. "
            "Deal size constrained: $1–5B range. Data confidence: medium (0.68)."
        ),
    ),
]


# ===========================================================================
# Part 2 — HYBRID COMPANIES (standalone commercial / peer consolidators)
# ===========================================================================

@dataclass
class HybridCompany:
    """A company that can be a target in the right scenario but has standalone momentum.

    Default posture: standalone commercial or platform owner.
    Should NOT be modeled as 'easy takeout' — sale_urgency is low.
    """
    company_id: str
    name: str
    ticker: str
    country: str
    market_cap_millions: float
    cash_millions: float
    therapeutic_areas: list[str]
    modalities: list[str]
    company_class: str = "hybrid"
    sale_urgency: str = "low"       # low | medium | high
    standalone_thesis: str = ""
    recent_bd_behavior: str = ""    # acquiring / partnering / independent
    change_of_control_risk: str = "low"
    notes: str = ""


HYBRID_UNIVERSE: list[HybridCompany] = [

    HybridCompany(
        company_id="argenx",
        name="argenx",
        ticker="ARGX",
        country="Netherlands",
        market_cap_millions=28_000,
        cash_millions=5_000,
        therapeutic_areas=["immunology", "neuromuscular"],
        modalities=["monoclonal_antibody"],
        sale_urgency="low",
        standalone_thesis=(
            "VYVGART commercial scale (19,000+ patients globally, gMG + CIDP). "
            "Active lifecycle management. FcRn platform with disclosed COC provisions."
        ),
        recent_bd_behavior="independent commercial build; licensing collaborations",
        change_of_control_risk="low",
        notes=(
            "High standalone value; FcRn platform with disclosed anti-takeover provisions. "
            "Not a forced seller. Peer consolidator or eventual mega-cap acquisition target "
            "at substantial premium ($40B+ range). Institutional model: hybrid."
        ),
    ),

    HybridCompany(
        company_id="genmab",
        name="Genmab",
        ticker="GMAB",
        country="Denmark",
        market_cap_millions=18_000,
        cash_millions=4_000,
        therapeutic_areas=["oncology"],
        modalities=["monoclonal_antibody", "bispecific"],
        sale_urgency="low",
        standalone_thesis=(
            "Building proprietary oncology portfolio (petosemtamab, rinatabart sesutecan). "
            "Acquired Merus; stopped acasunlimab. Capital allocation toward owned programs."
        ),
        recent_bd_behavior="acquiring (Merus); culling partners",
        change_of_control_risk="low",
        notes=(
            "Transitioning from pure-collaboration model to proprietary oncology. "
            "Not a simple sale candidate. Relevant as peer buyer or very-long-duration target."
        ),
    ),

    HybridCompany(
        company_id="biontech",
        name="BioNTech",
        ticker="BNTX",
        country="Germany",
        market_cap_millions=32_000,
        cash_millions=16_800,
        therapeutic_areas=["oncology", "immunology", "infectious_disease"],
        modalities=["mrna", "bispecific", "antibody_drug_conjugate"],
        sale_urgency="low",
        standalone_thesis=(
            "€16.8B cash. Growing late-stage oncology pipeline: mRNA cancer immunotherapy, "
            "ADCs, immunomodulators. Using M&A/partnerships to build oncology platform."
        ),
        recent_bd_behavior="acquiring; BMS collaboration; CureVac",
        change_of_control_risk="very_low",
        notes=(
            "Cash-rich oncology platform; also an acquirer itself. "
            "Not a near-term acquisition target. Model as cash-rich platform and "
            "occasional buyer of oncology / mRNA-adjacent assets."
        ),
    ),

    HybridCompany(
        company_id="ionis",
        name="Ionis Pharmaceuticals",
        ticker="IONS",
        country="United States",
        market_cap_millions=8_500,
        cash_millions=2_800,
        therapeutic_areas=["neurology", "cardiometabolic", "rare_disease"],
        modalities=["antisense", "rnai", "gene_editing"],
        sale_urgency="low",
        standalone_thesis=(
            "Scaled RNA platform; marketed products; deep neurology + cardiometabolic. "
            "Advancing gene editing. Platform acquirer posture rather than forced seller."
        ),
        recent_bd_behavior="platform licensing; AstraZeneca eplontersen deal",
        change_of_control_risk="low",
        notes=(
            "RNA platform leader with commercial products. "
            "More comparable to long-duration standalone than forced seller."
        ),
    ),

    HybridCompany(
        company_id="incyte",
        name="Incyte Corporation",
        ticker="INCY",
        country="United States",
        market_cap_millions=16_000,
        cash_millions=4_000,
        therapeutic_areas=["oncology", "inflammation", "autoimmunity"],
        modalities=["small_molecule", "biologic"],
        sale_urgency="low",
        standalone_thesis=(
            "$4.0B cash (March 2026). 10 Phase 3 studies underway. "
            "Global commercial in oncology + inflammation. Multiple expected launches."
        ),
        recent_bd_behavior="bolt-on acquisitions; regional licensing",
        change_of_control_risk="low",
        notes=(
            "Strong balance sheet + active pipeline materially lowers seller urgency. "
            "Better modeled as buyer or merger-of-equals comparator than near-term target."
        ),
    ),

    HybridCompany(
        company_id="neurocrine",
        name="Neurocrine Biosciences",
        ticker="NBIX",
        country="United States",
        market_cap_millions=13_000,
        cash_millions=2_900,
        therapeutic_areas=["neuroscience", "rare_disease", "metabolic"],
        modalities=["small_molecule", "biologic"],
        sale_urgency="low",
        standalone_thesis=(
            "Acquired Soleno for $2.9B cash (metabolic/rare disease). "
            "Ingrezza + Crenessity commercial base. Active BD behavior. "
        ),
        recent_bd_behavior="acquiring (Soleno $2.9B)",
        change_of_control_risk="low",
        notes=(
            "Live BD behavior (Soleno 2025) confirms acquirer posture. "
            "Model as hybrid/acquirer for targeted neuro or rare-disease assets."
        ),
    ),
]


# ===========================================================================
# Part 3 — TARGET UNIVERSE V2 (institutional-grade target profiles)
# ===========================================================================

TARGET_UNIVERSE_V2: list[AcquirableTarget] = [

    # -----------------------------------------------------------------------
    # Kura Oncology — ziftomenib / AML; Kyowa Kirin partnership
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="KURA",
        company_id="kura",
        asset_id="a-kura-zifto",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Kura Oncology",
            ticker="KURA",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PIPELINE_PORTFOLIO,
            market_cap_millions=1_800,
            cash_millions=581,
            quarterly_burn_millions=55,
            runway_months=36,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="ziftomenib",
            asset_stage="phase_3",
            modality="small_molecule",
            target="KAT6A/6B",
            mechanism_of_action="KAT6A/6B inhibitor (lysine acetyltransferase)",
            biology_validation="clinical",
            human_poc=True,
            registrational_ready=True,
        ),
        rights_and_economics=RightsAndEconomics(
            co_dev_partner="Kyowa Kirin",
            territory_split="Japan/Asia rights to Kyowa Kirin; US/EU retained by Kura",
            royalty_rate_pct=None,
            change_of_control_clause=None,
            coc_consequence="Kyowa Kirin co-development terms subject to COC review",
            milestones_remaining_millions=None,
            encumbrance_severity="medium",
        ),
        financing=FinancingProfile(
            cash_millions=581,
            runway_months=36,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            founder_led=False,
            poison_pill=None,
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=36,
            sale_urgency_score=0.40,
            preferred_outcome="acquisition",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.LOW,
            scale_up_risk="low",
            supplier_concentration="dual",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
            main_data_gaps=["Exact Kyowa Kirin COC language", "royalty stack detail"],
        ),
        analyst_notes=(
            "High-priority oncology target. Ziftomenib pivotal readout expected; "
            "Kyowa Kirin Asia partnership requires COC analysis. Cash cushioned by "
            "collaboration receipts. Pair: Takeda, JNJ, Pfizer for AML/hematology."
        ),
    ),

    # -----------------------------------------------------------------------
    # IDEAYA Biosciences — synthetic lethality + partnerships (Pfizer/Gilead/GSK)
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="IDYA",
        company_id="ideaya",
        asset_id="a-ideaya-daro",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="IDEAYA Biosciences",
            ticker="IDYA",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.PLATFORM,
            target_type=TargetType.PLATFORM,
            market_cap_millions=3_500,
            cash_millions=973,
            runway_months=54,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="darovasertib (IDE397)",
            asset_stage="phase_3",
            modality="small_molecule",
            target="MAT2A / PKC",
            mechanism_of_action="MAT2A + PKC synthetic lethality / darovasertib PKC inhibitor",
            biology_validation="clinical",
            human_poc=True,
        ),
        rights_and_economics=RightsAndEconomics(
            licensor_partner="Servier (darovasertib global rights pre-IDEAYA collaboration)",
            co_dev_partner="Pfizer (IDE397); Gilead (IDE161); GSK (other programs)",
            territory_split="Multiple partnerships; global rights split by asset",
            royalty_rate_pct=None,
            change_of_control_clause=True,
            coc_consequence="Multiple partner COC provisions; require individual consent analysis",
            encumbrance_severity="high",
            milestones_remaining_millions=500,
        ),
        financing=FinancingProfile(
            cash_millions=973,
            runway_months=54,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=54,
            sale_urgency_score=0.25,
            preferred_outcome="strategic_options",
            standalone_build_signals="Multiple big-pharma co-development partnerships signal standalone leverage",
        ),
        cmc=CMCProfile(manufacturing_complexity=ManufacturingComplexity.LOW),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
            main_data_gaps=[
                "Servier/Pfizer/Gilead COC consent requirements",
                "Exact royalty stacks per asset",
                "Change-of-control termination language",
            ],
        ),
        analyst_notes=(
            "Real target; not forced seller. Runway into 2030. Multiple partnerships "
            "(Pfizer, Gilead, GSK, Servier) create both value and COC friction. "
            "Any buyer must model rights clearance program-by-program. "
            "Best buyers: JNJ, Takeda, Gilead (already partnered)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Nuvalent — ROS1 + ALK NSCLC; zidesamtinib PDUFA Sept 18, 2026
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="NUVL",
        company_id="nuvalent",
        asset_id="a-nuvalent-zide",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Nuvalent",
            ticker="NUVL",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PIPELINE_PORTFOLIO,
            market_cap_millions=6_000,
            cash_millions=1_300,
            runway_months=42,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="zidesamtinib (ROS1 / ALK)",
            asset_stage="nda",
            modality="small_molecule",
            target="ROS1 / ALK",
            mechanism_of_action="ROS1 + ALK next-gen inhibitor; activity in brain-mets",
            biology_validation="clinical",
            human_poc=True,
            registrational_ready=True,
        ),
        regulatory=RegulatoryProfile(
            regulatory_designations=RegulatoryDesignations(
                breakthrough=True, priority_review=True,
            ),
            likely_regulatory_path="accelerated",
        ),
        rights_and_economics=RightsAndEconomics(
            global_rights_owned=True,
            change_of_control_clause=None,
            encumbrance_severity="low",
        ),
        financing=FinancingProfile(
            cash_millions=1_300,
            runway_months=42,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=42,
            sale_urgency_score=0.30,
            preferred_outcome="strategic_options",
            standalone_build_signals="Parallel ROS1 + ALK franchises; NDA submitted for neladalkib",
        ),
        cmc=CMCProfile(manufacturing_complexity=ManufacturingComplexity.LOW),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.HIGH,
            main_data_gaps=["Premium range vs standalone build value"],
        ),
        analyst_notes=(
            "PDUFA Sept 18, 2026 — imminent commercial asset. zidesamtinib (ROS1) + "
            "neladalkib (ALK NDA submitted). $1.3B cash; runway into 2029. "
            "Premium strategic value for oncology buyers needing NSCLC kinase depth. "
            "Low forced-sale urgency. Best buyers: JNJ, Takeda, Daiichi, Roche/Genentech."
        ),
    ),

    # -----------------------------------------------------------------------
    # Apogee Therapeutics — best-in-class antibody IL-13Rα1; atopic dermatitis
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="APGE",
        company_id="apogee",
        asset_id="a-apogee-zumilo",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Apogee Therapeutics",
            ticker="APGE",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PLATFORM,
            market_cap_millions=4_000,
            cash_millions=1_300,
            runway_months=42,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="zumilokibart (IL-13Rα1 antibody)",
            asset_stage="phase_2",
            modality="monoclonal_antibody",
            target="IL-13Rα1",
            mechanism_of_action="Half-life extended IL-13Rα1 monoclonal antibody; q4w dosing",
            biology_validation="clinical",
            human_poc=True,
        ),
        regulatory=RegulatoryProfile(
            regulatory_designations=RegulatoryDesignations(fast_track=True),
        ),
        rights_and_economics=RightsAndEconomics(
            global_rights_owned=True,
            change_of_control_clause=None,
            encumbrance_severity="low",
        ),
        financing=FinancingProfile(
            cash_millions=1_300,
            runway_months=42,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=42,
            sale_urgency_score=0.20,
            recent_financing="2026 financing round to ~$1.3B",
            standalone_build_signals="Planning Phase 3 initiation in atopic dermatitis",
            preferred_outcome="strategic_options",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.MEDIUM,
            scale_up_risk="low",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
            main_data_gaps=["Phase 2 top-line data timing", "Combination program readouts"],
        ),
        analyst_notes=(
            "Highest-priority new immunology target. Clean global rights; best-in-class "
            "IL-13Rα1 profile with potential BIC dosing advantage over dupilumab. "
            "$1.3B cash; runway 2029; Phase 3 initiation planned. Very low forced-sale urgency. "
            "Best buyers: Sanofi (dupilumab adjacency + competitive hedge), JNJ, UCB."
        ),
    ),

    # -----------------------------------------------------------------------
    # MoonLake Immunotherapeutics — sonelokimab IL-17A/F; Merck KGaA license
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="MLTX",
        company_id="moonlake",
        asset_id="a-moonlake-sone",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="MoonLake Immunotherapeutics",
            ticker="MLTX",
            exchange="NASDAQ",
            country="Switzerland",
            region="Europe",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PIPELINE_PORTFOLIO,
            market_cap_millions=2_800,
            cash_millions=800,
            runway_months=30,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="sonelokimab (IL-17A/F nanobody)",
            asset_stage="phase_3",
            modality="biologic",
            target="IL-17A/F",
            mechanism_of_action="Trivalent anti-IL-17A/F nanobody; dual neutralisation",
            biology_validation="clinical",
            human_poc=True,
        ),
        rights_and_economics=RightsAndEconomics(
            licensor_partner="Merck KGaA (historical license; global rights held by MoonLake)",
            territory_split="Global rights owned by MoonLake",
            royalty_rate_pct=None,
            royalty_rate_note="low teens royalty on net sales to Merck KGaA",
            change_of_control_clause=True,
            coc_consequence="Merck KGaA license includes COC provisions",
            licensor_consent_required_for_coc=True,
            supply_obligations="Nanobody format requires specialized manufacturing know-how",
            encumbrance_severity="medium",
        ),
        financing=FinancingProfile(
            cash_millions=800,
            runway_months=30,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=30,
            sale_urgency_score=0.45,
            preferred_outcome="acquisition",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.HIGH,
            modality_specific_cmc_risk="Nanobody format; proprietary production process",
            tech_transfer_difficulty="high",
            supplier_concentration="single_source",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
            main_data_gaps=[
                "Exact Merck KGaA COC consent mechanism",
                "Nanobody manufacturing transfer terms",
                "Full royalty rate confirmation",
            ],
        ),
        analyst_notes=(
            "Premium immunology target. Sonelokimab HS/PsA/psoriasis Phase 3 data strong. "
            "Rights model: global rights owned BUT low-teens Merck KGaA royalty + COC clause. "
            "CMC: nanobody format requires supply-chain due diligence and tech-transfer plan. "
            "Best buyers: Sanofi, UCB, JNJ (immunology); must resolve Merck KGaA license."
        ),
    ),

    # -----------------------------------------------------------------------
    # Verve Therapeutics — in vivo gene editing, PCSK9, cardiovascular
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="VERV",
        company_id="verve",
        asset_id="a-verve-pcsk9",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Verve Therapeutics",
            ticker="VERV",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.PLATFORM,
            target_type=TargetType.PLATFORM,
            market_cap_millions=1_200,
            cash_millions=500,
            quarterly_burn_millions=45,
            runway_months=24,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="VERVE-101 (PCSK9 gene editing)",
            asset_stage="phase_2",
            modality="gene_editing",
            target="PCSK9",
            mechanism_of_action="Single-course adenine base editor delivered via LNP; permanent PCSK9 reduction",
            biology_validation="clinical",
            human_poc=True,
        ),
        rights_and_economics=RightsAndEconomics(
            global_rights_owned=True,
            change_of_control_clause=None,
            encumbrance_severity="low",
        ),
        financing=FinancingProfile(
            cash_millions=500,
            runway_months=24,
            strategic_alternative_pressure=True,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=24,
            sale_urgency_score=0.60,
            preferred_outcome="acquisition",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.HIGH,
            modality_specific_cmc_risk="Base editing + LNP delivery; complex CMC",
            scale_up_risk="high",
            cold_chain_required=True,
            tech_transfer_difficulty="high",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
            main_data_gaps=[
                "Long-tail gene editing safety data",
                "LNP delivery scale-up track record",
                "Regulatory path for permanent genome modification",
            ],
        ),
        analyst_notes=(
            "Strategically interesting for cardiometabolic buyers (Novo, AZ, Novartis). "
            "Key diligence: CMC (base editor + LNP), long-tail safety, FDA stance on "
            "permanent gene modification in non-life-threatening disease. "
            "Runway ~24 months creates moderate financing pressure. "
            "Mark all first-order diligence items as technical-risk flags."
        ),
    ),

    # -----------------------------------------------------------------------
    # Rocket Pharmaceuticals — rare disease gene therapy; KRESLADI approved
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="RCKT",
        company_id="rocket",
        asset_id="a-rocket-kresladi",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Rocket Pharmaceuticals",
            ticker="RCKT",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PIPELINE_PORTFOLIO,
            market_cap_millions=1_100,
            cash_millions=323,
            quarterly_burn_millions=65,
            runway_months=20,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="KRESLADI (gene therapy; LAD-I)",
            asset_stage="approved",
            modality="gene_therapy",
            target="LAD-I (ITGB2)",
            mechanism_of_action="Lentiviral gene therapy for LAD-I (leukocyte adhesion deficiency)",
            biology_validation="clinical",
            human_poc=True,
            registrational_ready=True,
        ),
        rights_and_economics=RightsAndEconomics(
            global_rights_owned=True,
            change_of_control_clause=None,
            encumbrance_severity="low",
        ),
        financing=FinancingProfile(
            cash_millions=323,
            quarterly_burn_millions=65,
            runway_months=20,
            strategic_alternative_pressure=True,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=20,
            sale_urgency_score=0.70,
            preferred_outcome="acquisition",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.HIGH,
            modality_specific_cmc_risk="Lentiviral vector; autologous manufacturing complexity",
            scale_up_risk="high",
            viral_vector_capacity_needed=True,
            tech_transfer_difficulty="high",
            cell_therapy_complexity="autologous lentiviral gene therapy",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
            main_data_gaps=[
                "Autologous manufacturing scale and transfer risk",
                "Gene-therapy-specific long-term safety obligations",
                "PRV monetization remaining value",
            ],
        ),
        analyst_notes=(
            "More saleable than cash-rich immunology names given ~20 month runway. "
            "KRESLADI approved; gene-therapy-specific long-term safety obligations. "
            "Cash ~$323M after PRV monetization (Q1 2026). "
            "CMC-sensitive: autologous LV vector requires buyer with gene therapy manufacturing. "
            "Best buyers: Pfizer (gene therapy), Bluebird-acquirer, Sarepta."
        ),
    ),

    # -----------------------------------------------------------------------
    # Cytokinetics — cardiovascular; cardiac muscle biology platform
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="CYTK",
        company_id="cytokinetics",
        asset_id="a-cytk-aficamten",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Cytokinetics",
            ticker="CYTK",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PLATFORM,
            market_cap_millions=4_800,
            cash_millions=1_200,
            runway_months=36,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="aficamten (cardiac myosin inhibitor)",
            asset_stage="phase_3",
            modality="small_molecule",
            target="Cardiac myosin",
            mechanism_of_action="Cardiac sarcomere modulator; reduces hypercontractility in HCM",
            biology_validation="clinical",
            human_poc=True,
            registrational_ready=True,
        ),
        rights_and_economics=RightsAndEconomics(
            global_rights_owned=True,
            change_of_control_clause=None,
            encumbrance_severity="low",
        ),
        financing=FinancingProfile(
            cash_millions=1_200,
            runway_months=36,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=36,
            sale_urgency_score=0.35,
            preferred_outcome="acquisition",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.LOW,
            scale_up_risk="low",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.HIGH,
            main_data_gaps=["Aficamten pivotal data timeline vs mavacamten"],
        ),
        analyst_notes=(
            "Specialty cardiovascular; cardiac muscle platform. Case hinges on pair-by-pair "
            "buyer appetite, not broad auctionability. EXPLORER-HCM data readout key. "
            "Best buyers: AstraZeneca (CVRM franchise), Novartis, Novo Nordisk, BMS (cardiovascular)."
        ),
    ),

    # -----------------------------------------------------------------------
    # Vaxcyte — VAX-31 pneumococcal; Sutro XpressCF platform; $2.7B cash
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="PCVX",
        company_id="vaxcyte",
        asset_id="a-vaxcyte-vax31",
        company_class=CompanyClass.TARGET,
        identity=CompanyIdentity(
            company_name="Vaxcyte",
            ticker="PCVX",
            exchange="NASDAQ",
            country="United States",
            region="North America",
            company_type=CompanyType.THERAPEUTICS,
            target_type=TargetType.PLATFORM,
            market_cap_millions=9_500,
            cash_millions=2_700,
            runway_months=60,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="VAX-31 (31-valent pneumococcal conjugate vaccine)",
            asset_stage="phase_3",
            modality="vaccine",
            mechanism_of_action="Pneumococcal conjugate vaccine; broader serotype coverage than PCV20",
            biology_validation="clinical",
            human_poc=True,
        ),
        rights_and_economics=RightsAndEconomics(
            licensor_partner="Sutro Biopharma (XpressCF cell-free synthesis platform — exclusively licensed)",
            supply_obligations="Sutro supplies cell-free synthesis platform technology",
            change_of_control_clause=True,
            coc_consequence="Sutro license includes COC provisions; technology access may require consent",
            licensor_consent_required_for_coc=True,
            encumbrance_severity="medium",
        ),
        financing=FinancingProfile(
            cash_millions=2_700,
            runway_months=60,
            strategic_alternative_pressure=False,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.INDEPENDENT,
            capital_runway_months=60,
            sale_urgency_score=0.15,
            standalone_build_signals="North Carolina manufacturing buildout underway",
            preferred_outcome="standalone",
            management_standalone_rhetoric="Building manufacturing independence",
        ),
        cmc=CMCProfile(
            manufacturing_complexity=ManufacturingComplexity.HIGH,
            modality_specific_cmc_risk="Cell-free synthesis platform; proprietary Sutro technology",
            scale_up_risk="medium",
            tech_transfer_difficulty="high",
        ),
        ip_exclusivity=IPExclusivity(
            ip_strength_score=0.85,
            freedom_to_operate_risk="low",
        ),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.HIGH,
            main_data_gaps=[
                "Sutro XpressCF COC consent mechanism",
                "Manufacturing buildout timeline",
            ],
        ),
        analyst_notes=(
            "Top-tier vaccine target. VAX-31 Phase 3; $2.7B cash; manufacturing buildout. "
            "Strategic value obvious; seller willingness LOW (well-funded + independence build). "
            "Rights friction: Sutro XpressCF license with COC provisions. "
            "Best buyers: Pfizer (Prevnar franchise defense), Sanofi, GSK."
        ),
    ),

    # -----------------------------------------------------------------------
    # AbCellera — antibody platform / clinical-stage; tools-adjacent
    # -----------------------------------------------------------------------
    AcquirableTarget(
        ticker="ABCL",
        company_id="abcellera",
        asset_id="a-abcellera-platform",
        company_class=CompanyClass.HYBRID,  # platform / tools-adjacent
        identity=CompanyIdentity(
            company_name="AbCellera Biologics",
            ticker="ABCL",
            exchange="NASDAQ",
            country="Canada",
            region="North America",
            company_type=CompanyType.PLATFORM,
            target_type=TargetType.PLATFORM,
            market_cap_millions=2_000,
            cash_millions=800,
            runway_months=48,
        ),
        clinical=ClinicalAssetDetail(
            lead_asset_name="Platform + pipeline (endocrinology, women's health, immunology, oncology)",
            asset_stage="phase_2",
            modality="monoclonal_antibody",
            mechanism_of_action="Antibody discovery platform; clinical-stage programs across multiple TAs",
            biology_validation="clinical",
        ),
        rights_and_economics=RightsAndEconomics(
            global_rights_owned=True,
            change_of_control_clause=None,
            encumbrance_severity="low",
        ),
        financing=FinancingProfile(
            cash_millions=800,
            runway_months=48,
        ),
        seller_willingness=SellerWillingness(
            stated_strategy=SellerStrategy.STRATEGIC_OPTIONS,
            capital_runway_months=48,
            sale_urgency_score=0.30,
        ),
        cmc=CMCProfile(manufacturing_complexity=ManufacturingComplexity.MEDIUM),
        data_quality=DataQuality(
            overall_confidence=DataConfidence.MEDIUM,
        ),
        analyst_notes=(
            "Relevant both as platform acquisition and strategic capability add-on. "
            "Not a standard single-asset biotech — acquisition rationale is the discovery platform. "
            "Best buyers: antibody-platform-seeking acquirers (JNJ, AZ, Roche, Regeneron)."
        ),
    ),
]


# ===========================================================================
# Part 4 — PRECEDENT REGISTRY (closed/pending strategic deals)
# ===========================================================================

@dataclass
class PrecedentDeal:
    """A completed or pending acquisition. For calibration and comparables."""
    target_name: str
    target_ticker: str
    acquirer_name: str
    acquirer_id: str
    deal_value_millions: float
    announced_year: int
    deal_type: str              # acquisition | merger | asset_deal
    therapeutic_area: str
    lead_asset: str
    deal_rationale: str
    premium_pct: Optional[float] = None
    status: str = "closed"      # closed | pending | terminated
    notes: str = ""


PRECEDENT_REGISTRY: list[PrecedentDeal] = [
    PrecedentDeal(
        target_name="Akero Therapeutics",
        target_ticker="AKRO",
        acquirer_name="Novo Nordisk",
        acquirer_id="novo_nordisk",
        deal_value_millions=5_200,
        announced_year=2025,
        deal_type="acquisition",
        therapeutic_area="mash",
        lead_asset="efruxifermin (FGF21 analogue)",
        deal_rationale=(
            "Novo expands into MASH; efruxifermin Phase 3 data de-risks asset. "
            "Cardiometabolic platform extension beyond GLP-1. "
            "Up to $5.2B consideration."
        ),
        premium_pct=65,
        status="closed",
        notes="Akero should be removed from active standalone target universe.",
    ),
    PrecedentDeal(
        target_name="Soleno Therapeutics",
        target_ticker="SLNO",
        acquirer_name="Neurocrine Biosciences",
        acquirer_id="neurocrine",
        deal_value_millions=2_900,
        announced_year=2025,
        deal_type="acquisition",
        therapeutic_area="rare_disease",
        lead_asset="diazoxide choline (PWS)",
        deal_rationale="Neurocrine expands into metabolic/rare disease; adds Prader-Willi syndrome.",
        premium_pct=None,
        status="closed",
    ),
    PrecedentDeal(
        target_name="Candid Therapeutics",
        target_ticker="CAND",
        acquirer_name="UCB",
        acquirer_id="ucb",
        deal_value_millions=2_900,
        announced_year=2026,
        deal_type="acquisition",
        therapeutic_area="immunology",
        lead_asset="CD38 bispecific antibody",
        deal_rationale="UCB expands immunology franchise; bispecific capability addition.",
        premium_pct=None,
        status="pending",
        notes="Announced May 2026.",
    ),
    PrecedentDeal(
        target_name="Dren Bio (immunology unit)",
        target_ticker="",
        acquirer_name="Sanofi",
        acquirer_id="sanofi",
        deal_value_millions=None,
        announced_year=2025,
        deal_type="acquisition",
        therapeutic_area="immunology",
        lead_asset="FcγR pathway biologic",
        deal_rationale="Sanofi deepens innate immune axis post-Dupixent.",
        status="closed",
    ),
    PrecedentDeal(
        target_name="Momenta Pharmaceuticals",
        target_ticker="MNTA",
        acquirer_name="Johnson & Johnson",
        acquirer_id="jnj",
        deal_value_millions=6_500,
        announced_year=2020,
        deal_type="acquisition",
        therapeutic_area="immunology",
        lead_asset="nipocalimab (FcRn)",
        deal_rationale="JNJ acquires FcRn platform; nipocalimab becomes Imaavy.",
        premium_pct=70,
        status="closed",
    ),
]


# ===========================================================================
# Part 5 — ASIA INNOVATOR REGISTRY
# ===========================================================================

@dataclass
class AsiaCompanyNode:
    """Lightweight record for an Asia-origin innovation source.

    These companies matter as asset sources, regional rights holders,
    commercialization partners, or future buyers — NOT always as
    acquisition targets. Required for CMC scoring and BD flow tracking.
    """
    company_id: str
    name: str
    ticker: Optional[str]
    country: str
    primary_focus: list[str]   # TA list
    modalities: list[str]
    key_deals_with_west: list[str] = field(default_factory=list)
    asset_out_licensing_active: bool = False
    notes: str = ""


ASIA_REGISTRY: list[AsiaCompanyNode] = [
    AsiaCompanyNode("hengrui", "Jiangsu Hengrui Medicine", "HENGRUI", "China",
        ["oncology", "immunology", "metabolic", "respiratory"],
        ["small_molecule", "biologic"],
        key_deals_with_west=["GSK (respiratory/immunology/oncology package 2025)", "MSD (SHR-1316)"],
        asset_out_licensing_active=True,
        notes="Most active China out-licenser; major source of global BD flow.",
    ),
    AsiaCompanyNode("innovent", "Innovent Biologics", "1801.HK", "China",
        ["oncology", "metabolic", "immunology"],
        ["monoclonal_antibody", "bispecific"],
        key_deals_with_west=["Eli Lilly (sintilimab US rights)", "Multiple co-development"],
        asset_out_licensing_active=True,
        notes="37-asset pipeline; fully integrated R&D + CMC + commercial. Key oncology source.",
    ),
    AsiaCompanyNode("akeso", "Akeso Biopharma", "9926.HK", "China",
        ["oncology", "autoimmune"],
        ["bispecific"],
        key_deals_with_west=["Summit Therapeutics (ivonescimab PD-1/VEGF bispecific)"],
        asset_out_licensing_active=True,
        notes="ivonescimab vs Keytruda HEAD-to-HEAD data; bispecific platform.",
    ),
    AsiaCompanyNode("beigene", "BeiGene / BeOne Medicines", "BGNE", "China",
        ["oncology", "hematology"],
        ["small_molecule", "biologic"],
        key_deals_with_west=["Novartis (tislelizumab global)", "Multiple CRO/CMO relationships"],
        asset_out_licensing_active=True,
        notes="zanubrutinib (BTK) global commercial; major oncology platform.",
    ),
    AsiaCompanyNode("hansoh", "Hansoh Pharmaceutical", "3692.HK", "China",
        ["oncology", "metabolic", "CNS"],
        ["small_molecule"],
        key_deals_with_west=["AZ (HS-10353 GLP-1)", "Merck (HS-20093 ADC)"],
        asset_out_licensing_active=True,
        notes="Active GLP-1 and oncology out-licensing. Strong small-molecule chemistry.",
    ),
    AsiaCompanyNode("sino_biopharm", "Sino Biopharmaceutical", "1177.HK", "China",
        ["respiratory", "immunology", "oncology"],
        ["biologic", "small_molecule"],
        key_deals_with_west=["GSK (bepirovirsen commercialization)"],
        asset_out_licensing_active=True,
    ),
    AsiaCompanyNode("cspc", "CSPC Pharmaceutical Group", "1093.HK", "China",
        ["oncology", "neuroscience", "cardiometabolic"],
        ["small_molecule", "biologic"],
        asset_out_licensing_active=False,
        notes="Large diversified Chinese pharma; selected in-licensing of western assets.",
    ),
    AsiaCompanyNode("kelun_biotech", "Sichuan Kelun-Biotech", "6990.HK", "China",
        ["oncology"],
        ["antibody_drug_conjugate"],
        key_deals_with_west=["Merck & Co (ADC platform collaboration)"],
        asset_out_licensing_active=True,
        notes="ADC platform; major Merck collaboration validates quality.",
    ),
    AsiaCompanyNode("remegen", "RemeGen", "9995.HK", "China",
        ["oncology", "autoimmune"],
        ["antibody_drug_conjugate"],
        key_deals_with_west=["Seagen (disitamab vedotin global license)"],
        asset_out_licensing_active=True,
        notes="RC48 (disitamab vedotin) ADC global licensed to Pfizer/Seagen.",
    ),
    AsiaCompanyNode("zai_lab", "Zai Lab", "ZLAB", "China",
        ["oncology", "immunology", "CNS"],
        ["biologic", "small_molecule"],
        key_deals_with_west=["GlaxoSmithKline", "Pfizer", "MacroGenics", "Agenus"],
        asset_out_licensing_active=False,
        notes="In-licensing model; China commercialization partner for western biotechs.",
    ),
    AsiaCompanyNode("hutchmed", "HUTCHMED", "HCM", "China/HK",
        ["oncology"],
        ["small_molecule"],
        key_deals_with_west=["AZ (fruquintinib FRESCO-2)", "Takeda (colorectal)"],
        asset_out_licensing_active=True,
    ),
    AsiaCompanyNode("duality_bio", "DualityBio", "", "China",
        ["oncology"],
        ["antibody_drug_conjugate"],
        key_deals_with_west=["Bristol Myers Squibb (DB-1303 ADC deal 2024)"],
        asset_out_licensing_active=True,
        notes="Next-generation ADC platform; BMS deal validates platform.",
    ),
    AsiaCompanyNode("bio_thera", "Bio-Thera Solutions", "688177.SS", "China",
        ["immunology", "oncology"],
        ["biologic"],
        asset_out_licensing_active=True,
    ),
    AsiaCompanyNode("celltrion", "Celltrion", "068270.KS", "South Korea",
        ["immunology", "oncology"],
        ["biologic", "biosimilar"],
        asset_out_licensing_active=False,
        notes="Major biosimilar manufacturer; CT-P59 (COVID Ab), VEGEMAB.",
    ),
    AsiaCompanyNode("samsung_biologics", "Samsung Biologics", "207940.KS", "South Korea",
        ["manufacturing"],
        ["biologic"],
        asset_out_licensing_active=False,
        notes="Largest CDO/CDMO in Asia; critical for CMC scoring of Asia-origin assets.",
    ),
    AsiaCompanyNode("sk_biopharm", "SK Biopharmaceuticals", "326030.KS", "South Korea",
        ["CNS"],
        ["small_molecule"],
        key_deals_with_west=["Jazz Pharmaceuticals (cenobamate global)"],
        asset_out_licensing_active=True,
    ),
    AsiaCompanyNode("chugai", "Chugai Pharmaceutical", "4519.T", "Japan",
        ["oncology", "rare_disease", "immunology"],
        ["biologic", "bispecific"],
        key_deals_with_west=["Roche (majority shareholder; recycling antibody tech)"],
        asset_out_licensing_active=True,
        notes="Roche subsidiary; recycling antibody (SMART-Ig) platform leader.",
    ),
    AsiaCompanyNode("peptidream", "PeptiDream", "4587.T", "Japan",
        ["oncology", "rare_disease"],
        ["peptide"],
        key_deals_with_west=["BMS", "Pfizer", "Merck KGaA (peptide discovery)"],
        asset_out_licensing_active=True,
        notes="PDPS cyclic peptide discovery platform; multiple big-pharma discovery deals.",
    ),
]


# ===========================================================================
# Part 6 — TOOLS / CDMO REGISTRY
# ===========================================================================

@dataclass
class ToolsCDMONode:
    """Lightweight record for a manufacturing, CRO, or discovery-platform company.

    Required to score CMC bottlenecks, outsourcing dependence, platform leverage,
    and buyer manufacturing capability in the pair model.
    """
    company_id: str
    name: str
    ticker: Optional[str]
    country: str
    category: str       # cdmo | cro | analytics | discovery_platform | diagnostics
    modalities_served: list[str]
    key_clients_or_deals: list[str] = field(default_factory=list)
    notes: str = ""


TOOLS_CDMO_REGISTRY: list[ToolsCDMONode] = [
    ToolsCDMONode("lonza", "Lonza Group", "LONN.SW", "Switzerland",
        "cdmo", ["biologic", "gene_therapy", "cell_therapy", "mrna"],
        notes="Largest biotech CDMO; critical for ADC, LNP, viral vector CMC scoring.",
    ),
    ToolsCDMONode("catalent", "Catalent", "CTLT", "United States",
        "cdmo", ["biologic", "small_molecule", "gene_therapy", "mrna"],
        notes="Acquired by Novo Nordisk 2024 for fill-finish capacity.",
    ),
    ToolsCDMONode("thermo_fisher", "Thermo Fisher Scientific", "TMO", "United States",
        "cdmo", ["biologic", "small_molecule", "gene_therapy"],
        notes="PPD CRO + CDMO (Patheon) capabilities; broad pharma services.",
    ),
    ToolsCDMONode("danaher_cytiva", "Danaher / Cytiva", "DHR", "United States",
        "cdmo", ["biologic"],
        notes="Cytiva bioprocessing equipment; bioprocess supply chain critical path.",
    ),
    ToolsCDMONode("sartorius", "Sartorius", "SRT.DE", "Germany",
        "cdmo", ["biologic"],
        notes="Bioprocess filtration and chromatography; supply chain risk factor.",
    ),
    ToolsCDMONode("wuxi_biologics", "WuXi Biologics", "2269.HK", "China",
        "cdmo", ["biologic", "adc"],
        notes="Largest China biologics CDMO; significant US regulatory/geopolitical risk.",
    ),
    ToolsCDMONode("wuxi_apptec", "WuXi AppTec", "603259.SS", "China",
        "cdmo", ["small_molecule", "biologic"],
        notes="CRO + CDMO integration; BIOSECURE Act exposure.",
    ),
    ToolsCDMONode("charles_river", "Charles River Laboratories", "CRL", "United States",
        "cro", ["all"],
        notes="Preclinical CRO; toxicology, safety pharmacology, early discovery.",
    ),
    ToolsCDMONode("iqvia", "IQVIA", "IQV", "United States",
        "cro", ["all"],
        notes="Clinical CRO + data/analytics; Phase 2/3 execution at scale.",
    ),
    ToolsCDMONode("icon_plc", "ICON plc", "ICLR", "Ireland",
        "cro", ["all"],
        notes="Late-stage clinical CRO; oncology and rare disease specialization.",
    ),
    ToolsCDMONode("medpace", "Medpace Holdings", "MEDP", "United States",
        "cro", ["all"],
        notes="Mid-market CRO; strong in metabolic, oncology, rare disease.",
    ),
    ToolsCDMONode("genscript", "GenScript Biotech", "1548.HK", "China",
        "discovery_platform", ["biologic", "gene_therapy", "cell_therapy"],
        notes="Gene synthesis + antibody discovery platform.",
    ),
    ToolsCDMONode("illumina", "Illumina", "ILMN", "United States",
        "analytics", ["diagnostics", "genomics"],
        notes="NGS sequencing platform; companion diagnostic development critical.",
    ),
    ToolsCDMONode("agilent", "Agilent Technologies", "A", "United States",
        "analytics", ["small_molecule", "biologic"],
        notes="Analytical chemistry instruments; QC and bioanalytical.",
    ),
    ToolsCDMONode("revvity", "Revvity (PerkinElmer)", "RVTY", "United States",
        "analytics", ["diagnostics", "genomics"],
        notes="Newborn screening, immunoassay, drug discovery tools.",
    ),
    ToolsCDMONode("bio_rad", "Bio-Rad Laboratories", "BIO", "United States",
        "analytics", ["biologic"],
        notes="PCR, ddPCR, Western blot; QC in biologics manufacturing.",
    ),
    ToolsCDMONode("waters_corp", "Waters Corporation", "WAT", "United States",
        "analytics", ["small_molecule", "biologic"],
        notes="Liquid chromatography / mass spec; critical for CMC release testing.",
    ),
    ToolsCDMONode("becton_dickinson", "Becton, Dickinson & Company", "BDX", "United States",
        "analytics", ["cell_therapy"],
        notes="Flow cytometry, cell analysis; cell therapy manufacturing QC.",
    ),
    ToolsCDMONode("sutro_biopharma", "Sutro Biopharma", "STRO", "United States",
        "discovery_platform", ["biologic", "adc"],
        notes="XpressCF cell-free synthesis platform; Vaxcyte exclusive license.",
    ),
    ToolsCDMONode("abcellera_tools", "AbCellera (platform)", "ABCL", "Canada",
        "discovery_platform", ["monoclonal_antibody"],
        notes="Antibody discovery platform licensed to multiple large pharma.",
    ),
]


# ===========================================================================
# Part 7 — PAIR TABLE (buyer × target with full institutional PairScore)
# ===========================================================================

def _pair(
    acquirer_id: str,
    target_id: str,
    *,
    ta_fit: float,
    modality_fit: float,
    loe_gap_match: float = 0.0,
    commercial_synergy: float = 0.0,
    cmc_fit: float = 0.80,
    rights_friction: float = 0.10,
    asset_overlap: float = 0.0,
    commercial_adjacency: float = 0.0,
    antitrust_risk: float = 0.10,
    affordability_ratio: float = 1.0,
    strategic_urgency: float = 0.50,
    right_to_win_score: float = 0.50,
    probability_of_approach: float = 0.25,
    expected_synergies_millions: Optional[float] = None,
    management_relationship_history: str = "no_prior_contact",
    likely_deal_structure: str = "full_acquisition",
    likely_premium_pct: float = 0.50,
    reason_care: str = "",
    reason_not_bid: str = "",
    probability_top_bidder: float = 0.25,
    notes: str = "",
) -> AcquirerTargetPair:
    return AcquirerTargetPair(
        acquirer_id=acquirer_id,
        target_asset_id=target_id,
        scores=PairScore(
            ta_fit=ta_fit,
            modality_fit=modality_fit,
            loe_gap_match=loe_gap_match,
            commercial_synergy=commercial_synergy,
            cmc_fit=cmc_fit,
            rights_friction=rights_friction,
            asset_overlap=asset_overlap,
            commercial_adjacency=commercial_adjacency,
            antitrust_risk=antitrust_risk,
            affordability_ratio=affordability_ratio,
            strategic_urgency=strategic_urgency,
            right_to_win_score=right_to_win_score,
            probability_of_approach=probability_of_approach,
            expected_synergies_millions=expected_synergies_millions,
            management_relationship_history=management_relationship_history,
        ),
        outputs=PairOutputs(
            likely_deal_structure=likely_deal_structure,
            likely_premium_pct=likely_premium_pct,
            reason_this_buyer_would_care=reason_care,
            reason_this_buyer_would_not_bid=reason_not_bid,
            probability_buyer_is_top_bidder=probability_top_bidder,
        ),
        notes=notes,
    )


# Key (acquirer_id, target_asset_id) → AcquirerTargetPair
PAIR_TABLE: dict[tuple[str, str], AcquirerTargetPair] = {

    # --- JNJ pairs ---
    ("jnj", "a-apogee-zumilo"): _pair(
        "jnj", "a-apogee-zumilo",
        ta_fit=0.95, modality_fit=0.90,
        loe_gap_match=0.70, commercial_synergy=0.80,
        cmc_fit=0.90, rights_friction=0.05,
        asset_overlap=0.20, commercial_adjacency=0.85,
        antitrust_risk=0.25, affordability_ratio=1.20,
        strategic_urgency=0.75, right_to_win_score=0.70,
        probability_of_approach=0.40,
        expected_synergies_millions=800,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.55,
        reason_care=(
            "IL-13Rα1 antibody fills immunology adjacency to Imaavy/nipocalimab franchise. "
            "Best-in-class profile with potential dosing advantage vs dupilumab."
        ),
        reason_not_bid="High asking price vs competitive immunology M&A market; Sanofi likely outbids.",
        probability_top_bidder=0.25,
    ),

    ("jnj", "a-moonlake-sone"): _pair(
        "jnj", "a-moonlake-sone",
        ta_fit=0.90, modality_fit=0.80,
        loe_gap_match=0.65, commercial_synergy=0.75,
        cmc_fit=0.60, rights_friction=0.50,
        asset_overlap=0.15, commercial_adjacency=0.80,
        antitrust_risk=0.20, affordability_ratio=1.30,
        strategic_urgency=0.65, right_to_win_score=0.55,
        probability_of_approach=0.30,
        expected_synergies_millions=600,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.55,
        reason_care="IL-17A/F nanobody adds differentiated HS/psoriasis platform to immunology franchise.",
        reason_not_bid=(
            "Merck KGaA COC clause; nanobody manufacturing tech-transfer risk. "
            "Rights friction score 0.50 — requires dedicated rights clearance."
        ),
        probability_top_bidder=0.20,
        notes="Rights friction is the primary acquisition complexity factor.",
    ),

    ("jnj", "a-nuvalent-zide"): _pair(
        "jnj", "a-nuvalent-zide",
        ta_fit=0.90, modality_fit=0.90,
        loe_gap_match=0.50, commercial_synergy=0.80,
        cmc_fit=0.95, rights_friction=0.05,
        asset_overlap=0.10, commercial_adjacency=0.75,
        antitrust_risk=0.15, affordability_ratio=1.30,
        strategic_urgency=0.60, right_to_win_score=0.60,
        probability_of_approach=0.30,
        expected_synergies_millions=700,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.50,
        reason_care="NSCLC kinase depth; zidesamtinib PDUFA Sept 2026 is near-term commercial asset.",
        reason_not_bid="Premium valuation expected ($6B+ for near-commercial); multiple oncology buyers compete.",
        probability_top_bidder=0.20,
    ),

    # --- Sanofi pairs ---
    ("sanofi", "a-apogee-zumilo"): _pair(
        "sanofi", "a-apogee-zumilo",
        ta_fit=1.0, modality_fit=0.95,
        loe_gap_match=0.85, commercial_synergy=0.90,
        cmc_fit=0.90, rights_friction=0.05,
        asset_overlap=0.15, commercial_adjacency=0.95,
        antitrust_risk=0.30, affordability_ratio=1.20,
        strategic_urgency=0.90, right_to_win_score=0.80,
        probability_of_approach=0.55,
        expected_synergies_millions=1_200,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.65,
        reason_care=(
            "IL-13Rα1 is the most direct hedge/extension of the Dupixent franchise. "
            "Zumilokibart BIC profile with q4w dosing could extend Sanofi's atopic dominance post-LOE."
        ),
        reason_not_bid="Antitrust scrutiny possible given Dupixent dominance in same indication.",
        probability_top_bidder=0.45,
        notes="Highest-probability pair in immunology universe.",
    ),

    ("sanofi", "a-moonlake-sone"): _pair(
        "sanofi", "a-moonlake-sone",
        ta_fit=0.90, modality_fit=0.85,
        loe_gap_match=0.70, commercial_synergy=0.80,
        cmc_fit=0.65, rights_friction=0.50,
        asset_overlap=0.10, commercial_adjacency=0.85,
        antitrust_risk=0.15, affordability_ratio=1.30,
        strategic_urgency=0.70, right_to_win_score=0.65,
        probability_of_approach=0.35,
        expected_synergies_millions=700,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.60,
        reason_care="IL-17A/F coverage adds HS/psoriasis indication outside Dupixent's Th2 lane.",
        reason_not_bid="Merck KGaA license + nanobody CMC complexity adds integration risk.",
        probability_top_bidder=0.30,
    ),

    # --- UCB pairs ---
    ("ucb", "a-apogee-zumilo"): _pair(
        "ucb", "a-apogee-zumilo",
        ta_fit=0.90, modality_fit=0.90,
        loe_gap_match=0.70, commercial_synergy=0.75,
        cmc_fit=0.85, rights_friction=0.05,
        asset_overlap=0.05, commercial_adjacency=0.80,
        antitrust_risk=0.10, affordability_ratio=0.60,  # deal size strain for UCB
        strategic_urgency=0.80, right_to_win_score=0.45,
        probability_of_approach=0.25,
        expected_synergies_millions=400,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.60,
        reason_care="IL-13Rα1 adds dermatology immunology to UCB's BIMZELX franchise.",
        reason_not_bid="Affordability constraint — $4B+ deal size likely strains UCB balance sheet.",
        probability_top_bidder=0.12,
        notes="UCB can afford partnership/option deal; full acquisition is balance-sheet strained.",
    ),

    ("ucb", "a-moonlake-sone"): _pair(
        "ucb", "a-moonlake-sone",
        ta_fit=0.90, modality_fit=0.85,
        loe_gap_match=0.65, commercial_synergy=0.80,
        cmc_fit=0.60, rights_friction=0.50,
        asset_overlap=0.05, commercial_adjacency=0.85,
        antitrust_risk=0.05, affordability_ratio=0.80,
        strategic_urgency=0.75, right_to_win_score=0.50,
        probability_of_approach=0.30,
        expected_synergies_millions=350,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.55,
        reason_care="IL-17A/F adds HS/PsA to BIMZELX (IL-17A) immunology franchise at UCB.",
        reason_not_bid="Merck KGaA COC; nanobody CMC; UCB balance sheet cannot absorb above $3B.",
        probability_top_bidder=0.15,
    ),

    # --- Novo Nordisk pairs ---
    ("novo_nordisk", "a-cytk-aficamten"): _pair(
        "novo_nordisk", "a-cytk-aficamten",
        ta_fit=0.65, modality_fit=0.85,
        loe_gap_match=0.30, commercial_synergy=0.60,
        cmc_fit=0.90, rights_friction=0.05,
        asset_overlap=0.05, commercial_adjacency=0.50,
        antitrust_risk=0.05, affordability_ratio=1.50,
        strategic_urgency=0.45, right_to_win_score=0.40,
        probability_of_approach=0.20,
        expected_synergies_millions=300,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.50,
        reason_care="Cardiovascular adjacency to GLP-1 patient population; HCM is cardiometabolic-adjacent.",
        reason_not_bid="Not core Novo lane; obesity/MASH focus means limited commercial synergy.",
        probability_top_bidder=0.12,
    ),

    ("novo_nordisk", "a-verve-pcsk9"): _pair(
        "novo_nordisk", "a-verve-pcsk9",
        ta_fit=0.80, modality_fit=0.50,
        loe_gap_match=0.40, commercial_synergy=0.65,
        cmc_fit=0.40, rights_friction=0.10,
        asset_overlap=0.10, commercial_adjacency=0.55,
        antitrust_risk=0.10, affordability_ratio=1.40,
        strategic_urgency=0.55, right_to_win_score=0.35,
        probability_of_approach=0.20,
        expected_synergies_millions=400,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.55,
        reason_care="PCSK9 gene editing fits cardiometabolic platform; permanent efficacy is differentiated.",
        reason_not_bid=(
            "CMC fit low (Novo has no gene editing / LNP manufacturing). "
            "Long-tail safety unknown in non-life-threatening disease."
        ),
        probability_top_bidder=0.15,
        notes="CMC capability gap is the primary barrier; Novo would need to acquire/partner CMC.",
    ),

    # --- Takeda pairs ---
    ("takeda", "a-kura-zifto"): _pair(
        "takeda", "a-kura-zifto",
        ta_fit=0.85, modality_fit=0.85,
        loe_gap_match=0.70, commercial_synergy=0.70,
        cmc_fit=0.85, rights_friction=0.30,
        asset_overlap=0.10, commercial_adjacency=0.65,
        antitrust_risk=0.10, affordability_ratio=0.90,
        strategic_urgency=0.70, right_to_win_score=0.55,
        probability_of_approach=0.35,
        expected_synergies_millions=500,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.50,
        reason_care="AML/KAT6 fits thin oncology/hematology pipeline; ziftomenib near pivotal.",
        reason_not_bid="Kyowa Kirin Asia partnership rights require COC review; leverage constraints.",
        probability_top_bidder=0.25,
    ),

    ("takeda", "a-ideaya-daro"): _pair(
        "takeda", "a-ideaya-daro",
        ta_fit=0.80, modality_fit=0.80,
        loe_gap_match=0.60, commercial_synergy=0.70,
        cmc_fit=0.85, rights_friction=0.70,
        asset_overlap=0.05, commercial_adjacency=0.65,
        antitrust_risk=0.05, affordability_ratio=0.85,
        strategic_urgency=0.60, right_to_win_score=0.40,
        probability_of_approach=0.25,
        expected_synergies_millions=400,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.50,
        reason_care="Precision oncology platform (synthetic lethality) fills Takeda pipeline gap.",
        reason_not_bid=(
            "Rights friction 0.70 — Servier/Pfizer/Gilead/GSK multi-partner structure "
            "requires extensive COC consent process. Could be deal-blocking."
        ),
        probability_top_bidder=0.15,
        notes="Rights complexity is primary deal risk; legal review must precede term sheet.",
    ),

    # --- Daiichi Sankyo pairs ---
    ("daiichi_sankyo", "a-nuvalent-zide"): _pair(
        "daiichi_sankyo", "a-nuvalent-zide",
        ta_fit=0.95, modality_fit=0.85,
        loe_gap_match=0.50, commercial_synergy=0.80,
        cmc_fit=0.90, rights_friction=0.05,
        asset_overlap=0.25, commercial_adjacency=0.90,
        antitrust_risk=0.25, affordability_ratio=1.10,
        strategic_urgency=0.75, right_to_win_score=0.60,
        probability_of_approach=0.35,
        expected_synergies_millions=900,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.55,
        reason_care=(
            "Nuvalent ROS1/ALK inhibitors complement DXd ADC portfolio in NSCLC. "
            "Combination potential (targeted kinase + ADC) is credible and synergistic."
        ),
        reason_not_bid=(
            "Asset overlap 0.25 — Daiichi's Merck collaboration spans NSCLC; "
            "antitrust and JDA consent from Merck may constrain."
        ),
        probability_top_bidder=0.22,
    ),

    # --- GSK pairs ---
    ("gsk", "a-vaxcyte-vax31"): _pair(
        "gsk", "a-vaxcyte-vax31",
        ta_fit=0.90, modality_fit=0.90,
        loe_gap_match=0.80, commercial_synergy=0.85,
        cmc_fit=0.65, rights_friction=0.35,
        asset_overlap=0.25, commercial_adjacency=0.85,
        antitrust_risk=0.40, affordability_ratio=1.0,
        strategic_urgency=0.75, right_to_win_score=0.55,
        probability_of_approach=0.30,
        expected_synergies_millions=1_000,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.45,
        reason_care=(
            "VAX-31 fills pneumococcal gap vs Pfizer Prevnar; Shingrix/Arexvy franchise "
            "proves GSK adult vaccine commercial infrastructure."
        ),
        reason_not_bid=(
            "Antitrust risk 0.40 — significant pneumococcal overlap; Sutro license COC. "
            "Vaxcyte seller willingness is low (standalone build)."
        ),
        probability_top_bidder=0.20,
    ),

    # --- AstraZeneca pairs ---
    ("astrazeneca", "a-cytk-aficamten"): _pair(
        "astrazeneca", "a-cytk-aficamten",
        ta_fit=0.85, modality_fit=0.90,
        loe_gap_match=0.60, commercial_synergy=0.80,
        cmc_fit=0.90, rights_friction=0.05,
        asset_overlap=0.05, commercial_adjacency=0.80,
        antitrust_risk=0.05, affordability_ratio=1.20,
        strategic_urgency=0.65, right_to_win_score=0.65,
        probability_of_approach=0.35,
        expected_synergies_millions=700,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.50,
        reason_care=(
            "Aficamten HCM fits AZ's CVRM franchise (Farxiga, Brilinta); "
            "cardiac muscle biology is differentiated from existing mechanisms."
        ),
        reason_not_bid="Competing CVRM pipeline investments (ticagrelor sequel programs); timing.",
        probability_top_bidder=0.30,
    ),

    # --- Pfizer pairs ---
    ("pfizer", "a-vaxcyte-vax31"): _pair(
        "pfizer", "a-vaxcyte-vax31",
        ta_fit=0.90, modality_fit=0.90,
        loe_gap_match=0.85, commercial_synergy=0.70,
        cmc_fit=0.65, rights_friction=0.35,
        asset_overlap=0.50, commercial_adjacency=0.75,
        antitrust_risk=0.70, affordability_ratio=1.30,
        strategic_urgency=0.60, right_to_win_score=0.35,
        probability_of_approach=0.20,
        expected_synergies_millions=800,
        management_relationship_history="no_prior_contact",
        likely_premium_pct=0.40,
        reason_care="Prevnar franchise defense; VAX-31 broader coverage could obsolete PCV20.",
        reason_not_bid=(
            "Antitrust risk 0.70 — Pfizer + Vaxcyte = near-monopoly in pneumococcal vaccines. "
            "FTC would likely require Prevnar divestiture. Economic case collapses."
        ),
        probability_top_bidder=0.08,
        notes="Antitrust risk likely prohibitive; Pfizer more likely as blocker bid than winner.",
    ),
}


# ===========================================================================
# Helper functions
# ===========================================================================

def get_pairs_for_target(target_asset_id: str) -> list[AcquirerTargetPair]:
    """Return all pair records for a given target asset."""
    return [p for (_, tid), p in PAIR_TABLE.items() if tid == target_asset_id]


def get_pairs_for_acquirer(acquirer_id: str) -> list[AcquirerTargetPair]:
    """Return all pair records for a given acquirer."""
    return [p for (aid, _), p in PAIR_TABLE.items() if aid == acquirer_id]


# Combined universe (v1 + mna_universe new acquirers + registry new acquirers)
FULL_ACQUIRER_UNIVERSE: list[AcquirerProfile] = (
    ACQUIRER_UNIVERSE + NEW_ACQUIRERS + ALL_NEW_ACQUIRERS
)

ACQUIRER_BY_ID_V2: dict[str, AcquirerProfile] = {
    a.company_id: a for a in FULL_ACQUIRER_UNIVERSE
}

TARGET_BY_ASSET_ID: dict[str, AcquirableTarget] = {
    t.asset_id: t for t in TARGET_UNIVERSE_V2
}

# ---------------------------------------------------------------------------
# ACQUIRER_UNIVERSE_V2 — category-keyed dict of all acquirer profiles
# ---------------------------------------------------------------------------
ACQUIRER_UNIVERSE_V2: dict[str, list[AcquirerProfile]] = {
    # v1 core acquirers (Pfizer, LLY, Merck, AZ, BMS, Novartis, Roche, AbbVie, Amgen, Gilead)
    "mega_cap_core": ACQUIRER_UNIVERSE,
    # mna_universe additions (JNJ, Sanofi, GSK, Novo Nordisk, Takeda, Daiichi Sankyo, UCB)
    "mega_cap_v2": NEW_ACQUIRERS,
    # acquirer_registry Phase 1 (Vertex, Regeneron, Bayer, Boehringer, Astellas, Eisai,
    #                             Otsuka, Chugai, CSL)
    "mega_cap_v3": MEGA_CAP_ACQUIRERS_V2,
    # acquirer_registry Phase 2a (Biogen, Moderna, Alnylam, Sarepta, BioMarin,
    #                              United Therapeutics, Jazz, Ipsen, Galapagos,
    #                              Ascendis, Legend Biotech)
    "large_biotech": LARGE_BIOTECH_ACQUIRERS,
    # acquirer_registry Phase 2b (BeiGene, Hengrui, Innovent, Akeso, Hansoh,
    #                              CSPC, Sino Biopharm)
    "china_pharma": CHINA_PHARMA_ACQUIRERS,
    # acquirer_registry_specialty (BioNTech, Ionis, Incyte, Neurocrine, Sobi,
    #                               Grifols, argenx, Genmab)
    "specialty_biotech": SPECIALTY_ACQUIRERS,
}

# Flat list of all unique acquirers (deduped by company_id)
_seen_acquirer_ids: set[str] = set()
ALL_ACQUIRERS: list[AcquirerProfile] = []
for _cat_list in ACQUIRER_UNIVERSE_V2.values():
    for _acq in _cat_list:
        if _acq.company_id not in _seen_acquirer_ids:
            _seen_acquirer_ids.add(_acq.company_id)
            ALL_ACQUIRERS.append(_acq)

ACQUIRER_BY_ID_FULL: dict[str, AcquirerProfile] = {
    a.company_id: a for a in ALL_ACQUIRERS
}


# ---------------------------------------------------------------------------
# Re-export target registry V3 at module level for unified imports
# ---------------------------------------------------------------------------
# TARGET_UNIVERSE_V3   — dict[category, list[WatchlistTarget]]  (from target_registry.py)
# ALL_TARGETS          — flat list of all WatchlistTargets
# TARGET_BY_TICKER     — dict[ticker, WatchlistTarget]
# STRATEGIC_BIOTECH_HYBRIDS — tickers excluded from buy-side shortlists
#
# These are already imported above; re-export via __all__ or direct reference.
__all__ = [
    # acquirer exports
    "NEW_ACQUIRERS", "HYBRID_UNIVERSE", "FULL_ACQUIRER_UNIVERSE",
    "ACQUIRER_BY_ID_V2", "ACQUIRER_BY_ID_FULL",
    "ACQUIRER_UNIVERSE_V2", "ALL_ACQUIRERS",
    # target exports (v2 — AcquirableTarget full profiles)
    "TARGET_UNIVERSE_V2", "TARGET_BY_ASSET_ID",
    # target exports (v3 — WatchlistTarget expanded universe)
    "TARGET_UNIVERSE_V3", "ALL_TARGETS", "TARGET_BY_TICKER", "TARGET_BY_ASSET_ID_V3",
    "STRATEGIC_BIOTECH_HYBRIDS",
    # pair table
    "PAIR_TABLE", "PRECEDENT_REGISTRY", "ASIA_REGISTRY", "TOOLS_CDMO_REGISTRY",
    # helpers
    "get_pairs_for_target", "get_pairs_for_acquirer",
    "category_summary", "top_mna_targets",
]

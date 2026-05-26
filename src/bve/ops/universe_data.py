"""
Universe definition — enriched 27-asset watchlist.

Extracted from weekly_runner.py to keep file sizes manageable.
Import: ``from bve.ops.universe_data import UNIVERSE``

Each entry extends the base 10-field format with:
  - company_name, exchange, country, region
  - company_type  ("target" | "strategic_hybrid")
  - target_type   ("target" | "strategic_hybrid")
  - market_cap_millions, cash_millions
  - top_5_likely_acquirers  (list[str] of acquirer ticker IDs)
  - mna_relevance_score     (0–1; higher = more actionable M&A candidate)
  - data_confidence_score   (0–1; how complete/sourced the profile is)
  - executive_view          (analyst note on deal thesis)
"""
from __future__ import annotations

from bve.intelligence.thesis_tracker import ClaimType

UNIVERSE: list[dict] = [
    # ------------------------------------------------------------------
    # Strategic hybrids — large enough to be acquirers themselves but
    # also plausible acquisition targets for mega-cap pharma.
    # ------------------------------------------------------------------
    dict(
        ticker="VRTX",
        company_id="co-vrtx",
        asset_id="a-vrtx",
        indication="CF / pain / APOL1",
        ranking_score=0.58,
        opportunity_score=0.55,
        conviction="medium",
        catalyst="VX-548 NDA decision + non-opioid pain label expansion",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Pipeline PoS > market-implied; VX-548 label expansion underpriced",
        # --- enriched fields ---
        company_name="Vertex Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=115_000,
        cash_millions=11_000,
        top_5_likely_acquirers=["PFE", "MRK", "ABBV", "NVS", "RHHBY"],
        mna_relevance_score=0.55,
        data_confidence_score=0.85,
        executive_view=(
            "Best-in-class CF monopoly (>90% market share) with a strong adjacent pipeline "
            "in pain (VX-548), APOL1 kidney disease, and type 1 diabetes. At ~$115B market cap "
            "only mega-cap pharma can afford a full acquisition; more likely to remain an "
            "independent acquirer. Strategic acquirers would pay ~35-50% premium = $155-172B deal."
        ),
    ),
    dict(
        ticker="REGN",
        company_id="co-regn",
        asset_id="a-regn",
        indication="oncology / immunology / eye",
        ranking_score=0.52,
        opportunity_score=0.40,
        conviction="medium",
        catalyst="Dupixent label expansions; EYLEA HD biosimilar competition",
        claim_type=ClaimType.COMPETITOR_FAILURE,
        claim_assertion="EYLEA biosimilar penetration slower than feared; pricing holds",
        # --- enriched fields ---
        company_name="Regeneron Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=65_000,
        cash_millions=17_000,
        top_5_likely_acquirers=["PFE", "AZN", "MRK", "NVS", "RHHBY"],
        mna_relevance_score=0.58,
        data_confidence_score=0.82,
        executive_view=(
            "Dupixent (~$14B peak revenue) + antibody discovery platform (VelociSuite) make "
            "REGN a highly desirable acquisition. Sanofi collaboration on Dupixent complicates "
            "deal structure. Cash-rich ($17B) with buyback optionality. EYLEA HD biosimilar risk "
            "is the near-term overhang. Roche/Sanofi/Pfizer each have strategic rationale."
        ),
    ),
    dict(
        ticker="LLY",
        company_id="co-lly",
        asset_id="a-lly",
        indication="obesity / diabetes / Alzheimer's",
        ranking_score=0.45,
        opportunity_score=0.28,
        conviction="medium",
        catalyst="Zepbound share vs semaglutide; orforglipron oral data",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="GLP-1 dominance persists but expectations leave little upside",
        # --- enriched fields ---
        company_name="Eli Lilly and Company",
        exchange="NYSE",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=900_000,
        cash_millions=5_282,
        top_5_likely_acquirers=[],          # effectively unacquirable at this size
        mna_relevance_score=0.10,
        data_confidence_score=0.90,
        executive_view=(
            "GLP-1 dominant franchise (tirzepatide) with orforglipron oral optionality. "
            "Essentially unacquirable at $900B market cap — included as a strategic-hybrid "
            "reference point; LLY is more relevant as an acquirer than an acquiree. "
            "Watch for bolt-on acquisitions in obesity pipeline adjacencies."
        ),
    ),
    dict(
        ticker="ALNY",
        company_id="co-alny",
        asset_id="a-alny",
        indication="RNAi — TTR / hypertension / NASH",
        ranking_score=0.72,
        opportunity_score=0.70,
        conviction="medium-high",
        catalyst="Alnylam zilebesiran Ph3 KARDIA-2 readout; vutrisiran label expansion",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Zilebesiran meets primary BP endpoint in KARDIA-2",
        # --- enriched fields ---
        company_name="Alnylam Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=30_000,
        cash_millions=3_000,
        top_5_likely_acquirers=["NVS", "RHHBY", "MRK", "AZN", "PFE"],
        mna_relevance_score=0.75,
        data_confidence_score=0.88,
        executive_view=(
            "Global RNAi platform leader with three marketed products (onpattro, givlaari, vutrisiran) "
            "and a cardiometabolic pipeline catalyst in zilebesiran (hypertension). Novartis has the "
            "strongest strategic rationale (Leqvio RNAi franchise + cardiovascular TA priority). "
            "A zilebesiran Ph3 win would accelerate premium offers. Acquirable at $30B for mega-pharma."
        ),
    ),
    dict(
        ticker="MRNA",
        company_id="co-mrna",
        asset_id="a-mrna",
        indication="mRNA — flu / RSV / cancer vaccines",
        ranking_score=0.50,
        opportunity_score=0.52,
        conviction="medium",
        catalyst="mRNA-1283 next-gen COVID/flu combo Ph3; individualized cancer vaccine Ph3",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="mRNA-4157 (ICV) meets RFS endpoint in KEYNOTE-942 registrational",
        # --- enriched fields ---
        company_name="Moderna",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=14_000,
        cash_millions=6_500,
        top_5_likely_acquirers=["MRK", "PFE", "AZN", "NVS", "RHHBY"],
        mna_relevance_score=0.50,
        data_confidence_score=0.80,
        executive_view=(
            "mRNA platform leader post-COVID with elevated cash burn as COVID revenue collapses. "
            "mRNA-4157 individualized cancer vaccine (with Merck/KEYTRUDA) is the near-term inflection. "
            "Platform (manufacturing scale, LNP IP) is strategically valuable independent of pipeline. "
            "At $14B market cap with $6.5B cash, platform acquisition is feasible for large pharma."
        ),
    ),
    dict(
        ticker="BMRN",
        company_id="co-bmrn",
        asset_id="a-bmrn",
        indication="rare disease — PKU / hemophilia / achondroplasia",
        ranking_score=0.54,
        opportunity_score=0.50,
        conviction="medium",
        catalyst="Roctavian haemophilia A label durability data; BMN 333 achondroplasia Ph3",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Roctavian durability holds at 3-year follow-up; no label change needed",
        # --- enriched fields ---
        company_name="BioMarin Pharmaceutical",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=13_000,
        cash_millions=1_500,
        top_5_likely_acquirers=["RHHBY", "NVS", "ABBV", "AZN", "MRK"],
        mna_relevance_score=0.58,
        data_confidence_score=0.78,
        executive_view=(
            "Established rare disease franchise across PKU (Palynziq), hemophilia A (Roctavian), "
            "and achondroplasia (Voxzogo). Roctavian durability is the key risk overhang. "
            "Roche/Genentech has the strongest TA fit across all three franchises. "
            "Premium of 30-50% to current market cap = $17-20B total deal value."
        ),
    ),
    # ------------------------------------------------------------------
    # Core targets — active, catalyst-driven, high-conviction M&A angle
    # ------------------------------------------------------------------
    dict(
        ticker="CRSP",
        company_id="co-crsp",
        asset_id="a-crsp",
        indication="SCD / beta-thal / diabetes",
        ranking_score=0.55,
        opportunity_score=0.58,
        conviction="medium",
        catalyst="Casgevy commercial uptake trajectory; CTX310 IND data",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Casgevy treatment center activation on pace with 12-month guidance",
        # --- enriched fields ---
        company_name="CRISPR Therapeutics AG",
        exchange="NASDAQ",
        country="CH",
        region="Europe",
        company_type="target",
        target_type="target",
        market_cap_millions=5_000,
        cash_millions=2_000,
        top_5_likely_acquirers=["VRTX", "NVS", "PFE", "RHHBY", "MRK"],
        mna_relevance_score=0.68,
        data_confidence_score=0.75,
        executive_view=(
            "First approved CRISPR therapy (Casgevy, co-developed with Vertex). Vertex has ROFR "
            "on co-developed assets — a full acquisition would consolidate the CF/sickle cell "
            "gene editing franchise. At $5B market cap, acquirable for mid-large pharma. "
            "CTX310 (in vivo lipid targeting) could be transformative if IND data is positive."
        ),
    ),
    dict(
        ticker="NTLA",
        company_id="co-ntla",
        asset_id="a-ntla",
        indication="in vivo gene editing — ATTR / HAE",
        ranking_score=0.62,
        opportunity_score=0.65,
        conviction="medium",
        catalyst="NTLA-2001 Ph1 durability data; NTLA-2002 HAE Ph3 start",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="NTLA-2001 durable TTR reduction at 12-month follow-up",
        # --- enriched fields ---
        company_name="Intellia Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_500,
        cash_millions=900,
        top_5_likely_acquirers=["RHHBY", "NVS", "ABBV", "MRK", "PFE"],
        mna_relevance_score=0.70,
        data_confidence_score=0.72,
        executive_view=(
            "In vivo gene editing leader addressing ATTR (competing with Alnylam) and HAE. "
            "Roche/Genentech partnership provides validation but creates strategic tension. "
            "Cash constrained; M&A accelerant if NTLA-2001 12-month durability holds. "
            "At $2.5B, highly acquirable — Roche or Novartis most likely given platform fit."
        ),
    ),
    dict(
        ticker="BEAM",
        company_id="co-beam",
        asset_id="a-beam",
        indication="base editing — SCD / AML / immunology",
        ranking_score=0.42,
        opportunity_score=0.48,
        conviction="low-medium",
        catalyst="BEAM-101 SCD Ph1/2 initial efficacy; BEAM-201 AML IND",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="BEAM-101 achieves HbF induction with clean safety at 6 months",
        # --- enriched fields ---
        company_name="Beam Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=1_200,
        cash_millions=500,
        top_5_likely_acquirers=["NVS", "RHHBY", "AMGN", "ABBV", "PFE"],
        mna_relevance_score=0.55,
        data_confidence_score=0.65,
        executive_view=(
            "Base editing pioneer with single-base precision advantage over CRISPR/nickase methods. "
            "Earlier-stage than CRSP/NTLA — clinical proof-of-concept still pending on BEAM-101. "
            "Platform (A-to-I and C-to-T editing) is differentiated; acquirer would be buying "
            "the technology. At $1.2B, lowest-cost entry point for a gene-editing platform play."
        ),
    ),
    dict(
        ticker="SRPT",
        company_id="co-srpt",
        asset_id="a-srpt",
        indication="DMD gene therapy",
        ranking_score=0.68,
        opportunity_score=0.75,
        conviction="medium-high",
        catalyst="Elevidys full approval confirmation; SRP-9003 (LGMD2E) Ph3 data",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Elevidys receives broad label conversion (not restricted to ambulatory)",
        # --- enriched fields ---
        company_name="Sarepta Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=8_000,
        cash_millions=1_500,
        top_5_likely_acquirers=["RHHBY", "PFE", "NVS", "AMGN", "AZN"],
        mna_relevance_score=0.72,
        data_confidence_score=0.80,
        executive_view=(
            "Elevidys (micro-dystrophin AAV gene therapy) is the first approved DMD gene therapy — "
            "a rare disease moat that is difficult to replicate. Roche partnership provides gene therapy "
            "manufacturing and commercial infrastructure; acquisition would consolidate the franchise. "
            "At $8B, attainable for mid-large pharma. SRP-9003 (LGMD) extends the platform optionality."
        ),
    ),
    dict(
        ticker="VKTX",
        company_id="co-vktx",
        asset_id="a-vktx",
        indication="obesity / NASH",
        ranking_score=0.70,
        opportunity_score=0.78,
        conviction="medium-high",
        catalyst="VK2735 oral Ph2 readout; subcutaneous Ph3 enrollment completion",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="VK2735 oral meets >10% weight loss primary endpoint in Ph2",
        # --- enriched fields ---
        company_name="Viking Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=4_000,
        cash_millions=900,
        top_5_likely_acquirers=["LLY", "NVS", "AZN", "PFE", "RHHBY"],
        mna_relevance_score=0.80,
        data_confidence_score=0.82,
        executive_view=(
            "Best-in-class GLP-1/GIP dual agonist (VK2735) with oral formulation optionality — "
            "a direct competitive threat to Lilly tirzepatide and Novo semaglutide. No marketed "
            "product makes this a clean acquisition. Oral Ph2 readout is the primary catalyst; "
            "positive data = immediate premium offer from LLY or NVS to prevent erosion of franchise."
        ),
    ),
    dict(
        ticker="RXRX",
        company_id="co-rxrx",
        asset_id="a-rxrx",
        indication="AI-enabled rare disease / oncology",
        ranking_score=0.38,
        opportunity_score=0.42,
        conviction="low-medium",
        catalyst="First AI-generated IND → Ph1 data; Recursion-Nvidia compute milestones",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="At least one Recursion-originated compound reaches Ph1 dose escalation",
        # --- enriched fields ---
        company_name="Recursion Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_000,
        cash_millions=600,
        top_5_likely_acquirers=["RHHBY", "NVS", "AZN", "MRK", "PFE"],
        mna_relevance_score=0.40,
        data_confidence_score=0.60,
        executive_view=(
            "AI-first drug discovery platform; Nvidia partnership validates compute infrastructure. "
            "Clinical proof-of-concept for AI-generated compounds still pending. Strategic value "
            "is the biological dataset and ML infrastructure, not near-term pipeline. Acquirer "
            "would need conviction on AI-enabled discovery; Roche/NVS most likely given platform M&A history."
        ),
    ),
    dict(
        ticker="KYMR",
        company_id="co-kymr",
        asset_id="a-kymr",
        indication="protein degradation — STAT6 / IRAKIMiD / MDM2",
        ranking_score=0.65,
        opportunity_score=0.68,
        conviction="medium-high",
        catalyst="KT-474 STAT6 degrader Ph2 atopic derm readout; KT-333 STAT3 lymphoma data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="KT-474 achieves ≥50% EASI reduction vs placebo in Ph2 atopic derm",
        # --- enriched fields ---
        company_name="Kymera Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_500,
        cash_millions=800,
        top_5_likely_acquirers=["ABBV", "AZN", "PFE", "MRK", "RHHBY"],
        mna_relevance_score=0.65,
        data_confidence_score=0.70,
        executive_view=(
            "Targeted protein degradation pioneer with STAT6 (atopic derm), STAT3 (lymphoma), "
            "and MDM2 (AML) programs. AZ has strong interest in TPD modality. "
            "KT-474 Ph2 atopic derm data is the acquisition trigger — ABBV (dupilumab competitor) "
            "and AZ (immunology focus) are most motivated. At $2.5B, digestible for any large pharma."
        ),
    ),
    dict(
        ticker="ARVN",
        company_id="co-arvn",
        asset_id="a-arvn",
        indication="PROTAC protein degradation — ER+ breast cancer / AR prostate cancer",
        ranking_score=0.63,
        opportunity_score=0.66,
        conviction="medium-high",
        catalyst="ARV-471 VERITAC-2 Ph3 PFS readout in ER+/HER2- breast cancer",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="ARV-471 meets PFS primary endpoint in VERITAC-2 vs exemestane",
        # --- enriched fields ---
        company_name="Arvinas",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_200,
        cash_millions=700,
        top_5_likely_acquirers=["PFE", "AZN", "MRK", "BMY", "RHHBY"],
        mna_relevance_score=0.68,
        data_confidence_score=0.72,
        executive_view=(
            "PROTAC founder company with Pfizer partnership on ARV-471 (vepdegestrant). "
            "VERITAC-2 Ph3 PFS readout is a binary acquisition trigger. Pfizer partnership "
            "creates a natural acquisition pathway. Positive Ph3 = immediate premium offer; "
            "negative = distressed asset sale. AZ oncology focus provides a second buyer."
        ),
    ),
    dict(
        ticker="RVMD",
        company_id="co-rvmd",
        asset_id="a-rvmd",
        indication="RAS oncology — KRAS G12C/D, pan-RAS",
        ranking_score=0.61,
        opportunity_score=0.64,
        conviction="medium",
        catalyst="RMC-6236 pan-RAS Ph1/2 PDAC expansion cohort ORR; RMC-9805 KRAS G12D IND",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="RMC-6236 achieves ≥20% ORR in KRAS-mutant PDAC expansion cohort",
        # --- enriched fields ---
        company_name="Revolution Medicines",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=5_500,
        cash_millions=1_800,
        top_5_likely_acquirers=["MRK", "AZN", "AMGN", "RHHBY", "PFE"],
        mna_relevance_score=0.72,
        data_confidence_score=0.75,
        executive_view=(
            "Pan-RAS tri-complex inhibitor platform addressing the largest untapped oncology target. "
            "RMC-6236 PDAC data (>20% ORR) would be transformative in a disease with ~10% response "
            "to current chemotherapy. Amgen KRAS G12C (sotorasib) creates antitrust tension but also "
            "competitive motivation. AZ and MRK are most likely acquirers given KRAS franchise interest."
        ),
    ),
    dict(
        ticker="MDGL",
        company_id="co-mdgl",
        asset_id="a-mdgl",
        indication="NASH / MASH — resmetirom",
        ranking_score=0.60,
        opportunity_score=0.62,
        conviction="medium",
        catalyst="Rezdiffra (resmetirom) Rx uptake trajectory; label expansion to F2 fibrosis",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Rezdiffra achieves ≥40,000 prescriptions in first full year post-launch",
        # --- enriched fields ---
        company_name="Madrigal Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=5_500,
        cash_millions=1_400,
        top_5_likely_acquirers=["AZN", "NVS", "MRK", "RHHBY", "ABBV"],
        mna_relevance_score=0.65,
        data_confidence_score=0.78,
        executive_view=(
            "First and only approved MASH treatment (Rezdiffra, THR-β agonist). "
            "Launch trajectory and label expansion to F2 fibrosis are the near-term value drivers. "
            "AZ (MASH franchise with cotadutide) has the strongest strategic alignment. "
            "At $5.5B market cap, digestible for large pharma. $40B+ MASH market makes this strategic."
        ),
    ),
    dict(
        ticker="IMVT",
        company_id="co-imvt",
        asset_id="a-imvt",
        indication="FcRn — myasthenia gravis / thyroid eye disease / warm AIHA",
        ranking_score=0.56,
        opportunity_score=0.58,
        conviction="medium",
        catalyst="Batoclimab ASCEND+ Ph3 MG readout; nipocalimab competitive read-across",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Batoclimab meets MG-ADL responder rate ≥50% in ASCEND+ vs placebo",
        # --- enriched fields ---
        company_name="Immunovant",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_800,
        cash_millions=700,
        top_5_likely_acquirers=["ABBV", "AMGN", "AZN", "RHHBY", "MRK"],
        mna_relevance_score=0.62,
        data_confidence_score=0.70,
        executive_view=(
            "FcRn antagonist (batoclimab) targeting large autoimmune markets (MG, TED, warm AIHA). "
            "Competing with J&J nipocalimab and UCB rozanolixizumab in crowded FcRn space. "
            "Positive ASCEND+ MG readout would differentiate batoclimab and trigger acquisition offers. "
            "ABBV immunology franchise (adalimumab successor assets) provides strongest strategic fit."
        ),
    ),
    # ------------------------------------------------------------------
    # Tier B — speculative / earlier-stage targets
    # ------------------------------------------------------------------
    dict(
        ticker="FULC",
        company_id="co-fulc",
        asset_id="a-fulc",
        indication="rare muscle disease — FSHD / SMA",
        ranking_score=0.38,
        opportunity_score=0.36,
        conviction="low-medium",
        catalyst="Losmapimod Ph3 FSHD MRI/functional read; RO7204239 collaboration milestone",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Losmapimod Ph3 hits MRI fat fraction primary endpoint (p<0.05)",
        # --- enriched fields ---
        company_name="Fulcrum Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=350,
        cash_millions=200,
        top_5_likely_acquirers=["RHHBY", "NVS", "PFE", "AMGN", "SRPT"],
        mna_relevance_score=0.45,
        data_confidence_score=0.60,
        executive_view=(
            "Losmapimod (p38α/β inhibitor) in Ph3 for FSHD — a rare muscle disease with no "
            "approved therapy. Roche/Genentech FSHD research interest provides acquisition pathway. "
            "Cash constrained; acquisition decision driven purely by Ph3 MRI endpoint outcome. "
            "At $350M market cap, a distressed asset acquisition is possible even pre-data."
        ),
    ),
    dict(
        ticker="FATE",
        company_id="co-fate",
        asset_id="a-fate",
        indication="iPSC-derived NK / T-cell therapy — AML / myeloma",
        ranking_score=0.33,
        opportunity_score=0.30,
        conviction="low",
        catalyst="FT576 iPSC-NK myeloma Ph1 ORR update; partnership decision from J&J",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="FT576 achieves ≥30% ORR in RRMM monotherapy arm",
        # --- enriched fields ---
        company_name="Fate Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=400,
        cash_millions=250,
        top_5_likely_acquirers=["AMGN", "NVS", "AZN", "RHHBY", "PFE"],
        mna_relevance_score=0.38,
        data_confidence_score=0.58,
        executive_view=(
            "iPSC cell therapy pioneer with off-the-shelf NK and T-cell programs. "
            "J&J collaboration expiration created strategic uncertainty. Platform value "
            "(scalable, allogeneic cell manufacturing) exceeds near-term pipeline. "
            "Capital constrained; needs a strategic home. FT576 ORR in myeloma is the inflection point."
        ),
    ),
    dict(
        ticker="OCUL",
        company_id="co-ocul",
        asset_id="a-ocul",
        indication="rare retinal disease — LCA10 / RP",
        ranking_score=0.30,
        opportunity_score=0.28,
        conviction="low",
        catalyst="OCU400 (LCA10/RP) Ph2/3 best-corrected visual acuity data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="OCU400 shows ≥15-letter BCVA improvement in ≥40% of LCA10 patients",
        # --- enriched fields ---
        company_name="Ocugen",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=200,
        cash_millions=80,
        top_5_likely_acquirers=["NVS", "RHHBY", "AZN", "ABBV", "AMGN"],
        mna_relevance_score=0.35,
        data_confidence_score=0.55,
        executive_view=(
            "OCU400 (nuclear hormone receptor AAV gene therapy) for LCA10/RP rare retinal disease. "
            "Novartis/SPARK has precedent (Luxturna); retinal gene therapy acquisition is repeatable. "
            "Extremely small cap ($200M) with limited runway — acquisition is opportunistic and "
            "data-dependent. BCVA improvement data is the binary trigger."
        ),
    ),
    dict(
        ticker="SRRK",
        company_id="co-srrk",
        asset_id="a-srrk",
        indication="musculoskeletal — spinal muscular atrophy / cachexia",
        ranking_score=0.36,
        opportunity_score=0.34,
        conviction="low-medium",
        catalyst="Apitegromab TOPAZ Ph3 SMA motor function data; NDA readiness review",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Apitegromab meets HFMSE motor function endpoint at 12 months in TOPAZ",
        # --- enriched fields ---
        company_name="Scholar Rock Holding",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=700,
        cash_millions=400,
        top_5_likely_acquirers=["NVS", "RHHBY", "AZN", "AMGN", "PFE"],
        mna_relevance_score=0.50,
        data_confidence_score=0.65,
        executive_view=(
            "Apitegromab (GDF11/8 inhibitor) for SMA type 2/3 as add-on to nusinersen/risdiplam. "
            "TOPAZ Ph3 is the acquisition trigger. Biogen SMA franchise (nusinersen) creates "
            "competitive tension and potential acquirer interest. TGF-β family selectivity "
            "platform has applications in cachexia and muscle wasting beyond SMA."
        ),
    ),
    dict(
        ticker="IOVA",
        company_id="co-iova",
        asset_id="a-iova",
        indication="TIL therapy — melanoma / NSCLC / cervical",
        ranking_score=0.44,
        opportunity_score=0.40,
        conviction="low-medium",
        catalyst="Amtagvi commercial uptake trajectory; LN-145 NSCLC Ph2 expansion ORR",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Amtagvi treatment centers reach 50 sites by end of 2025; ramp holds",
        # --- enriched fields ---
        company_name="Iovance Biotherapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=1_500,
        cash_millions=500,
        top_5_likely_acquirers=["MRK", "BMY", "NVS", "AMGN", "RHHBY"],
        mna_relevance_score=0.58,
        data_confidence_score=0.68,
        executive_view=(
            "First commercial TIL (tumor-infiltrating lymphocyte) therapy (Amtagvi) for melanoma. "
            "Commercial ramp and treatment center activation are the key value drivers. "
            "Manufacturing scalability is both the primary risk and the moat. "
            "Merck (KEYTRUDA partner in combination studies) has strong strategic rationale. "
            "NSCLC expansion cohort ORR is the catalyst that would accelerate M&A interest."
        ),
    ),
    # ------------------------------------------------------------------
    # Tier C — known failures / distressed — stress-tests the filter
    # ------------------------------------------------------------------
    dict(
        ticker="NVAX",
        company_id="co-nvax",
        asset_id="a-nvax",
        indication="protein subunit vaccines — COVID / flu",
        ranking_score=0.22,
        opportunity_score=0.18,
        conviction="very-low",
        catalyst="COVID booster season share; Sanofi co-promotion milestone",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Nuvaxovid captures ≥5% of US COVID booster market in 2025 fall season",
        # --- enriched fields ---
        company_name="Novavax",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=1_000,
        cash_millions=700,
        top_5_likely_acquirers=["PFE", "MRK", "NVS", "RHHBY", "AZN"],
        mna_relevance_score=0.30,
        data_confidence_score=0.65,
        executive_view=(
            "Distressed COVID vaccine manufacturer. Sanofi partnership (Nuvaxovid promotion) "
            "provides a lifeline but not a growth story. Protein subunit platform is differentiated "
            "from mRNA but market share is minimal. Acquisition unlikely at current valuation trend; "
            "most likely outcome is continued partnership or asset licensing of nanoparticle VLP tech."
        ),
    ),
    dict(
        ticker="PRTA",
        company_id="co-prta",
        asset_id="a-prta",
        indication="neurodegenerative — Parkinson's / Alzheimer's (alpha-syn / tau / ATTR)",
        ranking_score=0.19,
        opportunity_score=0.16,
        conviction="very-low",
        catalyst="Prasinezumab (alpha-syn) Ph2b PADOVA extension; PRX012 ATTR-CM Ph1",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Prasinezumab slows motor progression in rapid-progressors in Ph2b extension",
        # --- enriched fields ---
        company_name="Prothena Corporation",
        exchange="NASDAQ",
        country="IE",
        region="Europe",
        company_type="target",
        target_type="target",
        market_cap_millions=500,
        cash_millions=350,
        top_5_likely_acquirers=["BMY", "ABBV", "MRK", "RHHBY", "NVS"],
        mna_relevance_score=0.40,
        data_confidence_score=0.60,
        executive_view=(
            "Neurodegenerative platform with alpha-syn (prasinezumab), tau, and ATTR-CM (PRX012) "
            "assets. Bristol Myers Squibb ATTR partnership on PRX012 provides validation and "
            "a natural acquisition pathway. Prasinezumab Parkinson's data is speculative. "
            "Asset-level deal (PRX012 acquisition) is more likely than a full company acquisition."
        ),
    ),
    dict(
        ticker="EDIT",
        company_id="co-edit",
        asset_id="a-edit",
        indication="CRISPR gene editing — SCD / LCA10 / AML",
        ranking_score=0.17,
        opportunity_score=0.14,
        conviction="very-low",
        catalyst="EDIT-301 SCD Ph1/2 durability data; cash runway / partnership decision",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="EDIT-301 achieves HbF induction sustaining HbS <30% at 12 months",
        # --- enriched fields ---
        company_name="Editas Medicine",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=300,
        cash_millions=200,
        top_5_likely_acquirers=["AMGN", "RHHBY", "NVS", "PFE", "ABBV"],
        mna_relevance_score=0.35,
        data_confidence_score=0.58,
        executive_view=(
            "CRISPR pioneer (MIT/Broad IP estate) facing patent disputes and clinical delays. "
            "EDIT-301 SCD program trails CRSP Casgevy (already approved). Cash constrained. "
            "Broad Institute IP has strategic value but licensing disputes cloud acquisition rationale. "
            "Most likely outcome: distressed asset sale of EDIT-301 IP or partnership, not full acquisition."
        ),
    ),
    dict(
        ticker="AMRN",
        company_id="co-amrn",
        asset_id="a-amrn",
        indication="cardiovascular — Vascepa (icosapentaenoic acid)",
        ranking_score=0.12,
        opportunity_score=0.10,
        conviction="very-low",
        catalyst="Vascepa patent challenge outcome; potential acquisition / licensing deal",
        claim_type=ClaimType.COMPETITOR_FAILURE,
        claim_assertion="Patent courts uphold Vascepa formulation claims, limiting generic entry",
        # --- enriched fields ---
        company_name="Amarin Corporation",
        exchange="NASDAQ",
        country="IE",
        region="Europe",
        company_type="target",
        target_type="target",
        market_cap_millions=350,
        cash_millions=150,
        top_5_likely_acquirers=["AZN", "PFE", "MRK", "ABBV", "AMGN"],
        mna_relevance_score=0.25,
        data_confidence_score=0.65,
        executive_view=(
            "Single-asset cardiovascular company (Vascepa/EPA) facing generic erosion after "
            "adverse patent rulings. REDUCE-IT outcomes data is the clinical anchor, but revenue "
            "declining. Acquirable at distressed valuation but strategic rationale is weak for "
            "large pharma. Possible niche cardiovascular acquirer or private equity roll-up."
        ),
    ),
    dict(
        ticker="ZYME",
        company_id="co-zyme",
        asset_id="a-zyme",
        indication="oncology — HER2 bispecific / ADC",
        ranking_score=0.28,
        opportunity_score=0.24,
        conviction="low",
        catalyst="Zanidatamab (HER2 bispecific) BLA FDA decision in biliary tract cancer",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Zanidatamab receives FDA approval in biliary tract cancer (BTC)",
        # --- enriched fields ---
        company_name="Zymeworks",
        exchange="NYSE",
        country="CA",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=700,
        cash_millions=400,
        top_5_likely_acquirers=["RHHBY", "AZN", "PFE", "AMGN", "BMY"],
        mna_relevance_score=0.55,
        data_confidence_score=0.68,
        executive_view=(
            "HER2 bispecific antibody (zanidatamab) BLA pending in biliary tract cancer — an "
            "orphan indication with high unmet need. BeiGene ex-US rights limit full deal structures. "
            "Bispecific antibody engineering platform (Azymetric) generates ADC + bispecific molecules. "
            "FDA approval would accelerate large pharma acquisition interest; Roche/AZ most likely given HER2 franchise."
        ),
    ),
    # ------------------------------------------------------------------
    # Wave 1 expansion — 13 active targets added 2026-05-25
    # Selected from universe_expanded_mna.yaml (116 assets screened)
    # Criteria: active independent public target, price data current,
    #           strong M&A thesis, high TA conviction
    # ------------------------------------------------------------------
    dict(
        ticker="IONS",
        company_id="co-ions",
        asset_id="a-ions",
        indication="antisense — TTR / SMA / Huntington / cardiometabolic",
        ranking_score=0.68,
        opportunity_score=0.65,
        conviction="medium-high",
        catalyst="Eplontersen ATTR-CM FDA submission; olezarsen ASCVD Ph3 readout; pelacarsen HORIZON readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Eplontersen achieves non-inferiority vs tafamidis in ATTR-CM primary composite",
        company_name="Ionis Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=7_500,
        cash_millions=2_200,
        top_5_likely_acquirers=["AZN", "AMGN", "NVS", "RHHBY", "LLY"],
        mna_relevance_score=0.62,
        data_confidence_score=0.82,
        executive_view=(
            "Antisense technology leader with the broadest late-stage pipeline in the space. "
            "AstraZeneca partnership (eplontersen/ATTR) is the most actionable acquisition trigger — "
            "AZ could acquire Ionis to secure full economics on an ATTR program poised to challenge tafamidis. "
            "At ~$7.5B market cap, a 40-50% premium ($10-11B) is within AZ/Novartis capacity."
        ),
    ),
    dict(
        ticker="BIIB",
        company_id="co-biib",
        asset_id="a-biib",
        indication="neurology — Alzheimer's / SMA / ALS / MS",
        ranking_score=0.60,
        opportunity_score=0.55,
        conviction="medium",
        catalyst="Lecanemab CLARITY-AD commercial uptake; ATLAS prevention trial enrollment; zuranolone launch",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Lecanemab achieves $1B+ annualized net revenue in first full commercial year",
        company_name="Biogen",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="strategic_hybrid",
        target_type="strategic_hybrid",
        market_cap_millions=28_000,
        cash_millions=4_500,
        top_5_likely_acquirers=["RHHBY", "NVS", "AZN", "PFE", "ABBV"],
        mna_relevance_score=0.48,
        data_confidence_score=0.88,
        executive_view=(
            "Lecanemab (partnered with Eisai) is the first amyloid-targeting therapy with consistent "
            "efficacy data. Biogen is in the unusual position of being both a large biotech and "
            "a potential acquisition target for mega-cap pharma seeking CNS leadership. At $28B market cap, "
            "an outright acquisition is difficult but not impossible for Roche or Novartis. "
            "More likely: asset-level partnership on lecanemab or zuranolone."
        ),
    ),
    dict(
        ticker="ACAD",
        company_id="co-acad",
        asset_id="a-acad",
        indication="CNS — Parkinson's psychosis / dementia-related psychosis / Rett syndrome",
        ranking_score=0.58,
        opportunity_score=0.60,
        conviction="medium",
        catalyst="Trofinetide (daybue) Rett syndrome commercial launch; pimavanserin label expansion readout",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Daybue captures >30% of eligible Rett patients within 24 months",
        company_name="Acadia Pharmaceuticals",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=3_200,
        cash_millions=900,
        top_5_likely_acquirers=["ABBV", "LLY", "ITCI_parent", "AZN", "NVS"],
        mna_relevance_score=0.65,
        data_confidence_score=0.78,
        executive_view=(
            "Two approved CNS assets (Nuplazid for PDP + Daybue for Rett syndrome) plus a pipeline, "
            "creating a rare disease CNS platform at a sub-$4B valuation. CNS consolidation thesis: "
            "large pharma (AbbVie post-Cerevel) seeking to build rare neurological disease portfolios. "
            "Rett syndrome is ultra-rare and recurring — high strategic value for a committed acquirer."
        ),
    ),
    dict(
        ticker="PTCT",
        company_id="co-ptct",
        asset_id="a-ptct",
        indication="rare disease — Duchenne muscular dystrophy / SMA / Friedreich's ataxia",
        ranking_score=0.62,
        opportunity_score=0.60,
        conviction="medium",
        catalyst="Translarna/ataluren durability data; SRK-015 (apitegromab) SMA data from Scholar Rock collaboration",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="PTC520 (vatiquinone) achieves primary endpoint in FA-2 Friedreich's ataxia Phase 3",
        company_name="PTC Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_400,
        cash_millions=700,
        top_5_likely_acquirers=["RHHBY", "NVS", "BIIB", "BMRN", "AZN"],
        mna_relevance_score=0.68,
        data_confidence_score=0.75,
        executive_view=(
            "Rare disease operator with multiple approved products (Translarna, Emflaza) and a deep "
            "neuromuscular pipeline. Vatiquinone (Friedreich's ataxia) is the near-term binary catalyst. "
            "BioMarin and Roche are natural acquirers given TA overlap. At <$2.5B, highly acquirable "
            "for a mid-large pharma building a rare disease platform."
        ),
    ),
    dict(
        ticker="PRAX",
        company_id="co-prax",
        asset_id="a-prax",
        indication="CNS — epilepsy / essential tremor",
        ranking_score=0.65,
        opportunity_score=0.68,
        conviction="medium",
        catalyst="PRAX-628 GABA-A potentiator Ph3 focal epilepsy readout; ulixacaltamide ET Ph3",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="PRAX-628 achieves ≥25% responder rate advantage vs placebo in focal epilepsy",
        company_name="Praxis Precision Medicine",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=1_800,
        cash_millions=600,
        top_5_likely_acquirers=["ABBV", "UCB", "LLY", "AZN", "PFE"],
        mna_relevance_score=0.72,
        data_confidence_score=0.70,
        executive_view=(
            "Precision CNS company with two late-stage readouts in 2025-2026 (epilepsy + essential tremor). "
            "PRAX-628 (GABA-A positive allosteric modulator) mechanism mirrors zuranolone but in a different "
            "CNS indication. UCB and AbbVie are the most natural buyers given Ion channel / CNS franchise alignment. "
            "Phase 3 success would likely trigger acquisition at 2-4x current market cap."
        ),
    ),
    dict(
        ticker="FOLD",
        company_id="co-fold",
        asset_id="a-fold",
        indication="rare disease — Pompe / Fabry / neuronal ceroid lipofuscinosis",
        ranking_score=0.62,
        opportunity_score=0.60,
        conviction="medium",
        catalyst="Pombiliti+opfolda (cipaglucosidase alfa+miglustat) Pompe COMET commercial launch uptake",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Pombiliti+opfolda captures >20% of late-onset Pompe patients within 18 months",
        company_name="Amicus Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_100,
        cash_millions=500,
        top_5_likely_acquirers=["RHHBY", "NVS", "AMGN", "AZN", "SNY"],
        mna_relevance_score=0.65,
        data_confidence_score=0.78,
        executive_view=(
            "Two approved products (Galafold for Fabry + Pombiliti/opfolda for Pompe) with recurring "
            "orphan disease revenue. Roche/Genentech acquired Spark Therapeutics for the gene therapy "
            "angle; Amicus fills the enzyme enhancement niche. Commercial ramp is the primary risk. "
            "A 40% premium would put the deal at ~$3B — manageable for Roche or Novartis."
        ),
    ),
    dict(
        ticker="GERN",
        company_id="co-gern",
        asset_id="a-gern",
        indication="hematology — myelodysplastic syndromes / myelofibrosis",
        ranking_score=0.60,
        opportunity_score=0.62,
        conviction="medium",
        catalyst="Imetelstat NDA/BLA filing for LR-MDS; FDA PDUFA date; commercial launch preparation",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Imetelstat receives FDA approval for low-risk MDS transfusion dependence",
        company_name="Geron Corporation",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=1_200,
        cash_millions=450,
        top_5_likely_acquirers=["ABBV", "NVS", "MRK", "SNY", "AZN"],
        mna_relevance_score=0.68,
        data_confidence_score=0.72,
        executive_view=(
            "Imetelstat (telomerase inhibitor) is the only clinical-stage telomerase inhibitor in oncology. "
            "If approved for LR-MDS, it fills a critical gap in transfusion-dependent patients who failed "
            "ESAs/luspatercept. At $1.2B market cap, highly acquirable. The FDA decision is the binary "
            "trigger — approval likely doubles or triples the stock and invites acquisition interest."
        ),
    ),
    dict(
        ticker="TGTX",
        company_id="co-tgtx",
        asset_id="a-tgtx",
        indication="hematology / oncology — CLL / NHL / multiple sclerosis",
        ranking_score=0.58,
        opportunity_score=0.55,
        conviction="medium",
        catalyst="Briumvi (ublituximab) MS commercial launch; umbralisib CLL combination data",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Briumvi captures >15% of high-efficacy MS market within 24 months",
        company_name="TG Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=2_000,
        cash_millions=550,
        top_5_likely_acquirers=["RHHBY", "NVS", "BIIB", "AZN", "ABBV"],
        mna_relevance_score=0.60,
        data_confidence_score=0.75,
        executive_view=(
            "Two-product hematology/oncology platform with Briumvi (approved MS) and TG-1601 pipeline. "
            "Anti-CD20 franchise in MS puts TG directly in competition with Biogen/Ocrevus and Roche. "
            "A large pharma seeking an anti-CD20 MS asset to compete with Ocrevus at lower price would "
            "find TG's platform attractive. Roche itself is an unlikely buyer given Ocrevus economics."
        ),
    ),
    dict(
        ticker="ANAB",
        company_id="co-anab",
        asset_id="a-anab",
        indication="immunology — atopic dermatitis / CSU / prurigo nodularis",
        ranking_score=0.55,
        opportunity_score=0.58,
        conviction="medium",
        catalyst="Imsidolimab (IL-36R) atopic dermatitis Ph3 readout; rosnilimab (PD-1 agonist) autoimmune",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Imsidolimab meets IGA 0/1 primary endpoint in moderate-to-severe AD Ph3",
        company_name="AnaptysBio",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=950,
        cash_millions=380,
        top_5_likely_acquirers=["ABBV", "LLY", "SNY", "AZN", "PFE"],
        mna_relevance_score=0.62,
        data_confidence_score=0.68,
        executive_view=(
            "Novel IL-36R mechanism (imsidolimab) addresses a distinct patient population from dupilumab "
            "in atopic dermatitis. Rosnilimab (PD-1 agonist — opposite of PD-1 inhibitors) is a novel "
            "immunology mechanism for autoimmune disease. If either Ph3 succeeds, AbbVie or Lilly "
            "(both with AD franchises) would be motivated buyers. Sub-$1B market cap makes it highly acquirable."
        ),
    ),
    dict(
        ticker="ARQT",
        company_id="co-arqt",
        asset_id="a-arqt",
        indication="dermatology — atopic dermatitis / rosacea / vitiligo",
        ranking_score=0.56,
        opportunity_score=0.54,
        conviction="medium",
        catalyst="Zoryve (roflumilast) foam/cream multi-indication commercial uptake; vitiligo Phase 3",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Zoryve achieves >$300M annualized revenue across approved indications",
        company_name="Arcutis Biotherapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=900,
        cash_millions=280,
        top_5_likely_acquirers=["ABBV", "LLY", "SNY", "PFE", "AZN"],
        mna_relevance_score=0.60,
        data_confidence_score=0.72,
        executive_view=(
            "Three approved dermatology products (Zoryve foam for scalp psoriasis, cream for plaque psoriasis, "
            "and roflumilast for seborrheic dermatitis) with a vitiligo Phase 3 in progress. "
            "AbbVie (Skyrizi dermatology franchise) or Leo Pharma are natural buyers. "
            "At ~$900M with multiple approved products, valuation is undemanding — acquisition at "
            "1.5-2.5x revenue run-rate is achievable."
        ),
    ),
    dict(
        ticker="AGEN",
        company_id="co-agen",
        asset_id="a-agen",
        indication="oncology — botensilimab (MSS CRC) / anti-TIGIT / bispecifics",
        ranking_score=0.52,
        opportunity_score=0.55,
        conviction="medium",
        catalyst="Botensilimab+balstilimab MSS CRC Ph2/3 regulatory strategy; mCRC NDA submission",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Botensilimab achieves >20% ORR in MSS CRC monotherapy Phase 2",
        company_name="Agenus Inc",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=550,
        cash_millions=180,
        top_5_likely_acquirers=["AZN", "MRK", "BMY", "RHHBY", "PFE"],
        mna_relevance_score=0.58,
        data_confidence_score=0.62,
        executive_view=(
            "Botensilimab (Fc-enhanced anti-CTLA-4) shows activity in MSS colorectal cancer, "
            "an immunologically cold tumor with virtually no approved IO options. If Ph2 data holds "
            "at NDA submission, this becomes the first immunotherapy in CRC — compelling for AZ or Merck "
            "to acquire as a complement to PD-1 franchise. Agenus is financially constrained, increasing "
            "acquisition likelihood."
        ),
    ),
    dict(
        ticker="TNGX",
        company_id="co-tngx",
        asset_id="a-tngx",
        indication="oncology — SMARCA2/4 degrader (MTAP-deletion / lung / GI)",
        ranking_score=0.52,
        opportunity_score=0.55,
        conviction="medium",
        catalyst="TNG260 SMARCA2 degrader Ph1 dose escalation data; KRAS G12C SHP2 combination cohort",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="TNG260 demonstrates tumor regression in SMARCA4-deficient NSCLC",
        company_name="Tango Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=600,
        cash_millions=220,
        top_5_likely_acquirers=["AZN", "BMY", "NVS", "RHHBY", "PFE"],
        mna_relevance_score=0.62,
        data_confidence_score=0.65,
        executive_view=(
            "SMARCA2/4 synthetic lethality platform (co-developed with AstraZeneca) addresses "
            "MTAP-deletion tumors — one of the largest unaddressed oncology patient populations. "
            "AZ co-development partnership reduces risk but also means AZ has first look at acquisition. "
            "If TNG260 shows anti-tumor activity in SMARCA4-deficient lung cancer, a full AZ "
            "acquisition or competing bid is highly probable at this $600M valuation."
        ),
    ),
    dict(
        ticker="RLAY",
        company_id="co-rlay",
        asset_id="a-rlay",
        indication="oncology — RAS-MAPK (KRAS/SHP2/RAF) pathway",
        ranking_score=0.50,
        opportunity_score=0.52,
        conviction="medium",
        catalyst="RLY-2608 allosteric PI3K-alpha Ph1/2 HR+/HER2- breast cancer; linifanib-class FGFR",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="RLY-2608 achieves confirmed PR in PI3K-mutant HR+ breast cancer",
        company_name="Relay Therapeutics",
        exchange="NASDAQ",
        country="US",
        region="North America",
        company_type="target",
        target_type="target",
        market_cap_millions=700,
        cash_millions=550,
        mna_relevance_score=0.58,
        data_confidence_score=0.70,
        top_5_likely_acquirers=["RHHBY", "NVS", "AZN", "PFE", "LLY"],
        executive_view=(
            "Computational drug design platform targeting allosteric sites in historically undruggable "
            "oncology drivers. RLY-2608 (allosteric PI3K-alpha) could displace alpelisib in the "
            "HR+/HER2- breast cancer space with a cleaner tolerability profile. At $700M (~$550M cash), "
            "the platform is essentially being acquired free. Ph2 confirmation data is the binary trigger."
        ),
    ),
]

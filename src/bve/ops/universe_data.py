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

    # ------------------------------------------------------------------
    # Wave 2 additions — active M&A monitor targets (no acquirer yet)
    # ------------------------------------------------------------------
    dict(
        ticker="ARGX", company_id="co-argx", asset_id="a-argx",
        indication="immunology — FcRn (efgartigimod) / C2 complement (ARGX-117)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Efgartigimod SC label expansions + ARGX-117 Ph2 CIDP readout",
        claim_type=ClaimType.LABEL_EXPANSION,
        claim_assertion="Efgartigimod gains ≥2 additional autoimmune indications by 2026",
        company_name="Argenx SE", exchange="NASDAQ", country="BE",
        region="Europe", company_type="strategic_hybrid", target_type="strategic_hybrid",
        market_cap_millions=28_000, cash_millions=4_500,
        top_5_likely_acquirers=["ABBV", "RHHBY", "PFE", "AZN", "JNJ"],
        mna_relevance_score=0.55, data_confidence_score=0.80,
        executive_view=(
            "FcRn platform leader with efgartigimod (gMG, CIDP, ITP) building a multi-indication "
            "franchise. At $28B market cap sits at the threshold for large-cap pharma acquisition. "
            "AbbVie (post-Humira patent cliff), Pfizer, and Roche are natural suitors for a scalable "
            "autoimmune franchise. ARGX-117 (C2 complement) in CIDP is the next catalyst."
        ),
    ),
    dict(
        ticker="ARWR", company_id="co-arwr", asset_id="a-arwr",
        indication="RNAi — cardiometabolic / NASH / rare pulmonary",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="ARO-APOC3 / ARO-ANG3 Ph3 cardiovascular outcomes readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="ARO-APOC3 achieves ≥50% TG reduction with CV outcomes signal",
        company_name="Arrowhead Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_200, cash_millions=600,
        top_5_likely_acquirers=["JNJ", "NVS", "RHHBY", "AZN", "MRK"],
        mna_relevance_score=0.62, data_confidence_score=0.70,
        executive_view=(
            "Broad subcutaneous RNAi platform with TRiM (Targeted RNAi Molecule) delivery across "
            "liver, lung, and muscle. J&J partnership (JNJ-75220795/ARO-JNJ1) validates platform; "
            "ARO-APOC3 and ARO-ANG3 are cardiometabolic shots on goal. At ~$2B market cap with "
            "multiple Ph3 assets, highly acquirable. Amgen or Novartis most likely."
        ),
    ),
    dict(
        ticker="BBIO", company_id="co-bbio", asset_id="a-bbio",
        indication="rare cardiovascular — acoramidis (ATTR-CM) / BBP-418 (LGMD2I)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Acoramidis ATTRibute-CM 30-month outcomes + NDA decision",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Acoramidis meets ATTRibute-CM composite CV endpoint at 30 months",
        company_name="BridgeBio Pharma", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=5_500, cash_millions=800,
        top_5_likely_acquirers=["PFE", "AZN", "NVS", "RHHBY", "JNJ"],
        mna_relevance_score=0.65, data_confidence_score=0.78,
        executive_view=(
            "Acoramidis (small molecule ATTR stabilizer) directly competes with Pfizer's tafamidis "
            "($3B/yr). ATTRibute-CM showed superior stabilisation vs tafamidis on TTR stabilisation "
            "endpoint. BridgeBio at $5.5B is an attractive bolt-on for AZ, Novartis, or Pfizer to "
            "capture or neutralise the ATTR market. BBP-418 (LGMD2I) adds rare disease upside."
        ),
    ),
    dict(
        ticker="BLUE", company_id="co-blue", asset_id="a-blue",
        indication="gene therapy — lovotibeglogene (SCD) / betibeglogene (beta-thal)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Lyfgenia (lovotibeglogene) commercial ramp + payer coverage decisions",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Lyfgenia achieves ≥200 commercial patients treated in first 12 months",
        company_name="bluebird bio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=350, cash_millions=200,
        top_5_likely_acquirers=["NVS", "RHHBY", "AMGN", "PFE", "JNJ"],
        mna_relevance_score=0.42, data_confidence_score=0.60,
        executive_view=(
            "Two approved gene therapies (Lyfgenia for SCD, Zynteglo for beta-thal) with commercial "
            "ramp challenged by high one-time pricing ($2.8-3.1M) and limited payer access. Very small "
            "market cap ($350M) and cash burn make this a distressed acquisition candidate. Novartis "
            "(Zolgensma) or Roche/Spark would most logically consolidate the hemoglobinopathy space."
        ),
    ),
    dict(
        ticker="ESPR", company_id="co-espr", asset_id="a-espr",
        indication="cardiovascular — bempedoic acid (NEXLETOL/NEXLIZET)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="CLEAR Outcomes post-hoc data + HF prevention label expansion filing",
        claim_type=ClaimType.LABEL_EXPANSION,
        claim_assertion="Bempedoic acid gains cardiovascular outcomes label from CLEAR Outcomes data",
        company_name="Esperion Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=350, cash_millions=120,
        top_5_likely_acquirers=["AZN", "NVS", "PFE", "AMGN", "MRK"],
        mna_relevance_score=0.50, data_confidence_score=0.65,
        executive_view=(
            "Bempedoic acid is the only oral LDL-lowering option for statin-intolerant patients with "
            "CV outcomes data (CLEAR: 13% MACE reduction). At $350M market cap with royalty-bearing "
            "commercial partnership with Daiichi Sankyo in EU, this is a cheap bolt-on for a large "
            "pharma seeking LDL franchise diversification beyond PCSK9."
        ),
    ),
    dict(
        ticker="GPCR", company_id="co-gpcr", asset_id="a-gpcr",
        indication="obesity/metabolic — GSBR-1290 (oral GLP-1R agonist)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="GSBR-1290 Ph2 weight loss and GI tolerability data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="GSBR-1290 achieves ≥12% placebo-adjusted weight loss at 26 weeks with GI advantage",
        company_name="Structure Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_200, cash_millions=400,
        top_5_likely_acquirers=["LLY", "NVO", "AZN", "PFE", "RHHBY"],
        mna_relevance_score=0.72, data_confidence_score=0.68,
        executive_view=(
            "Oral GLP-1R agonist in the most competitive therapeutic race in pharma history (obesity). "
            "Differentiation thesis: once-daily oral with better GI tolerability than semaglutide. "
            "At $1.2B market cap, structure is acquirable by Novo/Lilly/AZ to hedge their GLP-1 "
            "oral pipeline. Ph2 data is binary — success triggers acquisition, failure is existential."
        ),
    ),
    dict(
        ticker="IMCR", company_id="co-imcr", asset_id="a-imcr",
        indication="oncology — tebentafusp (uveal melanoma) / ImmTAC platform",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Tebentafusp OS data update + next ImmTAC molecule Ph1 readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Tebentafusp maintains OS benefit >2 years with durable responder tail",
        company_name="Immunocore Holdings", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_800, cash_millions=500,
        top_5_likely_acquirers=["RHHBY", "AZN", "MRK", "BMY", "NVS"],
        mna_relevance_score=0.60, data_confidence_score=0.72,
        executive_view=(
            "First approved T-cell receptor bispecific (tebentafusp) for uveal melanoma — a rare "
            "cancer with no prior approved therapy and median OS improvement of 4+ months. ImmTAC "
            "platform (TCR × CD3 bispecifics) could unlock solid tumor targets historically "
            "inaccessible to antibody-based approaches. Roche or AZ acquisition most logical."
        ),
    ),
    dict(
        ticker="ITOS", company_id="co-itos", asset_id="a-itos",
        indication="oncology — EOS-448 (TIGIT) / inupadenant (A2A/A2B adenosine)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="EOS-448 + pembrolizumab combination Ph2 cervical/endometrial readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="EOS-448 combination achieves ≥35% ORR in PD-1 refractory cervical cancer",
        company_name="iTeos Therapeutics", exchange="NASDAQ", country="BE",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=700, cash_millions=350,
        top_5_likely_acquirers=["GSK", "BMY", "MRK", "RHHBY", "AZN"],
        mna_relevance_score=0.55, data_confidence_score=0.65,
        executive_view=(
            "GSK partnership (EOS-448/GSK4428859A) validates TIGIT approach with $625M milestone deal. "
            "inupadenant (A2A/A2B) targets adenosine pathway — orthogonal to PD-1/CTLA-4. At $700M "
            "with $350M cash and a large-pharma partner already embedded, acquisition by GSK or "
            "another IO player is a credible outcome if Ph2 data delivers."
        ),
    ),
    dict(
        ticker="LNTH", company_id="co-lnth", asset_id="a-lnth",
        indication="oncology diagnostics / RLT — PYLARIFY (PSMA PET) / PNT2002 (PSMA RLT)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="PNT2002 (PSMA RLT) Ph3 SPLASH readout in mCRPC",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="PNT2002 SPLASH achieves rPFS ≥6 months improvement vs abiraterone in mCRPC",
        company_name="Lantheus Holdings", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=4_500, cash_millions=600,
        top_5_likely_acquirers=["NVS", "RHHBY", "AZN", "BMY", "PFE"],
        mna_relevance_score=0.65, data_confidence_score=0.75,
        executive_view=(
            "Lantheus dominates PSMA PET imaging (PYLARIFY, ~70% market share) and is building "
            "into radioligand therapy (PNT2002) with Novartis (Pluvicto) and Bayer (Xofigo) as "
            "comparators. At $4.5B with strong diagnostic cash flow funding RLT development, "
            "Lantheus is a rare profitable-and-growing biotech. NVS or AZ most logical acquirer."
        ),
    ),
    dict(
        ticker="MRUS", company_id="co-mrus", asset_id="a-mrus",
        indication="oncology — zenocutuzumab (NRG1) / petosemtamab (EGFR×LGR5)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Zenocutuzumab NRG1-fusion NDA submission + petosemtamab Ph2 CRC readout",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Zenocutuzumab NDA accepted and receives priority review for NRG1-fusion cancers",
        company_name="Merus N.V.", exchange="NASDAQ", country="NL",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=2_800, cash_millions=650,
        top_5_likely_acquirers=["RHHBY", "AZN", "JNJ", "BMY", "MRK"],
        mna_relevance_score=0.68, data_confidence_score=0.72,
        executive_view=(
            "Biclonics bispecific platform with zenocutuzumab (MCLA-128) as a first mover in "
            "NRG1-fusion cancers — a biomarker-selected indication with no approved therapy. "
            "Petosemtamab (EGFR×LGR5) targets CRC Wnt-pathway; MCLA-145 (PD-L1×CD137) broadens "
            "IO options. Roche (Biclonics history) or J&J most strategic acquirers at ~$2.8B."
        ),
    ),
    dict(
        ticker="NUVB", company_id="co-nuvb", asset_id="a-nuvb",
        indication="oncology — taletrectinib (ROS1/NTRK) / navtemadlin (MDM2) / safusidenib (IDH1)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Taletrectinib NDA decision + navtemadlin Ph3 AML enrollment completion",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Taletrectinib receives FDA approval for ROS1-positive NSCLC including G2032R resistance",
        company_name="Nuvation Bio", exchange="NYSE", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=700, cash_millions=400,
        top_5_likely_acquirers=["RHHBY", "PFE", "AZN", "MRK", "BMY"],
        mna_relevance_score=0.58, data_confidence_score=0.60,
        executive_view=(
            "Taletrectinib is a next-gen ROS1/NTRK inhibitor addressing crizotinib/entrectinib "
            "resistance mutations (G2032R). Navtemadlin (MDM2 inhibitor) targets AML with "
            "TP53 wild-type. Multi-mechanism portfolio in the $700M range; Roche (Rozlytrek) "
            "would logically acquire to maintain ROS1 franchise leadership."
        ),
    ),
    dict(
        ticker="PASG", company_id="co-pasg", asset_id="a-pasg",
        indication="rare CNS — PBFT02 (GBA1-FTD) / PBGM01 (GM1 gangliosidosis)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="PBFT02 Ph1/2 GBA1-FTD biomarker + cognitive function data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="PBFT02 demonstrates CSF GCase enzyme activity restoration ≥20x baseline in GBA1-FTD",
        company_name="Passage Bio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=150, cash_millions=80,
        top_5_likely_acquirers=["RHHBY", "NVS", "BIIB", "ABBV", "JNJ"],
        mna_relevance_score=0.50, data_confidence_score=0.55,
        executive_view=(
            "UPenn/Penn Medicine-licensed CNS gene therapy pipeline targeting GBA1-FTD and GM1 "
            "gangliosidosis. GBA1 mutations are the most common genetic risk factor for Parkinson's/DLB "
            "and FTD, making this highly strategic for Biogen or AbbVie's neurodegeneration pipeline. "
            "Very small cap ($150M) with runway risk — data-dependent acquisition target."
        ),
    ),
    dict(
        ticker="PRLD", company_id="co-prld", asset_id="a-prld",
        indication="hematology-oncology — PRT2527 (CDK9) / PRT1419 (MCL1)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="PRT2527 Ph1 AML/MDS ORR data + PRT1419 MCL1 combination signal",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="PRT2527 achieves ≥25% ORR in CDK9-sensitive AML/MDS as monotherapy or with venetoclax",
        company_name="Prelude Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=120, cash_millions=75,
        top_5_likely_acquirers=["ABBV", "BMY", "GSK", "AMGN", "AZN"],
        mna_relevance_score=0.45, data_confidence_score=0.55,
        executive_view=(
            "CDK9 and MCL1 inhibitors targeting venetoclax-resistant AML/MDS. Both are highly "
            "rational in the context of venetoclax combination resistance emerging in the clinic. "
            "AbbVie (venetoclax owner) is the most logical acquirer for a synergistic resistance-"
            "busting combination. Tiny market cap with binary data risk."
        ),
    ),
    dict(
        ticker="PRQR", company_id="co-prqr", asset_id="a-prqr",
        indication="ophthalmology — sepofarsen (CEP290 LCA10) / RNA editing platform",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Sepofarsen Ph2/3 ILLUMINATE CEP290 LCA10 visual function endpoint",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Sepofarsen achieves ≥0.3 LogMAR BCVA improvement vs sham in LCA10 at 12 months",
        company_name="ProQR Therapeutics", exchange="NASDAQ", country="NL",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=200, cash_millions=100,
        top_5_likely_acquirers=["RHHBY", "NVS", "AZN", "REGN", "ABBV"],
        mna_relevance_score=0.48, data_confidence_score=0.58,
        executive_view=(
            "RNA-based oligonucleotide and base-editing platform for inherited retinal dystrophies. "
            "Sepofarsen (CEP290 mutation) is the lead asset in LCA10 — an ultra-rare blinding disease "
            "with no approved therapy. Roche/Spark (Luxturna acquirer) or Novartis are logical "
            "buyers to expand gene/RNA therapy retinal portfolios."
        ),
    ),
    dict(
        ticker="PTGX", company_id="co-ptgx", asset_id="a-ptgx",
        indication="immunology/hematology — rusfertide (hepcidin mimetic) / PN-235 (oral IL-13Ra1)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Rusfertide Ph3 VERIFY polycythemia vera hematocrit control + NDA filing",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Rusfertide VERIFY achieves non-inferiority to phlebotomy with ≥50% response at 32 weeks",
        company_name="Protagonist Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_200, cash_millions=500,
        top_5_likely_acquirers=["JNJ", "NVS", "ABBV", "AMGN", "AZN"],
        mna_relevance_score=0.68, data_confidence_score=0.72,
        executive_view=(
            "Rusfertide is first-in-class hepcidin mimetic for polycythemia vera — J&J partnership "
            "with $200M upfront validates the asset. PN-235 (oral peptide IL-13Ra1 inhibitor) targets "
            "atopic dermatitis/eosinophilic GI. At $2.2B with a large-pharma partner, Protagonist is "
            "an ideal bolt-on acquisition for J&J or AbbVie's hematology/immunology pipeline."
        ),
    ),
    dict(
        ticker="RARE", company_id="co-rare", asset_id="a-rare",
        indication="rare disease — setrusumab (OI) / UX701 (Wilson disease) / DTX301 (OTC deficiency)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Setrusumab Ph3 ORBIT OI fracture reduction data + UX701 Ph1/2 Wilson disease readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Setrusumab ORBIT achieves ≥30% fracture reduction vs placebo in OI",
        company_name="Ultragenyx Pharmaceutical", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_200, cash_millions=700,
        top_5_likely_acquirers=["RHHBY", "NVS", "AMGN", "BIIB", "AZN"],
        mna_relevance_score=0.62, data_confidence_score=0.72,
        executive_view=(
            "Broad rare disease platform across bone disorders (setrusumab/OI, burosumab/XLH), "
            "gene therapy (Wilson disease, OTC deficiency, GSD), and enzyme replacement. Multiple "
            "approved products with validated revenue. At $3.2B, Ultragenyx is an acquirable rare "
            "disease franchise for Roche/Novartis looking to expand beyond hemophilia/SMA."
        ),
    ),
    dict(
        ticker="RCKT", company_id="co-rckt", asset_id="a-rckt",
        indication="rare disease gene therapy — LAD-I / PKD / Danon disease",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="RP-L201 (LAD-I) FDA approval decision + RP-A501 (Danon disease) Ph2 data",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="RP-L201 receives FDA approval for LAD-I as first gene therapy for primary immunodeficiency",
        company_name="Rocket Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=600, cash_millions=200,
        top_5_likely_acquirers=["NVS", "RHHBY", "AMGN", "GILD", "JNJ"],
        mna_relevance_score=0.58, data_confidence_score=0.60,
        executive_view=(
            "Lentiviral gene therapy pipeline for pediatric rare diseases (LAD-I, PKD, Danon disease, "
            "FA). RP-L201 (LAD-I) has shown 100% OS and near-complete immune reconstitution in early "
            "data — a compelling case. Danon disease (RP-A501) is a unique cardiomyopathy indication. "
            "At $600M with clinical proof-of-concept, acquisition is plausible from Novartis/Roche."
        ),
    ),
    dict(
        ticker="SLN", company_id="co-sln", asset_id="a-sln",
        indication="rare cardiovascular/hematology — SLN360 (Lp(a)) / ziltivekimab (IL-6)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="SLN360 Ph2 APOLLO Lp(a) reduction outcomes + RACING Ph3 (ziltivekimab/AZ partnership) CV events",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="SLN360 achieves ≥80% Lp(a) reduction with cardiovascular event signal in APOLLO",
        company_name="Silence Therapeutics", exchange="NASDAQ", country="GB",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=350, cash_millions=100,
        top_5_likely_acquirers=["NVS", "AZN", "LLY", "AMGN", "RHHBY"],
        mna_relevance_score=0.60, data_confidence_score=0.62,
        executive_view=(
            "AstraZeneca partnership for ziltivekimab (IL-6 ligand trap) in HFpEF/CKD validates "
            "siRNA delivery platform. SLN360 competes directly with pelacarsen/olpasiran in the "
            "Lp(a) reduction race. At $350M market cap, Silence is cheap optionality on the siRNA "
            "cardiovascular platform with a large-pharma partner already embedded."
        ),
    ),
    dict(
        ticker="SLRN", company_id="co-slrn", asset_id="a-slrn",
        indication="immunology — izokibep (IL-17A nanobody) / lonigutamab (IL-15Ra)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Izokibep Ph2/3 HS/PsA efficacy data + lonigutamab Ph2 celiac disease readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Izokibep achieves ≥50% IGA 0/1 or HiSCR50 in pivotal HS or PsA trial",
        company_name="Acelyrin", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=250, cash_millions=200,
        top_5_likely_acquirers=["ABBV", "RHHBY", "NVS", "AZN", "ELI"],
        mna_relevance_score=0.50, data_confidence_score=0.58,
        executive_view=(
            "Izokibep is a 6 kDa albumin-binding IL-17A nanobody — best-in-class subcutaneous dosing "
            "advantage over secukinumab/ixekizumab. Lonigutamab (IL-15Ra) targets celiac disease with "
            "no approved therapy. At $250M market cap mostly cash, risk-reward is attractive. "
            "AbbVie post-rinvoq or Novartis most logical acquirers for an IL-17 next-gen asset."
        ),
    ),
    dict(
        ticker="SNDX", company_id="co-sndx", asset_id="a-sndx",
        indication="hematology-oncology — revumenib (KMT2A/NPM1 AML) / axatilimab (HDAC)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Revumenib FDA approval + commercial launch in relapsed/refractory AML",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Revumenib achieves FDA approval for KMT2A-rearranged AML and NPM1-mutant AML",
        company_name="Syndax Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_200, cash_millions=300,
        top_5_likely_acquirers=["ABBV", "BMY", "MRK", "GSK", "AMGN"],
        mna_relevance_score=0.65, data_confidence_score=0.70,
        executive_view=(
            "Revumenib (menin inhibitor) approved 2023 for KMT2A/NPM1 AML — first-in-class in a "
            "large genomically-defined AML population. AbbVie (venetoclax) is the natural acquirer "
            "for a synergistic AML franchise. Axatilimab (CSF-1R) adds myelofibrosis/GVHD angle. "
            "At $1.2B with a launched product, Syndax is priced for near-term acquisition."
        ),
    ),
    dict(
        ticker="TERN", company_id="co-tern", asset_id="a-tern",
        indication="obesity/metabolic — TERN-601 (oral GLP-1R) / TERN-701 (THR-β agonist)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="TERN-601 Ph2 weight loss data vs semaglutide benchmark",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="TERN-601 achieves ≥10% placebo-adjusted weight loss at 26 weeks",
        company_name="Terns Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=450, cash_millions=250,
        top_5_likely_acquirers=["LLY", "NVO", "AZN", "PFE", "RHHBY"],
        mna_relevance_score=0.62, data_confidence_score=0.60,
        executive_view=(
            "Oral GLP-1R agonist + THR-β agonist combination approach targeting both weight loss "
            "and NASH/MASH. TERN-701 (resmetirom-class THR-β) for MASH adds to obesity platform. "
            "At $450M with oral mechanism upside, Terns is an affordable option play on the oral "
            "GLP-1 race. Acquisition by Lilly or AZ most likely if TERN-601 Ph2 shows efficacy."
        ),
    ),
    dict(
        ticker="TRDA", company_id="co-trda", asset_id="a-trda",
        indication="rare neuromuscular — ENTR-701 (myotonic dystrophy) / ENT-001 (Duchenne)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="ENTR-701 Ph1/2 DM1 muscle strength and biomarker data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="ENTR-701 achieves ≥30% MBNL nuclear foci reduction as DM1 biomarker endpoint",
        company_name="Entrada Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=150, cash_millions=90,
        top_5_likely_acquirers=["BIIB", "AMGN", "RHHBY", "NVS", "IONS"],
        mna_relevance_score=0.45, data_confidence_score=0.55,
        executive_view=(
            "ITREQ (intracellular targeted RNA endosomal escape and quality) delivery platform for "
            "DM1 and DMD. DM1 is a large unmet need with no approved DMT; ENTR-701 is a first-in-"
            "class intracellular ASO approach. Very small cap ($150M) with binary data risk. "
            "Biogen or Ionis (ASO platform leader) are logical acquirers."
        ),
    ),
    dict(
        ticker="ALUM", company_id="co-alum", asset_id="a-alum",
        indication="immunology — ESK-001 (TYK2 inhibitor)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="ESK-001 Ph2 psoriasis/IBD data vs deucravacitinib benchmark",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="ESK-001 achieves ≥70% PASI 75 at 16 weeks in moderate-to-severe psoriasis",
        company_name="Alumis Inc", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=800, cash_millions=400,
        top_5_likely_acquirers=["ABBV", "BMY", "PFE", "NVS", "AZN"],
        mna_relevance_score=0.65, data_confidence_score=0.62,
        executive_view=(
            "TYK2 inhibitor (ESK-001) competing with BMS's deucravacitinib (Sotyktu) in psoriasis "
            "and IBD. TYK2 selectivity over JAK1/2/3 supports clean safety profile. At $800M private "
            "with $400M cash and strong TYK2 market validation by BMS, Alumis is a credible bolt-on "
            "for AbbVie (upadacitinib franchise) or Pfizer to diversify beyond JAK1."
        ),
    ),
    dict(
        ticker="ANNX", company_id="co-annx", asset_id="a-annx",
        indication="ophthalmology/CNS — ANX007 (C1q intravitreal) / ANX005 (C1q systemic)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="ANX007 Ph2 geographic atrophy VA + DRSS data + ANX005 GBS Ph2 readout",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="ANX007 achieves ≥25% reduction in geographic atrophy lesion growth rate vs sham",
        company_name="Annexon Biosciences", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=300, cash_millions=150,
        top_5_likely_acquirers=["RHHBY", "ABBV", "NVS", "AZN", "REGN"],
        mna_relevance_score=0.55, data_confidence_score=0.60,
        executive_view=(
            "C1q complement inhibition — upstream of C3/C5 — in both eye (GA) and systemic (GBS) "
            "applications. If ANX007 shows GA slowing, it competes with approved complement therapies "
            "(pegcetacoplan/avacincaptad). ANX005 (Guillain-Barré) addresses an acute rare neurological "
            "emergency. At $300M with a clean safety profile, a low-risk acquisition for Roche/AbbVie."
        ),
    ),
    dict(
        ticker="APRE", company_id="co-apre", asset_id="a-apre",
        indication="hematology-oncology — eprenetapopt (p53 reactivator) / APR-1051",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="Eprenetapopt Ph2 MDS/AML ORR data in TP53-mutant patients",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Eprenetapopt achieves ≥30% ORR in TP53-mutant MDS/AML in combination with azacitidine",
        company_name="Aprea Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=80, cash_millions=50,
        top_5_likely_acquirers=["ABBV", "BMY", "AZN", "GSK", "JNJ"],
        mna_relevance_score=0.38, data_confidence_score=0.52,
        executive_view=(
            "p53 reactivation in TP53-mutant MDS/AML — a patient population with very poor outcomes "
            "on standard of care. Prior Ph3 failed in primary endpoint but ORR signal remains. "
            "Very small cap ($80M) with binary risk. APR-1051 is the next-gen compound with "
            "improved pharmacokinetics. Highly speculative; data-dependent acquisition only."
        ),
    ),
    dict(
        ticker="AVIR", company_id="co-avir", asset_id="a-avir",
        indication="virology — bemnifosbuvir (oral HCV/RSV/influenza)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Bemnifosbuvir Ph2/3 RSV/influenza data vs nirmatrelvir comparator",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Bemnifosbuvir achieves ≥1.5 day reduction in time-to-symptom-alleviation in RSV",
        company_name="Atea Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=300, cash_millions=350,
        top_5_likely_acquirers=["GILD", "ABBV", "MRK", "PFE", "RHHBY"],
        mna_relevance_score=0.48, data_confidence_score=0.60,
        executive_view=(
            "Nucleotide analogue antiviral with broad-spectrum RNA polymerase inhibition against "
            "RSV, influenza, and coronaviruses. Trades near cash with $350M and $300M market cap — "
            "essentially a free call option on antiviral development. Gilead (Sovaldi/Veklury "
            "precedent) or AbbVie most logical acquirers for the nucleotide platform."
        ),
    ),
    dict(
        ticker="BCYC", company_id="co-bcyc", asset_id="a-bcyc",
        indication="oncology — BT8009 (Nectin-4 bicycle ADC) / BT5528 (EphA2) / BT7480 (CD137)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="BT8009 Ph2 urothelial cancer ORR vs enfortumab vedotin benchmark",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="BT8009 achieves ≥45% ORR in Nectin-4 high urothelial cancer post-platinum",
        company_name="Bicycle Therapeutics", exchange="NASDAQ", country="GB",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=600, cash_millions=250,
        top_5_likely_acquirers=["RHHBY", "AZN", "SEAGEN", "PFE", "MRK"],
        mna_relevance_score=0.55, data_confidence_score=0.62,
        executive_view=(
            "Bicycle peptide ADC platform — smaller than antibodies, higher tissue penetration, "
            "shorter half-life allowing dose-dense regimens. BT8009 (Nectin-4) competes directly "
            "with enfortumab vedotin in bladder cancer. UK-based platform company; Roche or "
            "AZ most logical acquirers for bicyclic peptide ADC technology."
        ),
    ),
    dict(
        ticker="BDTX", company_id="co-bdtx", asset_id="a-bdtx",
        indication="oncology — BDTX-1535 (pan-EGFR MasterKey allosteric)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="BDTX-1535 Ph1/2 NSCLC (EGFR exon 20 / uncommon mutations) ORR data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="BDTX-1535 achieves ≥40% ORR in EGFR exon 20 insertion NSCLC",
        company_name="Black Diamond Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=100, cash_millions=80,
        top_5_likely_acquirers=["AZN", "RHHBY", "AMGN", "MRK", "JNJ"],
        mna_relevance_score=0.45, data_confidence_score=0.55,
        executive_view=(
            "MasterKey allosteric EGFR inhibitor designed to overcome osimertinib resistance and "
            "address uncommon EGFR mutations (exon 20). AZ (osimertinib/Tagrisso) is the natural "
            "acquirer to maintain EGFR dominance post-resistance. Near-cash market cap ($100M) "
            "makes this a low-cost option on EGFR resistance mechanisms."
        ),
    ),
    dict(
        ticker="BOLD", company_id="co-bold", asset_id="a-bold",
        indication="oncology — BBI-355 (FISH approach targeting ecDNA-dependent tumors)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="BBI-355 Ph2 CDK7 inhibition ecDNA+ solid tumor ORR",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="BBI-355 demonstrates ≥25% ORR in ecDNA-amplified solid tumors (CDK7-dependent)",
        company_name="Boundless Bio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=80, cash_millions=55,
        top_5_likely_acquirers=["RHHBY", "AZN", "MRK", "BMY", "PFE"],
        mna_relevance_score=0.40, data_confidence_score=0.50,
        executive_view=(
            "Novel oncology target: extrachromosomal DNA (ecDNA) amplifications drive oncogene "
            "overexpression in ~14% of solid tumors. BBI-355 (CDK7/ecDNA-dependent) is first "
            "clinical asset targeting ecDNA biology. Very high scientific interest but early-stage "
            "clinical validation required. Preclinical-stage acquisition risk."
        ),
    ),
    dict(
        ticker="CALT", company_id="co-calt", asset_id="a-calt",
        indication="kidney disease — budesonide targeted-release (Tarpeyo) for IgAN",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="Tarpeyo PROTECT Ph3 eGFR slope/proteinuria long-term data + EU approval decision",
        claim_type=ClaimType.LABEL_EXPANSION,
        claim_assertion="Tarpeyo PROTECT data supports full approval conversion and/or EU regulatory approval",
        company_name="Calliditas Therapeutics", exchange="NASDAQ", country="SE",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=500, cash_millions=200,
        top_5_likely_acquirers=["AZN", "JNJ", "ABBV", "NVS", "RHHBY"],
        mna_relevance_score=0.62, data_confidence_score=0.65,
        executive_view=(
            "Tarpeyo (Nefecon) is first-in-class oral targeted-release budesonide for IgA nephropathy, "
            "an indication with rapid growth of approved therapies (sparsentan, iptacopan). At $500M "
            "with a launched product and EU data ongoing, Calliditas is a clean acquirable IgAN "
            "franchise. AZ (dapagliflozin/IgAN label) or J&J most logical."
        ),
    ),
    dict(
        ticker="OCGN", company_id="co-ocgn", asset_id="a-ocgn",
        indication="ophthalmology — OCU400 (NR2E3 gene therapy retinal) / OCU410 (RORA)",
        ranking_score=0.58, opportunity_score=0.56, conviction="medium",
        catalyst="OCU400 Ph2/3 ILLUMINATE RP visual function data + NDA pathway discussions",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="OCU400 achieves ≥15 ETDRS letter improvement or microperimetry improvement vs sham in RP",
        company_name="Ocugen Inc", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=300, cash_millions=100,
        top_5_likely_acquirers=["NVS", "RHHBY", "REGN", "AZN", "ABBV"],
        mna_relevance_score=0.48, data_confidence_score=0.55,
        executive_view=(
            "NR2E3 nuclear hormone receptor gene therapy for a broad range of retinitis pigmentosa "
            "subtypes — a mutation-agnostic approach vs Luxturna's RPE65-specific gene replacement. "
            "If OCU400 shows durable visual benefit, it would represent a platform for many RP "
            "patients. Very small cap ($300M) with high binary data risk. Novartis most logical."
        ),
    ),
    dict(
        ticker="SLDB", company_id="co-sldb", asset_id="a-sldb",
        indication="rare disease — SGT-003 (Duchenne muscular dystrophy gene therapy)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="SGT-003 Ph1/2 ENVISION dystrophin expression and motor function data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="SGT-003 achieves ≥50% dystrophin expression (Western blot) at 6 months in DMD",
        company_name="Solid Biosciences", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=200, cash_millions=120,
        top_5_likely_acquirers=["RHHBY", "SRPT", "NVS", "AMGN", "SGEN"],
        mna_relevance_score=0.50, data_confidence_score=0.58,
        executive_view=(
            "Next-generation micro-dystrophin gene therapy for DMD with SGT-003 designed to overcome "
            "pre-existing antibody issues (using engineered AAV9 variants). Sarepta (Elevidys) is the "
            "approved competitor; Solid's differentiation is reduced immunogenicity. At $200M mostly "
            "cash, a strategic acquirer could get a best-in-class gene therapy option cheaply."
        ),
    ),

    # ------------------------------------------------------------------
    # Wave 2 additions — acquired companies (M&A history reference)
    # mna_relevance_score = 0.10 (already completed deals)
    # ------------------------------------------------------------------
    dict(
        ticker="AKUS", company_id="co-akus", asset_id="a-akus",
        indication="sensorineural hearing loss — AK-OTOF (AAV gene therapy)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Eli Lilly — 2022-10-18 at $610M",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="AK-OTOF gene therapy validates hearing loss gene therapy as strategic asset class",
        company_name="Akouos", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=610, cash_millions=0,
        top_5_likely_acquirers=["LLY"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Eli Lilly (2022-10-18, $610M). Historical M&A reference: Lilly entry into hearing loss gene therapy via AK-OTOF (OTOF-mutation deafness). No longer independent.",
    ),
    dict(
        ticker="ALPN", company_id="co-alpn", asset_id="a-alpn",
        indication="IgA nephropathy — povetacicept (APRIL/BAFF blocker)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Vertex — 2024-04-10 at $4.9B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Povetacicept validates dual APRIL/BAFF blockade as acquisition-worthy IgAN mechanism",
        company_name="Alpine Immune Sciences", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=4_900, cash_millions=0,
        top_5_likely_acquirers=["VRTX"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Vertex Pharmaceuticals (2024-04-10, ~$4.9B). Historical M&A reference: Vertex expansion into autoimmune (IgAN) via povetacicept. No longer independent.",
    ),
    dict(
        ticker="AMAM", company_id="co-amam", asset_id="a-amam",
        indication="mCRPC — ARX517 (PSMA ADC)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Johnson & Johnson — 2024-01-08 at $2B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="ARX517 PSMA ADC validates engineered antibody platform for oncology acquisition",
        company_name="Ambrx", exchange="NYSE", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_000, cash_millions=0,
        top_5_likely_acquirers=["JNJ"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Johnson & Johnson (2024-01-08, ~$2B). Historical M&A reference: J&J acquisition of PSMA-targeted ADC platform for prostate cancer. No longer independent.",
    ),
    dict(
        ticker="ARNA", company_id="co-arna", asset_id="a-arna",
        indication="ulcerative colitis — etrasimod (S1P1,4,5 modulator)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Pfizer — 2021-12-13 at $6.7B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Etrasimod validates oral S1P modulation as Pfizer immunology bolt-on",
        company_name="Arena Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=6_700, cash_millions=0,
        top_5_likely_acquirers=["PFE"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Pfizer (2021-12-13, $6.7B). Historical M&A reference: Pfizer immunology pipeline acquisition — etrasimod (Velsipity) now approved for UC. No longer independent.",
    ),
    dict(
        ticker="BHVN", company_id="co-bhvn", asset_id="a-bhvn",
        indication="migraine — rimegepant (CGRP) / zavegepant (CGRP nasal)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Pfizer — 2022-05-10 at $11.6B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Rimegepant validates oral CGRP antagonist franchise as Pfizer migraine platform acquisition",
        company_name="Biohaven Pharmaceuticals", exchange="NYSE", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=11_600, cash_millions=0,
        top_5_likely_acquirers=["PFE"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Pfizer (2022-05-10, $11.6B). Historical M&A reference: Pfizer entry into CGRP migraine market via rimegepant (Nurtec). No longer independent.",
    ),
    dict(
        ticker="BLU", company_id="co-blu", asset_id="a-blu",
        indication="refractory chronic cough — camlipixant (P2X3 antagonist)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by GSK — 2023-04-18 at $2B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Camlipixant validates P2X3 purinergic receptor as cough acquisition target",
        company_name="Bellus Health", exchange="NASDAQ", country="CA",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_000, cash_millions=0,
        top_5_likely_acquirers=["GSK"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by GSK (2023-04-18, ~$2B). Historical M&A reference: GSK expansion into refractory chronic cough via P2X3 mechanism. No longer independent.",
    ),
    dict(
        ticker="CBAY", company_id="co-cbay", asset_id="a-cbay",
        indication="primary biliary cholangitis — seladelpar (PPARδ agonist)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Gilead Sciences — 2024-02-12 at $4.3B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Seladelpar validates PPARdelta agonist as Gilead liver disease acquisition",
        company_name="CymaBay Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=4_300, cash_millions=0,
        top_5_likely_acquirers=["GILD"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Gilead Sciences (2024-02-12, ~$4.3B). Historical M&A reference: Gilead PBC/liver franchise expansion via seladelpar (Livdelzi). No longer independent.",
    ),
    dict(
        ticker="CCXI", company_id="co-ccxi", asset_id="a-ccxi",
        indication="ANCA-associated vasculitis — avacopan (C5aR1 inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Amgen — 2022-08-04 at $3.7B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Avacopan validates C5aR1 complement acquisition for Amgen immunology pipeline",
        company_name="ChemoCentryx", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_700, cash_millions=0,
        top_5_likely_acquirers=["AMGN"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Amgen (2022-08-04, $3.7B). Historical M&A reference: Amgen rare autoimmune expansion via avacopan (Tavneos). No longer independent.",
    ),
    dict(
        ticker="CERE", company_id="co-cere", asset_id="a-cere",
        indication="schizophrenia/CNS — emraclidine (M4 muscarinic PAM)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by AbbVie — 2023-12-06 at $8.7B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Emraclidine validates M4 muscarinic PAM as AbbVie non-D2 CNS acquisition",
        company_name="Cerevel Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=8_700, cash_millions=0,
        top_5_likely_acquirers=["ABBV"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by AbbVie (2023-12-06, $8.7B). Historical M&A reference: AbbVie's major CNS bet on muscarinic mechanism for schizophrenia. No longer independent.",
    ),
    dict(
        ticker="CINC", company_id="co-cinc", asset_id="a-cinc",
        indication="treatment-resistant hypertension — baxdrostat (CYP11B2 inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by AstraZeneca — 2023-01-09 at $1.8B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Baxdrostat validates aldosterone synthase inhibition as cardiovascular M&A target",
        company_name="CinCor Pharma", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_800, cash_millions=0,
        top_5_likely_acquirers=["AZN"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by AstraZeneca (2023-01-09, ~$1.8B). Historical M&A reference: AZ cardiovascular pipeline acquisition — baxdrostat for resistant hypertension. No longer independent.",
    ),
    dict(
        ticker="DRNA", company_id="co-drna", asset_id="a-drna",
        indication="rare/cardiometabolic — nedosiran (GalXC RNAi platform)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Novo Nordisk — 2021-11-22 at $3.3B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="GalXC RNAi platform validates subcutaneous RNAi delivery for Novo cardiometabolic pipeline",
        company_name="Dicerna Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_300, cash_millions=0,
        top_5_likely_acquirers=["NVO"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Novo Nordisk (2021-11-22, $3.3B). Historical M&A reference: Novo Nordisk's platform acquisition for RNAi cardiometabolic pipeline. No longer independent.",
    ),
    dict(
        ticker="FPRX", company_id="co-fprx", asset_id="a-fprx",
        indication="FGFR2b gastric/GEJ cancer — bemarituzumab",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Amgen — 2021-03-04 at $1.9B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Bemarituzumab FGFR2b validates Amgen gastric cancer oncology bolt-on thesis",
        company_name="Five Prime Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_900, cash_millions=0,
        top_5_likely_acquirers=["AMGN"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Amgen (2021-03-04, $1.9B). Historical M&A reference: Amgen gastric cancer pipeline expansion via FGFR2b antibody. No longer independent.",
    ),
    dict(
        ticker="GBT", company_id="co-gbt", asset_id="a-gbt",
        indication="sickle cell disease — voxelotor (hemoglobin stabilizer)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Pfizer — 2022-08-08 at $5.4B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Voxelotor validates SCD hemoglobin stabilizer mechanism as Pfizer rare hematology acquisition",
        company_name="Global Blood Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=5_400, cash_millions=0,
        top_5_likely_acquirers=["PFE"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Pfizer (2022-08-08, $5.4B). Historical M&A reference: Pfizer SCD franchise acquisition — Oxbryta subsequently withdrawn due to safety. No longer independent.",
    ),
    dict(
        ticker="HARP", company_id="co-harp", asset_id="a-harp",
        indication="SCLC — HPN328/MK-6070 (DLL3×CD3 TriTAC)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Merck — 2023-12-20 at $680M",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="DLL3 TriTAC validates bispecific T-cell engager acquisition for Merck SCLC pipeline",
        company_name="Harpoon Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=680, cash_millions=0,
        top_5_likely_acquirers=["MRK"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Merck (2023-12-20, $680M). Historical M&A reference: Merck SCLC bispecific engager acquisition. No longer independent.",
    ),
    dict(
        ticker="IMGO", company_id="co-imgo", asset_id="a-imgo",
        indication="myelofibrosis/ET — bomedemstat (LSD1 inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Merck — 2022-11-21 at $1.35B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Bomedemstat validates LSD1 inhibition as Merck hematology-oncology acquisition",
        company_name="Imago BioSciences", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_350, cash_millions=0,
        top_5_likely_acquirers=["MRK"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Merck (2022-11-21, $1.35B). Historical M&A reference: Merck myeloproliferative neoplasm pipeline acquisition via LSD1 inhibitor. No longer independent.",
    ),
    dict(
        ticker="IMMU", company_id="co-immu", asset_id="a-immu",
        indication="metastatic TNBC — Trodelvy (sacituzumab govitecan ADC)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Gilead Sciences — 2020-09-13 at $21B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Trodelvy validates TROP-2 ADC as Gilead mega-cap oncology acquisition",
        company_name="Immunomedics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=21_000, cash_millions=0,
        top_5_likely_acquirers=["GILD"],
        mna_relevance_score=0.10, data_confidence_score=0.95,
        executive_view="ACQUIRED by Gilead Sciences (2020-09-13, $21B). Historical M&A reference: Gilead's largest oncology acquisition — Trodelvy (TROP-2 ADC) now generating $800M+/yr. No longer independent.",
    ),
    dict(
        ticker="INBX", company_id="co-inbx", asset_id="a-inbx",
        indication="AATD — INBRX-101 (alpha-1 antitrypsin augmentation)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Sanofi — 2024-01-23 at $2.2B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="INBRX-101 validates engineered albumin-AAT fusion as Sanofi rare pulmonary acquisition",
        company_name="Inhibrx", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_200, cash_millions=0,
        top_5_likely_acquirers=["SNY"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Sanofi (2024-01-23, ~$2.2B). Historical M&A reference: Sanofi rare disease expansion via AAT augmentation therapy for AATD. No longer independent.",
    ),
    dict(
        ticker="ISEE", company_id="co-isee", asset_id="a-isee",
        indication="geographic atrophy — avacincaptad pegol (C5 complement inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Astellas — 2023-04-30 at $5.9B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Avacincaptad pegol validates C5 complement inhibition as Astellas ophthalmology acquisition",
        company_name="Iveric Bio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=5_900, cash_millions=0,
        top_5_likely_acquirers=["ASTEL"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Astellas (2023-04-30, $5.9B). Historical M&A reference: Astellas ophthalmology expansion via Izervay (avacincaptad pegol) for geographic atrophy. No longer independent.",
    ),
    dict(
        ticker="ITCI", company_id="co-itci", asset_id="a-itci",
        indication="schizophrenia/bipolar — Caplyta (lumateperone)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Johnson & Johnson — 2025-01-13 at $14.6B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Caplyta validates multireceptor CNS mechanism as J&J neuroscience mega-acquisition",
        company_name="Intra-Cellular Therapies", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=14_600, cash_millions=0,
        top_5_likely_acquirers=["JNJ"],
        mna_relevance_score=0.10, data_confidence_score=0.95,
        executive_view="ACQUIRED by Johnson & Johnson (2025-01-13, $14.6B). Historical M&A reference: J&J's largest recent CNS acquisition — Caplyta generating $700M+/yr. No longer independent.",
    ),
    dict(
        ticker="KDNY", company_id="co-kdny", asset_id="a-kdny",
        indication="IgA nephropathy — atrasentan / zigakibart",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Novartis — 2023-06-12 at $3.5B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Atrasentan/zigakibart validates IgAN dual-mechanism as Novartis kidney acquisition",
        company_name="Chinook Therapeutics", exchange="NASDAQ", country="CA",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_500, cash_millions=0,
        top_5_likely_acquirers=["NVS"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Novartis (2023-06-12, $3.5B). Historical M&A reference: Novartis kidney disease expansion via atrasentan (IgAN endothelin antagonist). No longer independent.",
    ),
    dict(
        ticker="KRTX", company_id="co-krtx", asset_id="a-krtx",
        indication="schizophrenia — KarXT (xanomeline/trospium muscarinic)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Bristol Myers Squibb — 2023-12-22 at $14B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="KarXT validates non-D2 muscarinic mechanism as BMS CNS mega-acquisition",
        company_name="Karuna Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=14_000, cash_millions=0,
        top_5_likely_acquirers=["BMY"],
        mna_relevance_score=0.10, data_confidence_score=0.95,
        executive_view="ACQUIRED by Bristol Myers Squibb (2023-12-22, $14B). Historical M&A reference: BMS's entry into CNS via KarXT (Cobenfy) — first non-D2 schizophrenia treatment. No longer independent.",
    ),
    dict(
        ticker="LBPH", company_id="co-lbph", asset_id="a-lbph",
        indication="developmental epileptic encephalopathies — bexicaserin (5-HT2C agonist)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Lundbeck — 2024-10-14 at $2.6B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Bexicaserin validates 5-HT2C serotonin agonism as Lundbeck CNS rare disease acquisition",
        company_name="Longboard Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_600, cash_millions=0,
        top_5_likely_acquirers=["LUND"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Lundbeck (2024-10-14, $2.6B). Historical M&A reference: Lundbeck expansion into DEE epilepsy via selective 5-HT2C mechanism. No longer independent.",
    ),
    dict(
        ticker="MNTA", company_id="co-mnta", asset_id="a-mnta",
        indication="autoimmune/FcRn — nipocalimab (FcRn antibody)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Johnson & Johnson — 2020-08-19 at $6.5B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Nipocalimab validates FcRn blockade as J&J autoimmune platform acquisition",
        company_name="Momenta Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=6_500, cash_millions=0,
        top_5_likely_acquirers=["JNJ"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Johnson & Johnson (2020-08-19, $6.5B). Historical M&A reference: J&J entry into FcRn-mediated autoimmune disease via nipocalimab. No longer independent.",
    ),
    dict(
        ticker="MORF", company_id="co-morf", asset_id="a-morf",
        indication="UC/Crohn's — MORF-057 (oral integrin αvβ6/αvβ1 inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Eli Lilly — 2024-07-08 at $3.2B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="MORF-057 validates oral integrin inhibition as Lilly IBD acquisition",
        company_name="Morphic Therapeutic", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_200, cash_millions=0,
        top_5_likely_acquirers=["LLY"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Eli Lilly (2024-07-08, $3.2B). Historical M&A reference: Lilly IBD pipeline expansion via oral integrin αvβ6 inhibitor MORF-057. No longer independent.",
    ),
    dict(
        ticker="MYOK", company_id="co-myok", asset_id="a-myok",
        indication="hypertrophic cardiomyopathy — mavacamten (cardiac myosin inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Bristol Myers Squibb — 2020-10-05 at $13.1B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Mavacamten validates cardiac myosin inhibition as BMS cardiovascular mega-acquisition",
        company_name="MyoKardia", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=13_100, cash_millions=0,
        top_5_likely_acquirers=["BMY"],
        mna_relevance_score=0.10, data_confidence_score=0.95,
        executive_view="ACQUIRED by Bristol Myers Squibb (2020-10-05, $13.1B). Historical M&A reference: BMS's HCM franchise acquisition — mavacamten (Camzyos) now approved. No longer independent.",
    ),
    dict(
        ticker="PAND", company_id="co-pand", asset_id="a-pand",
        indication="autoimmune (IBD/T1D) — PT-101 (IL-2 mutein)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Merck — 2021-03-29 at $1.85B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="PT-101 validates organ-specific IL-2 immunoregulation as Merck autoimmune acquisition",
        company_name="Pandion Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_850, cash_millions=0,
        top_5_likely_acquirers=["MRK"],
        mna_relevance_score=0.10, data_confidence_score=0.88,
        executive_view="ACQUIRED by Merck (2021-03-29, $1.85B). Historical M&A reference: Merck autoimmune/tolerance platform acquisition via IL-2 mutein approach. No longer independent.",
    ),
    dict(
        ticker="PRNB", company_id="co-prnb", asset_id="a-prnb",
        indication="autoimmune/MS — rilzabrutinib / tolebrutinib (BTK inhibitors)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Sanofi — 2020-08-17 at $3.68B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="BTK inhibitor platform validates oral CNS-penetrant autoimmune acquisition for Sanofi",
        company_name="Principia Biopharma", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_680, cash_millions=0,
        top_5_likely_acquirers=["SNY"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Sanofi (2020-08-17, $3.68B). Historical M&A reference: Sanofi acquisition of BTK inhibitor platform — tolebrutinib now in Ph3 for MS. No longer independent.",
    ),
    dict(
        ticker="PRVB", company_id="co-prvb", asset_id="a-prvb",
        indication="T1D delay — TZIELD (teplizumab anti-CD3)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Sanofi — 2023-03-13 at $2.9B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="TZIELD validates T-cell modulation as Sanofi T1D prevention acquisition",
        company_name="Provention Bio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_900, cash_millions=0,
        top_5_likely_acquirers=["SNY"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Sanofi (2023-03-13, $2.9B). Historical M&A reference: Sanofi T1D franchise expansion via TZIELD (teplizumab) — first therapy to delay T1D onset. No longer independent.",
    ),
    dict(
        ticker="PRVL", company_id="co-prvl", asset_id="a-prvl",
        indication="Parkinson's GBA1/FTD-GRN gene therapy — PR001/PR006",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Eli Lilly — 2020-12-15 at $1.04B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="PR001/PR006 validates CNS gene therapy as Lilly neurodegenerative disease acquisition",
        company_name="Prevail Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_040, cash_millions=0,
        top_5_likely_acquirers=["LLY"],
        mna_relevance_score=0.10, data_confidence_score=0.88,
        executive_view="ACQUIRED by Eli Lilly (2020-12-15, $1.04B). Historical M&A reference: Lilly CNS gene therapy platform acquisition for Parkinson's/FTD. No longer independent.",
    ),
    dict(
        ticker="RAPT", company_id="co-rapt", asset_id="a-rapt",
        indication="food allergy — ozureprubart (FLT3L antagonist)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by GSK — 2026-01-20 at $650M",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Ozureprubart validates FLT3 ligand blockade as GSK food allergy acquisition",
        company_name="RAPT Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=650, cash_millions=0,
        top_5_likely_acquirers=["GSK"],
        mna_relevance_score=0.10, data_confidence_score=0.88,
        executive_view="ACQUIRED by GSK (2026-01-20, $650M). Historical M&A reference: GSK food allergy pipeline acquisition via FLT3L mechanism. No longer independent.",
    ),
    dict(
        ticker="RETA", company_id="co-reta", asset_id="a-reta",
        indication="Friedreich's ataxia — Skyclarys (omaveloxolone, NRF2 activator)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Biogen — 2023-07-28 at $7.3B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Skyclarys validates NRF2 activation as Biogen rare neurological acquisition",
        company_name="Reata Pharmaceuticals", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=7_300, cash_millions=0,
        top_5_likely_acquirers=["BIIB"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Biogen (2023-07-28, $7.3B). Historical M&A reference: Biogen rare neurological expansion via Skyclarys (first FA therapy). No longer independent.",
    ),
    dict(
        ticker="RNA", company_id="co-rna", asset_id="a-rna",
        indication="neuromuscular (DM1/FSHD/DMD) — del-desiran / del-brax / del-zota",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Novartis — 2025-10-26 at $5.5B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="AOC platform validates antibody-oligonucleotide conjugate delivery as Novartis RNA acquisition",
        company_name="Avidity Biosciences", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=5_500, cash_millions=0,
        top_5_likely_acquirers=["NVS"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Novartis (2025-10-26, $5.5B). Historical M&A reference: Novartis AOC platform acquisition for muscle disease RNA therapy (DM1, FSHD, DMD). No longer independent.",
    ),
    dict(
        ticker="RXDX", company_id="co-rxdx", asset_id="a-rxdx",
        indication="UC/Crohn's — PRA023 (anti-TL1A antibody)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Merck — 2023-04-16 at $10.8B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="PRA023 validates TL1A blockade as Merck IBD mega-acquisition",
        company_name="Prometheus Biosciences", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=10_800, cash_millions=0,
        top_5_likely_acquirers=["MRK"],
        mna_relevance_score=0.10, data_confidence_score=0.95,
        executive_view="ACQUIRED by Merck (2023-04-16, $10.8B). Historical M&A reference: Merck's largest IBD acquisition — PRA023 (tulisokibart) for TL1A-driven Crohn's/UC. No longer independent.",
    ),
    dict(
        ticker="RYZB", company_id="co-ryzb", asset_id="a-ryzb",
        indication="GEP-NETs — RYZ101 (actinium-225 DOTATATE RLT)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Bristol Myers Squibb — 2023-12-26 at $4.1B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="RYZ101 validates alpha-particle radioligand therapy as BMS oncology acquisition",
        company_name="RayzeBio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=4_100, cash_millions=0,
        top_5_likely_acquirers=["BMY"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Bristol Myers Squibb (2023-12-26, $4.1B). Historical M&A reference: BMS alpha-RLT platform acquisition — actinium-225 next-gen radioligand therapy. No longer independent.",
    ),
    dict(
        ticker="SAGE", company_id="co-sage", asset_id="a-sage",
        indication="CNS — SAGE-718 (NMDA modulator) cognitive impairment in HD",
        ranking_score=0.54, opportunity_score=0.52, conviction="low-medium",
        catalyst="SAGE-718 Ph2 HD cognitive endpoint data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="SAGE-718 achieves ≥2-point improvement on cognitive assessment in HD patients at 12 weeks",
        company_name="Sage Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=600, cash_millions=350,
        top_5_likely_acquirers=["BIIB", "AZN", "ABBV", "RHHBY", "JNJ"],
        mna_relevance_score=0.45, data_confidence_score=0.60,
        executive_view=(
            "Sage's lead asset zuranolone (Zurzuvae) was co-commercialised with Biogen — making "
            "Biogen the natural acquirer for SAGE-718 (NMDA+) if HD cognitive data reads positively. "
            "At $600M market cap mostly cash, the risk-reward is attractive for a CNS-focused buyer."
        ),
    ),
    dict(
        ticker="SPNV", company_id="co-spnv", asset_id="a-spnv",
        indication="AI-diagnostics — DeepView (burn wound healing AI assessment)",
        ranking_score=0.58, opportunity_score=0.56, conviction="low",
        catalyst="DeepView FDA De Novo clearance + first commercial hospital contract",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="DeepView receives FDA 510(k)/De Novo clearance for burn wound perfusion assessment",
        company_name="Spectral AI", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=50, cash_millions=20,
        top_5_likely_acquirers=["MDT", "SYK", "JNJ", "HOLX", "ISRG"],
        mna_relevance_score=0.20, data_confidence_score=0.45,
        executive_view=(
            "AI wound-assessment technology using multispectral imaging to predict burn healing "
            "outcomes in 3-5 days (vs 10-14 days clinically). Very small cap ($50M), cash-limited. "
            "Medtech rather than pharma acquisition target — Medtronic or Stryker most logical. "
            "Low conviction; inclusion is for coverage breadth, not high-probability thesis."
        ),
    ),
    dict(
        ticker="SRRA", company_id="co-srra", asset_id="a-srra",
        indication="myelofibrosis — momelotinib (JAK1/2 + ACVR1 inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by GSK — 2022-04-13 at $1.9B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Momelotinib validates JAK/ACVR1 dual inhibition as GSK myelofibrosis acquisition",
        company_name="Sierra Oncology", exchange="NASDAQ", country="CA",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=1_900, cash_millions=0,
        top_5_likely_acquirers=["GSK"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by GSK (2022-04-13, $1.9B). Historical M&A reference: GSK myelofibrosis acquisition via momelotinib (Ojjaara) — addressing anemia complication with ACVR1 mechanism. No longer independent.",
    ),
    dict(
        ticker="TBIO", company_id="co-tbio", asset_id="a-tbio",
        indication="mRNA platform — vaccines / cystic fibrosis / rare pulmonary",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Sanofi — 2021-08-03 at $3.2B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Translate Bio mRNA platform validates Sanofi vaccine/rare disease platform acquisition",
        company_name="Translate Bio", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=3_200, cash_millions=0,
        top_5_likely_acquirers=["SNY"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Sanofi (2021-08-03, $3.2B). Historical M&A reference: Sanofi mRNA platform acquisition for respiratory/vaccine pipeline. No longer independent.",
    ),
    dict(
        ticker="TPTX", company_id="co-tptx", asset_id="a-tptx",
        indication="ROS1-positive NSCLC — repotrectinib (ROS1/NTRK next-gen TKI)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Bristol Myers Squibb — 2022-06-03 at $4.1B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Repotrectinib validates ROS1/NTRK resistance-breaking TKI as BMS thoracic oncology acquisition",
        company_name="Turning Point Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=4_100, cash_millions=0,
        top_5_likely_acquirers=["BMY"],
        mna_relevance_score=0.10, data_confidence_score=0.92,
        executive_view="ACQUIRED by Bristol Myers Squibb (2022-06-03, $4.1B). Historical M&A reference: BMS thoracic oncology acquisition — repotrectinib (Augtyro) approved 2023 for ROS1 NSCLC. No longer independent.",
    ),
    dict(
        ticker="TRIL", company_id="co-tril", asset_id="a-tril",
        indication="hematologic malignancies — TTI-622/TTI-621 (SIRPα-Fc, CD47 pathway)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Pfizer — 2021-08-23 at $2.26B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="SIRPα-Fc validates anti-phagocytic checkpoint blockade as Pfizer hematology acquisition",
        company_name="Trillium Therapeutics", exchange="NASDAQ", country="CA",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_260, cash_millions=0,
        top_5_likely_acquirers=["PFE"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Pfizer (2021-08-23, $2.26B). Historical M&A reference: Pfizer CD47/SIRPα checkpoint acquisition for hematologic malignancy pipeline. No longer independent.",
    ),
    dict(
        ticker="VERV", company_id="co-verv", asset_id="a-verv",
        indication="HeFH/ASCVD — VERVE-102 (base editing PCSK9)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Eli Lilly — 2025-06-17 at $2.9B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="VERVE-102 validates in vivo base editing for PCSK9 as Lilly cardiovascular acquisition",
        company_name="Verve Therapeutics", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=2_900, cash_millions=0,
        top_5_likely_acquirers=["LLY"],
        mna_relevance_score=0.10, data_confidence_score=0.88,
        executive_view="ACQUIRED by Eli Lilly (2025-06-17, $2.9B). Historical M&A reference: Lilly in vivo base editing acquisition — PCSK9 permanent gene silencing for familial hypercholesterolemia. No longer independent.",
    ),
    dict(
        ticker="VRNA", company_id="co-vrna", asset_id="a-vrna",
        indication="COPD maintenance — Ohtuvayre (ensifentrine PDE3/4 inhibitor)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Merck — 2025-07-09 at $6.8B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Ohtuvayre validates nebulised PDE3/4 dual inhibition as Merck COPD franchise acquisition",
        company_name="Verona Pharma", exchange="NASDAQ", country="GB",
        region="Europe", company_type="target", target_type="target",
        market_cap_millions=6_800, cash_millions=0,
        top_5_likely_acquirers=["MRK"],
        mna_relevance_score=0.10, data_confidence_score=0.90,
        executive_view="ACQUIRED by Merck (2025-07-09, $6.8B). Historical M&A reference: Merck COPD maintenance acquisition — Ohtuvayre (ensifentrine) first new COPD MOA in decades. No longer independent.",
    ),
    dict(
        ticker="XLRN", company_id="co-xlrn", asset_id="a-xlrn",
        indication="pulmonary arterial hypertension — sotatercept (ActRII activin trap)",
        ranking_score=0.12, opportunity_score=0.10, conviction="very-low",
        catalyst="Acquired by Merck — 2021-09-30 at $11.5B",
        claim_type=ClaimType.CUSTOM,
        claim_assertion="Sotatercept validates activin pathway for PAH as Merck cardiovascular mega-acquisition",
        company_name="Acceleron Pharma", exchange="NASDAQ", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=11_500, cash_millions=0,
        top_5_likely_acquirers=["MRK"],
        mna_relevance_score=0.10, data_confidence_score=0.95,
        executive_view="ACQUIRED by Merck (2021-09-30, $11.5B). Historical M&A reference: Merck PAH franchise acquisition — sotatercept (Winrevair) approved 2024 for PAH. No longer independent.",
    ),
    dict(
        ticker="NONE", company_id="co-none", asset_id="a-none",
        indication="obesity — bimagrumab (ActRIIA/B inhibitor muscle/fat)",
        ranking_score=0.54, opportunity_score=0.52, conviction="medium",
        catalyst="Bimagrumab Ph3 obesity + MASH body composition data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Bimagrumab achieves ≥5% lean mass preservation with ≥10% fat mass reduction vs semaglutide",
        company_name="Versanis Bio", exchange="PRIVATE", country="US",
        region="North America", company_type="target", target_type="target",
        market_cap_millions=500, cash_millions=200,
        top_5_likely_acquirers=["LLY", "NVO", "AZN", "PFE", "RHHBY"],
        mna_relevance_score=0.60, data_confidence_score=0.55,
        executive_view=(
            "Bimagrumab (licensed from Novartis) activates muscle growth while reducing fat — a "
            "differentiated obesity approach that preserves lean mass vs GLP-1-only weight loss. "
            "Ph3 readout directly competing with semaglutide muscle loss concerns. Private company "
            "but Eli Lilly (tirzepatide) most likely acquirer to add muscle-preserving mechanism."
        ),
    ),
]

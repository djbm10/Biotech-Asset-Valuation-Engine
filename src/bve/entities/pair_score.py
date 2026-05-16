"""Pair-level acquirer × target scoring model.

Records a strategic assessment for a specific (acquirer, target) combination,
capturing factors that cannot be derived from either party in isolation.

Usage:
    pair = AcquirerTargetPair(
        acquirer_id="merck",
        target_asset_id="a-vrtx",
        scores=PairScore(ta_fit=0.9, loe_gap_match=0.8, ...),
        outputs=PairOutputs(likely_deal_structure="full_acquisition", ...),
    )

    summary = TargetMNAOutput(
        asset_id="a-vrtx",
        top_5_likely_acquirers=["merck", "pfizer", ...],
        pairs={"merck": pair},
    )
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pair-level scores
# ---------------------------------------------------------------------------

class PairScore(BaseModel):
    """Quantitative strategic fit scores for one acquirer × target pair (all 0–1).

    Each dimension is Optional so partial assessments are valid.
    Higher = better fit, except antitrust_risk and bidder_competition_risk
    where higher = more risk.

    Institutional-grade fields required for M&A engine (not just a watchlist):
    - asset_overlap, commercial_adjacency, rights_friction, cmc_fit,
      expected_synergies_millions, management_relationship_history,
      probability_of_approach
    """
    # Core strategic fit
    ta_fit: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    modality_fit: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pipeline_gap_match: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    loe_gap_match: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    commercial_synergy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    development_synergy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cmc_synergy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    geographic_synergy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    relationship_advantage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    asset_control_advantage: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    affordability_ratio: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    antitrust_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)       # higher = more risk
    bidder_competition_risk: Optional[float] = Field(default=None, ge=0.0, le=1.0)  # higher = more competition
    strategic_urgency: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    right_to_win_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # Institutional-grade additions (required for institutional pair table)
    asset_overlap: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # 0 = no pipeline overlap; 1 = identical indication/MoA (antitrust risk)
    commercial_adjacency: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # existing salesforce or co-promotion proximity to target indication
    rights_friction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # 0 = clean global rights; 1 = severely encumbered (COC clause, licensor consent)
    cmc_fit: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # acquirer's manufacturing capability matches target's modality CMC requirements
    expected_synergies_millions: Optional[float] = None
    # NPV of cost + revenue synergies (Year 3 run-rate, pre-tax)
    management_relationship_history: Optional[str] = None
    # "prior collaboration", "no prior contact", "hostile history", etc.
    probability_of_approach: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    # model-estimated P(acquirer makes approach within 18 months)


# ---------------------------------------------------------------------------
# Pair-level outputs
# ---------------------------------------------------------------------------

class PairOutputs(BaseModel):
    """Analyst-level narrative outputs for one acquirer × target pair."""
    likely_deal_structure: Optional[str] = None  # full_acquisition | asset_deal | license | option | partnership
    likely_premium_pct: Optional[float] = None  # e.g. 0.45 = 45% premium
    expected_deal_value_millions: Optional[float] = None
    reason_this_buyer_would_care: Optional[str] = None
    reason_this_buyer_would_not_bid: Optional[str] = None
    probability_buyer_is_top_bidder: Optional[float] = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Full pair record
# ---------------------------------------------------------------------------

class AcquirerTargetPair(BaseModel):
    """Full pair-level assessment for a specific acquirer × target combination.

    Stores both the quantitative scores (PairScore) and qualitative analyst
    outputs (PairOutputs). Designed to be computed on demand and cached
    alongside the target's AcquirableTarget profile.
    """
    acquirer_id: str
    target_asset_id: str

    scores: Optional[PairScore] = None
    outputs: Optional[PairOutputs] = None

    # Weighted composite score (computed externally from PairScore dimensions)
    composite_pair_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Target-level M&A output — aggregates across all evaluated acquirers
# ---------------------------------------------------------------------------

class TargetMNAOutput(BaseModel):
    """Top-level M&A assessment for a target across all evaluated acquirers.

    Sections:
      - Scores:      final_mna_score, pre_gate_score, mispricing_score
      - Rankings:    top_5_likely_acquirers, best_acquirer
      - Deal framing: recommended_deal_structure, expected_deal_value_range,
                      expected_takeout_premium_pct
      - Probability: implied_market_takeout_probability, our_takeout_probability
      - Decision:    key_bull_case, key_bear_case, top_3_diligence_questions,
                     top_3_kill_criteria, main_data_gaps, next_catalyst, action
      - Pairs:       dict[acquirer_id → AcquirerTargetPair]
    """
    asset_id: str

    # Scores
    final_mna_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    pre_gate_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    mispricing_score: Optional[float] = None  # positive = undervalued vs our estimate

    # Rankings
    top_5_likely_acquirers: list[str] = Field(default_factory=list)
    best_acquirer: Optional[str] = None

    # Deal framing
    recommended_deal_structure: Optional[str] = None
    expected_deal_value_range: Optional[str] = None  # e.g. "$2B–$4B"
    expected_takeout_premium_pct: Optional[float] = None

    # Takeout probability
    implied_market_takeout_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    our_takeout_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Decision support
    key_bull_case: Optional[str] = None
    key_bear_case: Optional[str] = None
    top_3_diligence_questions: list[str] = Field(default_factory=list)
    top_3_kill_criteria: list[str] = Field(default_factory=list)
    main_data_gaps: list[str] = Field(default_factory=list)
    next_catalyst: Optional[str] = None
    action: Optional[str] = None  # pursue | monitor | pass | diligence_needed

    # All evaluated pair assessments keyed by acquirer_id
    pairs: dict[str, AcquirerTargetPair] = Field(default_factory=dict)

from bve.se.ranking.engine import rank_profiles
from bve.se.schemas.contracts import AttractivenessTier, EvidenceConfidenceTier, PairwiseProfile


def _profile(asset_id: str, **updates) -> PairwiseProfile:
    values = dict(
        subject_id=asset_id,
        cohort_id="cohort:1",
        clinical_tier=AttractivenessTier.MODERATE,
        differentiation_tier=AttractivenessTier.MODERATE,
        durability_safety_tier=AttractivenessTier.MODERATE,
        development_maturity_tier=AttractivenessTier.MODERATE,
        operating_fit_tier=AttractivenessTier.MODERATE,
        buyer_advantage_tier=AttractivenessTier.MODERATE,
        transaction_path_tier=AttractivenessTier.MODERATE,
        diligence_burden_tier=AttractivenessTier.MODERATE,
        evidence_confidence=EvidenceConfidenceTier.HIGH,
    )
    values.update(updates)
    return PairwiseProfile(**values)


def test_rank_engine_emits_unique_ranks_only_for_unique_dominance() -> None:
    result = rank_profiles(
        [
            _profile("a", clinical_tier=AttractivenessTier.HIGH),
            _profile("b"),
            _profile("c", clinical_tier=AttractivenessTier.LOW),
        ]
    )
    ranked = {entry.asset_id: entry for entry in result.ranked}
    assert ranked["a"].rank == 1
    assert ranked["b"].rank == 2
    assert ranked["c"].rank == 3


def test_rank_engine_abstains_for_tradeoff_graph() -> None:
    result = rank_profiles(
        [
            _profile("a", clinical_tier=AttractivenessTier.HIGH),
            _profile("b", differentiation_tier=AttractivenessTier.HIGH),
        ]
    )
    assert all(entry.abstained for entry in result.ranked)
    assert all(entry.rank is None for entry in result.ranked)

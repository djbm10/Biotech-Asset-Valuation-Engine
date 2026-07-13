"""Within-cohort ranking from pairwise comparisons, with explicit abstention."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from bve.se.ranking.pairwise import compare_profiles
from bve.se.schemas.contracts import (
    AttractivenessTier,
    PairwiseOutcome,
    PairwiseProfile,
    RankedAsset,
    RankingResult,
)


def rank_profiles(profiles: Iterable[PairwiseProfile]) -> RankingResult:
    grouped: dict[str, list[PairwiseProfile]] = defaultdict(list)
    for profile in profiles:
        grouped[profile.cohort_id].append(profile)
    comparisons = []
    entries: list[RankedAsset] = []
    for cohort_id, cohort in grouped.items():
        wins: dict[str, int] = {profile.subject_id: 0 for profile in cohort}
        losses: dict[str, int] = {profile.subject_id: 0 for profile in cohort}
        abstained: set[str] = set()
        for index, left in enumerate(cohort):
            for right in cohort[index + 1 :]:
                comparison = compare_profiles(left, right)
                comparisons.append(comparison)
                if comparison.outcome == PairwiseOutcome.LEFT_PREFERRED:
                    wins[left.subject_id] += 1
                    losses[right.subject_id] += 1
                elif comparison.outcome == PairwiseOutcome.RIGHT_PREFERRED:
                    wins[right.subject_id] += 1
                    losses[left.subject_id] += 1
                elif comparison.outcome in {PairwiseOutcome.ABSTAIN, PairwiseOutcome.NOT_COMPARABLE}:
                    abstained.update({left.subject_id, right.subject_id})
        for profile in cohort:
            if profile.subject_id in abstained:
                entries.append(
                    RankedAsset(
                        asset_id=profile.subject_id,
                        cohort_id=cohort_id,
                        tier=AttractivenessTier.UNRANKED,
                        rationale="Pairwise evidence is preference-sensitive or incomplete.",
                        abstained=True,
                    )
                )
                continue
            score = wins[profile.subject_id]
            tier = (
                AttractivenessTier.HIGH
                if score == len(cohort) - 1 and len(cohort) > 1
                else AttractivenessTier.MODERATE
                if score > 0
                else AttractivenessTier.LOW
            )
            entries.append(
                RankedAsset(
                    asset_id=profile.subject_id,
                    cohort_id=cohort_id,
                    rank=None,
                    tier=tier,
                    rationale=f"Won {score} of {len(cohort) - 1} within-cohort comparisons.",
                )
            )
        rankable = [entry for entry in entries if entry.cohort_id == cohort_id and not entry.abstained]
        rankable.sort(key=lambda entry: wins[entry.asset_id], reverse=True)
        # A rank is emitted only when win counts are unique; ties remain a tiered partial order.
        scores = [wins[entry.asset_id] for entry in rankable]
        if len(scores) == len(set(scores)):
            for rank, entry in enumerate(rankable, start=1):
                entry.rank = rank
    return RankingResult(ranked=entries, comparisons=comparisons)

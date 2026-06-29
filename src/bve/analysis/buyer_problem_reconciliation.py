"""Reconcile the problem-in shortlist against the universe-out broad scan (spec 2.3).

Two lenses run independently per buyer:

- **Problem-in** (Chris structure): gated, ranked ``BuyerProblemShortlist`` for the
  buyer's stated gap.
- **Universe-out** (existing broad scan): ungated takeout-probability scores from
  ``ma_probability`` / ``weekly_ma_screen``.

This module is a pure, side-effect-free join that *describes* the relationship —
it never blends the two into one score, mirroring ``analysis/dual_track._cross_read``.
The most valuable label is ``scan_only``: a strong broad-scan hit that the buyer's
hard gates rejected — either a real miss or a prompt to widen the sandbox.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field

from bve.intelligence.science_thesis import BuyerProblemShortlist


class ReconciliationLabel(str, Enum):
    AGREED = "agreed"  # strong in both lenses
    PROBLEM_ONLY = "problem_only"  # problem-in shortlist, broad scan did not surface it
    SCAN_ONLY = "scan_only"  # strong broad-scan hit, failed the buyer's hard gates
    NEITHER = "neither"  # low/absent in both


class AssetReconciliation(BaseModel):
    asset_id: str
    label: ReconciliationLabel
    in_shortlist: bool = False
    shortlist_rank: int | None = None
    bd_actionability: float | None = None
    failed_buyer_gates: bool = False
    in_scan: bool = False
    scan_score: float | None = None


class BuyerProblemReconciliationReport(BaseModel):
    buyer_problem_id: str
    scan_threshold: float
    assets: list[AssetReconciliation] = Field(default_factory=list)

    def by_label(self, label: ReconciliationLabel) -> list[AssetReconciliation]:
        return [asset for asset in self.assets if asset.label == label]

    @property
    def scan_only(self) -> list[AssetReconciliation]:
        """Strong broad-scan hits the buyer's gates rejected — the key feedback loop."""
        return self.by_label(ReconciliationLabel.SCAN_ONLY)


def reconcile_buyer_problem(
    shortlist: BuyerProblemShortlist,
    scan_hits: Mapping[str, float],
    *,
    scan_threshold: float = 0.5,
) -> BuyerProblemReconciliationReport:
    """Join a problem-in shortlist with universe-out scan scores.

    ``scan_hits`` maps ``asset_id -> takeout-probability score`` from the broad
    scan (caller extracts these from ``WeeklyMAScreenResult``). An asset counts as
    a strong scan hit when its score is ``>= scan_threshold``.

    Labels:
      - ``agreed``        — on the shortlist *and* a strong scan hit
      - ``problem_only``  — on the shortlist, but not a strong scan hit
      - ``scan_only``     — a strong scan hit that is not on the shortlist
                            (failed the buyer's hard gates, or absent from intake)
      - ``neither``       — present somewhere but neither strong-scan nor shortlisted
    """
    ranked_ids = {entry.asset_id for entry in shortlist.ranked}
    excluded_ids = set(shortlist.excluded)
    ranks = {entry.asset_id: i + 1 for i, entry in enumerate(shortlist.ranked)}
    scores = {entry.asset_id: entry.bd_actionability for entry in shortlist.ranked}

    strong_scan = {aid for aid, score in scan_hits.items() if score >= scan_threshold}
    all_ids = ranked_ids | excluded_ids | set(scan_hits)

    assets: list[AssetReconciliation] = []
    for asset_id in sorted(all_ids):
        on_shortlist = asset_id in ranked_ids
        strong = asset_id in strong_scan

        if on_shortlist and strong:
            label = ReconciliationLabel.AGREED
        elif on_shortlist:
            label = ReconciliationLabel.PROBLEM_ONLY
        elif strong:
            label = ReconciliationLabel.SCAN_ONLY
        else:
            label = ReconciliationLabel.NEITHER

        assets.append(
            AssetReconciliation(
                asset_id=asset_id,
                label=label,
                in_shortlist=on_shortlist,
                shortlist_rank=ranks.get(asset_id),
                bd_actionability=scores.get(asset_id),
                failed_buyer_gates=asset_id in excluded_ids,
                in_scan=asset_id in scan_hits,
                scan_score=scan_hits.get(asset_id),
            )
        )

    return BuyerProblemReconciliationReport(
        buyer_problem_id=shortlist.buyer_problem_id,
        scan_threshold=scan_threshold,
        assets=assets,
    )

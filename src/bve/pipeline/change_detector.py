"""Material-change detection for watchlist memo triggering."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import StoredValuationDiff


class MaterialityRule(BaseModel):
    """Thresholds for deciding whether a weekly memo should be generated."""

    min_abs_delta_npv: float = Field(default=10.0, ge=0.0)
    min_relative_delta_npv_pct: Optional[float] = Field(default=None, ge=0.0)
    min_diff_count: int = Field(default=1, ge=1)


class MaterialChangeDetector:
    """Applies materiality rules to valuation diffs."""

    def __init__(self, rule: Optional[MaterialityRule] = None) -> None:
        self.rule = rule or MaterialityRule()

    def is_material(self, diff: StoredValuationDiff) -> bool:
        if abs(diff.delta_npv) >= self.rule.min_abs_delta_npv:
            return True

        if self.rule.min_relative_delta_npv_pct is None:
            return False

        before_npv = diff.valuation_before.get("rnpv_millions")
        if before_npv in (None, 0):
            return False

        rel_pct = abs((float(diff.delta_npv) / float(before_npv)) * 100.0)
        return rel_pct >= self.rule.min_relative_delta_npv_pct

    def material_diffs(self, diffs: list[StoredValuationDiff]) -> list[StoredValuationDiff]:
        return [diff for diff in diffs if self.is_material(diff)]

    def should_generate_weekly_memo(self, diffs: list[StoredValuationDiff]) -> bool:
        material = self.material_diffs(diffs)
        return len(material) >= self.rule.min_diff_count

"""Post-run reference coverage for canonical discovery outputs.

Reference identities are evaluation-only. They are never supplied to acquisition, query
compilation, candidate extraction, resolution, gating, or ranking.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bve.se.pipeline import SESearchResult


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class DiscoveryCoverageAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    benchmark_id: str
    tier: str
    canonical_asset: str
    aliases: tuple[str, ...] = ()
    covered: bool
    matched_asset_ids: tuple[str, ...] = ()
    matched_names: tuple[str, ...] = ()


class DiscoveryCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_path: str
    total_assets: int = Field(ge=0)
    total_covered: int = Field(ge=0)
    gold_total: int = Field(ge=0)
    gold_covered: int = Field(ge=0)
    silver_total: int = Field(ge=0)
    silver_covered: int = Field(ge=0)
    assets: tuple[DiscoveryCoverageAsset, ...]

    @property
    def recall(self) -> float:
        return self.total_covered / self.total_assets if self.total_assets else 1.0

    def meets_release_thresholds(self) -> bool:
        return self.gold_covered == self.gold_total and self.silver_covered >= max(
            0, self.silver_total - 1
        )


def evaluate_discovery_coverage(
    result: SESearchResult,
    reference_path: Path,
) -> DiscoveryCoverageReport:
    """Measure whether each reference identity appears in canonical asset names/aliases."""

    with Path(reference_path).open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    observed = [
        (
            asset.asset_id,
            asset.canonical_name,
            {
                _normalize(value)
                for value in [asset.canonical_name, *asset.aliases]
                if value
            },
        )
        for asset in result.candidates
    ]
    coverage_assets: list[DiscoveryCoverageAsset] = []
    for row in rows:
        aliases = tuple(
            value.strip() for value in row.get("aliases", "").split("|") if value.strip()
        )
        expected = {
            _normalize(value)
            for value in [row["canonical_asset"], *aliases]
            if value
        }
        matches = [
            (asset_id, name)
            for asset_id, name, observed_names in observed
            if expected & observed_names
        ]
        coverage_assets.append(
            DiscoveryCoverageAsset(
                benchmark_id=row["benchmark_id"],
                tier=row["reference_tier"].upper(),
                canonical_asset=row["canonical_asset"],
                aliases=aliases,
                covered=bool(matches),
                matched_asset_ids=tuple(asset_id for asset_id, _ in matches),
                matched_names=tuple(name for _, name in matches),
            )
        )
    gold = [asset for asset in coverage_assets if asset.tier == "GOLD"]
    silver = [asset for asset in coverage_assets if asset.tier == "SILVER"]
    return DiscoveryCoverageReport(
        reference_path=str(reference_path),
        total_assets=len(coverage_assets),
        total_covered=sum(asset.covered for asset in coverage_assets),
        gold_total=len(gold),
        gold_covered=sum(asset.covered for asset in gold),
        silver_total=len(silver),
        silver_covered=sum(asset.covered for asset in silver),
        assets=tuple(coverage_assets),
    )


__all__ = [
    "DiscoveryCoverageAsset",
    "DiscoveryCoverageReport",
    "evaluate_discovery_coverage",
]

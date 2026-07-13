"""Corpus evidence-coverage evaluation.

This is the decisive readiness metric for the acquisition sprint: **does at least one supporting
document exist in the corpus for each benchmark asset?** It is measured directly against the corpus,
independent of discovery extraction or ranking.

Boundary: this module reads the benchmark reference universe (which contains asset names) *only* to
score coverage after acquisition. It must never be imported by acquisition connectors or the query
compiler -- benchmark asset names must not become production search seeds.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from bve.se.acquisition.corpus_store import CorpusDocument, CorpusStore
from bve.se.acquisition.source_health import SourceHealthReport

_NCT_RE = re.compile(r"NCT\d{8}", re.IGNORECASE)
_SETID_RE = re.compile(r"setid=([0-9a-fA-F-]{10,})")
_MIN_CODE_LEN = 5


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _asset_tokens(canonical_asset: str, aliases: str, source_locator: str) -> tuple[list[str], list[str]]:
    """Return (normalized substring tokens, exact-id tokens) for one benchmark asset."""

    substrings: list[str] = []
    for raw in [canonical_asset, *aliases.split("|")]:
        norm = _normalize(raw)
        if len(norm) >= _MIN_CODE_LEN:
            substrings.append(norm)
    exact_ids = [nct.upper() for nct in _NCT_RE.findall(source_locator)]
    exact_ids += _SETID_RE.findall(source_locator)
    return list(dict.fromkeys(substrings)), list(dict.fromkeys(exact_ids))


class AssetCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    benchmark_id: str
    canonical_asset: str
    reference_tier: str
    covered: bool
    matched_document_id: str | None = None
    matched_source_family: str | None = None
    matched_token: str | None = None
    matched_source_families: list[str] = Field(default_factory=list)


class CorpusCoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assets: list[AssetCoverage] = Field(default_factory=list)
    gold_covered: int = 0
    gold_total: int = 0
    silver_covered: int = 0
    silver_total: int = 0

    @property
    def total_covered(self) -> int:
        return self.gold_covered + self.silver_covered

    @property
    def total_assets(self) -> int:
        return self.gold_total + self.silver_total

    def meets_release_thresholds(self) -> bool:
        """GOLD 5/5 and SILVER >= 15/16 per the handoff release gate."""

        gold_ok = self.gold_total > 0 and self.gold_covered == self.gold_total
        silver_ok = self.silver_total > 0 and self.silver_covered >= self.silver_total - 1
        return gold_ok and silver_ok


def _match_asset(
    substrings: list[str],
    exact_ids: list[str],
    normalized_docs: list[tuple[CorpusDocument, str]],
) -> tuple[CorpusDocument | None, str | None, list[str]]:
    """Return (first matching doc, first matching token, all matching source families)."""

    exact_norm = [_normalize(i) for i in exact_ids if _normalize(i)]
    tokens = exact_norm + substrings
    first: tuple[CorpusDocument, str] | None = None
    families: list[str] = []
    for document, blob in normalized_docs:
        hit = next((token for token in tokens if token in blob), None)
        if hit is None:
            continue
        if first is None:
            first = (document, hit)
        if document.source_family not in families:
            families.append(document.source_family)
    if first is None:
        return None, None, []
    return first[0], first[1], families


def evaluate_corpus_coverage(
    corpus_dir: Path,
    reference_universe_csv: Path,
) -> CorpusCoverageReport:
    """Score per-asset document presence in the corpus against the reference universe."""

    store = CorpusStore(Path(corpus_dir))
    normalized_docs = [
        (document, _normalize(f"{document.source_url} {document.title} {document.text}"))
        for document in store.documents()
    ]

    report = CorpusCoverageReport()
    with Path(reference_universe_csv).open() as handle:
        for row in csv.DictReader(handle):
            tier = row["reference_tier"].strip().upper()
            substrings, exact_ids = _asset_tokens(
                row["canonical_asset"], row.get("aliases", ""), row.get("source_locator", "")
            )
            doc, token, families = _match_asset(substrings, exact_ids, normalized_docs)
            covered = doc is not None
            report.assets.append(
                AssetCoverage(
                    benchmark_id=row["benchmark_id"],
                    canonical_asset=row["canonical_asset"],
                    reference_tier=tier,
                    covered=covered,
                    matched_document_id=doc.document_id if doc else None,
                    matched_source_family=doc.source_family if doc else None,
                    matched_token=token,
                    matched_source_families=families,
                )
            )
            if tier == "GOLD":
                report.gold_total += 1
                report.gold_covered += int(covered)
            elif tier == "SILVER":
                report.silver_total += 1
                report.silver_covered += int(covered)
    return report


def attribute_required_evidence(
    coverage: CorpusCoverageReport, health: SourceHealthReport
) -> SourceHealthReport:
    """Fill stage 3 (required_evidence_present) on each source family from coverage results."""

    families_with_evidence = {
        family for asset in coverage.assets for family in asset.matched_source_families
    }
    updated = [
        source.model_copy(
            update={"required_evidence_present": source.source_family in families_with_evidence}
        )
        for source in health.sources
    ]
    return SourceHealthReport(sources=updated)

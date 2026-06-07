"""
Coverage reporting for the empirical POS dataset.

CoverageReport exposes dataset composition, stratification-cell counts,
and sparse-cell warnings so analysts can assess confidence in predictions
before acting on them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from bve.empirical.pos_outcome import POSOutcomeRecord

logger = logging.getLogger(__name__)

# Minimum cell count below which a sparse-cell warning is emitted.
_DEFAULT_SPARSE_THRESHOLD = 5


@dataclass
class CellCoverage:
    """Coverage stats for one stratification cell."""
    cell_key: str          # human-readable tuple repr
    n: int
    n_success: int
    n_failure: int
    raw_rate: float
    smoothed_rate: float   # with table's alpha
    is_sparse: bool        # n < sparse_threshold


@dataclass
class CoverageReport:
    """
    Dataset composition and cell-coverage statistics.

    Inspect this before trusting any EmpiricalPOSEngine prediction to
    verify that the relevant stratification cell has adequate support.
    """
    # Dataset totals
    total_records: int
    total_success: int
    total_failure: int
    overall_success_rate: float

    # Breakdowns (field → count dict; None/unknown values omitted)
    by_phase: dict[str, int]
    by_therapeutic_area: dict[str, int]
    by_modality: dict[str, int]
    by_sponsor: dict[str, int]      # top-N sponsors by record count
    by_year: dict[str, int]

    # BaseRateTable cell coverage
    cells: list[CellCoverage]
    total_cells: int
    sparse_cells: list[CellCoverage]   # n < sparse_threshold
    sparse_threshold: int

    # Phase-level smoothed rates (convenience summary)
    phase_smoothed_rates: dict[str, float]

    def summary(self) -> str:
        """Multi-line text summary suitable for printing."""
        lines = [
            "=== EmpiricalPOS Coverage Report ===",
            f"  Total records      : {self.total_records}",
            f"  Success            : {self.total_success} ({self.overall_success_rate:.1%})",
            f"  Failure            : {self.total_failure}",
            "",
            "  By phase:",
        ]
        for phase, n in sorted(self.by_phase.items()):
            lines.append(f"    {phase:<12}: {n}")
        lines.append("")
        lines.append("  Phase smoothed base rates:")
        for phase, rate in sorted(self.phase_smoothed_rates.items()):
            lines.append(f"    {phase:<12}: {rate:.1%}")
        lines.append("")
        lines.append(f"  Stratification cells  : {self.total_cells}")
        if self.sparse_cells:
            lines.append(
                f"  ⚠️  Sparse cells (n<{self.sparse_threshold}): {len(self.sparse_cells)}"
            )
            for c in self.sparse_cells:
                lines.append(f"    {c.cell_key}: n={c.n}")
        else:
            lines.append(f"  No sparse cells (threshold={self.sparse_threshold})")
        return "\n".join(lines)

    def sparse_warnings(self) -> list[str]:
        """
        Return human-readable warning strings for each sparse cell.

        Empty list when all cells meet the threshold.
        """
        return [
            f"Sparse cell {c.cell_key}: n={c.n} (< threshold {self.sparse_threshold}); "
            f"predictions for this stratum fall back to a less-specific cell."
            for c in self.sparse_cells
        ]


def build_coverage_report(
    records: list[POSOutcomeRecord],
    base_rate_table,   # BaseRateTable (avoids circular import in type annotation)
    sparse_threshold: int = _DEFAULT_SPARSE_THRESHOLD,
    top_n_sponsors: int = 20,
) -> CoverageReport:
    """
    Build a CoverageReport from a list of outcome records and a BaseRateTable.

    Parameters
    ----------
    records:
        Outcome records (censored excluded).
    base_rate_table:
        A constructed BaseRateTable instance.
    sparse_threshold:
        Cells with n < threshold are flagged as sparse.
    top_n_sponsors:
        Maximum number of sponsors to list in by_sponsor breakdown.

    Returns
    -------
    CoverageReport
    """
    if not records:
        return CoverageReport(
            total_records=0, total_success=0, total_failure=0,
            overall_success_rate=0.0, by_phase={}, by_therapeutic_area={},
            by_modality={}, by_sponsor={}, by_year={}, cells=[],
            total_cells=0, sparse_cells=[], sparse_threshold=sparse_threshold,
            phase_smoothed_rates={},
        )

    total = len(records)
    success_count = sum(1 for r in records if r.success)
    failure_count = total - success_count

    # Breakdowns
    by_phase: dict[str, int] = {}
    by_ta: dict[str, int] = {}
    by_modality: dict[str, int] = {}
    by_sponsor: dict[str, int] = {}
    by_year: dict[str, int] = {}

    for rec in records:
        by_phase[rec.phase_at_entry] = by_phase.get(rec.phase_at_entry, 0) + 1

        ta = rec.therapeutic_area or "unknown"
        by_ta[ta] = by_ta.get(ta, 0) + 1

        mod = rec.modality or "unknown"
        by_modality[mod] = by_modality.get(mod, 0) + 1

        by_sponsor[rec.sponsor] = by_sponsor.get(rec.sponsor, 0) + 1

        yr = rec.outcome_date or "unknown"
        by_year[yr] = by_year.get(yr, 0) + 1

    # Top-N sponsors
    top_sponsors = dict(
        sorted(by_sponsor.items(), key=lambda kv: -kv[1])[:top_n_sponsors]
    )

    # Cell coverage from BaseRateTable
    cell_coverages: list[CellCoverage] = []
    table_summary = base_rate_table.summary()

    for key_str, stats in table_summary.items():
        n = stats["n"]
        n_s = stats["n_success"]
        raw = stats["raw_rate"] or 0.0
        smoothed = stats["smoothed_rate"]
        cell_coverages.append(CellCoverage(
            cell_key=key_str,
            n=n,
            n_success=n_s,
            n_failure=n - n_s,
            raw_rate=raw,
            smoothed_rate=smoothed,
            is_sparse=n < sparse_threshold,
        ))

    sparse = [c for c in cell_coverages if c.is_sparse]
    if sparse:
        logger.warning(
            "%d stratification cells are sparse (n < %d). Predictions will fall "
            "back to less-specific strata for these cells.",
            len(sparse), sparse_threshold,
        )

    return CoverageReport(
        total_records=total,
        total_success=success_count,
        total_failure=failure_count,
        overall_success_rate=round(success_count / total, 4) if total > 0 else 0.0,
        by_phase=dict(sorted(by_phase.items())),
        by_therapeutic_area=dict(sorted(by_ta.items())),
        by_modality=dict(sorted(by_modality.items())),
        by_sponsor=top_sponsors,
        by_year=dict(sorted(by_year.items())),
        cells=cell_coverages,
        total_cells=len(cell_coverages),
        sparse_cells=sparse,
        sparse_threshold=sparse_threshold,
        phase_smoothed_rates=base_rate_table.phase_rates(),
    )

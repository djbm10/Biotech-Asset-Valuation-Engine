"""
BaseRateTable — stratified empirical POS base rates with Laplace smoothing.

Stratification hierarchy (most specific → fallback):
    1. (phase, moa_precedent, biomarker_selected)
    2. (phase, moa_precedent)
    3. (phase, biomarker_selected)
    4. (phase,)
    5. Global fallback from PHASE_SUCCESS_RATES constant

Laplace (add-one / add-alpha) smoothing prevents zero-probability estimates
in sparse cells:
    smoothed_rate = (n_success + alpha) / (n_total + 2 * alpha)

Alpha defaults to 1.0 (Laplace). Use alpha < 1 for stronger data dominance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from bve.empirical.pos_outcome import POSOutcomeRecord
# Provenance import is lazy (inside get_with_provenance) to avoid any cycles.

logger = logging.getLogger(__name__)

# Fallback base rates from published industry data (Citeline/Biomedtracker)
# Used when the empirical dataset has insufficient records for a cell.
_PUBLISHED_FALLBACK: dict[str, float] = {
    "phase_1": 0.54,
    "phase_2": 0.32,
    "phase_3": 0.55,
    "nda_bla": 0.83,
}


@dataclass
class _Cell:
    """Raw counts for a single stratification cell."""
    n: int = 0
    n_success: int = 0

    def rate(self, alpha: float = 1.0) -> float:
        """Laplace-smoothed success rate."""
        return (self.n_success + alpha) / (self.n + 2 * alpha)


class BaseRateTable:
    """
    Stratified empirical base-rate lookup with Laplace smoothing and fallback.

    Usage
    -----
    records = load_outcome_records(csv_path)
    table = BaseRateTable(records, smoothing_alpha=1.0)
    rate = table.get("phase_2", moa_precedent="novel", biomarker_selected=True)
    """

    def __init__(
        self,
        records: list[POSOutcomeRecord],
        smoothing_alpha: float = 1.0,
        min_n_for_stratified: int = 3,
    ):
        """
        Parameters
        ----------
        records:
            Outcome records (censored rows excluded).
        smoothing_alpha:
            Laplace smoothing parameter α. Higher → more shrinkage toward 50%.
            Default 1.0 (add-one smoothing).
        min_n_for_stratified:
            Minimum raw count in a stratified cell before falling back to a
            less-specific stratum. Prevents noisy single-sample estimates.
        """
        if smoothing_alpha <= 0:
            raise ValueError(f"smoothing_alpha must be > 0, got {smoothing_alpha}")
        self.smoothing_alpha = smoothing_alpha
        self.min_n = min_n_for_stratified
        self._n_records = len(records)

        # Build all cells
        # Keys are tuples of varying specificity
        self._cells: dict[tuple, _Cell] = {}
        for rec in records:
            self._add_record(rec)

    def _key(self, *parts) -> tuple:
        return tuple(parts)

    def _add_record(self, rec: POSOutcomeRecord) -> None:
        phase = rec.phase_at_entry
        moa = rec.moa_precedent  # may be None
        bio = rec.biomarker_selected

        # Level 1: phase only
        k1 = self._key(phase)
        self._cells.setdefault(k1, _Cell())
        self._cells[k1].n += 1
        if rec.success:
            self._cells[k1].n_success += 1

        # Level 2: phase + moa (when moa available)
        if moa is not None:
            k2 = self._key(phase, moa)
            self._cells.setdefault(k2, _Cell())
            self._cells[k2].n += 1
            if rec.success:
                self._cells[k2].n_success += 1

        # Level 3: phase + biomarker
        k3 = self._key(phase, "biomarker", str(bio))
        self._cells.setdefault(k3, _Cell())
        self._cells[k3].n += 1
        if rec.success:
            self._cells[k3].n_success += 1

        # Level 4: phase + moa + biomarker (most specific)
        if moa is not None:
            k4 = self._key(phase, moa, "biomarker", str(bio))
            self._cells.setdefault(k4, _Cell())
            self._cells[k4].n += 1
            if rec.success:
                self._cells[k4].n_success += 1

    def get(
        self,
        phase: str,
        moa_precedent: Optional[str] = None,
        biomarker_selected: Optional[bool] = None,
    ) -> float:
        """
        Return Laplace-smoothed empirical success rate for the given stratification.

        Falls back from most-specific to least-specific stratum, then to the
        published industry-rate fallback when the empirical dataset is sparse.

        Parameters
        ----------
        phase:
            Phase key: "phase_1", "phase_2", "phase_3", or "nda_bla".
        moa_precedent:
            "validated", "partial", "novel", or None (ignored in stratification).
        biomarker_selected:
            True/False to stratify by biomarker enrichment; None (default) to
            skip biomarker stratification and use the broader phase/MoA cell.

        Returns
        -------
        float in (0, 1) — Laplace-smoothed empirical base rate.
        """
        candidates = []

        # Most specific: phase + moa + biomarker (only when biomarker is explicitly set)
        if moa_precedent is not None and biomarker_selected is not None:
            k_full = self._key(phase, moa_precedent, "biomarker", str(biomarker_selected))
            candidates.append(k_full)

        # phase + moa
        if moa_precedent is not None:
            candidates.append(self._key(phase, moa_precedent))

        # phase + biomarker (only when biomarker is explicitly set)
        if biomarker_selected is not None:
            candidates.append(self._key(phase, "biomarker", str(biomarker_selected)))

        # phase only
        candidates.append(self._key(phase))

        for key in candidates:
            cell = self._cells.get(key)
            if cell is not None and cell.n >= self.min_n:
                rate = cell.rate(self.smoothing_alpha)
                logger.debug(
                    "BaseRateTable.get(%s, moa=%s, bio=%s): key=%s n=%d → %.3f",
                    phase, moa_precedent, biomarker_selected, key, cell.n, rate
                )
                return round(rate, 4)

        # Fallback to published industry rates (with smoothing applied against prior counts)
        fallback = _PUBLISHED_FALLBACK.get(phase, 0.40)
        logger.debug(
            "BaseRateTable.get(%s, moa=%s, bio=%s): sparse — fallback=%.3f",
            phase, moa_precedent, biomarker_selected, fallback
        )
        return fallback

    def get_with_provenance(
        self,
        phase: str,
        moa_precedent: Optional[str] = None,
        biomarker_selected: Optional[bool] = None,
    ) -> tuple:
        """
        Like get() but also returns a LookupProvenance object.

        Returns
        -------
        (rate: float, provenance: LookupProvenance)
        """
        from bve.empirical.provenance import (
            LookupProvenance,
            TIER_FULL, TIER_PHASE_MOA, TIER_PHASE_BIO, TIER_PHASE, TIER_PUBLISHED,
        )

        # Build candidate list with tier labels
        candidates: list[tuple[tuple, str]] = []
        if moa_precedent is not None and biomarker_selected is not None:
            candidates.append(
                (self._key(phase, moa_precedent, "biomarker", str(biomarker_selected)), TIER_FULL)
            )
        if moa_precedent is not None:
            candidates.append((self._key(phase, moa_precedent), TIER_PHASE_MOA))
        if biomarker_selected is not None:
            candidates.append((self._key(phase, "biomarker", str(biomarker_selected)), TIER_PHASE_BIO))
        candidates.append((self._key(phase), TIER_PHASE))

        for key, tier in candidates:
            cell = self._cells.get(key)
            if cell is not None and cell.n >= self.min_n:
                rate = round(cell.rate(self.smoothing_alpha), 4)
                prov = LookupProvenance(
                    cell_key=str(key),
                    fallback_tier=tier,
                    n=cell.n,
                    n_success=cell.n_success,
                    smoothed_rate=rate,
                    is_published_fallback=False,
                )
                return rate, prov

        # Published fallback
        fallback = _PUBLISHED_FALLBACK.get(phase, 0.40)
        prov = LookupProvenance(
            cell_key=f"({phase!r},)",
            fallback_tier=TIER_PUBLISHED,
            n=0,
            n_success=0,
            smoothed_rate=fallback,
            is_published_fallback=True,
        )
        return fallback, prov

    def summary(self) -> dict:
        """
        Return a summary of all non-empty cells with their smoothed rates.

        Useful for inspection and debugging.
        """
        result = {}
        for key, cell in sorted(self._cells.items()):
            result[str(key)] = {
                "n": cell.n,
                "n_success": cell.n_success,
                "raw_rate": round(cell.n_success / cell.n, 4) if cell.n > 0 else None,
                "smoothed_rate": round(cell.rate(self.smoothing_alpha), 4),
            }
        return result

    @property
    def n_records(self) -> int:
        """Total number of outcome records in the table."""
        return self._n_records

    def phase_rates(self) -> dict[str, float]:
        """
        Return Laplace-smoothed phase-level base rates (no stratification).

        Convenience method for quick comparison to published industry benchmarks.
        """
        rates = {}
        for phase in _PUBLISHED_FALLBACK:
            key = self._key(phase)
            cell = self._cells.get(key)
            if cell and cell.n >= 1:
                rates[phase] = round(cell.rate(self.smoothing_alpha), 4)
            else:
                rates[phase] = _PUBLISHED_FALLBACK[phase]
        return rates

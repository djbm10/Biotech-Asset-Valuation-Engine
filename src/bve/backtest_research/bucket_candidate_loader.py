"""
bucket_candidate_loader — load hard-negative candidates from the curated CSV.

Reads ``candidate_universe_by_deal_bucket.csv`` and returns rows filtered by
bucket name.  Each row is returned as a dict compatible with the shape that
``CandidateUniverseBuilder._find_hard_negatives()`` expects:

    {"ticker": ..., "name": ..., "ta": ..., "modality": ..., "stage": ...}

Bucket matching: a row's ``bucket_name`` must equal ``deal_id`` OR be a prefix
of ``deal_id`` (e.g. bucket ``VRTX_SEMMA_2019`` matches deal ``VRTX_SEMMA_20190903``).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional


# Default CSV location relative to this file's project root
_DEFAULT_CSV = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "research/backtests/vrtx_regn_2010/curated/candidate_universe_by_deal_bucket.csv"
)


class BucketCandidateLoader:
    """
    Load deal-specific hard-negative candidates from the curated bucket CSV.

    Parameters
    ----------
    csv_path:
        Override the default CSV path.  If None, uses the project-relative
        default at ``research/backtests/vrtx_regn_2010/curated/
        candidate_universe_by_deal_bucket.csv``.

    Usage::

        loader = BucketCandidateLoader()
        candidates = loader.load_for_deal("VRTX_SEMMA_20190903")
        # returns list of dicts with keys: ticker, name, ta, modality, stage,
        #   bucket_type, why_plausible, rights_or_encumbrance_status
    """

    def __init__(self, csv_path: Optional["str | Path"] = None) -> None:
        self._csv_path = Path(csv_path) if csv_path else _DEFAULT_CSV
        self._rows: Optional[list[dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_for_deal(self, deal_id: str) -> list[dict[str, Any]]:
        """
        Return all candidate rows whose bucket matches ``deal_id``.

        Matching rules (in priority order):
        1. ``bucket_name == deal_id``
        2. ``deal_id.startswith(bucket_name)``  (e.g. bucket=VRTX_SEMMA_2019 matches
           deal=VRTX_SEMMA_20190903)

        Returns an empty list when no rows match or the CSV does not exist.
        Each returned dict has normalised keys ready for ``CandidateUniverseBuilder``.
        """
        all_rows = self._get_all_rows()
        matched: list[dict[str, Any]] = []
        for row in all_rows:
            bucket = row.get("bucket_name", "")
            if bucket == deal_id or deal_id.startswith(bucket):
                matched.append(self._normalise(row))
        return matched

    def available_buckets(self) -> list[str]:
        """Return the sorted list of unique bucket names in the CSV."""
        all_rows = self._get_all_rows()
        return sorted({r.get("bucket_name", "") for r in all_rows if r.get("bucket_name")})

    def is_available(self) -> bool:
        """Return True if the CSV file exists and is readable."""
        return self._csv_path.exists()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_all_rows(self) -> list[dict[str, Any]]:
        if self._rows is not None:
            return self._rows
        if not self._csv_path.exists():
            self._rows = []
            return self._rows
        rows: list[dict[str, Any]] = []
        with self._csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(dict(row))
        self._rows = rows
        return self._rows

    @staticmethod
    def _normalise(row: dict[str, Any]) -> dict[str, Any]:
        """
        Convert a CSV row to the shape expected by CandidateUniverseBuilder.

        Original CSV columns:
            candidate_ticker, candidate_target, therapeutic_area, modality,
            stage_at_snapshot, bucket_type, why_plausible,
            rights_or_encumbrance_status, estimated_market_cap_or_value_at_snapshot
        """
        ticker = row.get("candidate_ticker", "").strip()
        # Strip private_ prefix used for private companies (e.g. private_VCYT → VCYT)
        if ticker.startswith("private_"):
            ticker = ticker[len("private_"):]
        return {
            "ticker": ticker,
            "name": row.get("candidate_target", "").strip(),
            "ta": row.get("therapeutic_area", "").strip(),
            "modality": row.get("modality", "").strip(),
            "stage": row.get("stage_at_snapshot", "").strip(),
            "bucket_type": row.get("bucket_type", "").strip(),
            "why_plausible": row.get("why_plausible", "").strip(),
            "rights_or_encumbrance_status": row.get("rights_or_encumbrance_status", "").strip(),
            "approx_market_cap": row.get("estimated_market_cap_or_value_at_snapshot", "").strip(),
        }

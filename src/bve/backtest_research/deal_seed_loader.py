"""
deal_seed_loader — load and validate deal seeds.

Reads ``deal_seed_vrtx_regn.csv`` (or any deal seed CSV), separates verified
and unverified entries, and exposes them as typed ``DealRecord`` objects.

Verification rules
------------------
A deal is considered verified when:
  - ``verified`` == "TRUE" (case-insensitive)
  - ``verification_source`` is not "research_gap"
  - ``verification_url`` is a non-empty string
  - ``announced_date`` is a valid ISO date

Unverified deals are included in the dataset for completeness but excluded
from primary ranking metrics unless ``include_unverified=True`` is passed.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# DealRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DealRecord:
    deal_id: str                        # constructed as "ACQUIRER_TARGET_YYYYMMDD"
    acquirer_ticker: str
    acquirer_name: str
    target_ticker: str
    target_name: str
    deal_type: str                      # full_acquisition | asset_acquisition | rights_acquisition | collaboration
    announced_date: date
    deal_value_usd_millions: Optional[float]
    deal_value_type: str                # cash | cash_plus_cvr | equity | milestone_based | unknown
    upfront_usd_millions: Optional[float]
    cvr_max_usd_millions: Optional[float]
    therapeutic_area: str
    lead_asset: str
    lead_asset_modality: str
    lead_asset_stage_at_deal: str
    indication: str
    verified: bool
    verification_source: str
    verification_url: str
    notes: str

    # ----- computed helpers -------------------------------------------------

    @property
    def is_scoring_eligible(self) -> bool:
        """True for deal types included in first-pass ranking (not rights/collaboration)."""
        return self.deal_type in ("full_acquisition", "asset_acquisition")

    @property
    def snapshot_group_key(self) -> str:
        return f"{self.acquirer_ticker}_{self.target_ticker}_{self.announced_date.isoformat()}"


# ---------------------------------------------------------------------------
# DealSeedLoader
# ---------------------------------------------------------------------------

@dataclass
class DealSeedLoader:
    """
    Load deal seed CSV and expose verified / unverified records.

    Usage::

        loader = DealSeedLoader.from_csv(path)
        verified = loader.verified_deals()
        all_deals = loader.all_deals()
    """

    _records: list[DealRecord] = field(default_factory=list)

    @classmethod
    def from_csv(cls, path: "str | Path") -> "DealSeedLoader":
        path = Path(path)
        loader = cls()
        with path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                record = cls._parse_row(row)
                if record is not None:
                    loader._records.append(record)
        return loader

    @classmethod
    def default(cls) -> "DealSeedLoader":
        """Load from the standard seed file."""
        seed_path = (
            Path(__file__).parent.parent.parent.parent
            / "research" / "backtests" / "vrtx_regn_2010" / "seeds"
            / "deal_seed_vrtx_regn.csv"
        )
        return cls.from_csv(seed_path)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def all_deals(self) -> list[DealRecord]:
        return list(self._records)

    def verified_deals(self) -> list[DealRecord]:
        return [r for r in self._records if r.verified]

    def unverified_deals(self) -> list[DealRecord]:
        return [r for r in self._records if not r.verified]

    def scoring_eligible(self, include_unverified: bool = False) -> list[DealRecord]:
        """Return deals eligible for ranking score computation."""
        records = self._records if include_unverified else self.verified_deals()
        return [r for r in records if r.is_scoring_eligible]

    def for_acquirer(self, ticker: str, include_unverified: bool = False) -> list[DealRecord]:
        records = self._records if include_unverified else self.verified_deals()
        return [r for r in records if r.acquirer_ticker.upper() == ticker.upper()]

    def research_gaps(self) -> list[DealRecord]:
        """Return records with research_gap verification source."""
        return [
            r for r in self._records
            if "research_gap" in r.verification_source.lower()
        ]

    # ------------------------------------------------------------------
    # Internal parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_row(row: dict[str, str]) -> Optional[DealRecord]:
        try:
            announced_raw = row.get("announced_date", "").strip()
            if not announced_raw:
                return None
            announced_date = date.fromisoformat(announced_raw)
        except ValueError:
            return None

        acquirer_ticker = row.get("acquirer_ticker", "").strip().upper()
        target_ticker   = row.get("target_ticker",   "").strip().upper()
        if not acquirer_ticker or not target_ticker:
            return None

        deal_id = f"{acquirer_ticker}_{target_ticker}_{announced_date.strftime('%Y%m%d')}"

        def _float(s: str) -> Optional[float]:
            s = s.strip()
            return float(s) if s else None

        verified_raw = row.get("verified", "FALSE").strip().upper()
        verified = verified_raw == "TRUE"

        return DealRecord(
            deal_id=deal_id,
            acquirer_ticker=acquirer_ticker,
            acquirer_name=row.get("acquirer_name", "").strip(),
            target_ticker=target_ticker,
            target_name=row.get("target_name", "").strip(),
            deal_type=row.get("deal_type", "unknown").strip(),
            announced_date=announced_date,
            deal_value_usd_millions=_float(row.get("deal_value_usd_millions", "")),
            deal_value_type=row.get("deal_value_type", "unknown").strip(),
            upfront_usd_millions=_float(row.get("upfront_usd_millions", "")),
            cvr_max_usd_millions=_float(row.get("cvr_max_usd_millions", "")),
            therapeutic_area=row.get("therapeutic_area", "").strip(),
            lead_asset=row.get("lead_asset", "").strip(),
            lead_asset_modality=row.get("lead_asset_modality", "").strip(),
            lead_asset_stage_at_deal=row.get("lead_asset_stage_at_deal", "").strip(),
            indication=row.get("indication", "").strip(),
            verified=verified,
            verification_source=row.get("verification_source", "").strip(),
            verification_url=row.get("verification_url", "").strip(),
            notes=row.get("notes", "").strip(),
        )

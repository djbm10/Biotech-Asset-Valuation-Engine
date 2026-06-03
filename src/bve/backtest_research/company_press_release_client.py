"""
company_press_release_client — parse raw press release files.

Reads pre-downloaded press release text/HTML from:
  research/backtests/vrtx_regn_2010/raw/company_press_releases/<ticker>/

File naming convention:
  <TICKER>_<YYYYMMDD>_<slug>.txt

Returns structured data with provenance fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional


EXTRACTION_METHOD = "press_release_text"


@dataclass(frozen=True)
class PressReleaseRecord:
    ticker: str
    release_date: date
    title: str
    body_text: str
    source_url: str
    file_path: str


class CompanyPressReleaseClient:
    """
    Read and parse pre-downloaded company press releases.

    Files should be placed in:
      <raw_dir>/<TICKER>/<TICKER>_<YYYYMMDD>_<slug>.txt

    The file name encodes the publication date for provenance tracking.
    """

    def __init__(self, raw_dir: "str | Path") -> None:
        self._raw_dir = Path(raw_dir)

    def get_releases(
        self,
        ticker: str,
        snapshot_date: date,
        lookback_years: int = 5,
    ) -> list[PressReleaseRecord]:
        """
        Return press releases for ticker published before snapshot_date.

        Only reads files whose embedded date (from filename) <= snapshot_date.
        """
        ticker_dir = self._raw_dir / ticker.upper()
        if not ticker_dir.exists():
            return []

        cutoff_str = snapshot_date.isoformat().replace("-", "")
        lookback_str = str(snapshot_date.year - lookback_years)

        results: list[PressReleaseRecord] = []
        for txt_file in sorted(ticker_dir.glob("*.txt")):
            parts = txt_file.stem.split("_")
            if len(parts) < 2:
                continue
            date_part = parts[1]
            if len(date_part) != 8 or not date_part.isdigit():
                continue
            if date_part > cutoff_str:
                continue  # published after snapshot_date
            if date_part[:4] < lookback_str:
                continue  # too old
            try:
                release_date = date(int(date_part[:4]), int(date_part[4:6]), int(date_part[6:8]))
            except ValueError:
                continue
            body = txt_file.read_text(encoding="utf-8", errors="replace")
            title = body.split("\n")[0][:200]
            results.append(PressReleaseRecord(
                ticker=ticker.upper(),
                release_date=release_date,
                title=title,
                body_text=body,
                source_url="",  # would be populated from a URL file alongside .txt
                file_path=str(txt_file),
            ))
        return results

    def to_provenance_dict(
        self,
        record: PressReleaseRecord,
        snapshot_date: date,
        confidence: float = 0.90,
    ) -> dict[str, Any]:
        return {
            "source_url": record.source_url,
            "source_published_date": record.release_date.isoformat(),
            "data_as_of_date": record.release_date.isoformat(),
            "extraction_method": EXTRACTION_METHOD,
            "confidence": confidence,
        }

    def get_deal_announcement(
        self,
        acquirer_ticker: str,
        target_name: str,
        announced_date: date,
        tolerance_days: int = 3,
    ) -> Optional[PressReleaseRecord]:
        """
        Find a press release that matches a specific deal announcement.

        Looks for files within tolerance_days of announced_date whose
        body mentions target_name (case-insensitive).
        """
        lower_name = target_name.lower()
        releases = self.get_releases(acquirer_ticker, announced_date, lookback_years=0)
        # Expand window to include files on announced_date itself
        releases += self.get_releases(
            acquirer_ticker,
            date(announced_date.year, announced_date.month, announced_date.day),
        )
        for r in releases:
            days_diff = abs((r.release_date - announced_date).days)
            if days_diff <= tolerance_days and lower_name in r.body_text.lower():
                return r
        return None

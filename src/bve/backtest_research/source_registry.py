"""
source_registry — provenance schema and source reliability rules.

Every data row in the feature store must reference a source entry defined here.
Sources have a reliability tier (1=official, 2=regulatory, 3=secondary, 4=tertiary)
and required provenance fields that must be present and non-null.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Reliability tiers
# ---------------------------------------------------------------------------

class Reliability(IntEnum):
    OFFICIAL      = 1  # company press release, IR page
    REGULATORY    = 2  # SEC filing, ClinicalTrials.gov, FDA
    SECONDARY     = 3  # confirmed secondary source (reputable news, analyst)
    UNVERIFIED    = 4  # unverified / fallback
    RESEARCH_GAP  = 5  # placeholder — no source identified


# ---------------------------------------------------------------------------
# Required provenance fields for every data point
# ---------------------------------------------------------------------------

REQUIRED_PROVENANCE_FIELDS: tuple[str, ...] = (
    "source_url",
    "source_published_date",
    "data_as_of_date",
    "extraction_method",
    "confidence",
)

VALID_EXTRACTION_METHODS: frozenset[str] = frozenset({
    "press_release_text",
    "sec_filing_text",
    "ct_gov_api",
    "fda_api",
    "market_data_api",
    "news_article",
    "analyst_report",
    "annual_report",
    "manual_research",
})


# ---------------------------------------------------------------------------
# SourceEntry dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SourceEntry:
    source_id: str
    display_name: str
    reliability: Reliability
    extraction_method: str
    base_url: str = ""
    cik: Optional[str] = None
    notes: str = ""

    def validate_provenance(self, row: dict[str, Any]) -> list[str]:
        """Return list of validation error strings for a data row."""
        errors: list[str] = []
        for f in REQUIRED_PROVENANCE_FIELDS:
            if row.get(f) is None or row.get(f) == "":
                errors.append(f"Missing provenance field: {f}")
        em = row.get("extraction_method", "")
        if em and em not in VALID_EXTRACTION_METHODS:
            errors.append(f"Unknown extraction_method: {em!r}")
        return errors


# ---------------------------------------------------------------------------
# SourceRegistry
# ---------------------------------------------------------------------------

@dataclass
class SourceRegistry:
    """
    Registry of all data sources used in the backtest.

    Load from YAML::

        registry = SourceRegistry.from_yaml(path)

    Validate a data row::

        errs = registry.validate_row(row, source_id="clinicaltrials_gov")
    """

    _entries: dict[str, SourceEntry] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: "str | Path") -> "SourceRegistry":
        try:
            import yaml
        except ImportError as exc:
            raise ImportError("PyYAML is required for SourceRegistry.from_yaml") from exc
        path = Path(path)
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        registry = cls()
        for source_id, data in (raw.get("sources") or {}).items():
            reliability_raw = data.get("reliability", 4)
            try:
                reliability = Reliability(int(reliability_raw))
            except (ValueError, KeyError):
                reliability = Reliability.UNVERIFIED
            entry = SourceEntry(
                source_id=source_id,
                display_name=data.get("display_name", source_id),
                reliability=reliability,
                extraction_method=data.get("extraction_method", "manual_research"),
                base_url=data.get("base_url", ""),
                cik=data.get("cik"),
                notes=data.get("notes", ""),
            )
            registry._entries[source_id] = entry
        return registry

    @classmethod
    def default(cls) -> "SourceRegistry":
        """Load from the standard seed file bundled with this package."""
        seed_path = (
            Path(__file__).parent.parent.parent.parent
            / "research" / "backtests" / "vrtx_regn_2010" / "seeds" / "source_registry.yaml"
        )
        if seed_path.exists():
            return cls.from_yaml(seed_path)
        return cls()

    def get(self, source_id: str) -> Optional[SourceEntry]:
        return self._entries.get(source_id)

    def reliability(self, source_id: str) -> Reliability:
        entry = self._entries.get(source_id)
        return entry.reliability if entry else Reliability.RESEARCH_GAP

    def validate_row(self, row: dict[str, Any], source_id: str) -> list[str]:
        entry = self._entries.get(source_id)
        if entry is None:
            return [f"Unknown source_id: {source_id!r}"]
        return entry.validate_provenance(row)

    def all_source_ids(self) -> list[str]:
        return list(self._entries.keys())

    def __len__(self) -> int:
        return len(self._entries)

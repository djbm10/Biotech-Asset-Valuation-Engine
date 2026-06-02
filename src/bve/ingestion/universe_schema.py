"""
Universe schema validator (Phase 2M).

Validates targets.yaml and acquirers.yaml against the Phase 2M required schema,
applying data quality gates that are stricter than the basic loader validation.

New required fields (Phase 2M)
──────────────────────────────
Targets:
  lead_asset_stage    — canonical stage name (replaces/supplements lead_asset_phase)
  modality            — canonical modality (replaces/supplements lead_modality)
  aliases             — list of common names / former names
  cash_position_source — data provenance for cash figure (e.g. "sec_10q_2025q4")
  rd_expense_source   — data provenance for R&D expense (e.g. "sec_10k_2025")
  last_verified_date  — ISO date of last manual data check

Acquirers:
  strategic_priorities — list of business development focus areas
  patent_cliff_exposure — free-text description of upcoming LOE risk
  last_verified_date  — ISO date of last manual data check

Validation rules
────────────────
ID   Severity  Description
─────────────────────────────────────────────────────────────────────────────
T01  ERROR     Ticker format invalid (must be 1–6 uppercase alphanumeric)
T02  ERROR     Duplicate ticker
T03  WARNING   CIK is null/empty (required for all US-listed companies)
T04  WARNING   aliases list is empty or missing
T05  ERROR     therapeutic_areas contains value outside valid vocabulary
T06  ERROR     modality outside valid vocabulary
T07  ERROR     lead_asset is empty or missing
T08  ERROR     lead_asset_stage outside valid vocabulary
T09  WARNING   last_verified_date is stale (older than MAX_STALE_DAYS)
T10  WARNING   cash_position_source is empty or missing
T11  WARNING   rd_expense_source is empty or missing
T12  ERROR     Required target field missing

A01  ERROR     Acquirer ticker format invalid
A02  ERROR     Duplicate acquirer ticker
A03  WARNING   Acquirer CIK is null/empty
A04  ERROR     Acquirer therapeutic_areas unknown vocab
A05  ERROR     Acquirer modalities unknown vocab
A06  ERROR     deal_size_range_millions invalid (must be [min, max] with min < max)
A07  WARNING   Acquirer last_verified_date stale
A08  WARNING   strategic_priorities empty or missing
A09  WARNING   patent_cliff_exposure empty or missing
A10  ERROR     Required acquirer field missing

Profile quality scoring (targets)
──────────────────────────────────
10 binary dimensions × 0.1 each:
  1. cik is not null
  2. aliases is a non-empty list
  3. lead_asset is non-empty
  4. all therapeutic_areas in valid vocab
  5. modality in valid vocab
  6. lead_asset_stage in valid vocab
  7. last_verified_date within 90 days
  8. cash_position_source non-empty
  9. rd_expense_source non-empty
 10. notes field non-empty
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Vocabularies  (shared with universe_loader — kept in sync manually)
# ---------------------------------------------------------------------------

VALID_THERAPEUTIC_AREAS: frozenset[str] = frozenset({
    "oncology", "rare_disease", "immunology", "neuroscience",
    "cardiovascular", "infectious_disease", "metabolic",
    "dermatology", "ophthalmology", "respiratory", "hematology",
    "musculoskeletal", "gastrointestinal", "kidney_disease",
    "pain", "vaccines", "urology", "transplant", "other",
})

VALID_MODALITIES: frozenset[str] = frozenset({
    "small_molecule", "biologic", "antibody_drug_conjugate",
    "cell_gene", "cell_therapy", "rna", "gene_editing",
    "base_editing", "antisense", "mrna", "vaccine", "unknown",
})

VALID_LEAD_ASSET_STAGES: frozenset[str] = frozenset({
    "preclinical", "phase1", "phase2", "phase3", "commercial", "unknown",
})

VALID_MARKET_CAP_BUCKETS: frozenset[str] = frozenset({
    "nano", "micro", "small", "mid", "large",
})

VALID_COMPANY_TYPES: frozenset[str] = frozenset({
    "drug_developer", "platform", "commercial", "diagnostics", "tools", "services",
})

# How many days before last_verified_date triggers a warning
MAX_STALE_DAYS: int = 180
# How many days before last_verified_date triggers quality score penalty
_QUALITY_STALE_DAYS: int = 90

# Required fields for targets (Phase 2M schema)
TARGET_REQUIRED_FIELDS: tuple[str, ...] = (
    "ticker", "name", "therapeutic_areas",
    "lead_asset", "lead_asset_stage", "modality",
    "company_type", "market_cap_bucket", "last_verified_date",
)

# Required fields for acquirers (Phase 2M schema)
ACQUIRER_REQUIRED_FIELDS: tuple[str, ...] = (
    "ticker", "name", "therapeutic_areas", "modalities",
    "deal_size_range_millions", "last_verified_date",
)

_TICKER_RE = re.compile(r"^[A-Z0-9]{1,6}$")


# ---------------------------------------------------------------------------
# Issue types
# ---------------------------------------------------------------------------

@dataclass
class UniverseIssue:
    """One validation finding attached to a specific ticker."""
    rule: str
    ticker: str
    severity: str        # "error" | "warning"
    message: str
    field: Optional[str] = None

    def __str__(self) -> str:
        loc = f"[{self.ticker}]" + (f".{self.field}" if self.field else "")
        return f"{self.severity.upper():7}  {self.rule}  {loc}  {self.message}"


@dataclass
class UniverseValidationResult:
    """Aggregated outcome from validate_universe_schema()."""
    target_count: int = 0
    acquirer_count: int = 0
    issues: list[UniverseIssue] = field(default_factory=list)
    target_quality_scores: dict[str, float] = field(default_factory=dict)

    @property
    def errors(self) -> list[UniverseIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[UniverseIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def missing_cik_count(self) -> int:
        return sum(
            1 for i in self.issues
            if i.rule in ("T03", "A03") and i.severity == "warning"
        )

    @property
    def quality_score_median(self) -> Optional[float]:
        if not self.target_quality_scores:
            return None
        scores = sorted(self.target_quality_scores.values())
        n = len(scores)
        mid = n // 2
        if n % 2 == 1:
            return scores[mid]
        return (scores[mid - 1] + scores[mid]) / 2.0

    @property
    def suppression_reason_distribution(self) -> dict[str, int]:
        """Count of issues by rule code — useful for understanding suppression patterns."""
        from collections import Counter
        return dict(Counter(i.rule for i in self.issues))


# ---------------------------------------------------------------------------
# Profile quality score
# ---------------------------------------------------------------------------

def profile_quality_score(entry: dict, as_of_date: Optional[date] = None) -> float:
    """
    Compute a 0–1 quality score for a single target entry.

    10 binary dimensions × 0.1 each:
      1. cik is not null
      2. aliases is a non-empty list
      3. lead_asset is non-empty
      4. all therapeutic_areas in valid vocab
      5. modality in valid vocab
      6. lead_asset_stage in valid vocab
      7. last_verified_date within 90 days
      8. cash_position_source non-empty
      9. rd_expense_source non-empty
     10. notes field non-empty (len > 10)
    """
    _as_of = as_of_date or date.today()
    score = 0.0

    # 1. CIK
    cik = entry.get("cik")
    if cik and str(cik).strip():
        score += 0.1

    # 2. aliases
    aliases = entry.get("aliases")
    if isinstance(aliases, list) and len(aliases) > 0:
        score += 0.1

    # 3. lead_asset
    if entry.get("lead_asset", "").strip():
        score += 0.1

    # 4. therapeutic_areas vocab
    tas = entry.get("therapeutic_areas", [])
    if tas and all(t in VALID_THERAPEUTIC_AREAS for t in tas):
        score += 0.1

    # 5. modality vocab
    if entry.get("modality", "") in VALID_MODALITIES:
        score += 0.1

    # 6. lead_asset_stage vocab
    if entry.get("lead_asset_stage", "") in VALID_LEAD_ASSET_STAGES:
        score += 0.1

    # 7. last_verified_date within 90 days
    lv = entry.get("last_verified_date", "")
    try:
        lv_date = date.fromisoformat(str(lv))
        if (_as_of - lv_date).days <= _QUALITY_STALE_DAYS:
            score += 0.1
    except (ValueError, TypeError):
        pass

    # 8. cash_position_source
    if entry.get("cash_position_source", "").strip():
        score += 0.1

    # 9. rd_expense_source
    if entry.get("rd_expense_source", "").strip():
        score += 0.1

    # 10. notes
    notes = entry.get("notes", "")
    if isinstance(notes, str) and len(notes) > 10:
        score += 0.1

    return round(score, 2)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_universe_schema(
    targets_data: dict,
    acquirers_data: dict,
    as_of_date: Optional[str] = None,
) -> UniverseValidationResult:
    """
    Validate targets and acquirers data dicts against the Phase 2M schema.

    Parameters
    ----------
    targets_data:
        Dict loaded from targets.yaml (top-level ticker keys).
    acquirers_data:
        Dict loaded from acquirers.yaml (top-level ticker keys).
    as_of_date:
        ISO date string for staleness checks. Defaults to today.
    """
    _as_of = date.fromisoformat(as_of_date) if as_of_date else date.today()
    result = UniverseValidationResult()

    # ── Validate targets ───────────────────────────────────────────────────
    seen_tickers: set[str] = set()
    for key, entry in (targets_data or {}).items():
        if not isinstance(entry, dict):
            continue
        result.target_count += 1
        ticker = str(entry.get("ticker", key) or key).strip()

        _validate_target(ticker, entry, _as_of, seen_tickers, result)
        result.target_quality_scores[ticker] = profile_quality_score(entry, _as_of)

    # ── Validate acquirers ─────────────────────────────────────────────────
    seen_acq: set[str] = set()
    for key, entry in (acquirers_data or {}).items():
        if not isinstance(entry, dict):
            continue
        result.acquirer_count += 1
        ticker = str(entry.get("ticker", key) or key).strip()
        _validate_acquirer(ticker, entry, _as_of, seen_acq, result)

    return result


# ---------------------------------------------------------------------------
# Target validation helpers
# ---------------------------------------------------------------------------

def _validate_target(
    ticker: str,
    entry: dict,
    as_of: date,
    seen: set[str],
    result: UniverseValidationResult,
) -> None:
    def err(rule: str, msg: str, fld: Optional[str] = None) -> None:
        result.issues.append(UniverseIssue(rule=rule, ticker=ticker, severity="error", message=msg, field=fld))

    def warn(rule: str, msg: str, fld: Optional[str] = None) -> None:
        result.issues.append(UniverseIssue(rule=rule, ticker=ticker, severity="warning", message=msg, field=fld))

    # T01 — ticker format
    if not _TICKER_RE.match(ticker):
        err("T01", f"ticker '{ticker}' must be 1–6 uppercase alphanumeric characters", "ticker")

    # T02 — duplicate
    upper = ticker.upper()
    if upper in seen:
        err("T02", f"Duplicate ticker '{ticker}'", "ticker")
    seen.add(upper)

    # T12 — required fields
    for fld in TARGET_REQUIRED_FIELDS:
        val = entry.get(fld)
        if val is None or (isinstance(val, (str, list)) and not val):
            err("T12", f"Required field '{fld}' is missing or empty", fld)

    # T03 — CIK
    cik = entry.get("cik")
    if not cik or not str(cik).strip():
        warn("T03", "cik is null or empty; required for US-listed filers", "cik")

    # T04 — aliases
    aliases = entry.get("aliases")
    if not aliases or (isinstance(aliases, list) and len(aliases) == 0):
        warn("T04", "aliases list is empty or missing", "aliases")

    # T05 — therapeutic_areas vocab
    tas = entry.get("therapeutic_areas") or []
    for ta in tas:
        if ta not in VALID_THERAPEUTIC_AREAS:
            err("T05", f"Unknown therapeutic_area '{ta}' (valid: {sorted(VALID_THERAPEUTIC_AREAS)[:5]}…)", "therapeutic_areas")

    # T06 — modality vocab
    modality = entry.get("modality", "")
    if modality and modality not in VALID_MODALITIES:
        err("T06", f"Unknown modality '{modality}'", "modality")

    # T07 — lead_asset
    if not entry.get("lead_asset", "").strip():
        err("T07", "lead_asset is empty or missing", "lead_asset")

    # T08 — lead_asset_stage vocab
    stage = entry.get("lead_asset_stage", "")
    if stage and stage not in VALID_LEAD_ASSET_STAGES:
        err("T08", f"Unknown lead_asset_stage '{stage}'", "lead_asset_stage")

    # T09 — stale last_verified_date
    lv = entry.get("last_verified_date", "")
    try:
        lv_date = date.fromisoformat(str(lv))
        if (as_of - lv_date).days > MAX_STALE_DAYS:
            warn("T09", f"last_verified_date {lv} is stale (>{MAX_STALE_DAYS}d ago)", "last_verified_date")
    except (ValueError, TypeError):
        if lv:
            err("T09", f"last_verified_date '{lv}' is not a valid ISO date", "last_verified_date")

    # T10 — cash_position_source
    if not entry.get("cash_position_source", "").strip():
        warn("T10", "cash_position_source is empty or missing", "cash_position_source")

    # T11 — rd_expense_source
    if not entry.get("rd_expense_source", "").strip():
        warn("T11", "rd_expense_source is empty or missing", "rd_expense_source")


# ---------------------------------------------------------------------------
# Acquirer validation helpers
# ---------------------------------------------------------------------------

def _validate_acquirer(
    ticker: str,
    entry: dict,
    as_of: date,
    seen: set[str],
    result: UniverseValidationResult,
) -> None:
    def err(rule: str, msg: str, fld: Optional[str] = None) -> None:
        result.issues.append(UniverseIssue(rule=rule, ticker=ticker, severity="error", message=msg, field=fld))

    def warn(rule: str, msg: str, fld: Optional[str] = None) -> None:
        result.issues.append(UniverseIssue(rule=rule, ticker=ticker, severity="warning", message=msg, field=fld))

    # A01 — ticker format
    if not _TICKER_RE.match(ticker):
        err("A01", f"ticker '{ticker}' must be 1–6 uppercase alphanumeric characters", "ticker")

    # A02 — duplicate
    upper = ticker.upper()
    if upper in seen:
        err("A02", f"Duplicate acquirer ticker '{ticker}'", "ticker")
    seen.add(upper)

    # A10 — required fields
    for fld in ACQUIRER_REQUIRED_FIELDS:
        val = entry.get(fld)
        if val is None or (isinstance(val, (str, list)) and not val):
            err("A10", f"Required field '{fld}' is missing or empty", fld)

    # A03 — CIK
    cik = entry.get("cik")
    if not cik or not str(cik).strip():
        warn("A03", "cik is null or empty", "cik")

    # A04 — therapeutic_areas vocab
    tas = entry.get("therapeutic_areas") or []
    for ta in tas:
        if ta not in VALID_THERAPEUTIC_AREAS:
            err("A04", f"Unknown therapeutic_area '{ta}'", "therapeutic_areas")

    # A05 — modalities vocab
    mods = entry.get("modalities") or []
    for mod in mods:
        if mod not in VALID_MODALITIES:
            err("A05", f"Unknown modality '{mod}'", "modalities")

    # A06 — deal_size_range_millions
    dsr = entry.get("deal_size_range_millions")
    if dsr is not None:
        if (
            not isinstance(dsr, (list, tuple))
            or len(dsr) != 2
            or not all(isinstance(x, (int, float)) for x in dsr)
            or float(dsr[0]) >= float(dsr[1])
        ):
            err("A06", f"deal_size_range_millions must be [min, max] with min < max, got {dsr!r}", "deal_size_range_millions")

    # A07 — stale last_verified_date
    lv = entry.get("last_verified_date", "")
    try:
        lv_date = date.fromisoformat(str(lv))
        if (as_of - lv_date).days > MAX_STALE_DAYS:
            warn("A07", f"last_verified_date {lv} is stale (>{MAX_STALE_DAYS}d ago)", "last_verified_date")
    except (ValueError, TypeError):
        if lv:
            err("A07", f"last_verified_date '{lv}' is not a valid ISO date", "last_verified_date")

    # A08 — strategic_priorities
    sp = entry.get("strategic_priorities")
    if not sp or (isinstance(sp, list) and len(sp) == 0):
        warn("A08", "strategic_priorities is empty or missing", "strategic_priorities")

    # A09 — patent_cliff_exposure
    pce = entry.get("patent_cliff_exposure", "")
    if not pce or not str(pce).strip():
        warn("A09", "patent_cliff_exposure is empty or missing", "patent_cliff_exposure")


# ---------------------------------------------------------------------------
# YAML loading helpers
# ---------------------------------------------------------------------------

def load_and_validate(
    targets_path: str | Path,
    acquirers_path: str | Path,
    as_of_date: Optional[str] = None,
) -> UniverseValidationResult:
    """Load YAML files and validate them. Convenience wrapper for the CLI."""
    import yaml  # type: ignore[import-untyped]

    targets_data: dict = {}
    acquirers_data: dict = {}

    tp = Path(targets_path)
    ap = Path(acquirers_path)

    if tp.exists():
        targets_data = yaml.safe_load(tp.read_text(encoding="utf-8")) or {}

    if ap.exists():
        acquirers_data = yaml.safe_load(ap.read_text(encoding="utf-8")) or {}

    return validate_universe_schema(targets_data, acquirers_data, as_of_date)

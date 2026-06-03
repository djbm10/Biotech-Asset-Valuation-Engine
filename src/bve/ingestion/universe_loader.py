"""
Universe loader for biotech M&A target and acquirer universe.

Loads and validates the four universe YAML files:
  targets.yaml          → dict[str, TargetEntry]
  acquirers.yaml        → dict[str, AcquirerEntry]
  company_aliases.yaml  → dict[str, CompanyAliases]
  manual_overrides.yaml → dict[str, dict]

Strict validation: every loaded universe produces a UniverseValidationResult
that lists ALL errors and warnings, not just the first one.

Use validate_universe() after loading to surface quality issues before
they silently corrupt downstream scoring and pair matching.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Valid vocabulary sets
# ---------------------------------------------------------------------------

VALID_PHASES: frozenset[str] = frozenset({
    "preclinical", "phase1", "phase2", "phase3", "commercial", "unknown",
})

VALID_COMPANY_TYPES: frozenset[str] = frozenset({
    "drug_developer", "platform", "commercial", "diagnostics", "tools", "services",
})

VALID_MODALITIES: frozenset[str] = frozenset({
    "small_molecule", "biologic", "antibody_drug_conjugate",
    "cell_gene", "cell_therapy", "rna", "gene_editing",
    "base_editing", "antisense", "mrna", "vaccine", "unknown",
})

VALID_TAS: frozenset[str] = frozenset({
    "oncology", "rare_disease", "immunology", "neuroscience",
    "cardiovascular", "infectious_disease", "metabolic",
    "dermatology", "ophthalmology", "respiratory", "hematology",
    "musculoskeletal", "gastrointestinal", "kidney_disease",
    "pain", "vaccines", "urology", "transplant", "other",
})

VALID_STAGES: frozenset[str] = VALID_PHASES  # alias for readability
VALID_MARKET_CAP_BUCKETS: frozenset[str] = frozenset({
    "nano", "micro", "small", "mid", "large",
})

# Required target fields
_TARGET_REQUIRED = {
    "name", "exchange", "company_type", "therapeutic_areas",
    "lead_asset", "lead_asset_phase", "lead_modality",
    "lead_indication", "is_single_asset_company", "include_in_screen",
}

# Required acquirer fields
_ACQUIRER_REQUIRED = {
    "name", "therapeutic_areas", "modalities",
    "deal_size_range_millions", "preferred_stages", "include_as_acquirer",
}


# ---------------------------------------------------------------------------
# Typed dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TargetEntry:
    """One row from targets.yaml, fully typed."""
    ticker: str
    name: str
    exchange: str
    company_type: str
    therapeutic_areas: list[str]
    lead_asset: str
    lead_asset_phase: str
    lead_modality: str
    lead_indication: str
    is_single_asset_company: bool
    include_in_screen: bool
    # Optional
    cik: Optional[str] = None
    market_cap_bucket: Optional[str] = None
    platform_type: Optional[str] = None
    has_partner_encumbrance: Optional[bool] = None
    notes: Optional[str] = None


@dataclass
class AcquirerEntry:
    """One row from acquirers.yaml, fully typed."""
    ticker: str
    name: str
    therapeutic_areas: list[str]
    modalities: list[str]
    deal_size_range_millions: tuple[float, float]
    preferred_stages: list[str]
    include_as_acquirer: bool
    # Optional
    cik: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class CompanyAliases:
    """One row from company_aliases.yaml."""
    ticker: str
    canonical_name: str
    aliases: list[str]
    assets: list[str]
    cik: Optional[str] = None


# ---------------------------------------------------------------------------
# Validation types
# ---------------------------------------------------------------------------


@dataclass
class UniverseValidationIssue:
    ticker: str
    field: str
    message: str
    severity: str  # "error" | "warning"


@dataclass
class UniverseValidationResult:
    valid: bool
    errors: list[UniverseValidationIssue]
    warnings: list[UniverseValidationIssue]
    target_count: int
    acquirer_count: int
    targets_included: int
    acquirers_included: int

    def all_issues(self) -> list[UniverseValidationIssue]:
        return self.errors + self.warnings

    def summary(self) -> str:
        """Short human-readable validation result."""
        status = "VALID" if self.valid else "INVALID"
        return (
            f"Universe validation: {status}\n"
            f"  Errors:   {len(self.errors)}\n"
            f"  Warnings: {len(self.warnings)}\n"
            f"  Targets:  {self.target_count} ({self.targets_included} in screen)\n"
            f"  Acquirers:{self.acquirer_count} ({self.acquirers_included} active)"
        )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Universe file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_targets(path: Path) -> dict[str, TargetEntry]:
    """
    Load and parse targets.yaml.

    Returns dict[ticker → TargetEntry]. Does NOT validate — call
    validate_universe() separately to get all issues at once.
    """
    raw = _load_yaml(path)
    result = {}
    for ticker, data in raw.items():
        if not isinstance(data, dict):
            continue
        entry = TargetEntry(
            ticker=ticker,
            name=data.get("name", ""),
            exchange=data.get("exchange", ""),
            company_type=data.get("company_type", ""),
            therapeutic_areas=list(data.get("therapeutic_areas") or []),
            lead_asset=data.get("lead_asset", ""),
            lead_asset_phase=data.get("lead_asset_phase", ""),
            lead_modality=data.get("lead_modality", ""),
            lead_indication=data.get("lead_indication", ""),
            is_single_asset_company=bool(data.get("is_single_asset_company", False)),
            include_in_screen=bool(data.get("include_in_screen", False)),
            cik=str(data["cik"]) if data.get("cik") is not None else None,
            market_cap_bucket=data.get("market_cap_bucket"),
            platform_type=data.get("platform_type"),
            has_partner_encumbrance=data.get("has_partner_encumbrance"),
            notes=data.get("notes"),
        )
        result[ticker] = entry
    return result


def load_acquirers(path: Path) -> dict[str, AcquirerEntry]:
    """Load and parse acquirers.yaml."""
    raw = _load_yaml(path)
    result = {}
    for ticker, data in raw.items():
        if not isinstance(data, dict):
            continue
        deal_range = data.get("deal_size_range_millions") or [0, 0]
        if isinstance(deal_range, list) and len(deal_range) == 2:
            deal_range_tuple = (float(deal_range[0]), float(deal_range[1]))
        else:
            deal_range_tuple = (0.0, 0.0)
        entry = AcquirerEntry(
            ticker=ticker,
            name=data.get("name", ""),
            therapeutic_areas=list(data.get("therapeutic_areas") or []),
            modalities=list(data.get("modalities") or []),
            deal_size_range_millions=deal_range_tuple,
            preferred_stages=list(data.get("preferred_stages") or []),
            include_as_acquirer=bool(data.get("include_as_acquirer", False)),
            cik=str(data["cik"]) if data.get("cik") is not None else None,
            notes=data.get("notes"),
        )
        result[ticker] = entry
    return result


def load_aliases(path: Path) -> dict[str, CompanyAliases]:
    """Load and parse company_aliases.yaml."""
    raw = _load_yaml(path)
    result = {}
    for ticker, data in raw.items():
        if not isinstance(data, dict):
            continue
        entry = CompanyAliases(
            ticker=ticker,
            canonical_name=data.get("canonical_name", ""),
            aliases=list(data.get("aliases") or []),
            assets=list(data.get("assets") or []),
            cik=str(data["cik"]) if data.get("cik") is not None else None,
        )
        result[ticker] = entry
    return result


def load_manual_overrides(path: Path) -> dict[str, dict]:
    """Load manual_overrides.yaml. Returns raw dict — no typed parsing."""
    return _load_yaml(path)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_universe(
    targets: dict[str, TargetEntry],
    acquirers: dict[str, AcquirerEntry],
    aliases: Optional[dict[str, CompanyAliases]] = None,
) -> UniverseValidationResult:
    """
    Validate the loaded universe. Returns a result with ALL errors and warnings.

    Checks:
      - Required fields present and non-empty
      - lead_asset_phase in VALID_PHASES
      - company_type in VALID_COMPANY_TYPES
      - lead_modality in VALID_MODALITIES
      - therapeutic_areas all in VALID_TAS
      - preferred_stages all in VALID_STAGES
      - modalities all in VALID_MODALITIES
      - market_cap_bucket in VALID_MARKET_CAP_BUCKETS (warning if set but invalid)
      - Ticker key matches ticker field (warning)
      - Same ticker in both targets and acquirers (warning)
      - Duplicate aliases across companies (warning)
    """
    issues: list[UniverseValidationIssue] = []

    def err(ticker: str, fname: str, msg: str) -> None:
        issues.append(UniverseValidationIssue(ticker, fname, msg, "error"))

    def warn(ticker: str, fname: str, msg: str) -> None:
        issues.append(UniverseValidationIssue(ticker, fname, msg, "warning"))

    # ── Validate targets ─────────────────────────────────────────────────
    for ticker, t in targets.items():
        # Required fields
        for fname in _TARGET_REQUIRED:
            val = getattr(t, fname)
            if val is None or val == "" or val == []:
                err(ticker, fname, f"Required field '{fname}' is missing or empty.")

        if t.lead_asset_phase and t.lead_asset_phase not in VALID_PHASES:
            err(ticker, "lead_asset_phase",
                f"'{t.lead_asset_phase}' is not in VALID_PHASES: {sorted(VALID_PHASES)}")

        if t.company_type and t.company_type not in VALID_COMPANY_TYPES:
            err(ticker, "company_type",
                f"'{t.company_type}' is not in VALID_COMPANY_TYPES: {sorted(VALID_COMPANY_TYPES)}")

        if t.lead_modality and t.lead_modality not in VALID_MODALITIES:
            err(ticker, "lead_modality",
                f"'{t.lead_modality}' is not in VALID_MODALITIES: {sorted(VALID_MODALITIES)}")

        for ta in t.therapeutic_areas:
            if ta not in VALID_TAS:
                err(ticker, "therapeutic_areas",
                    f"TA '{ta}' is not in VALID_TAS: {sorted(VALID_TAS)}")

        if t.market_cap_bucket and t.market_cap_bucket not in VALID_MARKET_CAP_BUCKETS:
            warn(ticker, "market_cap_bucket",
                 f"'{t.market_cap_bucket}' not in {sorted(VALID_MARKET_CAP_BUCKETS)}")

        if t.ticker != ticker:
            warn(ticker, "ticker", f"Key '{ticker}' ≠ ticker field '{t.ticker}'")

    # ── Validate acquirers ────────────────────────────────────────────────
    for ticker, a in acquirers.items():
        for fname in _ACQUIRER_REQUIRED:
            val = getattr(a, fname)
            if val is None or val == "" or val == [] or val == (0.0, 0.0):
                err(ticker, fname, f"Required field '{fname}' is missing or empty.")

        for ta in a.therapeutic_areas:
            if ta not in VALID_TAS:
                err(ticker, "therapeutic_areas",
                    f"TA '{ta}' is not in VALID_TAS: {sorted(VALID_TAS)}")

        for mod in a.modalities:
            if mod not in VALID_MODALITIES:
                err(ticker, "modalities",
                    f"Modality '{mod}' is not in VALID_MODALITIES: {sorted(VALID_MODALITIES)}")

        for stage in a.preferred_stages:
            if stage not in VALID_STAGES:
                err(ticker, "preferred_stages",
                    f"Stage '{stage}' is not in VALID_STAGES: {sorted(VALID_STAGES)}")

        dr = a.deal_size_range_millions
        if dr[1] <= dr[0]:
            warn(ticker, "deal_size_range_millions",
                 f"Upper bound {dr[1]} ≤ lower bound {dr[0]}")

    # ── Cross-checks ──────────────────────────────────────────────────────
    both = set(targets.keys()) & set(acquirers.keys())
    for ticker in both:
        warn(ticker, "ticker",
             "Ticker appears in both targets and acquirers — verify intent.")

    # ── Alias deduplication ───────────────────────────────────────────────
    if aliases:
        alias_to_tickers: dict[str, list[str]] = defaultdict(list)
        for ticker, ca in aliases.items():
            for alias in ca.aliases:
                alias_to_tickers[alias.lower()].append(ticker)
        for alias, tickers in alias_to_tickers.items():
            if len(tickers) > 1:
                warn(tickers[0], "aliases",
                     f"Alias '{alias}' appears for multiple tickers: {tickers}")

    # ── Compute result ────────────────────────────────────────────────────
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    return UniverseValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        target_count=len(targets),
        acquirer_count=len(acquirers),
        targets_included=sum(1 for t in targets.values() if t.include_in_screen),
        acquirers_included=sum(1 for a in acquirers.values() if a.include_as_acquirer),
    )


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------


def universe_summary(
    targets: dict[str, TargetEntry],
    acquirers: dict[str, AcquirerEntry],
) -> str:
    """
    Print a human-readable universe summary.

    Example output::

        Targets loaded: 50
        Included in screen: 50
        Acquirers loaded: 23

        Targets missing lead asset: 0
        Targets missing phase: 0

        Top therapeutic areas:
          oncology: 16
          rare_disease: 12
          ...

        Lead asset phases:
          phase3: 14
          commercial: 14
          phase2: 13
          phase1: 5
          ...

        Modalities:
          small_molecule: 21
          biologic: 11
          ...

        Acquirers:
          PFE   Pfizer                      deal range: $1,000M – $60,000M
          ...
    """
    included = [t for t in targets.values() if t.include_in_screen]
    missing_lead = sum(1 for t in included if not t.lead_asset)
    missing_phase = sum(1 for t in included if not t.lead_asset_phase)

    ta_counts: Counter = Counter()
    for t in included:
        for ta in t.therapeutic_areas:
            ta_counts[ta] += 1

    phase_counts: Counter = Counter(t.lead_asset_phase for t in included if t.lead_asset_phase)
    modality_counts: Counter = Counter(t.lead_modality for t in included if t.lead_modality)
    mcap_counts: Counter = Counter(t.market_cap_bucket for t in included if t.market_cap_bucket)

    lines = [
        f"Targets loaded:         {len(targets)}",
        f"Included in screen:     {len(included)}",
        f"Acquirers loaded:       {len(acquirers)}",
        f"Acquirers active:       {sum(1 for a in acquirers.values() if a.include_as_acquirer)}",
        "",
        f"Targets missing lead asset: {missing_lead}",
        f"Targets missing phase:      {missing_phase}",
        "",
        "Top therapeutic areas:",
    ]
    for ta, count in ta_counts.most_common(10):
        lines.append(f"  {ta:<25} {count}")

    lines.append("")
    lines.append("Lead asset phases:")
    for phase, count in phase_counts.most_common():
        lines.append(f"  {phase:<20} {count}")

    lines.append("")
    lines.append("Modalities:")
    for mod, count in modality_counts.most_common():
        lines.append(f"  {mod:<30} {count}")

    if mcap_counts:
        lines.append("")
        lines.append("Market cap buckets:")
        for bucket, count in mcap_counts.most_common():
            lines.append(f"  {bucket:<12} {count}")

    lines.append("")
    lines.append("Acquirers:")
    for ticker, a in acquirers.items():
        if a.include_as_acquirer:
            lo, hi = a.deal_size_range_millions
            lines.append(
                f"  {ticker:<8} {a.name:<35} "
                f"deal range: ${lo:,.0f}M – ${hi:,.0f}M"
            )

    return "\n".join(lines)

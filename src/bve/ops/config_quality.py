"""Corpus-wide config provenance + completeness dashboard.

Distinct from the two existing quality surfaces:

- ``ops/data_quality.py`` (``bve-data-quality``) scores *runtime* knowledge-store
  health per asset (doc freshness, connector errors, market-data freshness).
- ``cli/bve_input_integrity.py`` scores a single ticker's *market/financials*
  integrity at run time.

This module scans the **static valuation config corpus**
(``examples/configs/{auto_generated,replay_generated}/*.yaml``) for evidence
provenance, so analyst curation time is spent where it moves the rNPV most.

Two independent axes, deliberately never conflated:

``completeness``
    Fraction of high-leverage fields that are actually *sourced* — i.e. NOT in
    ``_meta.defaulted_fields``. This is the "missing → coerced to a conservative
    default" axis. A low score means the number rests on engine defaults.

``evidence``
    How *strongly* the present fields are sourced — ``_meta.evidence_level``
    (``coarse`` / ``full``) plus ``commercial_inputs`` provenance
    (``curated_funnel`` / ``derived`` / ``none``). A field can be present and
    non-defaulted yet still weakly sourced; that is an evidence problem, not a
    completeness problem, so the two are reported on separate columns.

The completeness weights are **explicit and versioned** (see
``QUALITY_SCORE_VERSIONS``), mirroring ``intelligence/actionable_output`` so the
"quality score" never becomes an opaque model.

Out of scope for slice 1 (this module): sensitivity / materiality weighting
(how much each defaulted field actually moves the rNPV via the tornado). That is
a deliberate phase-2 layer — see the project ROI notes — because sensitivity
parameter names do not map cleanly onto ``defaulted_fields`` across the legacy
market-field vs. ``commercial_inputs`` config shapes.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Score registry — version → completeness weights (must sum to 1.0)
# ---------------------------------------------------------------------------

QUALITY_SCORE_VERSIONS: dict[str, dict[str, float]] = {
    # v1.0 — initial weights (2026-Q2). High-leverage commercial + PoS fields
    # carry the most weight because they dominate the rNPV; structural rates
    # (patent life, ramp, discount) carry a little.
    "v1.0": {
        "net_price_per_patient_usd": 0.20,
        "addressable_patients_annual": 0.15,
        "success_probability": 0.15,
        "commercial_inputs": 0.15,
        "total_addressable_market_millions": 0.10,
        "peak_penetration": 0.10,
        "patent_life_years": 0.05,
        "years_to_peak": 0.05,
        "discount_rate": 0.05,
    },
}

CURRENT_QUALITY_VERSION = "v1.0"

# Partial completeness credit for the ``commercial_inputs`` weight, keyed by the
# provenance of the block. A curated prevalence funnel is full credit; a coarse
# derived block (addressable_k + WAC/gross-to-net) is half; absent is zero.
_CI_PROVENANCE_CREDIT: dict[str, float] = {
    "curated_funnel": 1.0,
    "derived": 0.5,
    "none": 0.0,
}

# Funnel keys that mark an analyst-curated patient_pool (vs. the derived
# addressable_k override the auto-generator emits).
_FUNNEL_KEYS = ("prevalence_thousands", "diagnosed_fraction", "eligible_rate", "treated_fraction")


# ---------------------------------------------------------------------------
# Record model (mirrors ops/data_quality.py style)
# ---------------------------------------------------------------------------


class ConfigQualityRecord(BaseModel):
    """Provenance + completeness summary for a single valuation config."""

    ticker: str
    config_path: str
    vintage: str  # auto_generated | replay_generated | other
    generator_version: str | None = None
    generated_at: str | None = None

    # evidence axis (present-but-weak)
    evidence_level: str = "unknown"  # coarse | full | not_assessed | unknown
    commercial_inputs_provenance: str = "none"  # curated_funnel | derived | none
    provisional: bool = False

    # completeness axis (missing → coerced)
    metadata_present: bool = True
    n_defaulted: int = 0
    defaulted_fields: list[str] = Field(default_factory=list)
    completeness_score: float | None = None  # None when metadata absent

    # provenance of the score itself
    score_version: str = CURRENT_QUALITY_VERSION
    score_weights: dict[str, float] = Field(default_factory=dict)
    staleness_days: int | None = None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def commercial_inputs_provenance(market_model: Mapping) -> str:
    """Classify the ``commercial_inputs`` block as curated / derived / none."""
    ci = market_model.get("commercial_inputs")
    if not ci:
        return "none"
    pool = ci.get("patient_pool", {}) or {}
    if any(key in pool for key in _FUNNEL_KEYS):
        return "curated_funnel"
    if "addressable_k" in pool:
        return "derived"
    # A commercial_inputs block with neither shape is unusual; treat as derived
    # (it is at least an explicit price×share build-up, not absent).
    return "derived"


def completeness_score(
    defaulted: Iterable[str],
    ci_provenance: str,
    weights: Mapping[str, float],
) -> float:
    """Weighted fraction of high-leverage fields that are actually sourced.

    The ``commercial_inputs`` weight is credited by provenance (curated > derived
    > none); every other weighted field scores full credit unless it appears in
    ``defaulted`` (i.e. was coerced to a conservative default).
    """
    defaulted_set = set(defaulted)
    total = 0.0
    for field_name, weight in weights.items():
        if field_name == "commercial_inputs":
            total += weight * _CI_PROVENANCE_CREDIT.get(ci_provenance, 0.0)
        elif field_name not in defaulted_set:
            total += weight
    return round(total, 4)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------


def scan_config(
    path: str | Path,
    *,
    score_version: str = CURRENT_QUALITY_VERSION,
    as_of: date | None = None,
) -> ConfigQualityRecord:
    """Scan a single config YAML into a :class:`ConfigQualityRecord`."""
    if score_version not in QUALITY_SCORE_VERSIONS:
        raise ValueError(
            f"Unknown quality score version {score_version!r}. "
            f"Valid: {sorted(QUALITY_SCORE_VERSIONS)}"
        )
    weights = QUALITY_SCORE_VERSIONS[score_version]
    as_of = as_of or datetime.now(timezone.utc).date()

    path = Path(path)
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    market_model = cfg.get("market_model", {}) or {}
    meta = cfg.get("_meta", {}) or {}
    company = cfg.get("company", {}) or {}

    ticker = (company.get("ticker") or path.stem).upper()
    vintage = path.parent.name
    ci_provenance = commercial_inputs_provenance(market_model)

    # Metadata is "present" only when _meta carries the defaulted_fields key —
    # otherwise we cannot trust a completeness number and must say so rather than
    # overstate precision (config vintages differ).
    metadata_present = "defaulted_fields" in meta
    defaulted = list(meta.get("defaulted_fields") or [])
    generated_at = meta.get("generated_at")

    score = (
        completeness_score(defaulted, ci_provenance, weights)
        if metadata_present
        else None
    )

    gen_date = _parse_date(generated_at)
    staleness = (as_of - gen_date).days if gen_date else None

    return ConfigQualityRecord(
        ticker=ticker,
        config_path=str(path),
        vintage=vintage,
        generator_version=meta.get("generator_version"),
        generated_at=generated_at,
        evidence_level=meta.get("evidence_level", "unknown"),
        commercial_inputs_provenance=ci_provenance,
        provisional=bool(meta.get("provisional", False)),
        metadata_present=metadata_present,
        n_defaulted=len(defaulted),
        defaulted_fields=sorted(defaulted),
        completeness_score=score,
        score_version=score_version,
        score_weights=dict(weights),
        staleness_days=staleness,
    )


def _sort_key(record: ConfigQualityRecord) -> tuple:
    # Worst-first: missing metadata, then lowest completeness, then most
    # defaulted fields, then ticker for stable ordering.
    score = record.completeness_score
    return (
        0 if not record.metadata_present else 1,
        score if score is not None else -1.0,
        -record.n_defaulted,
        record.ticker,
    )


def scan_corpus(
    roots: Sequence[str | Path],
    *,
    score_version: str = CURRENT_QUALITY_VERSION,
    as_of: date | None = None,
) -> list[ConfigQualityRecord]:
    """Scan every ``*.yaml`` under ``roots``, sorted worst-first."""
    records: list[ConfigQualityRecord] = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for path in sorted(root_path.glob("*.yaml")):
            records.append(
                scan_config(path, score_version=score_version, as_of=as_of)
            )
    records.sort(key=_sort_key)
    return records


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def to_json(records: Sequence[ConfigQualityRecord]) -> list[dict]:
    """Machine-readable list of record dicts."""
    return [r.model_dump() for r in records]


def _fmt_score(score: float | None) -> str:
    return "n/a" if score is None else f"{score:.2f}"


def to_markdown(records: Sequence[ConfigQualityRecord]) -> str:
    """Ranked Markdown dashboard, worst-quality configs first."""
    if not records:
        return "# Config Quality Dashboard\n\n_No configs found._\n"

    version = records[0].score_version
    n = len(records)
    n_no_meta = sum(1 for r in records if not r.metadata_present)
    n_derived = sum(1 for r in records if r.commercial_inputs_provenance == "derived")
    n_curated = sum(
        1 for r in records if r.commercial_inputs_provenance == "curated_funnel"
    )
    n_no_ci = sum(1 for r in records if r.commercial_inputs_provenance == "none")

    lines = [
        "# Config Quality Dashboard",
        "",
        f"_Score version `{version}` · {n} configs · worst-first._",
        "",
        f"- Commercial inputs: **{n_curated} curated**, {n_derived} derived, "
        f"{n_no_ci} none",
        f"- Missing metadata (completeness untrusted): **{n_no_meta}**",
        "",
        "Two axes: **completeness** = fraction of high-leverage fields actually "
        "sourced (vs. coerced defaults); **evidence** = how strongly present "
        "fields are sourced.",
        "",
        "| Ticker | Vintage | Completeness | Evidence | Commercial inputs | "
        "Defaulted | Stale (d) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in records:
        stale = "—" if r.staleness_days is None else str(r.staleness_days)
        lines.append(
            f"| {r.ticker} | {r.vintage} | {_fmt_score(r.completeness_score)} "
            f"| {r.evidence_level} | {r.commercial_inputs_provenance} "
            f"| {r.n_defaulted} | {stale} |"
        )
    lines.append("")
    return "\n".join(lines)

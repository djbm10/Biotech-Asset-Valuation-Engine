"""Map a :class:`CompanyProfile` to a valuation config dict the engine consumes.

The output mirrors the schema produced by ``pipeline/auto_config_generator.py``
(``asset`` / ``company`` / ``trials`` / ``market_model`` / ``_meta``) so it runs
unchanged through ``bve-asset`` / ``ValuationEngine``.

Honesty rules:
- The lead asset only is emitted (multi-asset is deferred).
- ``_meta.evidence_level`` is carried from the profile (``coarse`` for auto-built).
- Engine-required fields with no public value are coerced to a conservative
  default and recorded in ``_meta.defaulted_fields`` alongside every low-confidence
  (heuristic / structural-default) field — these are the analyst-review targets.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from bve.pipeline.asset_profile import CompanyProfile, ProvenancedField

_AUTO_DIR = "examples/configs/auto_generated"
GENERATOR_VERSION = "profile-0.1"

# Conservative fallbacks for engine-required fields when no public source exists.
_REQUIRED_DEFAULTS = {
    "cash_millions": 250.0,
    "shares_outstanding_millions": 100.0,
    "burn_rate_millions_per_quarter": 35.0,
    "success_probability": 0.30,
}


def _val(field: ProvenancedField, default: Any = None) -> Any:
    return default if field.value is None else field.value


def config_from_profile(profile: CompanyProfile) -> dict:
    """Build the engine config dict for the profile's lead asset."""
    asset = profile.lead_asset
    defaulted: list[str] = []

    def _required(name: str, field: ProvenancedField, default: Any) -> Any:
        if field.value is None:
            defaulted.append(name)
            return default
        return field.value

    asset_block = {
        "id": asset.asset_id,
        "name": _val(asset.drug_name, asset.asset_id),
        "indication": _val(asset.indication, "unknown"),
        "therapeutic_area": _val(asset.therapeutic_area, "other"),
        "stage": _val(asset.stage, "phase_2"),
        "modality": _val(asset.modality, "small_molecule"),
        "discount_rate": _val(asset.discount_rate, 0.10),
    }

    company_block = {
        "id": profile.company_id,
        "name": profile.name,
        "ticker": profile.ticker,
        "cash_millions": _required(
            "cash_millions", profile.cash_millions, _REQUIRED_DEFAULTS["cash_millions"]
        ),
        "shares_outstanding_millions": _required(
            "shares_outstanding_millions",
            profile.shares_outstanding_millions,
            _REQUIRED_DEFAULTS["shares_outstanding_millions"],
        ),
        "debt_millions": _val(profile.debt_millions, 0.0),
        "burn_rate_millions_per_quarter": _required(
            "burn_rate_millions_per_quarter",
            profile.burn_rate_millions_per_quarter,
            _REQUIRED_DEFAULTS["burn_rate_millions_per_quarter"],
        ),
        "current_price": _val(profile.current_price),
        "market_cap_millions": _val(profile.market_cap_millions),
    }

    trial_block = {
        "phase": _val(asset.stage, "phase_2"),
        "nct_id": asset.nct_id,
        "success_probability": _required(
            "success_probability",
            asset.success_probability,
            _REQUIRED_DEFAULTS["success_probability"],
        ),
        "duration_years": _val(asset.duration_years, 2.5),
        "cost_millions": _val(asset.cost_millions, 120.0),
        "enrollment": _val(asset.enrollment),
        "primary_endpoint": _val(asset.primary_endpoint),
        "endpoint_type": _val(asset.endpoint_type, "surrogate_validated"),
        "estimated_completion_date": _val(asset.estimated_completion_date),
    }

    market_block = {
        "total_addressable_market_millions": _val(asset.total_addressable_market_millions),
        "addressable_patients_annual": _val(asset.addressable_patients_annual),
        "net_price_per_patient_usd": _val(asset.net_price_per_patient_usd),
        "peak_penetration": _val(asset.peak_penetration, 0.10),
        "years_to_peak": _val(asset.years_to_peak, 5),
        "patent_life_years": _val(asset.patent_life_years, 10),
        "cogs_rate": _val(asset.cogs_rate, 0.15),
        "sgna_rate_launch": _val(asset.sgna_rate_launch, 0.40),
        "sgna_rate_mature": _val(asset.sgna_rate_mature, 0.20),
    }

    # Review targets = coerced-required fields + every low-confidence field.
    review_fields = set(defaulted)
    review_fields.update(asset.low_confidence_fields())
    review_fields.update(
        name
        for name, field in profile.company_provenanced_items().items()
        if field.confidence == "low"
    )

    meta = {
        "config_version": "auto-profile-v1",
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(timezone.utc).date().isoformat(),
        "source_nct_id": asset.nct_id,
        "evidence_level": profile.evidence_level,
        "defaulted_fields": sorted(review_fields),
        "provisional": True,
    }

    return {
        "asset": asset_block,
        "company": company_block,
        "trials": [trial_block],
        "market_model": market_block,
        "_meta": meta,
    }


def write_config(profile: CompanyProfile, out_dir: str | Path = _AUTO_DIR) -> Path:
    """Write the generated config to ``<out_dir>/<ticker>.yaml`` and return the path."""
    cfg = config_from_profile(profile)
    out_path = Path(out_dir) / f"{profile.ticker.lower()}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return out_path

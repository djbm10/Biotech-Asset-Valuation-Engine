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

# Standard specialty-pharma gross-to-net discount, used to document list (WAC) vs.
# net pricing when only a net price is known. Conservative midpoint of the 25-35%
# typical range — keeps the price build-up auditable instead of opaque.
_DEFAULT_GROSS_TO_NET = 0.30


def _val(field: ProvenancedField, default: Any = None) -> Any:
    return default if field.value is None else field.value


def _commercial_inputs_block(asset_block: dict, market_block: dict) -> dict | None:
    """Derive a coarse but explicit ``commercial_inputs`` block from market inputs.

    Uses the ``addressable_k`` override form — honest for auto-covered names where
    the full diagnosed → eligible → treated funnel is unknown, so no funnel is
    fabricated. Net price is documented as WAC + gross-to-net so the price build-up
    stays auditable. Returns ``None`` when there is no price to anchor the build-up.
    """
    net_price = market_block.get("net_price_per_patient_usd")
    if not net_price:
        return None

    addressable = market_block.get("addressable_patients_annual")
    if not addressable:
        tam = market_block.get("total_addressable_market_millions")
        if not tam:
            return None
        # Implied addressable population at 100% penetration from TAM ÷ net price.
        addressable = (tam * 1_000_000) / net_price

    g2n = _DEFAULT_GROSS_TO_NET
    wac = round(net_price / (1.0 - g2n), 2)
    return {
        "patient_pool": {
            "indication": asset_block["indication"],
            "addressable_k": round(addressable / 1_000.0, 4),
            "uncertainty_cv": 0.25,
        },
        "pricing": {
            "wac_per_year_usd": wac,
            "gross_to_net_rate": g2n,
            "launch_discount": 0.0,
            "annual_erosion_rate": 0.02,
            "uncertainty_cv": 0.15,
        },
        "share": {
            "peak_share": market_block.get("peak_penetration", 0.10),
            "years_to_peak": market_block.get("years_to_peak", 5),
            "share_cv": 0.20,
        },
        "ex_us_revenue_multiple": 1.0,
    }


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

    # Explicit patient × price × share build-up so every auto-covered name carries an
    # auditable commercial layer (not just an opaque TAM). Omitted only when there is
    # no price to anchor it.
    ci_block = _commercial_inputs_block(asset_block, market_block)
    if ci_block is not None:
        market_block["commercial_inputs"] = ci_block

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

    # Never clobber a hand-curated commercial_inputs block on regeneration. An analyst
    # curated funnel always beats the coarse derived one (see edit/fate/ntla, which lost
    # their curation when the generator rewrote them without preserving it).
    if out_path.exists():
        existing = yaml.safe_load(out_path.read_text()) or {}
        existing_ci = existing.get("market_model", {}).get("commercial_inputs")
        if existing_ci is not None:
            cfg.setdefault("market_model", {})["commercial_inputs"] = existing_ci

    out_path.write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    return out_path

"""
Snapshot bridge — two-way translation between CompanySnapshot and
CompanySOTPResult, plus the underwriting pack YAML loader.

sotp_result_from_snapshot()
    Derives a CompanySOTPResult (ephemeral computation output) from a
    canonical CompanySnapshot.  Lets existing SOTP consumers work while
    new code builds on snapshots.

snapshot_from_sotp_inputs()
    Bootstraps an initial draft CompanySnapshot from an existing SOTP run.
    Useful for seeding the snapshot store from the existing pipeline.

load_underwriting_pack(path)
    Parses an underwriting pack YAML into a validated CompanySnapshot.
    Entry point for the analyst quarterly-pack workflow.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import yaml


def load_underwriting_pack(path: str | Path) -> "CompanySnapshot":  # noqa: F821
    """
    Load an underwriting pack YAML and return a validated CompanySnapshot.

    The YAML schema is defined in:
      examples/packs/underwriting_pack_template.yaml

    Raises
    ------
    FileNotFoundError  if path does not exist
    ValueError         if required fields are missing or invalid
    pydantic.ValidationError  if model validation fails
    """
    from bve.entities.company_snapshot import (
        CatalystEntry,
        CompanySnapshot,
        ConfidenceMetadata,
        DilutionBridge,
        ManagementFlag,
        ProvenanceMetadata,
        ReviewerState,
    )

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Underwriting pack not found: {p}")

    with open(p) as f:
        raw = yaml.safe_load(f)

    # ---- market data ----
    market = raw.get("market", {})
    balance = raw.get("balance_sheet", {})

    # ---- modeled assets ----
    modeled_assets = []
    for bucket_raw in raw.get("modeled_assets", []):
        modeled_assets.append(_value_bucket_from_dict(bucket_raw, "modeled_asset"))

    # ---- royalty streams ----
    royalty_streams = []
    for bucket_raw in raw.get("royalty_streams", []):
        royalty_streams.append(_value_bucket_from_dict(bucket_raw, "royalty"))

    # ---- optional buckets ----
    platform_value = None
    if raw.get("platform_value"):
        platform_value = _value_bucket_from_dict(raw["platform_value"], "platform")

    unmodeled_pipeline = None
    if raw.get("unmodeled_pipeline"):
        unmodeled_pipeline = _value_bucket_from_dict(raw["unmodeled_pipeline"], "unmodeled_pipeline")

    # ---- dilution bridge ----
    dilution_bridge = None
    _dil_raw = raw.get("dilution") or {}
    if _dil_raw and float(_dil_raw.get("current_shares_millions", 0.0)) > 0:
        d = _dil_raw
        dilution_bridge = DilutionBridge(
            current_shares_millions=float(d["current_shares_millions"]),
            expected_dilution_pct=float(d.get("expected_dilution_pct", 0.0)),
            financing_runway_quarters=d.get("financing_runway_quarters"),
            atm_active=bool(d.get("atm_active", False)),
            atm_remaining_millions=d.get("atm_remaining_millions"),
            shelf_registration_millions=d.get("shelf_registration_millions"),
            warrant_shares_millions=float(d.get("warrant_shares_millions", 0.0)),
            convertible_shares_millions=float(d.get("convertible_shares_millions", 0.0)),
            source_ref=d.get("source_ref"),
            as_of_date=date.fromisoformat(d["as_of_date"]) if d.get("as_of_date") else None,
            notes=d.get("notes"),
        )

    # ---- catalysts ----
    catalysts = [
        CatalystEntry(**c)
        for c in raw.get("catalysts", [])
    ]

    # ---- management flags ----
    management_flags = [
        ManagementFlag(**f)
        for f in raw.get("management_flags", [])
    ]

    # ---- confidence ----
    conf_raw = raw.get("confidence", {})
    confidence = ConfidenceMetadata(
        overall_confidence=float(conf_raw.get("overall_confidence", 0.65)),
        notes=conf_raw.get("notes"),
    )

    # ---- provenance ----
    prov_raw = raw.get("provenance", {})
    provenance = ProvenanceMetadata(
        pack_version=int(prov_raw.get("pack_version", 1)),
        pack_quarter=prov_raw.get("pack_quarter") or raw.get("pack_quarter"),
        created_by=str(prov_raw.get("created_by", "analyst")),
        change_summary=prov_raw.get("change_summary"),
    )

    return CompanySnapshot(
        company_id=raw["company_id"].lower(),
        company_name=raw["company_name"],
        ticker=raw["ticker"].upper(),
        as_of_date=date.fromisoformat(raw["as_of_date"]),
        market_cap_millions=float(market.get("market_cap_millions", 0.0)),
        enterprise_value_millions=float(market.get("enterprise_value_millions", 0.0)),
        share_price=market.get("share_price"),
        cash_millions=float(balance.get("cash_millions", 0.0)),
        debt_millions=float(balance.get("debt_millions", 0.0)),
        modeled_assets=modeled_assets,
        royalty_streams=royalty_streams,
        platform_value=platform_value,
        unmodeled_pipeline=unmodeled_pipeline,
        dilution_bridge=dilution_bridge,
        catalysts=catalysts,
        management_flags=management_flags,
        confidence=confidence,
        provenance=provenance,
        reviewer_state=ReviewerState(raw.get("reviewer_state", "draft")),
        notes=raw.get("notes"),
    )


def _value_bucket_from_dict(d: dict, default_type: str) -> "ValueBucket":  # noqa: F821
    from bve.entities.company_snapshot import ValueBucket

    return ValueBucket(
        bucket_id=str(d["bucket_id"]),
        bucket_type=d.get("bucket_type", default_type),
        label=str(d["label"]),
        value_millions=float(d["value_millions"]),
        methodology=d.get("methodology", "analyst_estimate"),
        source_type=d.get("source_type", "analyst_bridge"),
        source_ref=str(d.get("source_ref", "")),
        as_of_date=date.fromisoformat(str(d["as_of_date"])),
        corroboration_count=int(d.get("corroboration_count", 0)),
        corroboration_refs=list(d.get("corroboration_refs", [])),
        reviewer=d.get("reviewer"),
        confidence=float(d.get("confidence", 0.65)),
        change_reason=d.get("change_reason"),
        notes=d.get("notes"),
    )


def sotp_result_from_snapshot(
    snapshot: "CompanySnapshot",  # noqa: F821
    *,
    rank: int = 0,
    ranked_sotp_discount: Optional[float] = None,
) -> "CompanySOTPResult":  # noqa: F821
    """
    Derive a CompanySOTPResult from a canonical CompanySnapshot.

    This lets the existing SOTP reporting pipeline consume snapshots
    without requiring a full SOTP rebuild from raw configs.

    Parameters
    ----------
    snapshot
        The canonical company snapshot.
    rank
        The snapshot's rank in the current screener output.
    ranked_sotp_discount
        Pre-computed cross-universe ranked discount (percentile).
        If None, uses snapshot.sotp_discount.
    """
    from bve.analysis.company_sotp import CompanySOTPBucket, CompanySOTPResult

    _ranked = ranked_sotp_discount if ranked_sotp_discount is not None else snapshot.sotp_discount

    # Convert ValueBuckets → CompanySOTPBuckets
    buckets = []
    for vb in snapshot.modeled_assets:
        buckets.append(CompanySOTPBucket(
            bucket_id=vb.bucket_id,
            bucket_type="modeled_asset",
            label=vb.label,
            value_millions=vb.value_millions,
            source=vb.source_ref,
            source_kind="modeled",
            confidence=vb.confidence,
            as_of_date=vb.as_of_date,
            notes=vb.notes,
        ))
    for vb in snapshot.royalty_streams:
        buckets.append(CompanySOTPBucket(
            bucket_id=vb.bucket_id,
            bucket_type="royalty",
            label=vb.label,
            value_millions=vb.value_millions,
            source=vb.source_ref,
            source_kind=_map_source_kind(vb.source_type),
            confidence=vb.confidence,
            as_of_date=vb.as_of_date,
            notes=vb.notes,
        ))
    for vb_opt, btype in [
        (snapshot.platform_value, "platform"),
        (snapshot.unmodeled_pipeline, "unmodeled_pipeline"),
    ]:
        if vb_opt:
            buckets.append(CompanySOTPBucket(
                bucket_id=vb_opt.bucket_id,
                bucket_type=btype,
                label=vb_opt.label,
                value_millions=vb_opt.value_millions,
                source=vb_opt.source_ref,
                source_kind=_map_source_kind(vb_opt.source_type),
                confidence=vb_opt.confidence,
                as_of_date=vb_opt.as_of_date,
                notes=vb_opt.notes,
            ))

    # Derive gap metrics
    gap_m = snapshot.sotp_equity_value_millions - snapshot.market_cap_millions
    gap_pct = snapshot.sotp_discount * 100.0
    ratio = (
        snapshot.sotp_equity_value_millions / snapshot.market_cap_millions
        if snapshot.market_cap_millions > 0 else 0.0
    )

    # Derive reconciliation_status from ratio
    if ratio > 5.0:
        recon_status = "extreme_discount"
        passes_gate = False
    elif ratio > 1.5:
        recon_status = "discounted"
        passes_gate = True
    elif ratio < 0.5:
        recon_status = "extreme_premium"
        passes_gate = False
    else:
        recon_status = "premium"
        passes_gate = True

    # Derive action_policy from reviewer_state
    state_to_policy = {
        "draft": "watch",
        "reviewed": "watch",
        "approved": "buy",
        "quarantined": "avoid",
        "stale": "needs_manual_review",
    }
    action_policy = state_to_policy.get(snapshot.reviewer_state.value, "watch")

    all_buckets_conf = [b.confidence for b in snapshot.all_buckets]
    conf_min = min(all_buckets_conf) if all_buckets_conf else 0.0
    conf_avg = (sum(all_buckets_conf) / len(all_buckets_conf)) if all_buckets_conf else 0.0

    return CompanySOTPResult(
        rank=rank,
        company_id=snapshot.company_id,
        company_name=snapshot.company_name,
        ticker=snapshot.ticker,
        snapshot_date=snapshot.as_of_date,
        asset_count_modeled=len(snapshot.modeled_assets),
        modeled_asset_ids=[b.bucket_id for b in snapshot.modeled_assets],
        market_cap_millions=snapshot.market_cap_millions,
        enterprise_value_millions=snapshot.enterprise_value_millions,
        net_cash_millions=snapshot.net_cash_millions,
        shares_outstanding_millions=(
            snapshot.dilution_bridge.current_shares_millions
            if snapshot.dilution_bridge else 0.0
        ),
        modeled_asset_value_millions=snapshot.modeled_asset_value_millions,
        platform_value_millions=snapshot.platform_value_millions,
        unmodeled_pipeline_value_millions=snapshot.unmodeled_pipeline_value_millions,
        royalty_value_millions=snapshot.royalty_value_millions,
        dilution_reserve_millions=snapshot.dilution_reserve_millions,
        sotp_equity_value_millions=snapshot.sotp_equity_value_millions,
        sotp_per_share=(
            snapshot.sotp_equity_value_millions
            / snapshot.dilution_bridge.current_shares_millions
            if (snapshot.dilution_bridge and snapshot.dilution_bridge.current_shares_millions > 0)
            else 0.0
        ),
        sotp_discount=snapshot.sotp_discount,
        ranked_sotp_discount=_ranked,
        reconciliation_gap_millions=gap_m,
        reconciliation_gap_pct=gap_pct,
        reconciliation_status=recon_status,
        reconciliation_passes_gate=passes_gate,
        sotp_tier="normal" if passes_gate else "needs_manual_review",
        sotp_action="surface" if passes_gate else "flag",
        sotp_confidence_tier=(
            "high" if snapshot.confidence.overall_confidence >= 0.85
            else "medium_flagged" if snapshot.confidence.overall_confidence >= 0.65
            else "low"
        ),
        sotp_tier_reason=f"Derived from CompanySnapshot reviewer_state={snapshot.reviewer_state.value}",
        modeled_asset_coverage_pct=snapshot.confidence.modeled_asset_coverage_pct,
        market_cap_source="snapshot",
        balance_sheet_source="snapshot",
        balance_sheet_source_ref=None,
        balance_sheet_snapshot_date=snapshot.as_of_date,
        balance_sheet_period_end_date=None,
        balance_sheet_form_type=None,
        balance_sheet_is_point_in_time=True,
        balance_sheet_age_days=0,
        balance_sheet_passes_recency_gate=True,
        balance_sheet_recency_penalty=0.0,
        modeled_asset_confidence_min=conf_min,
        modeled_asset_confidence_avg=conf_avg,
        action_policy=action_policy,
        action_reason=f"reviewer_state={snapshot.reviewer_state.value}; pack_version={snapshot.provenance.pack_version}",
        buckets=buckets,
        notes=snapshot.notes,
    )


def _map_source_kind(source_type: str) -> str:
    """Map ValueBucket.source_type to CompanySOTPBucket.source_kind."""
    mapping = {
        "modeled": "modeled",
        "sec_filing": "sec_filing",
        "contractual": "contractual",
        "company_disclosure": "company_disclosure",
        "investor_day": "investor_day",
        "analyst_bridge": "analyst_bridge",
        "inferred": "inferred",
    }
    return mapping.get(source_type, "analyst_bridge")

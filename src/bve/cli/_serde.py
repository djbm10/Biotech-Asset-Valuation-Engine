"""
JSON serialisation helpers for Phase 2 CLI data objects.

Handles the non-primitive types that arise from our dataclasses:
  - datetime.date → ISO string
  - tuple[float, float] → list (for deal_size_range_millions)

All public functions are pure (no side effects).
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date
from typing import Any

from bve.ingestion.profile_enricher import AcquirerProfileEnriched, TargetProfileEnriched
from bve.intelligence.weekly_ma_screen import (
    AcquirerPairResult,
    TargetScreenResult,
    WeeklyMAScreenResult,
)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def _default(obj: Any) -> Any:
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def _to_json(obj: Any) -> str:
    return json.dumps(dataclasses.asdict(obj), default=_default, indent=2, ensure_ascii=False)


def _from_json(s: str) -> dict:
    return json.loads(s)


# ---------------------------------------------------------------------------
# WeeklyMAScreenResult
# ---------------------------------------------------------------------------


def screen_result_to_json(result: WeeklyMAScreenResult) -> str:
    return _to_json(result)


def screen_result_from_dict(d: dict) -> WeeklyMAScreenResult:
    return WeeklyMAScreenResult(
        as_of_date=date.fromisoformat(d["as_of_date"]),
        score_mode=d["score_mode"],
        ranked_targets=[_target_screen_from_dict(t) for t in d["ranked_targets"]],
        suppressed_targets=[_target_screen_from_dict(t) for t in d["suppressed_targets"]],
        top_acquirer_pairs=[_pair_from_dict(p) for p in d["top_acquirer_pairs"]],
        diagnostics=d["diagnostics"],
    )


def screen_result_from_json(s: str) -> WeeklyMAScreenResult:
    return screen_result_from_dict(json.loads(s))


def _target_screen_from_dict(d: dict) -> TargetScreenResult:
    return TargetScreenResult(
        rank=int(d["rank"]),
        ticker=d["ticker"],
        name=d["name"],
        ma_probability=float(d["ma_probability"]),
        probability_low=float(d["probability_low"]),
        probability_high=float(d["probability_high"]),
        confidence_label=d["confidence_label"],
        asset_quality=float(d["asset_quality"]),
        seller_willingness=float(d["seller_willingness"]),
        financing_risk=float(d.get("financing_risk", 0.0)),
        catalyst_timing=float(d["catalyst_timing"]),
        ma_attractiveness=float(d["ma_attractiveness"]),
        evidence_coverage_overall=float(d["evidence_coverage_overall"]),
        profile_quality_score=float(d["profile_quality_score"]),
        top_acquirer=d.get("top_acquirer"),
        top_acquirer_pair_score=(
            float(d["top_acquirer_pair_score"])
            if d.get("top_acquirer_pair_score") is not None
            else None
        ),
        main_drivers=list(d.get("main_drivers") or []),
        key_risks=list(d.get("key_risks") or []),
        suppressed=bool(d["suppressed"]),
        suppression_reason=d.get("suppression_reason"),
    )


def _pair_from_dict(d: dict) -> AcquirerPairResult:
    return AcquirerPairResult(
        target_ticker=d["target_ticker"],
        acquirer_ticker=d["acquirer_ticker"],
        pair_score=float(d["pair_score"]),
        ta_overlap=float(d["ta_overlap"]),
        modality_fit=float(d["modality_fit"]),
        stage_fit=float(d["stage_fit"]),
        deal_size_fit=float(d["deal_size_fit"]),
        pipeline_gap_fill=float(d["pipeline_gap_fill"]),
        integration_complexity=float(d["integration_complexity"]),
        ta_fit_cap_applied=(
            float(d["ta_fit_cap_applied"])
            if d.get("ta_fit_cap_applied") not in (None, "")
            else None
        ),
        ta_fit_override_type=d.get("ta_fit_override_type"),
        ta_fit_override_source=d.get("ta_fit_override_source"),
    )


# ---------------------------------------------------------------------------
# TargetProfileEnriched / AcquirerProfileEnriched
# ---------------------------------------------------------------------------


def target_profiles_to_json(profiles: dict[str, TargetProfileEnriched]) -> str:
    return json.dumps(
        {k: dataclasses.asdict(v) for k, v in profiles.items()},
        default=_default,
        indent=2,
        ensure_ascii=False,
    )


def target_profile_from_dict(d: dict) -> TargetProfileEnriched:
    return TargetProfileEnriched(
        ticker=d["ticker"],
        name=d["name"],
        cik=d.get("cik"),
        exchange=d["exchange"],
        company_type=d["company_type"],
        therapeutic_areas=list(d.get("therapeutic_areas") or []),
        lead_asset=d["lead_asset"],
        lead_asset_phase=d["lead_asset_phase"],
        lead_modality=d["lead_modality"],
        lead_indication=d["lead_indication"],
        is_single_asset_company=bool(d["is_single_asset_company"]),
        include_in_screen=bool(d["include_in_screen"]),
        market_cap_bucket=d.get("market_cap_bucket"),
        has_partner_encumbrance=d.get("has_partner_encumbrance"),
        cash_millions=_opt_float(d.get("cash_millions")),
        rd_expense_ttm_millions=_opt_float(d.get("rd_expense_ttm_millions")),
        sgna_expense_ttm_millions=_opt_float(d.get("sgna_expense_ttm_millions")),
        operating_burn_ttm_millions=_opt_float(d.get("operating_burn_ttm_millions")),
        shares_outstanding_millions=_opt_float(d.get("shares_outstanding_millions")),
        cash_runway_months=_opt_float(d.get("cash_runway_months")),
        quality_score=float(d["quality_score"]),
        data_quality_flags=list(d.get("data_quality_flags") or []),
        source_map=dict(d.get("source_map") or {}),
        enriched_at=d["enriched_at"],
    )


def target_profiles_from_json(s: str) -> dict[str, TargetProfileEnriched]:
    raw = json.loads(s)
    return {k: target_profile_from_dict(v) for k, v in raw.items()}


def acquirer_profiles_to_json(profiles: dict[str, AcquirerProfileEnriched]) -> str:
    return json.dumps(
        {k: dataclasses.asdict(v) for k, v in profiles.items()},
        default=_default,
        indent=2,
        ensure_ascii=False,
    )


def acquirer_profile_from_dict(d: dict) -> AcquirerProfileEnriched:
    dr = d.get("deal_size_range_millions") or [0.0, 0.0]
    return AcquirerProfileEnriched(
        ticker=d["ticker"],
        name=d["name"],
        cik=d.get("cik"),
        therapeutic_areas=list(d.get("therapeutic_areas") or []),
        modalities=list(d.get("modalities") or []),
        deal_size_range_millions=(float(dr[0]), float(dr[1])),
        preferred_stages=list(d.get("preferred_stages") or []),
        include_as_acquirer=bool(d["include_as_acquirer"]),
        bd_appetite=float(d["bd_appetite"]),
        urgency=float(d["urgency"]),
        integration_capacity=float(d["integration_capacity"]),
        quality_score=float(d["quality_score"]),
        data_quality_flags=list(d.get("data_quality_flags") or []),
        source_map=dict(d.get("source_map") or {}),
        enriched_at=d["enriched_at"],
    )


def acquirer_profiles_from_json(s: str) -> dict[str, AcquirerProfileEnriched]:
    raw = json.loads(s)
    return {k: acquirer_profile_from_dict(v) for k, v in raw.items()}


def _opt_float(v: Any) -> float | None:
    return float(v) if v is not None else None

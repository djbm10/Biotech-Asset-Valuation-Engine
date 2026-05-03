"""Backfill dated M&A probability snapshots across a replay watchlist."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
from bve.intelligence.ma_probability import MAProbabilityConfig, MAProbabilityScanner
from bve.pipeline.watchlist_runner import load_watchlist_config


@dataclass(frozen=True)
class MABackfillSummary:
    watchlist_path: str
    knowledge_db_path: str
    dataset_mode: str
    snapshot_dates: int
    snapshot_start: date | None
    snapshot_end: date | None
    total_rows_written: int
    total_excluded_assets: int
    calibration_rows: int
    calibration_positive_rows: int
    calibration_positive_targets: int
    precision_at_k: float | None
    unique_target_recall_at_k: float | None
    median_lead_days_at_k: float | None
    dataset_csv_path: str
    metrics_json_path: str
    calibration_fit_path: str | None = None
    policy_comparison_json_path: str | None = None


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw.strip())


def _resolve_dates(
    store: KnowledgeStore,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[date]:
    dates = store.list_screen_snapshot_dates()
    if start_date is not None:
        dates = [item for item in dates if item >= start_date]
    if end_date is not None:
        dates = [item for item in dates if item <= end_date]
    return sorted(dates)


def _range_token(start_date: date | None, end_date: date | None) -> str:
    if start_date is None or end_date is None:
        return "unknown_range"
    return f"{start_date.isoformat()}_{end_date.isoformat()}"


def backfill_ma_probability_snapshots(
    *,
    watchlist_path: str | Path,
    knowledge_db_path: str | Path,
    start_date: date | None = None,
    end_date: date | None = None,
    score_version: str = "v1.4",  # Sprint 20: first version with derisking+scarcity weights
    dataset_mode: str = "canonical_predeal",
    anchor_days_before_announcement: int = 180,
    controls_per_positive: int = 2,
    profiles_file: str = "examples/research/acquirer_profiles",
    comps_file: str = "research/mna/comparable_deals.yaml",
    vulnerability_file: str = "research/mna/vulnerability_signals.yaml",
    deal_universe_path: str = "research/mna/deal_universe_2020_2026.yaml",
    readiness_filter: bool = True,
    top_k: int = 15,
    output_dir: str | Path = "outputs/analysis",
) -> MABackfillSummary:
    config = load_watchlist_config(watchlist_path)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    store = KnowledgeStore(knowledge_db_path)
    try:
        snapshot_dates = _resolve_dates(store, start_date=start_date, end_date=end_date)
        if not snapshot_dates:
            raise ValueError("No screen snapshot dates found for the requested range")

        scanner = MAProbabilityScanner(
            knowledge_store=store,
            config=MAProbabilityConfig(
                score_version=score_version,
                top_n=max(len(config.watchlist), top_k),
                persist_daily_snapshots=True,
                enable_monitor=False,
                use_stored_screen_context=True,
                vulnerability_signals_path=vulnerability_file,
                fit_integration_config={
                    "acquirer_profiles_path": profiles_file,
                    "comparable_deals_path": comps_file,
                    "top_n": max(len(config.watchlist), top_k),
                    "require_acquisition_readiness": readiness_filter,
                },
            ),
        )

        total_rows_written = 0
        total_excluded_assets = 0
        for snapshot_date in snapshot_dates:
            result = scanner.scan_from_watchlist_config(
                config,
                snapshot_date=snapshot_date,
                top_n=max(len(config.watchlist), top_k),
                run_id=f"ma-backfill:{snapshot_date.isoformat()}",
            )
            total_rows_written += result.snapshots_written
            total_excluded_assets += result.n_excluded

        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=deal_universe_path,
        )
        if dataset_mode == "canonical_predeal":
            dataset = builder.build_canonical_dataset(
                lookahead_days=365,
                start_date=snapshot_dates[0],
                end_date=snapshot_dates[-1],
                anchor_days_before_announcement=anchor_days_before_announcement,
                controls_per_positive=controls_per_positive,
            )
        elif dataset_mode == "historical_snapshot":
            dataset = builder.build_dataset(
                lookahead_days=365,
                start_date=snapshot_dates[0],
                end_date=snapshot_dates[-1],
            )
        else:
            raise ValueError(f"Unsupported dataset_mode: {dataset_mode}")
        metrics = builder.evaluate(dataset, top_k=top_k)

        range_token = _range_token(snapshot_dates[0], snapshot_dates[-1])
        if dataset_mode == "canonical_predeal":
            range_token = (
                f"{range_token}_canonical_anchor{anchor_days_before_announcement}"
                f"_controls{controls_per_positive}"
            )
        else:
            range_token = f"{range_token}_historical_snapshot"
        dataset_csv = output_root / f"ma_calibration_dataset_{range_token}.csv"
        metrics_json = output_root / f"ma_calibration_metrics_{range_token}.json"
        dataset.write_csv(dataset_csv)
        metrics_json.write_text(
            json.dumps(metrics.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        # Fit logistic model and persist JSON for live scoring
        calibration_fit_path: str | None = None
        policy_comparison_json_path: str | None = None
        if dataset_mode == "canonical_predeal" and dataset.n_positive_rows >= 3:
            fit_result = builder.fit_logistic_model(dataset, top_k=top_k)
            fit_json = output_root / "ma_calibration_fit.json"
            fit_result.write_json(fit_json)
            calibration_fit_path = str(fit_json)
            # Evaluate three ranking policies against the fitted model
            policy_result = builder.compare_ranking_policies(
                dataset, fit_result, top_k=top_k
            )
            policy_json = output_root / f"ma_policy_comparison_{range_token}.json"
            policy_json.write_text(
                json.dumps(policy_result.model_dump(mode="json"), indent=2),
                encoding="utf-8",
            )
            policy_comparison_json_path = str(policy_json)

        return MABackfillSummary(
            watchlist_path=str(Path(watchlist_path)),
            knowledge_db_path=str(Path(knowledge_db_path)),
            dataset_mode=dataset_mode,
            snapshot_dates=len(snapshot_dates),
            snapshot_start=snapshot_dates[0],
            snapshot_end=snapshot_dates[-1],
            total_rows_written=total_rows_written,
            total_excluded_assets=total_excluded_assets,
            calibration_rows=dataset.n_rows,
            calibration_positive_rows=dataset.n_positive_rows,
            calibration_positive_targets=dataset.n_unique_targets,
            precision_at_k=metrics.precision_at_k,
            unique_target_recall_at_k=metrics.unique_target_recall_at_k,
            median_lead_days_at_k=metrics.median_lead_days_at_k,
            dataset_csv_path=str(dataset_csv),
            metrics_json_path=str(metrics_json),
            calibration_fit_path=calibration_fit_path,
            policy_comparison_json_path=policy_comparison_json_path,
        )
    finally:
        store.close()



@dataclass(frozen=True)
class MARescoredSummary:
    knowledge_db_path: str
    score_version: str
    rows_rescored: int
    scarcity_cap_rate: float
    derisking_cap_rate: float
    mna_screening_cap_rate: float
    strategic_fit_cap_rate: float = 0.0


def _rescore_candidate_json(
    candidates_json: str | None,
    *,
    strategic_fit_hard_cap: float,
    apply_gate_fn,
    cv: float,
    de_risk: float,
) -> str:
    """Apply Sprint 22 caps to each candidate entry inside acquirer_candidates_json.

    - Caps strategic_fit_score at strategic_fit_hard_cap (0.70).
    - Applies _apply_transaction_likelihood_gate to mna_probability_score /
      p_acquisition / raw_probability using available sub-scores.
    - Populates transaction_gate_reason_codes for each candidate.

    Sub-scores not stored in the snapshot (external_deal_activity, activist_signal)
    default to 0.0 — conservative, so the dual-gate fires more often, which is the
    correct direction for reducing false positives.
    """
    if not candidates_json:
        return candidates_json or "[]"
    try:
        candidates = json.loads(candidates_json)
    except (json.JSONDecodeError, TypeError):
        return candidates_json or "[]"

    updated = []
    for cand in candidates:
        # Cap strategic_fit_score
        raw_sf = float(cand.get("strategic_fit_score") or 0.0)
        capped_sf = round(min(raw_sf, strategic_fit_hard_cap), 6)
        cand["strategic_fit_score"] = capped_sf

        # Apply transaction-likelihood gate to the candidate's own scores.
        # Use valuation_discount_score and de_risking_stage_score from the candidate
        # if present; fall back to the snapshot-level de_risk.
        vd_cand = float(cand.get("valuation_discount_score") or 0.0)
        de_risk_cand = float(cand.get("de_risking_stage_score") or de_risk)
        # financing_pressure: use capital_vulnerability_score from candidate if stored
        fp_cand = float(cand.get("capital_vulnerability_score") or cv)

        # Apply gate to each score key; capture reason codes from the first (primary) key.
        gate_codes: list[str] = []
        for i, score_key in enumerate(("mna_probability_score", "p_acquisition", "raw_probability")):
            raw_score = float(cand.get(score_key) or 0.0)
            gated_score, codes = apply_gate_fn(
                raw_score,
                financing_pressure=fp_cand,
                external_deal_activity=0.0,   # not stored in snapshot
                activist_signal=0.0,           # not stored in snapshot
                catalyst_days=None,            # not stored per-candidate
                valuation_discount=vd_cand,
                de_risking_stage=de_risk_cand,
            )
            cand[score_key] = round(gated_score, 6)
            if i == 0:
                gate_codes = codes  # capture from primary score before it is capped in-place

        cand["transaction_gate_reason_codes"] = gate_codes

        updated.append(cand)
    return json.dumps(updated)


def rescore_ma_probability_snapshots(
    *,
    knowledge_db_path: str | Path,
    watchlist_path: str | Path,
    score_version: str = "v1.4",
) -> MARescoredSummary:
    """Re-score all existing ma_probability_snapshots in-place using Sprint 22 functions.

    Much faster than a full backfill: reads stored sub-scores from the DB,
    applies the updated _derisking_stage_score and _assess_scarcity functions,
    caps strategic_fit_score at _STRATEGIC_FIT_HARD_CAP (0.70, Sprint 22),
    applies _apply_transaction_likelihood_gate to the composite (Sprint 22),
    and recomputes the composite probability using the requested score_version.

    Also updates acquirer_candidates_json: caps strategic_fit_score per candidate
    and populates transaction_gate_reason_codes.

    Use this when scoring logic changes (e.g. Sprint 22) but the raw acquisition
    screener data does not need full regeneration from the watchlist scanner.
    """
    import sqlite3
    from types import SimpleNamespace

    from bve.intelligence.ma_probability import (
        SCORE_VERSIONS,
        _apply_transaction_likelihood_gate,
        _compute_scarcity_modifiers,
        _derisking_stage_score,
        _scarcity_score_from_peer_count,
        _STRATEGIC_FIT_HARD_CAP,
    )
    from bve.intelligence.ma_scoring import SATURATION_THRESHOLD, apply_saturation_penalty

    if score_version not in SCORE_VERSIONS:
        raise ValueError(
            f"Unknown score version {score_version!r}. Valid: {sorted(SCORE_VERSIONS)}"
        )
    weights = SCORE_VERSIONS[score_version]

    # Load watchlist for asset indication metadata
    wl_config = load_watchlist_config(watchlist_path)
    indication_by_asset: dict[str, str | None] = {
        getattr(a, "asset_id", None): getattr(a, "indication", None)
        for a in getattr(wl_config, "watchlist", [])
    }

    conn = sqlite3.connect(str(knowledge_db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT rowid, asset_id, stage, therapeutic_area, scarcity_peer_count, "
            "strategic_fit_score, valuation_discount_score, capital_vulnerability_score, "
            "acquirer_candidates_json "
            "FROM ma_probability_snapshots"
        ).fetchall()

        updates: list[tuple] = []
        for row in rows:
            rowid = row["rowid"]
            asset_id: str | None = row["asset_id"]
            stage: str | None = row["stage"]
            ta: str | None = row["therapeutic_area"]
            peer_count: int = int(row["scarcity_peer_count"] or 0)
            sf_raw: float = float(row["strategic_fit_score"] or 0.0)
            vd: float = float(row["valuation_discount_score"] or 0.0)
            cv: float = float(row["capital_vulnerability_score"] or 0.0)

            # --- Sprint 22: cap strategic_fit_score at hard cap ---
            sf: float = round(min(sf_raw, _STRATEGIC_FIT_HARD_CAP), 6)

            # --- Re-score de_risking_stage_score with Sprint 20 function ---
            # Quality penalty attributes are not stored; they default to False
            # (conservative: base-score-only path through _derisking_stage_score).
            row_ns = SimpleNamespace(
                stage=stage,
                acquisition_readiness_bucket=None,
                acquisition_readiness_design_tier="standard",
                acquisition_readiness_prior_pos=None,
                acquisition_readiness_posterior_pos=None,
                acquisition_readiness_low_power=False,
                safety_overhang=False,
                prior_phase3_failure=False,
                label_uncertainty=False,
                prior_phase2_failure=False,
                regulatory_risk=False,
                endpoint_in_dispute=False,
                breakthrough_designation=False,
            )
            de_risk = _derisking_stage_score(row_ns)

            # --- Re-score scarcity with Sprint 20 function ---
            base_score, bucket = _scarcity_score_from_peer_count(peer_count)
            indication = indication_by_asset.get(asset_id)
            asset_ns = SimpleNamespace(
                indication=indication,
                therapeutic_area=ta,
                modality=None,       # not stored; no modality bonus applied
                mechanism_of_action=None,  # not stored; no MoA bonus applied
            )
            context_ns = SimpleNamespace(asset=asset_ns)
            modifier = _compute_scarcity_modifiers(context_ns)
            scarcity = round(min(max(base_score + modifier, 0.0), 0.80), 6)

            # --- Recompute composite probability using new score_version weights ---
            raw = (
                vd * weights["acquisition_discount"]
                + sf * weights["strategic_fit"]
                + de_risk * weights["derisking_stage"]
                + cv * weights["capital_vulnerability"]
                + scarcity * weights["scarcity"]
            )
            # The saturation-penalty sub_scores list mirrors _score_acquirer_candidate.
            # valuation_component_score is approximated by valuation_discount_score
            # (acquisition_discount weight = 0 for v1.4 so this doesn't affect raw).
            sub_scores = [vd, sf, de_risk, cv, scarcity]
            prob_penalised = apply_saturation_penalty(raw, sub_scores=sub_scores)

            # --- Sprint 22: apply transaction-likelihood gate ---
            # external_deal_activity and activist_signal not stored in snapshots;
            # default to 0.0 (conservative — gate fires more often, reducing FP rate).
            prob, _gate_codes = _apply_transaction_likelihood_gate(
                prob_penalised,
                financing_pressure=cv,
                external_deal_activity=0.0,
                activist_signal=0.0,
                catalyst_days=None,
                valuation_discount=vd,
                de_risking_stage=de_risk,
            )

            # --- Update acquirer_candidates_json with Sprint 22 caps ---
            updated_json = _rescore_candidate_json(
                row["acquirer_candidates_json"],
                strategic_fit_hard_cap=_STRATEGIC_FIT_HARD_CAP,
                apply_gate_fn=_apply_transaction_likelihood_gate,
                cv=cv,
                de_risk=de_risk,
            )

            updates.append((
                round(sf, 6),
                round(de_risk, 6),
                round(scarcity, 6),
                bucket,
                peer_count,
                round(prob, 6),
                updated_json,
                f"rescored:{score_version}:sprint22",
                rowid,
            ))

        conn.executemany(
            "UPDATE ma_probability_snapshots SET "
            "strategic_fit_score=?, de_risking_stage_score=?, scarcity_score=?, "
            "scarcity_bucket=?, scarcity_peer_count=?, probability=?, "
            "acquirer_candidates_json=?, run_id=? WHERE rowid=?",
            updates,
        )
        conn.commit()

        # Compute post-rescore diagnostics
        rows_after = conn.execute(
            "SELECT probability, scarcity_score, de_risking_stage_score, strategic_fit_score "
            "FROM ma_probability_snapshots WHERE probability IS NOT NULL"
        ).fetchall()
        scarcity_vals = [float(r[1]) for r in rows_after if r[1] is not None]
        derisking_vals = [float(r[2]) for r in rows_after if r[2] is not None]
        prob_vals = [float(r[0]) for r in rows_after if r[0] is not None]
        sf_vals = [float(r[3]) for r in rows_after if r[3] is not None]
        n = len(prob_vals)
        scarcity_cap = sum(1 for s in scarcity_vals if s >= SATURATION_THRESHOLD) / n if n else 0.0
        derisking_cap = sum(1 for s in derisking_vals if s >= SATURATION_THRESHOLD) / n if n else 0.0
        mna_cap = sum(1 for s in prob_vals if s >= SATURATION_THRESHOLD) / n if n else 0.0
        sf_cap = sum(1 for s in sf_vals if s >= SATURATION_THRESHOLD) / n if n else 0.0

        return MARescoredSummary(
            knowledge_db_path=str(Path(knowledge_db_path)),
            score_version=score_version,
            rows_rescored=len(updates),
            scarcity_cap_rate=round(scarcity_cap, 4),
            derisking_cap_rate=round(derisking_cap, 4),
            mna_screening_cap_rate=round(mna_cap, 4),
            strategic_fit_cap_rate=round(sf_cap, 4),
        )
    finally:
        conn.close()


def _render_summary(summary: MABackfillSummary) -> str:
    lines = [
        "M&A probability backfill complete",
        f"  Watchlist: {summary.watchlist_path}",
        f"  Knowledge DB: {summary.knowledge_db_path}",
        f"  Dataset mode: {summary.dataset_mode}",
        f"  Snapshot dates: {summary.snapshot_dates}",
        f"  Date range: {summary.snapshot_start} -> {summary.snapshot_end}",
        f"  Snapshot rows written: {summary.total_rows_written}",
        f"  Excluded assets: {summary.total_excluded_assets}",
        f"  Calibration rows: {summary.calibration_rows}",
        f"  Positive rows: {summary.calibration_positive_rows}",
        f"  Positive targets: {summary.calibration_positive_targets}",
        f"  Precision@15: {summary.precision_at_k}",
        f"  Recall@15: {summary.unique_target_recall_at_k}",
        f"  Median lead days@15: {summary.median_lead_days_at_k}",
        f"  Dataset CSV: {summary.dataset_csv_path}",
        f"  Metrics JSON: {summary.metrics_json_path}",
    ]
    if summary.calibration_fit_path:
        lines.append(f"  Calibration fit JSON: {summary.calibration_fit_path}")
    if summary.policy_comparison_json_path:
        lines.append(f"  Policy comparison JSON: {summary.policy_comparison_json_path}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical M&A probability snapshots")
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument("--db", required=True, help="KnowledgeStore SQLite path")
    parser.add_argument("--start", default=None, help="Optional YYYY-MM-DD start date")
    parser.add_argument("--end", default=None, help="Optional YYYY-MM-DD end date")
    parser.add_argument("--score-version", default="v1.2")
    parser.add_argument(
        "--dataset-mode",
        choices=["canonical_predeal", "historical_snapshot"],
        default="canonical_predeal",
    )
    parser.add_argument("--anchor-days-before-announcement", type=int, default=180)
    parser.add_argument("--controls-per-positive", type=int, default=2)
    parser.add_argument("--profiles-file", default="examples/research/acquirer_profiles")
    parser.add_argument("--comps-file", default="research/mna/comparable_deals.yaml")
    parser.add_argument("--vulnerability-file", default="research/mna/vulnerability_signals.yaml")
    parser.add_argument("--deal-universe", default="research/mna/deal_universe_2020_2026.yaml")
    parser.add_argument("--readiness-filter", choices=["strict", "off"], default="strict")
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument("--output-dir", default="outputs/analysis")
    args = parser.parse_args()

    summary = backfill_ma_probability_snapshots(
        watchlist_path=args.watchlist,
        knowledge_db_path=args.db,
        start_date=_parse_date(args.start) if args.start else None,
        end_date=_parse_date(args.end) if args.end else None,
        score_version=args.score_version,
        dataset_mode=args.dataset_mode,
        anchor_days_before_announcement=args.anchor_days_before_announcement,
        controls_per_positive=args.controls_per_positive,
        profiles_file=args.profiles_file,
        comps_file=args.comps_file,
        vulnerability_file=args.vulnerability_file,
        deal_universe_path=args.deal_universe,
        readiness_filter=args.readiness_filter == "strict",
        top_k=args.top_k,
        output_dir=args.output_dir,
    )
    print(_render_summary(summary))


if __name__ == "__main__":
    main()

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
from bve.intelligence.ma_probability import MAProbabilityRow, MAProbabilitySnapshotStore
from bve.intelligence.schemas.signals import Event
from bve.intelligence.taxonomy import EventType


def test_ma_probability_snapshot_store_round_trips_calibration_fields(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        row = _ma_row(
            asset_id="asset-take",
            ticker="TAKE",
            rank=1,
            probability=0.82,
            strategic_fit_score=0.76,
            therapeutic_area="oncology",
            days_to_catalyst=90,
        )

        written = snapshot_store.write_snapshots([row], snapshot_date=date(2025, 1, 1), run_id="run-1")
        snapshots = snapshot_store.list_snapshots()

        assert written == 1
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.ticker == "TAKE"
        assert snapshot.stage == "phase_3"
        assert snapshot.therapeutic_area == "oncology"
        assert snapshot.best_acquirer_name == "Pfizer"
        assert snapshot.strategic_fit_score == pytest.approx(0.76, abs=1e-9)
        assert snapshot.valuation_discount_score == pytest.approx(0.70, abs=1e-9)
        assert snapshot.scarcity_score == pytest.approx(0.55, abs=1e-9)
        assert snapshot.scarcity_peer_count == 4
        assert snapshot.scarcity_bucket == "medium"
        assert snapshot.days_to_catalyst == 90
        assert snapshot.estimated_deal_value_high_millions == pytest.approx(1200.0, abs=1e-9)
    finally:
        store.close()


def test_ma_calibration_builder_labels_takeouts_and_joins_screen_context(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take",
                    ticker="TAKE",
                    rank=1,
                    probability=0.91,
                    strategic_fit_score=0.84,
                    therapeutic_area="oncology",
                    days_to_catalyst=120,
                ),
                _ma_row(
                    asset_id="asset-ctrl",
                    ticker="CTRL",
                    rank=2,
                    probability=0.22,
                    strategic_fit_score=0.28,
                    therapeutic_area="oncology",
                    days_to_catalyst=220,
                ),
            ],
            snapshot_date=date(2025, 1, 1),
            run_id="run-1",
        )
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take",
                    ticker="TAKE",
                    rank=1,
                    probability=0.95,
                    strategic_fit_score=0.90,
                    therapeutic_area="oncology",
                    days_to_catalyst=5,
                ),
            ],
            snapshot_date=date(2025, 6, 5),
            run_id="run-2",
        )
        store.write_screen_snapshots(
            [
                _screen_row(
                    ticker="TAKE",
                    snapshot_date=date(2024, 12, 15),
                    spread_pp=22.5,
                    single_asset=True,
                    config_quality="gold",
                    market_exceeds_model=True,
                ),
                _screen_row(
                    ticker="CTRL",
                    snapshot_date=date(2025, 1, 1),
                    spread_pp=1.5,
                    single_asset=False,
                    config_quality="screening_grade",
                    market_exceeds_model=False,
                ),
            ]
        )
        store.add_event(
            Event(
                id="evt-partnership",
                event_type=EventType.PARTNERSHIP,
                asset_id="asset-take",
                company_id="co-take",
                observed_at=datetime(2024, 11, 1, 12, 0, tzinfo=timezone.utc),
                ingested_at=datetime(2024, 11, 1, 13, 0, tzinfo=timezone.utc),
                source_type="manual",
                headline="TAKE announces partnership",
                confidence=0.95,
            ),
            SourceTrace(source_type="unit_test", source_ref="evt-partnership"),
        )
        deal_universe_path = _write_deal_universe(tmp_path)

        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=deal_universe_path,
        )
        dataset = builder.build_dataset(lookahead_days=365)

        assert dataset.n_rows == 2
        assert dataset.n_positive_rows == 1
        take = next(row for row in dataset.rows if row.ticker == "TAKE")
        ctrl = next(row for row in dataset.rows if row.ticker == "CTRL")
        assert take.label == 1
        assert take.days_to_announcement == 151
        assert take.acquired_by == "Big Pharma"
        assert take.single_asset is True
        assert take.config_quality == "gold"
        assert take.market_exceeds_model is True
        assert take.prior_partnership_events == 1
        assert take.has_prior_partnership is True
        assert take.ta_deal_count_trailing_730d == 1
        assert take.ta_heat_score == pytest.approx(0.25, abs=1e-9)
        assert ctrl.label == 0
        assert ctrl.single_asset is False
    finally:
        store.close()


def test_ma_calibration_evaluate_reports_precision_and_recall(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take",
                    ticker="TAKE",
                    rank=1,
                    probability=0.91,
                    strategic_fit_score=0.84,
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-ctrl",
                    ticker="CTRL",
                    rank=2,
                    probability=0.22,
                    strategic_fit_score=0.28,
                    therapeutic_area="oncology",
                ),
            ],
            snapshot_date=date(2025, 1, 1),
            run_id="run-1",
        )
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-ctrl",
                    ticker="CTRL",
                    rank=1,
                    probability=0.77,
                    strategic_fit_score=0.55,
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-other",
                    ticker="OTHR",
                    rank=2,
                    probability=0.31,
                    strategic_fit_score=0.18,
                    therapeutic_area="rare disease",
                ),
            ],
            snapshot_date=date(2025, 2, 1),
            run_id="run-2",
        )
        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=_write_deal_universe(tmp_path),
        )

        dataset = builder.build_dataset(lookahead_days=365)
        metrics = builder.evaluate(dataset, top_k=1)

        assert metrics.n_snapshot_dates == 2
        assert metrics.n_positive_targets == 1
        assert metrics.n_positive_targets_in_top_k == 1
        assert metrics.precision_at_k == pytest.approx(0.5, abs=1e-9)
        assert metrics.unique_target_recall_at_k == pytest.approx(1.0, abs=1e-9)
        assert metrics.median_lead_days_at_k == pytest.approx(151.0, abs=1e-9)
        assert metrics.average_probability_positive == pytest.approx(0.91, abs=1e-9)
        assert metrics.average_probability_control == pytest.approx(0.433333, abs=1e-6)
    finally:
        store.close()


def test_ma_calibration_compare_baselines_reports_simple_rankers(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take",
                    ticker="TAKE",
                    rank=2,
                    probability=0.25,
                    strategic_fit_score=0.92,
                    valuation_discount_score=0.10,
                    capital_vulnerability_score=0.88,
                    de_risking_stage_score=0.80,
                    scarcity_score=1.0,
                    scarcity_peer_count=1,
                    scarcity_bucket="very_high",
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-ctrl",
                    ticker="CTRL",
                    rank=1,
                    probability=0.91,
                    strategic_fit_score=0.20,
                    valuation_discount_score=0.95,
                    capital_vulnerability_score=0.30,
                    de_risking_stage_score=0.25,
                    scarcity_score=0.10,
                    scarcity_peer_count=12,
                    scarcity_bucket="very_low",
                    therapeutic_area="oncology",
                ),
            ],
            snapshot_date=date(2025, 1, 1),
            run_id="run-1",
        )
        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=_write_deal_universe(tmp_path),
        )

        dataset = builder.build_dataset(lookahead_days=365)
        comparison = builder.compare_baselines(dataset, top_k=1)

        probability = comparison.baseline("stored_probability")
        strategic_fit = comparison.baseline("strategic_fit_only")
        fit_plus_scarcity = comparison.baseline("strategic_fit_plus_scarcity")
        fit_plus_capital = comparison.baseline("strategic_fit_plus_capital")
        fit_plus_derisking = comparison.baseline("strategic_fit_plus_derisking")
        no_valuation = comparison.baseline("composite_without_valuation_discount")
        inverted_valuation = comparison.baseline("composite_with_inverted_valuation_discount")

        assert probability is not None
        assert strategic_fit is not None
        assert fit_plus_scarcity is not None
        assert fit_plus_capital is not None
        assert fit_plus_derisking is not None
        assert no_valuation is not None
        assert inverted_valuation is not None

        assert probability.precision_at_k == pytest.approx(0.0, abs=1e-9)
        assert strategic_fit.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert fit_plus_scarcity.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert fit_plus_capital.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert fit_plus_derisking.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert no_valuation.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert inverted_valuation.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert strategic_fit.average_score_positive == pytest.approx(0.92, abs=1e-9)
        assert strategic_fit.average_score_control == pytest.approx(0.20, abs=1e-9)
    finally:
        store.close()


def test_ma_calibration_build_canonical_dataset_deduplicates_targets_and_matches_controls(
    tmp_path: Path,
):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take",
                    ticker="TAKE",
                    rank=1,
                    probability=0.88,
                    strategic_fit_score=0.86,
                    therapeutic_area="oncology",
                    days_to_catalyst=130,
                ),
                _ma_row(
                    asset_id="asset-ctrl1",
                    ticker="CTRL1",
                    rank=2,
                    probability=0.31,
                    strategic_fit_score=0.40,
                    therapeutic_area="oncology",
                    days_to_catalyst=150,
                ),
                _ma_row(
                    asset_id="asset-ctrl2",
                    ticker="CTRL2",
                    rank=3,
                    probability=0.29,
                    strategic_fit_score=0.35,
                    therapeutic_area="oncology",
                    days_to_catalyst=160,
                ),
                _ma_row(
                    asset_id="asset-futr",
                    ticker="FUTR",
                    rank=4,
                    probability=0.27,
                    strategic_fit_score=0.22,
                    therapeutic_area="oncology",
                    days_to_catalyst=170,
                ),
            ],
            snapshot_date=date(2025, 1, 1),
            run_id="run-1",
        )
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take",
                    ticker="TAKE",
                    rank=1,
                    probability=0.91,
                    strategic_fit_score=0.90,
                    therapeutic_area="oncology",
                    days_to_catalyst=60,
                ),
            ],
            snapshot_date=date(2025, 3, 1),
            run_id="run-2",
        )

        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=_write_deal_universe(
                tmp_path,
                extra_deals=[
                    {
                        "target_name": "Future Takeout",
                        "target_ticker": "FUTR",
                        "acquirer": "Another Buyer",
                        "announcement_date": "2026-03-01",
                        "headline_value_millions": 1800.0,
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_3",
                    },
                ],
            ),
        )

        historical = builder.build_dataset(lookahead_days=365)
        canonical = builder.build_canonical_dataset(
            lookahead_days=365,
            anchor_days_before_announcement=120,
            controls_per_positive=2,
        )

        assert historical.n_positive_rows == 2
        assert canonical.dataset_mode == "canonical_predeal"
        assert canonical.n_positive_rows == 1
        assert canonical.n_control_rows == 2
        assert canonical.n_rows == 3

        take = next(row for row in canonical.rows if row.ticker == "TAKE")
        controls = [row for row in canonical.rows if row.label == 0]
        assert take.snapshot_date == date(2025, 1, 1)
        assert {row.ticker for row in controls} == {"CTRL1", "CTRL2"}
        assert {row.snapshot_date for row in controls} == {date(2025, 1, 1)}
    finally:
        store.close()


def test_ma_calibration_evaluate_canonical_dataset_uses_global_case_control_ranking(
    tmp_path: Path,
):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take-a",
                    ticker="TAKA",
                    rank=1,
                    probability=0.92,
                    strategic_fit_score=0.85,
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-ctrl-a",
                    ticker="CTRA",
                    rank=2,
                    probability=0.51,
                    strategic_fit_score=0.30,
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-ctrl-b",
                    ticker="CTRB",
                    rank=3,
                    probability=0.41,
                    strategic_fit_score=0.25,
                    therapeutic_area="oncology",
                ),
            ],
            snapshot_date=date(2025, 1, 1),
            run_id="run-1",
        )
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take-b",
                    ticker="TAKB",
                    rank=1,
                    probability=0.83,
                    strategic_fit_score=0.78,
                    therapeutic_area="rare disease",
                ),
                _ma_row(
                    asset_id="asset-ctrl-c",
                    ticker="CTRC",
                    rank=2,
                    probability=0.45,
                    strategic_fit_score=0.32,
                    therapeutic_area="rare disease",
                ),
                _ma_row(
                    asset_id="asset-ctrl-d",
                    ticker="CTRD",
                    rank=3,
                    probability=0.36,
                    strategic_fit_score=0.20,
                    therapeutic_area="rare disease",
                ),
            ],
            snapshot_date=date(2025, 2, 1),
            run_id="run-2",
        )

        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=_write_deal_universe(
                tmp_path,
                deals=[
                    {
                        "target_name": "Takeout A",
                        "target_ticker": "TAKA",
                        "acquirer": "Buyer A",
                        "announcement_date": "2025-06-01",
                        "headline_value_millions": 2500.0,
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_3",
                    },
                    {
                        "target_name": "Takeout B",
                        "target_ticker": "TAKB",
                        "acquirer": "Buyer B",
                        "announcement_date": "2025-08-15",
                        "headline_value_millions": 1800.0,
                        "therapeutic_area": "rare disease",
                        "phase_at_acquisition": "phase_2",
                    },
                ],
            ),
        )

        canonical = builder.build_canonical_dataset(
            lookahead_days=365,
            anchor_days_before_announcement=150,
            controls_per_positive=2,
        )
        metrics = builder.evaluate(canonical, top_k=2)
        comparison = builder.compare_baselines(canonical, top_k=2)

        assert canonical.n_positive_rows == 2
        assert canonical.n_control_rows == 4
        assert metrics.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert metrics.unique_target_recall_at_k == pytest.approx(1.0, abs=1e-9)
        assert metrics.average_probability_positive == pytest.approx(0.875, abs=1e-9)
        assert metrics.average_probability_control == pytest.approx(0.4325, abs=1e-9)

        probability = comparison.baseline("stored_probability")
        assert probability is not None
        assert probability.precision_at_k == pytest.approx(1.0, abs=1e-9)
        assert probability.unique_target_recall_at_k == pytest.approx(1.0, abs=1e-9)
    finally:
        store.close()


def test_ma_calibration_fit_logistic_model_on_canonical_dataset(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    try:
        snapshot_store = MAProbabilitySnapshotStore(store)
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take-a",
                    ticker="TAKA",
                    rank=1,
                    probability=0.92,
                    strategic_fit_score=0.85,
                    valuation_discount_score=0.15,
                    capital_vulnerability_score=0.35,
                    de_risking_stage_score=1.0,
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-ctrl-a",
                    ticker="CTRA",
                    rank=2,
                    probability=0.51,
                    strategic_fit_score=0.51,
                    valuation_discount_score=0.80,
                    capital_vulnerability_score=0.15,
                    de_risking_stage_score=0.45,
                    therapeutic_area="oncology",
                ),
                _ma_row(
                    asset_id="asset-ctrl-b",
                    ticker="CTRB",
                    rank=3,
                    probability=0.41,
                    strategic_fit_score=0.41,
                    valuation_discount_score=1.0,
                    capital_vulnerability_score=0.0,
                    de_risking_stage_score=0.45,
                    therapeutic_area="oncology",
                ),
            ],
            snapshot_date=date(2025, 1, 1),
            run_id="run-1",
        )
        snapshot_store.write_snapshots(
            [
                _ma_row(
                    asset_id="asset-take-b",
                    ticker="TAKB",
                    rank=1,
                    probability=0.83,
                    strategic_fit_score=0.78,
                    valuation_discount_score=0.25,
                    capital_vulnerability_score=0.35,
                    de_risking_stage_score=1.0,
                    therapeutic_area="rare disease",
                ),
                _ma_row(
                    asset_id="asset-ctrl-c",
                    ticker="CTRC",
                    rank=2,
                    probability=0.45,
                    strategic_fit_score=0.45,
                    valuation_discount_score=0.80,
                    capital_vulnerability_score=0.15,
                    de_risking_stage_score=0.45,
                    therapeutic_area="rare disease",
                ),
                _ma_row(
                    asset_id="asset-ctrl-d",
                    ticker="CTRD",
                    rank=3,
                    probability=0.36,
                    strategic_fit_score=0.36,
                    valuation_discount_score=1.0,
                    capital_vulnerability_score=0.0,
                    de_risking_stage_score=0.45,
                    therapeutic_area="rare disease",
                ),
            ],
            snapshot_date=date(2025, 2, 1),
            run_id="run-2",
        )

        builder = MACalibrationDatasetBuilder(
            knowledge_store=store,
            deal_universe_path=_write_deal_universe(
                tmp_path,
                deals=[
                    {
                        "target_name": "Takeout A",
                        "target_ticker": "TAKA",
                        "acquirer": "Buyer A",
                        "announcement_date": "2025-06-01",
                        "headline_value_millions": 2500.0,
                        "therapeutic_area": "oncology",
                        "phase_at_acquisition": "phase_3",
                    },
                    {
                        "target_name": "Takeout B",
                        "target_ticker": "TAKB",
                        "acquirer": "Buyer B",
                        "announcement_date": "2025-08-15",
                        "headline_value_millions": 1800.0,
                        "therapeutic_area": "rare disease",
                        "phase_at_acquisition": "phase_2",
                    },
                ],
            ),
        )
        canonical = builder.build_canonical_dataset(
            lookahead_days=365,
            anchor_days_before_announcement=150,
            controls_per_positive=2,
        )
        result = builder.fit_logistic_model(canonical, l2_penalty=1.0, top_k=2)

        assert result.dataset_mode == "canonical_predeal"
        assert result.n_rows == 6
        assert result.n_match_groups == 2
        assert result.fit_converged is True
        assert result.cross_validated_groups_converged == 2
        assert result.feature_names == [
            "stored_probability",
            "strategic_fit_score",
            "capital_vulnerability_score",
            "log_enterprise_value",
        ]
        assert len(result.coefficients) == 4
        assert len(result.predictions) == 6
        assert all(item.match_group_id for item in result.predictions)
        assert result.fitted_metrics.auc is not None
        assert result.cross_validated_metrics.auc is not None
        assert result.cross_validated_metrics.precision_at_k is not None
    finally:
        store.close()


def _ma_row(
    *,
    asset_id: str,
    ticker: str,
    rank: int,
    probability: float,
    strategic_fit_score: float,
    therapeutic_area: str,
    days_to_catalyst: int | None = None,
    valuation_discount_score: float = 0.70,
    de_risking_stage_score: float = 0.95,
    capital_vulnerability_score: float = 0.60,
    scarcity_score: float = 0.55,
    scarcity_peer_count: int = 4,
    scarcity_bucket: str = "medium",
) -> MAProbabilityRow:
    return MAProbabilityRow(
        rank=rank,
        asset_id=asset_id,
        company_id=f"co-{ticker.lower()}",
        ticker=ticker,
        stage="phase_3",
        therapeutic_area=therapeutic_area,
        acquisition_ready=True,
        enterprise_value_millions=500.0,
        acquisition_discount=1.8,
        days_to_catalyst=days_to_catalyst,
        mna_probability_score=probability,
        p_acquisition=probability,
        raw_probability=probability,
        above_alert_threshold=probability >= 0.7,
        score_version="v1.0",
        best_acquirer_id="pfizer",
        best_acquirer_name="Pfizer",
        best_acquirer_fit_score=strategic_fit_score,
        runner_up_acquirer_id="lilly",
        valuation_discount_score=valuation_discount_score,
        strategic_fit_score=strategic_fit_score,
        de_risking_stage_score=de_risking_stage_score,
        capital_vulnerability_score=capital_vulnerability_score,
        scarcity_score=scarcity_score,
        scarcity_peer_count=scarcity_peer_count,
        scarcity_bucket=scarcity_bucket,
        vulnerability_score=capital_vulnerability_score,
        model_rnpv_millions=900.0,
        peak_sales_millions=700.0,
        estimated_deal_value_low_millions=800.0,
        estimated_deal_value_high_millions=1200.0,
        estimated_deal_value_source="comparable_deals",
        cash_runway_quarters=3.0,
        cash_runway_pressure_score=0.85,
        cash_runway_risk_level="high",
        runway_gap_months=2.0,
        nearest_catalyst_date=date(2025, 5, 1),
        target_signal_score=0.55,
        external_deal_pressure_score=0.25,
        target_signal_ids=[],
        external_deal_signal_ids=[],
        hard_fail_reasons=[],
        matched_therapeutic_gap=therapeutic_area,
        matched_modality="small_molecule",
        matched_priorities=["pipeline gap"],
        explanation="Synthetic calibration row.",
        acquirer_candidates=[],
    )


def _screen_row(
    *,
    ticker: str,
    snapshot_date: date,
    spread_pp: float,
    single_asset: bool,
    config_quality: str,
    market_exceeds_model: bool,
):
    return SimpleNamespace(
        ticker=ticker,
        data_date=snapshot_date,
        program_label=f"{ticker} program",
        stage="phase_3",
        ta="oncology",
        model_pos=0.55,
        implied_pos=0.33,
        spread_pp=spread_pp,
        rnpv_millions=900.0,
        ev_millions=500.0,
        acquisition_discount_pct=80.0,
        next_catalyst="Readout",
        catalyst_date=date(2025, 5, 1),
        days_to_catalyst=120,
        single_asset=single_asset,
        approximation_warning=None if single_asset else "multi_asset",
        thesis_strength=0.7,
        market_exceeds_model=market_exceeds_model,
        config_quality=config_quality,
    )


def _write_deal_universe(
    tmp_path: Path,
    *,
    deals: list[dict] | None = None,
    extra_deals: list[dict] | None = None,
) -> Path:
    path = tmp_path / "deal_universe.yaml"
    base_deals = deals or [
        {
            "target_name": "Peer Onco",
            "target_ticker": "PEER",
            "acquirer": "Peer Buyer",
            "announcement_date": "2024-07-01",
            "headline_value_millions": 1500.0,
            "therapeutic_area": "oncology",
            "phase_at_acquisition": "phase_2",
        },
        {
            "target_name": "Takeout Co",
            "target_ticker": "TAKE",
            "acquirer": "Big Pharma",
            "announcement_date": "2025-06-01",
            "headline_value_millions": 2500.0,
            "therapeutic_area": "oncology",
            "phase_at_acquisition": "phase_3",
        },
    ]
    if extra_deals:
        base_deals = [*base_deals, *extra_deals]
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2025-12-31",
                "deals": base_deals,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path

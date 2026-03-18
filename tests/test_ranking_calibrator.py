from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from bve.analysis.ranking_calibrator import RankingCalibrator
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ranking import DEFAULT_EVENT_TYPE_SCORES


def _insert_resolved_forecast(
    store: KnowledgeStore,
    *,
    idx: int,
    event_type: str,
    predicted_direction: str,
    actual_return_t30: float,
    conf: float = 0.6,
) -> None:
    ts = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)
    store._conn.execute(  # noqa: SLF001 - unit-test fixture setup
        """
        INSERT INTO forecast_records(
            forecast_id, signal_id, event_id, asset_id, event_type, signal_date,
            extraction_confidence, predicted_direction, predicted_delta_pct,
            horizon_days, predicted_at, actual_market_return_t30,
            actual_market_return_t180, outcome_correct, resolved, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"fc-{event_type}-{idx}",
            f"sig-{event_type}-{idx}",
            f"evt-{event_type}-{idx}",
            "asset-1",
            event_type,
            "2026-03-01",
            conf,
            predicted_direction,
            5.0,
            30,
            ts.isoformat(),
            actual_return_t30,
            None,
            None,
            1,
            ts.isoformat(),
        ),
    )
    store._conn.commit()  # noqa: SLF001 - unit-test fixture setup


def test_calibrator_zero_resolved_forecasts_writes_default_weights(tmp_path: Path):
    store = KnowledgeStore(":memory:")
    out_path = tmp_path / "ranking_calibration.yaml"

    calibrator = RankingCalibrator(store, calibration_path=out_path)
    report = calibrator.calibrate()
    calibrator.write_calibration(report)

    assert report.n_resolved_forecasts == 0
    assert report.event_type_weights == DEFAULT_EVENT_TYPE_SCORES

    payload = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert payload["event_type_weights"] == DEFAULT_EVENT_TYPE_SCORES
    assert payload["confidence_scaling_factor"] == 1.0
    store.close()


def test_calibrator_n_lt_20_keeps_event_weight_unchanged(tmp_path: Path):
    store = KnowledgeStore(":memory:")
    out_path = tmp_path / "ranking_calibration.yaml"

    for i in range(15):
        _insert_resolved_forecast(
            store,
            idx=i,
            event_type="publication",
            predicted_direction="up" if i % 2 == 0 else "down",
            actual_return_t30=0.05 if i % 3 == 0 else -0.04,
        )

    report = RankingCalibrator(store, calibration_path=out_path).calibrate()
    assert report.event_type_weights["publication"] == DEFAULT_EVENT_TYPE_SCORES["publication"]
    store.close()


def test_calibrator_n_gte_20_applies_dampened_f1_update_and_drift_alert(tmp_path: Path):
    store = KnowledgeStore(":memory:")
    out_path = tmp_path / "ranking_calibration.yaml"

    idx = 0
    # TP = 8
    for _ in range(8):
        _insert_resolved_forecast(
            store,
            idx=idx,
            event_type="financing",
            predicted_direction="up",
            actual_return_t30=0.06,
        )
        idx += 1
    # FP = 2
    for _ in range(2):
        _insert_resolved_forecast(
            store,
            idx=idx,
            event_type="financing",
            predicted_direction="up",
            actual_return_t30=-0.05,
        )
        idx += 1
    # FN = 2
    for _ in range(2):
        _insert_resolved_forecast(
            store,
            idx=idx,
            event_type="financing",
            predicted_direction="down",
            actual_return_t30=0.04,
        )
        idx += 1
    # TN = 13
    for _ in range(13):
        _insert_resolved_forecast(
            store,
            idx=idx,
            event_type="financing",
            predicted_direction="down",
            actual_return_t30=-0.03,
        )
        idx += 1

    report = RankingCalibrator(store, calibration_path=out_path).calibrate()
    prior = DEFAULT_EVENT_TYPE_SCORES["financing"]
    expected = 0.8 * prior + 0.2 * 0.8

    assert report.event_type_weights["financing"] == round(expected, 6)
    assert any("financing" in msg for msg in report.drift_alerts)
    store.close()


def test_calibrator_clamps_negative_prior_weights_from_file(tmp_path: Path):
    store = KnowledgeStore(":memory:")
    out_path = tmp_path / "ranking_calibration.yaml"
    out_path.write_text(
        yaml.safe_dump(
            {
                "confidence_scaling_factor": 1.0,
                "event_type_weights": {
                    "trial_readout": -0.25,
                },
            }
        ),
        encoding="utf-8",
    )

    report = RankingCalibrator(store, calibration_path=out_path).calibrate()
    assert report.event_type_weights["trial_readout"] == 0.0
    store.close()

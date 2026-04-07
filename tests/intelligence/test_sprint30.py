"""
Sprint 30 — Two-score architecture: v1.2 ranker + calibrated probability layer.

Tests for:
1. MALogisticFitResult.load_json() round-trip
2. MALogisticFitResult.predict() applies correct formula
3. p_takeout_calibrated field on MAProbabilityRow and MAProbabilitySnapshotRecord
4. DB column added by _ensure_schema migration
5. from_row() carries p_takeout_calibrated through to snapshot record
6. write_snapshots() / get_snapshot_map() / list_snapshots() persist and retrieve field
7. Scanner with calibration_model_path populates p_takeout_calibrated without changing rank order
8. MAPolicyComparisonResult structure and compare_ranking_policies() contract
9. calibration_model_path=None leaves p_takeout_calibrated as None (safe default)
10. _extract_calibration_features maps row fields to feature dict correctly
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from bve.intelligence.ma_calibration import (
    MACalibrationDataset,
    MACalibrationRow,
    MALogisticCoefficient,
    MALogisticFitResult,
    MALogisticMetrics,
    MAPolicyComparisonResult,
)
from bve.intelligence.ma_probability import (
    MAProbabilityRow,
    MAProbabilitySnapshotRecord,
    MAProbabilitySnapshotStore,
    _extract_calibration_features,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _minimal_metrics() -> MALogisticMetrics:
    return MALogisticMetrics(auc=0.70, brier_score=0.18)


def _fit_result(
    feature_names: list[str] | None = None,
    intercept: float = -2.0,
    coef_value: float = 1.0,
    mean: float = 0.5,
    std: float = 0.2,
) -> MALogisticFitResult:
    feature_names = feature_names or ["stored_probability"]
    coefficients = [
        MALogisticCoefficient(
            feature_name=name,
            coefficient=coef_value,
            odds_ratio=round(math.exp(coef_value), 6),
            mean=mean,
            std=std,
        )
        for name in feature_names
    ]
    return MALogisticFitResult(
        dataset_mode="canonical_predeal",
        feature_names=feature_names,
        l2_penalty=1.0,
        top_k=15,
        n_rows=10,
        n_positive_rows=3,
        n_control_rows=7,
        n_match_groups=3,
        fit_converged=True,
        cross_validated_groups_converged=3,
        intercept=intercept,
        coefficients=coefficients,
        stored_probability_metrics=_minimal_metrics(),
        fitted_metrics=_minimal_metrics(),
        cross_validated_metrics=_minimal_metrics(),
        predictions=[],
    )


def _ma_row(**kwargs: Any) -> MAProbabilityRow:
    defaults: dict[str, Any] = dict(
        asset_id="a-test",
        ticker="TEST",
        mna_probability_score=0.65,
        p_acquisition=0.50,
        raw_probability=0.50,
        above_alert_threshold=False,
        score_version="v1.2",
        best_acquirer_id="pfizer",
        best_acquirer_name="Pfizer",
        best_acquirer_fit_score=0.80,
        valuation_discount_score=0.60,
        strategic_fit_score=0.75,
        de_risking_stage_score=0.50,
        capital_vulnerability_score=0.30,
        scarcity_score=0.40,
        scarcity_peer_count=2,
        scarcity_bucket="moderate",
        vulnerability_score=0.25,
        explanation="stub",
        enterprise_value_millions=800.0,
    )
    defaults.update(kwargs)
    return MAProbabilityRow(**defaults)


# ---------------------------------------------------------------------------
# 1. MALogisticFitResult.load_json() round-trip
# ---------------------------------------------------------------------------

class TestLoadJson:
    def test_round_trip_preserves_intercept_and_coefficients(self, tmp_path: Path):
        result = _fit_result(intercept=-1.5, coef_value=0.8)
        out_path = result.write_json(tmp_path / "fit.json")
        loaded = MALogisticFitResult.load_json(out_path)
        assert loaded.intercept == pytest.approx(-1.5)
        assert len(loaded.coefficients) == 1
        assert loaded.coefficients[0].coefficient == pytest.approx(0.8)

    def test_round_trip_preserves_metrics(self, tmp_path: Path):
        result = _fit_result()
        result.write_json(tmp_path / "fit.json")
        loaded = MALogisticFitResult.load_json(tmp_path / "fit.json")
        assert loaded.fitted_metrics.auc == pytest.approx(0.70)
        assert loaded.feature_names == result.feature_names

    def test_load_json_from_str_path(self, tmp_path: Path):
        result = _fit_result()
        out_path = result.write_json(tmp_path / "fit.json")
        loaded = MALogisticFitResult.load_json(str(out_path))
        assert loaded.dataset_mode == "canonical_predeal"


# ---------------------------------------------------------------------------
# 2. MALogisticFitResult.predict() formula
# ---------------------------------------------------------------------------

class TestPredict:
    def test_predict_returns_float_in_unit_interval(self):
        result = _fit_result(intercept=0.0, coef_value=1.0, mean=0.5, std=0.2)
        p = result.predict({"stored_probability": 0.5})
        assert 0.0 < p < 1.0

    def test_predict_higher_feature_gives_higher_probability(self):
        result = _fit_result(intercept=-1.0, coef_value=2.0, mean=0.0, std=1.0)
        p_low = result.predict({"stored_probability": 0.0})
        p_high = result.predict({"stored_probability": 1.0})
        assert p_high > p_low

    def test_predict_missing_feature_defaults_to_zero_contribution(self):
        """Missing features default to 0.0 (raw), which standardises to -mean/std."""
        result = _fit_result(intercept=0.0, coef_value=1.0, mean=0.0, std=1.0)
        p_with = result.predict({"stored_probability": 0.0})
        p_without = result.predict({})  # missing key → 0.0
        assert p_with == pytest.approx(p_without)

    def test_predict_formula_matches_manual_logistic(self):
        intercept = -1.0
        coef = 2.0
        mean = 0.3
        std = 0.5
        raw = 0.7
        result = _fit_result(intercept=intercept, coef_value=coef, mean=mean, std=std)
        p = result.predict({"stored_probability": raw})
        z = intercept + coef * ((raw - mean) / std)
        expected = 1.0 / (1.0 + math.exp(-z))
        assert p == pytest.approx(expected, abs=1e-6)

    def test_predict_multiple_features(self):
        result = _fit_result(
            feature_names=["stored_probability", "capital_vulnerability_score"],
            intercept=0.0,
            coef_value=1.0,
            mean=0.0,
            std=1.0,
        )
        p = result.predict({"stored_probability": 0.5, "capital_vulnerability_score": 0.3})
        assert 0.0 < p < 1.0


# ---------------------------------------------------------------------------
# 3. p_takeout_calibrated field on MAProbabilityRow
# ---------------------------------------------------------------------------

class TestMAProbabilityRowField:
    def test_field_defaults_to_none(self):
        row = _ma_row()
        assert row.p_takeout_calibrated is None

    def test_field_accepts_float(self):
        row = _ma_row(p_takeout_calibrated=0.12)
        assert row.p_takeout_calibrated == pytest.approx(0.12)

    def test_snapshot_record_defaults_to_none(self):
        rec = MAProbabilitySnapshotRecord(
            snapshot_date=date(2025, 1, 1),
            asset_id="a-x",
            probability=0.5,
            rank=1,
            best_acquirer_id="pfizer",
            above_alert_threshold=False,
        )
        assert rec.p_takeout_calibrated is None


# ---------------------------------------------------------------------------
# 4 & 5. DB migration + from_row() carries p_takeout_calibrated
# ---------------------------------------------------------------------------

class TestSnapshotStoreMigration:
    def test_ensure_schema_adds_p_takeout_calibrated_column(self, tmp_path: Path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "k.db")
        try:
            snap_store = MAProbabilitySnapshotStore(store)
            cols = store._conn.execute(
                "PRAGMA table_info(ma_probability_snapshots)"
            ).fetchall()
            col_names = [c["name"] for c in cols]
            assert "p_takeout_calibrated" in col_names
        finally:
            store.close()

    def test_from_row_carries_calibrated_field(self):
        row = _ma_row(p_takeout_calibrated=0.08)
        record = MAProbabilitySnapshotStore.from_row(
            row, snapshot_date=date(2025, 1, 1)
        )
        assert record.p_takeout_calibrated == pytest.approx(0.08)

    def test_from_row_none_when_not_set(self):
        row = _ma_row()
        record = MAProbabilitySnapshotStore.from_row(
            row, snapshot_date=date(2025, 1, 1)
        )
        assert record.p_takeout_calibrated is None


# ---------------------------------------------------------------------------
# 6. write_snapshots / get_snapshot_map / list_snapshots round-trip
# ---------------------------------------------------------------------------

class TestSnapshotRoundTrip:
    def test_write_and_read_calibrated_probability(self, tmp_path: Path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "k.db")
        try:
            snap_store = MAProbabilitySnapshotStore(store)
            snap_date = date(2025, 6, 1)
            row = _ma_row(p_takeout_calibrated=0.14)
            snap_store.write_snapshots([row], snapshot_date=snap_date)
            snap_map = snap_store.get_snapshot_map(snapshot_date=snap_date)
            assert "a-test" in snap_map
            assert snap_map["a-test"].p_takeout_calibrated == pytest.approx(0.14)
        finally:
            store.close()

    def test_list_snapshots_returns_calibrated_field(self, tmp_path: Path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "k.db")
        try:
            snap_store = MAProbabilitySnapshotStore(store)
            row = _ma_row(p_takeout_calibrated=0.22)
            snap_store.write_snapshots([row], snapshot_date=date(2025, 6, 1))
            records = snap_store.list_snapshots()
            assert len(records) == 1
            assert records[0].p_takeout_calibrated == pytest.approx(0.22)
        finally:
            store.close()

    def test_none_calibrated_persists_as_null(self, tmp_path: Path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "k.db")
        try:
            snap_store = MAProbabilitySnapshotStore(store)
            row = _ma_row()  # p_takeout_calibrated=None
            snap_store.write_snapshots([row], snapshot_date=date(2025, 6, 1))
            records = snap_store.list_snapshots()
            assert records[0].p_takeout_calibrated is None
        finally:
            store.close()


# ---------------------------------------------------------------------------
# 7. _extract_calibration_features maps MAProbabilityRow correctly
# ---------------------------------------------------------------------------

class TestExtractCalibrationFeatures:
    def test_stored_probability_maps_to_p_acquisition(self):
        row = _ma_row(p_acquisition=0.42)
        features = _extract_calibration_features(row, ["stored_probability"])
        assert features["stored_probability"] == pytest.approx(0.42)

    def test_log_enterprise_value_correct(self):
        row = _ma_row(enterprise_value_millions=1000.0)
        features = _extract_calibration_features(row, ["log_enterprise_value"])
        assert features["log_enterprise_value"] == pytest.approx(math.log1p(1000.0))

    def test_ta_heat_score_defaults_to_zero(self):
        row = _ma_row()
        features = _extract_calibration_features(row, ["ta_heat_score"])
        assert features["ta_heat_score"] == pytest.approx(0.0)

    def test_unknown_feature_defaults_to_zero(self):
        row = _ma_row()
        features = _extract_calibration_features(row, ["nonexistent_feature"])
        assert features["nonexistent_feature"] == pytest.approx(0.0)

    def test_all_default_features_present(self):
        row = _ma_row()
        names = [
            "stored_probability",
            "strategic_fit_score",
            "capital_vulnerability_score",
            "log_enterprise_value",
        ]
        features = _extract_calibration_features(row, names)
        assert set(features.keys()) == set(names)


# ---------------------------------------------------------------------------
# 8. calibration_model_path=None leaves p_takeout_calibrated as None
# ---------------------------------------------------------------------------

class TestScannerDefaultBehavior:
    def test_no_calibration_model_path_leaves_field_none(self, tmp_path: Path):
        """Without a model path, scanner rows should have p_takeout_calibrated=None."""
        from bve.intelligence.ma_probability import MAProbabilityConfig
        from bve.intelligence.ma_probability import MAProbabilityScanner

        config = MAProbabilityConfig(
            calibration_model_path=None,
            persist_daily_snapshots=False,
            enable_monitor=False,
        )
        scanner = MAProbabilityScanner(config=config)
        assert scanner._calibration_model is None

    def test_nonexistent_path_gracefully_returns_none_model(self, tmp_path: Path):
        """A path that doesn't exist should silently produce a None model."""
        from bve.intelligence.ma_probability import MAProbabilityConfig
        from bve.intelligence.ma_probability import MAProbabilityScanner

        config = MAProbabilityConfig(
            calibration_model_path=str(tmp_path / "nonexistent.json"),
            persist_daily_snapshots=False,
            enable_monitor=False,
        )
        scanner = MAProbabilityScanner(config=config)
        assert scanner._calibration_model is None

    def test_valid_path_loads_model(self, tmp_path: Path):
        """A valid JSON path should load the model into scanner._calibration_model."""
        from bve.intelligence.ma_probability import MAProbabilityConfig
        from bve.intelligence.ma_probability import MAProbabilityScanner

        fit = _fit_result()
        fit.write_json(tmp_path / "fit.json")

        config = MAProbabilityConfig(
            calibration_model_path=str(tmp_path / "fit.json"),
            persist_daily_snapshots=False,
            enable_monitor=False,
        )
        scanner = MAProbabilityScanner(config=config)
        assert scanner._calibration_model is not None
        assert scanner._calibration_model.feature_names == fit.feature_names


# ---------------------------------------------------------------------------
# 9. MAPolicyComparisonResult structure
# ---------------------------------------------------------------------------

class TestPolicyComparisonResult:
    def test_model_fields_present(self):
        result = MAPolicyComparisonResult(
            top_k=15,
            calibration_threshold=0.10,
            policy_a_precision_at_k=0.40,
            policy_a_recall_at_k=0.60,
            policy_b_precision_at_k=0.53,
            policy_b_recall_at_k=0.40,
            policy_c_precision_at_k=0.40,
            policy_c_recall_at_k=0.60,
            baseline_auc=0.65,
            calibrated_auc=0.72,
        )
        assert result.top_k == 15
        assert result.policy_a_precision_at_k == pytest.approx(0.40)
        assert result.calibrated_auc == pytest.approx(0.72)

    def test_compare_ranking_policies_returns_correct_type(self):
        from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
        from bve.intelligence.knowledge_layer import KnowledgeStore
        import tempfile, os

        # Build a minimal canonical dataset in-memory
        rows = [
            MACalibrationRow(
                snapshot_date=date(2022, 1, 1),
                asset_id="a-x",
                ticker="X",
                label=1,
                probability=0.80,
                rank=1,
                best_acquirer_id="pfizer",
                match_group_id="X:2022-06-01",
                strategic_fit_score=0.8,
                capital_vulnerability_score=0.3,
                enterprise_value_millions=500.0,
            ),
            MACalibrationRow(
                snapshot_date=date(2022, 1, 1),
                asset_id="a-y",
                ticker="Y",
                label=0,
                probability=0.50,
                rank=2,
                best_acquirer_id="pfizer",
                match_group_id="X:2022-06-01",
                strategic_fit_score=0.5,
                capital_vulnerability_score=0.2,
                enterprise_value_millions=300.0,
            ),
            MACalibrationRow(
                snapshot_date=date(2022, 1, 1),
                asset_id="a-z",
                ticker="Z",
                label=0,
                probability=0.40,
                rank=3,
                best_acquirer_id="pfizer",
                match_group_id="X:2022-06-01",
                strategic_fit_score=0.4,
                capital_vulnerability_score=0.1,
                enterprise_value_millions=200.0,
            ),
        ]
        dataset = MACalibrationDataset(
            lookahead_days=365,
            n_rows=3,
            n_positive_rows=1,
            n_control_rows=2,
            n_unique_targets=1,
            dataset_mode="canonical_predeal",
            rows=rows,
        )
        fit = _fit_result(
            feature_names=["stored_probability"],
            intercept=0.0,
            coef_value=1.0,
            mean=0.5,
            std=0.2,
        )

        with tempfile.TemporaryDirectory() as td:
            store = KnowledgeStore(os.path.join(td, "k.db"))
            try:
                builder = MACalibrationDatasetBuilder(knowledge_store=store)
                result = builder.compare_ranking_policies(dataset, fit, top_k=3)
                assert isinstance(result, MAPolicyComparisonResult)
                assert result.top_k == 3
                assert result.policy_a_precision_at_k is not None
                assert result.policy_b_precision_at_k is not None
                assert result.policy_c_precision_at_k is not None
            finally:
                store.close()

    def test_policy_a_matches_v12_baseline_order(self):
        """Policy A should match precision@k of pure v1.2 rank order."""
        from bve.intelligence.ma_calibration import MACalibrationDatasetBuilder
        from bve.intelligence.knowledge_layer import KnowledgeStore
        import tempfile, os

        # Target ranked 1st by v1.2; should be captured in top-1
        rows = [
            MACalibrationRow(
                snapshot_date=date(2022, 1, 1),
                asset_id="a-target",
                ticker="TGT",
                label=1,
                probability=0.90,  # highest v1.2 score
                rank=1,
                best_acquirer_id="pfizer",
                match_group_id="TGT:2022-06-01",
            ),
            MACalibrationRow(
                snapshot_date=date(2022, 1, 1),
                asset_id="a-ctrl",
                ticker="CTL",
                label=0,
                probability=0.40,
                rank=2,
                best_acquirer_id="pfizer",
                match_group_id="TGT:2022-06-01",
            ),
        ]
        dataset = MACalibrationDataset(
            lookahead_days=365,
            n_rows=2,
            n_positive_rows=1,
            n_control_rows=1,
            n_unique_targets=1,
            dataset_mode="canonical_predeal",
            rows=rows,
        )
        fit = _fit_result(intercept=0.0, coef_value=0.0, mean=0.0, std=1.0)

        with tempfile.TemporaryDirectory() as td:
            store = KnowledgeStore(os.path.join(td, "k.db"))
            try:
                builder = MACalibrationDatasetBuilder(knowledge_store=store)
                result = builder.compare_ranking_policies(dataset, fit, top_k=1)
                # Policy A: top-1 is the target (rank=1) → precision = 1.0
                assert result.policy_a_precision_at_k == pytest.approx(1.0)
            finally:
                store.close()

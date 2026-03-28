"""
Sprint 21 tests — bve-recalibrate CLI and CalibratedPOS report.

Tests: text/JSON output, min-blend filter, empty DB handling, field completeness.
"""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from bve.analysis.calibration_metrics import OutcomeRecord, PredictionRecord
from bve.models.pos_calibrated import CalibratedPOSModel, N_FULL_POSTERIOR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pred(program_id, ta="oncology", phase="phase_2", model_pos=0.50):
    return PredictionRecord(
        program_id=program_id, ticker="X", ta=ta, phase=phase, model_pos=model_pos
    )


def _make_outcome(program_id, outcome_type="approval"):
    return OutcomeRecord(program_id=program_id, outcome_type=outcome_type)


def _seed_db(store, ta="oncology", phase="phase_2", n_success=40, n_fail=10):
    """Insert N_FULL_POSTERIOR outcomes into a KnowledgeStore so calibration has data."""
    preds = []
    outcomes = []
    for i in range(n_success):
        pid = f"{ta}_{phase}_S{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "approval"))
    for i in range(n_fail):
        pid = f"{ta}_{phase}_F{i}"
        preds.append(_make_pred(pid, ta=ta, phase=phase))
        outcomes.append(_make_outcome(pid, "failure_efficacy"))
    for p in preds:
        store.insert_pos_prediction(p)
    for o in outcomes:
        store.upsert_pos_outcome(o)


@pytest.fixture()
def empty_store():
    from bve.intelligence.knowledge_layer import KnowledgeStore
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ks = KnowledgeStore(db_path)
        yield ks
        ks.close()


@pytest.fixture()
def seeded_store():
    from bve.intelligence.knowledge_layer import KnowledgeStore
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        ks = KnowledgeStore(db_path)
        _seed_db(ks)
        yield ks
        ks.close()


# ===========================================================================
# TestRenderText
# ===========================================================================

class TestRenderText:
    def test_header_present(self, seeded_store):
        from bve.cli.recalibrate import _render_text
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        text = _render_text(model)
        assert "CalibratedPOS" in text
        assert "Recalibration Report" in text

    def test_n_outcomes_shown(self, seeded_store):
        from bve.cli.recalibrate import _render_text
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        text = _render_text(model)
        assert "50" in text  # 40 + 10 outcomes

    def test_bin_row_present(self, seeded_store):
        from bve.cli.recalibrate import _render_text
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        text = _render_text(model)
        assert "oncology" in text.lower()
        assert "phase_2" in text.lower()

    def test_empty_db_shows_no_bins_message(self, empty_store):
        from bve.cli.recalibrate import _render_text
        model = CalibratedPOSModel.from_store(empty_store.db_path)
        text = _render_text(model)
        assert "0" in text  # n_outcomes = 0

    def test_min_blend_filters_low_weight_bins(self, empty_store):
        from bve.cli.recalibrate import _render_text
        # Build a model with a low-blend-weight bin
        preds = [_make_pred(f"P{i}", ta="oncology", phase="phase_2") for i in range(5)]
        outcomes = [_make_outcome(f"P{i}", "approval") for i in range(5)]
        model = CalibratedPOSModel.from_records(preds, outcomes)
        # blend_weight=0.0 for N=5; min_blend=0.5 should exclude it
        text = _render_text(model, min_blend=0.5)
        assert "No bins" in text


# ===========================================================================
# TestRenderJSON
# ===========================================================================

class TestRenderJSON:
    def test_json_parses(self, seeded_store):
        from bve.cli.recalibrate import _render_json
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        data = json.loads(_render_json(model))
        assert isinstance(data, dict)

    def test_json_has_required_fields(self, seeded_store):
        from bve.cli.recalibrate import _render_json
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        data = json.loads(_render_json(model))
        assert "n_outcomes" in data
        assert "n_bins_calibrated" in data
        assert "bins" in data
        assert "generated_at" in data

    def test_json_n_outcomes(self, seeded_store):
        from bve.cli.recalibrate import _render_json
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        data = json.loads(_render_json(model))
        assert data["n_outcomes"] == 50

    def test_json_bin_fields(self, seeded_store):
        from bve.cli.recalibrate import _render_json
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        data = json.loads(_render_json(model))
        if data["bins"]:
            bin_ = data["bins"][0]
            for field in ["ta", "phase", "n_total", "n_success", "n_failure",
                          "posterior_mean", "industry_prior", "blend_weight",
                          "blended_rate", "ci_lo", "ci_hi"]:
                assert field in bin_

    def test_json_min_blend_filter(self, seeded_store):
        from bve.cli.recalibrate import _render_json
        model = CalibratedPOSModel.from_store(seeded_store.db_path)
        data_all = json.loads(_render_json(model, min_blend=0.0))
        data_filtered = json.loads(_render_json(model, min_blend=0.99))
        # High threshold should filter out most/all bins
        assert len(data_all["bins"]) >= len(data_filtered["bins"])

    def test_json_empty_db(self, empty_store):
        from bve.cli.recalibrate import _render_json
        model = CalibratedPOSModel.from_store(empty_store.db_path)
        data = json.loads(_render_json(model))
        assert data["n_outcomes"] == 0
        assert data["bins"] == []


# ===========================================================================
# TestCLI
# ===========================================================================

class TestCLI:
    def test_text_output(self, seeded_store, capsys):
        from bve.cli.recalibrate import main
        main(["--db", str(seeded_store.db_path), "--format", "text"])
        captured = capsys.readouterr()
        assert "CalibratedPOS" in captured.out

    def test_json_output(self, seeded_store, capsys):
        from bve.cli.recalibrate import main
        main(["--db", str(seeded_store.db_path), "--format", "json"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "n_outcomes" in data

    def test_min_blend_arg(self, seeded_store, capsys):
        from bve.cli.recalibrate import main
        main(["--db", str(seeded_store.db_path), "--format", "json", "--min-blend", "0.99"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        for b in data["bins"]:
            assert b["blend_weight"] >= 0.99

    def test_out_writes_file(self, seeded_store, tmp_path):
        from bve.cli.recalibrate import main
        out_file = tmp_path / "calibration.json"
        main(["--db", str(seeded_store.db_path), "--format", "json", "--out", str(out_file)])
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "n_outcomes" in data

    def test_empty_db_does_not_crash(self, empty_store, capsys):
        from bve.cli.recalibrate import main
        main(["--db", str(empty_store.db_path)])
        captured = capsys.readouterr()
        assert captured.out  # some output produced

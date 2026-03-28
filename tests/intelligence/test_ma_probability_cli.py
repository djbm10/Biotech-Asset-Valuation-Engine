from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from bve.cli.ma_probability import _format_report, main as ma_probability_main
from bve.intelligence.ma_probability import MAProbabilityResult, MAProbabilityRow


def _result() -> MAProbabilityResult:
    return MAProbabilityResult(
        scanned_at=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
        as_of_date=date(2026, 3, 24),
        score_version="v1.0",
        alert_threshold=0.70,
        n_assets=1,
        n_ranked=1,
        n_above_alert_threshold=1,
        alerts_emitted=[],
        alerts_suppressed_as_duplicate=0,
        snapshots_written=0,
        reference_snapshot_date=None,
        rows=[
            MAProbabilityRow(
                rank=1,
                asset_id="asset-cli",
                company_id="company-cli",
                ticker="CLI",
                stage="phase_3",
                acquisition_ready=True,
                enterprise_value_millions=500.0,
                acquisition_discount=1.8,
                p_acquisition=0.746,
                raw_probability=0.746,
                above_alert_threshold=True,
                score_version="v1.0",
                best_acquirer_id="regeneron",
                best_acquirer_name="Regeneron Pharmaceuticals",
                best_acquirer_fit_score=0.812,
                runner_up_acquirer_id="oncobuyer",
                valuation_discount_score=0.70,
                strategic_fit_score=0.82,
                de_risking_stage_score=1.0,
                vulnerability_score=0.61,
                cash_runway_quarters=3.0,
                cash_runway_pressure_score=0.85,
                cash_runway_risk_level="high",
                runway_gap_months=2.0,
                nearest_catalyst_date=date(2026, 5, 1),
                target_signal_score=0.55,
                external_deal_pressure_score=0.55,
                target_signal_ids=["asset-cli_board_change"],
                external_deal_signal_ids=["ophth_same_space_deal"],
                hard_fail_reasons=[],
                matched_therapeutic_gap="ophthalmology",
                matched_modality="fully_human_antibody",
                matched_priorities=["retina growth"],
                explanation="High strategic fit plus short runway before catalyst.",
                acquirer_candidates=[],
            )
        ],
    )


class _StubScanner:
    last_config = None
    last_call = None

    def __init__(self, *, knowledge_store=None, config=None, fit_engine=None, context_provider=None):
        type(self).last_config = config

    def scan_from_watchlist_config(
        self,
        watchlist_config,
        *,
        snapshot_date=None,
        top_n=None,
        run_id=None,
        scanned_at=None,
    ):
        type(self).last_call = {
            "snapshot_date": snapshot_date,
            "top_n": top_n,
            "run_id": run_id,
            "scanned_at": scanned_at,
            "n_watchlist": len(watchlist_config.watchlist),
        }
        return _result()


def test_format_report_surfaces_required_fields():
    output = _format_report(_result())

    assert "M&A probability scan date: 2026-03-24" in output
    assert "asset-cli" in output
    assert "regeneron" in output
    assert "signals=asset-cli_board_change,ophth_same_space_deal" in output
    assert "High strategic fit plus short runway before catalyst." in output


def test_ma_probability_cli_report_output(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_ma_probability.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge.db"),
                "watchlist": [{"company_id": "company-cli", "asset_id": "asset-cli", "ticker": "CLI"}],
            }
        ),
        encoding="utf-8",
    )
    _StubScanner.last_config = None
    _StubScanner.last_call = None

    monkeypatch.setattr("bve.cli.ma_probability.MAProbabilityScanner", _StubScanner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-ma-probability",
            "--watchlist",
            str(watchlist_path),
            "--output-format",
            "report",
        ],
    )

    ma_probability_main()
    out = capsys.readouterr().out

    assert "M&A probability scan date: 2026-03-24" in out
    assert "asset-cli" in out
    assert "regeneron" in out
    assert _StubScanner.last_config.persist_daily_snapshots is False
    assert _StubScanner.last_config.enable_monitor is False
    assert _StubScanner.last_call["top_n"] == 10


def test_ma_probability_cli_json_output_and_alert_flag(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_ma_probability_json.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge_json.db"),
                "watchlist": [{"company_id": "company-cli", "asset_id": "asset-cli", "ticker": "CLI"}],
            }
        ),
        encoding="utf-8",
    )
    _StubScanner.last_config = None
    _StubScanner.last_call = None

    monkeypatch.setattr("bve.cli.ma_probability.MAProbabilityScanner", _StubScanner)
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-ma-probability",
            "--watchlist",
            str(watchlist_path),
            "--as-of",
            "2026-03-24",
            "--top",
            "7",
            "--alert-threshold",
            "0.8",
            "--emit-alerts",
            "--readiness-filter",
            "off",
            "--output-format",
            "json",
        ],
    )

    ma_probability_main()
    out = capsys.readouterr().out

    assert '"asset_id": "asset-cli"' in out
    assert '"p_acquisition": 0.746' in out
    assert _StubScanner.last_config.alert_threshold == 0.8
    assert _StubScanner.last_config.top_n == 7
    assert _StubScanner.last_config.persist_daily_snapshots is True
    assert _StubScanner.last_config.enable_monitor is True
    assert _StubScanner.last_config.fit_integration_config.require_acquisition_readiness is False
    assert _StubScanner.last_call["snapshot_date"] == date(2026, 3, 24)
    assert _StubScanner.last_call["top_n"] == 7

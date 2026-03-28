from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from bve.cli.screen import _format_report, main as screen_main
from bve.intelligence.mispricing_screener import MispricingScreenResult, MispricingScreenRow


def _result() -> MispricingScreenResult:
    return MispricingScreenResult(
        screened_at=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
        as_of_date=date(2026, 3, 24),
        score_version="v1.0",
        score_weights={
            "ranking": 0.60,
            "acquisition": 0.25,
            "stage": 0.05,
            "pos_adjustment": 0.10,
        },
        n_assets=1,
        n_with_ranking=1,
        n_with_acquisition_discount=1,
        n_with_catalyst=1,
        rows=[
            MispricingScreenRow(
                rank=1,
                asset_id="asset-cli",
                company_id="company-cli",
                ticker="CLI",
                stage="phase_2",
                unified_score=0.812,
                score_version="v1.0",
                ranking_rank=1,
                ranking_score=0.71,
                acquisition_score=0.80,
                stage_score=0.55,
                pos_adjustment_score=0.68,
                ranking_component=0.426,
                acquisition_component=0.200,
                stage_component=0.0275,
                pos_adjustment_component=0.068,
                catalyst_modifier=1.05,
                rnpv_millions=220.0,
                market_cap_millions=120.0,
                enterprise_value_millions=105.0,
                acquisition_discount=2.10,
                acquisition_ready=True,
                acquisition_exclusion_reason=None,
                market_cap_source="knowledge_store_price",
                mispricing=0.8333,
                mispricing_pct=83.33,
                model_pos=0.55,
                implied_pos=0.30,
                pos_gap=-0.25,
                pos_adjustment_value=0.25,
                pos_adjustment_source="pos_gap",
                catalyst_type="trial_readout",
                catalyst_date=date(2026, 4, 4),
                catalyst_source="unit_test",
                catalyst_signal_strength=1.20,
                days_to_catalyst=11,
                data_notes=["missing_phase_update"],
                explanation="asset-cli explanation",
            )
        ],
    )


def test_format_report_surfaces_required_fields():
    output = _format_report(_result())

    assert "Unified mispricing screen date: 2026-03-24" in output
    assert "asset-cli" in output
    assert "trial_readout" in output
    assert "phase_2" in output
    assert "rNPV=220.0" in output
    assert "EV=105.0" in output


def test_screen_cli_report_output(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_screen.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge.db"),
                "watchlist": [{"company_id": "company-cli", "asset_id": "asset-cli", "ticker": "CLI"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bve.cli.screen.UnifiedMispricingScreener.screen_from_watchlist_config",
        lambda self, watchlist_config, screened_at=None: _result(),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-screen",
            "--watchlist",
            str(watchlist_path),
            "--output-format",
            "report",
        ],
    )

    screen_main()
    out = capsys.readouterr().out
    assert "Unified mispricing screen date: 2026-03-24" in out
    assert "asset-cli" in out
    assert "trial_readout" in out


def test_screen_cli_json_output(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_screen_json.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge_json.db"),
                "watchlist": [{"company_id": "company-cli", "asset_id": "asset-cli", "ticker": "CLI"}],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "bve.cli.screen.UnifiedMispricingScreener.screen_from_watchlist_config",
        lambda self, watchlist_config, screened_at=None: _result(),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-screen",
            "--watchlist",
            str(watchlist_path),
            "--output-format",
            "json",
        ],
    )

    screen_main()
    out = capsys.readouterr().out
    assert '"asset_id": "asset-cli"' in out
    assert '"unified_score": 0.812' in out

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml

from bve.cli.acquirer_fit import _format_report, main as acquirer_fit_main
from bve.intelligence.acquirer_fit import AcquirerFitResult, AcquirerFitRow


def _result() -> AcquirerFitResult:
    return AcquirerFitResult(
        scored_at=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
        as_of_date=date(2026, 3, 24),
        acquirer_id="regeneron",
        score_version="v1.0",
        n_assets=1,
        n_ranked=1,
        n_with_comps=1,
        n_passing_hard_filters=1,
        rows=[
            AcquirerFitRow(
                rank=1,
                acquirer_id="regeneron",
                asset_id="asset-cli",
                ticker="CLI",
                company_name="CliCo",
                score_version="v1.0",
                raw_fit_score=0.812,
                fit_score=0.812,
                passes_hard_filters=True,
                therapeutic_area_score=1.0,
                modality_score=0.85,
                stage_score=1.0,
                strategic_priority_score=0.65,
                valuation_score=0.85,
                budget_score=1.0,
                therapeutic_area_component=0.25,
                modality_component=0.17,
                stage_component=0.15,
                strategic_priority_component=0.0975,
                valuation_component=0.085,
                budget_component=0.15,
                hard_fail_reasons=[],
                matched_therapeutic_gap="ophthalmology",
                matched_modality="fully_human_antibody",
                matched_priorities=["retina growth", "late-stage external innovation"],
                valuation_source="comparable_deals",
                valuation_reference_median_ev_to_peak_sales=1.5,
                valuation_reference_band_low_millions=None,
                valuation_reference_band_high_millions=None,
                budget_capacity_millions=18000.0,
                budget_required_millions=600.0,
                budget_headroom_millions=17400.0,
                explanation="Strong TA and modality match with ample budget headroom.",
                company_id="company-cli",
                therapeutic_area="ophthalmology",
                indication="wet AMD",
                modality="fully_human_antibody",
                stage="phase_3",
                enterprise_value_millions=600.0,
                acquisition_discount=1.8,
                acquisition_ready=True,
                acquisition_readiness_bucket="phase_3_ready",
                ev_to_peak_sales=1.0,
                comparable_match_tier="exact",
                comparable_n=3,
                comparable_percentile_vs_peers=0.10,
                comparable_peer_median_ev_to_peak_sales=1.5,
            )
        ],
    )


def test_format_report_surfaces_required_fields():
    output = _format_report(_result())

    assert "Acquirer fit screen date: 2026-03-24" in output
    assert "Acquirer: regeneron" in output
    assert "asset-cli" in output
    assert "ophthalmology" in output
    assert "fully_human_antibody" in output


def test_acquirer_fit_cli_report_output(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_acquirer_fit.yaml"
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
        "bve.cli.acquirer_fit.AcquirerFitEngine.screen_from_watchlist_config",
        lambda self, watchlist_config, acquirer_id, snapshot_date=None, top_n=None: _result(),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-acquirer-fit",
            "--watchlist",
            str(watchlist_path),
            "--acquirer",
            "regeneron",
            "--output-format",
            "report",
        ],
    )

    acquirer_fit_main()
    out = capsys.readouterr().out
    assert "Acquirer fit screen date: 2026-03-24" in out
    assert "asset-cli" in out
    assert "pass" in out


def test_acquirer_fit_cli_json_output(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_acquirer_fit_json.yaml"
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
        "bve.cli.acquirer_fit.AcquirerFitEngine.screen_from_watchlist_config",
        lambda self, watchlist_config, acquirer_id, snapshot_date=None, top_n=None: _result(),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-acquirer-fit",
            "--watchlist",
            str(watchlist_path),
            "--acquirer",
            "regeneron",
            "--output-format",
            "json",
        ],
    )

    acquirer_fit_main()
    out = capsys.readouterr().out
    assert '"asset_id": "asset-cli"' in out
    assert '"fit_score": 0.812' in out


def test_acquirer_fit_cli_writes_memos(tmp_path: Path, monkeypatch, capsys):
    watchlist_path = tmp_path / "watchlist_acquirer_fit_memos.yaml"
    watchlist_path.write_text(
        yaml.safe_dump(
            {
                "knowledge_db_path": str(tmp_path / "knowledge_memos.db"),
                "watchlist": [{"company_id": "company-cli", "asset_id": "asset-cli", "ticker": "CLI"}],
            }
        ),
        encoding="utf-8",
    )
    memo_dir = tmp_path / "memos"
    persist_calls: list[bool] = []

    monkeypatch.setattr(
        "bve.cli.acquirer_fit.AcquirerFitEngine.screen_from_watchlist_config",
        lambda self, watchlist_config, acquirer_id, snapshot_date=None, top_n=None: _result(),
    )

    def _fake_generate(self, watchlist, *, fit_result, persist=False):
        persist_calls.append(persist)
        return [
            SimpleNamespace(
                asset_id="asset-cli",
                acquirer_id="regeneron",
                rendered_markdown="# Acquisition Memo\n\nCLI test memo",
            )
        ]

    monkeypatch.setattr(
        "bve.cli.acquirer_fit.AcquisitionMemoGenerator.generate_from_fit_result",
        _fake_generate,
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-acquirer-fit",
            "--watchlist",
            str(watchlist_path),
            "--acquirer",
            "regeneron",
            "--write-memos",
            "--persist-memos",
            "--memo-dir",
            str(memo_dir),
        ],
    )

    acquirer_fit_main()
    captured = capsys.readouterr()
    memo_files = list(memo_dir.glob("*.md"))

    assert persist_calls == [True]
    assert len(memo_files) == 1
    assert "CLI test memo" in memo_files[0].read_text(encoding="utf-8")
    assert "Acquisition memos written: 1" in captured.err


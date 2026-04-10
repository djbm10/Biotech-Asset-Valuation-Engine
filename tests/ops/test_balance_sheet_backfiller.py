from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from bve.ops.balance_sheet_backfiller import BalanceSheetBackfiller
from bve.ops.historical_replay import ReplayStore
from bve.ops.signal_backfiller import SignalBackfiller


def _write_watchlist(path: Path, entries: list[dict[str, str]]) -> Path:
    path.write_text(yaml.safe_dump({"watchlist": entries}, sort_keys=False), encoding="utf-8")
    return path


def test_signal_backfiller_writes_capital_snapshots_for_all_assets_same_ticker(
    tmp_path: Path,
    monkeypatch,
) -> None:
    replay = ReplayStore(str(tmp_path / "replay.sqlite"))
    try:
        monkeypatch.setattr("bve.ingestion.sec_edgar.get_cik", lambda ticker: "0000123456")
        monkeypatch.setattr(
            "bve.ingestion.sec_edgar.get_company_facts",
            lambda cik: {
                "us-gaap": {
                    "CashAndCashEquivalentsAtCarryingValue": {
                        "units": {
                            "USD": [
                                {
                                    "form": "10-Q",
                                    "filed": "2025-05-10",
                                    "end": "2025-03-31",
                                    "val": 420_000_000,
                                }
                            ]
                        }
                    },
                    "ResearchAndDevelopmentExpense": {
                        "units": {
                            "USD": [
                                {
                                    "form": "10-K",
                                    "filed": "2025-02-20",
                                    "end": "2024-12-31",
                                    "val": 120_000_000,
                                }
                            ]
                        }
                    },
                },
                "dei": {
                    "EntityCommonStockSharesOutstanding": {
                        "units": {
                            "shares": [
                                {
                                    "form": "10-Q",
                                    "filed": "2025-05-10",
                                    "end": "2025-03-31",
                                    "val": 105_000_000,
                                }
                            ]
                        }
                    }
                },
            },
        )

        n = SignalBackfiller(replay).backfill_capital_risk(
            [
                {"ticker": "TEST", "asset_id": "asset-1"},
                {"ticker": "TEST", "asset_id": "asset-2"},
            ]
        )
        assert n == 2
        count = replay._conn.execute(
            "SELECT COUNT(*) FROM capital_snapshots WHERE snapshot_date = '2025-05-10'"
        ).fetchone()[0]
        assert count == 2
        bs_count = replay._conn.execute(
            "SELECT COUNT(*) FROM balance_sheet_snapshots WHERE ticker = 'TEST'"
        ).fetchone()[0]
        assert bs_count == 1
    finally:
        replay.close()


def test_balance_sheet_backfiller_writes_coverage_csv(tmp_path: Path, monkeypatch) -> None:
    replay_path = tmp_path / "replay.sqlite"
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "TEST",
            },
            {
                "company_id": "co-test",
                "asset_id": "asset-2",
                "ticker": "TEST",
            },
            {
                "company_id": "co-othr",
                "asset_id": "asset-3",
                "ticker": "OTHR",
            },
        ],
    )

    monkeypatch.setattr("bve.ingestion.sec_edgar.get_cik", lambda ticker: f"0000{ticker}")

    def _facts(cik: str):
        return {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-Q",
                                "filed": "2025-05-10",
                                "end": "2025-03-31",
                                "val": 300_000_000 if cik.endswith("TEST") else 150_000_000,
                            }
                        ]
                    }
                },
                "ResearchAndDevelopmentExpense": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-K",
                                "filed": "2025-02-20",
                                "end": "2024-12-31",
                                "val": 120_000_000,
                            }
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "form": "10-Q",
                                "filed": "2025-05-10",
                                "end": "2025-03-31",
                                "val": 90_000_000,
                            }
                        ]
                    }
                }
            },
        }

    monkeypatch.setattr("bve.ingestion.sec_edgar.get_company_facts", _facts)

    summary = BalanceSheetBackfiller(
        replay_db_path=replay_path,
        output_dir=tmp_path / "analysis",
        reporter=None,
    ).backfill_watchlist(watchlist_path)

    assert summary.n_watchlist_assets == 3
    assert summary.n_unique_tickers == 2
    assert summary.n_capital_rows_inserted == 3
    assert summary.n_tickers_with_balance_sheet == 2
    assert summary.n_balance_sheet_rows_added == 2
    assert summary.coverage_csv_path.exists()
    by_ticker = {row.ticker: row for row in summary.coverage_rows}
    assert by_ticker["TEST"].asset_ids == ("asset-1", "asset-2")
    assert by_ticker["TEST"].snapshot_count == 1
    assert by_ticker["TEST"].latest_snapshot_date == date(2025, 5, 10)


def test_balance_sheet_backfiller_uses_company_name_hint_and_cash_fallback_concept(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "asset.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "asset": {"id": "asset-1", "name": "Asset One"},
                "company": {
                    "id": "co-test",
                    "name": "Avidity Biosciences",
                    "ticker": "RNA",
                    "cash_millions": 100.0,
                    "shares_outstanding_millions": 20.0,
                    "burn_rate_millions_per_quarter": 10.0,
                    "current_price": 10.0,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    watchlist_path = _write_watchlist(
        tmp_path / "watchlist.yaml",
        [
            {
                "company_id": "co-test",
                "asset_id": "asset-1",
                "ticker": "RNA",
                "valuation_config": str(config_path),
            }
        ],
    )

    captured: dict[str, str | None] = {}

    def fake_get_cik(ticker: str, company_name: str | None = None) -> str:
        captured["ticker"] = ticker
        captured["company_name"] = company_name
        return "0000123456"

    monkeypatch.setattr("bve.ingestion.sec_edgar.get_cik", fake_get_cik)
    monkeypatch.setattr(
        "bve.ingestion.sec_edgar.get_company_facts",
        lambda cik: {
            "us-gaap": {
                "Cash": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-Q",
                                "filed": "2025-05-10",
                                "end": "2025-03-31",
                                "val": 250_000_000,
                            }
                        ]
                    }
                },
                "ResearchAndDevelopmentExpense": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-K",
                                "filed": "2025-02-20",
                                "end": "2024-12-31",
                                "val": 120_000_000,
                            }
                        ]
                    }
                },
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "form": "10-Q",
                                "filed": "2025-05-10",
                                "end": "2025-03-31",
                                "val": 50_000_000,
                            }
                        ]
                    }
                }
            },
        },
    )

    summary = BalanceSheetBackfiller(
        replay_db_path=tmp_path / "replay.sqlite",
        output_dir=tmp_path / "analysis",
        reporter=None,
    ).backfill_watchlist(watchlist_path)

    assert captured == {"ticker": "RNA", "company_name": "Avidity Biosciences"}
    assert summary.n_tickers_with_balance_sheet == 1
    assert summary.coverage_rows[0].snapshot_count == 1

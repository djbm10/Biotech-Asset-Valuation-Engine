from __future__ import annotations

from bve.cli.generate_config import _build_parser as build_generate_parser
from bve.cli.replay_documents import _build_parser as build_replay_documents_parser
from bve.cli.service_control import _build_parser as build_service_parser
from bve.cli.watchlist_run import _build_parser as build_watchlist_parser


def test_watchlist_run_accepts_watchlist_dir_flag() -> None:
    parser = build_watchlist_parser()
    args = parser.parse_args(["--watchlist-dir", "examples/configs/watchlists"])
    assert args.watchlist_dir == "examples/configs/watchlists"
    assert args.watchlist is None


def test_watchlist_run_accepts_positional_watchlist_path() -> None:
    parser = build_watchlist_parser()
    args = parser.parse_args(["examples/configs/watchlists/watchlist_stage1.yaml"])
    assert args.watchlist_path == "examples/configs/watchlists/watchlist_stage1.yaml"
    assert args.watchlist is None
    assert args.watchlist_dir is None


def test_watchlist_run_accepts_reprocess_documents_flag() -> None:
    parser = build_watchlist_parser()
    args = parser.parse_args(
        [
            "--watchlist",
            "examples/configs/watchlists/watchlist_stage1.yaml",
            "--reprocess-documents",
            "--since",
            "7d",
        ]
    )
    assert args.reprocess_documents is True
    assert args.since == "7d"


def test_service_control_start_accepts_watchlist_dir_flag() -> None:
    parser = build_service_parser()
    args = parser.parse_args(["start", "--watchlist-dir", "examples/configs/watchlists"])
    assert args.command == "start"
    assert args.watchlist_dir == "examples/configs/watchlists"
    assert args.watchlist is None


def test_service_control_replay_accepts_watchlist_dir_flag() -> None:
    parser = build_service_parser()
    args = parser.parse_args(
        [
            "replay-run",
            "--watchlist-dir",
            "examples/configs/watchlists",
            "--run-id",
            "run-123",
        ]
    )
    assert args.command == "replay-run"
    assert args.watchlist_dir == "examples/configs/watchlists"


def test_generate_config_accepts_asset_alias() -> None:
    parser = build_generate_parser()
    args = parser.parse_args(["--asset", "VRTX"])
    assert args.asset == "VRTX"
    assert args.ticker is None


def test_replay_documents_accepts_since_without_watchlist() -> None:
    parser = build_replay_documents_parser()
    args = parser.parse_args(["--since", "7d"])
    assert args.since == "7d"
    assert args.watchlist is None

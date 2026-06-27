import pytest

from bve.cli.watchlist_run import _load_selected_buyer_problem


def test_watchlist_load_selected_buyer_problem_by_id() -> None:
    problem = _load_selected_buyer_problem(
        "examples/configs/buyer_problems/vertex.yaml",
        "autoimmune_b_cell_depth",
    )
    assert problem.problem_id == "autoimmune_b_cell_depth"
    assert problem.buyer_id == "vertex"


def test_watchlist_buyer_problem_id_without_buyer_problem_fails(monkeypatch) -> None:
    from bve.cli import watchlist_run

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-watchlist-run",
            "--watchlist",
            "examples/configs/watchlists/watchlist_stage1.yaml",
            "--buyer-problem-id",
            "autoimmune_b_cell_depth",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        watchlist_run.main()
    assert "--buyer-problem-id requires --buyer-problem" in str(exc.value)


def test_watchlist_buyer_problem_requires_science_thesis(monkeypatch) -> None:
    from bve.cli import watchlist_run

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-watchlist-run",
            "--watchlist",
            "examples/configs/watchlists/watchlist_stage1.yaml",
            "--buyer-problem",
            "examples/configs/buyer_problems/vertex.yaml",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        watchlist_run.main()
    assert "--buyer-problem requires --science-thesis" in str(exc.value)

import pytest

from bve.cli.run_asset import _load_selected_buyer_problem


def test_load_selected_buyer_problem_by_id() -> None:
    problem = _load_selected_buyer_problem(
        "examples/configs/buyer_problems/vertex.yaml",
        "autoimmune_b_cell_depth",
    )

    assert problem.problem_id == "autoimmune_b_cell_depth"
    assert problem.buyer_id == "vertex"


def test_load_selected_buyer_problem_unknown_id_fails() -> None:
    with pytest.raises(SystemExit) as exc:
        _load_selected_buyer_problem(
            "examples/configs/buyer_problems/vertex.yaml",
            "missing_problem",
        )

    assert exc.value.code == 2


def test_buyer_problem_id_without_buyer_problem_fails(monkeypatch, tmp_path) -> None:
    from bve.cli import run_asset

    monkeypatch.setattr(
        "sys.argv",
        [
            "bve-asset",
            "--config",
            "examples/configs/relay_rly2608.yaml",
            "--buyer-problem-id",
            "autoimmune_b_cell_depth",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        run_asset.main()

    assert exc.value.code == 2

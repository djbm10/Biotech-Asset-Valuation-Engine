"""Asking the engine a question instead of authoring a YAML (productization step 1).

The natural-language intake --- parse, resolve against the ontology snapshot, compile to a
BuyerProblem v2 --- has existed since M9 and nothing outside ``bve.se.intent`` imported it.
The only way into the engine was a hand-authored problem file, which means hand-typing a
target's aliases: the one input the snapshot knows better than the operator does.

These tests pin the entry point and, more importantly, pin what it refuses to do. A question
that does not resolve must not run: filling in a plausible target to make the pipeline
produce something is how a landscape ends up being about the wrong gene.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bve.cli.se_search import build_parser, problem_from_args
from bve.se.schemas.contracts import BuyerProblemV2


def _args(argv: list[str]):
    return build_parser().parse_args(argv)


class TestAQuestionIsAValidEntryPoint:
    def test_a_resolvable_question_compiles_to_a_problem(self) -> None:
        problem = problem_from_args(
            _args(["--query", "small molecule CHRM1 programs", "--as-of", "2026-09-16"])
        )
        assert isinstance(problem, BuyerProblemV2)
        symbols = [
            term.canonical_id
            for term in problem.strategic_gap.target_expression.targets
        ]
        assert symbols == ["CHRM1"]
        assert problem.strategic_gap.modalities == ["SMALL_MOLECULE"]

    def test_aliases_come_from_the_snapshot_not_the_operator(self) -> None:
        problem = problem_from_args(
            _args(["--query", "small molecule CHRM1 programs", "--as-of", "2026-09-16"])
        )
        aliases = problem.strategic_gap.target_expression.targets[0].aliases
        assert "HM1" in aliases

    def test_the_question_is_still_reproducible_as_a_file(self, tmp_path) -> None:
        emitted = tmp_path / "problem.yaml"
        problem = problem_from_args(
            _args(
                [
                    "--query",
                    "small molecule CHRM1 programs",
                    "--as-of",
                    "2026-09-16",
                    "--emit-problem",
                    str(emitted),
                ]
            )
        )
        # A typed question is an input like any other. Writing it back out is what keeps a
        # result explainable after the fact and lets the same run be replayed from a file.
        restored = BuyerProblemV2.model_validate(yaml.safe_load(emitted.read_text()))
        assert restored == problem

    def test_a_problem_file_still_works_unchanged(self) -> None:
        path = (
            Path(__file__).resolve().parents[2]
            / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml"
        )
        problem = problem_from_args(_args(["--problem", str(path)]))
        assert problem.problem_id == "benchmark_cd19_or_bcma_tce"


class TestAQuestionThatDoesNotResolveDoesNotRun:
    def test_an_ambiguous_target_is_refused_with_its_claimants(self, capsys) -> None:
        with pytest.raises(SystemExit):
            problem_from_args(
                _args(["--query", "small molecule PD-1 programs", "--as-of", "2026-09-16"])
            )
        message = capsys.readouterr().err
        assert "PD-1" in message
        # The operator has to be able to argue with the interpretation, so the claimants
        # are named rather than summarized as "ambiguous".
        assert "PDCD1" in message and "RPL17" in message

    def test_an_underdetermined_question_names_its_blockers(self, capsys) -> None:
        with pytest.raises(SystemExit):
            problem_from_args(_args(["--query", "CHRM1 antagonists", "--as-of", "2026-09-16"]))
        assert "modality" in capsys.readouterr().err

    def test_a_query_and_a_problem_file_are_mutually_exclusive(self) -> None:
        with pytest.raises(SystemExit):
            _args(["--query", "small molecule CHRM1 programs", "--problem", "x.yaml"])

    def test_one_of_them_is_required(self) -> None:
        with pytest.raises(SystemExit):
            _args([])


class TestTheInterpretationIsShown:
    def test_how_the_question_was_read_is_reported(self, capsys) -> None:
        problem_from_args(
            _args(["--query", "small molecule CHRM1 programs", "--as-of", "2026-09-16"])
        )
        message = capsys.readouterr().err
        # Per-span, with the rule that fired: an interpretation the operator cannot see is
        # an interpretation they cannot correct.
        assert "CHRM1" in message
        assert "SMALL_MOLECULE" in message

"""The whole run, not just discovery, must be reproducible from its declared inputs.

`test_trial_universe_wiring.py` pins the adapter: same universe in, same hits out. That
is the cheaper half. The claim that matters downstream is about the *partitions* —
eligible / excluded / unresolved / review — because those are what a benchmark scores and
what an analyst acts on. Registry identity assignment, gate evaluation and review routing
all sit between the hits and those lists, and any ordering or identity instability in that
middle would move a recall number without moving a single input.

So this binds all four declared inputs (buyer problem, ontology snapshot, trial universe,
extractor version) and asserts the partitions are byte-identical across two runs.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from bve.se.discovery.adapters import CTGOV_EXTRACTOR, ClinicalTrialsGovAdapter
from bve.se.pipeline import SESearchResult, run_landscape_search
from bve.se.schemas.contracts import BuyerProblemV2
from bve.se.universe.ctgov import ClinicalTrialsGovProvider

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 7, 12)


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )


def _protocol(nct_id: str, name: str, description: str) -> dict:
    return {
        "identificationModule": {"nctId": nct_id, "briefTitle": f"{name} study"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-05-01"}},
        "armsInterventionsModule": {
            "interventions": [{"name": name, "description": description}]
        },
    }


#: A universe wide enough that ordering instability could show: two targets, and one
#: record that is deliberately thin so it can land outside the eligible set.
UNIVERSE = [
    _protocol("NCT00000001", "CLN-978", "CD19-directed CD3 bispecific T-cell engager"),
    _protocol("NCT00000002", "Teclistamab", "BCMA-directed CD3 bispecific T-cell engager"),
    _protocol("NCT00000003", "Compound X", "investigational agent, mechanism undisclosed"),
]


def _run(run_id: str) -> tuple[SESearchResult, ClinicalTrialsGovAdapter]:
    # Acquisition goes through the provider so the universe is a declared, hashable input
    # rather than an anonymous callable the manifest cannot describe.
    adapter = ClinicalTrialsGovAdapter(
        provider=ClinicalTrialsGovProvider(search_fn=lambda **_: list(UNIVERSE))
    )
    result = run_landscape_search(
        _problem(),
        [adapter],
        run_id=run_id,
        code_version="test",
        normalization_version="test",
    )
    return result, adapter


def _partitions(result: SESearchResult) -> dict[str, list]:
    """Everything a benchmark or an analyst reads, with wall-clock fields left out."""

    return {
        "eligible": sorted(result.eligible_asset_ids),
        "excluded": sorted(result.excluded_asset_ids),
        "unresolved": sorted(result.unresolved_asset_ids),
        "review": sorted(
            (item.review_id, item.subject_id, item.gate_id or "") for item in result.review_queue
        ),
        "candidates": sorted(asset.canonical_name for asset in result.candidates),
        "gates": sorted(
            (
                evaluation.subject_id,
                evaluation.disposition.value,
                tuple(
                    (decision.gate_id, decision.requirement_id, decision.status.value)
                    for decision in evaluation.decisions
                ),
            )
            for evaluation in result.gate_evaluations
        ),
        "ranking": [
            (entry.asset_id, entry.rank, entry.tier.value) for entry in result.ranking.ranked
        ],
        "errors": sorted(result.processing_errors),
    }


@pytest.fixture
def two_runs(se_ontology_snapshot):
    return _run("run:determinism:a"), _run("run:determinism:b")


class TestFullOrchestratorDeterminism:
    def test_partitions_are_identical_across_runs(self, two_runs) -> None:
        (first, _), (second, _) = two_runs
        assert _partitions(first) == _partitions(second)

    def test_the_partitions_are_not_all_empty(self, two_runs) -> None:
        """Guard the guard: two empty runs would compare equal and prove nothing."""

        (first, _), _ = two_runs
        assert first.candidates
        assert first.eligible_asset_ids or first.excluded_asset_ids or first.review_queue

    def test_runs_agree_on_the_declared_inputs(self, two_runs) -> None:
        """Equal outputs only mean something if the four inputs were in fact the same."""

        (first, first_adapter), (second, second_adapter) = two_runs

        # Ontology snapshot: pinned, and pinned to the same thing.
        assert first.run_manifest.ontology_version == second.run_manifest.ontology_version
        assert not first.run_manifest.ontology_version.startswith("no_snapshot")
        # Trial universe: one universe, identified by content rather than by wall clock.
        assert (
            first_adapter.trial_universe.provenance_hash
            == second_adapter.trial_universe.provenance_hash
        )
        # Extractor: the parser that read the payloads is named and stable.
        assert first_adapter.trial_universe.extractor == CTGOV_EXTRACTOR
        # Buyer problem: same problem at the same version.
        assert (first.run_manifest.problem_id, first.run_manifest.problem_version) == (
            second.run_manifest.problem_id,
            second.run_manifest.problem_version,
        )

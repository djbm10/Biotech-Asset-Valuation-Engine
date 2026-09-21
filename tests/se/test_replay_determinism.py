"""The same sealed input must give the same scientific answer, in any process.

`test_orchestrator_determinism.py` already pins the run's *partitions* across two calls in
one process. That is necessary and it is not enough, for two reasons this milestone found
the hard way.

First, it compares partitions, not facts. A run can put an asset in the same bucket for a
different reason, and it is the reason a delta attributes. The conference human-PoC delta
moved `identity.distinct_asset` by +4 and `minimum_stage` by +1 between two runs that
differed only by a flag that cannot reach either gate -- and every partition-level test in
the suite stayed green while it happened.

Second, and this is the mechanism the older test cannot see: **two calls in one process
share a hash seed.** Python randomises string hashing per interpreter, so any place the
pipeline iterates a set of names and then truncates, tie-breaks, or takes the first match
will agree with itself all day and disagree with tomorrow's run. A same-process comparison
is structurally blind to exactly the defect that invalidated the delta.

So this module asserts the stronger property: the scientific state -- canonical identities,
gate decisions, target assertions, human-PoC facts, minimum-stage facts and the reviewed
asset set -- is identical across processes started with *different* hash seeds. Run
identifiers and wall-clock fields are excluded, because those are metadata and are supposed
to differ; nothing else is.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
import yaml

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter, IndexedDocumentAdapter
from bve.se.pipeline import SESearchResult, run_landscape_search
from bve.se.schemas.contracts import BuyerProblemV2
from bve.se.universe.ctgov import ClinicalTrialsGovProvider

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 7, 12)
PROBLEM = ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml"


def _protocol(nct_id: str, name: str, description: str, phase: str = "PHASE2") -> dict:
    return {
        "identificationModule": {"nctId": nct_id, "briefTitle": f"{name} study"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {
            "lastUpdatePostDateStruct": {"date": "2026-05-01"},
            "overallStatus": "RECRUITING",
        },
        "designModule": {"phases": [phase]},
        "armsInterventionsModule": {
            "interventions": [{"name": name, "description": description}]
        },
    }


#: Wide enough that ordering instability has somewhere to show. Several assets share a
#: target, several share a sponsor, and the names are deliberately of mixed shape -- a
#: code, an INN, and a near-miss -- because the identity layer's tie-breaks are what a
#: hash-order defect would move.
UNIVERSE = [
    _protocol("NCT00000001", "CLN-978", "CD19-directed CD3 bispecific T-cell engager", "PHASE1"),
    _protocol("NCT00000002", "Teclistamab", "BCMA-directed CD3 bispecific T-cell engager"),
    _protocol("NCT00000003", "Elranatamab", "BCMA-directed CD3 bispecific T-cell engager"),
    _protocol("NCT00000004", "Blinatumomab", "CD19-directed CD3 bispecific T-cell engager", "PHASE3"),
    _protocol("NCT00000005", "Compound X", "investigational agent, mechanism undisclosed"),
    _protocol("NCT00000006", "ABBV-383", "BCMA CD3 bispecific antibody", "PHASE3"),
]

#: A second source family, because a single-source run cannot expose an ordering defect in
#: how families are merged -- and family merge order is on the list of suspects.
DOCUMENTS = [
    {
        "document_id": "doc:pr:1",
        "title": "Example Bio reports data for CLN-978",
        "text": (
            "Of 26 evaluable patients treated with CLN-978, 18 of 26 achieved a complete "
            "response. CLN-978 is a CD19-directed T-cell engager in Phase 1."
        ),
        "url": "https://example-bio.test/1",
        "publication_date": "2026-04-01",
    },
    {
        "document_id": "doc:pr:2",
        "title": "Teclistamab and elranatamab in relapsed myeloma",
        "text": (
            "Teclistamab is a BCMA-directed CD3 bispecific antibody. In 40 patients, 24 of "
            "40 achieved a partial response. Elranatamab is under study in Phase 2."
        ),
        "url": "https://example-bio.test/2",
        "publication_date": "2026-04-02",
    },
]


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(yaml.safe_load(PROBLEM.read_text()))


def _run(run_id: str, snapshot_root: Path) -> SESearchResult:
    # Snapshots are not optional scaffolding here. Evidence extraction reads the saved
    # payload, not the in-memory hit, so an adapter with nowhere to write produces a run
    # with candidates and no facts -- which would compare equal across seeds while
    # asserting nothing about the fact families this module exists to watch.
    return run_landscape_search(
        _problem(),
        [
            ClinicalTrialsGovAdapter(
                provider=ClinicalTrialsGovProvider(search_fn=lambda **_: list(UNIVERSE)),
                snapshot_root=snapshot_root / "clinicaltrials_gov",
            ),
            IndexedDocumentAdapter(
                "company_press_release",
                list(DOCUMENTS),
                snapshot_root=snapshot_root / "company_press_release",
            ),
        ],
        run_id=run_id,
        code_version="test",
        normalization_version="test",
    )


#: The fact types behind each gate, named rather than prefix-matched. A prefix looked
#: tidier and was wrong twice over: "target" matches neither ``construct_target_set`` nor
#: ``document_target_context``, and "development_stage" silently missed
#: ``development_status``. Both mistakes produce an empty family that compares equal
#: forever, which is the failure mode this module is least able to notice about itself.
TARGET_FACTS = ("construct_target_set", "document_target_context")
HUMAN_POC_FACTS = ("human_poc_present",)
MINIMUM_STAGE_FACTS = ("development_stage_order", "development_status")


def _facts_of_type(
    result: SESearchResult, types: tuple[str, ...]
) -> list[tuple[str, str, str]]:
    return sorted(
        (fact.subject_id, fact.fact_type, json.dumps(fact.value, sort_keys=True, default=str))
        for fact in result.facts
        if fact.fact_type in types
    )


def scientific_state(result: SESearchResult) -> dict[str, object]:
    """Everything the run asserts about the world, and nothing about the run itself.

    Deliberately keyed by *content* rather than by generated identifier. Fact ids and
    claim ids embed a hash of their own provenance, so comparing them would pass whenever
    the inputs matched even if the conclusions did not -- and would fail on a pure id
    change that altered nothing scientific. The subject, the type and the value are the
    claim; the rest is bookkeeping.
    """

    return {
        # Canonical identities: what the run decided the molecules are called, and which
        # names it merged into one.
        "identities": sorted(
            (asset.canonical_name, tuple(sorted(asset.aliases))) for asset in result.candidates
        ),
        "merges": sorted(
            (merge.surviving_asset_id, merge.merged_asset_id) for merge in result.identity_merges
        ),
        # Gate decisions, at requirement granularity: the bucket *and* the reason.
        "gates": sorted(
            (
                evaluation.subject_id,
                evaluation.disposition.value,
                tuple(
                    sorted(
                        (decision.gate_id, decision.requirement_id, decision.status.value)
                        for decision in evaluation.decisions
                    )
                ),
            )
            for evaluation in result.gate_evaluations
        ),
        # The three fact families this milestone watched move.
        "target_facts": _facts_of_type(result, TARGET_FACTS),
        "human_poc_facts": _facts_of_type(result, HUMAN_POC_FACTS),
        "minimum_stage_facts": _facts_of_type(result, MINIMUM_STAGE_FACTS),
        # The population an analyst actually reads.
        "shortlist": sorted(result.eligible_asset_ids),
        "review": sorted(result.excluded_asset_ids + result.unresolved_asset_ids),
        "errors": sorted(result.processing_errors),
    }


# --------------------------------------------------------------------------------------
# In-process: the cheap half, kept because it localises a failure to the pipeline rather
# than to the harness.
# --------------------------------------------------------------------------------------


@pytest.fixture
def two_runs(se_ontology_snapshot, tmp_path):
    # Separate snapshot roots, so the second run cannot read the first one's artefacts and
    # agree with it for that reason.
    return (
        _run("run:determinism:a", tmp_path / "a"),
        _run("run:determinism:b", tmp_path / "b"),
    )


class TestTheSameInputGivesTheSameAnswerInOneProcess:
    def test_the_scientific_state_is_identical(self, two_runs) -> None:
        first, second = two_runs
        assert scientific_state(first) == scientific_state(second)

    def test_the_state_is_not_vacuously_empty(self, two_runs) -> None:
        # Guard the guard. Two empty runs compare equal and prove nothing, and this whole
        # module would then be a test that the pipeline can fail identically twice.
        first, _ = two_runs
        state = scientific_state(first)
        assert state["identities"]
        assert state["gates"]
        assert state["shortlist"] or state["review"]
        # Each fact family separately, because an empty one compares equal across every
        # seed and would let this module report determinism it never tested. These are the
        # three the conference milestone watched move.
        assert state["target_facts"]
        assert state["human_poc_facts"]
        assert state["minimum_stage_facts"]

    def test_the_run_identifier_is_the_thing_that_differs(self, two_runs) -> None:
        # If the two runs were accidentally given the same id, the comparison above would
        # hold for an uninteresting reason.
        first, second = two_runs
        assert first.run_manifest.run_id != second.run_manifest.run_id


# --------------------------------------------------------------------------------------
# Cross-process: the half that can actually see hash-order instability.
# --------------------------------------------------------------------------------------

_DRIVER = """
import hashlib, json, sys, tempfile, pathlib
sys.path.insert(0, {tests!r})
sys.path.insert(0, {src!r})
from test_replay_determinism import _run, scientific_state
root = pathlib.Path(tempfile.mkdtemp())
state = scientific_state(_run("run:determinism:subprocess", root))
sys.stdout.write(hashlib.sha256(
    json.dumps(state, sort_keys=True, default=str).encode()
).hexdigest())
"""


def _digest_under_seed(seed: str) -> str:
    # The snapshot path comes from the environment the fixture installed, not from the
    # fixture's return value: the child needs the artifact on disk, and the object the
    # fixture yields is the in-memory one.
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = seed
    env["PYTHONPATH"] = str(ROOT / "src")
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _DRIVER.format(tests=str(Path(__file__).parent), src=str(ROOT / "src")),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    return proc.stdout.strip()


class TestTheSameInputGivesTheSameAnswerUnderADifferentHashSeed:
    """The property a same-process test cannot assert.

    String hashing is randomised per interpreter. Anywhere the pipeline iterates a set of
    names and then truncates, tie-breaks or takes the first match, the answer is a function
    of the seed -- and every run inside one pytest process shares one. Two seeds is the
    minimum that can tell a stable pipeline from a pipeline that merely agrees with itself.
    """

    def test_two_hash_seeds_produce_the_same_scientific_state(
        self, se_ontology_snapshot
    ) -> None:
        assert _digest_under_seed("0") == _digest_under_seed("1")

    def test_the_seed_is_actually_being_varied(self) -> None:
        # Guards the harness rather than the pipeline: if PYTHONHASHSEED were not reaching
        # the child, the test above would compare two identical configurations and pass
        # for no reason at all.
        script = "import sys; sys.stdout.write(str(hash('CLN-978')))"
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")

        def _hash(seed: str) -> str:
            return subprocess.run(
                [sys.executable, "-c", script],
                env={**env, "PYTHONHASHSEED": seed},
                capture_output=True,
                text=True,
                check=True,
            ).stdout

        assert _hash("0") != _hash("1")

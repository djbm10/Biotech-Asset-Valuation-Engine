"""Phase intent is a scientific gate, not a filter applied to a finished list.

``SearchIntent.phases`` was parsed and then dropped on the floor: "in phase 2" changed
nothing about a run. Fixing that meant deciding what "phase 2" *means* before deciding where
to enforce it. It is an exact request. Folding it onto the evidence floor's ``minimum_stage``
would have been one line of code and would have answered a different question --- every
Phase 3 asset admitted --- so the constraint is explicit about which of EXACT, ANY_OF and
MINIMUM was asked for, and the gate engine decides it against the asset's own development
stage facts.

Two properties carry most of the weight here. Unknown phase is not a mismatch: an asset with
no stage evidence is UNKNOWN and goes to review, exactly as every other gate treats absence.
And only asset-specific stage evidence counts --- the discovery-context text a candidate was
found in never satisfies the gate, however many phases it mentions.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from bve.se.gates.engine import PHASE_REQUIREMENT_ID, GateEngine
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache
from bve.se.pipeline import GateEvaluation, SESearchResult
from bve.se.reporting.shortlist import build_shortlist
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    CanonicalAsset,
    ExtractedClaim,
    GateStatus,
    IdentityMention,
    NormalizedFact,
    OverallDisposition,
    PhaseConstraint,
    PhaseConstraintOperator,
    RunManifest,
    SourceDocument,
    SourceTier,
)

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml"

#: The ``development_stage_order`` values the CT.gov extractor emits for each phase.
PHASE_1_ORDER = 2
PHASE_2_ORDER = 3
PHASE_3_ORDER = 4


def _problem(constraint: PhaseConstraint | None = None) -> BuyerProblemV2:
    problem = BuyerProblemV2.model_validate(yaml.safe_load(BENCHMARK.read_text()))
    if constraint is None:
        return problem
    gap = problem.strategic_gap.model_copy(update={"phase_constraint": constraint})
    return problem.model_copy(update={"strategic_gap": gap})


def _fact(fact_id: str, fact_type: str, value) -> NormalizedFact:
    return NormalizedFact(
        fact_id=fact_id,
        subject_id="asset:1",
        fact_type=fact_type,
        value=value,
        supporting_claim_ids=[f"claim:{fact_id}"],
        confidence=0.9,
    )


def _facts(stage_order: int | None) -> list[NormalizedFact]:
    facts = [
        _fact("identity", "identity_valid", True),
        _fact("targets", "construct_target_set", ["CD19"]),
        _fact("modality", "modality_id", "T_CELL_ENGAGER"),
        _fact("ta", "therapeutic_area", "oncology"),
        _fact("poc", "human_poc_present", True),
        _fact("access", "available_deal_routes", ["LICENSE"]),
    ]
    if stage_order is not None:
        facts.append(_fact("stage", "development_stage_order", stage_order))
    return facts


def _phase_decision(problem: BuyerProblemV2, facts: list[NormalizedFact]):
    evaluation = GateEngine().evaluate(problem, subject_id="asset:1", facts=facts)
    return next(
        (
            decision
            for decision in evaluation.decisions
            if decision.requirement_id == PHASE_REQUIREMENT_ID
        ),
        None,
    ), evaluation


EXACT_2 = PhaseConstraint(operator=PhaseConstraintOperator.EXACT, phases=["PHASE2"])
MINIMUM_2 = PhaseConstraint(operator=PhaseConstraintOperator.MINIMUM, phases=["PHASE2"])


@pytest.fixture()
def snapshot(tmp_path, monkeypatch):
    OntologySnapshot(
        sources=[
            SourceProvenance(
                source="open_targets",
                release="26.06",
                retrieved_at=date(2026, 8, 15),
                locator="ftp://example.invalid/target",
            )
        ],
        records=[
            SourceEntityRecord(
                source="open_targets",
                source_id="ENSG00000188389",
                entity_type=EntityType.TARGET,
                canonical_symbol="PDCD1",
                label="PDCD1",
                aliases=[SourceAlias(value="PD-1", alias_type=AliasType.SYNONYM)],
                xrefs={"uniprot": ["Q15116"]},
            )
        ],
    ).write(tmp_path / "snap")
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "snap"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


class TestWhatAPhaseRequestMeans:
    def test_bare_phase_2_is_exact_and_not_a_floor(self, snapshot) -> None:
        intent = parse_query("PD-1 monoclonal antibody assets in phase 2")
        assert intent.phases == ["PHASE2"]
        assert intent.phase_operator is PhaseConstraintOperator.EXACT
        # The distinction only matters if it survives into the contract the gate reads.
        constraint = intent.phase_constraint
        assert constraint is not None
        assert constraint.operator is not PhaseConstraintOperator.MINIMUM

    def test_phase_2_does_not_behave_as_phase_2_plus(self) -> None:
        exact, _ = _phase_decision(_problem(EXACT_2), _facts(PHASE_3_ORDER))
        minimum, _ = _phase_decision(_problem(MINIMUM_2), _facts(PHASE_3_ORDER))
        assert exact.status is GateStatus.FAIL
        assert minimum.status is GateStatus.PASS

    @pytest.mark.parametrize(
        "query",
        ["PD-1 antibody assets in phase 2 or later", "at least phase 2 PD-1 antibody assets"],
    )
    def test_minimum_phrasings_are_read_as_a_floor(self, snapshot, query: str) -> None:
        intent = parse_query(query)
        assert intent.phases == ["PHASE2"]
        assert intent.phase_operator is PhaseConstraintOperator.MINIMUM
        # The cue is consumed with the phase, so "or later" never becomes a free-text
        # indication that would silently narrow retrieval.
        assert not any("later" in term.casefold() for term in intent.residual_terms)

    def test_an_alternative_is_read_as_an_allowed_set(self, snapshot) -> None:
        intent = parse_query("PD-1 antibody assets in phase 1 or phase 2")
        assert intent.phases == ["PHASE1", "PHASE2"]
        assert intent.phase_operator is PhaseConstraintOperator.ANY_OF


class TestTheGateDecidesOnAssetEvidence:
    def test_known_phase_2_passes_exact_phase_2(self) -> None:
        decision, evaluation = _phase_decision(_problem(EXACT_2), _facts(PHASE_2_ORDER))
        assert decision.status is GateStatus.PASS
        assert evaluation.disposition is OverallDisposition.ELIGIBLE

    def test_known_phase_1_fails_exact_phase_2(self) -> None:
        decision, evaluation = _phase_decision(_problem(EXACT_2), _facts(PHASE_1_ORDER))
        assert decision.status is GateStatus.FAIL
        assert evaluation.disposition is OverallDisposition.EXCLUDED

    def test_known_phase_3_fails_exact_phase_2(self) -> None:
        decision, evaluation = _phase_decision(_problem(EXACT_2), _facts(PHASE_3_ORDER))
        assert decision.status is GateStatus.FAIL
        assert evaluation.disposition is OverallDisposition.EXCLUDED

    def test_unknown_phase_routes_to_review_not_exclusion(self) -> None:
        decision, evaluation = _phase_decision(_problem(EXACT_2), _facts(None))
        assert decision.status is GateStatus.UNKNOWN
        assert evaluation.disposition is OverallDisposition.UNRESOLVED
        assert any(
            item.requirement_id == PHASE_REQUIREMENT_ID for item in evaluation.review_items
        )

    def test_conflicting_phase_evidence_routes_to_review(self) -> None:
        facts = [*_facts(PHASE_2_ORDER), _fact("stage2", "development_stage_order", PHASE_1_ORDER)]
        decision, evaluation = _phase_decision(_problem(EXACT_2), facts)
        assert decision.status is GateStatus.UNKNOWN
        assert evaluation.disposition is OverallDisposition.UNRESOLVED

    def test_at_least_phase_2_admits_2_and_3_but_not_1(self) -> None:
        problem = _problem(MINIMUM_2)
        statuses = {
            order: _phase_decision(problem, _facts(order))[0].status
            for order in (PHASE_1_ORDER, PHASE_2_ORDER, PHASE_3_ORDER)
        }
        assert statuses == {
            PHASE_1_ORDER: GateStatus.FAIL,
            PHASE_2_ORDER: GateStatus.PASS,
            PHASE_3_ORDER: GateStatus.PASS,
        }

    def test_discovery_context_phase_text_cannot_satisfy_the_gate(self) -> None:
        # Everything the run knows about phase, except an asset-specific stage fact.
        facts = [
            *_facts(None),
            _fact("context", "discovery_target_context", ["a phase 2 study of CD19"]),
            _fact("modality_text", "modality_id", "T_CELL_ENGAGER"),
        ]
        decision, _ = _phase_decision(_problem(EXACT_2), facts)
        assert decision.status is GateStatus.UNKNOWN
        assert decision.observed_fact_ids == []

    def test_the_decision_keeps_the_evidence_that_caused_it(self) -> None:
        for order in (PHASE_2_ORDER, PHASE_1_ORDER):
            decision, _ = _phase_decision(_problem(EXACT_2), _facts(order))
            assert decision.observed_fact_ids == ["stage"]
            assert decision.supporting_or_contradictory_claim_ids == ["claim:stage"]


class TestTheTwoEntryPointsAgree:
    def test_query_and_compiled_yaml_produce_identical_behavior(self, snapshot) -> None:
        intent = parse_query("PD-1 monoclonal antibody assets in phase 2")
        compiled = compile_intent(
            intent, buyer=build_buyer_identity("NL", as_of_date=date(2026, 8, 15))
        )
        # The round trip is the CLI's --emit-problem path: a typed question is an input
        # like any other, and must replay from the file it wrote.
        round_tripped = BuyerProblemV2.model_validate(
            yaml.safe_load(yaml.safe_dump(compiled.model_dump(mode="json")))
        )
        assert round_tripped.strategic_gap.phase_constraint == compiled.strategic_gap.phase_constraint
        assert round_tripped.strategic_gap.phase_constraint == PhaseConstraint(
            operator=PhaseConstraintOperator.EXACT, phases=["PHASE2"]
        )
        for order in (PHASE_1_ORDER, PHASE_2_ORDER, PHASE_3_ORDER):
            facts = _facts(order)
            from_query = GateEngine().evaluate(compiled, subject_id="asset:1", facts=facts)
            from_file = GateEngine().evaluate(round_tripped, subject_id="asset:1", facts=facts)
            assert from_query.model_dump(mode="json") == from_file.model_dump(mode="json")


class TestNothingElseMoved:
    def test_a_problem_without_a_phase_constraint_gates_exactly_as_before(self) -> None:
        problem = _problem()
        assert problem.strategic_gap.phase_constraint is None
        evaluation = GateEngine().evaluate(
            problem, subject_id="asset:1", facts=_facts(PHASE_1_ORDER)
        )
        assert all(
            decision.requirement_id != PHASE_REQUIREMENT_ID for decision in evaluation.decisions
        )
        # Phase 1 evidence against a benchmark with no phase intent stays eligible; the new
        # gate is additive and silent unless the query asked for a phase.
        assert evaluation.disposition is OverallDisposition.ELIGIBLE

    def test_existing_benchmark_problems_still_validate_and_round_trip(self) -> None:
        raw = yaml.safe_load(BENCHMARK.read_text())
        assert "phase_constraint" not in raw["strategic_gap"]
        problem = BuyerProblemV2.model_validate(raw)
        assert BuyerProblemV2.model_validate(problem.model_dump(mode="json")) == problem


NOW = datetime(2026, 9, 17, tzinfo=timezone.utc)


def _shortlist_result(phase_status: GateStatus) -> SESearchResult:
    document = SourceDocument(
        document_id="document:" + "1".rjust(20, "0"),
        source_url="https://clinicaltrials.gov/study/NCT03646318",
        publisher="ClinicalTrials.gov",
        document_type="registry_record",
        publication_date=date(2024, 5, 1),
        retrieval_date=date(2026, 9, 1),
        content_hash="hash0001",
        source_tier=SourceTier.REGISTRY,
    )
    asset = CanonicalAsset(
        asset_id="asset:aaaa",
        canonical_name="Blinatumomab",
        aliases=["Blinatumomab"],
        identity_keys=["blinatumomab"],
        discovery_target_context=["CD19"],
        modality_id="T_CELL_ENGAGER",
        development_stage="PHASE_2",
        mention_ids=["mention:" + "1".rjust(20, "0")],
        supporting_claim_ids=["claim:" + "1".rjust(20, "0")],
    )
    facts = _facts(PHASE_2_ORDER if phase_status is GateStatus.PASS else None)
    evaluation = GateEngine().evaluate(_problem(EXACT_2), subject_id=asset.asset_id, facts=facts)
    return SESearchResult(
        problem_id="problem_phase",
        run_manifest=RunManifest(
            run_id="se:phase-test",
            problem_id="problem_phase",
            problem_version="v2",
            as_of_date=date(2026, 9, 16),
            started_at=NOW,
            code_version="deadbeef",
            normalization_version="v1",
        ),
        candidates=[asset],
        identity_mentions=[
            IdentityMention(
                mention_id="mention:" + "1".rjust(20, "0"),
                hit_id="hit:1",
                raw_asset_name="Blinatumomab",
                normalized_asset_name="blinatumomab",
                source_document_id=document.document_id,
                observed_at=NOW,
            )
        ],
        source_documents=[document],
        claims=[
            ExtractedClaim(
                claim_id="claim:" + "1".rjust(20, "0"),
                subject_id=asset.asset_id,
                predicate="development_stage_order",
                normalized_value="PHASE_2",
                source_document_id=document.document_id,
                supporting_passage='["PHASE2"]',
                locator="NCT03646318",
                extraction_method="ctgov_structured",
                extractor_version="v1",
                extraction_confidence=1.0,
                applicable_as_of_date=date(2026, 9, 1),
            )
        ],
        unresolved_asset_ids=[asset.asset_id],
        gate_evaluations=[
            GateEvaluation(
                subject_id=asset.asset_id,
                disposition=OverallDisposition.UNRESOLVED,
                decisions=evaluation.decisions,
            )
        ],
    )


class TestTheShortlistShowsTheSameDecision:
    def test_the_gate_result_and_its_phase_provenance_are_displayed(self) -> None:
        shortlist = build_shortlist(_shortlist_result(GateStatus.PASS))
        entry = shortlist.entries[0]
        phase = next(fact for fact in entry.facts if fact.label == "Phase")
        assert phase.value == "PHASE_2"
        assert "phase gate PASS" in (phase.note or "")
        # The same decision, and the evidence behind it, not a second opinion.
        assert any("phase gate PASS" in line for line in entry.why)
        assert [citation.native_id for citation in phase.citations] == ["NCT03646318"]

    def test_an_undecided_phase_is_shown_as_undecided(self) -> None:
        shortlist = build_shortlist(_shortlist_result(GateStatus.UNKNOWN))
        entry = shortlist.entries[0]
        phase = next(fact for fact in entry.facts if fact.label == "Phase")
        assert "phase gate UNKNOWN" in (phase.note or "")

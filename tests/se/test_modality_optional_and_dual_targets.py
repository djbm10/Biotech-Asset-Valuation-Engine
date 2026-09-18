"""Two readings of a BD question that the engine used to get wrong in opposite directions.

**Modality.** "Find dual CD19/BCMA *therapies*" names no modality on purpose: the asker
wants whatever hits both targets, CAR-T or bispecific or anything else. The engine refused
the question outright — ``no modality recognized in the query`` — which forced the user to
invent a narrowing they had not asked for, and then answered that narrower question under
the original's name. Naming no modality is now a valid, *wider* question: no modality gate
is emitted at all, and the run states ``modality constraint: none`` rather than leaving the
reader to infer it from an absence. A question that *does* name a modality is untouched.

**Dual.** The word ``dual`` used to land in residual text. That was tolerable only for as
long as the target operator happened to come out ``ALL``, and it does not always: the
operator is *inferred* from the connector between the target spans, and an unrecognized
connector falls back to ``ANY`` — at which point a question asking for dual CD19/BCMA
assets would happily return a CD19-only asset. ``dual`` is a scientific claim about one
molecule, so it now sets the conjunction explicitly instead of confirming it by luck.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.gates.engine import GateEngine
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
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    GateStatus,
    NormalizedFact,
    TargetOperator,
)

BUYER = build_buyer_identity("NL Query", as_of_date=date(2026, 9, 17))

MODALITY_GATE = "modality_technology"
TARGET_GATE = "target_logic"


def _record(source_id: str, symbol: str, aliases: list[str], uniprot: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=source_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=symbol,
        aliases=[SourceAlias(value=alias, alias_type=AliasType.SYNONYM) for alias in aliases],
        xrefs={"uniprot": [uniprot]},
    )


@pytest.fixture()
def snapshot(tmp_path, monkeypatch):
    OntologySnapshot(
        sources=[
            SourceProvenance(
                source="open_targets",
                release="26.06",
                retrieved_at=date(2026, 9, 17),
                locator="ftp://example.invalid/target",
            )
        ],
        records=[
            _record("ENSG00000048462", "TNFRSF17", ["BCMA", "CD269"], "Q02223"),
            _record("ENSG00000177455", "CD19", ["B4"], "P15391"),
        ],
    ).write(tmp_path / "snap")
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "snap"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


def _fact(fact_id: str, fact_type: str, value) -> NormalizedFact:
    return NormalizedFact(
        fact_id=fact_id,
        subject_id="asset:1",
        fact_type=fact_type,
        value=value,
        supporting_claim_ids=[f"claim:{fact_id}"],
        confidence=0.9,
    )


def _facts(targets: list[str], *, modality: str = "CAR_T") -> list[NormalizedFact]:
    return [
        _fact("identity", "identity_valid", True),
        _fact("targets", "construct_target_set", targets),
        _fact("modality", "modality_id", modality),
        _fact("ta", "therapeutic_area", "autoimmune"),
        _fact("stage", "development_stage_order", 3),
        _fact("access", "available_deal_routes", ["LICENSE"]),
    ]


def _decisions(problem: BuyerProblemV2, facts: list[NormalizedFact], gate_id: str):
    evaluation = GateEngine().evaluate(problem, subject_id="asset:1", facts=facts)
    return [decision for decision in evaluation.decisions if decision.gate_id == gate_id]


class TestModalityIsOptional:
    def test_a_modality_free_question_compiles(self, snapshot) -> None:
        problem = compile_intent(parse_query("CD19 therapies"), buyer=BUYER)
        assert problem.strategic_gap.modalities == []

    @pytest.mark.parametrize("word", ["therapy", "therapies", "program", "asset", "drug"])
    def test_a_generic_noun_infers_no_modality(self, snapshot, word: str) -> None:
        # These are the words for "a thing that treats people". Reading any of them as a
        # modality would be the engine choosing a narrowing and attributing it to the user.
        assert parse_query(f"CD19 {word}").modalities == []

    def test_a_modality_free_question_emits_no_modality_gate(self, snapshot) -> None:
        problem = compile_intent(parse_query("CD19 therapies"), buyer=BUYER)
        # Not "a gate that passes everything" -- no gate. A requirement of IN [] would FAIL
        # every asset, which is the opposite of the wider question that was asked.
        assert _decisions(problem, _facts(["CD19"]), MODALITY_GATE) == []

    def test_an_asset_of_any_modality_survives_a_modality_free_question(self, snapshot) -> None:
        problem = compile_intent(parse_query("CD19 therapies"), buyer=BUYER)
        for modality in ("CAR_T", "BISPECIFIC_ANTIBODY", "SMALL_MOLECULE"):
            facts = _facts(["CD19"], modality=modality)
            assert _decisions(problem, facts, MODALITY_GATE) == []

    def test_the_absence_is_stated_rather_than_left_to_inference(self, snapshot) -> None:
        intent = parse_query("CD19 therapies")
        assert "modality constraint: none" in intent.explain_constraints()

    def test_a_stated_modality_is_unchanged(self, snapshot) -> None:
        problem = compile_intent(parse_query("CD19 CAR-T therapies"), buyer=BUYER)
        assert problem.strategic_gap.modalities == ["CAR_T"]
        decisions = _decisions(problem, _facts(["CD19"], modality="CAR_T"), MODALITY_GATE)
        assert [decision.status for decision in decisions] == [GateStatus.PASS]

    def test_a_stated_modality_still_excludes_another_modality(self, snapshot) -> None:
        problem = compile_intent(parse_query("CD19 CAR-T therapies"), buyer=BUYER)
        decisions = _decisions(problem, _facts(["CD19"], modality="SMALL_MOLECULE"), MODALITY_GATE)
        assert [decision.status for decision in decisions] == [GateStatus.FAIL]


class TestDualMeansOneMolecule:
    def test_dual_sets_the_conjunction_explicitly(self, snapshot) -> None:
        intent = parse_query("dual CD19/BCMA therapies")
        assert intent.target_operator is TargetOperator.ALL

    def test_the_warning_does_not_call_a_stated_reading_an_inference(self, snapshot) -> None:
        warnings = parse_query("dual CD19/BCMA therapies").warnings
        assert any("ALL stated by conjunction_stated" in warning for warning in warnings)

    def test_dual_is_not_residual(self, snapshot) -> None:
        # Residual is where a word goes to be ignored. "dual" decides which assets qualify.
        assert "dual" not in parse_query("dual CD19/BCMA therapies").residual_terms

    def test_dual_overrides_a_connector_that_would_otherwise_read_as_either(self, snapshot) -> None:
        # Without "dual" this comma falls through to the default disjunction and a
        # single-target asset qualifies. The word the user wrote has to win.
        assert parse_query("dual CD19, BCMA therapies").target_operator is TargetOperator.ALL

    def test_a_cd19_only_asset_cannot_satisfy_the_dual_question(self, snapshot) -> None:
        problem = compile_intent(parse_query("dual CD19/BCMA therapies"), buyer=BUYER)
        decisions = _decisions(problem, _facts(["CD19"]), TARGET_GATE)
        assert [decision.status for decision in decisions] == [GateStatus.FAIL]

    def test_a_bcma_only_asset_cannot_satisfy_the_dual_question(self, snapshot) -> None:
        problem = compile_intent(parse_query("dual CD19/BCMA therapies"), buyer=BUYER)
        decisions = _decisions(problem, _facts(["TNFRSF17"]), TARGET_GATE)
        assert [decision.status for decision in decisions] == [GateStatus.FAIL]

    def test_an_asset_hitting_both_satisfies_it(self, snapshot) -> None:
        problem = compile_intent(parse_query("dual CD19/BCMA therapies"), buyer=BUYER)
        decisions = _decisions(problem, _facts(["CD19", "TNFRSF17"]), TARGET_GATE)
        assert [decision.status for decision in decisions] == [GateStatus.PASS]

    def test_dual_naming_only_one_target_is_refused_not_quietly_narrowed(self, snapshot) -> None:
        # "dual CD19" asks for a two-target molecule and names one. Compiling it as a
        # plain CD19 search would answer a different, wider question in silence.
        intent = parse_query("dual CD19 therapies")
        assert any("dual" in blocker for blocker in intent.blockers())

    def test_dual_contradicted_by_or_is_refused(self, snapshot) -> None:
        intent = parse_query("dual CD19 or BCMA therapies")
        assert any("dual" in blocker for blocker in intent.blockers())


class TestNoScientificPhraseIsSilentlyDropped:
    def test_every_recognized_phrase_of_the_acceptance_query_has_a_fate(self, snapshot) -> None:
        intent = parse_query(
            "Find clinical-stage dual CD19/BCMA therapies for autoimmune disease "
            "with human efficacy."
        )
        rendered = "\n".join(intent.explain())
        assert "'clinical-stage' -> EVIDENCE" in rendered
        assert "'dual' -> TARGET_LOGIC" in rendered
        assert "'CD19' -> TARGET CD19" in rendered
        assert "'BCMA' -> TARGET TNFRSF17" in rendered
        assert "'autoimmune disease' -> UNRESOLVED_SCIENTIFIC" in rendered
        assert "'human efficacy' -> EVIDENCE" in rendered
        assert intent.residual_terms == []


class TestTheWarningTracksWhatWasActuallySupplied:
    QUERY = "dual CD19/BCMA therapies for autoimmune disease"

    def test_unanswered_the_phrase_is_warned_about(self, snapshot) -> None:
        warnings = parse_query(self.QUERY).warnings_for(indication_supplied=False)
        assert any("autoimmune disease" in warning for warning in warnings)

    def test_once_supplied_the_engine_stops_saying_it_was_not_applied(self, snapshot) -> None:
        warnings = parse_query(self.QUERY).warnings_for(indication_supplied=True)
        assert not any("will NOT apply" in warning for warning in warnings)

    def test_and_says_what_it_was_answered_with_instead(self, snapshot) -> None:
        warnings = parse_query(self.QUERY).warnings_for(indication_supplied=True)
        assert any("autoimmune disease" in warning for warning in warnings)

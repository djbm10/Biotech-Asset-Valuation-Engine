"""M9C — a typed question compiles deterministically, or refuses to compile."""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.intent import (
    IntentNotCompilable,
    SpanKind,
    build_buyer_identity,
    compile_intent,
    intent_to_trial_query,
    parse_query,
    supported_modalities,
)
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache
from bve.se.schemas.contracts import TargetOperator

BUYER = build_buyer_identity("NL Query", as_of_date=date(2026, 8, 15))


def _record(source_id: str, symbol: str, aliases: list[str], uniprot: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=source_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        aliases=[SourceAlias(value=alias, alias_type=AliasType.SYNONYM) for alias in aliases],
        xrefs={"uniprot": [uniprot]},
    )


@pytest.fixture()
def snapshot(tmp_path, monkeypatch):
    """A three-target snapshot; nothing here is benchmark-specific seeding."""

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
            _record("ENSG00000188389", "PDCD1", ["PD-1", "PD1", "CD279"], "Q15116"),
            _record("ENSG00000048462", "TNFRSF17", ["BCMA", "CD269"], "Q02223"),
            _record("ENSG00000177455", "CD19", ["B4"], "P15391"),
        ],
    ).write(tmp_path / "snap")
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "snap"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


@pytest.fixture()
def no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "absent"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


class TestParsing:
    def test_resolves_targets_through_the_ontology_not_the_query_spelling(self, snapshot):
        intent = parse_query("find PD-1 monoclonal antibody programs")
        assert [target.canonical_id for target in intent.targets] == ["PDCD1"]

    def test_synonym_and_approved_symbol_produce_the_same_intent(self, snapshot):
        by_synonym = parse_query("BCMA T cell engager assets")
        by_symbol = parse_query("TNFRSF17 T cell engager assets")
        assert by_synonym.targets == by_symbol.targets
        assert by_synonym.modalities == by_symbol.modalities

    def test_longest_modality_phrase_wins(self, snapshot):
        intent = parse_query("CD19 bispecific T cell engager trials")
        assert intent.modalities == ["T_CELL_ENGAGER"]

    def test_registry_phase_and_status_are_recognized(self, snapshot):
        intent = parse_query("recruiting phase 1/2 CD19 CAR-T trials")
        assert intent.phases == ["PHASE1", "PHASE2"]
        assert intent.statuses == ["RECRUITING"]
        assert intent.modalities == ["CAR_T"]

    def test_roman_numeral_phases(self, snapshot):
        assert parse_query("phase III CD19 CAR-T").phases == ["PHASE3"]

    def test_unrecognized_words_become_residual_not_facts(self, snapshot):
        intent = parse_query("CD19 CAR-T in relapsed myeloma")
        assert "myeloma" in intent.residual_terms
        assert "relapsed" in intent.residual_terms
        # The residual is never promoted into a resolved criterion.
        assert all(span.resolved_to is None for span in intent.spans if span.kind is SpanKind.RESIDUAL)

    def test_stopwords_are_not_residual_terms(self, snapshot):
        intent = parse_query("find me the best CD19 CAR-T assets")
        assert "the" not in intent.residual_terms
        assert "find" not in intent.residual_terms


class TestDeterminism:
    def test_same_query_yields_the_same_intent(self, snapshot):
        first = parse_query("PD-1 monoclonal antibody phase 2")
        second = parse_query("PD-1 monoclonal antibody phase 2")
        assert first == second

    def test_problem_id_is_stable_across_whitespace_and_case(self, snapshot):
        assert parse_query("CD19 CAR-T").problem_id == parse_query("  cd19   CAR-T ").problem_id

    def test_different_questions_get_different_problem_ids(self, snapshot):
        assert parse_query("CD19 CAR-T").problem_id != parse_query("BCMA CAR-T").problem_id


class TestTargetOperator:
    def test_conjunction_means_one_molecule_hitting_both(self, snapshot):
        intent = parse_query("CD19 and BCMA T cell engager")
        assert intent.target_operator is TargetOperator.ALL

    def test_disjunction_means_either_target(self, snapshot):
        intent = parse_query("CD19 or BCMA CAR-T")
        assert intent.target_operator is TargetOperator.ANY

    def test_the_inference_is_surfaced_as_a_warning(self, snapshot):
        intent = parse_query("CD19 and BCMA T cell engager")
        assert any("target operator ALL" in warning for warning in intent.warnings)

    def test_single_target_defaults_to_any(self, snapshot):
        assert parse_query("CD19 CAR-T").target_operator is TargetOperator.ANY


class TestAbstention:
    def test_without_a_snapshot_nothing_resolves_and_it_says_so(self, no_snapshot):
        intent = parse_query("CD19 CAR-T assets")
        assert intent.targets == []
        assert intent.ontology_version.startswith("no_snapshot")
        assert any("no ontology snapshot" in warning for warning in intent.warnings)
        assert intent.is_compilable is False

    def test_an_unrecognized_target_does_not_compile(self, snapshot):
        intent = parse_query("ZZZ9 CAR-T assets")
        with pytest.raises(IntentNotCompilable) as excinfo:
            compile_intent(intent, buyer=BUYER)
        assert "no biological target recognized" in str(excinfo.value)

    def test_a_missing_modality_does_not_compile(self, snapshot):
        intent = parse_query("CD19 assets")
        with pytest.raises(IntentNotCompilable, match="no modality recognized"):
            compile_intent(intent, buyer=BUYER)

    def test_ambiguity_is_reported_rather_than_resolved(self, tmp_path, monkeypatch):
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
                _record("ENSG1", "ABL1", ["p150"], "P00519"),
                _record("ENSG2", "ELP1", ["p150"], "O95163"),
            ],
        ).write(tmp_path / "amb")
        monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "amb"))
        reset_resolver_cache()
        try:
            intent = parse_query("p150 CAR-T assets")
            assert intent.targets == []
            assert intent.ambiguous_terms == ["p150"]
            span = next(s for s in intent.spans if s.kind is SpanKind.AMBIGUOUS_TARGET)
            assert sorted(span.candidates) == ["TARGET:ABL1", "TARGET:ELP1"]
            with pytest.raises(IntentNotCompilable, match="ambiguous"):
                compile_intent(intent, buyer=BUYER)
        finally:
            reset_resolver_cache()


class TestCompilation:
    def test_compiles_to_a_buyer_problem_with_snapshot_aliases(self, snapshot):
        intent = parse_query("PD-1 monoclonal antibody assets")
        problem = compile_intent(intent, buyer=BUYER)
        target = problem.strategic_gap.target_expression.targets[0]
        assert target.canonical_id == "PDCD1"
        # Aliases come from the snapshot, so recall does not depend on the spelling typed.
        assert "CD279" in target.aliases
        assert problem.strategic_gap.modalities == ["MONOCLONAL_ANTIBODY"]

    def test_version_pins_both_compiler_and_snapshot(self, snapshot):
        problem = compile_intent(parse_query("CD19 CAR-T"), buyer=BUYER)
        assert problem.version.startswith("intent_v1__")
        assert "resolver_v1" in problem.version

    def test_problem_id_matches_the_intent(self, snapshot):
        intent = parse_query("CD19 CAR-T")
        assert compile_intent(intent, buyer=BUYER).problem_id == intent.problem_id

    def test_compilation_is_byte_identical_for_the_same_question(self, snapshot):
        left = compile_intent(parse_query("CD19 CAR-T"), buyer=BUYER)
        right = compile_intent(parse_query("CD19 CAR-T"), buyer=BUYER)
        assert left.model_dump_json() == right.model_dump_json()

    def test_unspecified_therapeutic_area_is_stated_not_invented(self, snapshot):
        problem = compile_intent(parse_query("CD19 CAR-T"), buyer=BUYER)
        assert problem.strategic_gap.therapeutic_areas == ["UNSPECIFIED"]

    def test_caller_supplied_therapeutic_area_is_used(self, snapshot):
        problem = compile_intent(
            parse_query("CD19 CAR-T"), buyer=BUYER, therapeutic_areas=["ONCOLOGY"]
        )
        assert problem.strategic_gap.therapeutic_areas == ["ONCOLOGY"]

    def test_residual_terms_become_indications_not_resolved_concepts(self, snapshot):
        problem = compile_intent(parse_query("CD19 CAR-T in myeloma"), buyer=BUYER)
        assert "myeloma" in problem.strategic_gap.indications

    def test_buyer_identity_for_an_ad_hoc_query_is_labelled_as_such(self):
        assert build_buyer_identity("NL Query", as_of_date=date(2026, 8, 15)).buyer_id == "nl_query"


class TestTrialQueryHandoff:
    def test_intent_expands_to_snapshot_aliases_for_retrieval(self, snapshot):
        query = intent_to_trial_query(parse_query("PD-1 monoclonal antibody"))
        assert "PDCD1" in query.terms
        assert "CD279" in query.terms

    def test_status_carries_into_the_trial_query(self, snapshot):
        query = intent_to_trial_query(parse_query("recruiting CD19 CAR-T"))
        assert query.statuses == ["RECRUITING"]

    def test_as_of_date_is_carried_for_no_lookahead(self, snapshot):
        query = intent_to_trial_query(parse_query("CD19 CAR-T"), as_of_date=date(2024, 1, 1))
        assert query.as_of_date == date(2024, 1, 1)


class TestExplainability:
    def test_every_span_records_the_rule_that_fired(self, snapshot):
        intent = parse_query("recruiting phase 2 PD-1 monoclonal antibody in melanoma")
        assert all(span.rule for span in intent.spans)
        rendered = "\n".join(intent.explain())
        assert "'PD-1' -> TARGET PDCD1" in rendered
        assert "melanoma" in rendered

    def test_target_spans_carry_the_resolution_derivation(self, snapshot):
        intent = parse_query("PD-1 CAR-T")
        span = next(s for s in intent.spans if s.kind is SpanKind.TARGET)
        assert span.explanation is not None
        assert "PDCD1" in span.explanation

    def test_supported_modalities_are_enumerable_for_error_messages(self):
        assert "CAR_T" in supported_modalities()

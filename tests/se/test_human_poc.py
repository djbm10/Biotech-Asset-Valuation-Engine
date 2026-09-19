"""Human proof of concept: what counts as efficacy, and whose efficacy it is.

``human_poc_required`` is the second requirement in the acceptance query that compiled
correctly and then decided nothing, because no producer answered it. The fact it needs is
narrow on purpose. Being in the clinic is not efficacy; having a trial is not efficacy;
being tolerated is not efficacy; and a number printed next to a protocol endpoint that was
never measured is not a result.

The other half is attribution. A combination trial reports one regimen's outcome, and
handing that outcome to each component would let a single-target asset inherit a dual
construct's evidence -- the same failure the construct target set exists to prevent,
arriving through the efficacy door instead.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.evidence.human_poc import (
    efficacy_statements,
    human_poc_evidence,
    result_supports_human_poc,
)
from bve.se.gates.engine import GateEngine
from bve.se.schemas.contracts import BuyerProblemV2, ClinicalResult

AS_OF = date(2026, 9, 17)


def _result(**overrides) -> ClinicalResult:
    base = dict(
        result_id="res:1",
        subject_id="asset:a",
        indication="systemic lupus erythematosus",
        population="refractory SLE",
        treatment_line="",
        development_stage="PHASE1",
        endpoint="Overall response rate",
        endpoint_family="response",
        effect_size=0.75,
        evaluable_patients=12,
        incomplete_reporting=False,
        supporting_claim_ids=["claim:1"],
    )
    base.update(overrides)
    return ClinicalResult(**base)


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        {
            "problem_id": "p",
            "version": "1",
            "buyer": {"buyer_id": "b", "name": "Buyer", "as_of_date": AS_OF.isoformat()},
            "strategic_gap": {
                "therapeutic_areas": ["autoimmune"],
                "target_expression": {
                    "operator": "ANY",
                    "targets": [{"canonical_id": "MS4A1", "label": "MS4A1", "aliases": []}],
                },
                "evidence_floor": {"human_poc_required": True},
                "acceptable_deal_routes": ["LICENSE"],
            },
        }
    )


def _decision(facts):
    evaluation = GateEngine().evaluate(_problem(), subject_id="asset:a", facts=facts)
    return next(
        decision
        for decision in evaluation.decisions
        if decision.requirement_id == "evidence.human_poc"
    )


def _fact(**kwargs):
    evidence = human_poc_evidence("asset:a", as_of_date=AS_OF, **kwargs)
    return None if evidence is None else evidence.fact


class TestAReportedEfficacyResultIsProofOfConcept:
    def test_a_reported_response_rate_passes_the_gate(self) -> None:
        fact = _fact(results=[_result()], statements=[])
        assert fact is not None and fact.value is True
        assert _decision([fact]).status.value == "PASS"

    def test_the_fact_carries_what_a_reader_would_have_to_check(self) -> None:
        evidence = human_poc_evidence(
            "asset:a", results=[_result()], statements=[], as_of_date=AS_OF
        )
        assert evidence is not None
        claim = evidence.claims[0]
        assert claim.indication == "systemic lupus erythematosus"
        assert claim.endpoint == "Overall response rate"
        assert claim.population == "refractory SLE"
        assert claim.supporting_passage
        assert evidence.fact.supporting_claim_ids == [claim.claim_id]


class TestBeingInTheClinicIsNotEfficacy:
    """Each of these is a true statement about an asset that says nothing about benefit."""

    def test_a_trial_with_no_reported_result_is_unknown(self) -> None:
        # A phase 2 protocol. The endpoint exists because someone intends to measure it.
        assert _fact(results=[_result(effect_size=None, incomplete_reporting=True)], statements=[]) is None

    def test_a_protocol_endpoint_without_a_value_is_unknown(self) -> None:
        # Registry outcome measures arrive this way in bulk: named, never reported.
        assert _fact(results=[_result(effect_size=None)], statements=[]) is None

    def test_safety_data_is_not_efficacy(self) -> None:
        assert not result_supports_human_poc(
            _result(endpoint="Incidence of treatment-emergent adverse events", endpoint_family="safety")
        )
        assert (
            _fact(
                results=[
                    _result(
                        endpoint="Incidence of treatment-emergent adverse events",
                        endpoint_family="safety",
                    )
                ],
                statements=[],
            )
            is None
        )

    @pytest.mark.parametrize(
        "endpoint",
        [
            "Maximum plasma concentration (Cmax)",
            "Area under the curve (AUC)",
            "Dose-limiting toxicities",
            "Number of participants with cytokine release syndrome",
            "Peak CAR-T cell expansion in peripheral blood",
        ],
    )
    def test_pharmacology_and_tolerability_endpoints_are_not_efficacy(self, endpoint) -> None:
        assert not result_supports_human_poc(_result(endpoint=endpoint, endpoint_family=""))

    def test_an_unresolved_asset_with_no_results_says_nothing(self) -> None:
        assert _fact(results=[], statements=[]) is None

    def test_the_gate_prefers_unknown_to_a_false_negative(self) -> None:
        # Nothing produced means nothing is asserted; the asset goes to review rather
        # than being excluded for evidence no one looked for.
        assert _decision([]).status.value == "UNKNOWN"


class TestOnlyHumanEvidenceCounts:
    def test_animal_efficacy_is_not_human_proof_of_concept(self) -> None:
        text = (
            "In a murine model of lupus nephritis, treatment with ABC-123 produced complete "
            "remission in 8 of 10 mice."
        )
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_in_vitro_activity_is_not_human_proof_of_concept(self) -> None:
        text = "ABC-123 lysed 95% of CD19-positive target cells in vitro."
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []


class TestEfficacyBelongsToOneAsset:
    """Co-administration is not attribution -- the rule the construct target set needed too."""

    def test_a_combination_result_does_not_prove_either_component_alone(self) -> None:
        text = (
            "Patients treated with ABC-123 plus dexamethasone achieved an overall response "
            "rate of 75% (9 of 12)."
        )
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_a_co_administered_assets_result_does_not_transfer(self) -> None:
        text = (
            "Among patients receiving teclistamab, the overall response rate was 63%. "
            "ABC-123 was administered as bridging therapy."
        )
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_a_result_reaches_the_asset_through_a_legitimate_alias(self) -> None:
        text = "Treatment with obecabtagene autoleucel achieved remission in 11 of 14 patients."
        statements = efficacy_statements(
            text, asset_names=["AUCATZYL", "obecabtagene autoleucel"]
        )
        assert len(statements) == 1
        assert statements[0].asset_name == "obecabtagene autoleucel"

    def test_a_defined_combination_product_may_carry_its_own_result(self) -> None:
        # When the candidate *is* the combination, the regimen's result is its own.
        text = "CD19/BCMA dual CAR-T achieved complete remission in 10 of 12 patients."
        statements = efficacy_statements(text, asset_names=["CD19/BCMA dual CAR-T"])
        assert len(statements) == 1


class TestAStatementHasToReportSomething:
    def test_an_intention_to_measure_is_not_a_measurement(self) -> None:
        text = (
            "The primary endpoint is overall response rate at 3 months. Enrollment of 40 "
            "patients is planned."
        )
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_a_sponsor_claim_without_a_result_is_not_a_result(self) -> None:
        text = "ABC-123 is a promising therapy with the potential to improve response rates."
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_a_review_article_calling_for_trials_reports_nothing(self) -> None:
        text = (
            "MoAbs offer the potential to improve efficacy by reducing toxicity. However, "
            "there is a huge need for clinical trials exploring response duration."
        )
        assert efficacy_statements(text, asset_names=["MoAbs"]) == []

    def test_eligibility_criteria_are_not_results(self) -> None:
        # The only thing the prose route matched on the live corpus, before this rule: a
        # registry eligibility block, written in exactly the vocabulary of a result.
        text = (
            "Active symptoms with inadequate response to at least one immunomodulatory "
            "therapy in 40% of patients."
        )
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_a_concatenated_field_is_not_a_sentence(self) -> None:
        # Registry text arrives as multi-thousand-character blobs in which an efficacy word
        # and a number coincide without one being about the other.
        blob = (
            "ABC-123 " + "study procedures and administrative detail. " * 30
            + "response 40% somewhere in patients"
        ).replace(". ", " ")
        assert efficacy_statements(blob, asset_names=["ABC-123"]) == []

    def test_an_endpoint_definition_in_the_past_tense_is_not_a_result(self) -> None:
        # Drawn from a real abstract: a number appears, and it defines the endpoint.
        text = (
            "The primary outcome was the response rate at 16 weeks after ABC-123 initiation, "
            "defined as the proportion of patients achieving a 50% reduction in seizures."
        )
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []

    def test_a_reported_response_rate_is_a_result(self) -> None:
        text = "Treatment with ABC-123 produced an overall response rate of 75% (9 of 12 patients)."
        statements = efficacy_statements(text, asset_names=["ABC-123"])
        assert len(statements) == 1
        assert statements[0].endpoint


class TestTheQuestionCannotAnswerItself:
    def test_query_context_cannot_create_human_poc(self) -> None:
        # The buyer asking for human efficacy is the reason to look, never the finding.
        text = "A phase 1 study of ABC-123 in patients with systemic lupus erythematosus."
        assert efficacy_statements(text, asset_names=["ABC-123"]) == []
        assert _fact(results=[], statements=[]) is None


class TestBothRoutesMeanTheSameThing:
    def test_a_prose_result_and_a_structured_result_produce_the_same_fact(self) -> None:
        statements = efficacy_statements(
            "Treatment with ABC-123 produced an overall response rate of 75% (9 of 12 patients).",
            asset_names=["ABC-123"],
        )
        from_prose = _fact(results=[], statements=statements)
        from_structured = _fact(results=[_result()], statements=[])
        assert from_prose is not None and from_structured is not None
        assert from_prose.fact_type == from_structured.fact_type == "human_poc_present"
        assert from_prose.value is from_structured.value is True
        assert _decision([from_prose]).status == _decision([from_structured]).status


class TestNoAssetIsSpecialCased:
    def test_the_module_names_no_asset_and_no_indication(self) -> None:
        import ast
        import inspect

        from bve.se.evidence import human_poc

        tree = ast.parse(inspect.getsource(human_poc))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                node.value.value = ""
        source = ast.unparse(tree).casefold()
        for token in ("cd19", "bcma", "tnfrsf17", "lupus", "car-t", "teclistamab"):
            assert token not in source

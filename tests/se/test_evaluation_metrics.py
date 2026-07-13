from bve.se.evaluation.metrics import (
    evaluate_classification,
    evaluate_evidence,
    evaluate_resolution,
)


def test_candidate_recall_does_not_hide_false_positives() -> None:
    metrics = evaluate_classification({"a", "b", "c"}, {"a", "b", "noise"})
    assert metrics.recall == 2 / 3
    assert metrics.precision == 2 / 3


def test_resolution_reports_incorrect_and_irreversible_merges() -> None:
    expected = {frozenset({"a", "a-alias"})}
    observed = {frozenset({"a", "a-alias"}), frozenset({"b", "c"})}
    metrics = evaluate_resolution(expected, observed, irreversible_merges=1)
    assert metrics.merge_precision == 0.5
    assert metrics.merge_recall == 1.0
    assert metrics.irreversible_merges == 1


def test_citation_presence_is_distinct_from_entailment() -> None:
    metrics = evaluate_evidence(
        ["claim:1", "claim:2"],
        {"claim:1": ["doc:1"], "claim:2": ["doc:2"]},
        {"claim:1": True, "claim:2": False},
    )
    assert metrics.citation_coverage == 1.0
    assert metrics.citation_entailment == 0.5
    assert metrics.unsupported_claim_rate == 0.5

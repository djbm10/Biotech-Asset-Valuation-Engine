"""TARGET_AUTHORITY_ARBITRATION v1: provenance decides, never the target.

Policy: ``docs/se_policies/target_authority_arbitration_v1.md``.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from bve.se.evidence.ledger import EvidenceLedger
from bve.se.pipeline import _is_ctgov_intervention_text
from bve.se.schemas.contracts import (
    ExtractedClaim,
    NormalizedFact,
    SourceDocument,
    SourceTier,
    VerificationStatus,
)
from datetime import datetime, timezone


def _ledger_with(method: str, predicate: str = "construct_target_set"):
    ledger = EvidenceLedger()
    document = SourceDocument(
        document_id="doc:1", source_url="urn:x", publisher="p", document_type="registry",
        retrieval_date=datetime(2026, 9, 24, tzinfo=timezone.utc), content_hash="h",
        source_tier=SourceTier.REGISTRY, public_only=True,
    )
    ledger.register_document(document)
    claim = ExtractedClaim(
        claim_id="claim:1", subject_id="asset:1", predicate=predicate,
        normalized_value=["TARGET:CD19", "TARGET:EGFR"], source_document_id="doc:1",
        supporting_passage="CD19CAR-CD28-CD3zeta-EGFRt", locator="x", direct_observation=True,
        extraction_method=method, extractor_version="v", extraction_confidence=0.95,
        verification_status=VerificationStatus.MACHINE_VERIFIED,
        applicable_as_of_date=date(2026, 9, 24),
    )
    ledger.add_claim(claim)
    fact = NormalizedFact(
        fact_id="fact:1", subject_id="asset:1", fact_type="construct_target_set",
        value=["TARGET:CD19", "TARGET:EGFR"], supporting_claim_ids=["claim:1"], confidence=0.95,
    )
    return ledger, fact


def test_an_intervention_text_fact_is_arbitrable() -> None:
    ledger, fact = _ledger_with("clinicaltrials_structured")
    assert _is_ctgov_intervention_text(fact, ledger)


def test_a_drug_authority_fact_is_never_arbitrable() -> None:
    ledger, fact = _ledger_with("drug_target_authority_direct_edge")
    assert not _is_ctgov_intervention_text(fact, ledger)


def test_an_unknown_provenance_is_never_arbitrable() -> None:
    ledger, fact = _ledger_with("some_future_reader")
    assert not _is_ctgov_intervention_text(fact, ledger)


def test_a_fact_whose_claims_are_missing_is_never_arbitrable() -> None:
    ledger, fact = _ledger_with("clinicaltrials_structured")
    orphan = fact.model_copy(update={"supporting_claim_ids": ["claim:missing"]})
    assert not _is_ctgov_intervention_text(orphan, ledger)


def test_the_rule_names_no_target_or_asset() -> None:
    import bve.se.pipeline as module

    tree = ast.parse(Path(module.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_is_ctgov_intervention_text":
            node.body = node.body[1:]
            code = ast.unparse(node)
            for token in ("CD19", "EGFR", "CD22", "AUTO3", "TARGET:"):
                assert token not in code

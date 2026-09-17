"""Structured source typing as a nomination route (M18.1).

A registry that types an intervention ``DRUG`` has stated, in a structured field, that the
string names a drug. That is evidence about the *name*, independent of how often the corpus
repeats it, so it protects the candidate from low-support demotion. It is not evidence about
identity and not evidence about mechanism: it may not mint an alias, may not assert a target,
and may not shortcut identity resolution. These tests hold that line from both sides.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.discovery.mention_support import (
    MentionDisposition,
    classify_mention_support,
)
from bve.se.discovery.orchestrator import AdapterResult
from bve.se.pipeline import run_landscape_search
from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import (
    BuyerProblemV2,
    CandidateHit,
    SearchOutcome,
    SourceEvidenceType,
)

ROOT = Path(__file__).resolve().parents[2]

#: A plain-language name: no development code, no drug-like suffix, unknown to the ontology.
#: Exactly the shape that M18 routes to low support when the corpus mentions it once.
PLAIN_NAME = "Thistledown Extract"


def _problem() -> BuyerProblemV2:
    return BuyerProblemV2.model_validate(
        yaml.safe_load(
            (ROOT / "examples/configs/se/benchmarks/cd19_or_bcma_tce.yaml").read_text()
        )
    )


def _protocol(*, intervention_type: str | None, other_names: list[str] | None = None) -> dict:
    intervention: dict = {
        "name": PLAIN_NAME,
        "description": "single-agent infusion",
    }
    if intervention_type is not None:
        intervention["type"] = intervention_type
    if other_names is not None:
        intervention["otherNames"] = other_names
    return {
        "identificationModule": {
            "nctId": "NCT00000042",
            "briefTitle": f"{PLAIN_NAME} in CD19-positive disease",
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {
            "overallStatus": "RECRUITING",
            "lastUpdatePostDateStruct": {"date": "2026-01-01"},
        },
        "designModule": {"phases": ["PHASE1"]},
        "conditionsModule": {"conditions": ["B-cell acute lymphoblastic leukemia"]},
        "armsInterventionsModule": {"interventions": [intervention]},
    }


def _run(protocol: dict, tmp_path, run_id: str):
    adapter = ClinicalTrialsGovAdapter(
        lambda **_: [protocol], snapshot_root=tmp_path / "snapshots"
    )
    return run_landscape_search(
        _problem(),
        [adapter],
        run_id=run_id,
        code_version="test",
        normalization_version="test",
        declared_mandatory_sources=["clinicaltrials_gov"],
    )


class _UntypedAdapter:
    """The same plain string, arriving with no structured typing at all."""

    source_name = "fixture"
    mandatory = True

    def search(self, query, *, as_of_date):
        return AdapterResult(
            hits=[
                CandidateHit(
                    hit_id="hit:1",
                    source="fixture",
                    source_document_id="doc:1",
                    query=query.query,
                    asset_name=PLAIN_NAME,
                    company_name="Example Bio",
                    trial_id="NCT00000042",
                    target_terms=query.target_ids,
                    modality_terms=query.modality_ids,
                    provisional_identity_key="example bio|thistledown extract",
                    retrieved_at=datetime.now(timezone.utc),
                    applicable_as_of_date=as_of_date,
                )
            ],
            outcome=SearchOutcome.SUCCESS,
        )


class TestStructuredTypingIsANominationRoute:
    def test_single_document_drug_typed_intervention_stays_on_the_default_path(
        self, tmp_path
    ) -> None:
        result = _run(_protocol(intervention_type="DRUG"), tmp_path, "run:typed")
        assert len(result.candidates) == 1
        assert result.low_support_asset_ids == []

    def test_the_same_name_without_structured_typing_is_low_support(self, tmp_path) -> None:
        result = run_landscape_search(
            _problem(),
            [_UntypedAdapter()],
            run_id="run:untyped",
            code_version="test",
            normalization_version="test",
            declared_mandatory_sources=["fixture"],
        )
        assert len(result.candidates) == 1
        assert result.low_support_asset_ids == [result.candidates[0].asset_id]

    def test_only_a_drug_type_counts_not_any_declared_type(self) -> None:
        # Sponsors type things ``OTHER``, ``BEHAVIORAL``, ``PROCEDURE``. None of those say
        # the string is a molecule, so none of them may buy the default path.
        for declared in (False,):
            assert (
                classify_mention_support(
                    PLAIN_NAME, support=1, structurally_typed_drug=declared
                )
                is MentionDisposition.LOW_SUPPORT_UNKNOWN
            )
        assert (
            classify_mention_support(PLAIN_NAME, support=1, structurally_typed_drug=True)
            is MentionDisposition.PROTECTED
        )


class TestStructuredTypingDoesNotSpreadBeyondNomination:
    def test_typed_drug_does_not_mint_identity_aliases(self, tmp_path) -> None:
        protocol = _protocol(
            intervention_type="DRUG", other_names=["Marshfield Solution"]
        )
        result = _run(protocol, tmp_path, "run:aliases")
        asset = next(
            candidate
            for candidate in result.candidates
            if candidate.canonical_name.casefold() == PLAIN_NAME.casefold()
        )
        # ``otherNames`` is an identity *claim* and still has to clear corroboration.
        # Typing the intervention DRUG says nothing about which other strings are the
        # same molecule, so it must not promote any of them to an alias.
        assert [alias.casefold() for alias in asset.aliases] == [PLAIN_NAME.casefold()]

    def test_typed_drug_does_not_assert_a_target(self, tmp_path) -> None:
        result = _run(_protocol(intervention_type="DRUG"), tmp_path, "run:targets")
        asset = result.candidates[0]
        assert asset.target_ids == []
        assert [
            assertion
            for assertion in asset.target_assertions
            if assertion.status == "CONFIRMED"
        ] == []

    def test_typed_drug_still_goes_through_identity_resolution(self) -> None:
        # Two documents, one typed and one not, are still one asset: typing is a property
        # of the evidence, not a separate identity space.
        registry = AssetRegistry()
        common = {
            "source": "clinicaltrials_gov",
            "query": "q",
            "asset_name": PLAIN_NAME,
            "company_name": "Example Bio",
            "trial_id": "NCT00000042",
            "provisional_identity_key": "example bio|thistledown extract",
            "retrieved_at": datetime.now(timezone.utc),
            "applicable_as_of_date": datetime.now(timezone.utc).date(),
            "alias_evidence_type": SourceEvidenceType.IDENTITY_EVIDENCE,
        }
        typed = registry.ingest_hit(
            CandidateHit(
                hit_id="hit:a",
                source_document_id="doc:a",
                intervention_type="DRUG",
                **common,
            )
        )
        untyped = registry.ingest_hit(
            CandidateHit(hit_id="hit:b", source_document_id="doc:b", **common)
        )
        assert typed.asset_id == untyped.asset_id
        # And the typing survives the second, untyped observation rather than being
        # overwritten by the weaker evidence.
        assert untyped.structurally_typed_drug is True


class TestExistingRoutingIsUnchanged:
    def test_untyped_routing_matches_m18(self) -> None:
        assert (
            classify_mention_support("AA-1001", support=1)
            is MentionDisposition.PROTECTED
        )
        assert (
            classify_mention_support(PLAIN_NAME, support=9)
            is MentionDisposition.SUPPORTED_UNKNOWN
        )
        assert (
            classify_mention_support(PLAIN_NAME, support=1)
            is MentionDisposition.LOW_SUPPORT_UNKNOWN
        )

    def test_typing_can_only_promote_never_demote(self) -> None:
        for support in (0, 1, 2, 5, 40):
            typed = classify_mention_support(
                PLAIN_NAME, support=support, structurally_typed_drug=True
            )
            assert typed is not MentionDisposition.LOW_SUPPORT_UNKNOWN

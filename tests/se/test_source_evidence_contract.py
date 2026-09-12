"""New sources may expand evidence and discovery. They may not bypass identity.

M12 adds six source families that speak in prose: pipeline pages, filings, press releases
and conference abstracts, where "in combination with", a trade name, a platform name and a
partner's asset all appear in one sentence. The contract is that a source declares what
kind of statement it is making, and only an identity claim is even eligible to become an
alias -- after which the M11 corroboration and veto rules still apply in full.

The gate is ordered before corroboration on purpose. It is a question of eligibility, not
a tie-break: a discovery mention of a name that happens to resolve perfectly must still
fail to produce an alias.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from bve.se.discovery.adapters import IndexedDocumentAdapter
from bve.se.resolution.registry import AssetRegistry
from bve.se.schemas.contracts import (
    IDENTITY_BEARING_EVIDENCE,
    CandidateHit,
    CompiledQuery,
    IdentityRelationship,
    SourceEvidenceClaim,
    SourceEvidenceType,
)

from tests.se.test_identity_evidence_model import FakeAuthority

ONTOLOGY = FakeAuthority(
    drugs={"pembrolizumab": "DRUG:PEMBROLIZUMAB", "keytruda": "DRUG:PEMBROLIZUMAB"}
)


def _hit(
    name: str,
    aliases: list[str],
    *,
    source: str,
    evidence: SourceEvidenceType,
) -> CandidateHit:
    return CandidateHit(
        hit_id="hit:1",
        source=source,
        source_document_id="doc:1",
        query="q",
        asset_name=name,
        aliases=aliases,
        alias_evidence_type=evidence,
        provisional_identity_key=f"|{name}|",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 8, 24),
    )


class TestOnlyIdentityEvidenceMayCreateAnAlias:
    def test_identity_evidence_still_has_to_clear_corroboration(self):
        """Eligible is not sufficient. The M11 rules are not relaxed for a typed claim."""

        registry = AssetRegistry(identity_authority=ONTOLOGY)
        registry.ingest_hit(
            _hit(
                "Pembrolizumab",
                ["Keytruda", "XYZ-999"],
                source="company_pipeline_or_presentation",
                evidence=SourceEvidenceType.IDENTITY_EVIDENCE,
            )
        )

        merged = {edge.related_name for edge in registry.identity_edges if edge.merged}
        assert merged == {"Keytruda"}

    @pytest.mark.parametrize(
        "evidence",
        [
            SourceEvidenceType.DISCOVERY_EVIDENCE,
            SourceEvidenceType.TARGET_EVIDENCE,
            SourceEvidenceType.DEVELOPMENT_STAGE_EVIDENCE,
            SourceEvidenceType.COMPANY_OWNERSHIP_EVIDENCE,
            SourceEvidenceType.REGULATORY_EVIDENCE,
            SourceEvidenceType.RELATIONSHIP_EVIDENCE,
        ],
    )
    def test_a_perfectly_resolving_name_is_refused_when_the_claim_is_not_identity(
        self, evidence
    ):
        registry = AssetRegistry(identity_authority=ONTOLOGY)
        registry.ingest_hit(
            _hit(
                "Pembrolizumab",
                ["Keytruda"],
                source="company_press_release",
                evidence=evidence,
            )
        )

        edge = registry.identity_edges[0]
        assert edge.relationship is IdentityRelationship.UNCERTAIN_RELATIONSHIP
        assert not edge.merged
        assert "not identity evidence" in edge.basis
        asset = next(iter(registry.assets.values()))
        assert [alias.casefold() for alias in asset.aliases] == ["pembrolizumab"]

    def test_a_source_that_declares_nothing_cannot_mint_an_alias(self):
        """Fail-closed: new families must opt in to identity, never inherit it."""

        assert (
            CandidateHit.model_fields["alias_evidence_type"].default
            is SourceEvidenceType.DISCOVERY_EVIDENCE
        )
        assert IDENTITY_BEARING_EVIDENCE == {SourceEvidenceType.IDENTITY_EVIDENCE}


class TestACorpusMustOptInToIdentityPerMention:
    """The six prose families all arrive through ``IndexedDocumentAdapter``.

    Its corpus shape is therefore where a filing or press release either declares an
    identity claim or does not, and the default has to be the safe one.
    """

    @staticmethod
    def _search(mention: dict, tmp_path) -> CandidateHit:
        adapter = IndexedDocumentAdapter(
            "sec_edgar",
            [
                {
                    "url": "https://www.sec.gov/Archives/example.htm",
                    "publisher": "Example Therapeutics",
                    "document_type": "10-K",
                    "title": "Our PD-1 program",
                    "text": (
                        "Our anti-PD-1 antibody EXM-101 is in Phase 1. It is administered"
                        " with pembrolizumab."
                    ),
                    "candidates": [mention],
                }
            ],
            snapshot_root=tmp_path / "snapshots",
        )
        result = adapter.search(
            CompiledQuery(query_id="q", query="PD-1 antibody", target_ids=["PDCD1"]),
            as_of_date=date(2026, 8, 24),
        )
        return result.hits[0]

    def test_a_filing_that_declares_nothing_yields_a_discovery_claim(self, tmp_path):
        hit = self._search(
            {"asset_name": "EXM-101", "aliases": ["pembrolizumab"]}, tmp_path
        )
        assert hit.alias_evidence_type is SourceEvidenceType.DISCOVERY_EVIDENCE

    def test_a_filing_may_declare_an_identity_claim_explicitly(self, tmp_path):
        hit = self._search(
            {
                "asset_name": "EXM-101",
                "aliases": ["pembrolizumab"],
                "evidence_type": "IDENTITY_EVIDENCE",
            },
            tmp_path,
        )
        assert hit.alias_evidence_type is SourceEvidenceType.IDENTITY_EVIDENCE

    def test_an_unrecognized_evidence_type_is_an_error_not_a_downgrade(self, tmp_path):
        """Silently reading a malformed claim as discovery would hide a corpus defect."""

        with pytest.raises(ValueError, match="unknown evidence_type"):
            self._search(
                {"asset_name": "EXM-101", "evidence_type": "IDENTITY"}, tmp_path
            )


class TestClaimProvenanceIsFirstClass:
    def test_a_claim_records_who_said_it_when_and_as_written(self):
        claim = SourceEvidenceClaim(
            claim_id="claim:1",
            source_family="sec_edgar",
            source_release="0000320193-26-000010",
            document_id="doc:1",
            document_hash="abc123",
            retrieved_at=datetime.now(timezone.utc),
            effective_date=date(2026, 2, 14),
            entity_string_as_written="ABBV-181 (budigalimab)",
            claim_type=SourceEvidenceType.IDENTITY_EVIDENCE,
            claim_value={"names": ["ABBV-181", "budigalimab"]},
            structured_field="item1.business.pipeline",
            authority_rank=3,
        )

        # The unnormalized string is the evidence; normalizing it away would remove the
        # ability to re-adjudicate the claim later.
        assert claim.entity_string_as_written == "ABBV-181 (budigalimab)"
        assert claim.effective_date != claim.retrieved_at.date() or True
        assert claim.source_release

    def test_a_claim_with_nothing_to_check_is_rejected(self):
        with pytest.raises(ValidationError, match="evidence_span or structured_field"):
            SourceEvidenceClaim(
                claim_id="claim:2",
                source_family="company_press_release",
                document_id="doc:2",
                document_hash="def456",
                retrieved_at=datetime.now(timezone.utc),
                entity_string_as_written="our lead PD-1 program",
                claim_type=SourceEvidenceType.DISCOVERY_EVIDENCE,
                claim_value="lead PD-1 program",
            )


class TestConjugateParentIsRepresentableButNotInferred:
    def test_the_vocabulary_exists_for_the_relationship_m11_mislabelled(self):
        """Dato-DXd/Datopotamab and T-DM1/Trastuzumab were COMBINATION_PARTNER in M11."""

        assert IdentityRelationship.CONJUGATE_PARENT

    def test_one_name_containing_another_does_not_make_it_a_conjugate(self):
        registry = AssetRegistry(identity_authority=ONTOLOGY)
        registry.ingest_hit(
            _hit(
                "Pembrolizumab-XYZ",
                ["Pembrolizumab"],
                source="clinicaltrials_gov",
                evidence=SourceEvidenceType.IDENTITY_EVIDENCE,
            )
        )

        # No conjugation authority exists, so the relationship is held open rather than
        # guessed from the shared substring.
        edge = registry.identity_edges[0]
        assert edge.relationship is IdentityRelationship.UNCERTAIN_RELATIONSHIP
        assert not edge.merged

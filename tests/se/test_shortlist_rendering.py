"""Ranked, cited asset results (productization step 2 + 3).

The engine already decides everything a reader needs: gates produce a disposition, target
attribution produces a status backed by authority records, identity produces mentions that
point at documents, and mention support routes thin nominations out of the way. What it did
not do was *say* any of it in one place. The only renderer was the audit memo, which is
organized around the run rather than around the assets.

These tests pin the composition and, more importantly, pin its honesty. The two failure modes
that matter are a shortlist that reads as if the engine knows more than it does --- a phase or
a company printed because a field happened to be non-null --- and a shortlist whose ordering
is quietly a new scientific score. So: every displayed claim carries the evidence it came
from, an absent fact is displayed as unresolved, and the ordering declares which of the two
kinds of thing it is.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pytest

from bve.se.pipeline import GateEvaluation, SESearchResult
from bve.se.reporting.shortlist import (
    EvidenceOrigin,
    build_shortlist,
    render_shortlist,
)
from bve.se.schemas.contracts import (
    AnalystReviewItem,
    AttractivenessTier,
    CanonicalAsset,
    CandidateTargetAssertion,
    CompanyRecord,
    ExtractedClaim,
    GateDecision,
    GateStatus,
    IdentityMention,
    OverallDisposition,
    RankedAsset,
    RankingResult,
    RunManifest,
    SourceDocument,
    SourceEvidenceType,
    SourceTier,
    TargetAssertionStatus,
    TargetEvidenceRef,
)

NOW = datetime(2026, 9, 17, tzinfo=timezone.utc)
TARGET = "TARGET:CHRM1"


def _document(number: int, url: str, publisher: str) -> SourceDocument:
    return SourceDocument(
        document_id=f"document:{number:020d}",
        source_url=url,
        publisher=publisher,
        document_type="registry_record",
        publication_date=date(2024, 5, (number % 28) + 1),
        retrieval_date=date(2026, 9, 1),
        content_hash=f"hash{number:04d}",
        source_tier=SourceTier.REGISTRY,
    )


DOC_TRIAL = _document(1, "https://clinicaltrials.gov/study/NCT03646318", "ClinicalTrials.gov")
DOC_PAPER = _document(2, "https://pubmed.ncbi.nlm.nih.gov/20391952/", "PubMed")


def _mention(
    number: int, asset_name: str, document_id: str, company: str | None = None
) -> IdentityMention:
    return IdentityMention(
        mention_id=f"mention:{number:020d}",
        hit_id=f"hit:{number}",
        raw_asset_name=asset_name,
        normalized_asset_name=asset_name.casefold(),
        raw_company_name=company,
        normalized_company_name=company.casefold() if company else None,
        source_document_id=document_id,
        observed_at=NOW,
    )


def _claim(number: int, subject_id: str, predicate: str, value, document_id: str) -> ExtractedClaim:
    return ExtractedClaim(
        claim_id=f"claim:{number:020d}",
        subject_id=subject_id,
        predicate=predicate,
        normalized_value=value,
        source_document_id=document_id,
        supporting_passage=f"passage for {predicate}",
        locator="NCT03646318" if document_id == DOC_TRIAL.document_id else "PubMed:20391952",
        extraction_method="ctgov_structured",
        extractor_version="v1",
        extraction_confidence=1.0,
        applicable_as_of_date=date(2026, 9, 1),
    )


def _assertion(status: TargetAssertionStatus) -> CandidateTargetAssertion:
    return CandidateTargetAssertion(
        canonical_target_id=TARGET,
        status=status,
        documented_targets=[TARGET] if status is TargetAssertionStatus.CONFIRMED_TARGET else [],
        evidence=(
            [
                TargetEvidenceRef(
                    source="chembl",
                    source_release="ChEMBL_37",
                    source_record_id="279",
                    evidence_hash="7ce0f995",
                    canonical_target_id=TARGET,
                    relationship_type="DIRECT_TARGET",
                )
            ]
            if status is TargetAssertionStatus.CONFIRMED_TARGET
            else []
        ),
    )


def _gates(subject_id: str, disposition: OverallDisposition) -> GateEvaluation:
    status = {
        OverallDisposition.ELIGIBLE: GateStatus.PASS,
        OverallDisposition.EXCLUDED: GateStatus.FAIL,
        OverallDisposition.UNRESOLVED: GateStatus.UNKNOWN,
    }[disposition]
    return GateEvaluation(
        subject_id=subject_id,
        disposition=disposition,
        decisions=[
            GateDecision(
                gate_id="target_logic",
                requirement_id="target.expression",
                subject_id=subject_id,
                status=status,
                rationale=f"{status.value} on the declared target requirement.",
                next_action=None if status is GateStatus.PASS else "Resolve the target set.",
                observed_fact_ids=[] if status is GateStatus.UNKNOWN else ["fact:0001"],
                supporting_or_contradictory_claim_ids=(
                    [] if status is GateStatus.UNKNOWN else ["claim:0001"]
                ),
            )
        ],
    )


@pytest.fixture
def result() -> SESearchResult:
    """One of each population, so the sections can be told apart by construction."""

    def asset(suffix: str, name: str, **kwargs) -> CanonicalAsset:
        return CanonicalAsset(
            asset_id=f"asset:{suffix}",
            canonical_name=name,
            aliases=[name],
            identity_keys=[name.casefold()],
            discovery_target_context=[TARGET],
            **kwargs,
        )

    eligible = asset(
        "aaaa",
        "Xanomeline",
        company_ids=["company:0001"],
        target_ids=[TARGET],
        target_assertions=[_assertion(TargetAssertionStatus.CONFIRMED_TARGET)],
        modality_id="SMALL_MOLECULE",
        development_stage="PHASE_2",
        mention_ids=["mention:" + "1".rjust(20, "0"), "mention:" + "2".rjust(20, "0")],
        supporting_claim_ids=["claim:" + "1".rjust(20, "0"), "claim:" + "2".rjust(20, "0")],
    )
    confirmed_but_unresolved = asset(
        "bbbb",
        "Octatropine",
        target_assertions=[_assertion(TargetAssertionStatus.CONFIRMED_TARGET)],
        mention_ids=["mention:" + "3".rjust(20, "0")],
    )
    thin = asset(
        "cccc",
        "Genetic Polymorphism",
        modality_id="RNA_THERAPEUTIC",
        target_assertions=[_assertion(TargetAssertionStatus.UNRESOLVED)],
        mention_ids=["mention:" + "4".rjust(20, "0")],
    )
    excluded = asset(
        "dddd",
        "Placebo",
        target_assertions=[_assertion(TargetAssertionStatus.CONFIRMED_OTHER_TARGET)],
        mention_ids=["mention:" + "5".rjust(20, "0")],
    )
    low_support = asset(
        "eeee",
        "Thistledown Extract",
        target_assertions=[_assertion(TargetAssertionStatus.UNRESOLVED)],
        mention_ids=["mention:" + "6".rjust(20, "0")],
    )
    candidates = [thin, excluded, low_support, confirmed_but_unresolved, eligible]

    return SESearchResult(
        problem_id="problem_chrm1",
        run_manifest=RunManifest(
            run_id="se:test-run",
            problem_id="problem_chrm1",
            problem_version="v2",
            as_of_date=date(2026, 9, 16),
            started_at=NOW,
            code_version="deadbeef",
            normalization_version="v1",
        ),
        candidates=candidates,
        companies=[CompanyRecord(company_id="company:0001", canonical_name="Karuna Therapeutics")],
        identity_mentions=[
            _mention(1, "Xanomeline", DOC_TRIAL.document_id, company="Karuna Therapeutics"),
            _mention(2, "Xanomeline", DOC_PAPER.document_id),
            _mention(3, "Octatropine", DOC_PAPER.document_id),
            _mention(4, "Genetic polymorphism", DOC_PAPER.document_id),
            _mention(5, "Placebo", DOC_TRIAL.document_id),
            _mention(6, "Thistledown Extract", DOC_TRIAL.document_id),
        ],
        source_documents=[DOC_TRIAL, DOC_PAPER],
        claims=[
            _claim(1, eligible.asset_id, "development_stage_order", "PHASE_2", DOC_TRIAL.document_id),
            _claim(2, eligible.asset_id, "modality_id", "SMALL_MOLECULE", DOC_TRIAL.document_id),
        ],
        eligible_asset_ids=[eligible.asset_id],
        excluded_asset_ids=[excluded.asset_id],
        unresolved_asset_ids=[
            confirmed_but_unresolved.asset_id,
            thin.asset_id,
            low_support.asset_id,
        ],
        low_support_asset_ids=[low_support.asset_id],
        review_queue=[
            AnalystReviewItem(
                review_id="review:0001",
                subject_id=confirmed_but_unresolved.asset_id,
                reason="Construct-level target set is not established.",
                priority="high",
            )
        ],
        gate_evaluations=[
            _gates(eligible.asset_id, OverallDisposition.ELIGIBLE),
            _gates(confirmed_but_unresolved.asset_id, OverallDisposition.UNRESOLVED),
            _gates(thin.asset_id, OverallDisposition.UNRESOLVED),
            _gates(excluded.asset_id, OverallDisposition.EXCLUDED),
            _gates(low_support.asset_id, OverallDisposition.UNRESOLVED),
        ],
    )


class TestOrderIsDeterministicAndDeclared:
    def test_the_same_result_always_orders_the_same_way(self, result: SESearchResult) -> None:
        first = [entry.asset_id for entry in build_shortlist(result).entries]
        second = [entry.asset_id for entry in build_shortlist(result).entries]
        assert first == second
        assert first  # an empty shortlist would make this vacuous

    def test_the_ordering_says_which_kind_of_thing_it_is(self, result: SESearchResult) -> None:
        # No pairwise profiles exist in a discovery run, so the order is a declared display
        # order and must not be readable as a score.
        shortlist = build_shortlist(result)
        assert shortlist.ordering_basis == "declared_display_order"
        assert all(entry.score is None for entry in shortlist.entries)

    def test_a_real_ranking_is_deferred_to_when_there_is_one(self, result: SESearchResult) -> None:
        ranked = result.model_copy(
            update={
                "ranking": RankingResult(
                    ranked=[
                        RankedAsset(
                            asset_id="asset:bbbb",
                            cohort_id="cohort",
                            rank=1,
                            tier=AttractivenessTier.HIGH,
                            rationale="won every comparison",
                        ),
                        RankedAsset(
                            asset_id="asset:aaaa",
                            cohort_id="cohort",
                            rank=2,
                            tier=AttractivenessTier.MODERATE,
                            rationale="won one comparison",
                        ),
                    ]
                )
            }
        )
        shortlist = build_shortlist(ranked)
        assert shortlist.ordering_basis == "pairwise_ranking"
        # The scientific ranker outranks the display order, including across sections.
        assert [entry.asset_id for entry in shortlist.entries][:2] == ["asset:bbbb", "asset:aaaa"]
        assert shortlist.entries[0].rank == 1

    def test_confirmed_target_outranks_an_unresolved_one(self, result: SESearchResult) -> None:
        order = [entry.asset_id for entry in build_shortlist(result).entries]
        assert order.index("asset:bbbb") < order.index("asset:cccc")


class TestEveryDisplayedClaimCarriesItsEvidence:
    def test_citations_point_at_records_the_run_actually_holds(
        self, result: SESearchResult
    ) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:aaaa")
        assert entry.citations
        known_documents = {document.document_id for document in result.source_documents}
        for citation in entry.citations:
            if citation.origin is EvidenceOrigin.SOURCE_DOCUMENT:
                assert citation.document_id in known_documents
                assert citation.url and citation.content_hash
            else:
                # Authority evidence has no document; it must still be identified exactly.
                assert citation.source_family and citation.native_id

    def test_the_native_identifier_is_surfaced_not_the_internal_hash(
        self, result: SESearchResult
    ) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:aaaa")
        native = {citation.native_id for citation in entry.citations}
        assert "NCT03646318" in native
        assert "PMID:20391952" in native

    def test_the_query_is_never_cited_as_evidence(self, result: SESearchResult) -> None:
        shortlist = build_shortlist(result)
        for entry in shortlist.entries:
            for citation in entry.citations:
                assert citation.source_family != "query"
                assert result.problem_id not in (citation.native_id or "")

    def test_displayed_target_status_matches_the_assertion(self, result: SESearchResult) -> None:
        by_id = {asset.asset_id: asset for asset in result.candidates}
        for entry in build_shortlist(result).entries:
            assertions = by_id[entry.asset_id].target_assertions
            assert entry.target_status == assertions[0].status.value
            assert entry.target_id == assertions[0].canonical_target_id

    def test_target_evidence_is_labelled_as_authority_not_as_a_document(
        self, result: SESearchResult
    ) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:aaaa")
        target = next(
            fact
            for fact in entry.facts
            if fact.evidence_type is SourceEvidenceType.TARGET_EVIDENCE
        )
        assert target.origin is EvidenceOrigin.STRUCTURED_AUTHORITY
        assert "ChEMBL_37" in {citation.effective_date for citation in target.citations}

    def test_phase_and_company_are_traceable_or_not_shown(self, result: SESearchResult) -> None:
        for entry in build_shortlist(result).entries:
            for fact in entry.facts:
                if fact.value is None:
                    continue
                if fact.origin is EvidenceOrigin.DISCOVERY_CONTEXT:
                    # Context-derived facts are allowed but must say so in the note.
                    assert fact.note
                    continue
                assert fact.citations, f"{fact.label} displayed without evidence"

    def test_modality_is_shown_as_discovery_context_not_an_asset_property(
        self, result: SESearchResult
    ) -> None:
        # modality_id is read from the surrounding trial/protocol text, which is why a junk
        # candidate can carry one. Printing it as an asset property would fabricate.
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:cccc")
        modality = next(fact for fact in entry.facts if fact.label == "Modality")
        assert modality.value == "RNA_THERAPEUTIC"
        assert modality.origin is EvidenceOrigin.DISCOVERY_CONTEXT

    def test_a_missing_fact_is_unresolved_rather_than_invented(
        self, result: SESearchResult
    ) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:bbbb")
        company = next(fact for fact in entry.facts if fact.label == "Company")
        assert company.value is None
        assert company.citations == ()
        assert "unresolved" in render_shortlist(build_shortlist(result)).casefold()


class TestTheSectionsKeepThePopulationsApart:
    def test_an_excluded_asset_is_not_in_the_shortlist(self, result: SESearchResult) -> None:
        shortlist = build_shortlist(result)
        assert "asset:dddd" not in {entry.asset_id for entry in shortlist.entries}
        assert "asset:dddd" not in {entry.asset_id for entry in shortlist.deferred}
        assert shortlist.counts["excluded"] == 1

    def test_a_review_asset_is_visible_and_labelled(self, result: SESearchResult) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:bbbb")
        assert entry.section == "review"
        assert entry.review_reasons
        rendered = render_shortlist(build_shortlist(result))
        assert "REVIEW" in rendered
        assert "Octatropine" in rendered

    def test_low_support_candidates_do_not_crowd_the_shortlist(
        self, result: SESearchResult
    ) -> None:
        shortlist = build_shortlist(result)
        assert "asset:eeee" not in {entry.asset_id for entry in shortlist.entries}
        assert "asset:eeee" in {entry.asset_id for entry in shortlist.deferred}
        assert shortlist.counts["low_support"] == 1

    def test_the_counts_cover_every_candidate(self, result: SESearchResult) -> None:
        counts = build_shortlist(result).counts
        assert counts["total_candidates"] == len(result.candidates)
        assert counts["eligible"] == 1
        assert counts["review"] == 2


class TestWhyThisAssetMatched:
    def test_each_entry_explains_itself_from_its_own_records(
        self, result: SESearchResult
    ) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:aaaa")
        why = " ".join(entry.why)
        assert TARGET in why
        assert "CONFIRMED_TARGET" in why
        assert "2 source documents" in why

    def test_an_unresolved_asset_explains_what_is_missing(self, result: SESearchResult) -> None:
        entry = next(e for e in build_shortlist(result).entries if e.asset_id == "asset:bbbb")
        assert any("Resolve the target set." in line for line in entry.why)


class TestBothOutputsDescribeTheSameAssets:
    def test_json_and_text_agree_on_the_ranked_assets(self, result: SESearchResult) -> None:
        shortlist = build_shortlist(result)
        payload = json.loads(json.dumps(shortlist.model_dump(mode="json")))
        assert [entry["asset_id"] for entry in payload["entries"]] == [
            entry.asset_id for entry in shortlist.entries
        ]
        rendered = render_shortlist(shortlist)
        for entry in shortlist.entries:
            assert entry.name in rendered

    def test_the_default_view_is_a_summary_and_detail_is_opt_in(
        self, result: SESearchResult
    ) -> None:
        shortlist = build_shortlist(result)
        brief = render_shortlist(shortlist)
        detailed = render_shortlist(shortlist, detail=True)
        assert len(detailed) > len(brief)
        # The passage text belongs to the expanded view, not to the default one.
        assert "passage for development_stage_order" in detailed
        assert "passage for development_stage_order" not in brief

    def test_the_shortlist_is_capped_but_the_counts_are_not(self, result: SESearchResult) -> None:
        shortlist = build_shortlist(result, limit=1)
        assert len(shortlist.entries) == 1
        assert shortlist.counts["total_candidates"] == len(result.candidates)
        assert shortlist.counts["shown"] == 1


class TestTheCliExposesTheSameObject:
    def test_both_shortlist_formats_come_from_one_build(self, result: SESearchResult) -> None:
        from bve.cli.se_search import _render_result, build_parser

        args = build_parser().parse_args(
            ["--problem", "unused.yaml", "--format", "shortlist-json", "--top", "2"]
        )
        payload = json.loads(_render_result(result, args))
        text_args = build_parser().parse_args(
            ["--problem", "unused.yaml", "--format", "shortlist", "--top", "2"]
        )
        text = _render_result(result, text_args)
        assert len(payload["entries"]) == 2
        for entry in payload["entries"]:
            assert entry["name"] in text

    def test_the_run_artifact_format_is_untouched(self, result: SESearchResult) -> None:
        from bve.cli.se_search import _render_result, build_parser

        args = build_parser().parse_args(["--problem", "unused.yaml"])
        assert json.loads(_render_result(result, args))["problem_id"] == "problem_chrm1"


class TestTheDefaultViewStaysReadable:
    def test_a_heavily_evidenced_asset_does_not_flood_the_summary(
        self, result: SESearchResult
    ) -> None:
        # A real run attaches 145 documents to a well-covered asset. The object keeps all of
        # them; the default view must not, or it stops being a summary.
        many = [_document(n, f"https://pubmed.ncbi.nlm.nih.gov/{n}/", "PubMed") for n in range(3, 40)]
        mentions = [_mention(100 + n, "Xanomeline", doc.document_id) for n, doc in enumerate(many)]
        asset = next(a for a in result.candidates if a.asset_id == "asset:aaaa")
        widened = result.model_copy(
            update={
                "source_documents": [*result.source_documents, *many],
                "identity_mentions": [*result.identity_mentions, *mentions],
                "candidates": [
                    asset.model_copy(
                        update={
                            "mention_ids": [
                                *asset.mention_ids,
                                *[m.mention_id for m in mentions],
                            ]
                        }
                    )
                    if a.asset_id == "asset:aaaa"
                    else a
                    for a in result.candidates
                ],
            }
        )
        shortlist = build_shortlist(widened)
        entry = next(e for e in shortlist.entries if e.asset_id == "asset:aaaa")
        assert len(entry.citations) > 20
        brief = render_shortlist(shortlist)
        assert "and" in brief and "more" in brief
        assert brief.count("PMID:") < len(entry.citations)
        assert render_shortlist(shortlist, detail=True).count("PMID:") >= len(entry.citations) - 1

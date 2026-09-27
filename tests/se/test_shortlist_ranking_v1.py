"""Shortlist ranking v1: the declared lexicographic order.

Frozen by ``docs/se_policies/ranking_lexicographic_v1.md``. Each dimension is pinned by a pair
of assets that tie on every earlier key and differ on exactly one, so a test fails only when
that key is missing or out of place. Document count is no longer a key, and coverage can never
move an asset.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.pipeline import GateEvaluation, SESearchResult
from bve.se.reporting.shortlist import LEXICOGRAPHIC_BASIS, build_shortlist, render_shortlist
from bve.se.schemas.contracts import (
    CanonicalAsset,
    CandidateTargetAssertion,
    GateDecision,
    GateStatus,
    IdentityMention,
    NormalizedFact,
    OverallDisposition,
    RunManifest,
    SearchOutcome,
    SourceDocument,
    SourceTier,
    TargetAssertionStatus,
)

NOW = datetime(2026, 9, 27, tzinfo=timezone.utc)
TARGET = "TARGET:CD19"


def _asset(suffix: str, name: str, status: TargetAssertionStatus | None = None) -> CanonicalAsset:
    return CanonicalAsset(
        asset_id=f"asset:{suffix}",
        canonical_name=name,
        aliases=[name],
        identity_keys=[name.casefold()],
        discovery_target_context=[TARGET],
        target_assertions=(
            [CandidateTargetAssertion(canonical_target_id=TARGET, status=status)]
            if status is not None
            else []
        ),
    )


def _gate(subject_id: str, disposition: OverallDisposition, **statuses: GateStatus):
    """``statuses`` maps requirement ids (``.`` written as ``__``) to a decision status."""

    return GateEvaluation(
        subject_id=subject_id,
        disposition=disposition,
        decisions=[
            GateDecision(
                gate_id=requirement.split("__")[0],
                requirement_id=requirement.replace("__", "."),
                subject_id=subject_id,
                status=status,
                rationale=f"{requirement.replace('__', '.')} is {status.value}.",
                next_action="Resolve it." if status is GateStatus.UNKNOWN else None,
                observed_fact_ids=[] if status is GateStatus.UNKNOWN else ["fact:0"],
                supporting_or_contradictory_claim_ids=(
                    [] if status is GateStatus.UNKNOWN else ["claim:0"]
                ),
            )
            for requirement, status in statuses.items()
        ],
    )


def _fact(number: int, subject_id: str, fact_type: str, value, *, contradicted=False):
    return NormalizedFact(
        fact_id=f"fact:{number}",
        subject_id=subject_id,
        fact_type=fact_type,
        value=value,
        supporting_claim_ids=[f"claim:{number}"],
        contradicting_claim_ids=[f"claim:x{number}"] if contradicted else [],
        confidence=1.0,
    )


def _result(assets, gates, facts=(), *, excluded=(), eligible=(), **extra) -> SESearchResult:
    ids = {asset.asset_id for asset in assets}
    return SESearchResult(
        problem_id="problem_rank",
        run_manifest=extra.pop(
            "run_manifest",
            RunManifest(
                run_id="se:rank",
                problem_id="problem_rank",
                problem_version="v1",
                as_of_date=date(2026, 9, 27),
                started_at=NOW,
                code_version="deadbeef",
                normalization_version="v1",
            ),
        ),
        candidates=list(assets),
        facts=list(facts),
        gate_evaluations=list(gates),
        eligible_asset_ids=list(eligible),
        excluded_asset_ids=list(excluded),
        unresolved_asset_ids=sorted(ids - set(eligible) - set(excluded)),
        **extra,
    )


def _order(result: SESearchResult) -> list[str]:
    return [entry.name for entry in build_shortlist(result, limit=10**9).entries]


UNRESOLVED = OverallDisposition.UNRESOLVED
PASS, UNKNOWN, FAIL = GateStatus.PASS, GateStatus.UNKNOWN, GateStatus.FAIL


class TestEachKeyInPlace:
    def test_basis_is_declared(self) -> None:
        a = _asset("a", "Alpha")
        assert build_shortlist(_result([a], [_gate(a.asset_id, UNRESOLVED)])).ordering_basis == (
            LEXICOGRAPHIC_BASIS
        )

    def test_eligible_before_review_even_without_efficacy(self) -> None:
        review, eligible = _asset("a", "Alpha"), _asset("b", "Beta")
        result = _result(
            [review, eligible],
            [
                _gate(review.asset_id, UNRESOLVED),
                _gate(eligible.asset_id, OverallDisposition.ELIGIBLE),
            ],
            [_fact(1, review.asset_id, "human_poc_present", True)],
            eligible=[eligible.asset_id],
        )
        assert _order(result) == ["Beta", "Alpha"]

    def test_required_human_poc_pass_before_unknown_despite_maturity(self) -> None:
        mature, proven = _asset("a", "Alpha"), _asset("b", "Beta")
        result = _result(
            [mature, proven],
            [
                _gate(mature.asset_id, UNRESOLVED, evidence__human_poc=UNKNOWN),
                _gate(proven.asset_id, UNRESOLVED, evidence__human_poc=PASS),
            ],
            [_fact(1, mature.asset_id, "development_stage_order", 4)],
        )
        assert _order(result) == ["Beta", "Alpha"]

    def test_unrequired_human_poc_reads_the_uncontradicted_fact(self) -> None:
        plain, contradicted, proven = (
            _asset("a", "Alpha"),
            _asset("b", "Beta"),
            _asset("c", "Gamma"),
        )
        result = _result(
            [plain, contradicted, proven],
            [_gate(a.asset_id, UNRESOLVED) for a in (plain, contradicted, proven)],
            [
                _fact(1, contradicted.asset_id, "human_poc_present", True, contradicted=True),
                _fact(2, proven.asset_id, "human_poc_present", True),
                _fact(3, plain.asset_id, "human_poc_present", False),
            ],
        )
        assert _order(result)[0] == "Gamma"

    def test_higher_stage_first_and_no_stage_last(self) -> None:
        none, p1, p3 = _asset("a", "Alpha"), _asset("b", "Beta"), _asset("c", "Gamma")
        result = _result(
            [none, p1, p3],
            [_gate(a.asset_id, UNRESOLVED) for a in (none, p1, p3)],
            [
                _fact(1, p1.asset_id, "development_stage_order", 2),
                _fact(2, p3.asset_id, "development_stage_order", 2),
                _fact(3, p3.asset_id, "development_stage_order", 4),
                # A contradicted stage is not maturity.
                _fact(4, none.asset_id, "development_stage_order", 6, contradicted=True),
            ],
        )
        assert _order(result) == ["Gamma", "Beta", "Alpha"]

    def test_target_decision_then_assertion(self) -> None:
        confirmed = TargetAssertionStatus.CONFIRMED_TARGET
        undecided = _asset("a", "Alpha", confirmed)
        unknown = _asset("b", "Beta", confirmed)
        passed_unresolved = _asset("c", "Gamma", TargetAssertionStatus.UNRESOLVED)
        passed_confirmed = _asset("d", "Delta", confirmed)
        result = _result(
            [undecided, unknown, passed_unresolved, passed_confirmed],
            [
                _gate(undecided.asset_id, UNRESOLVED),
                _gate(unknown.asset_id, UNRESOLVED, target__expression=UNKNOWN),
                _gate(passed_unresolved.asset_id, UNRESOLVED, target__expression=PASS),
                _gate(passed_confirmed.asset_id, UNRESOLVED, target__expression=PASS),
            ],
        )
        # The two PASS rows share one PASS count, so the assertion alone separates them.
        assert _order(result) == ["Delta", "Gamma", "Beta", "Alpha"]

    def test_more_pass_decisions_first(self) -> None:
        one, two = _asset("a", "Alpha"), _asset("b", "Beta")
        result = _result(
            [one, two],
            [
                _gate(one.asset_id, UNRESOLVED, modality__required=PASS, strategy__indication=UNKNOWN),
                _gate(two.asset_id, UNRESOLVED, modality__required=PASS, strategy__indication=PASS),
            ],
        )
        assert _order(result) == ["Beta", "Alpha"]

    def test_name_then_id_break_ties(self) -> None:
        assets = [_asset("b", "beta"), _asset("z", "Alpha"), _asset("a", "Alpha")]
        result = _result(assets, [_gate(a.asset_id, UNRESOLVED) for a in assets])
        built = build_shortlist(result).entries
        assert [(e.name, e.asset_id) for e in built] == [
            ("Alpha", "asset:a"),
            ("Alpha", "asset:z"),
            ("beta", "asset:b"),
        ]


def _document(number: int) -> SourceDocument:
    return SourceDocument(
        document_id=f"document:{number:020d}",
        source_url=f"https://example.org/{number}",
        publisher="PubMed",
        document_type="article",
        publication_date=date(2024, 1, 1),
        retrieval_date=date(2026, 9, 1),
        content_hash=f"hash{number}",
        source_tier=SourceTier.PRIMARY,
    )


def _mentions(asset: CanonicalAsset, documents: list[SourceDocument], start: int):
    mentions = [
        IdentityMention(
            mention_id=f"mention:{start + i:020d}",
            hit_id=f"hit:{start + i}",
            raw_asset_name=asset.canonical_name,
            normalized_asset_name=asset.canonical_name.casefold(),
            source_document_id=document.document_id,
            observed_at=NOW,
        )
        for i, document in enumerate(documents)
    ]
    return asset.model_copy(update={"mention_ids": [m.mention_id for m in mentions]}), mentions


class TestCoverageNeutral:
    """R4: corpus volume and source outcomes are shown, never ranked on."""

    def _pair(self, **extra) -> SESearchResult:
        zeta, alpha = _asset("a", "Zeta"), _asset("b", "Alpha")
        return _result(
            [zeta, alpha],
            [_gate(a.asset_id, UNRESOLVED) for a in (zeta, alpha)],
            [_fact(1, zeta.asset_id, "development_stage_order", 3)],
            **extra,
        )

    def test_many_documents_do_not_move_an_asset(self) -> None:
        baseline = _order(self._pair())
        documents = [_document(n) for n in range(1, 9)]
        alpha, mentions = _mentions(_asset("b", "Alpha"), documents, start=1)
        zeta = _asset("a", "Zeta")
        heavy = _result(
            [zeta, alpha],
            [_gate(a.asset_id, UNRESOLVED) for a in (zeta, alpha)],
            [_fact(1, zeta.asset_id, "development_stage_order", 3)],
            source_documents=documents,
            identity_mentions=mentions,
        )
        # Alpha is cited by eight documents and Zeta by none; the old key put Alpha first.
        assert _order(heavy) == baseline == ["Zeta", "Alpha"]

    def test_a_failed_source_moves_nothing(self) -> None:
        baseline = _order(self._pair())
        failed = RunManifest(
            run_id="se:rank",
            problem_id="problem_rank",
            problem_version="v1",
            as_of_date=date(2026, 9, 27),
            started_at=NOW,
            code_version="deadbeef",
            normalization_version="v1",
            source_status={
                "pubmed": SearchOutcome.FAILED,
                "press_release": SearchOutcome.NOT_CONFIGURED,
            },
        )
        assert _order(self._pair(run_manifest=failed)) == baseline


class TestExcludedBecause:
    def _result(self) -> SESearchResult:
        kept = _asset("a", "Kept")
        chemo = _asset("b", "Fludarabine")
        other = _asset("c", "Cyclophosphamide")
        return _result(
            [kept, chemo, other],
            [
                _gate(kept.asset_id, UNRESOLVED, target__expression=UNKNOWN),
                _gate(
                    chemo.asset_id,
                    OverallDisposition.EXCLUDED,
                    target__expression=FAIL,
                    strategy__indication=FAIL,
                    modality__required=PASS,
                ),
                _gate(other.asset_id, OverallDisposition.EXCLUDED, target__expression=FAIL),
            ],
            excluded=[chemo.asset_id, other.asset_id],
        )

    def test_excluded_are_listed_by_name_with_every_fail(self) -> None:
        shortlist = build_shortlist(self._result())
        assert [e.name for e in shortlist.entries] == ["Kept"]
        assert [e.name for e in shortlist.excluded] == ["Cyclophosphamide", "Fludarabine"]
        fludarabine = shortlist.excluded[1]
        assert fludarabine.review_reasons == (
            "target.expression FAIL: target.expression is FAIL.",
            "strategy.indication FAIL: strategy.indication is FAIL.",
        )
        assert shortlist.counts["excluded"] == 2

    def test_rendered_after_the_ranked_list(self) -> None:
        text = render_shortlist(build_shortlist(self._result()))
        assert "Excluded because (2 total, 2 shown):" in text
        assert text.index("Kept") < text.index("Excluded because")
        assert "strategy.indication FAIL" in text

    def test_band_is_capped_but_counts_are_not(self) -> None:
        shortlist = build_shortlist(self._result(), limit=1)
        assert len(shortlist.excluded) == 1
        assert shortlist.counts["excluded"] == 2

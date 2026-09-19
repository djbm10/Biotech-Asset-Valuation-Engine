"""The fact that decides a multi-target question, and what may not produce it.

``TargetOperator.ALL`` asks whether one construct hits every target named. It reads
``construct_target_set``, and in the live CD19/BCMA acceptance run no such fact existed on
any of 1,919 candidates, so every dual-target decision came back UNKNOWN and the shortlist
filled with single-target CD19 assets under a dual-target heading.

The two producers that did exist derived the set from a *document*: CT.gov fell back to
scanning the whole trial record, so a trial studying a CD19 CAR-T alongside a BCMA CAR-T
would have attributed both targets to each. That is the failure this fact has to be immune
to, so the set is derived from per-asset direct mechanism assertions -- the same evidence
behind ``CanonicalAsset.target_ids`` -- and from nothing else. Co-occurrence in a document,
co-administration in a regimen, and the targets a query was scoped to are all excluded by
construction rather than by filtering afterwards.

The distinction the tests below spend most of their effort on is silence versus denial. An
asset no authority documents must come back UNKNOWN, because a set derived from partial
evidence would read as a complete description of the construct and exclude the asset for a
reason the evidence never gave.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.evidence.construct_targets import (
    construct_target_evidence,
    intervention_construct_targets,
)
from bve.se.gates.engine import GateEngine
from bve.se.intent import build_buyer_identity, compile_intent, parse_query
from bve.se.ontology.mechanisms import (
    DrugTargetAuthority,
    DrugTargetEdge,
    EdgeStatus,
    TargetRelationship,
)
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache
from bve.se.resolution.target_attribution import OntologyTargetAttribution
from bve.se.schemas.contracts import (
    CanonicalAsset,
    GateStatus,
    NormalizedFact,
    TargetAssertionStatus,
)

AS_OF = date(2026, 9, 17)
BUYER = build_buyer_identity("NL Query", as_of_date=AS_OF)
TARGET_GATE = "target_logic"

CD19 = "TARGET:CD19"
BCMA = "TARGET:TNFRSF17"
CD3 = "TARGET:CD3E"


def _drug(source_id: str, name: str, *aliases: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="chembl",
        source_id=source_id,
        entity_type=EntityType.DRUG,
        canonical_symbol=name,
        label=name,
        aliases=[
            SourceAlias(value=value, alias_type=AliasType.SYNONYM) for value in (name, *aliases)
        ],
        xrefs={"chembl": [source_id]},
    )


def _target(source_id: str, symbol: str, *aliases: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=source_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=symbol,
        aliases=[SourceAlias(value=value, alias_type=AliasType.SYNONYM) for value in aliases],
        xrefs={"uniprot": [source_id]},
    )


def _snapshot() -> OntologySnapshot:
    return OntologySnapshot(
        sources=[
            SourceProvenance(
                source="chembl",
                release="ChEMBL_37",
                retrieved_at=date(2026, 9, 7),
                locator="test",
                digest="d",
                record_count=6,
            ),
            SourceProvenance(
                source="open_targets",
                release="26.06",
                retrieved_at=date(2026, 9, 7),
                locator="test",
                digest="d",
                record_count=2,
            ),
        ],
        records=[
            _drug("CHEMBL1", "BLINATUMOMAB"),
            _drug("CHEMBL2", "TECLISTAMAB"),
            _drug("CHEMBL3", "INEBILIZUMAB"),
            _drug("CHEMBL4", "DUALCONSTRUCTMAB"),
            _drug("CHEMBL5", "UNDOCUMENTEDMAB"),
            _target("P15391", "CD19", "B4"),
            _target("Q02223", "TNFRSF17", "BCMA"),
            _target("P07766", "CD3E", "CD3"),
        ],
    )


def _edge(
    drug: str,
    target: str,
    *,
    relationship: TargetRelationship = TargetRelationship.DIRECT_TARGET,
    source: str = "chembl",
) -> DrugTargetEdge:
    return DrugTargetEdge(
        canonical_drug_id=drug,
        canonical_target_id=target,
        relationship_type=relationship,
        source=source,
        source_release="ChEMBL_37",
        source_record_id="1",
        evidence_hash=f"{source}:{drug}:{target}:{relationship.value}",
        status=EdgeStatus.USABLE,
    )


def _assertions(asset_name: str, edges: list[DrugTargetEdge], requested: list[str]):
    resolver = BiomedicalEntityResolver(_snapshot())
    attribution = OntologyTargetAttribution(resolver, DrugTargetAuthority(edges), requested)
    return attribution.assert_targets(asset_name, [])


def _asset(name: str, edges: list[DrugTargetEdge], requested: list[str] = [CD19, BCMA]):
    assertions = _assertions(name, edges, requested)
    confirmed = [
        assertion.canonical_target_id
        for assertion in assertions
        if assertion.status is TargetAssertionStatus.CONFIRMED_TARGET
    ]
    return CanonicalAsset(
        asset_id=f"asset:{name}",
        canonical_name=name,
        target_assertions=assertions,
        target_ids=confirmed,
    )


def _drug_id(name: str) -> str:
    resolver = BiomedicalEntityResolver(_snapshot())
    return resolver.resolve(name, entity_type=EntityType.DRUG).canonical_id


def _observed(asset: CanonicalAsset) -> list[str] | None:
    evidence = construct_target_evidence(asset, as_of_date=AS_OF)
    return None if evidence is None else list(evidence.fact.value)


@pytest.fixture()
def snapshot(tmp_path, monkeypatch):
    _snapshot().write(tmp_path / "snap")
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path / "snap"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


def _dual_decisions(asset: CanonicalAsset) -> list[GateStatus]:
    """Run the real dual question against whatever this asset's evidence produces."""

    problem = compile_intent(parse_query("dual CD19/BCMA therapies"), buyer=BUYER)
    evidence = construct_target_evidence(asset, as_of_date=AS_OF)
    facts: list[NormalizedFact] = [
        NormalizedFact(
            fact_id="fact:identity",
            subject_id=asset.asset_id,
            fact_type="identity_valid",
            value=True,
            supporting_claim_ids=["claim:identity"],
            confidence=0.9,
        )
    ]
    if evidence is not None:
        facts.append(evidence.fact)
    evaluation = GateEngine().evaluate(problem, subject_id=asset.asset_id, facts=facts)
    return [
        decision.status
        for decision in evaluation.decisions
        if decision.gate_id == TARGET_GATE
    ]


class TestOneConstructOneSet:
    def test_a_single_target_asset_cannot_satisfy_a_dual_question(self, snapshot) -> None:
        asset = _asset("INEBILIZUMAB", [_edge(_drug_id("INEBILIZUMAB"), CD19)])
        assert _observed(asset) == [CD19]
        assert _dual_decisions(asset) == [GateStatus.FAIL]

    def test_the_other_single_target_asset_cannot_either(self, snapshot) -> None:
        asset = _asset("TECLISTAMAB", [_edge(_drug_id("TECLISTAMAB"), BCMA)])
        assert _observed(asset) == [BCMA]
        assert _dual_decisions(asset) == [GateStatus.FAIL]

    def test_a_genuine_dual_construct_satisfies_it(self, snapshot) -> None:
        drug = _drug_id("DUALCONSTRUCTMAB")
        asset = _asset("DUALCONSTRUCTMAB", [_edge(drug, CD19), _edge(drug, BCMA)])
        assert _observed(asset) == [CD19, BCMA]
        assert _dual_decisions(asset) == [GateStatus.PASS]

    def test_the_set_keeps_targets_the_question_never_asked_about(self, snapshot) -> None:
        # A T-cell engager's CD3 arm is part of what the construct is. Reporting only the
        # targets that were asked about would make the fact a description of the query.
        drug = _drug_id("BLINATUMOMAB")
        asset = _asset("BLINATUMOMAB", [_edge(drug, CD19), _edge(drug, CD3)])
        assert _observed(asset) == [CD19, CD3]


class TestCoAdministrationIsNotOneConstruct:
    def test_two_single_target_drugs_given_together_do_not_add_up(self, snapshot) -> None:
        # The regimen covers both targets. Neither molecule in it does, and the question
        # asked for a molecule.
        cd19 = _asset("INEBILIZUMAB", [_edge(_drug_id("INEBILIZUMAB"), CD19)])
        bcma = _asset("TECLISTAMAB", [_edge(_drug_id("TECLISTAMAB"), BCMA)])
        assert _observed(cd19) == [CD19]
        assert _observed(bcma) == [BCMA]
        assert _dual_decisions(cd19) == [GateStatus.FAIL]
        assert _dual_decisions(bcma) == [GateStatus.FAIL]

    def test_a_regimen_partners_targets_never_reach_the_other_asset(self, snapshot) -> None:
        both = [_edge(_drug_id("INEBILIZUMAB"), CD19), _edge(_drug_id("TECLISTAMAB"), BCMA)]
        # Both edges are in front of the authority at once, as they are in any real run.
        assert _observed(_asset("INEBILIZUMAB", both)) == [CD19]
        assert _observed(_asset("TECLISTAMAB", both)) == [BCMA]


class TestSilenceIsNotDenial:
    def test_an_undocumented_asset_produces_no_fact_at_all(self, snapshot) -> None:
        asset = _asset("UNDOCUMENTEDMAB", [_edge(_drug_id("INEBILIZUMAB"), CD19)])
        assert _observed(asset) is None

    def test_and_therefore_decides_unknown_rather_than_fail(self, snapshot) -> None:
        asset = _asset("UNDOCUMENTEDMAB", [_edge(_drug_id("INEBILIZUMAB"), CD19)])
        assert _dual_decisions(asset) == [GateStatus.UNKNOWN]

    def test_an_unresolvable_name_produces_no_fact(self, snapshot) -> None:
        asset = _asset("SOMETHING NOT IN THE ONTOLOGY", [])
        assert all(
            assertion.status is TargetAssertionStatus.UNRESOLVED
            for assertion in asset.target_assertions
        )
        assert _observed(asset) is None

    def test_conflicting_authorities_produce_no_fact(self, snapshot) -> None:
        drug = _drug_id("INEBILIZUMAB")
        conflicting = [
            _edge(drug, CD19, source="chembl"),
            _edge(drug, BCMA, source="open_targets"),
        ]
        asset = _asset("INEBILIZUMAB", conflicting)
        if any(
            assertion.status is TargetAssertionStatus.CONFLICTING
            for assertion in asset.target_assertions
        ):
            assert _observed(asset) is None
            assert _dual_decisions(asset) == [GateStatus.UNKNOWN]
        else:  # pragma: no cover - documents the authority's own reading
            pytest.skip("this authority does not read these two edges as a conflict")

    def test_an_asset_with_no_assertions_produces_no_fact(self, snapshot) -> None:
        # No ontology snapshot in the run at all. Attribution is skipped, not defaulted.
        assert _observed(CanonicalAsset(asset_id="asset:x", canonical_name="X")) is None


class TestOnlyDirectAssetEvidenceCounts:
    def test_family_or_complex_association_cannot_satisfy_the_set(self, snapshot) -> None:
        drug = _drug_id("INEBILIZUMAB")
        asset = _asset(
            "INEBILIZUMAB",
            [
                _edge(drug, CD19),
                _edge(drug, BCMA, relationship=TargetRelationship.FAMILY_OR_COMPLEX_ASSOCIATION),
            ],
        )
        assert _observed(asset) == [CD19]
        assert _dual_decisions(asset) == [GateStatus.FAIL]

    def test_the_query_target_context_cannot_create_the_set(self, snapshot) -> None:
        # discovery_target_context is why a candidate surfaced. Reading it here would
        # reinstate query-target inheritance through the back door.
        asset = CanonicalAsset(
            asset_id="asset:ctx",
            canonical_name="UNDOCUMENTEDMAB",
            discovery_target_context=[CD19, BCMA],
        )
        assert _observed(asset) is None

    def test_declared_target_ids_alone_cannot_create_the_set(self, snapshot) -> None:
        # target_ids is derived from assertions; an asset carrying it without the
        # assertions behind it is unsupported, and the fact is the audited artifact.
        asset = CanonicalAsset(
            asset_id="asset:bare",
            canonical_name="UNDOCUMENTEDMAB",
            target_ids=[CD19, BCMA],
        )
        assert _observed(asset) is None


class TestTheFactCarriesItsProvenance:
    def test_it_cites_the_upstream_rows_it_rests_on(self, snapshot) -> None:
        drug = _drug_id("DUALCONSTRUCTMAB")
        asset = _asset("DUALCONSTRUCTMAB", [_edge(drug, CD19), _edge(drug, BCMA)])
        evidence = construct_target_evidence(asset, as_of_date=AS_OF)
        assert evidence is not None
        assert evidence.fact.supporting_claim_ids
        assert {claim.claim_id for claim in evidence.claims} == set(
            evidence.fact.supporting_claim_ids
        )
        assert {document.document_id for document in evidence.documents} == {
            claim.source_document_id for claim in evidence.claims
        }

    def test_the_source_and_release_are_named_not_just_the_conclusion(self, snapshot) -> None:
        drug = _drug_id("DUALCONSTRUCTMAB")
        asset = _asset("DUALCONSTRUCTMAB", [_edge(drug, CD19), _edge(drug, BCMA)])
        evidence = construct_target_evidence(asset, as_of_date=AS_OF)
        assert evidence is not None
        rendered = " ".join(claim.supporting_passage for claim in evidence.claims)
        assert "chembl" in rendered
        assert "ChEMBL_37" in rendered
        assert "DIRECT_TARGET" in rendered

    def test_the_fact_is_stable_across_identical_evidence(self, snapshot) -> None:
        drug = _drug_id("DUALCONSTRUCTMAB")
        asset = _asset("DUALCONSTRUCTMAB", [_edge(drug, CD19), _edge(drug, BCMA)])
        first = construct_target_evidence(asset, as_of_date=AS_OF)
        second = construct_target_evidence(asset, as_of_date=AS_OF)
        assert first is not None and second is not None
        assert first.fact == second.fact


class TestAnInterventionRecordDescribesItsOwnConstruct:
    """The second admissible route, and the boundary that keeps it from being the first.

    A registry intervention that says "CLN-978: CD19-directed CD3 bispecific T-cell
    engager" is a structured, asset-specific statement about one molecule -- the authority
    being silent on a development code is a gap in a drug dictionary, not evidence that
    the sponsor never said what their asset binds. What this must not become is the
    document scan it replaced, so it reads the intervention's own fields only, and says
    nothing at all about a regimen.
    """

    def test_an_interventions_own_description_attributes_its_targets(self, snapshot) -> None:
        targets = intervention_construct_targets(
            {
                "name": "CLN-978",
                "description": "CD19-directed CD3 bispecific T-cell engager",
            },
            intervention_type=None,
        )
        assert targets == [CD19, CD3]

    def test_a_protocol_naming_another_arms_target_does_not_reach_this_asset(
        self, snapshot
    ) -> None:
        # The words are in the trial record, not in this intervention. That was the
        # original defect: the whole protocol was scanned and every arm inherited the lot.
        targets = intervention_construct_targets(
            {"name": "CLN-978", "description": "CD19-directed T-cell engager"},
            intervention_type=None,
        )
        assert "TNFRSF17" not in (targets or [])

    def test_a_declared_combination_product_describes_no_single_construct(
        self, snapshot
    ) -> None:
        assert (
            intervention_construct_targets(
                {
                    "name": "CLN-978 plus teclistamab",
                    "description": "CD19-directed engager with a BCMA-directed engager",
                },
                intervention_type="COMBINATION_PRODUCT",
            )
            is None
        )

    def test_a_regimen_named_in_one_field_is_not_one_construct_either(self, snapshot) -> None:
        # Untyped by the registry, but the name denotes two molecules. Reading the union
        # of their targets as one construct is how a regimen passes a dual-target gate.
        assert (
            intervention_construct_targets(
                {
                    "name": "Inebilizumab and teclistamab",
                    "description": "CD19-directed antibody with a BCMA-directed engager",
                },
                intervention_type=None,
            )
            is None
        )

    def test_an_intervention_that_names_no_target_says_nothing(self, snapshot) -> None:
        assert (
            intervention_construct_targets(
                {"name": "CLN-978", "description": "an investigational agent"},
                intervention_type=None,
            )
            is None
        )


class TestNoTargetIsSpecialCased:
    def test_the_rule_holds_for_targets_the_acceptance_query_never_mentions(
        self, snapshot
    ) -> None:
        drug = _drug_id("BLINATUMOMAB")
        single = _asset("BLINATUMOMAB", [_edge(drug, CD19)], requested=[CD19, CD3])
        dual = _asset(
            "BLINATUMOMAB", [_edge(drug, CD19), _edge(drug, CD3)], requested=[CD19, CD3]
        )
        assert _observed(single) == [CD19]
        assert _observed(dual) == [CD19, CD3]

    def test_no_target_identifier_is_named_in_the_derivation_code(self) -> None:
        # Prose may cite a target to explain a rule; the rule itself may not know one
        # exists. Docstrings and comments are stripped so the check is about behaviour
        # rather than about how the module is described.
        import ast
        from pathlib import Path

        import bve.se.evidence.construct_targets as module

        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                if node.body and isinstance(node.body[0], ast.Expr):
                    if isinstance(node.body[0].value, ast.Constant):
                        node.body = node.body[1:] or [ast.Pass()]
        code = ast.unparse(ast.fix_missing_locations(tree))
        for symbol in ("CD19", "TNFRSF17", "BCMA", "CD3"):
            assert symbol not in code


class TestTwoAdmissibleRoutesDoNotArgue:
    """What happens when the authority and an intervention record both speak.

    Nothing merges them: a union would let a sponsor's prose add a target the authority
    never documented, which is the regimen failure by another name. And nothing leaves the
    disagreement standing either, because the gate reads competing target facts as UNKNOWN
    -- so an asset the authority describes correctly would lose its decision to a second,
    weaker witness. The authority wins, and the loser stays in the ledger.
    """

    def _fact(self, fact_id: str, value: list[str]) -> NormalizedFact:
        return NormalizedFact(
            fact_id=fact_id,
            subject_id="asset:1",
            fact_type="construct_target_set",
            value=value,
            supporting_claim_ids=[f"claim:{fact_id}"],
            confidence=0.9,
        )

    def test_the_authority_replaces_an_intervention_derived_set(self) -> None:
        from bve.se.evidence.construct_targets import supersede_construct_targets

        intervention = self._fact("fact:intervention", [CD19, BCMA])
        authority = self._fact("fact:authority", [CD19])
        kept = supersede_construct_targets([intervention], authority)
        assert kept == [authority]

    def test_exactly_one_construct_fact_survives_so_the_gate_can_decide(self) -> None:
        from bve.se.evidence.construct_targets import supersede_construct_targets

        facts = [self._fact("fact:a", [CD19, BCMA]), self._fact("fact:b", [BCMA])]
        kept = supersede_construct_targets(facts, self._fact("fact:authority", [CD19]))
        assert [fact.fact_type for fact in kept].count("construct_target_set") == 1

    def test_other_facts_are_left_alone(self) -> None:
        from bve.se.evidence.construct_targets import supersede_construct_targets

        modality = NormalizedFact(
            fact_id="fact:modality",
            subject_id="asset:1",
            fact_type="modality_id",
            value="CAR_T",
            supporting_claim_ids=["claim:modality"],
            confidence=0.9,
        )
        kept = supersede_construct_targets(
            [modality, self._fact("fact:intervention", [BCMA])],
            self._fact("fact:authority", [CD19]),
        )
        assert modality in kept

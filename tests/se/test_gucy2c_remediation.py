"""Regression tests for gucy2c_pilot_remediation_v1 (C2-C9).

Every record here is synthetic, shaped like the ClinicalTrials.gov records the GUCY2C pilot
exposed. The tests pin the general rules, not GUCY2C: each one would fail for any target
the same way.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.discovery import adapters as A
from bve.se.ontology.records import AliasType, EntityType, SourceAlias, SourceEntityRecord
from bve.se.ontology.snapshot import OntologySnapshot, SourceProvenance
from bve.se.ontology.targets import reset_resolver_cache
from bve.se.schemas.contracts import CompiledQuery


def _target(source_id: str, symbol: str, *synonyms: str) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets", source_id=source_id, entity_type=EntityType.TARGET,
        canonical_symbol=symbol, label=symbol,
        aliases=[SourceAlias(value=v, alias_type=AliasType.SYNONYM) for v in synonyms],
        xrefs={"uniprot": [f"P{source_id[-5:]}"]},
    )


@pytest.fixture
def ontology(tmp_path_factory, monkeypatch):
    snapshot = OntologySnapshot(
        sources=[SourceProvenance(source="open_targets", release="26.06",
                                  retrieved_at=date(2026, 8, 15), locator="test")],
        records=[
            _target("ENSG00000070019", "GUCY2C", "GCC", "GC-C", "STAR",
                    "guanylyl cyclase C", "hSTAR"),
            # A second claimant of "STAR": the alias is shared, so retrieval refuses it.
            _target("ENSG00000147465", "STAR", "STARD1"),
            _target("ENSG00000160145", "KALRN", "DUO"),
            _target("ENSG00000177455", "CD19"),
            _target("ENSG00000048462", "TNFRSF17", "BCMA"),
        ],
    )
    path = tmp_path_factory.mktemp("gucy2c_ontology") / "snapshot"
    snapshot.write(path)
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(path))
    reset_resolver_cache()
    A.QueryVocabulary.for_ontology.cache_clear()
    yield snapshot
    reset_resolver_cache()
    A.QueryVocabulary.for_ontology.cache_clear()


def _query(**kw) -> CompiledQuery:
    base = {"query_id": "q", "query": "GUCY2C", "target_ids": ["GUCY2C"],
                "aliases": ["GUCY2C", "GCC", "STAR", "guanylyl cyclase C", "hSTAR"]}
    return CompiledQuery(**(base | kw))


def _protocol(interventions, arms, title="A study", summary=""):
    return {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": title,
                                 "officialTitle": title},
        "descriptionModule": {"briefSummary": summary},
        "armsInterventionsModule": {"interventions": interventions, "armGroups": arms},
    }


def _iv(name, kind="DRUG", description="", other=None):
    return {"type": kind, "name": name, "description": description, "otherNames": other or []}


def _arm(label, *names, kind="EXPERIMENTAL"):
    return {"type": kind, "label": label, "interventionNames": list(names)}


def _hits(protocol, vocabulary):
    serialized = A._protocol_text(protocol)
    return {n: t for n, t, _ in A._candidate_interventions(protocol, vocabulary, serialized)}


# ------------------------------------------------------------------ C2 vocabulary
def test_shared_alias_from_the_problem_is_not_a_target_term(ontology) -> None:
    vocabulary = A.QueryVocabulary.for_query(_query())
    terms = dict(vocabulary.targets)["GUCY2C"]
    assert "star" not in terms
    assert "gucy2c" in terms and "guanylyl cyclase c" in terms
    assert vocabulary.targets_in("STAR-AF ablation trial") == set()


def test_shared_alias_is_not_a_retrieval_facet(ontology) -> None:
    facets = A.QueryVocabulary.for_query(_query()).query_facets()
    assert all("STAR" not in facet for facet in facets)
    assert any("GUCY2C" in facet for facet in facets)


def test_follow_up_lead_is_not_a_target_term(ontology) -> None:
    vocabulary = A.QueryVocabulary.for_query(
        _query(query="Walking", aliases=["Walking"], expansion_depth=1)
    )
    assert vocabulary.targets_in("A walking exercise study") == set()
    assert vocabulary.lead_terms == ("walking",)


# ------------------------------------------------------------------ C3 short alias frames
@pytest.mark.parametrize(
    "text",
    [
        "GCC 0845: vorinostat and lapatinib in advanced solid tumors",
        "OCT retinal GCC thickness",
        "Gulf Cooperation Council (GCC) countries",
        "Gemcitabine/Carboplatin/Cetuximab (GCC) plus cixutumumab",
        "Japanese Encephalitis vaccine-GCC inj",
    ],
)
def test_short_alias_without_a_target_frame_is_not_the_target(ontology, text) -> None:
    assert A.QueryVocabulary.for_query(_query()).targets_in(text) == set()


@pytest.mark.parametrize(
    "text",
    [
        "Chimeric antigen receptor T cell preparation targeting GCC",
        "An armored GCC targeting CAR-T",
        "advanced GCC-positive GI cancer",
        "patients with expression of GCC",
        "guanylyl cyclase C in colorectal cancer, GCC",
    ],
)
def test_short_alias_in_a_target_frame_is_the_target(ontology, text) -> None:
    assert A.QueryVocabulary.for_query(_query()).targets_in(text) == {"GUCY2C"}


def test_established_sense_covers_the_records_own_intervention_text(ontology) -> None:
    vocabulary = A.QueryVocabulary.for_query(_query())
    assert vocabulary.targets_in("EB-DUO-CAR-NK-CEA/GCC") == set()
    assert vocabulary.targets_in("EB-DUO-CAR-NK-CEA/GCC", established={"GUCY2C"}) == {"GUCY2C"}


def test_short_terms_match_whole_words_only(ontology) -> None:
    vocabulary = A.QueryVocabulary.for_query(_query())
    assert vocabulary.targets_in("org study id NORTHSTAR003") == set()
    # Longer terms keep substring semantics: hGUCY2C is human GUCY2C.
    assert vocabulary.targets_in("Ad5.F35-hGUCY2C-PADRE vaccine") == {"GUCY2C"}


# ------------------------------------------------------------------ C4 protocol backbone
def test_backbone_of_a_combination_trial_inherits_the_protocol_target(ontology) -> None:
    protocol = _protocol(
        [_iv("PF-07062119"), _iv("Anti-PD1"), _iv("Anti-VEGF")],
        [_arm("Dose Escalation", "Drug: PF-07062119"),
         _arm("Combo", "Drug: PF-07062119", "Drug: Anti-PD1"),
         _arm("Combo 2", "Drug: PF-07062119", "Drug: Anti-VEGF")],
        title="PF-07062119 in GUCY2C-expressing gastrointestinal tumors",
    )
    hits = _hits(protocol, A.QueryVocabulary.for_query(_query()))
    assert hits["PF-07062119"] == {"GUCY2C"}
    assert hits.get("Anti-PD1", set()) == set() and hits.get("Anti-VEGF", set()) == set()


def test_two_monotherapy_arms_have_no_backbone(ontology) -> None:
    protocol = _protocol(
        [_iv("ABC-101"), _iv("XYZ-202")],
        [_arm("A", "Drug: ABC-101"), _arm("B", "Drug: XYZ-202")],
        title="ABC-101 or XYZ-202 in GUCY2C tumors",
    )
    hits = _hits(protocol, A.QueryVocabulary.for_query(_query()))
    assert all(targets == set() for targets in hits.values())


# ------------------------------------------------------------------ C5 / C6 naming
def test_diagnostic_and_procedure_interventions_are_not_nominated(ontology) -> None:
    protocol = _protocol(
        [_iv("Lm-GUCY2C vaccine", "BIOLOGICAL"), _iv("CT Scan", "DIAGNOSTIC_TEST"),
         _iv("Biopsy", "PROCEDURE")],
        [_arm("Arm 1", "Biological: Lm-GUCY2C vaccine", "Diagnostic Test: CT Scan")],
        title="GUCY2C vaccination",
    )
    names = set(_hits(protocol, A.QueryVocabulary.for_query(_query())))
    assert names == {"Lm-GUCY2C"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LCAR-G08 cells", "LCAR-G08"),
        ("Ad5-hGCC-PADRE vaccine", "Ad5-hGCC-PADRE"),
        ("EB-DUO-CAR-NK-CEA/GCC (IV)", "EB-DUO-CAR-NK-CEA/GCC"),
        ("CAR-T cells", "CAR-T cells"),
        ("gucy2c cart cells", "gucy2c cart cells"),
        ("CAR-T", "CAR-T"),
    ],
)
def test_identity_name_drops_form_and_route_suffixes_only_from_codes(raw, expected) -> None:
    assert A.identity_name_for_intervention({}, _iv(raw, "BIOLOGICAL")) == expected


def test_descriptor_intervention_takes_the_code_its_title_and_arm_name() -> None:
    descriptor = "Chimeric antigen receptor T cell preparation targeting GCC"
    protocol = _protocol(
        [_iv(descriptor)],
        [_arm("XKDCT080 treatment for patients with GCC target positivity", f"Drug: {descriptor}")],
        title="XKDCT080 in GCC-positive Recurrent or Refractory Solid Tumors",
    )
    assert A.identity_name_for_intervention(protocol, _iv(descriptor)) == "XKDCT080"


def test_descriptor_without_an_arm_naming_the_code_stays_unnamed() -> None:
    descriptor = "Chimeric antigen receptor T cell preparation targeting GCC"
    protocol = _protocol(
        [_iv(descriptor)], [_arm("Treatment arm", f"Drug: {descriptor}")],
        title="XKDCT080 in GCC-positive solid tumors",
    )
    assert A.identity_name_for_intervention(protocol, _iv(descriptor)) == descriptor


# ------------------------------------------------------------------ C7 construct targets
def test_code_fragment_is_not_a_construct_target(ontology) -> None:
    from bve.se.evidence.construct_targets import attributed_targets_in

    assert "TARGET:KALRN" not in attributed_targets_in("EB-DUO-CAR-NK-CEA/GCC")
    assert attributed_targets_in("CD19-BCMA CAR-T") == ["TARGET:CD19", "TARGET:TNFRSF17"]


def test_cue_does_not_reach_across_a_comma(ontology) -> None:
    from bve.se.evidence.construct_targets import attributed_targets_in

    assert attributed_targets_in("a tandem CAR, a CD19 support element") == []
    assert attributed_targets_in("anti-CD19 CAR-T cells") == ["TARGET:CD19"]


# ------------------------------------------------------------------ C8 action type
def test_authority_action_type_becomes_a_fact() -> None:
    from bve.se.evidence.construct_targets import construct_target_evidence
    from bve.se.schemas.contracts import (
        CandidateTargetAssertion,
        CanonicalAsset,
        TargetAssertionStatus,
        TargetEvidenceRef,
    )

    ref = TargetEvidenceRef(source="chembl", source_release="37", source_record_id="1",
                            evidence_hash="h1", canonical_target_id="TARGET:GUCY2C",
                            relationship_type="DIRECT", action_type="AGONIST")
    asset = CanonicalAsset(
        asset_id="a1", canonical_name="exampletide",
        target_assertions=[CandidateTargetAssertion(
            canonical_target_id="TARGET:GUCY2C",
            status=TargetAssertionStatus.CONFIRMED_TARGET,
            documented_targets=["TARGET:GUCY2C"], evidence=[ref])],
    )
    evidence = construct_target_evidence(asset, as_of_date=date(2026, 10, 24))
    assert evidence is not None
    assert [(f.fact_type, f.value) for f in evidence.action_facts] == [
        ("target_action_type", "AGONIST")
    ]
    assert set(evidence.action_facts[0].supporting_claim_ids) <= {c.claim_id for c in evidence.claims}


def test_agonist_exclusion_fails_agonists_and_leaves_unknown_unknown() -> None:
    from bve.se.gates.evaluator import evaluate_requirement
    from bve.se.schemas.contracts import (
        BuyerRequirement,
        GateStatus,
        NormalizedFact,
        RequirementDomain,
        RequirementOperator,
    )

    requirement = BuyerRequirement(
        requirement_id="x", domain=RequirementDomain.ELIGIBILITY,
        fact_type="target_action_type", operator=RequirementOperator.NOT_IN,
        expected_value=["AGONIST"], pass_condition="p", fail_condition="f",
        unknown_condition="u",
    )

    def fact(value):
        return NormalizedFact(fact_id=f"f-{value}", subject_id="s", fact_type="target_action_type",
                              value=value, supporting_claim_ids=["c"], confidence=0.9)

    def decide(facts):
        return evaluate_requirement(requirement, subject_id="s", facts=facts, gate_id="g").status

    assert decide([fact("AGONIST")]) is GateStatus.FAIL
    assert decide([fact("BINDING AGENT")]) is GateStatus.PASS
    assert decide([]) is GateStatus.UNKNOWN
    assert decide([fact("AGONIST"), fact("ANTAGONIST")]) is GateStatus.UNKNOWN

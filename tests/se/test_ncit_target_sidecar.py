"""NCIT_TARGET_SIDECAR v1: emit only where NCIt's class and mechanism sentence agree.

Definitions below are verbatim NCIt 26.08e text (trimmed to the sentences that matter).
Policy: ``docs/se_policies/ncit_target_sidecar_v1.md``.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from bve.se.ontology.ncit_targets import (
    NCIT_EXTRACTOR_KEY,
    NcitTargetAuthority,
    decide,
    mechanism_antigens,
    ncit_authority,
    ncit_construct_evidence,
    reset_ncit_cache,
)

CD19_CLASS, BCMA_CLASS, GD2_CLASS = "C176018", "C176023", "C201491"

ARCHITECTURE = (
    "A preparation of autologous T-lymphocytes transduced with a CAR composed of an anti-CD19 "
    "scFv linked to the costimulatory domain CD28, the zeta chain of the TCR/CD3 complex "
    "(CD3zeta; CD247), membrane-bound IL-15 and truncated HER1. Upon reintroduction of the "
    "autologous CD19-CD8-CD28-CD3zeta-CAR-mbIL15-HER1t T cells into the patient, the T-cells "
    "target and bind to CD19-expressing tumor cells."
)
DUAL = (
    "A preparation of CAR-T cells. Upon administration, the autologous bispecific "
    "BCMA/CD19-targeted CAR-T cells GC012F specifically and simultaneously target and bind to "
    "tumor cells expressing BCMA and/or CD19."
)


class TestDecision:
    def test_architecture_never_becomes_a_target(self, se_ontology_snapshot) -> None:
        decision = decide({CD19_CLASS}, ARCHITECTURE)
        assert decision.targets == ("TARGET:CD19",)

    def test_a_dual_construct_is_one_set(self, se_ontology_snapshot) -> None:
        decision = decide({CD19_CLASS, BCMA_CLASS}, DUAL)
        assert decision.targets == ("TARGET:CD19", "TARGET:TNFRSF17")

    def test_an_incomplete_class_set_disagrees_and_emits_nothing(self, se_ontology_snapshot) -> None:
        decision = decide({BCMA_CLASS}, DUAL)
        assert decision.targets == () and decision.reason == "class_mechanism_disagree"

    def test_no_class_is_unknown_even_with_a_clear_sentence(self, se_ontology_snapshot) -> None:
        # TAK-007 (CAR-NK): NCIt has no CAR-NK antigen classes (Amendment 1).
        decision = decide(set(), "Upon transfusion, X recognize CD19-expressing tumor cells.")
        assert decision.targets == () and decision.reason == "no_antigen_class"

    def test_no_definition_is_unknown(self, se_ontology_snapshot) -> None:
        # Resecabtagene: class only, no definition text (Amendment 1).
        decision = decide({CD19_CLASS}, "")
        assert decision.targets == () and decision.reason == "no_mechanism_sentence"

    def test_a_non_gene_antigen_is_not_forced_onto_a_gene(self, se_ontology_snapshot) -> None:
        decision = decide({GD2_CLASS}, "Upon administration, X kill GD2-expressing cells.")
        assert decision.targets == () and decision.reason == "non_protein_antigen"

    def test_a_polyclonal_product_has_no_target(self, se_ontology_snapshot) -> None:
        lifileucel = (
            "A preparation of autologous tumor infiltrating lymphocytes. Upon re-introduction, "
            "the TILs specifically recognize the tumor-associated antigens (TAAs)."
        )
        assert decide(set(), lifileucel).reason == "no_antigen_class"

    def test_an_unresolvable_antigen_refuses(self, se_ontology_snapshot) -> None:
        targets, why = mechanism_antigens("Upon administration, X kill ZZQ9-expressing cells.")
        assert targets is None and why.startswith("unresolved")


def _payload() -> dict:
    def product(name, names, targets, reason):
        return {
            "name": name, "names": names, "classes": [CD19_CLASS] if targets else [],
            "targets": targets, "reason": reason, "class_set": targets,
            "mechanism_set": targets,
            "mechanism_sentence": "Upon administration, X kill CD19-expressing cells.",
            "definition_sha256": "x",
        }

    return {
        "version": "ncit_target_sidecar_v1", "ncit_release": "26.08e",
        "release_zip_sha256": "z", "target_ontology_version": "t",
        "products": {
            "C1": product("Acmecabtagene Autoleucel", ["Acmecabtagene Autoleucel", "ACME-19"],
                          ["TARGET:CD19"], "emit"),
            "C2": product("Tabelecleucel", ["Tabelecleucel"], [], "no_antigen_class"),
            "C3": product("Twin A", ["TWIN-1"], ["TARGET:CD19"], "emit"),
            "C4": product("Twin B", ["TWIN 1"], ["TARGET:CD19"], "emit"),
            "C5": product("Tisagenlecleucel", ["Tisagenlecleucel", "CART19"],
                          ["TARGET:CD19"], "emit"),
        },
    }


@pytest.fixture
def authority() -> NcitTargetAuthority:
    return NcitTargetAuthority(_payload(), "a" * 64)


class TestLinking:
    def test_an_authority_name_links_exactly_one_concept(self, authority) -> None:
        link = authority.link(["acme-19"])
        assert link.code == "C1" and link.reason == "emit"

    def test_two_concepts_is_ambiguous_and_never_a_fact(self, authority) -> None:
        link = authority.link(["TWIN-1"])
        assert link.reason == "ambiguous_link"
        assert ncit_construct_evidence("a", link, authority, as_of_date=date(2026, 9, 24)) is None

    def test_class_terms_never_link(self, authority) -> None:
        assert authority.link(["CART19", "CAR-T"]) is None

    def test_a_non_target_disposition_has_no_fact(self, authority) -> None:
        link = authority.link(["Tabelecleucel"])
        assert link.reason == "no_antigen_class"
        assert ncit_construct_evidence("a", link, authority, as_of_date=date(2026, 9, 24)) is None


class TestEvidence:
    def test_the_fact_cites_concept_class_mechanism_and_link(self, authority) -> None:
        link = authority.link(["Acmecabtagene autoleucel"])
        evidence = ncit_construct_evidence("asset:1", link, authority, as_of_date=date(2026, 9, 24))
        assert evidence.fact.value == ["TARGET:CD19"]
        (claim,) = evidence.claims
        assert claim.locator.startswith("NCIt:C1#class=[TARGET:CD19]")
        assert claim.extraction_method == "ncit_class_mechanism_agreement"
        assert evidence.documents[0].source_url == "urn:ncit:26.08e"

    def test_evidence_is_deterministic(self, authority) -> None:
        link = authority.link(["ACME-19"])
        first = ncit_construct_evidence("asset:1", link, authority, as_of_date=date(2026, 9, 24))
        second = ncit_construct_evidence("asset:1", link, authority, as_of_date=date(2026, 9, 24))
        assert first == second


class TestReplayDependency:
    def _custody(self, tmp_path, token):
        from bve.se.discovery.replay import SealedCorpusReplay

        replay = SealedCorpusReplay.__new__(SealedCorpusReplay)
        replay.custody_root = tmp_path
        versions = {NCIT_EXTRACTOR_KEY: token} if token else {}
        (tmp_path / "corpus_manifest.json").write_text(json.dumps({"extractor_versions": versions}))
        return replay

    def _install(self, tmp_path, monkeypatch) -> str:
        path = tmp_path / "sidecar.json"
        path.write_text(json.dumps(_payload()))
        monkeypatch.setenv("BVE_SE_NCIT_SIDECAR", str(path))
        reset_ncit_cache()
        return ncit_authority().version_token

    def test_a_missing_sidecar_fails_closed(self, tmp_path) -> None:
        from bve.se.discovery.replay import OntologyMismatch

        replay = self._custody(tmp_path, "ncit_target_sidecar_v1@ncit_26.08e@deadbeef")
        with pytest.raises(OntologyMismatch):
            replay._require_matching_sidecars()

    def test_a_different_sidecar_fails_closed(self, tmp_path, monkeypatch) -> None:
        from bve.se.discovery.replay import OntologyMismatch

        self._install(tmp_path, monkeypatch)
        replay = self._custody(tmp_path, "ncit_target_sidecar_v1@ncit_26.08e@deadbeef")
        with pytest.raises(OntologyMismatch):
            replay._require_matching_sidecars()

    def test_the_identical_sidecar_replays(self, tmp_path, monkeypatch) -> None:
        token = self._install(tmp_path, monkeypatch)
        self._custody(tmp_path, token)._require_matching_sidecars()

    def test_a_corpus_that_predates_the_sidecar_replays(self, tmp_path) -> None:
        self._custody(tmp_path, None)._require_matching_sidecars()

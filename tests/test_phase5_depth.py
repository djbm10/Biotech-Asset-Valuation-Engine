"""Phase 5 Depth tests: OncologyEndpointLibrary, RareDiseaseEndpointLibrary, PrecedentExpander, ControversyLayer."""
from __future__ import annotations

from datetime import date

import pytest

from bve.trials.oncology_endpoints import (
    ONCOLOGY_ENDPOINTS,
    OncologyEndpointLibrary,
)
from bve.trials.rare_disease_endpoints import (
    RareDiseaseEndpointLibrary,
)
from bve.regulatory.precedent_expander import (
    ApprovalPathway,
    PrecedentExpander,
)
from bve.biology.controversy_layer import (
    Counterargument,
    ControversyLayer,
    ControversyType,
)


# ---------------------------------------------------------------------------
# OncologyEndpointLibrary
# ---------------------------------------------------------------------------


class TestOncologyEndpointLibrary:
    def setup_method(self) -> None:
        self.lib = OncologyEndpointLibrary()

    def test_get_returns_correct_endpoint_by_abbreviation(self) -> None:
        ep = self.lib.get("OS")
        assert ep is not None
        assert ep.abbreviation == "OS"
        assert "Overall Survival" in ep.name

    def test_get_returns_pfs(self) -> None:
        ep = self.lib.get("PFS")
        assert ep is not None
        assert ep.abbreviation == "PFS"

    def test_get_returns_orr(self) -> None:
        ep = self.lib.get("ORR")
        assert ep is not None
        assert ep.endpoint_type == "primary"

    def test_get_returns_none_for_unknown_abbreviation(self) -> None:
        result = self.lib.get("XYZUNKNOWN")
        assert result is None

    def test_get_returns_none_for_empty_string(self) -> None:
        result = self.lib.get("")
        assert result is None

    def test_by_tumor_type_returns_nsclc_endpoints(self) -> None:
        results = self.lib.by_tumor_type("nsclc")
        assert len(results) >= 3
        abbreviations = {ep.abbreviation for ep in results}
        assert "OS" in abbreviations
        assert "PFS" in abbreviations

    def test_by_tumor_type_includes_all_solid_endpoints(self) -> None:
        # Endpoints tagged "all_solid" must appear in any tumor type query
        results = self.lib.by_tumor_type("prostate")
        all_solid_in_corpus = [ep for ep in ONCOLOGY_ENDPOINTS if "all_solid" in ep.tumor_types]
        for ep in all_solid_in_corpus:
            assert ep in results

    def test_by_tumor_type_returns_heme_for_aml(self) -> None:
        results = self.lib.by_tumor_type("aml")
        abbrevs = {ep.abbreviation for ep in results}
        assert "CR" in abbrevs

    def test_established_primaries_only_established_and_primary(self) -> None:
        primaries = self.lib.established_primaries()
        for ep in primaries:
            assert ep.regulatory_precedent == "established"
            assert ep.endpoint_type == "primary"

    def test_established_primaries_not_empty(self) -> None:
        primaries = self.lib.established_primaries()
        assert len(primaries) >= 2

    def test_established_primaries_does_not_include_accelerated(self) -> None:
        primaries = self.lib.established_primaries()
        for ep in primaries:
            assert ep.regulatory_precedent != "accelerated"

    def test_surrogates_only_endpoints_with_surrogate_for_set(self) -> None:
        surrogates = self.lib.surrogates()
        for ep in surrogates:
            assert ep.surrogate_for is not None

    def test_surrogates_includes_pfs(self) -> None:
        surrogates = self.lib.surrogates()
        abbrevs = {ep.abbreviation for ep in surrogates}
        assert "PFS" in abbrevs

    def test_surrogates_does_not_include_os(self) -> None:
        surrogates = self.lib.surrogates()
        abbrevs = {ep.abbreviation for ep in surrogates}
        assert "OS" not in abbrevs  # OS is not a surrogate for anything

    def test_all_endpoints_has_at_least_20_entries(self) -> None:
        all_eps = self.lib.all_endpoints()
        assert len(all_eps) >= 20

    def test_all_endpoints_no_empty_names(self) -> None:
        for ep in self.lib.all_endpoints():
            assert ep.name != ""

    def test_all_endpoints_no_empty_abbreviations(self) -> None:
        for ep in self.lib.all_endpoints():
            assert ep.abbreviation != ""

    def test_all_endpoints_no_empty_tumor_types(self) -> None:
        for ep in self.lib.all_endpoints():
            assert len(ep.tumor_types) > 0

    def test_all_endpoints_abbreviations_are_unique(self) -> None:
        abbrevs = [ep.abbreviation for ep in self.lib.all_endpoints()]
        assert len(abbrevs) == len(set(abbrevs))

    def test_cr_endpoint_is_heme(self) -> None:
        ep = self.lib.get("CR")
        assert ep is not None
        assert "aml" in ep.tumor_types or "all" in ep.tumor_types

    def test_pcr_is_surrogate(self) -> None:
        ep = self.lib.get("pCR")
        assert ep is not None
        assert ep.surrogate_for is not None

    def test_qol_c30_is_exploratory_secondary(self) -> None:
        ep = self.lib.get("QoL-C30")
        assert ep is not None
        assert ep.endpoint_type == "secondary"


# ---------------------------------------------------------------------------
# RareDiseaseEndpointLibrary
# ---------------------------------------------------------------------------


class TestRareDiseaseEndpointLibrary:
    def setup_method(self) -> None:
        self.lib = RareDiseaseEndpointLibrary()

    def test_get_returns_6mwd(self) -> None:
        ep = self.lib.get("6MWD")
        assert ep is not None
        assert ep.abbreviation == "6MWD"

    def test_get_returns_fev1(self) -> None:
        ep = self.lib.get("FEV1")
        assert ep is not None
        assert ep.indication_area == "pulmonary"

    def test_get_returns_none_for_unknown(self) -> None:
        result = self.lib.get("NOTREAL")
        assert result is None

    def test_by_indication_area_neuromuscular(self) -> None:
        results = self.lib.by_indication_area("neuromuscular")
        assert len(results) >= 4
        for ep in results:
            assert ep.indication_area == "neuromuscular"

    def test_by_indication_area_pulmonary(self) -> None:
        results = self.lib.by_indication_area("pulmonary")
        assert len(results) >= 3

    def test_by_indication_area_hematologic(self) -> None:
        results = self.lib.by_indication_area("hematologic")
        assert len(results) >= 3

    def test_by_indication_area_metabolic(self) -> None:
        results = self.lib.by_indication_area("metabolic")
        assert len(results) >= 2

    def test_by_indication_area_ophthalmic(self) -> None:
        results = self.lib.by_indication_area("ophthalmic")
        assert len(results) >= 1

    def test_validated_endpoints_all_have_validated_true(self) -> None:
        validated = self.lib.validated_endpoints()
        for ep in validated:
            assert ep.validated is True

    def test_validated_endpoints_not_empty(self) -> None:
        validated = self.lib.validated_endpoints()
        assert len(validated) >= 10

    def test_unvalidated_endpoints_excluded_from_validated(self) -> None:
        validated = self.lib.validated_endpoints()
        for ep in validated:
            assert ep.validated is True
        # LCI is explicitly not validated
        abbrevs = {ep.abbreviation for ep in validated}
        assert "LCI" not in abbrevs

    def test_all_endpoints_at_least_15(self) -> None:
        all_eps = self.lib.all_endpoints()
        assert len(all_eps) >= 15

    def test_endpoints_span_multiple_indication_areas(self) -> None:
        areas = {ep.indication_area for ep in self.lib.all_endpoints()}
        assert len(areas) >= 4

    def test_all_endpoints_no_empty_names(self) -> None:
        for ep in self.lib.all_endpoints():
            assert ep.name != ""

    def test_all_endpoints_no_empty_abbreviations(self) -> None:
        for ep in self.lib.all_endpoints():
            assert ep.abbreviation != ""

    def test_hgb_is_hematologic(self) -> None:
        ep = self.lib.get("Hgb")
        assert ep is not None
        assert ep.indication_area == "hematologic"


# ---------------------------------------------------------------------------
# PrecedentExpander
# ---------------------------------------------------------------------------


class TestPrecedentExpander:
    def setup_method(self) -> None:
        self.exp = PrecedentExpander()

    def test_by_modality_small_molecule(self) -> None:
        results = self.exp.by_modality("small_molecule")
        assert len(results) >= 4
        for r in results:
            assert r.modality == "small_molecule"

    def test_by_modality_biologic(self) -> None:
        results = self.exp.by_modality("biologic")
        assert len(results) >= 3
        for r in results:
            assert r.modality == "biologic"

    def test_by_modality_cell_therapy(self) -> None:
        results = self.exp.by_modality("cell_therapy")
        assert len(results) >= 1
        for r in results:
            assert r.modality == "cell_therapy"

    def test_by_modality_gene_therapy(self) -> None:
        results = self.exp.by_modality("gene_therapy")
        assert len(results) >= 1

    def test_by_modality_rna(self) -> None:
        results = self.exp.by_modality("rna")
        assert len(results) >= 1

    def test_by_pathway_accelerated(self) -> None:
        results = self.exp.by_pathway(ApprovalPathway.ACCELERATED)
        assert len(results) >= 6
        for r in results:
            assert ApprovalPathway.ACCELERATED in r.approval_pathway

    def test_by_pathway_breakthrough(self) -> None:
        results = self.exp.by_pathway(ApprovalPathway.BREAKTHROUGH)
        assert len(results) >= 5
        for r in results:
            assert ApprovalPathway.BREAKTHROUGH in r.approval_pathway

    def test_by_pathway_orphan(self) -> None:
        results = self.exp.by_pathway(ApprovalPathway.ORPHAN)
        assert len(results) >= 4

    def test_by_ta_oncology(self) -> None:
        results = self.exp.by_ta("oncology")
        assert len(results) >= 5
        for r in results:
            assert r.therapeutic_area == "oncology"

    def test_by_ta_rare_disease(self) -> None:
        results = self.exp.by_ta("rare_disease")
        assert len(results) >= 5
        for r in results:
            assert r.therapeutic_area == "rare_disease"

    def test_by_ta_neurology(self) -> None:
        results = self.exp.by_ta("neurology")
        assert len(results) >= 2

    def test_crls_returns_only_crl_issued_true(self) -> None:
        crls = self.exp.crls()
        assert len(crls) >= 2
        for r in crls:
            assert r.crl_issued is True

    def test_at_least_2_crl_records_in_corpus(self) -> None:
        crls = self.exp.crls()
        assert len(crls) >= 2

    def test_approvals_returns_only_approved_true(self) -> None:
        approvals = self.exp.approvals()
        for r in approvals:
            assert r.approved is True

    def test_approvals_not_empty(self) -> None:
        approvals = self.exp.approvals()
        assert len(approvals) >= 12

    def test_lessons_for_modality_returns_nonempty_strings(self) -> None:
        lessons = self.exp.lessons_for_modality("small_molecule")
        assert len(lessons) >= 1
        for lesson in lessons:
            assert isinstance(lesson, str)
            assert len(lesson) > 0

    def test_lessons_for_unknown_modality_returns_empty_list(self) -> None:
        lessons = self.exp.lessons_for_modality("unknown_modality")
        assert lessons == []

    def test_all_records_at_least_15(self) -> None:
        all_r = self.exp.all_records()
        assert len(all_r) >= 15

    def test_all_records_no_empty_drug_names(self) -> None:
        for r in self.exp.all_records():
            assert r.drug_name != ""

    def test_all_records_no_empty_key_lessons(self) -> None:
        for r in self.exp.all_records():
            assert r.key_lesson != ""


# ---------------------------------------------------------------------------
# ControversyLayer
# ---------------------------------------------------------------------------


class TestControversyLayer:
    def setup_method(self) -> None:
        self.layer = ControversyLayer()

    def _make_ca(
        self,
        asset_id: str = "asset-1",
        controversy_type: ControversyType = ControversyType.TARGET_VALIDITY,
        severity: str = "medium",
        argument: str = "The target is not causal.",
    ) -> Counterargument:
        return Counterargument(
            asset_id=asset_id,
            controversy_type=controversy_type,
            argument=argument,
            severity=severity,
            added_date=date(2025, 1, 1),
        )

    def test_add_and_get_for_asset_roundtrip(self) -> None:
        ca = self._make_ca(asset_id="asset-A")
        self.layer.add_counterargument(ca)
        results = self.layer.get_for_asset("asset-A")
        assert len(results) == 1
        assert results[0].counterargument_id == ca.counterargument_id

    def test_get_for_asset_returns_empty_for_unknown(self) -> None:
        results = self.layer.get_for_asset("no-such-asset")
        assert results == []

    def test_add_multiple_counterarguments(self) -> None:
        ca1 = self._make_ca(asset_id="asset-B", argument="Arg 1")
        ca2 = self._make_ca(asset_id="asset-B", argument="Arg 2", severity="high")
        self.layer.add_counterargument(ca1)
        self.layer.add_counterargument(ca2)
        results = self.layer.get_for_asset("asset-B")
        assert len(results) == 2

    def test_resolve_sets_resolved_true(self) -> None:
        ca = self._make_ca(asset_id="asset-C", severity="high")
        self.layer.add_counterargument(ca)
        self.layer.resolve(ca.counterargument_id, rebuttal="We disagree because X.")
        updated = self.layer.get_for_asset("asset-C")[0]
        assert updated.resolved is True

    def test_resolve_stores_rebuttal(self) -> None:
        ca = self._make_ca(asset_id="asset-D")
        self.layer.add_counterargument(ca)
        self.layer.resolve(ca.counterargument_id, rebuttal="Rebuttal text here.")
        updated = self.layer.get_for_asset("asset-D")[0]
        assert updated.rebuttal == "Rebuttal text here."

    def test_resolve_unknown_id_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            self.layer.resolve("nonexistent-id", rebuttal="Nothing.")

    def test_assess_zero_scores_for_unknown_asset(self) -> None:
        assessment = self.layer.assess("ghost-asset")
        assert assessment.total_counterarguments == 0
        assert assessment.unresolved == 0
        assert assessment.critical_count == 0
        assert assessment.high_count == 0
        assert assessment.controversy_score == 0.0
        assert assessment.dominant_controversy is None

    def test_controversy_score_critical_weighted_more_than_low(self) -> None:
        # Add one critical and compare score vs one low
        layer_crit = ControversyLayer()
        ca_crit = Counterargument(asset_id="X", controversy_type=ControversyType.SAFETY_CONCERN,
                                   argument="Serious safety signal", severity="critical")
        layer_crit.add_counterargument(ca_crit)

        layer_low = ControversyLayer()
        ca_low = Counterargument(asset_id="X", controversy_type=ControversyType.SAFETY_CONCERN,
                                  argument="Minor concern", severity="low")
        layer_low.add_counterargument(ca_low)

        score_crit = layer_crit.assess("X").controversy_score
        score_low = layer_low.assess("X").controversy_score
        assert score_crit > score_low

    def test_resolved_items_not_counted_in_score_numerator(self) -> None:
        ca = self._make_ca(asset_id="asset-E", severity="critical")
        self.layer.add_counterargument(ca)
        score_before = self.layer.assess("asset-E").controversy_score
        self.layer.resolve(ca.counterargument_id, rebuttal="Resolved.")
        score_after = self.layer.assess("asset-E").controversy_score
        assert score_after < score_before

    def test_unresolved_critical_returns_only_critical_unresolved(self) -> None:
        ca_crit = Counterargument(asset_id="asset-F", controversy_type=ControversyType.SAFETY_CONCERN,
                                   argument="Critical issue", severity="critical")
        ca_high = Counterargument(asset_id="asset-F", controversy_type=ControversyType.TARGET_VALIDITY,
                                   argument="High issue", severity="high")
        self.layer.add_counterargument(ca_crit)
        self.layer.add_counterargument(ca_high)
        results = self.layer.unresolved_critical("asset-F")
        assert len(results) == 1
        assert results[0].severity == "critical"

    def test_unresolved_critical_excludes_resolved_critical(self) -> None:
        ca = Counterargument(asset_id="asset-G", controversy_type=ControversyType.SAFETY_CONCERN,
                              argument="Critical", severity="critical")
        self.layer.add_counterargument(ca)
        self.layer.resolve(ca.counterargument_id, rebuttal="Resolved critical.")
        results = self.layer.unresolved_critical("asset-G")
        assert len(results) == 0

    def test_dominant_controversy_is_most_common_type(self) -> None:
        # 2x SAFETY_CONCERN, 1x TARGET_VALIDITY -> dominant = SAFETY_CONCERN
        ca1 = Counterargument(asset_id="asset-H", controversy_type=ControversyType.SAFETY_CONCERN,
                               argument="Safety 1", severity="medium")
        ca2 = Counterargument(asset_id="asset-H", controversy_type=ControversyType.SAFETY_CONCERN,
                               argument="Safety 2", severity="high")
        ca3 = Counterargument(asset_id="asset-H", controversy_type=ControversyType.TARGET_VALIDITY,
                               argument="Target concern", severity="low")
        for ca in (ca1, ca2, ca3):
            self.layer.add_counterargument(ca)
        assessment = self.layer.assess("asset-H")
        assert assessment.dominant_controversy == ControversyType.SAFETY_CONCERN

    def test_total_counterarguments_count(self) -> None:
        for i in range(5):
            ca = Counterargument(asset_id="asset-I", controversy_type=ControversyType.MECHANISM_DEBATE,
                                  argument=f"Argument {i}", severity="medium")
            self.layer.add_counterargument(ca)
        assessment = self.layer.assess("asset-I")
        assert assessment.total_counterarguments == 5

    def test_unresolved_count(self) -> None:
        cas = []
        for i in range(4):
            ca = Counterargument(asset_id="asset-J", controversy_type=ControversyType.BIOMARKER_DISPUTE,
                                  argument=f"Arg {i}", severity="medium")
            self.layer.add_counterargument(ca)
            cas.append(ca)
        # Resolve 2
        self.layer.resolve(cas[0].counterargument_id, "Rebuttal 0")
        self.layer.resolve(cas[1].counterargument_id, "Rebuttal 1")
        assessment = self.layer.assess("asset-J")
        assert assessment.total_counterarguments == 4
        assert assessment.unresolved == 2

    def test_controversy_score_capped_at_1(self) -> None:
        # Add many critical unresolved items
        for i in range(10):
            ca = Counterargument(asset_id="asset-K", controversy_type=ControversyType.SAFETY_CONCERN,
                                  argument=f"Critical {i}", severity="critical")
            self.layer.add_counterargument(ca)
        assessment = self.layer.assess("asset-K")
        assert assessment.controversy_score <= 1.0

    def test_critical_and_high_counts_in_assessment(self) -> None:
        ca_crit = Counterargument(asset_id="asset-L", controversy_type=ControversyType.SAFETY_CONCERN,
                                   argument="Crit", severity="critical")
        ca_high = Counterargument(asset_id="asset-L", controversy_type=ControversyType.TARGET_VALIDITY,
                                   argument="High", severity="high")
        ca_med = Counterargument(asset_id="asset-L", controversy_type=ControversyType.TRANSLATIONAL_GAP,
                                  argument="Med", severity="medium")
        for ca in (ca_crit, ca_high, ca_med):
            self.layer.add_counterargument(ca)
        assessment = self.layer.assess("asset-L")
        assert assessment.critical_count == 1
        assert assessment.high_count == 1

    def test_assets_are_isolated_from_each_other(self) -> None:
        ca1 = Counterargument(asset_id="asset-M1", controversy_type=ControversyType.MECHANISM_DEBATE,
                               argument="Concern for M1", severity="high")
        ca2 = Counterargument(asset_id="asset-M2", controversy_type=ControversyType.TARGET_VALIDITY,
                               argument="Concern for M2", severity="low")
        self.layer.add_counterargument(ca1)
        self.layer.add_counterargument(ca2)
        assert len(self.layer.get_for_asset("asset-M1")) == 1
        assert len(self.layer.get_for_asset("asset-M2")) == 1

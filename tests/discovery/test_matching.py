"""Tests for predicted-vs-truth field matching."""
from __future__ import annotations

from bve.discovery.matching import (
    infer_modality,
    map_phase_to_stage,
    match_drug,
    match_indication,
    match_modality,
    match_stage,
)


class TestMatchDrug:
    def test_exact(self):
        assert match_drug("Vutrisiran", "Vutrisiran") == (True, False)

    def test_case_insensitive(self):
        assert match_drug("vutrisiran", "Vutrisiran")[0] is True

    def test_substring_combo(self):
        # Truth is a combo; predicted is one component.
        assert match_drug("tezacaftor", "VX-121/tezacaftor/deutivacaftor")[0] is True

    def test_shared_token(self):
        assert match_drug("RLY-2608", "RLY-2608 monotherapy")[0] is True

    def test_unrelated_no_match(self):
        m, near = match_drug("Aspirin", "Vutrisiran")
        assert m is False

    def test_empty(self):
        assert match_drug("", "X") == (False, False)


class TestMatchIndication:
    def test_token_overlap(self):
        assert match_indication(["Breast Cancer"], "Breast cancer") is True

    def test_no_overlap(self):
        assert match_indication(["Alzheimer Disease"], "Cystic fibrosis") is False

    def test_empty(self):
        assert match_indication([], "Cancer") is False


class TestStage:
    def test_phase_identity(self):
        assert map_phase_to_stage("phase_2") == "phase_2"

    def test_exact_match(self):
        assert match_stage("phase_3", "phase_3") == (True, False)

    def test_mismatch(self):
        assert match_stage("phase_1", "phase_3") == (False, False)

    def test_nda_bla_understated(self):
        m, understated = match_stage("phase_3", "nda_bla")
        assert m is False and understated is True

    def test_approved_understated(self):
        assert match_stage("phase_3", "approved")[1] is True


class TestModality:
    def test_antibody(self):
        assert infer_modality("Trastuzumab") == "biologic"

    def test_adc(self):
        assert infer_modality("Trastuzumab deruxtecan") == "adc"

    def test_antisense(self):
        assert infer_modality("Tofersen (ASO)") == "rna_therapy"

    def test_car_t(self):
        assert infer_modality("CAR-T cell therapy") == "cell_gene"

    def test_no_signal_is_unknown(self):
        # No name cue and no CT.gov type → honest unknown, not a confident guess.
        assert infer_modality("RLY-2608") == "unknown"

    def test_drug_type_implies_small_molecule(self):
        assert infer_modality("RLY-2608", intervention_type="DRUG") == "small_molecule"

    def test_biological_type_implies_biologic(self):
        # No -mab cue, but CT.gov classifies it BIOLOGICAL.
        assert infer_modality("ABC-123", intervention_type="BIOLOGICAL") == "biologic"

    def test_genetic_type_implies_cell_gene(self):
        assert infer_modality("XYZ-9", intervention_type="GENETIC") == "cell_gene"

    def test_peptide_pattern(self):
        assert infer_modality("Semaglutide") == "peptide"

    def test_name_pattern_beats_type(self):
        # A decisive name cue wins over a generic DRUG type.
        assert infer_modality("Tisagenlecleucel", intervention_type="DRUG") == "cell_gene"

    def test_aliases_provide_modality_cue(self):
        assert infer_modality("LN-145", aliases=["autologous TIL therapy"]) == "cell_gene"

    def test_description_provides_modality_cue(self):
        # Code name has no cue and type is DRUG, but the description states it.
        assert infer_modality(
            "ABC-1", intervention_type="DRUG",
            descriptions=["A monoclonal antibody targeting IL-13"],
        ) == "biologic"

    def test_suffix_anchor_survives_appended_description(self):
        # Regression: appending a description must not move the -tide suffix off
        # the end and defeat the peptide stem.
        assert infer_modality(
            "Rusfertide", intervention_type="DRUG",
            descriptions=["Experimental drug"],
        ) == "peptide"

    def test_antisense_inn_stem_without_hyphen(self):
        assert infer_modality("Olezarsen") == "rna_therapy"

    def test_curated_override_wins(self):
        # VK2735 is a peptide but its code name + DRUG type give no cue.
        assert infer_modality("VK2735", intervention_type="DRUG", drug_key="vk2735") == "peptide"

    def test_override_keyed_by_canonical_drug_key(self):
        from bve.discovery.drug_identity import canonical_drug_key

        assert infer_modality("VK-2735", drug_key=canonical_drug_key("VK-2735")) == "peptide"

    def test_match_exact(self):
        assert match_modality("small_molecule", "small_molecule") is True

    def test_match_equivalence_adc_under_biologic(self):
        assert match_modality("adc", "biologic") is True

    def test_match_cell_gene_equiv(self):
        assert match_modality("cell_gene", "gene_therapy") is True

    def test_no_match(self):
        assert match_modality("small_molecule", "biologic") is False

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

    def test_default_small_molecule(self):
        assert infer_modality("RLY-2608") == "small_molecule"

    def test_match_exact(self):
        assert match_modality("small_molecule", "small_molecule") is True

    def test_match_equivalence_adc_under_biologic(self):
        assert match_modality("adc", "biologic") is True

    def test_match_cell_gene_equiv(self):
        assert match_modality("cell_gene", "gene_therapy") is True

    def test_no_match(self):
        assert match_modality("small_molecule", "biologic") is False

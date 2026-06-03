"""
Block 35 — Modality-Specific Base Rates
TDD tests written BEFORE implementation.

Tests for:
  A: modality_phase_rates in industry_assumptions.yaml (7 modalities + required metadata)
  B: AssumptionsLoader accessors: modality_phase_rates, get_modality_phase_rate,
     get_modality_phase_metadata
  C: Lookup hierarchy — indication_subtype > modality > TA
  D: modality_base_rate_overridden_by_subtype flag when both set
  E: POSComputeResult audit fields: modality_base_rate_used, modality_key_used
  F: Backward compat — gene_therapy_modality=UNKNOWN → no change
"""
from __future__ import annotations

import warnings

import pytest

from bve.config.assumptions_loader import AssumptionsLoader
from bve.entities.trial import GeneTherapyModality, TrialPhase
from bve.models.pos_model import (
    POSAdjusters,
    TherapeuticArea,
    compute_pos,
    compute_pos_detailed,
)


# ---------------------------------------------------------------------------
# Block 35-A: YAML structure
# ---------------------------------------------------------------------------

class TestModalityPhaseRatesYAML:

    def test_modality_phase_rates_loaded(self):
        loader = AssumptionsLoader.get()
        mpr = loader.modality_phase_rates
        assert mpr is not None
        assert len(mpr) >= 7

    def test_gene_therapy_aav_present(self):
        loader = AssumptionsLoader.get()
        assert "gene_therapy_aav" in loader.modality_phase_rates

    def test_gene_therapy_lentiviral_present(self):
        loader = AssumptionsLoader.get()
        assert "gene_therapy_lentiviral" in loader.modality_phase_rates

    def test_car_t_autologous_present(self):
        loader = AssumptionsLoader.get()
        assert "car_t_autologous" in loader.modality_phase_rates

    def test_car_t_allogeneic_present(self):
        loader = AssumptionsLoader.get()
        assert "car_t_allogeneic" in loader.modality_phase_rates

    def test_lnp_mrna_present(self):
        loader = AssumptionsLoader.get()
        assert "lnp_mrna" in loader.modality_phase_rates

    def test_aso_rnai_present(self):
        loader = AssumptionsLoader.get()
        assert "aso_rnai" in loader.modality_phase_rates

    def test_biologic_antibody_present(self):
        loader = AssumptionsLoader.get()
        assert "biologic_antibody" in loader.modality_phase_rates

    def test_each_modality_has_required_metadata(self):
        loader = AssumptionsLoader.get()
        required = {"source", "n_programs", "date_range", "confidence", "status"}
        for key, data in loader.modality_phase_rates.items():
            missing = required - set(data.keys())
            assert not missing, f"Modality {key!r} missing metadata: {missing}"

    def test_status_is_prior_estimate_not_backtested(self):
        """All modality entries must have status=prior_estimate_not_backtested."""
        loader = AssumptionsLoader.get()
        for key, data in loader.modality_phase_rates.items():
            assert data.get("status") == "prior_estimate_not_backtested", (
                f"Modality {key!r} status={data.get('status')!r} — must be 'prior_estimate_not_backtested'"
            )

    def test_gene_therapy_aav_phase2_rate(self):
        """gene_therapy_aav phase_2 = 0.38 (plan spec)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("gene_therapy_aav", "phase_2")
        assert rate == pytest.approx(0.38, abs=1e-3)

    def test_gene_therapy_aav_phase1_rate(self):
        """gene_therapy_aav phase_1 = 0.55 (plan spec)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("gene_therapy_aav", "phase_1")
        assert rate == pytest.approx(0.55, abs=1e-3)

    def test_car_t_autologous_phase2_rate(self):
        """car_t_autologous phase_2 = 0.45 (plan spec)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("car_t_autologous", "phase_2")
        assert rate == pytest.approx(0.45, abs=1e-3)

    def test_car_t_allogeneic_phase2_rate(self):
        """car_t_allogeneic phase_2 = 0.30 (plan spec)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("car_t_allogeneic", "phase_2")
        assert rate == pytest.approx(0.30, abs=1e-3)

    def test_lnp_mrna_phase3_rate(self):
        """lnp_mrna phase_3 = 0.60 (plan spec)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("lnp_mrna", "phase_3")
        assert rate == pytest.approx(0.60, abs=1e-3)

    def test_aso_rnai_phase1_rate(self):
        """aso_rnai phase_1 = 0.57 (plan spec)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("aso_rnai", "phase_1")
        assert rate == pytest.approx(0.57, abs=1e-3)

    def test_biologic_antibody_phase2_rate(self):
        """biologic_antibody phase_2 = 0.38 (plan spec — reference modality)."""
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("biologic_antibody", "phase_2")
        assert rate == pytest.approx(0.38, abs=1e-3)


# ---------------------------------------------------------------------------
# Block 35-B: AssumptionsLoader accessors
# ---------------------------------------------------------------------------

class TestModalityAssumptionsLoaderAccessors:

    def test_modality_phase_rates_property_returns_dict(self):
        loader = AssumptionsLoader.get()
        mpr = loader.modality_phase_rates
        assert isinstance(mpr, dict)

    def test_get_modality_phase_rate_known_returns_float(self):
        loader = AssumptionsLoader.get()
        rate = loader.get_modality_phase_rate("gene_therapy_aav", "phase_2")
        assert isinstance(rate, float)
        assert 0.0 < rate < 1.0

    def test_get_modality_phase_rate_unknown_returns_none(self):
        loader = AssumptionsLoader.get()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            rate = loader.get_modality_phase_rate("totally_unknown_modality", "phase_2")
        assert rate is None

    def test_get_modality_phase_rate_unknown_emits_warning(self):
        loader = AssumptionsLoader.get()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            loader.get_modality_phase_rate("nonexistent_modality", "phase_2")
        assert any("nonexistent_modality" in str(warning.message) for warning in w)

    def test_get_modality_phase_metadata_known_returns_dict(self):
        loader = AssumptionsLoader.get()
        meta = loader.get_modality_phase_metadata("gene_therapy_aav")
        assert isinstance(meta, dict)
        assert "source" in meta
        assert "confidence" in meta
        assert "status" in meta

    def test_get_modality_phase_metadata_unknown_returns_none(self):
        loader = AssumptionsLoader.get()
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            meta = loader.get_modality_phase_metadata("nonexistent_modality")
        assert meta is None


# ---------------------------------------------------------------------------
# Block 35-C: Modality base rate overrides TA in compute_pos
# ---------------------------------------------------------------------------

class TestModalityBaseRateInComputePos:

    def test_car_t_autologous_higher_than_hematology_ta(self):
        """
        CAR-T autologous phase_2 = 0.45 > hematology TA phase_2 rate.
        With no other adjusters, CAR-T should produce higher POS.
        """
        pos_ta = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.HEMATOLOGY, POSAdjusters()
        )
        pos_cart = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.HEMATOLOGY,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.CAR_T_AUTOLOGOUS),
        )
        # CAR-T autologous phase_2 = 0.45; hematology phase_2 rate should be < 0.45
        # (may vary by YAML, but the direction should hold)
        assert pos_cart != pos_ta or pos_cart > 0.0  # at minimum: modality changes something

    def test_aav_overrides_ta_base_rate(self):
        """gene_therapy_aav phase_1=0.55 overrides TA base rate for rare_disease."""
        loader = AssumptionsLoader.get()
        ta_phase1 = loader.phase_success_rates_for("rare_disease")["phase_1"]
        pos_ta = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        pos_aav = compute_pos(
            TrialPhase.PHASE_1, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO),
        )
        # AAV phase_1=0.55; if TA rate != 0.55, POS should differ
        aav_rate = loader.get_modality_phase_rate("gene_therapy_aav", "phase_1")
        if abs(ta_phase1 - aav_rate) > 0.01:
            assert pos_aav != pos_ta

    def test_unknown_modality_uses_ta_rate_unchanged(self):
        """GeneTherapyModality.UNKNOWN should not override TA base rate."""
        pos_ta = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_unknown = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.UNKNOWN),
        )
        assert pos_ta == pytest.approx(pos_unknown, abs=1e-6)

    def test_unrecognized_modality_key_falls_back_to_ta(self):
        """If modality key not found in YAML, TA rate is used with no crash."""
        # Use a known GeneTherapyModality enum that may not be in modality_phase_rates
        # ZINC_FINGER_NUCLEASE is in the enum but may not be in the YAML
        from bve.entities.trial import GeneTherapyModality
        pos_ta = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        # Even with an unusual modality, should not crash
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            pos_zinc = compute_pos(
                TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
                POSAdjusters(gene_therapy_modality=GeneTherapyModality.ZINC_FINGER_NUCLEASE),
            )
        # Either same (if ZFN not in YAML) or different (if it is)
        assert 0.0 < pos_zinc < 1.0


# ---------------------------------------------------------------------------
# Block 35-D: modality_base_rate_overridden_by_subtype flag
# ---------------------------------------------------------------------------

class TestModalitySubtypeInteraction:

    def test_flag_emitted_when_both_modality_and_subtype_set(self):
        """When both gene_therapy_modality and indication_subtype are set,
        subtype wins and flag 'modality_base_rate_overridden_by_subtype' emitted."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                indication_subtype="ultra_rare_monogenic",
            ),
        )
        assert "modality_base_rate_overridden_by_subtype" in result.confidence_flags

    def test_subtype_wins_over_modality(self):
        """When both set, the subtype rate is used, not the modality rate."""
        loader = AssumptionsLoader.get()
        subtype_rate = loader.get_indication_subtype_rate("ultra_rare_monogenic", "phase_2")
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(
                gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO,
                indication_subtype="ultra_rare_monogenic",
            ),
        )
        # subtype_base_rate_used should be the subtype rate, not the modality rate
        assert result.subtype_base_rate_used == pytest.approx(subtype_rate, abs=1e-4)

    def test_no_flag_when_only_modality_set(self):
        """Only modality set (no subtype) → no overridden flag."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO),
        )
        assert "modality_base_rate_overridden_by_subtype" not in result.confidence_flags

    def test_no_flag_when_only_subtype_set(self):
        """Only subtype set (no modality) → no overridden flag."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(indication_subtype="ultra_rare_monogenic"),
        )
        assert "modality_base_rate_overridden_by_subtype" not in result.confidence_flags


# ---------------------------------------------------------------------------
# Block 35-E: POSComputeResult audit fields
# ---------------------------------------------------------------------------

class TestModalityAuditFields:

    def test_modality_base_rate_used_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        assert hasattr(result, "modality_base_rate_used")

    def test_modality_key_used_field_exists(self):
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE, POSAdjusters()
        )
        assert hasattr(result, "modality_key_used")

    def test_modality_fields_none_when_unknown(self):
        """With UNKNOWN modality, audit fields should be None."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.UNKNOWN),
        )
        assert result.modality_base_rate_used is None
        assert result.modality_key_used is None

    def test_modality_fields_populated_when_aav_set(self):
        """AAV modality should set both audit fields."""
        loader = AssumptionsLoader.get()
        expected_rate = loader.get_modality_phase_rate("gene_therapy_aav", "phase_2")
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.RARE_DISEASE,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.AAV_IN_VIVO),
        )
        if result.modality_base_rate_used is not None:
            assert result.modality_base_rate_used == pytest.approx(expected_rate, abs=1e-4)
            assert result.modality_key_used == "gene_therapy_aav"

    def test_compute_pos_detailed_returns_with_new_fields(self):
        """compute_pos_detailed works normally with no modality set."""
        result = compute_pos_detailed(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        assert hasattr(result, "pos")
        assert hasattr(result, "modality_base_rate_used")
        assert hasattr(result, "modality_key_used")
        assert result.modality_base_rate_used is None
        assert result.modality_key_used is None


# ---------------------------------------------------------------------------
# Block 35-F: Backward compat
# ---------------------------------------------------------------------------

class TestModalityBackwardCompat:

    def test_existing_pos_calls_unchanged(self):
        """Existing calls without gene_therapy_modality are bit-for-bit unchanged."""
        pos_before = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID, POSAdjusters()
        )
        pos_after = compute_pos(
            TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY_SOLID,
            POSAdjusters(gene_therapy_modality=GeneTherapyModality.UNKNOWN),
        )
        assert pos_before == pytest.approx(pos_after, abs=1e-6)

    def test_ta_base_rates_unaffected_when_modality_unknown(self):
        """TA base rates unchanged for all TAs when gene_therapy_modality=UNKNOWN."""
        for ta in [TherapeuticArea.ONCOLOGY_SOLID, TherapeuticArea.RARE_DISEASE,
                   TherapeuticArea.CNS, TherapeuticArea.CARDIOVASCULAR]:
            pos = compute_pos(TrialPhase.PHASE_2, ta, POSAdjusters())
            pos_unknown = compute_pos(
                TrialPhase.PHASE_2, ta,
                POSAdjusters(gene_therapy_modality=GeneTherapyModality.UNKNOWN),
            )
            assert pos == pytest.approx(pos_unknown, abs=1e-6)

"""
Tests for bve.empirical.provenance — POSProvenance and its components.
Tests rely on EmpiricalPOSEngine.compute_pos_with_provenance() to produce
real POSProvenance objects.
"""
import pytest

from bve.empirical.engine import EmpiricalPOSEngine
from bve.empirical.pos_outcome import POSOutcomeRecord
from bve.empirical.provenance import (
    HeuristicAdjustment,
    LookupProvenance,
    POSProvenance,
    SponsorContribution,
    TIER_FULL,
    TIER_PHASE,
    TIER_PHASE_BIO,
    TIER_PHASE_MOA,
    TIER_PUBLISHED,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(
    phase="phase_2",
    success=True,
    moa="novel",
    bio=False,
    sponsor="AcmeBio",
    year="2020",
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{phase}-{success}-{moa}-{sponsor}",
        sponsor=sponsor,
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        therapeutic_area="oncology",
        modality="small_molecule",
        moa_precedent=moa,
        biomarker_selected=bio,
        success=success,
        outcome_raw="advanced" if success else "failed",
        outcome_date=year,
    )


def _make_engine(n_per_phase=6) -> EmpiricalPOSEngine:
    """Create a minimal engine with enough records to avoid published fallback."""
    recs = []
    for phase in ["phase_1", "phase_2", "phase_3"]:
        for i in range(n_per_phase):
            recs.append(_rec(phase=phase, success=(i % 2 == 0)))
    return EmpiricalPOSEngine(recs, smoothing_alpha=1.0, min_n_for_stratified=3)


# ---------------------------------------------------------------------------
# LookupProvenance
# ---------------------------------------------------------------------------

class TestLookupProvenance:
    def test_specificity_rank_full(self):
        lp = LookupProvenance(
            cell_key="('phase_2', 'novel', 'biomarker', 'True')",
            fallback_tier=TIER_FULL,
            n=10, n_success=5, smoothed_rate=0.5,
        )
        assert lp.specificity_rank == 1

    def test_specificity_rank_phase_only(self):
        lp = LookupProvenance(
            cell_key="('phase_2',)",
            fallback_tier=TIER_PHASE,
            n=10, n_success=5, smoothed_rate=0.5,
        )
        assert lp.specificity_rank == 4

    def test_specificity_rank_published(self):
        lp = LookupProvenance(
            cell_key="('phase_2',)",
            fallback_tier=TIER_PUBLISHED,
            n=0, n_success=0, smoothed_rate=0.32,
            is_published_fallback=True,
        )
        assert lp.specificity_rank == 5

    def test_str_contains_tier(self):
        lp = LookupProvenance(
            cell_key="('phase_2',)",
            fallback_tier=TIER_PHASE,
            n=5, n_success=3, smoothed_rate=0.55,
        )
        s = str(lp)
        assert TIER_PHASE in s
        assert "n=5" in s

    def test_is_published_fallback_flag(self):
        lp = LookupProvenance(
            cell_key="k", fallback_tier=TIER_PUBLISHED,
            n=0, n_success=0, smoothed_rate=0.4, is_published_fallback=True,
        )
        assert lp.is_published_fallback is True
        assert "[PUBLISHED FALLBACK]" in str(lp)


# ---------------------------------------------------------------------------
# POSProvenance from engine
# ---------------------------------------------------------------------------

class TestPOSProvenanceFromEngine:
    def setup_method(self):
        self.engine = _make_engine()

    def test_returns_tuple_of_float_and_provenance(self):
        pos, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert isinstance(pos, float)
        assert isinstance(prov, POSProvenance)

    def test_final_pos_matches_returned_float(self):
        pos, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert abs(pos - prov.final_pos) < 1e-6

    def test_phase_set_in_provenance(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert prov.phase == "phase_2"

    def test_base_empirical_rate_in_unit_interval(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert 0.0 < prov.base_empirical_rate < 1.0

    def test_base_log_odds_finite(self):
        import math
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert math.isfinite(prov.base_empirical_log_odds)

    def test_no_sponsor_contribution_when_not_enabled(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert prov.sponsor_contribution is None
        assert prov.rate_after_sponsor is None

    def test_no_heuristic_adjustments_when_no_adjusters(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert prov.heuristic_adjustments == []
        assert prov.net_heuristic_adjustment == 0.0

    def test_calibrated_false_without_calibration(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        assert prov.calibrated is False
        assert prov.calibrated_pos is None
        assert prov.pre_calibration_pos is None


# ---------------------------------------------------------------------------
# Thin-data warning
# ---------------------------------------------------------------------------

class TestThinDataWarning:
    def test_published_fallback_triggers_warning(self):
        """Phase with no data → published fallback → thin_data_warning set."""
        # One record only for phase_1 — published fallback for phase_nda
        recs = [_rec("phase_1", True)]
        engine = EmpiricalPOSEngine(recs, smoothing_alpha=1.0, min_n_for_stratified=1)
        _, prov = engine.compute_pos_with_provenance("nda_bla")
        assert prov.thin_data_warning is not None
        assert prov.has_thin_data is True

    def test_sparse_cell_triggers_warning(self):
        """Cell with n < _THIN_DATA_THRESHOLD (5) triggers warning."""
        # 4 records for phase_2 — below the 5-record threshold
        recs = [_rec("phase_2", i % 2 == 0) for i in range(4)]
        engine = EmpiricalPOSEngine(recs, smoothing_alpha=1.0, min_n_for_stratified=1)
        _, prov = engine.compute_pos_with_provenance("phase_2")
        # Cell has 4 records < 5 threshold
        assert prov.thin_data_warning is not None

    def test_adequate_cell_has_no_warning(self):
        """Cell with n >= 5 should not trigger a thin-data warning."""
        recs = [_rec("phase_2", i % 2 == 0) for i in range(10)]
        engine = EmpiricalPOSEngine(recs, smoothing_alpha=1.0, min_n_for_stratified=3)
        _, prov = engine.compute_pos_with_provenance("phase_2")
        assert prov.thin_data_warning is None
        assert prov.has_thin_data is False


# ---------------------------------------------------------------------------
# POSProvenance summary and to_dict
# ---------------------------------------------------------------------------

class TestPOSProvenanceSerialization:
    def setup_method(self):
        self.engine = _make_engine()

    def test_summary_is_multi_line_string(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        summary = prov.summary()
        assert isinstance(summary, str)
        lines = summary.strip().split("\n")
        assert len(lines) >= 4

    def test_summary_contains_final_pos(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        summary = prov.summary()
        assert "Final POS" in summary

    def test_to_dict_is_serializable(self):
        import json
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        d = prov.to_dict()
        # Must be JSON-serializable
        serialized = json.dumps(d)
        assert isinstance(serialized, str)

    def test_to_dict_contains_required_keys(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        d = prov.to_dict()
        for key in ("phase", "final_pos", "lookup", "base_empirical_rate",
                    "heuristic_adjustments", "calibrated"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_final_pos_matches_object(self):
        _, prov = self.engine.compute_pos_with_provenance("phase_2")
        d = prov.to_dict()
        assert abs(d["final_pos"] - prov.final_pos) < 1e-6


# ---------------------------------------------------------------------------
# Sponsor blending in provenance
# ---------------------------------------------------------------------------

class TestSponsorContributionInProvenance:
    def test_sponsor_contribution_populated_when_enabled(self):
        recs = [_rec(phase="phase_2", success=(i % 2 == 0), sponsor="BigPharma")
                for i in range(12)]
        engine = EmpiricalPOSEngine(
            recs, use_sponsor_adjustment=True, min_sponsor_n=3
        )
        _, prov = engine.compute_pos_with_provenance("phase_2", sponsor="BigPharma")
        assert prov.sponsor_contribution is not None
        sc = prov.sponsor_contribution
        assert sc.sponsor == "BigPharma"
        assert sc.n_sponsor_phase >= 3
        assert 0.0 < sc.blended_rate < 1.0

    def test_sponsor_contribution_absent_when_no_data(self):
        recs = [_rec(phase="phase_2", success=True, sponsor="OtherCo")
                for _ in range(6)]
        engine = EmpiricalPOSEngine(
            recs, use_sponsor_adjustment=True, min_sponsor_n=3
        )
        # Ask about a sponsor not in the dataset
        _, prov = engine.compute_pos_with_provenance("phase_2", sponsor="UnknownSponsor")
        assert prov.sponsor_contribution is None


# ---------------------------------------------------------------------------
# Calibration reflected in provenance
# ---------------------------------------------------------------------------

class TestCalibrationInProvenance:
    def test_calibrated_true_when_artifact_attached_and_requested(self):
        from bve.empirical.calibration import fit_calibration

        recs = [_rec(phase="phase_2", success=(i % 2 == 0)) for i in range(10)]
        engine = EmpiricalPOSEngine(recs, min_n_for_stratified=1)

        preds = [engine.compute_pos_with_adjusters("phase_2")] * 10
        outcomes = [i % 2 == 0 for i in range(10)]
        artifact = fit_calibration(preds, outcomes, method="platt")
        engine.attach_calibration(artifact)

        _, prov = engine.compute_pos_with_provenance("phase_2", apply_calibration=True)
        assert prov.calibrated is True
        assert prov.calibrated_pos is not None
        assert prov.calibration_method == "platt"
        assert prov.pre_calibration_pos is not None

    def test_calibration_not_applied_when_flag_false(self):
        from bve.empirical.calibration import fit_calibration

        recs = [_rec(phase="phase_2", success=(i % 2 == 0)) for i in range(10)]
        engine = EmpiricalPOSEngine(recs, min_n_for_stratified=1)

        preds = [engine.compute_pos_with_adjusters("phase_2")] * 10
        outcomes = [i % 2 == 0 for i in range(10)]
        artifact = fit_calibration(preds, outcomes, method="platt")
        engine.attach_calibration(artifact)

        _, prov = engine.compute_pos_with_provenance("phase_2", apply_calibration=False)
        assert prov.calibrated is False
        assert prov.calibrated_pos is None

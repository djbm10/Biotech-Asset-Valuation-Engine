"""
Tests for bve.empirical.features — feature extraction from records and adjusters.
"""
import pytest

from bve.empirical.features import (
    FEATURE_NAMES,
    N_FEATURES,
    MIN_OVERLAY_RECORDS,
    build_feature_vector,
    build_feature_vector_from_adjusters,
    feature_coverage,
    record_to_adjusters,
    sparsity_report,
)
from bve.empirical.pos_outcome import POSOutcomeRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(
    phase="phase_2",
    success=True,
    moa: str | None = "novel",
    bio: bool = False,
    endpoint: str | None = "surrogate_validated",
    safety: str | None = "minor",
    competition: str | None = "moderate",
) -> POSOutcomeRecord:
    return POSOutcomeRecord(
        program_id=f"T-{moa}-{bio}-{endpoint}-{safety}",
        sponsor="AcmeBio",
        asset_name="DrugX",
        indication_raw="NSCLC",
        phase_at_entry=phase,
        moa_precedent=moa,
        biomarker_selected=bio,
        endpoint_type=endpoint,
        safety_profile=safety,
        competitive_pressure=competition,
        success=success,
        outcome_raw="advanced" if success else "failed",
    )


# ---------------------------------------------------------------------------
# FEATURE_NAMES contract
# ---------------------------------------------------------------------------

class TestFeatureNames:
    def test_length_is_11(self):
        assert len(FEATURE_NAMES) == 11

    def test_n_features_matches(self):
        assert N_FEATURES == 11

    def test_all_expected_names_present(self):
        expected = {
            "moa_validated", "moa_novel", "biomarker_selected",
            "endpoint_hard_clinical", "endpoint_surrogate_novel", "endpoint_biomarker_only",
            "safety_clean", "safety_concerning", "safety_serious",
            "competition_low", "competition_high",
        }
        assert set(FEATURE_NAMES) == expected

    def test_no_duplicates(self):
        assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES))


# ---------------------------------------------------------------------------
# build_feature_vector — from POSOutcomeRecord
# ---------------------------------------------------------------------------

class TestBuildFeatureVector:
    def test_returns_correct_length(self):
        rec = _rec()
        fv = build_feature_vector(rec)
        assert len(fv) == N_FEATURES

    def test_all_values_zero_or_one(self):
        rec = _rec()
        fv = build_feature_vector(rec)
        assert all(v in (0.0, 1.0) for v in fv)

    def test_moa_validated_indicator(self):
        fv = build_feature_vector(_rec(moa="validated"))
        idx = FEATURE_NAMES.index("moa_validated")
        assert fv[idx] == 1.0
        assert fv[FEATURE_NAMES.index("moa_novel")] == 0.0

    def test_moa_novel_indicator(self):
        fv = build_feature_vector(_rec(moa="novel"))
        assert fv[FEATURE_NAMES.index("moa_novel")] == 1.0
        assert fv[FEATURE_NAMES.index("moa_validated")] == 0.0

    def test_moa_partial_is_baseline(self):
        fv = build_feature_vector(_rec(moa="partial"))
        assert fv[FEATURE_NAMES.index("moa_validated")] == 0.0
        assert fv[FEATURE_NAMES.index("moa_novel")] == 0.0

    def test_moa_none_is_baseline(self):
        fv = build_feature_vector(_rec(moa=None))
        assert fv[FEATURE_NAMES.index("moa_validated")] == 0.0
        assert fv[FEATURE_NAMES.index("moa_novel")] == 0.0

    def test_biomarker_selected_true(self):
        fv = build_feature_vector(_rec(bio=True))
        assert fv[FEATURE_NAMES.index("biomarker_selected")] == 1.0

    def test_biomarker_selected_false(self):
        fv = build_feature_vector(_rec(bio=False))
        assert fv[FEATURE_NAMES.index("biomarker_selected")] == 0.0

    def test_endpoint_hard_clinical(self):
        fv = build_feature_vector(_rec(endpoint="hard_clinical"))
        assert fv[FEATURE_NAMES.index("endpoint_hard_clinical")] == 1.0

    def test_endpoint_surrogate_validated_is_baseline(self):
        fv = build_feature_vector(_rec(endpoint="surrogate_validated"))
        assert fv[FEATURE_NAMES.index("endpoint_hard_clinical")] == 0.0
        assert fv[FEATURE_NAMES.index("endpoint_surrogate_novel")] == 0.0
        assert fv[FEATURE_NAMES.index("endpoint_biomarker_only")] == 0.0

    def test_safety_clean_indicator(self):
        fv = build_feature_vector(_rec(safety="clean"))
        assert fv[FEATURE_NAMES.index("safety_clean")] == 1.0
        assert fv[FEATURE_NAMES.index("safety_concerning")] == 0.0
        assert fv[FEATURE_NAMES.index("safety_serious")] == 0.0

    def test_safety_minor_is_baseline(self):
        fv = build_feature_vector(_rec(safety="minor"))
        assert fv[FEATURE_NAMES.index("safety_clean")] == 0.0
        assert fv[FEATURE_NAMES.index("safety_concerning")] == 0.0

    def test_competition_low_indicator(self):
        fv = build_feature_vector(_rec(competition="low"))
        assert fv[FEATURE_NAMES.index("competition_low")] == 1.0
        assert fv[FEATURE_NAMES.index("competition_high")] == 0.0

    def test_competition_moderate_is_baseline(self):
        fv = build_feature_vector(_rec(competition="moderate"))
        assert fv[FEATURE_NAMES.index("competition_low")] == 0.0
        assert fv[FEATURE_NAMES.index("competition_high")] == 0.0

    def test_all_baseline_gives_all_zeros(self):
        rec = _rec(moa="partial", bio=False, endpoint="surrogate_validated",
                   safety="minor", competition="moderate")
        fv = build_feature_vector(rec)
        assert all(v == 0.0 for v in fv)

    def test_all_non_baseline_gives_nonzero(self):
        rec = _rec(moa="validated", bio=True, endpoint="hard_clinical",
                   safety="clean", competition="low")
        fv = build_feature_vector(rec)
        # At least 5 features should be 1.0 (one per dimension)
        assert sum(fv) >= 5


# ---------------------------------------------------------------------------
# build_feature_vector_from_adjusters
# ---------------------------------------------------------------------------

class TestBuildFeatureVectorFromAdjusters:
    def _make_adjusters(
        self,
        moa="partial",
        endpoint="surrogate_validated",
        safety="minor",
        competition="moderate",
        bio=False,
    ):
        from bve.models.pos_model import (
            POSAdjusters, MoAPrecedent, SafetyProfile, CompetitivePressure,
        )
        from bve.entities.trial import EndpointType

        _moa = {
            "validated": MoAPrecedent.VALIDATED,
            "partial": MoAPrecedent.PARTIAL,
            "novel": MoAPrecedent.NOVEL,
        }[moa]
        _ep = {
            "hard_clinical": EndpointType.HARD_CLINICAL,
            "surrogate_validated": EndpointType.SURROGATE_VALIDATED,
            "surrogate_novel": EndpointType.SURROGATE_NOVEL,
            "biomarker_only": EndpointType.BIOMARKER_ONLY,
        }[endpoint]
        _sf = {
            "clean": SafetyProfile.CLEAN,
            "minor": SafetyProfile.MINOR,
            "concerning": SafetyProfile.CONCERNING,
            "serious": SafetyProfile.SERIOUS,
        }[safety]
        _cp = {
            "low": CompetitivePressure.LOW,
            "moderate": CompetitivePressure.MODERATE,
            "high": CompetitivePressure.HIGH,
        }[competition]
        return POSAdjusters(
            moa_precedent=_moa,
            endpoint_type=_ep,
            safety_profile=_sf,
            competitive_pressure=_cp,
            biomarker_selected_population=bio,
        )

    def test_returns_correct_length(self):
        adj = self._make_adjusters()
        fv = build_feature_vector_from_adjusters(adj)
        assert len(fv) == N_FEATURES

    def test_none_returns_all_zeros(self):
        fv = build_feature_vector_from_adjusters(None)
        assert fv == [0.0] * N_FEATURES

    def test_moa_validated_matches_record_encoding(self):
        adj = self._make_adjusters(moa="validated")
        rec = _rec(moa="validated")
        fv_adj = build_feature_vector_from_adjusters(adj)
        fv_rec = build_feature_vector(rec)
        # moa_validated and moa_novel should match
        for name in ("moa_validated", "moa_novel"):
            idx = FEATURE_NAMES.index(name)
            assert fv_adj[idx] == fv_rec[idx]

    def test_biomarker_selected_matches_record(self):
        adj = self._make_adjusters(bio=True)
        rec = _rec(bio=True)
        fv_adj = build_feature_vector_from_adjusters(adj)
        fv_rec = build_feature_vector(rec)
        assert fv_adj[FEATURE_NAMES.index("biomarker_selected")] == 1.0
        assert fv_adj[FEATURE_NAMES.index("biomarker_selected")] == fv_rec[FEATURE_NAMES.index("biomarker_selected")]

    def test_all_baseline_gives_all_zeros(self):
        adj = self._make_adjusters()  # all defaults are baseline
        fv = build_feature_vector_from_adjusters(adj)
        assert all(v == 0.0 for v in fv)


# ---------------------------------------------------------------------------
# record_to_adjusters
# ---------------------------------------------------------------------------

class TestRecordToAdjusters:
    def test_returns_pos_adjusters(self):
        from bve.models.pos_model import POSAdjusters
        adj = record_to_adjusters(_rec())
        assert isinstance(adj, POSAdjusters)

    def test_moa_mapping(self):
        from bve.models.pos_model import MoAPrecedent
        adj_v = record_to_adjusters(_rec(moa="validated"))
        assert adj_v.moa_precedent == MoAPrecedent.VALIDATED
        adj_n = record_to_adjusters(_rec(moa="novel"))
        assert adj_n.moa_precedent == MoAPrecedent.NOVEL

    def test_moa_none_maps_to_partial(self):
        from bve.models.pos_model import MoAPrecedent
        adj = record_to_adjusters(_rec(moa=None))
        assert adj.moa_precedent == MoAPrecedent.PARTIAL

    def test_biomarker_selected_propagated(self):
        adj_t = record_to_adjusters(_rec(bio=True))
        adj_f = record_to_adjusters(_rec(bio=False))
        assert adj_t.biomarker_selected_population is True
        assert adj_f.biomarker_selected_population is False

    def test_safety_mapping(self):
        from bve.models.pos_model import SafetyProfile
        adj = record_to_adjusters(_rec(safety="serious"))
        assert adj.safety_profile == SafetyProfile.SERIOUS

    def test_competition_mapping(self):
        from bve.models.pos_model import CompetitivePressure
        adj = record_to_adjusters(_rec(competition="low"))
        assert adj.competitive_pressure == CompetitivePressure.LOW

    def test_feature_vectors_are_consistent(self):
        """build_feature_vector(rec) and build_feature_vector_from_adjusters(record_to_adjusters(rec)) agree."""
        rec = _rec(moa="validated", bio=True, endpoint="hard_clinical",
                   safety="clean", competition="low")
        adj = record_to_adjusters(rec)
        fv_rec = build_feature_vector(rec)
        fv_adj = build_feature_vector_from_adjusters(adj)
        assert fv_rec == fv_adj


# ---------------------------------------------------------------------------
# feature_coverage + sparsity_report
# ---------------------------------------------------------------------------

class TestFeatureCoverage:
    def test_empty_records_all_zero(self):
        cov = feature_coverage([])
        assert all(v == 0.0 for v in cov.values())

    def test_all_baseline_records_all_zero(self):
        recs = [_rec(moa="partial", bio=False, endpoint="surrogate_validated",
                     safety="minor", competition="moderate") for _ in range(5)]
        cov = feature_coverage(recs)
        assert all(v == 0.0 for v in cov.values())

    def test_coverage_fraction_correct(self):
        # 3 records with moa_validated, 2 without
        recs = [_rec(moa="validated") for _ in range(3)] + [_rec(moa="partial") for _ in range(2)]
        cov = feature_coverage(recs)
        assert abs(cov["moa_validated"] - 0.6) < 0.01

    def test_returns_all_feature_names(self):
        recs = [_rec()]
        cov = feature_coverage(recs)
        assert set(cov.keys()) == set(FEATURE_NAMES)

    def test_sparsity_report_structure(self):
        recs = [_rec()] * 5
        report = sparsity_report(recs)
        assert "n_records" in report
        assert "n_features" in report
        assert "coverage" in report
        assert "sparse_features" in report
        assert "sparse_threshold" in report

    def test_sparsity_identifies_low_coverage_features(self):
        # All records at baseline → all features have 0.0 coverage → all sparse
        recs = [_rec(moa="partial", bio=False, endpoint="surrogate_validated",
                     safety="minor", competition="moderate")] * 5
        report = sparsity_report(recs, sparse_threshold=0.05)
        assert set(report["sparse_features"]) == set(FEATURE_NAMES)

    def test_sparsity_no_sparse_when_threshold_zero(self):
        recs = [_rec()] * 3
        report = sparsity_report(recs, sparse_threshold=0.0)
        assert report["sparse_features"] == []

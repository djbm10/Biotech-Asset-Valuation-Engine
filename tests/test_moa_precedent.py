"""Tests for the expanded MoAPrecedent 8-tier table and MoAExceptionFlag overrides."""
from __future__ import annotations

import pytest

from bve.entities.asset import TherapeuticArea
from bve.entities.trial import TrialPhase
from bve.models.pos_model import (
    MoAExceptionFlag,
    MoAPrecedent,
    POSAdjusters,
    _MOA_EXCEPTION_LOGODDS,
    _MOA_LOGODDS,
    compute_pos,
)


# ---------------------------------------------------------------------------
# Tier ordering
# ---------------------------------------------------------------------------

class TestMoaLogoddsOrdering:
    def test_validated_highest(self):
        assert _MOA_LOGODDS[MoAPrecedent.VALIDATED] == pytest.approx(0.35)
        assert _MOA_LOGODDS[MoAPrecedent.VALIDATED_CLASS] == pytest.approx(0.35)

    def test_descending_order(self):
        tiers = [
            MoAPrecedent.VALIDATED,
            MoAPrecedent.CLINICALLY_VALIDATED_TARGET,
            MoAPrecedent.PATHWAY_VALIDATED,
            MoAPrecedent.PARTIAL,
            MoAPrecedent.PRECLINICAL_ONLY,
            MoAPrecedent.NOVEL,
            MoAPrecedent.PRIOR_FAILURES,
            MoAPrecedent.KNOWN_LIABILITY,
        ]
        scores = [_MOA_LOGODDS[t] for t in tiers]
        assert scores == sorted(scores, reverse=True), "Tiers must be in descending log-odds order"

    def test_partial_is_zero_reference(self):
        assert _MOA_LOGODDS[MoAPrecedent.PARTIAL] == 0.00

    def test_known_liability_most_negative(self):
        assert _MOA_LOGODDS[MoAPrecedent.KNOWN_LIABILITY] == pytest.approx(-0.60)

    def test_all_eight_tiers_present(self):
        expected = {
            MoAPrecedent.VALIDATED, MoAPrecedent.VALIDATED_CLASS,
            MoAPrecedent.CLINICALLY_VALIDATED_TARGET, MoAPrecedent.PATHWAY_VALIDATED,
            MoAPrecedent.PARTIAL, MoAPrecedent.PRECLINICAL_ONLY,
            MoAPrecedent.NOVEL, MoAPrecedent.PRIOR_FAILURES,
            MoAPrecedent.KNOWN_LIABILITY,
        }
        assert set(_MOA_LOGODDS.keys()) == expected


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_validated_unchanged(self):
        """VALIDATED must remain at +0.35 to avoid breaking existing configs."""
        assert _MOA_LOGODDS[MoAPrecedent.VALIDATED] == pytest.approx(0.35)

    def test_partial_unchanged(self):
        assert _MOA_LOGODDS[MoAPrecedent.PARTIAL] == 0.00

    def test_novel_unchanged(self):
        assert _MOA_LOGODDS[MoAPrecedent.NOVEL] == pytest.approx(-0.35)

    def test_validated_and_validated_class_identical(self):
        assert _MOA_LOGODDS[MoAPrecedent.VALIDATED] == _MOA_LOGODDS[MoAPrecedent.VALIDATED_CLASS]

    def test_legacy_string_values_parseable(self):
        """Existing YAML values 'validated', 'partial', 'novel' must still parse."""
        assert MoAPrecedent("validated") == MoAPrecedent.VALIDATED
        assert MoAPrecedent("partial") == MoAPrecedent.PARTIAL
        assert MoAPrecedent("novel") == MoAPrecedent.NOVEL


# ---------------------------------------------------------------------------
# New tier scores
# ---------------------------------------------------------------------------

class TestNewTiers:
    def test_clinically_validated_between_validated_and_partial(self):
        cvt = _MOA_LOGODDS[MoAPrecedent.CLINICALLY_VALIDATED_TARGET]
        assert _MOA_LOGODDS[MoAPrecedent.PARTIAL] < cvt < _MOA_LOGODDS[MoAPrecedent.VALIDATED]

    def test_pathway_validated_between_partial_and_cvt(self):
        pw = _MOA_LOGODDS[MoAPrecedent.PATHWAY_VALIDATED]
        assert _MOA_LOGODDS[MoAPrecedent.PARTIAL] <= pw <= _MOA_LOGODDS[MoAPrecedent.CLINICALLY_VALIDATED_TARGET]

    def test_preclinical_only_between_partial_and_novel(self):
        pc = _MOA_LOGODDS[MoAPrecedent.PRECLINICAL_ONLY]
        assert _MOA_LOGODDS[MoAPrecedent.NOVEL] < pc < _MOA_LOGODDS[MoAPrecedent.PARTIAL]

    def test_prior_failures_below_novel(self):
        assert _MOA_LOGODDS[MoAPrecedent.PRIOR_FAILURES] < _MOA_LOGODDS[MoAPrecedent.NOVEL]

    def test_known_liability_below_prior_failures(self):
        assert _MOA_LOGODDS[MoAPrecedent.KNOWN_LIABILITY] < _MOA_LOGODDS[MoAPrecedent.PRIOR_FAILURES]


# ---------------------------------------------------------------------------
# Exception flags — standalone values
# ---------------------------------------------------------------------------

class TestExceptionFlagValues:
    def test_all_flags_positive(self):
        for flag, val in _MOA_EXCEPTION_LOGODDS.items():
            assert val > 0, f"{flag} should be a positive rescue adjustment"

    def test_prior_failures_bad_drug_highest(self):
        assert _MOA_EXCEPTION_LOGODDS[MoAExceptionFlag.PRIOR_FAILURES_DUE_TO_BAD_DRUG] == pytest.approx(0.25)

    def test_genetics_second_highest(self):
        assert _MOA_EXCEPTION_LOGODDS[MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET] == pytest.approx(0.20)

    def test_biomarker_lowest(self):
        assert _MOA_EXCEPTION_LOGODDS[MoAExceptionFlag.STRONG_BIOMARKER_RESPONSE] == pytest.approx(0.10)

    def test_all_four_flags_present(self):
        assert len(_MOA_EXCEPTION_LOGODDS) == 4


# ---------------------------------------------------------------------------
# Exception flags — POS integration
# ---------------------------------------------------------------------------

class TestExceptionFlagIntegration:
    """Verify exception flags shift POS in the expected direction."""

    def _pos(self, moa, flags=()):
        adj = POSAdjusters(moa_precedent=moa, moa_exception_flags=list(flags))
        return compute_pos(TrialPhase.PHASE_2, TherapeuticArea.ONCOLOGY, adj)

    def test_genetics_rescues_novel_target(self):
        """NOVEL + GENETICALLY_VALIDATED_TARGET should be > NOVEL alone."""
        pos_novel = self._pos(MoAPrecedent.NOVEL)
        pos_rescued = self._pos(MoAPrecedent.NOVEL, [MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET])
        assert pos_rescued > pos_novel

    def test_genetics_on_novel_approaches_preclinical_only(self):
        """NOVEL (−0.35) + genetics (+0.20) = −0.15, closer to PRECLINICAL_ONLY (−0.20)."""
        pos_novel_genetics = self._pos(MoAPrecedent.NOVEL, [MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET])
        pos_preclinical = self._pos(MoAPrecedent.PRECLINICAL_ONLY)
        assert abs(pos_novel_genetics - pos_preclinical) < 0.05

    def test_bad_drug_flag_rescues_prior_failures(self):
        pos_plain = self._pos(MoAPrecedent.PRIOR_FAILURES)
        pos_rescued = self._pos(MoAPrecedent.PRIOR_FAILURES, [MoAExceptionFlag.PRIOR_FAILURES_DUE_TO_BAD_DRUG])
        assert pos_rescued > pos_plain

    def test_multiple_flags_additive(self):
        """Two flags should lift more than one flag."""
        one = self._pos(MoAPrecedent.NOVEL, [MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET])
        two = self._pos(MoAPrecedent.NOVEL, [
            MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET,
            MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM,
        ])
        assert two > one

    def test_empty_flags_no_effect(self):
        pos_no_flags = self._pos(MoAPrecedent.NOVEL, [])
        pos_with_flags = self._pos(MoAPrecedent.NOVEL)
        assert pos_no_flags == pytest.approx(pos_with_flags)

    def test_full_rescue_scenario(self):
        """Novel + genetics + POM + bad-drug should get close to PATHWAY_VALIDATED."""
        pos_full_rescue = self._pos(MoAPrecedent.NOVEL, [
            MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET,
            MoAExceptionFlag.HUMAN_PROOF_OF_MECHANISM,
            MoAExceptionFlag.PRIOR_FAILURES_DUE_TO_BAD_DRUG,
        ])
        pos_pathway = self._pos(MoAPrecedent.PATHWAY_VALIDATED)
        # NOVEL(−0.35) + 0.20 + 0.15 + 0.25 = +0.25 > PATHWAY_VALIDATED(+0.05)
        assert pos_full_rescue > pos_pathway

    def test_known_liability_not_fully_rescued_by_single_flag(self):
        """Even with genetics, KNOWN_LIABILITY remains clearly below PARTIAL."""
        pos_rescued = self._pos(MoAPrecedent.KNOWN_LIABILITY, [MoAExceptionFlag.GENETICALLY_VALIDATED_TARGET])
        pos_partial = self._pos(MoAPrecedent.PARTIAL)
        assert pos_rescued < pos_partial

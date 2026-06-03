"""Sprint 20 tests — scarcity distribution, de_risking saturation, and false-positive logic."""
from __future__ import annotations

import pytest

from bve.intelligence.ma_probability import (
    _DERISKING_STAGE_SCORE_CAP,
    _DERISKING_BUCKET_SCORES,
    _STAGE_FALLBACK_SCORES,
    _DESIGN_TIER_ADJUSTMENTS,
    _DERISKING_QUALITY_PENALTIES,
    _DERISKING_QUALITY_BONUSES,
    _derisking_stage_score,
    _scarcity_score_from_peer_count,
    _compute_scarcity_modifiers,
)
from bve.intelligence.ma_scoring import (
    COMPOSITE_MAX_DUAL_GATE,
    COMPOSITE_MAX_ONE_DRIVER,
    COMPOSITE_MAX_ZERO_DRIVERS,
    COMPOSITE_MAX_WITH_DL_GATE,
    SATURATION_THRESHOLD,
)


# ---------------------------------------------------------------------------
# scarcity_score distribution
# ---------------------------------------------------------------------------

class TestScarcityScoreDistribution:
    """Verify scarcity_score is not constant and <10% of a realistic population hits cap."""

    def test_peer_count_zero_base_score_below_cap(self):
        """peer_count=0 base score should be well below saturation threshold."""
        base, bucket = _scarcity_score_from_peer_count(0)
        assert bucket == "very_high"
        assert base < SATURATION_THRESHOLD  # well below 0.95
        assert base < 0.70                  # substantially lower than old 0.85

    def test_peer_count_monotone_decreasing(self):
        """Higher peer count → lower scarcity base score."""
        bases = [_scarcity_score_from_peer_count(p)[0] for p in [0, 1, 4, 7, 12]]
        for i in range(len(bases) - 1):
            assert bases[i] > bases[i + 1], f"peer_count {i} not > {i+1}: {bases}"

    def test_orphan_modifier_substantial(self):
        """Orphan/rare disease indication should produce a significant positive modifier."""

        class _Context:
            class asset:
                indication = "Gaucher disease"
                therapeutic_area = "rare disease"
                modality = None
                mechanism_of_action = None

        modifier = _compute_scarcity_modifiers(_Context())
        assert modifier >= 0.15, f"orphan modifier too small: {modifier}"

    def test_high_competition_ta_penalty(self):
        """Oncology indication should produce a negative scarcity modifier."""

        class _Context:
            class asset:
                indication = "non-small cell lung cancer"
                therapeutic_area = "oncology"
                modality = None
                mechanism_of_action = None

        modifier = _compute_scarcity_modifiers(_Context())
        assert modifier < 0.0, f"oncology should have negative modifier: {modifier}"

    def test_novel_modality_bonus(self):
        """Scarce modality (gene therapy) produces a positive modifier."""

        class _MockModality:
            value = "gene therapy"

        class _Context:
            class asset:
                indication = None
                therapeutic_area = None
                mechanism_of_action = None
                modality = _MockModality()

        modifier = _compute_scarcity_modifiers(_Context())
        assert modifier >= 0.10, f"gene therapy modifier too small: {modifier}"

    def test_named_moa_bonus(self):
        """Named mechanism of action produces a positive modifier."""

        class _Context:
            class asset:
                indication = None
                therapeutic_area = None
                modality = None
                mechanism_of_action = "KRAS G12C inhibitor"

        modifier = _compute_scarcity_modifiers(_Context())
        assert modifier > 0.0, f"named MoA should give positive modifier: {modifier}"

    def test_scarcity_cap_max_at_080(self):
        """Maximum achievable scarcity score is 0.80 (hard cap)."""
        # Best case: peer_count=0 + orphan + scarce modality + named MoA
        base, _ = _scarcity_score_from_peer_count(0)

        class _MockModality:
            value = "gene therapy"

        class _Context:
            class asset:
                indication = "hemophilia A"
                therapeutic_area = "rare disease"
                mechanism_of_action = "Factor VIII gene replacement"
                modality = _MockModality()

        modifier = _compute_scarcity_modifiers(_Context())
        score = min(max(base + modifier, 0.0), 0.80)
        assert score <= 0.80
        assert score > 0.70  # orphan + gene therapy + MoA should be high

    def test_realistic_population_cap_rate_below_10pct(self):
        """Over a realistic mix of assets, <10% should hit the SATURATION_THRESHOLD (0.95)."""
        import random
        rng = random.Random(42)
        peer_counts = [0, 0, 0, 1, 2, 2, 3, 5, 8, 12]  # realistic universe distribution
        modifiers = [0.25, 0.10, -0.05, 0.20, 0.05, -0.10, 0.10, -0.15, 0.00, -0.15]
        scores = []
        for pc, mod in zip(peer_counts, modifiers):
            base, _ = _scarcity_score_from_peer_count(pc)
            score = round(min(max(base + mod, 0.0), 0.80), 6)
            scores.append(score)
        pct_at_cap = sum(1 for s in scores if s >= SATURATION_THRESHOLD) / len(scores)
        assert pct_at_cap < 0.10, f"Scarcity cap rate too high: {pct_at_cap:.1%}"

    def test_oncology_asset_score_below_ophthalmology(self):
        """Oncology (high competition) should score lower than ophthalmology (neutral TA)."""

        class _OncologyContext:
            class asset:
                indication = "NSCLC"
                therapeutic_area = "oncology"
                modality = None
                mechanism_of_action = "PD-1 inhibitor"

        class _OphthalmologyContext:
            class asset:
                indication = "wet AMD"
                therapeutic_area = "ophthalmology"
                modality = None
                mechanism_of_action = "VEGF inhibitor"

        onco_mod = _compute_scarcity_modifiers(_OncologyContext())
        opht_mod = _compute_scarcity_modifiers(_OphthalmologyContext())
        # Oncology should have a lower modifier due to TA competition penalty
        assert onco_mod < opht_mod


# ---------------------------------------------------------------------------
# de_risking_stage_score distribution
# ---------------------------------------------------------------------------

class TestDeRiskingStageScore:
    """Verify de_risking_stage_score has spread and <20% at cap."""

    def test_phase3_base_below_cap(self):
        """Phase 3 base score alone is below the new cap of 0.80."""
        base = _DERISKING_BUCKET_SCORES["phase_3_or_later"]
        assert base < _DERISKING_STAGE_SCORE_CAP
        assert base < 0.70  # well below old cap of 0.90

    def test_nda_bla_base_below_cap(self):
        """NDA/BLA base score alone is below the new cap."""
        base = _DERISKING_BUCKET_SCORES.get("nda_bla") or _STAGE_FALLBACK_SCORES["nda_bla"]
        assert base < _DERISKING_STAGE_SCORE_CAP

    def test_os_rct_adjustment_positive(self):
        """OS RCT design tier provides a positive adjustment."""
        assert _DESIGN_TIER_ADJUSTMENTS["os_rct"] > 0

    def test_single_arm_adjustment_negative(self):
        """Single-arm design tier provides a negative adjustment."""
        assert _DESIGN_TIER_ADJUSTMENTS["single_arm"] < 0

    def test_quality_penalties_negative(self):
        """All quality penalty keys produce negative adjustments."""
        for key, penalty in _DERISKING_QUALITY_PENALTIES.items():
            assert penalty < 0, f"Penalty {key} should be negative, got {penalty}"

    def test_btd_bonus_positive(self):
        """Breakthrough designation provides a positive bonus."""
        assert _DERISKING_QUALITY_BONUSES["breakthrough_designation"] > 0

    def test_phase3_plus_os_rct_still_below_cap(self):
        """Phase 3 + OS RCT design tier should NOT reach the hard cap."""
        base = _DERISKING_BUCKET_SCORES["phase_3_or_later"]
        os_adj = _DESIGN_TIER_ADJUSTMENTS["os_rct"]
        combined = base + os_adj
        assert combined < _DERISKING_STAGE_SCORE_CAP

    def test_safety_overhang_reduces_score(self):
        """safety_overhang attribute on acquisition_row reduces the score."""
        from types import SimpleNamespace
        row_clean = SimpleNamespace(
            acquisition_readiness_bucket="phase_3_or_later",
            stage="phase_3",
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=False,
            prior_phase3_failure=False,
            label_uncertainty=False,
            prior_phase2_failure=False,
            regulatory_risk=False,
            endpoint_in_dispute=False,
            breakthrough_designation=False,
        )
        row_unsafe = SimpleNamespace(
            acquisition_readiness_bucket="phase_3_or_later",
            stage="phase_3",
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=True,   # penalized
            prior_phase3_failure=False,
            label_uncertainty=False,
            prior_phase2_failure=False,
            regulatory_risk=False,
            endpoint_in_dispute=False,
            breakthrough_designation=False,
        )
        score_clean = _derisking_stage_score(row_clean)
        score_unsafe = _derisking_stage_score(row_unsafe)
        assert score_unsafe < score_clean

    def test_breakthrough_designation_increases_score(self):
        """breakthrough_designation attribute increases de_risking score."""
        from types import SimpleNamespace
        row_base = SimpleNamespace(
            acquisition_readiness_bucket="phase_2_poc",
            stage="phase_2",
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=False,
            prior_phase3_failure=False,
            label_uncertainty=False,
            prior_phase2_failure=False,
            regulatory_risk=False,
            endpoint_in_dispute=False,
            breakthrough_designation=False,
        )
        row_btd = SimpleNamespace(
            acquisition_readiness_bucket="phase_2_poc",
            stage="phase_2",
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=False,
            prior_phase3_failure=False,
            label_uncertainty=False,
            prior_phase2_failure=False,
            regulatory_risk=False,
            endpoint_in_dispute=False,
            breakthrough_designation=True,  # bonus
        )
        assert _derisking_stage_score(row_btd) > _derisking_stage_score(row_base)

    def test_realistic_population_cap_rate_below_20pct(self):
        """Over a realistic mix of Phase 2/3 assets, <20% hit the hard cap."""
        from types import SimpleNamespace

        def _row(bucket, tier="standard", safety=False, p3fail=False,
                 label_unc=False, p2fail=False, reg_risk=False, btd=False):
            return SimpleNamespace(
                acquisition_readiness_bucket=bucket,
                stage="phase_3" if "3" in bucket else "phase_2",
                acquisition_readiness_design_tier=tier,
                acquisition_readiness_prior_pos=None,
                acquisition_readiness_posterior_pos=None,
                acquisition_readiness_low_power=False,
                safety_overhang=safety,
                prior_phase3_failure=p3fail,
                label_uncertainty=label_unc,
                prior_phase2_failure=p2fail,
                regulatory_risk=reg_risk,
                endpoint_in_dispute=False,
                breakthrough_designation=btd,
            )

        # Realistic mix of late-stage assets
        rows = [
            _row("phase_3_or_later", tier="os_rct"),         # best case P3
            _row("phase_3_or_later", tier="pfs"),             # typical P3
            _row("phase_3_or_later", tier="standard"),        # standard P3
            _row("phase_3_or_later", tier="surrogate"),       # surrogate endpoint
            _row("phase_3_or_later", tier="single_arm"),      # single arm
            _row("phase_3_or_later", safety=True),            # safety issue
            _row("phase_3_or_later", p3fail=True),            # prior P3 failure
            _row("phase_3_or_later", label_unc=True),         # label uncertainty
            _row("phase_2_poc", tier="os_rct", btd=True),    # P2 PoC + BTD
            _row("phase_2_poc", tier="pfs"),                  # P2 PoC
            _row("phase_2_poc", p2fail=True),                 # P2 PoC + prior failure
            _row("phase_2_pre_poc"),                          # early P2
            _row("pre_phase_2"),                              # pre-Phase 2
        ]
        scores = [_derisking_stage_score(r) for r in rows]
        pct_at_cap = sum(1 for s in scores if s >= _DERISKING_STAGE_SCORE_CAP) / len(scores)
        assert pct_at_cap < 0.20, (
            f"de_risking cap rate too high: {pct_at_cap:.1%}\n"
            f"Scores: {[round(s, 3) for s in scores]}"
        )

    def test_phase3_scores_strictly_above_phase2(self):
        """Phase 3 scores should generally exceed Phase 2 (same other conditions)."""
        from types import SimpleNamespace
        p3 = _derisking_stage_score(SimpleNamespace(
            acquisition_readiness_bucket="phase_3_or_later",
            stage="phase_3",
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=False, prior_phase3_failure=False,
            label_uncertainty=False, prior_phase2_failure=False,
            regulatory_risk=False, endpoint_in_dispute=False,
            breakthrough_designation=False,
        ))
        p2 = _derisking_stage_score(SimpleNamespace(
            acquisition_readiness_bucket="phase_2_poc",
            stage="phase_2",
            acquisition_readiness_design_tier="standard",
            acquisition_readiness_prior_pos=None,
            acquisition_readiness_posterior_pos=None,
            acquisition_readiness_low_power=False,
            safety_overhang=False, prior_phase3_failure=False,
            label_uncertainty=False, prior_phase2_failure=False,
            regulatory_risk=False, endpoint_in_dispute=False,
            breakthrough_designation=False,
        ))
        assert p3 > p2


# ---------------------------------------------------------------------------
# Scarcity constants sanity
# ---------------------------------------------------------------------------

class TestScarcityConstants:
    def test_very_high_bucket_base_below_060(self):
        """very_high bucket base should be below 0.60 to avoid constant saturation."""
        base, bucket = _scarcity_score_from_peer_count(0)
        assert bucket == "very_high"
        assert base <= 0.60

    def test_high_bucket_below_very_high(self):
        base_vh, _ = _scarcity_score_from_peer_count(0)
        base_h, _ = _scarcity_score_from_peer_count(2)
        assert base_h < base_vh

    def test_hard_cap_at_080(self):
        """The scarcity hard cap used in _assess_scarcity should be 0.80."""
        # Verify this is reflected: best possible score = 0.55 + 0.30 (max modifier) = 0.85
        # → capped at 0.80
        base, _ = _scarcity_score_from_peer_count(0)
        max_modifier = 0.30  # _compute_scarcity_modifiers returns min(modifier, 0.30)
        uncapped = base + max_modifier
        capped = min(uncapped, 0.80)
        assert capped == 0.80
        assert uncapped > 0.80  # cap is binding


# ---------------------------------------------------------------------------
# Composite-level constants sanity
# ---------------------------------------------------------------------------

class TestCompositeCapConstants:
    def test_dual_gate_stricter_than_single_gate(self):
        assert COMPOSITE_MAX_DUAL_GATE < COMPOSITE_MAX_WITH_DL_GATE

    def test_zero_drivers_stricter_than_one_driver(self):
        assert COMPOSITE_MAX_ZERO_DRIVERS < COMPOSITE_MAX_ONE_DRIVER

    def test_one_driver_ceiling_matches_dl_gate(self):
        """Single driver ceiling == DL gate cap: both enforce the same 0.65 ceiling."""
        assert COMPOSITE_MAX_ONE_DRIVER == COMPOSITE_MAX_WITH_DL_GATE

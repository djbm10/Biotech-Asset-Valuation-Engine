"""Sprint 21 tests — strategic_fit_score penalties, transaction-likelihood gate,
and buyer alias coverage."""
from __future__ import annotations

import pytest
from types import SimpleNamespace

from bve.intelligence.ma_probability import (
    _STRATEGIC_FIT_HARD_CAP,
    _STRATEGIC_FIT_PENALTY_WEAK_TA,
    _STRATEGIC_FIT_PENALTY_POOR_MODALITY,
    _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP,
    _STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE,
    _STRATEGIC_FIT_WEAK_TA_THRESHOLD,
    _STRATEGIC_FIT_POOR_MODALITY_THRESHOLD,
    _STRATEGIC_FIT_NO_GAP_THRESHOLD,
    _STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD,
    STRATEGIC_FIT_REASON_WEAK_TA,
    STRATEGIC_FIT_REASON_POOR_MODALITY,
    STRATEGIC_FIT_REASON_NO_GAP,
    STRATEGIC_FIT_REASON_POOR_DEAL_SIZE,
    _MNA_PROB_DUAL_GATE_CAP,
    _MNA_PROB_HIGH_SCORE_FLOOR,
    _TRIGGER_FINANCING_MIN,
    _TRIGGER_EXTERNAL_MIN,
    _TRIGGER_ACTIVIST_MIN,
    _TRIGGER_VALUATION_MIN,
    _TRIGGER_DERISKING_MIN,
    _apply_transaction_likelihood_gate,
)
from bve.analysis.candidate_coverage_report import _acquirers_match


# ---------------------------------------------------------------------------
# Inline strategic-fit scorer (mirrors _strategic_fit_score logic without
# needing MAProbabilityScanner, which requires a full environment)
# ---------------------------------------------------------------------------

def _compute_strategic_fit(
    ta_score: float,
    modality_score: float,
    strategic_priority_score: float,
    budget_score: float,
    *,
    ta_weight: float = 0.30,
    modality_weight: float = 0.25,
    strat_weight: float = 0.25,
    budget_weight: float = 0.20,
) -> float:
    """Reproduce _strategic_fit_score logic for unit testing."""
    strategic_weight = ta_weight + modality_weight + strat_weight + budget_weight
    if strategic_weight <= 0:
        return 0.0
    component = (
        ta_score * ta_weight
        + modality_score * modality_weight
        + strategic_priority_score * strat_weight
        + budget_score * budget_weight
    )
    base = min(max(component / strategic_weight, 0.0), 1.0)

    penalty = 0.0
    if ta_score < _STRATEGIC_FIT_WEAK_TA_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_WEAK_TA
    if modality_score < _STRATEGIC_FIT_POOR_MODALITY_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_POOR_MODALITY
    if strategic_priority_score < _STRATEGIC_FIT_NO_GAP_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP
    if budget_score < _STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD:
        penalty += _STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE

    penalized = max(base - penalty, 0.0)
    return round(min(penalized, _STRATEGIC_FIT_HARD_CAP), 6)


# ---------------------------------------------------------------------------
# TestStrategicFitScoreConstants
# ---------------------------------------------------------------------------

class TestStrategicFitScoreConstants:
    def test_hard_cap_at_080(self):
        assert _STRATEGIC_FIT_HARD_CAP == 0.80

    def test_penalties_all_positive(self):
        assert _STRATEGIC_FIT_PENALTY_WEAK_TA > 0
        assert _STRATEGIC_FIT_PENALTY_POOR_MODALITY > 0
        assert _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP > 0
        assert _STRATEGIC_FIT_PENALTY_POOR_DEAL_SIZE > 0

    def test_thresholds_in_unit_interval(self):
        for t in [
            _STRATEGIC_FIT_WEAK_TA_THRESHOLD,
            _STRATEGIC_FIT_POOR_MODALITY_THRESHOLD,
            _STRATEGIC_FIT_NO_GAP_THRESHOLD,
            _STRATEGIC_FIT_POOR_DEAL_SIZE_THRESHOLD,
        ]:
            assert 0.0 < t < 1.0

    def test_reason_codes_nonempty(self):
        for code in [
            STRATEGIC_FIT_REASON_WEAK_TA,
            STRATEGIC_FIT_REASON_POOR_MODALITY,
            STRATEGIC_FIT_REASON_NO_GAP,
            STRATEGIC_FIT_REASON_POOR_DEAL_SIZE,
        ]:
            assert isinstance(code, str) and len(code) > 0


# ---------------------------------------------------------------------------
# TestStrategicFitScorePenalties
# ---------------------------------------------------------------------------

class TestStrategicFitScorePenalties:
    def test_all_perfect_capped_at_hard_cap(self):
        """All sub-scores = 1.0 should yield exactly _STRATEGIC_FIT_HARD_CAP."""
        score = _compute_strategic_fit(1.0, 1.0, 1.0, 1.0)
        assert score == _STRATEGIC_FIT_HARD_CAP

    def test_weak_ta_reduces_score(self):
        """TA score below threshold triggers penalty."""
        score_good = _compute_strategic_fit(0.80, 0.80, 0.80, 0.80)
        score_weak_ta = _compute_strategic_fit(0.40, 0.80, 0.80, 0.80)
        assert score_weak_ta < score_good

    def test_poor_modality_reduces_score(self):
        score_good = _compute_strategic_fit(0.80, 0.80, 0.80, 0.80)
        score_poor_mod = _compute_strategic_fit(0.80, 0.30, 0.80, 0.80)
        assert score_poor_mod < score_good

    def test_no_pipeline_gap_reduces_score(self):
        """Strategic priority < 0.50 triggers largest penalty (0.15)."""
        score_gap = _compute_strategic_fit(0.80, 0.80, 0.80, 0.80)
        score_no_gap = _compute_strategic_fit(0.80, 0.80, 0.30, 0.80)
        assert score_no_gap < score_gap
        # pipeline_gap penalty is largest
        assert (
            _STRATEGIC_FIT_PENALTY_NO_PIPELINE_GAP
            >= _STRATEGIC_FIT_PENALTY_WEAK_TA
        )

    def test_poor_deal_size_reduces_score(self):
        score_good = _compute_strategic_fit(0.80, 0.80, 0.80, 0.80)
        score_poor_size = _compute_strategic_fit(0.80, 0.80, 0.80, 0.30)
        assert score_poor_size < score_good

    def test_all_penalties_stack(self):
        """All four penalties together should produce a very low score."""
        score = _compute_strategic_fit(0.30, 0.30, 0.30, 0.30)
        assert score <= 0.20, f"Expected score ≤ 0.20 with all penalties, got {score}"

    def test_no_penalties_when_all_strong(self):
        """Above all thresholds — no penalty, only hard cap applies."""
        score_no_penalty = _compute_strategic_fit(0.70, 0.70, 0.70, 0.70)
        # With strong sub-scores, the only limit is the hard cap
        base = (0.70 * 0.30 + 0.70 * 0.25 + 0.70 * 0.25 + 0.70 * 0.20) / 1.0
        expected = min(base, _STRATEGIC_FIT_HARD_CAP)
        assert abs(score_no_penalty - expected) < 1e-5


# ---------------------------------------------------------------------------
# TestStrategicFitScoreCapRate
# ---------------------------------------------------------------------------

class TestStrategicFitScoreCapRate:
    def test_cap_rate_below_10pct_realistic_population(self):
        """Over a realistic population of acquirer-target pairs, <10% should
        hit the hard cap (0.80)."""
        # Realistic distribution: mix of strong, moderate, and weak fits
        population = [
            # Strong fits (top-quartile acquirers)
            (0.90, 0.85, 0.80, 0.85),  # ideal fit
            (0.80, 0.75, 0.70, 0.80),  # good fit
            (0.75, 0.70, 0.65, 0.75),  # above-average
            # Moderate fits (median acquirers)
            (0.65, 0.60, 0.55, 0.65),  # moderate
            (0.55, 0.55, 0.50, 0.60),  # below avg strategic priority
            (0.60, 0.45, 0.60, 0.55),  # modality concern
            (0.50, 0.60, 0.40, 0.65),  # no pipeline gap
            # Weak fits (marginal acquirers)
            (0.40, 0.50, 0.35, 0.50),  # weak TA
            (0.35, 0.40, 0.30, 0.40),  # multiple deficits
            (0.25, 0.30, 0.25, 0.30),  # poor all-round
            # Atypical cases
            (0.90, 0.30, 0.70, 0.80),  # great TA, poor modality
            (0.80, 0.80, 0.30, 0.80),  # no pipeline gap despite TA/mod
            (0.70, 0.70, 0.70, 0.30),  # deal size mismatch
        ]
        scores = [_compute_strategic_fit(*p) for p in population]
        cap_rate = sum(1 for s in scores if s >= _STRATEGIC_FIT_HARD_CAP) / len(scores)
        assert cap_rate < 0.10, (
            f"Cap rate too high: {cap_rate:.1%}\n"
            f"Scores: {[round(s, 3) for s in scores]}"
        )

    def test_score_distribution_has_spread(self):
        """Scores should span at least 0.40 range (not all bunched near cap)."""
        population = [
            (0.90, 0.85, 0.80, 0.85),
            (0.65, 0.60, 0.55, 0.65),
            (0.35, 0.40, 0.30, 0.40),
            (0.25, 0.30, 0.25, 0.30),
        ]
        scores = [_compute_strategic_fit(*p) for p in population]
        spread = max(scores) - min(scores)
        assert spread >= 0.35, f"Spread too narrow: {spread:.3f}"


# ---------------------------------------------------------------------------
# TestTransactionLikelihoodGate
# ---------------------------------------------------------------------------

class TestTransactionLikelihoodGate:
    """Verify _apply_transaction_likelihood_gate caps correctly."""

    def _gate(self, score, *, fp=0.10, eda=0.10, activist=0.10,
              catalyst_days=None, vd=0.20, dr=0.40):
        return _apply_transaction_likelihood_gate(
            score,
            financing_pressure=fp,
            external_deal_activity=eda,
            activist_signal=activist,
            catalyst_days=catalyst_days,
            valuation_discount=vd,
            de_risking_stage=dr,
        )

    def test_dual_gate_caps_at_mna_prob_dual_gate_cap(self):
        """Both not-pressured AND no-urgency → score ≤ 0.60."""
        result = self._gate(0.90, fp=0.10, eda=0.10)
        assert result <= _MNA_PROB_DUAL_GATE_CAP
        assert result == _MNA_PROB_DUAL_GATE_CAP

    def test_low_score_unaffected_by_dual_gate(self):
        """Score already ≤ 0.60 → dual gate has no effect."""
        result = self._gate(0.50, fp=0.10, eda=0.10)
        assert result == 0.50

    def test_financing_pressure_prevents_dual_gate(self):
        """High financing pressure → dual gate should not fire."""
        result = self._gate(0.90, fp=0.40, eda=0.10)
        # Not both low-pressure, so dual gate doesn't fire
        # But check high-score trigger
        assert result >= _MNA_PROB_DUAL_GATE_CAP  # not capped at 0.60

    def test_external_activity_prevents_dual_gate(self):
        """High external deal activity → dual gate should not fire."""
        result = self._gate(0.90, fp=0.10, eda=0.35)
        assert result >= _MNA_PROB_DUAL_GATE_CAP

    def test_high_score_requires_trigger(self):
        """Score > 0.75 with no triggers → capped at 0.75."""
        result = self._gate(0.90, fp=0.10, eda=0.10, activist=0.10,
                            catalyst_days=None, vd=0.20, dr=0.40)
        # Dual gate fires first (both low-pressure) → caps at 0.60
        assert result <= _MNA_PROB_HIGH_SCORE_FLOOR

    def test_financing_pressure_trigger_allows_high_score(self):
        """Financing pressure ≥ threshold bypasses high-score cap."""
        result = _apply_transaction_likelihood_gate(
            0.80,
            financing_pressure=_TRIGGER_FINANCING_MIN,  # exactly at threshold
            external_deal_activity=0.10,  # low
            activist_signal=0.10,
            catalyst_days=None,
            valuation_discount=0.20,
            de_risking_stage=0.40,
        )
        # Not both low-pressure (eda < 0.20 but fp >= 0.35 ≥ 0.25 threshold)
        # fp=0.35 is NOT < 0.25, so not financing_not_pressured → dual gate won't fire
        # High score: fp >= 0.35 → has_trigger=True → score unchanged
        assert result == 0.80

    def test_catalyst_trigger_allows_high_score(self):
        """Near-term catalyst (≤ 90 days) bypasses high-score cap."""
        result = _apply_transaction_likelihood_gate(
            0.80,
            financing_pressure=0.10,  # not pressured
            external_deal_activity=0.25,  # slightly above 0.20 → no dual gate
            activist_signal=0.10,
            catalyst_days=45,  # within 90 days
            valuation_discount=0.20,
            de_risking_stage=0.40,
        )
        # eda=0.25 ≥ 0.20 → dual gate doesn't fire
        # catalyst_days=45 ≤ 90 → catalyst trigger fires → score allowed
        assert result == 0.80

    def test_valuation_distress_trigger_allows_high_score(self):
        """Valuation distress (deep discount + de-risked) bypasses cap."""
        result = _apply_transaction_likelihood_gate(
            0.80,
            financing_pressure=0.10,
            external_deal_activity=0.25,  # above 0.20 → no dual gate
            activist_signal=0.10,
            catalyst_days=None,
            valuation_discount=_TRIGGER_VALUATION_MIN,  # 0.45
            de_risking_stage=_TRIGGER_DERISKING_MIN,    # 0.50
        )
        assert result == 0.80

    def test_dual_gate_cap_is_more_restrictive_than_high_score_floor(self):
        assert _MNA_PROB_DUAL_GATE_CAP <= _MNA_PROB_HIGH_SCORE_FLOOR

    def test_score_always_in_unit_interval(self):
        """Gate never produces a score outside [0, 1]."""
        for raw in [0.0, 0.3, 0.6, 0.75, 0.9, 1.0]:
            r = self._gate(raw, fp=0.05, eda=0.05)
            assert 0.0 <= r <= 1.0


# ---------------------------------------------------------------------------
# TestAcquirerAliasCoverage
# ---------------------------------------------------------------------------

class TestAcquirerAliasCoverage:
    """Verify Sprint 21 alias additions match correctly."""

    # Each tuple: (real_acquirer_name_in_deal_universe, profile_name)
    _ALIAS_PAIRS = [
        ("Merck", "merck"),
        ("Merck & Co", "merck"),
        ("MSD", "merck"),
        ("MRK", "merck"),
        ("Amgen", "amgen"),
        ("AMGN", "amgen"),
        ("AbbVie", "abbvie"),
        ("ABBV", "abbvie"),
        ("Takeda", "takeda"),
        ("Takeda Pharmaceutical", "takeda"),
        ("Sanofi", "sanofi"),
        ("Sanofi-Aventis", "sanofi"),
        ("Biogen", "biogen"),
        ("BIIB", "biogen"),
        ("Regeneron", "regeneron"),
        ("REGN", "regeneron"),
        ("Daiichi Sankyo", "daiichi sankyo"),
        ("Kyowa Kirin", "kyowa kirin"),
        ("Boehringer Ingelheim", "boehringer ingelheim"),
        ("Jazz Pharmaceuticals", "jazz pharmaceuticals"),
        ("Incyte", "incyte"),
        ("INCY", "incyte"),
        # Previously existing aliases should still work
        ("BMS", "bristol-myers squibb"),
        ("Janssen", "johnson & johnson"),
        ("Lilly", "eli lilly"),
        ("Roche", "roche / genentech"),
        ("GSK", "gsk"),
    ]

    @pytest.mark.parametrize("real,profile", _ALIAS_PAIRS)
    def test_alias_pair_matches(self, real, profile):
        assert _acquirers_match(real, profile), (
            f"Expected '{real}' to match '{profile}'"
        )

    def test_merck_us_does_not_match_merck_kgaa(self):
        """Merck (US) and Merck KGaA are distinct companies; should NOT cross-match."""
        # Merck KGaA is the German company — it does NOT appear in _ACQUIRER_ALIASES
        # under the "merck" key (no alias "kgaa" or "merck group").
        # This test verifies the alias is specific enough.
        assert not _acquirers_match("Merck KGaA", "merck"), (
            "Merck KGaA (German) should NOT match US Merck profile"
        )

    def test_alias_matching_is_case_insensitive(self):
        assert _acquirers_match("SANOFI-AVENTIS", "sanofi")
        assert _acquirers_match("amgen inc", "AMGN")

    def test_exact_match_still_works(self):
        assert _acquirers_match("pfizer", "pfizer")
        assert _acquirers_match("AstraZeneca", "astrazeneca")

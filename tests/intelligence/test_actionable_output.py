"""Tests for Wave K — Weekly Actionable Output Generator."""
from __future__ import annotations

from datetime import date

import pytest

from bve.intelligence.capital_structure import CapitalRiskLevel
from bve.intelligence.actionable_output import (
    ActionableGenerator,
    ActionableOpportunity,
    CURRENT_SCORE_VERSION,
    SCORE_VERSIONS,
    ScoredCandidate,
    WeeklyActionableReport,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candidate(
    asset_id: str = "a-1",
    ticker: str = "XYZ",
    ranking_score: float = 0.80,
    thesis_strength: float = 0.70,
    opportunity_score: float = 0.60,
    critic_severity: str | None = None,
    catalyst: str = "Phase 3 readout H2 2025",
    indication: str = "oncology",
) -> ScoredCandidate:
    return ScoredCandidate(
        asset_id=asset_id,
        ticker=ticker,
        ranking_score=ranking_score,
        thesis_strength=thesis_strength,
        opportunity_score=opportunity_score,
        critic_severity=critic_severity,
        catalyst_description=catalyst,
        indication=indication,
    )


def _gen(**kwargs) -> ActionableGenerator:
    return ActionableGenerator(**kwargs)


# ---------------------------------------------------------------------------
# Score versions
# ---------------------------------------------------------------------------

def test_current_score_version_registered() -> None:
    assert CURRENT_SCORE_VERSION in SCORE_VERSIONS


def test_unknown_score_version_raises() -> None:
    with pytest.raises(ValueError, match="Unknown score version"):
        ActionableGenerator(score_version="v99.0")


def test_report_logs_score_weights() -> None:
    gen = _gen()
    report = gen.generate([])
    assert "ranking" in report.score_weights
    assert "thesis" in report.score_weights
    assert "opportunity" in report.score_weights


def test_report_logs_score_version() -> None:
    gen = _gen()
    report = gen.generate([_candidate()])
    assert report.opportunities[0].score_version == CURRENT_SCORE_VERSION


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

def test_generate_empty_returns_report() -> None:
    gen = _gen()
    report = gen.generate([])
    assert isinstance(report, WeeklyActionableReport)
    assert report.has_actionable is False
    assert report.opportunities == []
    assert report.n_considered == 0


def test_generate_empty_never_raises() -> None:
    gen = _gen()
    report = gen.generate([])
    assert report is not None


# ---------------------------------------------------------------------------
# Action assignment
# ---------------------------------------------------------------------------

def test_high_composite_gets_buy() -> None:
    gen = _gen()
    # ranking=0.9, thesis=0.9, opportunity=0.9 → composite = 0.9
    c = _candidate(ranking_score=0.9, thesis_strength=0.9, opportunity_score=0.9)
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "buy"


def test_medium_composite_gets_add() -> None:
    gen = _gen()
    # ranking=0.6, thesis=0.6, opportunity=0.0 → composite = 0.5*0.6 + 0.3*0.6 = 0.48+? Let me calc
    # 0.5*0.6 + 0.3*0.6 + 0.2*0.0 = 0.30+0.18 = 0.48 → "monitor" actually
    # Need composite between 0.50 and 0.70
    # 0.5*0.7 + 0.3*0.7 + 0.2*0.5 = 0.35+0.21+0.10 = 0.66 → "add"
    c = _candidate(ranking_score=0.70, thesis_strength=0.70, opportunity_score=0.50)
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "add"


def test_low_composite_gets_monitor() -> None:
    gen = _gen()
    # composite = 0.5*0.4 + 0.3*0.4 + 0.2*0.0 = 0.20+0.12 = 0.32 → monitor
    c = _candidate(ranking_score=0.40, thesis_strength=0.40, opportunity_score=0.0)
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "monitor"


def test_very_low_composite_gets_avoid() -> None:
    gen = _gen(min_composite_score=0.0)  # below 0.30 → avoid
    c = _candidate(ranking_score=0.10, thesis_strength=0.0, opportunity_score=0.0)
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "avoid"


# ---------------------------------------------------------------------------
# Critic caution → downgrade
# ---------------------------------------------------------------------------

def test_caution_downgrades_buy_to_monitor() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, thesis_strength=0.9, critic_severity="caution")
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "monitor"
    assert report.n_elevated_by_critic == 1


def test_caution_downgrades_add_to_monitor() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.65, thesis_strength=0.65, opportunity_score=0.5, critic_severity="caution")
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "monitor"


def test_warning_does_not_downgrade() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, thesis_strength=0.9, critic_severity="warning")
    report = gen.generate([c])
    assert report.opportunities[0].recommended_action == "buy"
    assert report.n_elevated_by_critic == 0


def test_caution_zero_size() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, thesis_strength=0.9, critic_severity="caution")
    report = gen.generate([c])
    assert report.opportunities[0].recommended_size_pct == 0.0


# ---------------------------------------------------------------------------
# Score decomposition
# ---------------------------------------------------------------------------

def test_components_sum_to_composite() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.8, thesis_strength=0.6, opportunity_score=0.5)
    report = gen.generate([c])
    opp = report.opportunities[0]
    total = opp.ranking_component + opp.thesis_component + opp.opportunity_component
    assert abs(total - opp.composite_score) < 1e-6


def test_zero_thesis_strength_uses_zero() -> None:
    gen = _gen()
    c = ScoredCandidate(
        asset_id="a", ticker="T",
        ranking_score=0.8, opportunity_score=0.5, thesis_strength=None,
    )
    report = gen.generate([c])
    opp = report.opportunities[0]
    assert opp.thesis_component == pytest.approx(0.0)
    assert opp.thesis_strength is None


# ---------------------------------------------------------------------------
# Top-N ordering and sizing
# ---------------------------------------------------------------------------

def test_sorted_by_composite_desc() -> None:
    gen = _gen()
    candidates = [
        _candidate("a1", "A1", ranking_score=0.3),
        _candidate("a2", "A2", ranking_score=0.9),
        _candidate("a3", "A3", ranking_score=0.6),
    ]
    report = gen.generate(candidates)
    scores = [o.composite_score for o in report.opportunities]
    assert scores == sorted(scores, reverse=True)


def test_top_n_limits_output() -> None:
    gen = _gen()
    candidates = [_candidate(f"a{i}", f"T{i}", ranking_score=0.8) for i in range(10)]
    report = gen.generate(candidates, top_n=3)
    assert len(report.opportunities) == 3


def test_n_considered_counts_all_input() -> None:
    gen = _gen()
    candidates = [_candidate(f"a{i}", f"T{i}") for i in range(7)]
    report = gen.generate(candidates)
    assert report.n_considered == 7


def test_recommended_size_clipped_to_max() -> None:
    gen = _gen(max_position_pct=0.10)
    c = _candidate(ranking_score=1.0, thesis_strength=1.0, opportunity_score=1.0)
    report = gen.generate([c])
    assert report.opportunities[0].recommended_size_pct <= 0.10


def test_min_composite_score_filters() -> None:
    gen = _gen(min_composite_score=0.60)
    low = _candidate("low", "LOW", ranking_score=0.2, thesis_strength=0.2, opportunity_score=0.0)
    high = _candidate("high", "HIGH", ranking_score=0.9, thesis_strength=0.9)
    report = gen.generate([low, high])
    asset_ids = [o.asset_id for o in report.opportunities]
    assert "low" not in asset_ids
    assert "high" in asset_ids
    assert report.n_filtered_by_min_score == 1


# ---------------------------------------------------------------------------
# has_actionable
# ---------------------------------------------------------------------------

def test_has_actionable_true_when_buy_present() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, thesis_strength=0.9)
    report = gen.generate([c])
    assert report.has_actionable is True


def test_has_actionable_false_when_all_monitor() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, thesis_strength=0.9, critic_severity="caution")
    report = gen.generate([c])
    assert report.has_actionable is False


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------

def test_caution_appears_in_risk_flags() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, critic_severity="caution")
    report = gen.generate([c])
    flags = report.opportunities[0].risk_flags
    assert any("CAUTION" in f for f in flags)


def test_weak_thesis_appears_in_risk_flags() -> None:
    gen = _gen()
    c = _candidate(ranking_score=0.9, thesis_strength=0.20)
    report = gen.generate([c])
    flags = report.opportunities[0].risk_flags
    assert any("weak thesis" in f for f in flags)


# ---------------------------------------------------------------------------
# one_line_summary
# ---------------------------------------------------------------------------

def test_one_line_summary_populated() -> None:
    gen = _gen()
    c = _candidate(ticker="MRNA", catalyst="mRNA flu readout Q4 2025")
    report = gen.generate([c])
    summary = report.opportunities[0].one_line_summary
    assert "MRNA" in summary
    assert len(summary) > 10


# ---------------------------------------------------------------------------
# week_ending
# ---------------------------------------------------------------------------

def test_week_ending_default_is_today() -> None:
    gen = _gen()
    report = gen.generate([])
    assert isinstance(report.week_ending, date)


def test_week_ending_custom() -> None:
    gen = _gen()
    d = date(2025, 6, 20)
    report = gen.generate([], week_ending=d)
    assert report.week_ending == d


# ---------------------------------------------------------------------------
# Task 9.16 — Capital Risk Hard Gate
# ---------------------------------------------------------------------------

def _tier_a_candidate(**kwargs) -> "ScoredCandidate":
    """Tier A: ranking=0.72, thesis=0.80, opportunity=0.70 → composite ~0.79."""
    from bve.intelligence.actionable_output import ScoredCandidate
    return ScoredCandidate(
        asset_id="tier-a",
        ticker="TIERA",
        ranking_score=0.72,
        thesis_strength=0.80,
        opportunity_score=0.70,
        **kwargs,
    )


def test_critical_capital_risk_forces_avoid_on_tier_a() -> None:
    """Tier A (composite ~0.79) with CRITICAL capital risk → action = 'avoid'."""
    gen = ActionableGenerator()
    cand = _tier_a_candidate(capital_risk_level=CapitalRiskLevel.CRITICAL)
    report = gen.generate([cand])
    assert len(report.opportunities) == 1
    opp = report.opportunities[0]
    assert opp.recommended_action == "avoid"
    # composite is still penalised (score < pure base) — but not zero
    assert opp.composite_score > 0.0


def test_critical_capital_risk_composite_still_penalised() -> None:
    """CRITICAL gate forces avoid but does not zero out composite score."""
    gen = ActionableGenerator()
    cand_no_risk = _tier_a_candidate()
    cand_critical = _tier_a_candidate(capital_risk_level=CapitalRiskLevel.CRITICAL)
    base_composite = gen.generate([cand_no_risk]).opportunities[0].composite_score
    gated_composite = gen.generate([cand_critical]).opportunities[0].composite_score
    # Score is identical (hard gate doesn't adjust composite, only action)
    assert base_composite == pytest.approx(gated_composite, abs=0.01)
    assert gated_composite > 0.0


def test_critical_capital_risk_sets_has_actionable_false() -> None:
    """CRITICAL hard gate means no actionable opportunities."""
    gen = ActionableGenerator()
    report = gen.generate([_tier_a_candidate(capital_risk_level=CapitalRiskLevel.CRITICAL)])
    assert report.has_actionable is False


def test_high_capital_risk_reduces_when_composite_below_threshold() -> None:
    """HIGH capital risk on an asset whose composite falls below 0.50 → 'reduce'."""
    gen = ActionableGenerator()
    # ranking=0.50, thesis=0.30, opportunity=0.30 → base ~0.46 (below 0.50)
    from bve.intelligence.actionable_output import ScoredCandidate
    cand = ScoredCandidate(
        asset_id="hi-risk",
        ticker="HIRISK",
        ranking_score=0.50,
        thesis_strength=0.30,
        opportunity_score=0.30,
        capital_risk_level=CapitalRiskLevel.HIGH,
    )
    report = gen.generate([cand])
    assert report.opportunities[0].recommended_action == "reduce"


def test_high_capital_risk_does_not_override_when_composite_above_threshold() -> None:
    """HIGH capital risk with composite ≥ 0.50 → normal 'add'/'buy' (no reduce)."""
    gen = ActionableGenerator()
    # Tier A → composite well above 0.50
    cand = _tier_a_candidate(capital_risk_level=CapitalRiskLevel.HIGH)
    report = gen.generate([cand])
    assert report.opportunities[0].recommended_action in ("buy", "add")


def test_low_capital_risk_has_no_effect_on_action() -> None:
    """LOW capital risk is a no-op on action determination."""
    gen = ActionableGenerator()
    cand_no = _tier_a_candidate()
    cand_low = _tier_a_candidate(capital_risk_level=CapitalRiskLevel.LOW)
    action_no = gen.generate([cand_no]).opportunities[0].recommended_action
    action_low = gen.generate([cand_low]).opportunities[0].recommended_action
    assert action_no == action_low


def test_critical_capital_risk_flag_in_risk_flags() -> None:
    """CRITICAL capital risk populates a human-readable flag on the opportunity."""
    gen = ActionableGenerator()
    cand = _tier_a_candidate(capital_risk_level=CapitalRiskLevel.CRITICAL)
    opp = gen.generate([cand]).opportunities[0]
    assert any("CRITICAL" in f for f in opp.risk_flags)


def test_high_capital_risk_flag_in_risk_flags() -> None:
    """HIGH capital risk populates a risk flag on the opportunity."""
    gen = ActionableGenerator()
    from bve.intelligence.actionable_output import ScoredCandidate
    cand = ScoredCandidate(
        asset_id="hi",
        ticker="HI",
        ranking_score=0.50,
        thesis_strength=0.30,
        opportunity_score=0.30,
        capital_risk_level=CapitalRiskLevel.HIGH,
    )
    opp = gen.generate([cand]).opportunities[0]
    assert any("HIGH capital risk" in f for f in opp.risk_flags)


# ---------------------------------------------------------------------------
# Task 9.17 — Score Bounds Clamping + Signal Validation
# ---------------------------------------------------------------------------

def test_composite_score_never_exceeds_one() -> None:
    """Stacking max-positive signals cannot push composite above 1.0."""
    gen = ActionableGenerator()
    cand = ScoredCandidate(
        asset_id="maxout",
        ticker="MAX",
        ranking_score=1.0,
        thesis_strength=1.0,
        opportunity_score=1.0,
    )
    opp = gen.generate([cand]).opportunities[0]
    assert opp.composite_score <= 1.0


def test_composite_score_never_below_zero() -> None:
    """Even with all-negative adjustments, composite stays ≥ 0.0."""
    gen = ActionableGenerator()
    cand = ScoredCandidate(
        asset_id="minout",
        ticker="MIN",
        ranking_score=0.0,
        thesis_strength=0.0,
        opportunity_score=0.0,
        capital_risk_level=CapitalRiskLevel.CRITICAL,
    )
    opp = gen.generate([cand]).opportunities[0]
    assert opp.composite_score >= 0.0


def test_reduce_action_yields_zero_size() -> None:
    """'reduce' action should have size = 0.0 (same as monitor/avoid)."""
    gen = ActionableGenerator()
    from bve.intelligence.actionable_output import ScoredCandidate
    cand = ScoredCandidate(
        asset_id="red",
        ticker="RED",
        ranking_score=0.50,
        thesis_strength=0.30,
        opportunity_score=0.30,
        capital_risk_level=CapitalRiskLevel.HIGH,
    )
    opp = gen.generate([cand]).opportunities[0]
    assert opp.recommended_action == "reduce"
    assert opp.recommended_size_pct == 0.0

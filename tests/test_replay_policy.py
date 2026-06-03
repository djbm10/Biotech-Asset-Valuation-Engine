"""
Tests for ReplayPolicy (rules-based decision selection).

Coverage
--------
1.  ReplayPolicy.select() returns at most 2 decisions (max_positions=2)
2.  Skip assets already in open_asset_ids
3.  Skip critic_severity="warning" when skip_critic_warning=True
4.  Include critic_severity="warning" when skip_critic_warning=False
5.  Position capped at max_single_pct
6.  Total exposure capped at max_total_exposure_pct
7.  Only "buy" / "add" actions are selected (not "monitor" or "avoid")
8.  Deterministic: same report → same decisions, same order
9.  exit_date() = entry_date + max_hold_days
10. Empty report → empty decisions
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from bve.intelligence.actionable_output import (
    ActionableOpportunity,
    WeeklyActionableReport,
    CURRENT_SCORE_VERSION,
)
from bve.intelligence.replay_policy import ReplayDecision, ReplayPolicy, ReplayPolicyConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_opportunity(
    asset_id: str,
    ticker: str,
    action: str,
    composite_score: float,
    recommended_size_pct: float = 0.08,
    critic_severity: str | None = None,
) -> ActionableOpportunity:
    w = 0.50 * composite_score
    return ActionableOpportunity(
        asset_id=asset_id,
        ticker=ticker,
        recommended_action=action,
        recommended_size_pct=recommended_size_pct,
        composite_score=composite_score,
        ranking_component=w,
        thesis_component=0.0,
        opportunity_component=composite_score - w,
        score_version=CURRENT_SCORE_VERSION,
        critic_severity=critic_severity,
        one_line_summary=f"{ticker}: {action} | score={composite_score:.2f}",
    )


def _make_report(
    opportunities: list[ActionableOpportunity],
    week_ending: date = date(2025, 6, 2),
) -> WeeklyActionableReport:
    has_actionable = any(o.recommended_action in ("buy", "add") for o in opportunities)
    return WeeklyActionableReport(
        week_ending=week_ending,
        opportunities=opportunities,
        n_considered=len(opportunities),
        has_actionable=has_actionable,
    )


# ---------------------------------------------------------------------------
# 1. Returns at most max_positions decisions
# ---------------------------------------------------------------------------

def test_select_max_positions_two():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
        _make_opportunity("a-ntla", "NTLA", "add", 0.65),
        _make_opportunity("a-crsp", "CRSP", "add", 0.60),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert len(decisions) <= 2


def test_select_max_positions_one():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=1))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert len(decisions) == 1


def test_select_respects_max_open_positions_capacity():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=8, max_open_positions=3))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.90),
        _make_opportunity("a-alny", "ALNY", "buy", 0.85),
        _make_opportunity("a-ntla", "NTLA", "buy", 0.80),
    ]
    report = _make_report(opps)

    decisions = policy.select(report, open_asset_ids={"a-beam", "a-crsp"})

    assert len(decisions) == 1
    assert decisions[0].asset_id == "a-vktx"


def test_select_returns_no_decisions_when_open_positions_at_cap():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=8, max_open_positions=2))
    report = _make_report(
        [
            _make_opportunity("a-vktx", "VKTX", "buy", 0.90),
            _make_opportunity("a-alny", "ALNY", "buy", 0.85),
        ]
    )

    decisions = policy.select(report, open_asset_ids={"a-beam", "a-crsp"})
    assert decisions == []


# ---------------------------------------------------------------------------
# 2. Skip assets already in open_asset_ids
# ---------------------------------------------------------------------------

def test_skip_open_asset_ids():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
        _make_opportunity("a-ntla", "NTLA", "add", 0.65),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, open_asset_ids={"a-vktx", "a-alny"})
    # Both top candidates are open, only NTLA should be selected
    assert all(d.asset_id not in {"a-vktx", "a-alny"} for d in decisions)
    if decisions:
        assert decisions[0].asset_id == "a-ntla"


def test_skip_open_asset_ids_all_open():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, open_asset_ids={"a-vktx", "a-alny"})
    assert decisions == []


# ---------------------------------------------------------------------------
# 3. Skip critic_severity="warning" when skip_critic_warning=True
# ---------------------------------------------------------------------------

def test_skip_critic_warning_when_enabled():
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=2,
        skip_critic_warning=True,
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80, critic_severity="warning"),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75, critic_severity=None),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    # VKTX should be skipped due to warning
    assert all(d.asset_id != "a-vktx" for d in decisions)
    assert any(d.asset_id == "a-alny" for d in decisions)


def test_skip_critic_warning_skips_only_warning_not_caution():
    """critic_severity='caution' should NOT be skipped by skip_critic_warning."""
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=2,
        skip_critic_warning=True,
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80, critic_severity="caution"),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75, critic_severity="warning"),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    asset_ids = {d.asset_id for d in decisions}
    # VKTX (caution) should be included, ALNY (warning) should be skipped
    assert "a-vktx" in asset_ids
    assert "a-alny" not in asset_ids


# ---------------------------------------------------------------------------
# 4. Include critic_severity="warning" when skip_critic_warning=False
# ---------------------------------------------------------------------------

def test_include_critic_warning_when_disabled():
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=2,
        skip_critic_warning=False,
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80, critic_severity="warning"),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    asset_ids = {d.asset_id for d in decisions}
    assert "a-vktx" in asset_ids  # warning NOT skipped
    assert "a-alny" in asset_ids


# ---------------------------------------------------------------------------
# 5. Position capped at max_single_pct
# ---------------------------------------------------------------------------

def test_position_capped_at_max_single_pct():
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=2,
        max_single_pct=0.03,
        max_total_exposure_pct=0.20,
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80, recommended_size_pct=0.20),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert len(decisions) == 1
    assert decisions[0].recommended_size_pct <= 0.03


# ---------------------------------------------------------------------------
# 6. Total exposure capped at max_total_exposure_pct
# ---------------------------------------------------------------------------

def test_total_exposure_cap():
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=3,
        max_single_pct=0.05,
        max_total_exposure_pct=0.06,  # just over one position
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80, recommended_size_pct=0.05),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75, recommended_size_pct=0.05),
        _make_opportunity("a-ntla", "NTLA", "add", 0.65, recommended_size_pct=0.05),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    total = sum(d.recommended_size_pct for d in decisions)
    assert total <= 0.06 + 1e-9  # allow for floating-point epsilon


def test_total_exposure_already_full():
    """When current_total_exposure == max_total_exposure_pct, no new decisions."""
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=2,
        max_single_pct=0.05,
        max_total_exposure_pct=0.10,
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80, recommended_size_pct=0.05),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, current_total_exposure=0.10)
    assert decisions == []


# ---------------------------------------------------------------------------
# 7. Only "buy" / "add" actions are selected (not "monitor" or "avoid")
# ---------------------------------------------------------------------------

def test_only_actionable_actions_selected():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=5))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "monitor", 0.45),
        _make_opportunity("a-alny", "ALNY", "avoid", 0.20),
        _make_opportunity("a-ntla", "NTLA", "buy", 0.75),
        _make_opportunity("a-crsp", "CRSP", "add", 0.60),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    actions = {d.recommended_action for d in decisions}
    assert "monitor" not in actions
    assert "avoid" not in actions
    assert actions.issubset({"buy", "add"})


def test_only_actionable_all_monitor():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "monitor", 0.45),
        _make_opportunity("a-alny", "ALNY", "monitor", 0.40),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert decisions == []


# ---------------------------------------------------------------------------
# 8. Deterministic: same report → same decisions, same order
# ---------------------------------------------------------------------------

def test_deterministic_selection():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
        _make_opportunity("a-ntla", "NTLA", "add", 0.65),
    ]
    report = _make_report(opps)
    # Run selection three times — all must agree
    all_decisions = [policy.select(report) for _ in range(3)]
    for d_list in all_decisions[1:]:
        assert len(d_list) == len(all_decisions[0])
        for d1, d2 in zip(all_decisions[0], d_list):
            assert d1.asset_id == d2.asset_id
            assert d1.composite_score == d2.composite_score


def test_deterministic_ordering_by_score():
    """Higher composite_score should come first."""
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert len(decisions) == 2
    assert decisions[0].composite_score >= decisions[1].composite_score


def test_deterministic_tie_broken_by_ticker():
    """Equal composite scores → sorted by ticker alphabetically."""
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=1))
    opps = [
        _make_opportunity("a-z", "ZZZZ", "buy", 0.75),
        _make_opportunity("a-a", "AAAA", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert decisions[0].ticker == "AAAA"


# ---------------------------------------------------------------------------
# 9. exit_date() = entry_date + max_hold_days
# ---------------------------------------------------------------------------

def test_exit_date():
    policy = ReplayPolicy(ReplayPolicyConfig(max_hold_days=30))
    entry = date(2025, 6, 1)
    expected = date(2025, 7, 1)
    assert policy.exit_date(entry) == expected


def test_exit_date_custom_hold():
    policy = ReplayPolicy(ReplayPolicyConfig(max_hold_days=14))
    entry = date(2025, 12, 20)
    expected = date(2026, 1, 3)
    assert policy.exit_date(entry) == expected


def test_default_stop_loss_threshold():
    cfg = ReplayPolicyConfig()
    assert cfg.stop_loss_pct == pytest.approx(-40.0)


# ---------------------------------------------------------------------------
# 10. Empty report → empty decisions
# ---------------------------------------------------------------------------

def test_empty_report():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    report = _make_report([])
    decisions = policy.select(report)
    assert decisions == []


def test_report_with_no_actionable():
    """Report that has only monitor/avoid → empty decisions."""
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    opps = [
        _make_opportunity("a-rxrx", "RXRX", "monitor", 0.35),
        _make_opportunity("a-beam", "BEAM", "avoid", 0.25),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert decisions == []


# ---------------------------------------------------------------------------
# Additional: ReplayDecision dataclass fields
# ---------------------------------------------------------------------------

def test_replay_decision_defaults():
    dec = ReplayDecision(
        asset_id="a-vktx",
        ticker="VKTX",
        recommended_action="buy",
        recommended_size_pct=0.05,
        composite_score=0.80,
        decided_at=date(2025, 6, 1),
    )
    assert dec.is_simulated is True
    assert dec.reasoning == ""


def test_replay_decision_reasoning():
    dec = ReplayDecision(
        asset_id="a-alny",
        ticker="ALNY",
        recommended_action="add",
        recommended_size_pct=0.03,
        composite_score=0.65,
        decided_at=date(2025, 6, 1),
        reasoning="Zilebesiran KARDIA-2 upcoming",
    )
    assert dec.reasoning == "Zilebesiran KARDIA-2 upcoming"


# ---------------------------------------------------------------------------
# Additional: custom actionable_actions config
# ---------------------------------------------------------------------------

def test_custom_actionable_actions_only_buy():
    """Only 'buy' counted as actionable — 'add' excluded."""
    policy = ReplayPolicy(ReplayPolicyConfig(
        max_positions=2,
        actionable_actions=frozenset({"buy"}),
    ))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "add", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report)
    assert all(d.recommended_action == "buy" for d in decisions)


# ---------------------------------------------------------------------------
# Cooling gate tests
# ---------------------------------------------------------------------------

def test_cooling_blocks_cooled_asset():
    """Asset in cooling_asset_ids is skipped when cooling_enabled=True."""
    policy = ReplayPolicy(ReplayPolicyConfig(cooling_enabled=True))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, cooling_asset_ids={"a-vktx"})
    assert len(decisions) == 1
    assert decisions[0].ticker == "ALNY"


def test_cooling_disabled_ignores_cooling_set():
    """cooling_asset_ids has no effect when cooling_enabled=False."""
    policy = ReplayPolicy(ReplayPolicyConfig(cooling_enabled=False))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, cooling_asset_ids={"a-vktx"})
    assert len(decisions) == 2


def test_cooling_all_cooled_returns_empty():
    """All candidates cooled → empty decisions."""
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2, cooling_enabled=True))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, cooling_asset_ids={"a-vktx", "a-alny"})
    assert decisions == []


def test_cooling_none_cooling_set_no_effect():
    """cooling_asset_ids=None with cooling_enabled=True → no assets blocked."""
    policy = ReplayPolicy(ReplayPolicyConfig(cooling_enabled=True))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
    ]
    report = _make_report(opps)
    decisions = policy.select(report, cooling_asset_ids=None)
    assert len(decisions) == 1


# ---------------------------------------------------------------------------
# Loss-based blocking tests
# ---------------------------------------------------------------------------

def test_asset_blocked_after_large_loss_then_unblocked_after_eight_weeks():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=1))
    policy.record_closed_position("a-vktx", date(2025, 1, 1), -20.0)

    blocked_report = _make_report(
        [_make_opportunity("a-vktx", "VKTX", "buy", 0.80)],
        week_ending=date(2025, 2, 15),
    )
    assert policy.select(blocked_report) == []

    unblocked_report = _make_report(
        [_make_opportunity("a-vktx", "VKTX", "buy", 0.80)],
        week_ending=date(2025, 2, 26),
    )
    decisions = policy.select(unblocked_report)
    assert len(decisions) == 1
    assert decisions[0].asset_id == "a-vktx"


def test_only_one_entry_per_asset_per_step(capsys: pytest.CaptureFixture[str]):
    policy = ReplayPolicy(
        ReplayPolicyConfig(
            max_positions=3,
            max_total_exposure_pct=0.20,
        )
    )
    report = _make_report([
        _make_opportunity("a-vktx", "VKTX", "buy", 0.90),
        _make_opportunity("a-vktx", "VKTX", "add", 0.85),
        _make_opportunity("a-alny", "ALNY", "buy", 0.80),
    ])

    decisions = policy.select(report)

    assert [d.asset_id for d in decisions] == ["a-vktx", "a-alny"]
    assert capsys.readouterr().out.count("Skipped duplicate entry for a-vktx") == 1


def test_asset_permanently_blocked_after_three_consecutive_losses(
    capsys: pytest.CaptureFixture[str],
):
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=1, max_consecutive_losses=3))
    policy.record_closed_position("a-vktx", date(2025, 1, 1), -5.0)
    policy.record_closed_position("a-vktx", date(2025, 1, 15), -6.0)
    policy.record_closed_position("a-vktx", date(2025, 1, 29), -7.0)

    report = _make_report(
        [_make_opportunity("a-vktx", "VKTX", "buy", 0.80)],
        week_ending=date(2025, 2, 5),
    )
    assert policy.select(report) == []
    assert "Permanently blocked a-vktx: 3 consecutive losses" in capsys.readouterr().out


def test_loss_blocking_does_not_affect_other_assets():
    policy = ReplayPolicy(ReplayPolicyConfig(max_positions=2))
    policy.record_closed_position("a-vktx", date(2025, 1, 1), -20.0)

    report = _make_report(
        [
            _make_opportunity("a-vktx", "VKTX", "buy", 0.90),
            _make_opportunity("a-alny", "ALNY", "buy", 0.80),
        ],
        week_ending=date(2025, 1, 20),
    )

    decisions = policy.select(report)
    assert [d.asset_id for d in decisions] == ["a-alny"]


# ---------------------------------------------------------------------------
# Catalyst density gate tests
# ---------------------------------------------------------------------------

def test_catalyst_density_blocks_no_catalyst():
    """require_catalyst_within_days=14: asset with no catalyst is blocked."""
    policy = ReplayPolicy(ReplayPolicyConfig(require_catalyst_within_days=14))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    week = date(2025, 9, 1)
    report = WeeklyActionableReport(
        opportunities=opps,
        week_ending=week,
        score_version=CURRENT_SCORE_VERSION,
        generated_at=week,
    )
    # ALNY has catalyst in 7 days (within 14), VKTX has no catalyst
    catalyst_dates = {"a-alny": week + timedelta(days=7)}
    decisions = policy.select(report, catalyst_dates=catalyst_dates)
    assert len(decisions) == 1
    assert decisions[0].ticker == "ALNY"


def test_catalyst_density_blocks_far_catalyst():
    """Catalyst exists but is beyond require_catalyst_within_days window → blocked."""
    policy = ReplayPolicy(ReplayPolicyConfig(require_catalyst_within_days=14))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
    ]
    week = date(2025, 9, 1)
    report = WeeklyActionableReport(
        opportunities=opps,
        week_ending=week,
        score_version=CURRENT_SCORE_VERSION,
        generated_at=week,
    )
    catalyst_dates = {"a-vktx": week + timedelta(days=20)}  # 20 days > 14
    decisions = policy.select(report, catalyst_dates=catalyst_dates)
    assert decisions == []


def test_catalyst_density_allows_near_catalyst():
    """Catalyst within window → entry allowed."""
    policy = ReplayPolicy(ReplayPolicyConfig(require_catalyst_within_days=14))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
    ]
    week = date(2025, 9, 1)
    report = WeeklyActionableReport(
        opportunities=opps,
        week_ending=week,
        score_version=CURRENT_SCORE_VERSION,
        generated_at=week,
    )
    catalyst_dates = {"a-vktx": week + timedelta(days=10)}  # 10 days ≤ 14
    decisions = policy.select(report, catalyst_dates=catalyst_dates)
    assert len(decisions) == 1


def test_catalyst_density_zero_disabled():
    """require_catalyst_within_days=0 disables the gate → all pass through."""
    policy = ReplayPolicy(ReplayPolicyConfig(require_catalyst_within_days=0))
    opps = [
        _make_opportunity("a-vktx", "VKTX", "buy", 0.80),
        _make_opportunity("a-alny", "ALNY", "buy", 0.75),
    ]
    report = _make_report(opps)
    # No catalyst_dates at all — gate disabled, both pass through
    decisions = policy.select(report, catalyst_dates=None)
    assert len(decisions) == 2  # gate off, both candidates selected

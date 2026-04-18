"""Tests for Phase 5 learning engine components."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

from bve.learning.outcome_linker import OutcomeLinker
from bve.learning.recalibration_job import RecalibrationJob
from bve.learning.shadow_backtest import ShadowBacktest, ShadowBacktestConfig, ShadowBacktestResult
from bve.learning.weight_promotion import PromotionResult, WeightPromoter
from bve.learning.weight_updates import WeightUpdate, WeightUpdateEngine
from bve.persistence.gap_fill_store import DecisionRecord, OutcomeRecord, ParameterVersion


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_decision(composite_score: float = 0.65) -> DecisionRecord:
    return DecisionRecord(
        decision_id=str(uuid4()),
        asset_id="asset-001",
        ticker="DEMO",
        decision_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
        action="add",
        target_position_pct=5.0,
        composite_score=composite_score,
        rationale="Test decision",
    )


def _make_outcome(
    return_pct: float,
    attribution: str = "unclassified",
    catalyst_triggered: bool = False,
    thesis_confirmed: bool | None = None,
) -> OutcomeRecord:
    return OutcomeRecord(
        decision_id=str(uuid4()),
        asset_id="asset-001",
        ticker="DEMO",
        decision_date=date(2025, 1, 10),
        outcome_date=date(2025, 2, 10),
        return_realized_pct=return_pct,
        catalyst_triggered=catalyst_triggered,
        thesis_confirmed=thesis_confirmed,
        attribution=attribution,
    )


def _make_weight_update(
    approved: bool = True,
    requires_human_review: bool = False,
) -> WeightUpdate:
    return WeightUpdate(
        update_id=str(uuid4()),
        module="pos",
        parameter_name="phase2_success_rate",
        old_value=0.35,
        new_value=0.40,
        delta=0.05,
        rationale="Improved calibration from backtest data.",
        created_at=datetime.now(timezone.utc),
        approved=approved,
        requires_human_review=requires_human_review,
    )


# ---------------------------------------------------------------------------
# OutcomeLinker tests
# ---------------------------------------------------------------------------


class TestOutcomeLinker:
    def test_confirmed_thesis_catalyst_positive_return(self):
        """catalyst triggered + positive return → confirmed_thesis."""
        linker = OutcomeLinker()
        decision = _make_decision()
        outcome = linker.link(
            decision,
            outcome_date=date(2025, 2, 10),
            return_realized_pct=0.15,
            catalyst_triggered=True,
            thesis_confirmed=True,
        )
        assert outcome.attribution == "confirmed_thesis"

    def test_thesis_error_no_catalyst_negative_return(self):
        """no catalyst + negative return → thesis_error."""
        linker = OutcomeLinker()
        decision = _make_decision()
        outcome = linker.link(
            decision,
            outcome_date=date(2025, 2, 10),
            return_realized_pct=-0.08,
            catalyst_triggered=False,
        )
        assert outcome.attribution == "thesis_error"

    def test_market_drift_no_catalyst_positive_return(self):
        """no catalyst + positive return → market_drift."""
        linker = OutcomeLinker()
        decision = _make_decision()
        outcome = linker.link(
            decision,
            outcome_date=date(2025, 2, 10),
            return_realized_pct=0.05,
            catalyst_triggered=False,
        )
        assert outcome.attribution == "market_drift"

    def test_timing_error_positive_catalyst_negative_return(self):
        """positive catalyst event + negative return → timing_error."""
        linker = OutcomeLinker()
        decision = _make_decision()
        outcome = linker.link(
            decision,
            outcome_date=date(2025, 2, 10),
            return_realized_pct=-0.12,
            catalyst_triggered=True,
            thesis_confirmed=True,
        )
        assert outcome.attribution == "timing_error"

    def test_pos_error_negative_catalyst_positive_return(self):
        """negative catalyst event + positive return → pos_error."""
        linker = OutcomeLinker()
        decision = _make_decision()
        outcome = linker.link(
            decision,
            outcome_date=date(2025, 2, 10),
            return_realized_pct=0.15,
            catalyst_triggered=True,
            thesis_confirmed=False,
        )
        assert outcome.attribution == "pos_error"

    def test_link_returns_outcome_record_with_correct_fields(self):
        """link() returns OutcomeRecord with correctly populated fields."""
        linker = OutcomeLinker()
        decision = _make_decision()
        outcome_date = date(2025, 3, 15)
        outcome = linker.link(
            decision,
            outcome_date=outcome_date,
            return_realized_pct=0.20,
            catalyst_triggered=True,
            catalyst_description="Phase 3 readout positive",
            thesis_confirmed=True,
        )
        assert outcome.decision_id == decision.decision_id
        assert outcome.asset_id == decision.asset_id
        assert outcome.ticker == decision.ticker
        assert outcome.outcome_date == outcome_date
        assert outcome.return_realized_pct == 0.20
        assert outcome.catalyst_triggered is True
        assert outcome.catalyst_description == "Phase 3 readout positive"
        assert outcome.thesis_confirmed is True

    def test_link_batch_processes_multiple_decisions(self):
        """link_batch returns an outcome for each decision with a matching return."""
        linker = OutcomeLinker()
        decisions = [_make_decision() for _ in range(3)]
        returns = {d.decision_id: float(i) * 0.05 for i, d in enumerate(decisions)}
        outcomes = linker.link_batch(decisions, returns, outcome_date=date(2025, 4, 1))
        assert len(outcomes) == 3

    def test_link_batch_skips_missing_decision_ids(self):
        """link_batch skips decisions whose ID is absent from returns_by_decision_id."""
        linker = OutcomeLinker()
        decisions = [_make_decision() for _ in range(4)]
        # Only provide returns for first two
        returns = {decisions[0].decision_id: 0.10, decisions[1].decision_id: -0.05}
        outcomes = linker.link_batch(decisions, returns, outcome_date=date(2025, 4, 1))
        assert len(outcomes) == 2
        result_ids = {o.decision_id for o in outcomes}
        assert decisions[0].decision_id in result_ids
        assert decisions[1].decision_id in result_ids


# ---------------------------------------------------------------------------
# RecalibrationJob tests
# ---------------------------------------------------------------------------


class TestRecalibrationJob:
    def test_ingest_outcomes_runs_without_error(self):
        """ingest_outcomes processes a list of outcomes without raising."""
        job = RecalibrationJob()
        outcomes = [
            _make_outcome(0.10, attribution="confirmed_thesis", catalyst_triggered=True),
            _make_outcome(-0.05, attribution="thesis_error"),
            _make_outcome(0.08, attribution="market_drift"),
            _make_outcome(-0.12, attribution="pos_error", catalyst_triggered=True),
        ]
        job.ingest_outcomes(outcomes)  # should not raise

    def test_summarize_returns_list(self):
        """summarize returns a list (may be empty if no resolved records)."""
        job = RecalibrationJob()
        summaries = job.summarize()
        assert isinstance(summaries, list)

    def test_summarize_after_ingest_returns_non_empty(self):
        """After ingesting outcomes, summarize returns summaries for affected modules."""
        job = RecalibrationJob()
        outcomes = [
            _make_outcome(0.10, attribution="pos_error", catalyst_triggered=True),
            _make_outcome(-0.10, attribution="thesis_error"),
        ]
        job.ingest_outcomes(outcomes)
        summaries = job.summarize()
        assert len(summaries) > 0

    def test_generate_bias_report_returns_bias_report(self):
        """generate_bias_report returns a BiasReport object."""
        from bve.learning.bias_report import BiasReport

        job = RecalibrationJob()
        outcomes = [
            _make_outcome(0.10, attribution="confirmed_thesis"),
            _make_outcome(-0.05, attribution="thesis_error"),
        ]
        job.ingest_outcomes(outcomes)
        report = job.generate_bias_report()
        assert isinstance(report, BiasReport)
        assert report.report_id
        assert isinstance(report.recommendations, list)


# ---------------------------------------------------------------------------
# ShadowBacktest tests
# ---------------------------------------------------------------------------


class TestShadowBacktest:
    def test_empty_outcomes_returns_hold(self):
        """Empty outcome list fails gate and returns 'hold'."""
        sb = ShadowBacktest()
        result = sb.run([])
        assert result.passed is False
        assert result.recommendation == "hold"
        assert result.n_decisions == 0

    def test_too_few_outcomes_returns_hold(self):
        """Fewer than min_decisions_required → 'hold'."""
        config = ShadowBacktestConfig(min_decisions_required=10)
        sb = ShadowBacktest(config)
        outcomes = [_make_outcome(0.10) for _ in range(5)]
        result = sb.run(outcomes)
        assert result.passed is False
        assert result.recommendation == "hold"

    def test_all_positive_returns_low_error_returns_promote(self):
        """All positive returns and low attribution error rate → 'promote'."""
        config = ShadowBacktestConfig(
            min_decisions_required=5,
            min_positive_return_rate=0.50,
            max_attribution_error_rate=0.40,
        )
        sb = ShadowBacktest(config)
        outcomes = [
            _make_outcome(0.10, attribution="confirmed_thesis") for _ in range(8)
        ]
        result = sb.run(outcomes)
        assert result.passed is True
        assert result.recommendation == "promote"

    def test_high_attribution_error_rate_returns_reject(self):
        """Attribution error rate exceeding threshold → 'reject'."""
        config = ShadowBacktestConfig(
            min_decisions_required=5,
            min_positive_return_rate=0.50,
            max_attribution_error_rate=0.20,
        )
        sb = ShadowBacktest(config)
        # 6/10 outcomes are error attributions (60%)
        outcomes = (
            [_make_outcome(-0.05, attribution="thesis_error") for _ in range(6)]
            + [_make_outcome(0.10, attribution="confirmed_thesis") for _ in range(4)]
        )
        result = sb.run(outcomes)
        assert result.passed is False
        assert result.recommendation == "reject"

    def test_low_positive_return_rate_returns_reject(self):
        """Positive return rate below threshold → 'reject'."""
        config = ShadowBacktestConfig(
            min_decisions_required=5,
            min_positive_return_rate=0.60,
            max_attribution_error_rate=0.40,
        )
        sb = ShadowBacktest(config)
        # Only 3/10 positive returns (30%)
        outcomes = (
            [_make_outcome(0.05, attribution="market_drift") for _ in range(3)]
            + [_make_outcome(-0.05, attribution="thesis_error") for _ in range(7)]
        )
        result = sb.run(outcomes)
        assert result.passed is False
        assert result.recommendation == "reject"

    def test_shadow_backtest_result_fields_accessible(self):
        """ShadowBacktestResult has all required fields."""
        result = ShadowBacktestResult(
            passed=True,
            n_decisions=10,
            positive_return_rate=0.70,
            attribution_error_rate=0.20,
            mean_return_pct=0.08,
            recommendation="promote",
            notes=["All gates passed."],
        )
        assert result.passed is True
        assert result.n_decisions == 10
        assert result.positive_return_rate == 0.70
        assert result.attribution_error_rate == 0.20
        assert result.mean_return_pct == 0.08
        assert result.recommendation == "promote"
        assert result.notes == ["All gates passed."]


# ---------------------------------------------------------------------------
# WeightPromoter tests
# ---------------------------------------------------------------------------


class TestWeightPromoter:
    def test_promote_approved_not_human_review_backtest_passed(self):
        """approved + not requires_human_review + backtest passed → promoted=True."""
        promoter = WeightPromoter()
        update = _make_weight_update(approved=True, requires_human_review=False)
        backtest = ShadowBacktestResult(
            passed=True,
            n_decisions=15,
            positive_return_rate=0.67,
            attribution_error_rate=0.10,
            mean_return_pct=0.05,
            recommendation="promote",
            notes=["All gates passed."],
        )
        result = promoter.promote(update, backtest)
        assert result.promoted is True
        assert result.new_version_id is not None
        assert result.promoted_at is not None

    def test_promote_requires_human_review_not_promoted(self):
        """requires_human_review=True → never auto-promoted."""
        promoter = WeightPromoter()
        update = _make_weight_update(approved=True, requires_human_review=True)
        backtest = ShadowBacktestResult(
            passed=True,
            n_decisions=15,
            positive_return_rate=0.67,
            attribution_error_rate=0.10,
            mean_return_pct=0.05,
            recommendation="promote",
            notes=[],
        )
        result = promoter.promote(update, backtest)
        assert result.promoted is False
        assert "human review" in result.reason.lower()

    def test_promote_backtest_failed_not_promoted(self):
        """Backtest not passed → not promoted."""
        promoter = WeightPromoter()
        update = _make_weight_update(approved=True, requires_human_review=False)
        backtest = ShadowBacktestResult(
            passed=False,
            n_decisions=15,
            positive_return_rate=0.40,
            attribution_error_rate=0.10,
            mean_return_pct=-0.02,
            recommendation="reject",
            notes=["Low positive return rate."],
        )
        result = promoter.promote(update, backtest)
        assert result.promoted is False
        assert result.new_version_id is None

    def test_promote_not_approved_not_promoted(self):
        """Update not approved → not promoted."""
        promoter = WeightPromoter()
        update = _make_weight_update(approved=False, requires_human_review=False)
        backtest = ShadowBacktestResult(
            passed=True,
            n_decisions=15,
            positive_return_rate=0.67,
            attribution_error_rate=0.10,
            mean_return_pct=0.05,
            recommendation="promote",
            notes=[],
        )
        result = promoter.promote(update, backtest)
        assert result.promoted is False
        assert result.new_version_id is None

    def test_build_parameter_version_returns_valid_parameter_version(self):
        """build_parameter_version returns a ParameterVersion with correct fields."""
        promoter = WeightPromoter()
        update = _make_weight_update(approved=True, requires_human_review=False)
        pv = promoter.build_parameter_version(update)
        assert isinstance(pv, ParameterVersion)
        assert pv.module == update.module
        assert update.parameter_name in pv.parameters
        assert pv.parameters[update.parameter_name] == update.new_value
        assert pv.is_active is True
        assert pv.promoted_from_backtest is True

    def test_promotion_result_fields_accessible(self):
        """PromotionResult has all required fields."""
        result = PromotionResult(
            update_id="test-uuid",
            promoted=True,
            reason="All gates passed.",
            new_version_id="new-version-uuid",
            promoted_at=datetime.now(timezone.utc),
        )
        assert result.update_id == "test-uuid"
        assert result.promoted is True
        assert result.reason == "All gates passed."
        assert result.new_version_id == "new-version-uuid"
        assert result.promoted_at is not None


# ---------------------------------------------------------------------------
# End-to-end test
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def test_end_to_end_create_link_ingest_backtest_promote(self):
        """
        Full pipeline: create decision → link outcome → ingest → backtest → promote.
        """
        # 1. Create a decision
        decision = _make_decision(composite_score=0.70)

        # 2. Link to an outcome
        linker = OutcomeLinker()
        outcome = linker.link(
            decision,
            outcome_date=date(2025, 3, 1),
            return_realized_pct=0.18,
            catalyst_triggered=True,
            thesis_confirmed=True,
            catalyst_description="Phase 3 data readout",
        )
        assert outcome.attribution == "confirmed_thesis"

        # 3. Ingest into recalibration job
        job = RecalibrationJob()
        job.ingest_outcomes([outcome])
        summaries = job.summarize()
        assert len(summaries) >= 1

        bias_report = job.generate_bias_report()
        assert bias_report is not None

        # 4. Build enough outcomes for shadow backtest to pass
        outcomes_bulk = [
            _make_outcome(0.10, attribution="confirmed_thesis") for _ in range(12)
        ]

        config = ShadowBacktestConfig(
            min_decisions_required=10,
            min_positive_return_rate=0.50,
            max_attribution_error_rate=0.40,
        )
        sb = ShadowBacktest(config)
        backtest_result = sb.run(outcomes_bulk)
        assert backtest_result.passed is True
        assert backtest_result.recommendation == "promote"

        # 5. Promote weight update
        update_engine = WeightUpdateEngine()
        update = update_engine.propose_update(
            module="pos",
            parameter_name="phase2_base_rate",
            old_value=0.35,
            new_value=0.40,
            rationale="Calibration improved based on outcome data.",
        )
        # Override human review flag (not possible on frozen model — create directly)
        approved_update = WeightUpdate(
            update_id=update.update_id,
            module=update.module,
            parameter_name=update.parameter_name,
            old_value=update.old_value,
            new_value=update.new_value,
            delta=update.delta,
            rationale=update.rationale,
            created_at=update.created_at,
            approved=True,
            requires_human_review=False,
        )

        promoter = WeightPromoter(update_engine)
        promotion = promoter.promote(approved_update, backtest_result)
        assert promotion.promoted is True
        assert promotion.new_version_id is not None

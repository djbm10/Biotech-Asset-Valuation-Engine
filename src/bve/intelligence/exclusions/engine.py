"""ExclusionEngine — runs all 11 gates and produces a final ExclusionAssessment.

Public API
----------
evaluate_company_exclusions(company: CompanyProfile) -> ExclusionAssessment
    Run Gates 0–1, 3–10 (company-level gates only).

evaluate_pair_exclusions(
    company: CompanyProfile, acquirer: AcquirerProfile
) -> ExclusionAssessment
    Run all gates including the pair-level Gate 2.

apply_exclusion_assessment_to_score(
    raw_score: float, assessment: ExclusionAssessment
) -> float | None
    Apply the assessment verdict to a raw M&A score:
    - HARD_FAIL / HISTORICAL_ONLY / ROUTE_TO_OTHER_MODEL → None (excluded)
    - DILIGENCE_QUEUE / REFRESH_REQUIRED                → None (hold)
    - SEVERE_CAP / PAIR_LEVEL_CAP                       → min(raw_score, max_score_cap)
    - PAIR_LEVEL_FAIL                                   → None (pair excluded)
    - PASS                                              → raw_score unchanged

Integration with ma_eligibility.py (Layer 0)
---------------------------------------------
This engine replaces the ``_evaluate_hard_exclusion`` (0A) section in
``ma_eligibility.py``.  Call ``evaluate_company_exclusions()`` before
assembling the ``Layer0Result``:

    assessment = engine.evaluate_company_exclusions(profile)
    if not assessment.live_ranking_eligible:
        # Hard exclude or route — Layer 0 short-circuits here.
        ...
    # Otherwise continue with Layer 0 0B–0G as before, but also honour
    # assessment.max_score_cap as an additional cap.
"""
from __future__ import annotations

import logging
from typing import Optional

from .enums import ExclusionStatus, most_severe, RoutingModel
from .models import AcquirerProfile, CompanyProfile, ExclusionAssessment, GateResult
from .rules import (
    gate_0_entity_validity,
    gate_1_corporate_status,
    gate_2_buyer_target_validity,
    gate_3_asset_visibility,
    gate_4_asset_viability,
    gate_5_rights_ip_ownership,
    gate_6_financial_going_concern,
    gate_7_market_data_quality,
    gate_8_legal_integrity,
    gate_9_commercial_relevance,
    gate_10_model_routing,
)

_LOG = logging.getLogger("bve.intelligence.exclusions.engine")

# Statuses that prevent a company from appearing in the live ranked output.
_LIVE_RANKING_BLOCKED: frozenset[ExclusionStatus] = frozenset({
    ExclusionStatus.HARD_FAIL,
    ExclusionStatus.HISTORICAL_ONLY,
    ExclusionStatus.ROUTE_TO_OTHER_MODEL,
    ExclusionStatus.DILIGENCE_QUEUE,
    ExclusionStatus.REFRESH_REQUIRED,
    ExclusionStatus.PAIR_LEVEL_FAIL,
})

# Statuses that allow historical training / backtest use.
_HISTORICAL_ELIGIBLE: frozenset[ExclusionStatus] = frozenset({
    ExclusionStatus.HISTORICAL_ONLY,
    ExclusionStatus.PASS,
    ExclusionStatus.SEVERE_CAP,
    ExclusionStatus.PAIR_LEVEL_CAP,
})


def _collapse_gate_results(gate_results: list[GateResult]) -> ExclusionAssessment:
    """Derive final ExclusionAssessment from a list of individual GateResults."""
    raise NotImplementedError("use _build_assessment()")


def _build_assessment(
    company: CompanyProfile,
    gate_results: list[GateResult],
    acquirer_id: Optional[str] = None,
) -> ExclusionAssessment:
    """Collapse gate results into a final ExclusionAssessment."""
    statuses = [g.status for g in gate_results]
    overall = most_severe(statuses)

    live_eligible = overall not in _LIVE_RANKING_BLOCKED
    historical_eligible = (
        overall == ExclusionStatus.HISTORICAL_ONLY
        or (live_eligible and overall in _HISTORICAL_ELIGIBLE)
    )

    # Determine routing model: first non-None route_to_model wins.
    routed_model: Optional[RoutingModel] = None
    for gr in gate_results:
        if gr.route_to_model is not None:
            routed_model = gr.route_to_model
            break

    # Score cap: most restrictive (lowest) cap across all SEVERE_CAP / PAIR_LEVEL_CAP gates.
    cap_values = [
        gr.score_cap
        for gr in gate_results
        if gr.score_cap is not None
        and gr.status in (ExclusionStatus.SEVERE_CAP, ExclusionStatus.PAIR_LEVEL_CAP)
    ]
    max_score_cap: Optional[float] = min(cap_values) if cap_values else None

    # Diligence flags: reasons from DILIGENCE_QUEUE gates.
    diligence_flags = [
        f"{gr.gate_name.value}:{gr.reason}"
        for gr in gate_results
        if gr.status == ExclusionStatus.DILIGENCE_QUEUE
    ]

    # Roll-up of all triggered rule IDs.
    triggered_rules = [
        rule
        for gr in gate_results
        for rule in gr.triggered_rules
    ]

    # Human-readable summary.
    non_pass = [gr for gr in gate_results if gr.status != ExclusionStatus.PASS]
    if non_pass:
        summary = "; ".join(f"[{gr.gate_name.value}] {gr.reason}" for gr in non_pass)
    else:
        summary = "all_gates_passed"

    return ExclusionAssessment(
        company_id=company.company_id,
        ticker=company.ticker,
        acquirer_id=acquirer_id,
        overall_status=overall,
        live_ranking_eligible=live_eligible,
        historical_training_eligible=historical_eligible,
        routed_model=routed_model,
        max_score_cap=max_score_cap,
        diligence_flags=diligence_flags,
        all_gate_results=gate_results,
        triggered_exclusion_rules=triggered_rules,
        exclusion_reason_summary=summary,
    )


class ExclusionEngine:
    """Run the full 11-gate exclusion/routing cascade for M&A targets.

    Usage::

        engine = ExclusionEngine()

        # Company-level assessment (no specific acquirer)
        assessment = engine.evaluate_company_exclusions(profile)

        # Pair-level assessment (with a specific acquirer)
        assessment = engine.evaluate_pair_exclusions(profile, acquirer)

        # Adjust a raw score using the assessment verdict
        final_score = engine.apply_exclusion_assessment_to_score(0.82, assessment)
    """

    def evaluate_company_exclusions(self, company: CompanyProfile) -> ExclusionAssessment:
        """Run all company-level gates (Gates 0–1, 3–10).

        Gate 2 (buyer-target pair validation) is skipped because no acquirer
        is provided.  Call ``evaluate_pair_exclusions()`` when a specific
        acquirer needs to be validated.

        Gates run in strict order.  HARD_FAIL gates short-circuit — remaining
        gates are skipped once a HARD_FAIL is emitted to avoid spurious
        additional signals that cannot change the outcome.
        """
        gate_results: list[GateResult] = []

        for gate_fn in (
            gate_0_entity_validity,
            gate_1_corporate_status,
            # Gate 2 skipped — pair-level
            gate_3_asset_visibility,
            gate_4_asset_viability,
            gate_5_rights_ip_ownership,
            gate_6_financial_going_concern,
            gate_7_market_data_quality,
            gate_8_legal_integrity,
            gate_9_commercial_relevance,
            gate_10_model_routing,
        ):
            result = gate_fn(company)
            gate_results.append(result)
            # Short-circuit on HARD_FAIL — subsequent gates cannot override.
            if result.status == ExclusionStatus.HARD_FAIL:
                _LOG.debug(
                    "ExclusionEngine: HARD_FAIL at %s for %s — skipping remaining gates",
                    result.gate_name.value,
                    company.company_id,
                )
                break

        return _build_assessment(company, gate_results, acquirer_id=None)

    def evaluate_pair_exclusions(
        self,
        company: CompanyProfile,
        acquirer: AcquirerProfile,
    ) -> ExclusionAssessment:
        """Run all gates including the pair-level Gate 2.

        Company-level gates that produce HARD_FAIL still short-circuit.
        Gate 2 is injected after Gate 1 in the gate order.
        """
        gate_results: list[GateResult] = []

        for gate_fn in (gate_0_entity_validity, gate_1_corporate_status):
            result = gate_fn(company)
            gate_results.append(result)
            if result.status == ExclusionStatus.HARD_FAIL:
                return _build_assessment(company, gate_results, acquirer_id=acquirer.acquirer_id)

        # Gate 2 — pair-level
        pair_result = gate_2_buyer_target_validity(company, acquirer)
        gate_results.append(pair_result)
        # PAIR_LEVEL_FAIL does not short-circuit company-level gates;
        # the company may still rank against other acquirers.

        for gate_fn in (
            gate_3_asset_visibility,
            gate_4_asset_viability,
            gate_5_rights_ip_ownership,
            gate_6_financial_going_concern,
            gate_7_market_data_quality,
            gate_8_legal_integrity,
            gate_9_commercial_relevance,
            gate_10_model_routing,
        ):
            result = gate_fn(company)
            gate_results.append(result)
            if result.status == ExclusionStatus.HARD_FAIL:
                break

        return _build_assessment(company, gate_results, acquirer_id=acquirer.acquirer_id)

    def apply_exclusion_assessment_to_score(
        self,
        raw_score: float,
        assessment: ExclusionAssessment,
    ) -> Optional[float]:
        """Apply the assessment verdict to a raw M&A probability score.

        Returns None when the company (or pair) should be excluded from live
        ranking.  Returns the capped score when SEVERE_CAP or PAIR_LEVEL_CAP
        applies.  Returns raw_score unchanged when status is PASS.

        Note: PAIR_LEVEL_FAIL and PAIR_LEVEL_CAP only make sense when the
        assessment was produced by ``evaluate_pair_exclusions()``.
        """
        s = assessment.overall_status

        if s in (
            ExclusionStatus.HARD_FAIL,
            ExclusionStatus.HISTORICAL_ONLY,
            ExclusionStatus.ROUTE_TO_OTHER_MODEL,
            ExclusionStatus.DILIGENCE_QUEUE,
            ExclusionStatus.REFRESH_REQUIRED,
            ExclusionStatus.PAIR_LEVEL_FAIL,
        ):
            return None

        if s in (ExclusionStatus.SEVERE_CAP, ExclusionStatus.PAIR_LEVEL_CAP):
            if assessment.max_score_cap is not None:
                return min(raw_score, assessment.max_score_cap)
            return raw_score  # cap declared but no value — treat as PASS

        return raw_score  # PASS


# ---------------------------------------------------------------------------
# Module-level convenience wrappers
# ---------------------------------------------------------------------------

_DEFAULT_ENGINE = ExclusionEngine()


def evaluate_company_exclusions(company: CompanyProfile) -> ExclusionAssessment:
    """Module-level convenience — uses a shared default ExclusionEngine."""
    return _DEFAULT_ENGINE.evaluate_company_exclusions(company)


def evaluate_pair_exclusions(
    company: CompanyProfile,
    acquirer: AcquirerProfile,
) -> ExclusionAssessment:
    """Module-level convenience — uses a shared default ExclusionEngine."""
    return _DEFAULT_ENGINE.evaluate_pair_exclusions(company, acquirer)


def apply_exclusion_assessment_to_score(
    raw_score: float,
    assessment: ExclusionAssessment,
) -> Optional[float]:
    """Module-level convenience — uses a shared default ExclusionEngine."""
    return _DEFAULT_ENGINE.apply_exclusion_assessment_to_score(raw_score, assessment)

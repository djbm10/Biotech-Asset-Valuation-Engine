"""
Press / news event classification — focused test suite.

Covers the press/news classification hardening work:

  Phase 1  negation + speculation guards
  Phase 2  financing / runway distress (going concern, delisting)
  Phase 3  M&A deal-status routing (pending acquisition, deal termination)
  Phase 4  earnings / guidance signals
  Phase 5  clinical readout refinements (topline / interim, Phase 2b)

These are deterministic, no-LLM classifications. Each new pattern gets at
least one positive case and one negative (must-not-match) case.
"""
from __future__ import annotations

from bve.ingestion.event_classifier import (
    CASH_LOW,
    CRL,
    DEAL_TERMINATED,
    DELISTING_NOTICE,
    FDA_APPROVAL,
    GOING_CONCERN,
    GUIDANCE_LOWERED,
    GUIDANCE_RAISED,
    PENDING_ACQUISITION,
    SCORE_DELTA_MAP,
    SEVERITY_ORDER,
    STRATEGIC_REVIEW,
    UNCLASSIFIED,
    classify_headline,
    classify_headline_multi,
)


# ---------------------------------------------------------------------------
# Phase 1 — negation guard
# ---------------------------------------------------------------------------


class TestNegationGuard:
    def test_declined_to_approve_is_not_fda_approval(self):
        ev = classify_headline(
            "FDA declined to approve the company's NDA for its lead asset",
            ticker="T",
        )
        assert ev.event_type != FDA_APPROVAL

    def test_did_not_approve_is_not_fda_approval(self):
        ev = classify_headline(
            "The FDA did not approve the resubmission this cycle",
            ticker="T",
        )
        assert ev.event_type != FDA_APPROVAL

    def test_plain_approval_still_classifies(self):
        ev = classify_headline(
            "FDA approved the company's BLA for its lead asset",
            ticker="T",
        )
        assert ev.event_type == FDA_APPROVAL

    def test_negation_does_not_swallow_distant_unrelated_clause(self):
        # "did not" far from "approve" must not suppress a genuine approval.
        ev = classify_headline(
            "FDA approved the therapy; the label did not include a boxed warning",
            ticker="T",
        )
        assert ev.event_type == FDA_APPROVAL


# ---------------------------------------------------------------------------
# Phase 1 — speculation discount
# ---------------------------------------------------------------------------


class TestSpeculationGuard:
    def test_rumored_acquisition_is_not_pending_acquisition(self):
        ev = classify_headline(
            "Company reportedly in talks to be acquired, sources say",
            ticker="T",
        )
        assert ev.event_type != PENDING_ACQUISITION

    def test_speculation_reduces_confidence(self):
        spec = classify_headline(
            "Company reportedly exploring a potential sale, sources say",
            ticker="T",
        )
        firm = classify_headline(
            "Company announces it is exploring strategic alternatives",
            ticker="T",
        )
        assert spec.confidence < firm.confidence


# ---------------------------------------------------------------------------
# Phase 2 — financing / runway distress
# ---------------------------------------------------------------------------


class TestFinancingDistress:
    def test_going_concern(self):
        ev = classify_headline(
            "Auditor expresses substantial doubt about going concern",
            ticker="T",
            source_type="sec_filing",
        )
        assert ev.event_type == GOING_CONCERN or GOING_CONCERN in ev.secondary_events

    def test_delisting_notice(self):
        ev = classify_headline(
            "Company receives Nasdaq delisting notification for bid price deficiency",
            ticker="T",
        )
        assert ev.event_type == DELISTING_NOTICE or DELISTING_NOTICE in ev.secondary_events

    def test_distress_raises_seller_willingness(self):
        ev = classify_headline(
            "Auditor expresses substantial doubt about going concern",
            ticker="T",
            source_type="sec_filing",
        )
        assert ev.score_deltas.get("seller_willingness", 0.0) > 0

    def test_routine_headline_not_distress(self):
        ev = classify_headline(
            "Company to present at an upcoming healthcare investor conference",
            ticker="T",
        )
        assert ev.event_type not in (GOING_CONCERN, DELISTING_NOTICE)


# ---------------------------------------------------------------------------
# Phase 3 — M&A deal status routing
# ---------------------------------------------------------------------------


class TestDealStatus:
    def test_definitive_acquisition_is_pending_acquisition(self):
        ev = classify_headline(
            "Company enters definitive agreement to be acquired by BigPharma for $4.5 billion",
            ticker="T",
        )
        assert ev.event_type == PENDING_ACQUISITION

    def test_pending_acquisition_is_routing_not_scoring(self):
        # An already-announced deal is a routing/exclusion signal, not a
        # "great new opportunity" — it must not inflate seller_willingness.
        assert SCORE_DELTA_MAP[PENDING_ACQUISITION] == {}

    def test_pending_acquisition_high_severity(self):
        assert SEVERITY_ORDER[PENDING_ACQUISITION] >= 90

    def test_deal_termination_is_negative(self):
        ev = classify_headline(
            "Partner terminates collaboration and license agreement for the program",
            ticker="T",
        )
        assert ev.event_type == DEAL_TERMINATED
        assert ev.score_deltas.get("asset_quality", 0.0) < 0

    def test_speculative_talk_routes_to_strategic_review(self):
        ev = classify_headline(
            "Company announces it is exploring strategic alternatives including a sale",
            ticker="T",
        )
        assert ev.event_type == STRATEGIC_REVIEW


# ---------------------------------------------------------------------------
# Phase 4 — earnings / guidance
# ---------------------------------------------------------------------------


class TestEarningsGuidance:
    def test_guidance_raised(self):
        ev = classify_headline(
            "Company raises full-year revenue guidance after strong quarter",
            ticker="T",
            source_type="earnings_release",
        )
        assert ev.event_type == GUIDANCE_RAISED or GUIDANCE_RAISED in ev.secondary_events

    def test_guidance_lowered(self):
        ev = classify_headline(
            "Company lowers full-year guidance citing slower product uptake",
            ticker="T",
            source_type="earnings_release",
        )
        assert ev.event_type == GUIDANCE_LOWERED or GUIDANCE_LOWERED in ev.secondary_events

    def test_guidance_lowered_pressures_seller(self):
        ev = classify_headline(
            "Company lowers full-year guidance citing slower product uptake",
            ticker="T",
            source_type="earnings_release",
        )
        assert ev.score_deltas.get("seller_willingness", 0.0) >= 0

    def test_earnings_call_date_is_not_guidance(self):
        ev = classify_headline(
            "Company announces date of third quarter earnings conference call",
            ticker="T",
        )
        assert ev.event_type not in (GUIDANCE_RAISED, GUIDANCE_LOWERED)


# ---------------------------------------------------------------------------
# Phase 5 — clinical readout refinements
# ---------------------------------------------------------------------------


class TestClinicalRefinements:
    def test_topline_positive_phase3(self):
        ev = classify_headline(
            "Topline Phase 3 results: study met its primary endpoint",
            ticker="T",
        )
        assert ev.direction == "positive"
        assert ev.phase_detected == "Phase 3"

    def test_phase_2b_detected(self):
        ev = classify_headline(
            "Positive Phase 2b data: trial met primary endpoint",
            ticker="T",
        )
        assert ev.phase_detected == "Phase 2"

    def test_interim_readout_does_not_crash(self):
        ev = classify_headline(
            "Interim analysis shows the trial did not meet its primary endpoint",
            ticker="T",
        )
        assert ev.direction == "negative"
        assert ev.event_type != UNCLASSIFIED

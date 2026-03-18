"""
Schema validation tests for all 10 Phase 0 intelligence schemas.

Covers:
  - Valid construction with realistic data
  - Pydantic field validation (ge/le constraints, literals)
  - Computed fields (proposed_delta_pct, delta_rnpv_millions)
  - Model validator logic (bound enforcement on proposals)
  - Frozen model immutability
  - Round-trip serialization (model_dump → model_validate)
  - Cross-schema foreign key placeholder patterns
"""
from __future__ import annotations

import pytest
from datetime import date, datetime, timezone

from pydantic import ValidationError

from bve.entities.asset import TherapeuticArea, DevelopmentStage, Modality
from bve.entities.trial import TrialPhase

from bve.intelligence.taxonomy import EventType, ChangeMode
from bve.intelligence.schemas import (
    IntelligenceCompany,
    IntelligenceAsset,
    IntelligenceIndication,
    Event,
    StructuredSignal,
    AssumptionChangeProposal,
    ValuationRun,
    ReviewDecision,
    Thesis,
    KnowledgeArtifact,
)

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
_TODAY = date(2024, 6, 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def company() -> IntelligenceCompany:
    return IntelligenceCompany(
        id="company-regn-001",
        name="Regeneron Pharmaceuticals",
        ticker="REGN",
        engine_company_id="regn-2016",
        created_at=_NOW,
        updated_at=_NOW,
    )


@pytest.fixture
def asset(company) -> IntelligenceAsset:
    return IntelligenceAsset(
        id="asset-dupilumab-001",
        name="dupilumab (DUPIXENT)",
        engine_asset_id="dupilumab-ad",
        company_id=company.id,
        therapeutic_area=TherapeuticArea.IMMUNOLOGY,
        stage=DevelopmentStage.APPROVED,
        modality=Modality.BIOLOGIC,
        created_at=_NOW,
        updated_at=_NOW,
    )


@pytest.fixture
def indication(asset) -> IntelligenceIndication:
    return IntelligenceIndication(
        id="ind-ad-001",
        name="Moderate-to-Severe Atopic Dermatitis",
        engine_indication_id=None,
        asset_id=asset.id,
        icd10_codes=["L20.9"],
        approval_status="approved",
        created_at=_NOW,
        updated_at=_NOW,
    )


@pytest.fixture
def event(asset, company) -> Event:
    return Event(
        id="evt-001",
        event_type=EventType.TRIAL_READOUT,
        asset_id=asset.id,
        company_id=company.id,
        observed_at=datetime(2017, 3, 28, 14, 0, tzinfo=timezone.utc),
        ingested_at=_NOW,
        source_type="press_release",
        headline="FDA approves DUPIXENT for moderate-to-severe atopic dermatitis.",
        confidence=0.99,
    )


@pytest.fixture
def signal(event, asset, company) -> StructuredSignal:
    return StructuredSignal(
        id="sig-001",
        event_id=event.id,
        asset_id=asset.id,
        company_id=company.id,
        event_type=EventType.TRIAL_READOUT,
        signal_date=date(2017, 3, 28),
        trial_phase=TrialPhase.NDA_BLA,
        primary_endpoint_met=True,
        fda_action_type="approval",
        extraction_model="gpt-4o-2024-11-20",
        extraction_confidence=0.97,
        created_at=_NOW,
    )


@pytest.fixture
def proposal(signal, asset) -> AssumptionChangeProposal:
    return AssumptionChangeProposal(
        id="prop-001",
        signal_id=signal.id,
        asset_id=asset.id,
        engine_asset_id="dupilumab-ad",
        parameter_path="trials[*].success_probability",
        current_value=0.50,
        proposed_value=0.60,
        change_mode=ChangeMode.AUTO,
        bound_pct=20.0,
        event_type=EventType.TRIAL_READOUT,
        rationale="Positive Ph3 topline — met IGA 0/1 and EASI-75.",
        created_at=_NOW,
    )


# ---------------------------------------------------------------------------
# IntelligenceCompany
# ---------------------------------------------------------------------------

class TestIntelligenceCompany:
    def test_valid_construction(self, company):
        assert company.ticker == "REGN"
        assert company.engine_company_id == "regn-2016"

    def test_ticker_optional(self):
        c = IntelligenceCompany(
            id="c1", name="Private Bio", created_at=_NOW, updated_at=_NOW
        )
        assert c.ticker is None

    def test_monitoring_enabled_default_true(self):
        c = IntelligenceCompany(
            id="c1", name="X", created_at=_NOW, updated_at=_NOW
        )
        assert c.monitoring_enabled is True

    def test_data_sources_default_empty_list(self):
        c = IntelligenceCompany(
            id="c1", name="X", created_at=_NOW, updated_at=_NOW
        )
        assert c.data_sources == []

    def test_frozen(self, company):
        with pytest.raises((TypeError, ValidationError)):
            company.ticker = "XYZ"  # type: ignore[misc]

    def test_round_trip(self, company):
        d = company.model_dump()
        c2 = IntelligenceCompany.model_validate(d)
        assert c2 == company


# ---------------------------------------------------------------------------
# IntelligenceAsset
# ---------------------------------------------------------------------------

class TestIntelligenceAsset:
    def test_valid_construction(self, asset):
        assert asset.therapeutic_area == TherapeuticArea.IMMUNOLOGY
        assert asset.modality == Modality.BIOLOGIC

    def test_engine_asset_id_optional(self, company):
        a = IntelligenceAsset(
            id="a1", name="Drug X", company_id=company.id,
            therapeutic_area=TherapeuticArea.ONCOLOGY,
            stage=DevelopmentStage.PHASE_2,
            created_at=_NOW, updated_at=_NOW,
        )
        assert a.engine_asset_id is None

    def test_indication_ids_default_empty(self, company):
        a = IntelligenceAsset(
            id="a1", name="Drug X", company_id=company.id,
            therapeutic_area=TherapeuticArea.CNS,
            stage=DevelopmentStage.PHASE_1,
            created_at=_NOW, updated_at=_NOW,
        )
        assert a.indication_ids == []

    def test_engine_enums_accepted(self, company):
        """Frozen engine enums survive Pydantic v2 field validation."""
        for ta in TherapeuticArea:
            a = IntelligenceAsset(
                id="a", name="X", company_id="c",
                therapeutic_area=ta,
                stage=DevelopmentStage.PHASE_1,
                created_at=_NOW, updated_at=_NOW,
            )
            assert a.therapeutic_area is ta

    def test_frozen(self, asset):
        with pytest.raises((TypeError, ValidationError)):
            asset.stage = DevelopmentStage.PHASE_1  # type: ignore[misc]

    def test_round_trip(self, asset):
        d = asset.model_dump()
        a2 = IntelligenceAsset.model_validate(d)
        assert a2 == asset


# ---------------------------------------------------------------------------
# IntelligenceIndication
# ---------------------------------------------------------------------------

class TestIntelligenceIndication:
    def test_valid_construction(self, indication):
        assert indication.icd10_codes == ["L20.9"]
        assert indication.approval_status == "approved"

    def test_engine_indication_id_optional(self, indication):
        assert indication.engine_indication_id is None

    def test_icd10_default_empty(self, asset):
        ind = IntelligenceIndication(
            id="i1", name="Asthma", asset_id=asset.id,
            created_at=_NOW, updated_at=_NOW,
        )
        assert ind.icd10_codes == []

    def test_round_trip(self, indication):
        d = indication.model_dump()
        i2 = IntelligenceIndication.model_validate(d)
        assert i2 == indication


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------

class TestEvent:
    def test_valid_construction(self, event):
        assert event.event_type == EventType.TRIAL_READOUT
        assert event.confidence == 0.99

    def test_confidence_bounds(self, asset, company):
        with pytest.raises(ValidationError):
            Event(
                id="e", event_type=EventType.FINANCING,
                asset_id=asset.id, company_id=company.id,
                observed_at=_NOW, ingested_at=_NOW,
                source_type="manual", headline="X",
                confidence=1.5,  # > 1.0
            )
        with pytest.raises(ValidationError):
            Event(
                id="e", event_type=EventType.FINANCING,
                asset_id=asset.id, company_id=company.id,
                observed_at=_NOW, ingested_at=_NOW,
                source_type="manual", headline="X",
                confidence=-0.1,  # < 0.0
            )

    def test_source_type_literal_validation(self, asset, company):
        with pytest.raises(ValidationError):
            Event(
                id="e", event_type=EventType.FINANCING,
                asset_id=asset.id, company_id=company.id,
                observed_at=_NOW, ingested_at=_NOW,
                source_type="bloomberg_terminal",  # not in Literal
                headline="X",
            )

    def test_indication_id_optional(self, event):
        assert event.indication_id is None

    def test_tags_default_empty(self, event):
        assert event.tags == []

    def test_raw_text_optional(self, event):
        assert event.raw_text is None

    def test_round_trip(self, event):
        d = event.model_dump()
        e2 = Event.model_validate(d)
        assert e2 == event


# ---------------------------------------------------------------------------
# StructuredSignal
# ---------------------------------------------------------------------------

class TestStructuredSignal:
    def test_valid_construction(self, signal):
        assert signal.trial_phase == TrialPhase.NDA_BLA
        assert signal.primary_endpoint_met is True

    def test_hazard_ratio_must_be_positive(self, event, asset, company):
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-hr", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.TRIAL_READOUT,
                signal_date=_TODAY, hazard_ratio=-0.5,
                extraction_confidence=0.9, created_at=_NOW,
            )

    def test_p_value_bounds(self, event, asset, company):
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-pv1", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.TRIAL_READOUT,
                signal_date=_TODAY, p_value=1.5,
                extraction_confidence=0.9, created_at=_NOW,
            )
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-pv2", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.TRIAL_READOUT,
                signal_date=_TODAY, p_value=-0.01,
                extraction_confidence=0.9, created_at=_NOW,
            )

    def test_response_rate_bounds(self, event, asset, company):
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-rr", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.TRIAL_READOUT,
                signal_date=_TODAY, response_rate=1.1,
                extraction_confidence=0.9, created_at=_NOW,
            )

    def test_safety_grade_bounds(self, event, asset, company):
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-sg1", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.SAFETY_SIGNAL,
                signal_date=_TODAY, safety_grade=6,
                extraction_confidence=0.9, created_at=_NOW,
            )
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-sg2", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.SAFETY_SIGNAL,
                signal_date=_TODAY, safety_grade=0,
                extraction_confidence=0.9, created_at=_NOW,
            )

    def test_trial_phase_from_frozen_engine(self, signal):
        """TrialPhase enum imported from frozen engine works in intelligence schema."""
        assert signal.trial_phase is TrialPhase.NDA_BLA

    def test_fda_action_literal(self, event, asset, company):
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-fda", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.FDA_APPROVAL,
                signal_date=_TODAY, fda_action_type="tentative_approval",
                extraction_confidence=0.9, created_at=_NOW,
            )

    def test_designation_type_literal(self, event, asset, company):
        with pytest.raises(ValidationError):
            StructuredSignal(
                id="s-bad-des", event_id=event.id, asset_id=asset.id,
                company_id=company.id, event_type=EventType.FDA_DESIGNATION,
                signal_date=_TODAY, designation_type="SPA",
                extraction_confidence=0.9, created_at=_NOW,
            )

    def test_all_optional_fields_none(self, event, asset, company):
        s = StructuredSignal(
            id="s-min",
            event_id=event.id,
            asset_id=asset.id,
            company_id=company.id,
            event_type=EventType.SEC_FILING,
            signal_date=_TODAY,
            extraction_confidence=0.0,
            created_at=_NOW,
        )
        assert s.trial_phase is None
        assert s.primary_endpoint_met is None
        assert s.hazard_ratio is None

    def test_round_trip(self, signal):
        d = signal.model_dump()
        s2 = StructuredSignal.model_validate(d)
        assert s2 == signal


# ---------------------------------------------------------------------------
# AssumptionChangeProposal
# ---------------------------------------------------------------------------

class TestAssumptionChangeProposal:
    def test_proposed_delta_pct_computed(self, proposal):
        # (0.60 - 0.50) / 0.50 × 100 = 20.0
        assert abs(proposal.proposed_delta_pct - 20.0) < 1e-9

    def test_auto_within_bound_accepted(self, proposal):
        assert proposal.status == "pending"

    def test_auto_exceeds_bound_rejected(self, signal, asset):
        with pytest.raises(ValidationError):
            AssumptionChangeProposal(
                id="p2",
                signal_id=signal.id,
                asset_id=asset.id,
                engine_asset_id="dupilumab-ad",
                parameter_path="trials[*].success_probability",
                current_value=0.50,
                proposed_value=0.70,   # +40% — exceeds 20% bound
                change_mode=ChangeMode.AUTO,
                bound_pct=20.0,
                event_type=EventType.TRIAL_READOUT,
                rationale="Should fail.",
                created_at=_NOW,
            )

    def test_bounded_exceeds_bound_rejected(self, signal, asset):
        with pytest.raises(ValidationError):
            AssumptionChangeProposal(
                id="p3",
                signal_id=signal.id,
                asset_id=asset.id,
                engine_asset_id="dupilumab-ad",
                parameter_path="asset.discount_rate",
                current_value=0.10,
                proposed_value=0.14,   # +40% — exceeds 15% bound
                change_mode=ChangeMode.BOUNDED,
                bound_pct=15.0,
                event_type=EventType.SAFETY_SIGNAL,
                rationale="Should fail.",
                created_at=_NOW,
            )

    def test_manual_has_no_bound(self, signal, asset):
        """MANUAL proposals accept any delta and require bound_pct=None."""
        prop = AssumptionChangeProposal(
            id="p4",
            signal_id=signal.id,
            asset_id=asset.id,
            engine_asset_id="dupilumab-ad",
            parameter_path="market_model.competition_model",
            current_value=0.0,
            proposed_value=0.0,
            change_mode=ChangeMode.MANUAL,
            bound_pct=None,
            event_type=EventType.COMPETITOR_EVENT,
            rationale="Analyst to update CompetitionModel in YAML.",
            created_at=_NOW,
        )
        assert prop.change_mode == ChangeMode.MANUAL

    def test_manual_with_bound_pct_rejected(self, signal, asset):
        with pytest.raises(ValidationError):
            AssumptionChangeProposal(
                id="p5",
                signal_id=signal.id,
                asset_id=asset.id,
                engine_asset_id="dupilumab-ad",
                parameter_path="market_model.competition_model",
                current_value=0.0,
                proposed_value=0.0,
                change_mode=ChangeMode.MANUAL,
                bound_pct=20.0,   # MANUAL must not have bound_pct
                event_type=EventType.COMPETITOR_EVENT,
                rationale="Should fail.",
                created_at=_NOW,
            )

    def test_auto_without_bound_pct_rejected(self, signal, asset):
        with pytest.raises(ValidationError):
            AssumptionChangeProposal(
                id="p6",
                signal_id=signal.id,
                asset_id=asset.id,
                engine_asset_id="dupilumab-ad",
                parameter_path="trials[*].success_probability",
                current_value=0.50,
                proposed_value=0.55,
                change_mode=ChangeMode.AUTO,
                bound_pct=None,   # AUTO requires bound_pct
                event_type=EventType.TRIAL_READOUT,
                rationale="Should fail.",
                created_at=_NOW,
            )

    def test_decrease_delta_accepted_within_bound(self, signal, asset):
        """Negative deltas (step-down) should also be bounded."""
        prop = AssumptionChangeProposal(
            id="p7",
            signal_id=signal.id,
            asset_id=asset.id,
            engine_asset_id="dupilumab-ad",
            parameter_path="trials[*].success_probability",
            current_value=0.50,
            proposed_value=0.40,   # -20% — exactly at bound
            change_mode=ChangeMode.AUTO,
            bound_pct=20.0,
            event_type=EventType.SAFETY_SIGNAL,
            rationale="Safety signal — step-down POS.",
            created_at=_NOW,
        )
        assert abs(prop.proposed_delta_pct - (-20.0)) < 1e-9

    def test_status_default_pending(self, proposal):
        assert proposal.status == "pending"

    def test_supporting_signal_ids_default_empty(self, proposal):
        assert proposal.supporting_signal_ids == []

    def test_round_trip(self, proposal):
        d = proposal.model_dump()
        p2 = AssumptionChangeProposal.model_validate(d)
        assert abs(p2.proposed_delta_pct - proposal.proposed_delta_pct) < 1e-9


# ---------------------------------------------------------------------------
# ValuationRun
# ---------------------------------------------------------------------------

class TestValuationRun:
    def test_valid_construction(self):
        run = ValuationRun(
            id="run-001",
            engine_asset_id="dupilumab-ad",
            triggered_by_signal_id="sig-001",
            triggered_by_proposal_ids=["prop-001"],
            parameter_overrides={"trials[nda_bla].success_probability": 0.60},
            rnpv_millions_before=3200.0,
            rnpv_millions_after=3731.0,
            run_at=_NOW,
            status="completed",
        )
        assert run.delta_rnpv_millions == pytest.approx(531.0, abs=0.01)

    def test_delta_none_when_before_missing(self):
        run = ValuationRun(
            id="r2", engine_asset_id="x",
            rnpv_millions_after=1000.0,
            run_at=_NOW,
        )
        assert run.delta_rnpv_millions is None

    def test_delta_none_when_after_missing(self):
        run = ValuationRun(
            id="r3", engine_asset_id="x",
            rnpv_millions_before=500.0,
            run_at=_NOW,
        )
        assert run.delta_rnpv_millions is None

    def test_manual_trigger(self):
        """Manual run has no signal_id."""
        run = ValuationRun(
            id="r4", engine_asset_id="x",
            run_at=_NOW,
        )
        assert run.triggered_by_signal_id is None

    def test_status_default_pending(self):
        run = ValuationRun(id="r5", engine_asset_id="x", run_at=_NOW)
        assert run.status == "pending"

    def test_parameter_overrides_default_empty(self):
        run = ValuationRun(id="r6", engine_asset_id="x", run_at=_NOW)
        assert run.parameter_overrides == {}

    def test_round_trip(self):
        run = ValuationRun(
            id="r7", engine_asset_id="x",
            rnpv_millions_before=100.0, rnpv_millions_after=150.0,
            run_at=_NOW, status="completed",
        )
        d = run.model_dump()
        r2 = ValuationRun.model_validate(d)
        assert r2.delta_rnpv_millions == run.delta_rnpv_millions


# ---------------------------------------------------------------------------
# ReviewDecision
# ---------------------------------------------------------------------------

class TestReviewDecision:
    def test_accepted_decision(self):
        dec = ReviewDecision(
            id="dec-001",
            proposal_id="prop-001",
            decision="accepted",
            reviewer_id="analyst-dj",
            reviewed_at=_NOW,
            rationale="Clear Ph3 readout. POS step-up justified.",
        )
        assert dec.decision == "accepted"
        assert dec.run_id is None   # set later when run is created

    def test_rejected_decision_no_run(self):
        dec = ReviewDecision(
            id="dec-002",
            proposal_id="prop-002",
            decision="rejected",
            reviewer_id="analyst-dj",
            reviewed_at=_NOW,
            rationale="Conference abstract — insufficient to update POS.",
        )
        assert dec.run_id is None
        assert dec.override_value is None

    def test_deferred_decision(self):
        dec = ReviewDecision(
            id="dec-003",
            proposal_id="prop-003",
            decision="deferred",
            reviewer_id="analyst-dj",
            reviewed_at=_NOW,
            rationale="Awaiting full trial data before updating model.",
        )
        assert dec.decision == "deferred"

    def test_override_value_accepted(self):
        dec = ReviewDecision(
            id="dec-004",
            proposal_id="prop-004",
            decision="accepted",
            reviewer_id="analyst-dj",
            reviewed_at=_NOW,
            override_value=0.58,   # reviewer adjusts from proposed 0.60
            rationale="Stronger than proposed but tempered by ARIA signal.",
        )
        assert dec.override_value == pytest.approx(0.58)

    def test_invalid_decision_literal(self):
        with pytest.raises(ValidationError):
            ReviewDecision(
                id="d", proposal_id="p",
                decision="approved",   # not in Literal
                reviewer_id="a",
                reviewed_at=_NOW,
                rationale="x",
            )

    def test_round_trip(self):
        dec = ReviewDecision(
            id="dec-rt", proposal_id="p",
            decision="accepted", reviewer_id="a",
            reviewed_at=_NOW, rationale="ok",
        )
        d = dec.model_dump()
        d2 = ReviewDecision.model_validate(d)
        assert d2 == dec


# ---------------------------------------------------------------------------
# Thesis
# ---------------------------------------------------------------------------

class TestThesis:
    def test_valid_construction(self, asset, company):
        thesis = Thesis(
            id="th-001",
            asset_id=asset.id,
            company_id=company.id,
            variant_perception="Market prices AD only; we model atopic march expansion.",
            our_pos_estimate=0.82,
            consensus_pos_estimate=0.70,
            peak_sales_estimate_millions=4500.0,
            kill_criteria=["IGA 0/1 < 25%", "FDA clinical hold"],
            created_at=_NOW,
            updated_at=_NOW,
            status="active",
        )
        assert thesis.version == 1
        assert thesis.superseded_by_id is None

    def test_pos_estimate_bounds(self, asset, company):
        with pytest.raises(ValidationError):
            Thesis(
                id="th", asset_id=asset.id, company_id=company.id,
                our_pos_estimate=1.5,   # > 1.0
                created_at=_NOW, updated_at=_NOW,
            )

    def test_optional_fields_default_none(self, asset, company):
        thesis = Thesis(
            id="th-min", asset_id=asset.id, company_id=company.id,
            created_at=_NOW, updated_at=_NOW,
        )
        assert thesis.variant_perception is None
        assert thesis.our_pos_estimate is None
        assert thesis.kill_criteria == []

    def test_version_chain(self, asset, company):
        v1 = Thesis(
            id="th-v1", asset_id=asset.id, company_id=company.id,
            version=1, status="archived",
            superseded_by_id="th-v2",
            created_at=_NOW, updated_at=_NOW,
        )
        v2 = Thesis(
            id="th-v2", asset_id=asset.id, company_id=company.id,
            version=2, status="active",
            created_at=_NOW, updated_at=_NOW,
        )
        assert v1.superseded_by_id == v2.id
        assert v2.superseded_by_id is None

    def test_status_literal(self, asset, company):
        with pytest.raises(ValidationError):
            Thesis(
                id="th", asset_id=asset.id, company_id=company.id,
                status="published",   # not in Literal
                created_at=_NOW, updated_at=_NOW,
            )

    def test_round_trip(self, asset, company):
        t = Thesis(
            id="th-rt", asset_id=asset.id, company_id=company.id,
            status="active", created_at=_NOW, updated_at=_NOW,
        )
        d = t.model_dump()
        t2 = Thesis.model_validate(d)
        assert t2 == t


# ---------------------------------------------------------------------------
# KnowledgeArtifact
# ---------------------------------------------------------------------------

class TestKnowledgeArtifact:
    def test_valid_construction(self, asset, company):
        art = KnowledgeArtifact(
            id="art-001",
            artifact_type="competitor_landscape",
            asset_id=asset.id,
            company_id=company.id,
            title="IL-4/IL-13 Competitor Landscape 2016",
            content_markdown="## Landscape\nNo approved biologics at filing.",
            created_at=_NOW,
            updated_at=_NOW,
            created_by="analyst-dj",
            confidence=0.85,
        )
        assert art.artifact_type == "competitor_landscape"

    def test_company_level_artifact_no_asset_id(self, company):
        art = KnowledgeArtifact(
            id="art-002",
            artifact_type="payer_intelligence",
            company_id=company.id,
            title="REGN Payer Strategy Summary",
            content_markdown="## Payer Intelligence\n...",
            created_at=_NOW,
            updated_at=_NOW,
        )
        assert art.asset_id is None

    def test_artifact_type_literal_validation(self):
        with pytest.raises(ValidationError):
            KnowledgeArtifact(
                id="art",
                artifact_type="press_release",   # not in ArtifactType
                title="X",
                content_markdown="Y",
                created_at=_NOW, updated_at=_NOW,
            )

    def test_confidence_bounds(self, asset, company):
        with pytest.raises(ValidationError):
            KnowledgeArtifact(
                id="art",
                artifact_type="thesis",
                title="X", content_markdown="Y",
                created_at=_NOW, updated_at=_NOW,
                confidence=1.5,
            )

    def test_llm_created_by_pattern(self, asset, company):
        art = KnowledgeArtifact(
            id="art-003",
            artifact_type="signal_summary",
            asset_id=asset.id,
            company_id=company.id,
            title="Signal summary for TRIAL_READOUT evt-001",
            content_markdown="Dupilumab Phase 3 met all primary endpoints.",
            created_at=_NOW,
            updated_at=_NOW,
            created_by="llm:gpt-4o-2024-11-20",
        )
        assert art.created_by.startswith("llm:")

    def test_source_ids_default_empty(self, asset, company):
        art = KnowledgeArtifact(
            id="art-004",
            artifact_type="regulatory_precedent",
            title="X", content_markdown="Y",
            created_at=_NOW, updated_at=_NOW,
        )
        assert art.source_signal_ids == []
        assert art.source_run_ids == []

    def test_round_trip(self, asset, company):
        art = KnowledgeArtifact(
            id="art-rt",
            artifact_type="trial_design_critique",
            asset_id=asset.id,
            title="Trial Design Critique — SOLO-1",
            content_markdown="## Design\n...",
            created_at=_NOW, updated_at=_NOW,
        )
        d = art.model_dump()
        a2 = KnowledgeArtifact.model_validate(d)
        assert a2 == art

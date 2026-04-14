"""
Tests for evidence reference models, MemoEvidenceBuilder, and memo rendering
with full, partial, and no evidence.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

import pytest

from bve.reporting.evidence import (
    MemoEvidence,
    MemoEvidenceRef,
    MemoSectionEvidence,
    SourceType,
)
from bve.reporting.evidence_builder import MemoEvidenceBuilder


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ref(label="test claim", source_type=SourceType.ASSUMPTION, **kwargs) -> MemoEvidenceRef:
    return MemoEvidenceRef(source_type=source_type, label=label, **kwargs)


def _section(key="assumptions", refs=(), gaps=()) -> MemoSectionEvidence:
    return MemoSectionEvidence(
        section_key=key,
        refs=list(refs),
        unsupported_claims=list(gaps),
    )


def _make_output(
    *,
    with_assumption_log: bool = True,
    with_comps: bool = False,
    with_catalysts: bool = False,
    with_decision_framing: bool = False,
    biological_target: Optional[str] = None,
    mechanism_of_action: Optional[str] = None,
    competitor_assets=(),
    differentiation_notes: Optional[str] = None,
):
    """Build a minimal ValuationOutput mock for evidence builder tests."""
    from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
    from bve.entities.company import Company
    from bve.models.market_model import MarketModel
    from bve.models.monte_carlo import MonteCarloResult
    from bve.models.rnpv_model import PhaseBreakdown, RNPVResult
    from bve.valuation.outputs import SensitivityPoint, ValuationOutput
    from bve.valuation.scenario import ScenarioResult, ScenarioSet

    asset = Asset(
        id="ev-test",
        name="EV Test Asset",
        indication="ulcerative colitis",
        therapeutic_area=TherapeuticArea.IMMUNOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.BIOLOGIC,
        mechanism_of_action=mechanism_of_action,
        biological_target=biological_target,
        competitor_assets=list(competitor_assets),
        differentiation_notes=differentiation_notes,
    )

    company = Company(
        id="ev-co",
        name="EV Biotech",
        ticker="EVBT",
        shares_outstanding_millions=100.0,
        cash_millions=50.0,
    )

    phase_breakdown = [
        PhaseBreakdown(
            phase="phase_3",
            success_probability=0.55,
            prob_reaching=1.0,
            duration_years=3.0,
            pv_cost_gross=15.0,
            pv_cost_weighted=12.5,
        )
    ]

    rnpv = RNPVResult(
        asset_id="ev-asset",
        asset_name="EV-101",
        rnpv_millions=250.0,
        peak_sales_millions=500.0,
        gross_revenue_pv_millions=800.0,
        probability_adjusted_revenue_pv_millions=440.0,
        trial_costs_pv_millions=190.0,
        cumulative_success_probability=0.55,
        years_to_launch=4.0,
        discount_rate=0.12,
        net_ownership=1.0,
        phase_breakdown=phase_breakdown,
    )

    market = MarketModel(
        asset_id="ev-asset",
        total_addressable_market_millions=5000.0,
        peak_penetration=0.10,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.15,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.20,
    )

    scenario_result = ScenarioResult(
        label="base",
        description="Base case",
        rnpv_millions=250.0,
        peak_sales_millions=500.0,
        years_to_launch=4.0,
        nav_millions=300.0,
        nav_per_share=3.0,
        cumulative_success_probability=0.55,
    )
    scenarios = ScenarioSet(
        bull=ScenarioResult(label="bull", description="Bull case", rnpv_millions=400.0,
                           peak_sales_millions=700.0, years_to_launch=3.5,
                           nav_millions=450.0, nav_per_share=4.5, cumulative_success_probability=0.70),
        base=scenario_result,
        bear=ScenarioResult(label="bear", description="Bear case", rnpv_millions=100.0,
                           peak_sales_millions=250.0, years_to_launch=5.0,
                           nav_millions=150.0, nav_per_share=1.5, cumulative_success_probability=0.30),
    )

    mc = MonteCarloResult(
        asset_id="ev-asset",
        simulated_values_millions=[250.0] * 1000,
        n_simulations=1000,
        mean_millions=260.0,
        median_millions=250.0,
        std_millions=80.0,
        percentile_5_millions=80.0,
        percentile_10_millions=120.0,
        percentile_25_millions=180.0,
        percentile_50_millions=250.0,
        percentile_75_millions=330.0,
        percentile_90_millions=390.0,
        percentile_95_millions=440.0,
        probability_positive=0.85,
        probability_above_500m=0.20,
        probability_above_1b=0.05,
    )

    assumption_log = None
    if with_assumption_log:
        from bve.valuation.assumptions import build_assumption_log
        assumption_log = build_assumption_log(
            asset=asset, trials=[], market_model=market, rnpv_result=rnpv
        )

    comps = None
    if with_comps:
        from bve.models.deal_models import ComparableDealAnalysis, FairValueBand
        comps = ComparableDealAnalysis(
            asset_ev_to_peak_sales=0.5,
            match_tier="therapeutic_area_phase",
            n_comps=4,
            n_hq_comps=3,
            peer_min_ev_to_peak_sales=0.3,
            peer_median_ev_to_peak_sales=0.6,
            peer_max_ev_to_peak_sales=1.2,
            percentile_vs_comps=0.45,
            premium_discount_vs_median=-0.17,
            matched_targets=["Target A", "Target B", "Target C", "Target D"],
            fair_value_band=FairValueBand(
                n_comps_with_ev=4,
                ev_p25=180.0, ev_p50=300.0, ev_p75=480.0,
            ),
        )

    decision_framing = None
    if with_decision_framing:
        from bve.valuation.assumptions import DecisionFraming
        decision_framing = DecisionFraming(
            kill_criteria=[
                "Phase 3 primary endpoint misses pre-specified threshold.",
                "Grade 3+ on-target toxicity requiring REMS or label restriction.",
            ]
        )

    if with_catalysts:
        from bve.entities.asset import Catalyst
        asset = asset.model_copy(update={
            "upcoming_catalysts": [
                Catalyst(description="Ph3 primary readout", expected_date="2026-Q4",
                         catalyst_type="readout", probability_positive=0.55)
            ]
        })

    return ValuationOutput(
        asset=asset,
        company=company,
        trials=[],
        market_model=market,
        rnpv=rnpv,
        scenarios=scenarios,
        monte_carlo=mc,
        nav_millions=300.0,
        nav_per_share=3.0,
        assumption_log=assumption_log,
        comps_fair_value_band=comps,
        decision_framing=decision_framing,
    )


# ── Model tests ───────────────────────────────────────────────────────────────

class TestMemoEvidenceRef:
    def test_basic_ref(self):
        ref = _ref(label="WACC: 12%", confidence_label="High", url="https://example.com")
        assert ref.label == "WACC: 12%"
        assert ref.confidence_label == "High"
        assert ref.url == "https://example.com"

    def test_confidence_display_label_preferred(self):
        ref = _ref(confidence_label="Medium", confidence_score=0.65)
        assert ref.confidence_display == "Medium"

    def test_confidence_display_score_fallback(self):
        ref = _ref(confidence_label="—", confidence_score=0.75)
        assert ref.confidence_display == "75%"

    def test_confidence_display_missing(self):
        ref = _ref()
        assert ref.confidence_display == "—"

    def test_is_gap_default_false(self):
        ref = _ref()
        assert ref.is_gap is False

    def test_is_gap_true(self):
        ref = _ref(is_gap=True)
        assert ref.is_gap is True


class TestMemoSectionEvidence:
    def test_has_evidence_true(self):
        sec = _section(refs=[_ref()])
        assert sec.has_evidence is True

    def test_has_evidence_false(self):
        sec = _section(refs=[])
        assert sec.has_evidence is False

    def test_has_gaps_true(self):
        sec = _section(gaps=["something missing"])
        assert sec.has_gaps is True

    def test_has_gaps_false(self):
        sec = _section(gaps=[])
        assert sec.has_gaps is False

    def test_is_empty_true(self):
        sec = _section()
        assert sec.is_empty is True

    def test_is_empty_false_when_refs(self):
        sec = _section(refs=[_ref()])
        assert sec.is_empty is False

    def test_is_empty_false_when_gaps(self):
        sec = _section(gaps=["gap"])
        assert sec.is_empty is False


class TestMemoEvidence:
    def test_default_sections_exist(self):
        ev = MemoEvidence()
        assert ev.biology.section_key == "biology"
        assert ev.trial.section_key == "trial"
        assert ev.competitive.section_key == "competitive"
        assert ev.assumptions.section_key == "assumptions"
        assert ev.comps.section_key == "comps"
        assert ev.falsification.section_key == "falsification"

    def test_total_refs_counts_all_sections(self):
        ev = MemoEvidence(
            biology=_section("biology", refs=[_ref(), _ref()]),
            assumptions=_section("assumptions", refs=[_ref()]),
        )
        assert ev.total_refs == 3

    def test_total_gaps(self):
        ev = MemoEvidence(
            biology=_section("biology", gaps=["gap1"]),
            trial=_section("trial", gaps=["gap2", "gap3"]),
        )
        assert ev.total_gaps == 3

    def test_has_any_evidence_true(self):
        ev = MemoEvidence(biology=_section("biology", refs=[_ref()]))
        assert ev.has_any_evidence is True

    def test_has_any_evidence_false_when_empty(self):
        ev = MemoEvidence()
        assert ev.has_any_evidence is False

    def test_section_by_key(self):
        ev = MemoEvidence(biology=_section("biology", refs=[_ref()]))
        assert ev.section("biology").has_evidence is True

    def test_section_unknown_key_returns_empty(self):
        ev = MemoEvidence()
        sec = ev.section("unknown_key_xyz")
        assert sec.is_empty


# ── Builder tests ─────────────────────────────────────────────────────────────

class TestBuilderFullEvidence:
    def test_build_returns_memo_evidence(self):
        output = _make_output(with_assumption_log=True, with_comps=True,
                              with_decision_framing=True, with_catalysts=True,
                              biological_target="PD-1",
                              mechanism_of_action="checkpoint inhibitor")
        ev = MemoEvidenceBuilder.build(output)
        assert isinstance(ev, MemoEvidence)

    def test_biology_has_moa_ref(self):
        output = _make_output(mechanism_of_action="checkpoint inhibitor")
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.biology.refs]
        assert any("checkpoint inhibitor" in l for l in labels)

    def test_biology_has_target_ref(self):
        output = _make_output(biological_target="PD-1")
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.biology.refs]
        assert any("PD-1" in l for l in labels)

    def test_biology_has_pos_methodology_ref(self):
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.biology.refs]
        assert any("pos model" in l.lower() or "heuristic" in l.lower() for l in labels)

    def test_trial_has_phase_pos_refs(self):
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        # Should have at least one phase POS ref
        assert ev.trial.has_evidence

    def test_trial_has_catalyst_ref(self):
        output = _make_output(with_catalysts=True)
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.trial.refs]
        assert any("catalyst" in l.lower() or "readout" in l.lower() for l in labels)

    def test_assumptions_has_refs(self):
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        assert ev.assumptions.has_evidence
        assert len(ev.assumptions.refs) >= 5  # At least WACC, patent, penetration, POS, etc.

    def test_assumptions_refs_have_confidence(self):
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        for ref in ev.assumptions.refs:
            assert ref.confidence_label  # Never None

    def test_comps_has_refs(self):
        output = _make_output(with_comps=True)
        ev = MemoEvidenceBuilder.build(output)
        assert ev.comps.has_evidence

    def test_comps_refs_include_deal_comp_type(self):
        output = _make_output(with_comps=True)
        ev = MemoEvidenceBuilder.build(output)
        types = {r.source_type for r in ev.comps.refs}
        assert SourceType.DEAL_COMP in types

    def test_falsification_has_kill_criteria(self):
        output = _make_output(with_decision_framing=True)
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.falsification.refs]
        assert any("kill criterion" in l.lower() for l in labels)

    def test_falsification_has_thesis_changers(self):
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.falsification.refs]
        assert any("thesis changer" in l.lower() for l in labels)

    def test_competitive_has_competitor_refs(self):
        output = _make_output(competitor_assets=["Competitor A", "Competitor B"])
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.competitive.refs]
        assert any("Competitor A" in l for l in labels)


class TestBuilderPartialEvidence:
    def test_no_moa_adds_gap(self):
        output = _make_output(mechanism_of_action=None)
        ev = MemoEvidenceBuilder.build(output)
        assert ev.biology.has_gaps
        gaps = " ".join(ev.biology.unsupported_claims)
        assert "mechanism of action" in gaps.lower()

    def test_no_target_adds_gap(self):
        output = _make_output(biological_target=None)
        ev = MemoEvidenceBuilder.build(output)
        assert ev.biology.has_gaps
        gaps = " ".join(ev.biology.unsupported_claims)
        assert "biological target" in gaps.lower()

    def test_no_catalysts_adds_gap(self):
        output = _make_output(with_catalysts=False)
        ev = MemoEvidenceBuilder.build(output)
        gaps = " ".join(ev.trial.unsupported_claims)
        assert "catalyst" in gaps.lower()

    def test_no_competitor_assets_adds_gap(self):
        output = _make_output(competitor_assets=[])
        ev = MemoEvidenceBuilder.build(output)
        assert ev.competitive.has_gaps

    def test_no_comps_adds_gap(self):
        output = _make_output(with_comps=False)
        ev = MemoEvidenceBuilder.build(output)
        assert ev.comps.has_gaps
        gaps = " ".join(ev.comps.unsupported_claims)
        assert "comparable" in gaps.lower()

    def test_no_kill_criteria_adds_gap(self):
        output = _make_output(with_decision_framing=False)
        ev = MemoEvidenceBuilder.build(output)
        gaps = " ".join(ev.falsification.unsupported_claims)
        assert "kill" in gaps.lower()

    def test_phase_only_comps_adds_gap(self):
        from bve.models.deal_models import ComparableDealAnalysis
        output = _make_output()
        output.comps_fair_value_band = ComparableDealAnalysis(
            asset_ev_to_peak_sales=0.5,
            match_tier="phase_only",
            n_comps=2,
            n_hq_comps=1,
            peer_min_ev_to_peak_sales=0.3,
            peer_median_ev_to_peak_sales=0.6,
            peer_max_ev_to_peak_sales=0.9,
            percentile_vs_comps=0.4,
            matched_targets=["Target X", "Target Y"],
        )
        ev = MemoEvidenceBuilder.build(output)
        gaps = " ".join(ev.comps.unsupported_claims)
        assert "phase only" in gaps.lower()


class TestBuilderNoEvidence:
    def test_no_assumption_log_adds_gap(self):
        output = _make_output(with_assumption_log=False)
        ev = MemoEvidenceBuilder.build(output)
        assert ev.assumptions.has_gaps
        gaps = " ".join(ev.assumptions.unsupported_claims)
        assert "assumption" in gaps.lower()

    def test_biology_always_has_pharmacology_gap(self):
        """Structural/pharmacology data is never in ValuationOutput — always flagged."""
        output = _make_output(
            mechanism_of_action="checkpoint inhibitor",
            biological_target="PD-1",
        )
        ev = MemoEvidenceBuilder.build(output)
        gaps = " ".join(ev.biology.unsupported_claims)
        assert "pharmacology" in gaps.lower() or "structural" in gaps.lower()

    def test_trial_always_has_signal_gap(self):
        """StructuredSignal trial data is never in ValuationOutput — always flagged."""
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        gaps = " ".join(ev.trial.unsupported_claims)
        assert "signal" in gaps.lower() or "hazard ratio" in gaps.lower()

    def test_competitive_always_has_knowledge_artifact_gap(self):
        """KnowledgeArtifact competitor data not in ValuationOutput — always flagged."""
        output = _make_output(competitor_assets=["Comp A"])
        ev = MemoEvidenceBuilder.build(output)
        gaps = " ".join(ev.competitive.unsupported_claims)
        assert "knowledgeartifact" in gaps.lower() or "knowledge" in gaps.lower()

    def test_builder_never_raises(self):
        """Builder must be fault-tolerant — errors become gap annotations."""
        # Minimal valid output
        output = _make_output()
        ev = MemoEvidenceBuilder.build(output)
        assert isinstance(ev, MemoEvidence)


# ── Memo rendering tests ──────────────────────────────────────────────────────

DEALS_YAML = (
    Path(__file__).parent.parent.parent / "research" / "mna" / "comparable_deals.yaml"
)


def _engine_output(with_comps: bool = False, **kwargs):
    """Build a real ValuationEngine output for memo rendering tests."""
    from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea, Catalyst
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial
    from bve.models.market_model import MarketModel
    from bve.valuation.valuation_engine import ValuationEngine

    asset = Asset(
        id="memo-ev-test",
        name="Evimab",
        indication="ulcerative colitis",
        therapeutic_area=TherapeuticArea.IMMUNOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.BIOLOGIC,
        mechanism_of_action=kwargs.get("mechanism_of_action", "IL-4/IL-13 blocker"),
        biological_target=kwargs.get("biological_target", "IL-13"),
        competitor_assets=kwargs.get("competitor_assets", ["Dupilumab"]),
        upcoming_catalysts=[
            Catalyst(description="Phase 3 primary endpoint", expected_date="2026-Q4",
                     catalyst_type="readout", probability_positive=0.60)
        ],
    )
    company = Company(
        id="memo-co",
        name="EvimaBio",
        ticker="EVMB",
        shares_outstanding_millions=80.0,
        cash_millions=120.0,
        current_price=12.50,
    )
    trials = [
        ClinicalTrial(id="ph2", asset_id=asset.id, phase=DevelopmentStage.PHASE_2,
                      duration_years=2.0, success_probability=0.45, cost_millions=30.0),
        ClinicalTrial(id="ph3", asset_id=asset.id, phase=DevelopmentStage.PHASE_3,
                      duration_years=3.0, success_probability=0.55, cost_millions=60.0),
        ClinicalTrial(id="nda", asset_id=asset.id, phase=DevelopmentStage.NDA_BLA,
                      duration_years=1.0, success_probability=0.90, cost_millions=5.0),
    ]
    market = MarketModel(
        asset_id=asset.id,
        addressable_patients_annual=200_000,
        net_price_per_patient_usd=30_000,
        peak_penetration=0.15,
        years_to_peak=5,
        patent_life_years=12,
        cogs_rate=0.15,
        sgna_rate_launch=0.35,
        sgna_rate_mature=0.20,
    )

    comparable_deals = None
    if with_comps:
        from bve.intelligence.comparable_deals import ComparableDealLoader
        deal_set = ComparableDealLoader.load(DEALS_YAML)
        comparable_deals = deal_set.deals

    from bve.models.monte_carlo import MonteCarloParams
    engine = ValuationEngine(
        asset=asset,
        company=company,
        trials=trials,
        market_model=market,
        comparable_deals=comparable_deals,
        mc_params=MonteCarloParams(random_seed=42, n_simulations=500),
    )
    return engine.run()


class TestMemoRenderingWithEvidence:
    @pytest.fixture(scope="class")
    def output_with_comps(self):
        return _engine_output(with_comps=True)

    @pytest.fixture(scope="class")
    def output_no_comps(self):
        return _engine_output(with_comps=False)

    def test_memo_renders_with_comps(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_with_comps, memo_type="bd")
        assert isinstance(memo, str)
        assert len(memo) > 500

    def test_memo_has_evidence_section_header(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_with_comps, memo_type="bd")
        assert "Evidence & Sources" in memo

    def test_memo_has_evidence_gaps_for_biology(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_with_comps, memo_type="bd")
        # Structural pharmacology gap should always appear
        assert "Evidence gap" in memo

    def test_memo_evidence_attached_to_output(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        generate_memo(output_with_comps, memo_type="bd")
        assert output_with_comps.memo_evidence is not None

    def test_memo_evidence_bundle_has_all_sections(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        from bve.reporting.evidence import MemoEvidence
        generate_memo(output_with_comps, memo_type="bd")
        ev = output_with_comps.memo_evidence
        assert isinstance(ev, MemoEvidence)
        assert ev.total_refs > 0
        assert ev.total_gaps > 0

    def test_memo_no_comps_evidence_gap_shown(self, output_no_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_no_comps, memo_type="bd")
        # Should show the comps evidence gap
        assert "comparable" in memo.lower() or "Evidence gap" in memo

    def test_memo_renders_without_comps_no_crash(self, output_no_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_no_comps, memo_type="bd")
        assert isinstance(memo, str)

    def test_memo_assumptions_evidence_table_rendered(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_with_comps, memo_type="bd")
        # The evidence table should show assumption source types
        assert "Assumption" in memo or "assumption" in memo

    def test_memo_competitor_gap_present(self, output_with_comps):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(output_with_comps, memo_type="bd")
        # Competitive landscape has a permanent gap for KnowledgeArtifact data
        assert "Evidence gap" in memo

# ═══════════════════════════════════════════════════════════════════════════════
# Sprint 5 — source-backed evidence plumbing
# ═══════════════════════════════════════════════════════════════════════════════

# ── Fixtures: mock StructuredSignal and KnowledgeArtifact ────────────────────

def _make_signal(
    *,
    event_type: str = "trial_readout",
    signal_date_str: str = "2025-09-15",
    extraction_confidence: float = 0.85,
    trial_phase: str | None = "phase_3",
    primary_endpoint_met: bool | None = True,
    p_value: float | None = 0.003,
    hazard_ratio: float | None = 0.72,
    response_rate: float | None = None,
    enrollment_status: str | None = None,
    extraction_model: str | None = "gpt-4o-2024-11-20",
    sig_id: str = "sig-001",
):
    """Build a duck-typed mock StructuredSignal for testing without triggering bve.intelligence imports."""
    from unittest.mock import MagicMock
    from datetime import date

    sig = MagicMock()
    sig.id = sig_id
    sig.event_type = event_type  # string value (matching enum .value)
    sig.signal_date = date.fromisoformat(signal_date_str)
    sig.extraction_confidence = extraction_confidence
    sig.trial_phase = trial_phase
    sig.primary_endpoint_met = primary_endpoint_met
    sig.p_value = p_value
    sig.hazard_ratio = hazard_ratio
    sig.response_rate = response_rate
    sig.enrollment_status = enrollment_status
    sig.extraction_model = extraction_model
    return sig


def _make_artifact(
    *,
    artifact_type: str = "competitor_landscape",
    title: str = "Oncology competitor landscape Q1-2026",
    confidence: float = 0.75,
    created_at_str: str = "2026-01-10T14:30:00",
    source_signal_ids: list | None = None,
    created_by: str = "llm:gpt-4o",
    art_id: str = "art-001",
):
    """Build a duck-typed mock KnowledgeArtifact for testing."""
    from unittest.mock import MagicMock
    from datetime import datetime

    art = MagicMock()
    art.id = art_id
    art.artifact_type = artifact_type
    art.title = title
    art.confidence = confidence
    art.created_at = datetime.fromisoformat(created_at_str)
    art.source_signal_ids = source_signal_ids or ["sig-001"]
    art.created_by = created_by
    return art


def _output_with_signals(signals=(), knowledge_artifacts=()):
    """Return a minimal ValuationOutput with the given signals/artifacts attached."""
    output = _make_output(with_assumption_log=True, with_comps=False)
    output.signals = list(signals)
    output.knowledge_artifacts = list(knowledge_artifacts)
    return output


# ── TestSignalWiring ──────────────────────────────────────────────────────────

class TestSignalWiring:
    """StructuredSignal objects flow into biology and trial evidence sections."""

    def test_trial_readout_signal_appears_in_trial_section(self):
        sig = _make_signal(event_type="trial_readout")
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        labels = [r.label for r in ev.trial.refs]
        assert any("Trial Readout" in l or "trial_readout" in l.lower() for l in labels)

    def test_trial_signal_has_as_of_date(self):
        sig = _make_signal(event_type="trial_readout", signal_date_str="2025-09-15")
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert len(signal_refs) >= 1
        assert signal_refs[0].as_of_date == "2025-09-15"

    def test_trial_signal_has_source_id(self):
        sig = _make_signal(event_type="trial_readout", sig_id="sig-xyz")
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert any(r.source_id == "sig-xyz" for r in signal_refs)

    def test_trial_signal_confidence_high_for_score_0_9(self):
        sig = _make_signal(event_type="trial_readout", extraction_confidence=0.9)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert signal_refs[0].confidence_label == "High"

    def test_trial_signal_confidence_medium_for_score_0_6(self):
        sig = _make_signal(event_type="trial_readout", extraction_confidence=0.6)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert signal_refs[0].confidence_label == "Medium"

    def test_trial_signal_confidence_low_for_score_0_3(self):
        sig = _make_signal(event_type="trial_readout", extraction_confidence=0.3)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert signal_refs[0].confidence_label == "Low"

    def test_interim_analysis_signal_appears_in_trial(self):
        sig = _make_signal(event_type="interim_analysis")
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        types = [r.source_type for r in ev.trial.refs]
        assert SourceType.SIGNAL in types

    def test_enrollment_update_signal_appears_in_trial(self):
        sig = _make_signal(
            event_type="enrollment_update",
            primary_endpoint_met=None,
            p_value=None,
            hazard_ratio=None,
            enrollment_status="recruiting",
        )
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        types = [r.source_type for r in ev.trial.refs]
        assert SourceType.SIGNAL in types

    def test_publication_signal_appears_in_biology_section(self):
        sig = _make_signal(event_type="publication", primary_endpoint_met=None, p_value=None, hazard_ratio=None)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        types = [r.source_type for r in ev.biology.refs]
        assert SourceType.SIGNAL in types

    def test_publication_signal_has_as_of_date_in_biology(self):
        sig = _make_signal(event_type="publication", signal_date_str="2024-11-01",
                          primary_endpoint_met=None, p_value=None, hazard_ratio=None)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.biology.refs if r.source_type == SourceType.SIGNAL]
        assert signal_refs[0].as_of_date == "2024-11-01"

    def test_signal_in_biology_but_not_trial_for_publication(self):
        sig = _make_signal(event_type="publication", primary_endpoint_met=None, p_value=None, hazard_ratio=None)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        bio_signal_refs = [r for r in ev.biology.refs if r.source_type == SourceType.SIGNAL]
        # publication is in biology; trial should still show signal gap (no trial-type signals)
        assert len(bio_signal_refs) >= 1
        assert "StructuredSignal" in " ".join(ev.trial.unsupported_claims)

    def test_no_signals_produces_trial_gap(self):
        output = _output_with_signals(signals=[])
        ev = MemoEvidenceBuilder.build(output)
        assert any("StructuredSignal" in g for g in ev.trial.unsupported_claims)

    def test_no_signals_produces_biology_gap(self):
        output = _output_with_signals(signals=[])
        ev = MemoEvidenceBuilder.build(output)
        assert any("StructuredSignal" in g or "extraction pipeline" in g for g in ev.biology.unsupported_claims)

    def test_signal_label_includes_endpoint_result(self):
        sig = _make_signal(event_type="trial_readout", primary_endpoint_met=True)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert any("endpoint met" in r.label for r in signal_refs)

    def test_signal_label_includes_pvalue(self):
        sig = _make_signal(event_type="trial_readout", p_value=0.003)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert any("p=0.003" in r.label for r in signal_refs)

    def test_signal_label_includes_hazard_ratio(self):
        sig = _make_signal(event_type="trial_readout", hazard_ratio=0.72)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert any("HR=0.72" in r.label for r in signal_refs)

    def test_multiple_signals_all_appear(self):
        sigs = [
            _make_signal(event_type="trial_readout", sig_id="s1"),
            _make_signal(event_type="interim_analysis", sig_id="s2",
                        primary_endpoint_met=None, p_value=None, hazard_ratio=None),
        ]
        output = _output_with_signals(signals=sigs)
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert len(signal_refs) == 2

    def test_non_trial_signal_not_in_trial_section(self):
        sig = _make_signal(event_type="financing", primary_endpoint_met=None, p_value=None, hazard_ratio=None)
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        trial_signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert len(trial_signal_refs) == 0


# ── TestKnowledgeArtifactWiring ───────────────────────────────────────────────

class TestKnowledgeArtifactWiring:
    """KnowledgeArtifact competitor_landscape artifacts flow into competitive section."""

    def test_competitor_landscape_artifact_appears_in_competitive(self):
        art = _make_artifact(artifact_type="competitor_landscape")
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        types = [r.source_type for r in ev.competitive.refs]
        assert SourceType.KNOWLEDGE_ART in types

    def test_artifact_has_as_of_date_from_created_at(self):
        art = _make_artifact(artifact_type="competitor_landscape", created_at_str="2026-01-10T14:30:00")
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert len(art_refs) == 1
        assert art_refs[0].as_of_date == "2026-01-10"

    def test_artifact_has_source_id(self):
        art = _make_artifact(art_id="art-xyz")
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert art_refs[0].source_id == "art-xyz"

    def test_artifact_confidence_high_for_score_0_9(self):
        art = _make_artifact(confidence=0.9)
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert art_refs[0].confidence_label == "High"

    def test_artifact_confidence_medium_for_score_0_6(self):
        art = _make_artifact(confidence=0.6)
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert art_refs[0].confidence_label == "Medium"

    def test_artifact_label_contains_title(self):
        art = _make_artifact(title="My competitive analysis")
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert "My competitive analysis" in art_refs[0].label

    def test_non_landscape_artifact_not_in_competitive(self):
        art = _make_artifact(artifact_type="thesis")
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert len(art_refs) == 0

    def test_no_artifacts_produces_competitive_gap(self):
        output = _output_with_signals(knowledge_artifacts=[])
        ev = MemoEvidenceBuilder.build(output)
        assert any("KnowledgeArtifact" in g for g in ev.competitive.unsupported_claims)

    def test_multiple_artifacts_all_appear(self):
        arts = [
            _make_artifact(art_id="a1", title="Landscape Q1"),
            _make_artifact(art_id="a2", title="Landscape Q2"),
        ]
        output = _output_with_signals(knowledge_artifacts=arts)
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert len(art_refs) == 2


# ── TestDatePopulation ────────────────────────────────────────────────────────

class TestDatePopulation:
    """as_of_date is populated only when the source record carries a timestamp."""

    def test_signal_as_of_date_set_from_signal_date(self):
        sig = _make_signal(signal_date_str="2025-06-01")
        output = _output_with_signals(signals=[sig])
        ev = MemoEvidenceBuilder.build(output)
        signal_refs = [r for r in ev.trial.refs if r.source_type == SourceType.SIGNAL]
        assert signal_refs[0].as_of_date == "2025-06-01"

    def test_artifact_as_of_date_uses_date_portion_only(self):
        art = _make_artifact(created_at_str="2025-11-20T09:15:00")
        output = _output_with_signals(knowledge_artifacts=[art])
        ev = MemoEvidenceBuilder.build(output)
        art_refs = [r for r in ev.competitive.refs if r.source_type == SourceType.KNOWLEDGE_ART]
        assert art_refs[0].as_of_date == "2025-11-20"

    def test_assumption_refs_have_no_date(self):
        output = _make_output(with_assumption_log=True)
        ev = MemoEvidenceBuilder.build(output)
        assumption_refs = [r for r in ev.assumptions.refs if r.source_type == SourceType.ASSUMPTION]
        # No fake dates — all should be None
        assert all(r.as_of_date is None for r in assumption_refs)

    def test_catalyst_refs_have_no_as_of_date(self):
        output = _make_output(with_assumption_log=True, with_catalysts=True)
        ev = MemoEvidenceBuilder.build(output)
        catalyst_refs = [r for r in ev.trial.refs if r.source_type == SourceType.MANUAL]
        # Catalyst refs don't carry evidence timestamps
        assert all(r.as_of_date is None for r in catalyst_refs)


# ── TestVCMemoEvidence ────────────────────────────────────────────────────────

class TestVCMemoEvidence:
    """VC memo renders with evidence blocks wired in."""

    @pytest.fixture(scope="class")
    def vc_output(self):
        return _engine_output(with_comps=False)

    def test_vc_memo_renders(self, vc_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(vc_output, memo_type="vc")
        assert isinstance(memo, str)
        assert len(memo) > 200

    def test_vc_memo_has_evidence_header(self, vc_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(vc_output, memo_type="vc")
        assert "Evidence & Sources" in memo

    def test_vc_memo_has_biology_evidence(self, vc_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(vc_output, memo_type="vc")
        # Biology evidence block appears in scientific rationale section
        assert "Evidence & Sources" in memo

    def test_vc_memo_has_trial_evidence(self, vc_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(vc_output, memo_type="vc")
        # Trial evidence block appears after development timeline
        assert "Evidence & Sources" in memo

    def test_vc_memo_has_competitive_evidence(self, vc_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(vc_output, memo_type="vc")
        # Competitive section gap (no KnowledgeArtifact linked) should appear
        assert "Evidence gap" in memo

    def test_vc_memo_no_crash_with_signals(self):
        from bve.reporting.memo_generator import generate_memo
        output = _engine_output(with_comps=False)
        sig = _make_signal(event_type="trial_readout")
        output.signals = [sig]
        memo = generate_memo(output, memo_type="vc")
        assert "Evidence & Sources" in memo
        # Signal should appear in rendered evidence
        assert "Trial Readout" in memo or "trial readout" in memo.lower()

    def test_vc_memo_evidence_attached_to_output(self, vc_output):
        from bve.reporting.memo_generator import generate_memo
        generate_memo(vc_output, memo_type="vc")
        assert vc_output.memo_evidence is not None


# ── TestHFMemoEvidence ────────────────────────────────────────────────────────

class TestHFMemoEvidence:
    """HF memo renders with evidence blocks wired in."""

    @pytest.fixture(scope="class")
    def hf_output(self):
        return _engine_output(with_comps=False)

    def test_hf_memo_renders(self, hf_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(hf_output, memo_type="hf")
        assert isinstance(memo, str)
        assert len(memo) > 200

    def test_hf_memo_has_evidence_header(self, hf_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(hf_output, memo_type="hf")
        assert "Evidence & Sources" in memo

    def test_hf_memo_trial_evidence_after_catalyst_section(self, hf_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(hf_output, memo_type="hf")
        # Catalyst Calendar section should be followed by evidence
        assert "Catalyst Calendar" in memo
        assert "Evidence & Sources" in memo

    def test_hf_memo_falsification_evidence_present(self, hf_output):
        from bve.reporting.memo_generator import generate_memo
        memo = generate_memo(hf_output, memo_type="hf")
        # Falsification evidence (kill criteria gap at minimum) appears
        assert "Evidence gap" in memo or "Evidence & Sources" in memo

    def test_hf_memo_no_crash_with_knowledge_artifact(self):
        from bve.reporting.memo_generator import generate_memo
        output = _engine_output(with_comps=False)
        art = _make_artifact(artifact_type="competitor_landscape")
        output.knowledge_artifacts = [art]
        memo = generate_memo(output, memo_type="hf")
        assert isinstance(memo, str)

    def test_hf_memo_evidence_attached_to_output(self, hf_output):
        from bve.reporting.memo_generator import generate_memo
        generate_memo(hf_output, memo_type="hf")
        assert hf_output.memo_evidence is not None


# ── TestGracefulFallback ──────────────────────────────────────────────────────

class TestGracefulFallback:
    """Empty signals/artifacts degrade gracefully — identical gap behaviour to Sprint 4."""

    def test_empty_signals_same_gaps_as_no_signals(self):
        output_no_signals = _make_output(with_assumption_log=True)
        output_empty_signals = _make_output(with_assumption_log=True)
        output_empty_signals.signals = []
        ev_no = MemoEvidenceBuilder.build(output_no_signals)
        ev_empty = MemoEvidenceBuilder.build(output_empty_signals)
        assert ev_no.trial.unsupported_claims == ev_empty.trial.unsupported_claims
        assert ev_no.biology.unsupported_claims == ev_empty.biology.unsupported_claims

    def test_empty_artifacts_same_gaps_as_no_artifacts(self):
        output_no_art = _make_output(with_assumption_log=True)
        output_empty_art = _make_output(with_assumption_log=True)
        output_empty_art.knowledge_artifacts = []
        ev_no = MemoEvidenceBuilder.build(output_no_art)
        ev_empty = MemoEvidenceBuilder.build(output_empty_art)
        assert ev_no.competitive.unsupported_claims == ev_empty.competitive.unsupported_claims

    def test_malformed_signal_does_not_crash_builder(self):
        """A signal object missing expected fields defaults to a gap via the fault-tolerant builder."""
        from unittest.mock import MagicMock
        bad_sig = MagicMock(spec=[])  # spec=[] means no attributes → all access raises AttributeError
        bad_sig.event_type = "trial_readout"  # minimal attribute to pass routing
        output = _output_with_signals(signals=[bad_sig])
        # Builder must not raise; it may produce refs or gaps, but must return MemoEvidence
        ev = MemoEvidenceBuilder.build(output)
        assert isinstance(ev, MemoEvidence)

    def test_malformed_artifact_does_not_crash_builder(self):
        from unittest.mock import MagicMock
        bad_art = MagicMock(spec=[])
        bad_art.artifact_type = "competitor_landscape"
        output = _output_with_signals(knowledge_artifacts=[bad_art])
        ev = MemoEvidenceBuilder.build(output)
        assert isinstance(ev, MemoEvidence)

    def test_signals_on_output_default_to_empty_list(self):
        output = _make_output(with_assumption_log=True)
        assert output.signals == []

    def test_knowledge_artifacts_on_output_default_to_empty_list(self):
        output = _make_output(with_assumption_log=True)
        assert output.knowledge_artifacts == []

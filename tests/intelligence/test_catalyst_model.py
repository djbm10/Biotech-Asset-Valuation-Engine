from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from bve.entities.trial import TrialPhase
from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType
from bve.models.catalyst_model import CatalystModel


def _add_signal(
    store: KnowledgeStore, *, signal_id: str, randomization: str, endpoint_type: str
) -> None:
    signal = StructuredSignal(
        id=signal_id,
        event_id=f"evt-{signal_id}",
        asset_id="asset-1",
        company_id="company-1",
        event_type=EventType.TRIAL_READOUT,
        signal_date=date(2026, 3, 9),
        trial_phase=TrialPhase.PHASE_3,
        randomization=randomization,
        endpoint_type=endpoint_type,
        extraction_model="unit-test",
        extraction_confidence=0.9,
        created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )
    store.add_structured_signal(
        signal,
        SourceTrace(source_type="test", source_ref="signal"),
        extraction_result_id="extract-1",
    )


def test_score_catalyst_applies_trial_design_multiplier_os_rct():
    store = KnowledgeStore(":memory:")
    _add_signal(store, signal_id="sig-os-rct", randomization="randomized", endpoint_type="os")
    model = CatalystModel(store=store)

    out = model.score_catalyst(
        "trial_readout",
        "phase_3",
        signal_id="sig-os-rct",
        asset_id="asset-1",
        event_key="evt-os-rct",
    )

    # Base profile p=0.52; design-adjusted probability is surfaced separately.
    assert out.p_positive_outcome == pytest.approx(0.52, abs=1e-6)
    assert out.design_adjusted_p_positive_outcome == pytest.approx(0.572, abs=1e-6)
    assert out.design_quality_multiplier == pytest.approx(1.10, abs=1e-6)
    store.close()


def test_score_catalyst_without_assessment_keeps_base_probability():
    store = KnowledgeStore(":memory:")
    model = CatalystModel(store=store)

    out = model.score_catalyst(
        "trial_readout",
        "phase_3",
        signal_id=None,
        asset_id="asset-1",
        event_key="evt-no-assessment",
    )

    assert out.p_positive_outcome == pytest.approx(0.52, abs=1e-6)
    store.close()


def test_catalyst_valuation_is_rnpv_independent_shape():
    store = KnowledgeStore(":memory:")
    model = CatalystModel(store=store)

    out = model.score_catalyst("fda_approval", None, asset_id="asset-1", event_key="evt-1")
    payload = out.model_dump(mode="json")

    assert "rnpv" not in " ".join(payload.keys()).lower()
    assert "delta_npv" not in " ".join(payload.keys()).lower()
    store.close()

from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pytest

from bve.entities.trial import TrialPhase
from bve.intelligence.knowledge_layer import DossierRecord, SourceTrace, StoredValuationDiff
from bve.intelligence.memo_generation import (
    WeeklyMemoGenerator,
    WeeklyMemoInput,
    WeeklyMemoPromptBuilder,
)
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.taxonomy import EventType

_NOW = datetime(2026, 3, 8, 10, 0, tzinfo=timezone.utc)


def _signal(
    signal_id: str,
    event_id: str,
    event_type: EventType,
    signal_date: date,
    confidence: float,
) -> StructuredSignal:
    return StructuredSignal(
        id=signal_id,
        event_id=event_id,
        asset_id="asset-1",
        company_id="company-1",
        event_type=event_type,
        signal_date=signal_date,
        trial_phase=TrialPhase.PHASE_2,
        primary_endpoint_met=True,
        extraction_confidence=confidence,
        extraction_model="unit-test",
        created_at=_NOW,
    )


def _diff(run_id: str, event_id: str, delta_npv: float) -> StoredValuationDiff:
    return StoredValuationDiff(
        run_id=run_id,
        event_id=event_id,
        asset_id="asset-1",
        valuation_before={"rnpv_millions": 100.0, "nav_per_share": 4.0},
        valuation_after={"rnpv_millions": 100.0 + delta_npv, "nav_per_share": 4.0 + delta_npv / 100.0},
        delta_npv=delta_npv,
        created_at=_NOW,
        assumptions_changed=[
            {
                "field": "trials[phase_2].success_probability",
                "old_value": 0.45,
                "new_value": 0.53,
            }
        ],
    )


def _decision(decision_id: str, run_id: str | None, decision: str, rationale: str) -> ReviewDecision:
    return ReviewDecision(
        id=decision_id,
        proposal_id=f"prop-{decision_id}",
        run_id=run_id,
        decision=decision,
        reviewer_id="analyst-1",
        reviewed_at=_NOW,
        rationale=rationale,
    )


def _dossier(diff: StoredValuationDiff) -> DossierRecord:
    return DossierRecord(
        id="dossier-1",
        company_id="company-1",
        asset_id="asset-1",
        generated_at=_NOW,
        current_assumptions={"trials[phase_2].success_probability": 0.53},
        latest_valuation_snapshot={"rnpv_millions": 130.0, "nav_per_share": 4.3},
        recent_changes=[diff],
        open_questions=["Need updated enrollment timeline"],
        source_trace=SourceTrace(source_type="unit_test", source_ref="dossier"),
    )


def test_prompt_builder_contains_guardrails_and_input_ids():
    signal = _signal("sig-1", "evt-1", EventType.TRIAL_READOUT, date(2026, 3, 7), 0.92)
    diff = _diff("run-1", "evt-1", 30.0)
    decision = _decision("dec-1", "run-1", "accepted", "Evidence adequate")
    dossier = _dossier(diff)

    memo_input = WeeklyMemoInput(
        dossier=dossier,
        structured_events=[signal],
        valuation_diffs=[diff],
        review_decisions=[decision],
        ambiguous_signal_ids=[signal.id],
        generated_at=_NOW,
    )

    builder = WeeklyMemoPromptBuilder()
    system = builder.build_system_prompt()
    user = builder.build_user_prompt(memo_input)

    assert "Do not invent claims" in system
    assert "Every factual bullet must include at least one record citation" in system
    assert "## Key Events" in user
    assert "## Needs Review Next" in user
    assert "[signal:<id>]" in user
    assert "sig-1" in user
    assert "run-1" in user
    assert "dossier-1" in user


def test_weekly_memo_output_format_and_citations():
    signal = _signal("sig-1", "evt-1", EventType.TRIAL_READOUT, date(2026, 3, 7), 0.92)
    diff = _diff("run-1", "evt-1", 30.0)
    decision = _decision("dec-1", "run-1", "accepted", "Evidence adequate")
    dossier = _dossier(diff)

    output = WeeklyMemoGenerator().generate(
        WeeklyMemoInput(
            dossier=dossier,
            structured_events=[signal],
            valuation_diffs=[diff],
            review_decisions=[decision],
            generated_at=_NOW,
        ),
        memo_id="memo-1",
        week_ending=date(2026, 3, 8),
    )

    content = output.content_markdown
    for section in (
        "## Key Events",
        "## Valuation Changes",
        "## Why It Changed",
        "## Uncertainties",
        "## Needs Review Next",
        "## Sources",
    ):
        assert section in content

    bullet_lines = [line for line in content.splitlines() if line.strip().startswith("- ")]
    assert bullet_lines, "Expected bullet lines in memo output"
    for line in bullet_lines:
        assert re.search(r"\[[a-z_]+:[^\]]+\]", line), f"Missing citation: {line}"

    assert output.cited_signal_ids == ["sig-1"]
    assert output.cited_run_ids == ["run-1"]
    assert output.cited_event_ids == ["evt-1"]
    assert output.period_start == date(2026, 3, 2)
    assert output.period_end == date(2026, 3, 8)


def test_uncertainties_and_next_review_highlighted():
    low_conf_signal = _signal("sig-low", "evt-low", EventType.SAFETY_SIGNAL, date(2026, 3, 7), 0.61)
    diff = _diff("run-2", "evt-low", -12.0)
    deferred = _decision("dec-deferred", "run-2", "deferred", "Need external benchmark")
    dossier = _dossier(diff)

    output = WeeklyMemoGenerator(low_confidence_threshold=0.80).generate(
        WeeklyMemoInput(
            dossier=dossier,
            structured_events=[low_conf_signal],
            valuation_diffs=[diff],
            review_decisions=[deferred],
            ambiguous_signal_ids=["sig-low"],
            generated_at=_NOW,
        ),
        memo_id="memo-uncertain",
        week_ending=date(2026, 3, 8),
    )

    content = output.content_markdown
    assert "ambiguity flagged" in content
    assert "low extraction confidence" in content
    assert "deferred review dec-deferred" in content
    assert "Complete deferred decision dec-deferred" in content
    assert "Need updated enrollment timeline" in output.open_questions

    memo_record = output.to_memo_record(SourceTrace(source_type="unit_test", source_ref="memo"))
    assert memo_record.memo_type == "weekly_asset_memo"
    assert memo_record.source_signal_ids == ["sig-low"]
    assert memo_record.source_run_ids == ["run-2"]
    assert memo_record.referenced_event_ids == ["evt-low"]
    assert memo_record.referenced_diff_ids == ["run-2"]
    assert memo_record.referenced_review_ids == ["dec-deferred"]


def test_valuation_diff_coverage_guard_raises_when_section_omits_diff():
    signal = _signal("sig-1", "evt-1", EventType.TRIAL_READOUT, date(2026, 3, 7), 0.92)
    diff = _diff("run-1", "evt-1", 30.0)
    dossier = _dossier(diff)

    # max_diffs=0 forces the valuation section to emit a \"no records\" line.
    generator = WeeklyMemoGenerator(max_diffs=0)
    with pytest.raises(ValueError, match="valuation_diffs were provided"):
        generator.generate(
            WeeklyMemoInput(
                dossier=dossier,
                structured_events=[signal],
                valuation_diffs=[diff],
                review_decisions=[],
                generated_at=_NOW,
            ),
            memo_id="memo-guard",
            week_ending=date(2026, 3, 8),
        )

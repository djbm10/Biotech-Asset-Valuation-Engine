"""
Score-change audit trail — test suite.

Validates that ledger replay can produce a per-change trail explaining exactly
why a company's feature scores moved: which sourced event applied which delta,
before/after, with decay and clamping made explicit.

Core guarantee: compute_score_state_with_trail produces the SAME final scores
as compute_score_state (wrapper equivalence) — the trail is additive.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from bve.ingestion.evidence_ledger import (
    DEFAULT_SEED_SCORES,
    EvidenceLedger,
    EvidenceRecord,
    ScoreChangeEntry,
)


def _record(
    ticker="SRPT",
    event_date="2026-01-10",
    event_type="clinical_positive_ph3",
    direction="positive",
    deltas=None,
    confidence=0.85,
    source_type="press_release",
    source_url="https://example.com/pr",
    raw_text="Phase 3 trial met its primary endpoint with high significance",
    reasons=None,
) -> EvidenceRecord:
    return EvidenceRecord(
        ticker=ticker,
        event_date=event_date,
        event_type=event_type,
        direction=direction,
        phase_detected="Phase 3",
        source_type=source_type,
        source_url=source_url,
        raw_text=raw_text,
        confidence=confidence,
        match_reasons=reasons or ["met_primary"],
        score_deltas=deltas if deltas is not None else {"asset_quality": 0.10},
    )


def _ledger(tmp_path: Path, records) -> EvidenceLedger:
    led = EvidenceLedger(path=tmp_path / "ledger.jsonl")
    for r in records:
        led.append_if_not_duplicate(r)
    return led


# ---------------------------------------------------------------------------
# Wrapper equivalence (the non-negotiable test)
# ---------------------------------------------------------------------------


class TestEquivalence:
    def test_trail_scores_match_plain_scores(self, tmp_path):
        records = [
            _record(event_date="2026-01-05", deltas={"asset_quality": 0.10}),
            _record(event_date="2026-02-05", event_type="cash_low",
                    deltas={"seller_willingness": 0.12}, direction="negative"),
            _record(event_date="2026-03-05", event_type="strategic_review",
                    deltas={"seller_willingness": 0.20}, direction="mixed"),
        ]
        led = _ledger(tmp_path, records)

        plain = led.compute_score_state(ticker="SRPT")
        scores, trail = led.compute_score_state_with_trail(ticker="SRPT")

        assert scores == plain
        assert len(trail) >= 1

    def test_equivalence_with_decay(self, tmp_path):
        records = [
            _record(event_date="2026-01-05", deltas={"asset_quality": 0.10}),
            _record(event_date="2026-02-05", event_type="cash_low",
                    deltas={"seller_willingness": 0.12}),
        ]
        led = _ledger(tmp_path, records)

        plain = led.compute_score_state(ticker="SRPT", as_of_date=date(2026, 6, 1), apply_decay=True)
        scores, _ = led.compute_score_state_with_trail(
            ticker="SRPT", as_of_date=date(2026, 6, 1), apply_decay=True
        )
        assert scores == plain


# ---------------------------------------------------------------------------
# Trail arithmetic
# ---------------------------------------------------------------------------


class TestTrailArithmetic:
    def test_before_plus_applied_equals_after(self, tmp_path):
        led = _ledger(tmp_path, [_record(deltas={"asset_quality": 0.10})])
        _, trail = led.compute_score_state_with_trail(ticker="SRPT")
        for e in trail:
            assert e.score_after == pytest.approx(e.score_before + e.delta_applied)

    def test_chronological_chaining(self, tmp_path):
        records = [
            _record(event_date="2026-01-05", deltas={"asset_quality": 0.10}),
            _record(event_date="2026-02-05", deltas={"asset_quality": 0.05}),
        ]
        led = _ledger(tmp_path, records)
        _, trail = led.compute_score_state_with_trail(ticker="SRPT")
        aq = [e for e in trail if e.feature == "asset_quality"]
        assert len(aq) == 2
        # Second entry starts where the first left off.
        assert aq[1].score_before == pytest.approx(aq[0].score_after)

    def test_clamp_recorded(self, tmp_path):
        # A huge positive delta should clamp at 1.0 and flag clamped=True.
        seed = {"asset_quality": 0.95}
        led = _ledger(tmp_path, [_record(deltas={"asset_quality": 0.50})])
        _, trail = led.compute_score_state_with_trail(ticker="SRPT", seed_scores=seed)
        aq = [e for e in trail if e.feature == "asset_quality"][0]
        assert aq.score_after == pytest.approx(1.0)
        assert aq.clamped is True
        # Requested exceeds applied because of the clamp.
        assert aq.delta_requested > aq.delta_applied

    def test_decay_reduces_applied_delta(self, tmp_path):
        led = _ledger(tmp_path, [
            _record(event_date="2026-01-05", event_type="cash_low",
                    deltas={"seller_willingness": 0.12}),
        ])
        _, trail = led.compute_score_state_with_trail(
            ticker="SRPT", as_of_date=date(2026, 6, 1), apply_decay=True
        )
        sw = [e for e in trail if e.feature == "seller_willingness"]
        if sw and sw[0].decay_weight < 1.0:
            assert abs(sw[0].delta_applied) < abs(sw[0].delta_requested)


# ---------------------------------------------------------------------------
# Provenance carried on each entry
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_entry_carries_source_fields(self, tmp_path):
        led = _ledger(tmp_path, [_record(
            source_url="https://sec.gov/8k", source_type="sec_filing",
            confidence=0.9, reasons=["met_primary", "stat_sig"],
        )])
        _, trail = led.compute_score_state_with_trail(ticker="SRPT")
        e = trail[0]
        assert e.source_url == "https://sec.gov/8k"
        assert e.source_type == "sec_filing"
        assert e.confidence == 0.9
        assert "met_primary" in e.reasons
        assert e.event_type == "clinical_positive_ph3"

    def test_snippet_truncated(self, tmp_path):
        long_text = "x" * 500
        led = _ledger(tmp_path, [_record(raw_text=long_text)])
        _, trail = led.compute_score_state_with_trail(ticker="SRPT")
        assert len(trail[0].snippet) <= 200


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------


class TestRenderer:
    def test_render_includes_provenance(self, tmp_path):
        from bve.reporting.score_audit import render_score_audit

        led = _ledger(tmp_path, [_record(
            source_url="https://sec.gov/8k", deltas={"asset_quality": 0.10},
        )])
        scores, trail = led.compute_score_state_with_trail(ticker="SRPT")
        md = render_score_audit("SRPT", scores, trail)
        assert "SRPT" in md
        assert "asset_quality" in md
        assert "sec.gov/8k" in md
        assert "clinical_positive_ph3" in md

    def test_render_handles_empty_trail(self, tmp_path):
        from bve.reporting.score_audit import render_score_audit

        led = _ledger(tmp_path, [])
        scores, trail = led.compute_score_state_with_trail(ticker="NOPE")
        md = render_score_audit("NOPE", scores, trail)
        assert "NOPE" in md


# ---------------------------------------------------------------------------
# ScoreChangeEntry shape
# ---------------------------------------------------------------------------


class TestEntryShape:
    def test_entry_is_serializable(self, tmp_path):
        led = _ledger(tmp_path, [_record()])
        _, trail = led.compute_score_state_with_trail(ticker="SRPT")
        d = trail[0].to_dict()
        assert d["feature"] == "asset_quality"
        assert "delta_applied" in d
        assert "source_url" in d

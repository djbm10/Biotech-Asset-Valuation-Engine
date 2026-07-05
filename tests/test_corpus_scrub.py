"""Tests for the corpus outcome-leakage scrubber.

Pins: the scrubber removes outcome language, preserves the pre-decision evidence, is
idempotent, and — the regression guard — the live corpus has ZERO residual leakage.
"""
from __future__ import annotations

from pathlib import Path

from bve.analysis.claim_calibration_corpus import load_corpus
from bve.analysis.corpus_scrub import (
    audit_corpus,
    detect_leakage,
    scrub_corpus,
    scrub_text,
)

REPO = Path(__file__).resolve().parents[1]
LIVE_CORPUS = REPO / "research" / "data" / "claim_calibration_corpus.csv"


def test_detect_leakage_flags_outcome_terms():
    assert detect_leakage("feasible for accelerated approval") == ["approval"]
    assert "withdrawal" in detect_leakage("before market withdrawal decision")
    assert detect_leakage("dose-limiting thrombocytopenia at efficacious exposure") == []


def test_scrub_removes_outcome_but_keeps_evidence():
    src = (
        "CHRYSALIS showed ORR around 40% with median DOR 11.1 months; infusion/rash risks "
        "but exposure judged feasible for approval. Need label discontinuation extraction."
    )
    out = scrub_text(src)
    assert detect_leakage(out) == []
    # Evidence preserved.
    assert "ORR around 40%" in out
    assert "median DOR 11.1 months" in out
    assert "infusion/rash" in out
    # "discontinuation" is a legitimate data request, not an outcome — must survive.
    assert "discontinuation extraction" in out


def test_scrub_neutralizes_common_phrases():
    assert "at the selected dose" in scrub_text("active exposure feasible for accelerated approval")
    assert detect_leakage(scrub_text("approvals support held therapeutic window")) == []
    assert detect_leakage(scrub_text("but ODAC judged risk-benefit unfavorable")) == []
    assert detect_leakage(scrub_text("Single-arm trial showed high ORR before approval")) == []


def test_scrub_is_idempotent():
    src = "exposure judged feasible for accelerated approval before market withdrawal decision"
    once = scrub_text(src)
    assert scrub_text(once) == once
    assert detect_leakage(once) == []


def test_scrub_leaves_clean_text_unchanged():
    clean = "Dose-limiting thrombocytopenia constrained the efficacious exposure."
    assert scrub_text(clean) == clean


# --- regression guard: the live corpus must stay clean ------------------------


def test_live_corpus_has_zero_leakage():
    records = load_corpus(LIVE_CORPUS)
    assert records, "corpus should exist"
    flagged = audit_corpus(records)
    assert flagged == {}, f"outcome leakage present in: {flagged}"


def test_scrubbing_live_corpus_is_a_noop_now():
    # Already scrubbed => re-scrubbing changes nothing.
    records = load_corpus(LIVE_CORPUS)
    _, changed = scrub_corpus(records)
    assert changed == []

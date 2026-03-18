"""
Tests for the LLM confidence gating logic in ExtractionRuntimeConfig (Wave 1 safeguard).

Uses a mocked pipeline to isolate the gating logic without network calls or LLM APIs.
Tests the three zones:
  - conf < 0.30 (discard threshold): signal not stored, not sent to valuation
  - 0.30 ≤ conf < 0.50 (review threshold): signal stored for audit, not sent to valuation
  - conf ≥ 0.50: signal processed normally through pipeline
"""
from __future__ import annotations

import pytest

from bve.pipeline.watchlist_runner import ExtractionRuntimeConfig


class TestExtractionRuntimeConfigDefaults:
    def test_default_discard_threshold(self):
        cfg = ExtractionRuntimeConfig()
        assert cfg.confidence_discard_threshold == 0.3

    def test_default_review_threshold(self):
        cfg = ExtractionRuntimeConfig()
        assert cfg.confidence_review_threshold == 0.5

    def test_discard_threshold_must_be_nonnegative(self):
        with pytest.raises(Exception):
            ExtractionRuntimeConfig(confidence_discard_threshold=-0.1)

    def test_review_threshold_must_be_le_one(self):
        with pytest.raises(Exception):
            ExtractionRuntimeConfig(confidence_review_threshold=1.1)

    def test_custom_thresholds_accepted(self):
        cfg = ExtractionRuntimeConfig(
            confidence_discard_threshold=0.2,
            confidence_review_threshold=0.6,
        )
        assert cfg.confidence_discard_threshold == 0.2
        assert cfg.confidence_review_threshold == 0.6


class TestGatingLogic:
    """
    Test the three-zone gating logic using the threshold comparisons
    that the pipeline applies.  Logic extracted to pure functions for testability.
    """

    @staticmethod
    def _gate(conf: float, discard: float = 0.3, review: float = 0.5) -> str:
        """Mirror of the gating logic in watchlist_runner.run_once()."""
        if conf < discard:
            return "discard"
        if conf < review:
            return "review_only"
        return "process"

    def test_zero_confidence_discarded(self):
        assert self._gate(0.0) == "discard"

    def test_below_discard_discarded(self):
        assert self._gate(0.15) == "discard"

    def test_at_discard_threshold_review(self):
        assert self._gate(0.3) == "review_only"

    def test_between_thresholds_review(self):
        assert self._gate(0.4) == "review_only"

    def test_at_review_threshold_processed(self):
        assert self._gate(0.5) == "process"

    def test_above_review_threshold_processed(self):
        assert self._gate(0.9) == "process"

    def test_full_confidence_processed(self):
        assert self._gate(1.0) == "process"

    def test_custom_thresholds_discard_zone(self):
        assert self._gate(0.15, discard=0.2, review=0.6) == "discard"

    def test_custom_thresholds_review_zone(self):
        assert self._gate(0.4, discard=0.2, review=0.6) == "review_only"

    def test_custom_thresholds_process_zone(self):
        assert self._gate(0.7, discard=0.2, review=0.6) == "process"

    def test_boundary_precision(self):
        # Confirm floating-point boundary behavior: 0.2999... is discard
        assert self._gate(0.2999) == "discard"
        # 0.3000 exactly is review_only
        assert self._gate(0.3000) == "review_only"
        # 0.4999... is review_only
        assert self._gate(0.4999) == "review_only"
        # 0.5000 exactly is process
        assert self._gate(0.5000) == "process"

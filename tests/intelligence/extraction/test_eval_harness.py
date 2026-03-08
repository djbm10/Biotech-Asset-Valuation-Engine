"""
Evaluation harness tests for the extraction pipeline.

Validates:
  1. All synthetic fixture files are valid JSON and loadable.
  2. All labeled fixture files are valid JSON and loadable.
  3. FakeLLMClient extracts expected event_types for each fixture
     (using the fixture's expected event_type as the mock response).
  4. EvalScore scoring logic (field matching, tolerance).
  5. EvalSummary aggregation across fixtures.
  6. Fixtures have required top-level keys.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pytest

from bve.intelligence.extraction.extractor import SignalExtractor
from bve.intelligence.extraction.llm_client import FakeLLMClient
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument
from bve.intelligence.extraction.result import ExtractionResult, ExtractionStatus

FIXTURES_DIR  = Path(__file__).parent / "fixtures"
SYNTHETIC_DIR = FIXTURES_DIR / "synthetic"
LABELED_DIR   = FIXTURES_DIR / "labeled"

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Harness data structures
# ---------------------------------------------------------------------------

class EvalScore:
    """Per-fixture scoring result."""

    def __init__(
        self,
        fixture_id: str,
        status_match: bool,
        field_scores: dict[str, bool],
    ) -> None:
        self.fixture_id   = fixture_id
        self.status_match = status_match
        self.field_scores = field_scores
        self.overall_pass = status_match and all(field_scores.values())

    def __repr__(self) -> str:
        return (
            f"EvalScore(id={self.fixture_id!r}, pass={self.overall_pass}, "
            f"fields={self.field_scores})"
        )


class EvalSummary:
    """Aggregated accuracy across all fixtures."""

    def __init__(self, scores: list[EvalScore]) -> None:
        self.total          = len(scores)
        self.passed         = sum(1 for s in scores if s.overall_pass)
        self.pass_rate      = self.passed / self.total if self.total > 0 else 0.0
        self.failure_cases  = [s.fixture_id for s in scores if not s.overall_pass]

        # Per-field accuracy
        all_fields: dict[str, list[bool]] = {}
        for s in scores:
            for field, result in s.field_scores.items():
                all_fields.setdefault(field, []).append(result)
        self.per_field_accuracy = {
            f: sum(v) / len(v) for f, v in all_fields.items()
        }


def load_fixtures(fixture_dir: Path) -> list[dict[str, Any]]:
    """Load all *.json fixture files from a directory (non-recursive)."""
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(fixture_dir.glob("*.json"))
    ]


def score_result(
    fixture_id: str,
    result: ExtractionResult,
    expected: dict[str, Any],
    tolerance: dict[str, float],
) -> EvalScore:
    """Compare extraction result against expected fields."""
    status_match = result.status == ExtractionStatus.SUCCESS

    field_scores: dict[str, bool] = {}
    if result.signal is None:
        # All expected fields fail if signal is absent
        for field in expected:
            field_scores[field] = False
        return EvalScore(fixture_id, status_match, field_scores)

    signal = result.signal
    for field, expected_value in expected.items():
        actual_value = getattr(signal, field, None)
        if expected_value is None:
            field_scores[field] = actual_value is None
        elif isinstance(expected_value, float):
            tol = tolerance.get(field, abs(expected_value) * 0.02 + 1e-9)  # 2% default
            field_scores[field] = (
                actual_value is not None
                and abs(float(actual_value) - expected_value) <= tol
            )
        elif isinstance(expected_value, bool):
            field_scores[field] = actual_value is expected_value
        elif isinstance(expected_value, str):
            actual_str = (
                actual_value.value if hasattr(actual_value, "value") else str(actual_value)
                if actual_value is not None else None
            )
            field_scores[field] = actual_str == expected_value
        else:
            field_scores[field] = actual_value == expected_value

    return EvalScore(fixture_id, status_match, field_scores)


def _make_doc_from_fixture(fixture: dict) -> RawDocument:
    rd = fixture["raw_document"]
    hints_data = rd.get("entity_hints", {})
    hints = EntityHints(
        asset_id=hints_data.get("asset_id", "asset-test"),
        company_id=hints_data.get("company_id", "company-test"),
        drug_name=hints_data.get("drug_name"),
        indication=hints_data.get("indication"),
        ticker=hints_data.get("ticker"),
        nct_id=hints_data.get("nct_id"),
    )
    published_at = None
    if rd.get("published_at"):
        try:
            published_at = datetime.fromisoformat(
                rd["published_at"].replace("Z", "+00:00")
            )
        except ValueError:
            pass
    return RawDocument.from_text(
        id=rd.get("id", str(uuid.uuid4())),
        source=rd.get("source", "manual"),
        title=rd.get("title", "Test Document"),
        raw_text=rd.get("raw_text", "placeholder"),
        entity_hints=hints,
        retrieved_at=_NOW,
        source_url=rd.get("source_url"),
        published_at=published_at,
    )


def _make_success_response(expected: dict) -> str:
    """
    Build a canned LLM response that should produce a successful extraction
    matching the expected fields.
    """
    response = {
        "event_type": expected.get("event_type", "trial_readout"),
        "signal_date": expected.get("signal_date", "2024-06-01"),
        "confidence": 0.92,
        "ambiguity_flag": False,
        "rationale": f"This is a {expected.get('event_type', 'unknown')} event.",
        "interim_flag": expected.get("interim_flag", False),
    }
    # Add optional fields from expected if not None
    for field in [
        "trial_phase", "trial_nct_id", "primary_endpoint_met",
        "hazard_ratio", "p_value", "response_rate", "safety_grade",
        "fda_action_type", "designation_type",
        "deal_value_millions", "deal_type", "payer_name",
    ]:
        val = expected.get(field)
        if val is not None:
            response[field] = val
    return json.dumps(response)


# ---------------------------------------------------------------------------
# Fixture loading tests
# ---------------------------------------------------------------------------

class TestFixtureLoading:
    def test_synthetic_fixtures_exist(self):
        assert SYNTHETIC_DIR.exists()
        fixtures = list(SYNTHETIC_DIR.glob("*.json"))
        assert len(fixtures) >= 8, f"Expected ≥8 synthetic fixtures, found {len(fixtures)}"

    def test_labeled_fixtures_exist(self):
        assert LABELED_DIR.exists()
        fixtures = list(LABELED_DIR.glob("*.json"))
        assert len(fixtures) >= 2, f"Expected ≥2 labeled fixtures, found {len(fixtures)}"

    @pytest.mark.parametrize("fixture_path", sorted(SYNTHETIC_DIR.glob("*.json")))
    def test_synthetic_fixture_valid_json(self, fixture_path: Path):
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        assert "fixture_id" in data
        assert "raw_document" in data
        assert "expected" in data

    @pytest.mark.parametrize("fixture_path", sorted(LABELED_DIR.glob("*.json")))
    def test_labeled_fixture_valid_json(self, fixture_path: Path):
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        assert "fixture_id" in data
        assert "raw_document" in data
        assert "expected" in data
        # Labeled fixtures must have provenance metadata
        assert "labeled_by" in data
        assert "labeled_at" in data

    @pytest.mark.parametrize("fixture_path", sorted(SYNTHETIC_DIR.glob("*.json")))
    def test_synthetic_fixture_raw_document_valid(self, fixture_path: Path):
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        doc = _make_doc_from_fixture(data)
        assert isinstance(doc, RawDocument)
        assert doc.raw_text.strip()

    @pytest.mark.parametrize("fixture_path", sorted(SYNTHETIC_DIR.glob("*.json")))
    def test_synthetic_fixture_event_type_valid(self, fixture_path: Path):
        from bve.intelligence.taxonomy import EventType
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        event_type_str = data["expected"]["event_type"]
        # Should not raise
        et = EventType(event_type_str)
        assert et.value == event_type_str


# ---------------------------------------------------------------------------
# EvalScore scoring logic
# ---------------------------------------------------------------------------

class TestEvalScoring:
    def _make_result(self, signal_kwargs: dict) -> ExtractionResult:
        """Create a mock ExtractionResult with a real StructuredSignal."""
        from bve.intelligence.schemas.signals import StructuredSignal
        from bve.intelligence.taxonomy import EventType
        from datetime import date
        signal = StructuredSignal(
            id=str(uuid.uuid4()),
            event_id="evt-eval-001",
            asset_id="asset-001",
            company_id="company-001",
            event_type=EventType.TRIAL_READOUT,
            signal_date=date(2024, 6, 1),
            extraction_confidence=0.9,
            created_at=_NOW,
            **signal_kwargs,
        )
        return ExtractionResult(
            document_id="doc-001",
            asset_id="asset-001",
            company_id="company-001",
            status=ExtractionStatus.SUCCESS,
            signal=signal,
            extracted_at=_NOW,
        )

    def test_exact_match_event_type(self):
        result = self._make_result({})
        expected = {"event_type": "trial_readout"}
        score = score_result("test", result, expected, tolerance={})
        assert score.field_scores["event_type"] is True

    def test_wrong_event_type_fails(self):
        result = self._make_result({})
        expected = {"event_type": "fda_approval"}
        score = score_result("test", result, expected, tolerance={})
        assert score.field_scores["event_type"] is False

    def test_float_within_tolerance_passes(self):
        result = self._make_result({"hazard_ratio": 0.72})
        expected = {"hazard_ratio": 0.73}
        score = score_result("test", result, expected, tolerance={"hazard_ratio": 0.02})
        assert score.field_scores["hazard_ratio"] is True

    def test_float_outside_tolerance_fails(self):
        result = self._make_result({"hazard_ratio": 0.50})
        expected = {"hazard_ratio": 0.73}
        score = score_result("test", result, expected, tolerance={"hazard_ratio": 0.02})
        assert score.field_scores["hazard_ratio"] is False

    def test_null_expected_none_actual_passes(self):
        result = self._make_result({})  # safety_grade is None by default
        expected = {"safety_grade": None}
        score = score_result("test", result, expected, tolerance={})
        assert score.field_scores["safety_grade"] is True

    def test_null_expected_but_value_actual_fails(self):
        result = self._make_result({"safety_grade": 3})
        expected = {"safety_grade": None}
        score = score_result("test", result, expected, tolerance={})
        assert score.field_scores["safety_grade"] is False

    def test_overall_pass_requires_all_fields_correct(self):
        result = self._make_result({"hazard_ratio": 0.72})
        expected = {
            "event_type": "trial_readout",  # correct
            "hazard_ratio": 0.90,           # wrong
        }
        score = score_result("test", result, expected, tolerance={})
        assert score.overall_pass is False

    def test_status_mismatch_fails_overall(self):
        result = ExtractionResult(
            document_id="d",
            asset_id="a",
            company_id="c",
            status=ExtractionStatus.PARSE_ERROR,
            extracted_at=_NOW,
        )
        expected = {"event_type": "trial_readout"}
        score = score_result("test", result, expected, tolerance={})
        assert score.status_match is False
        assert score.overall_pass is False


# ---------------------------------------------------------------------------
# EvalSummary aggregation
# ---------------------------------------------------------------------------

class TestEvalSummary:
    def test_all_passing(self):
        scores = [
            EvalScore("f1", True, {"event_type": True}),
            EvalScore("f2", True, {"event_type": True, "trial_phase": True}),
        ]
        summary = EvalSummary(scores)
        assert summary.total == 2
        assert summary.passed == 2
        assert summary.pass_rate == 1.0
        assert summary.failure_cases == []

    def test_partial_failure(self):
        scores = [
            EvalScore("f1", True, {"event_type": True}),
            EvalScore("f2", False, {"event_type": False}),
        ]
        summary = EvalSummary(scores)
        assert summary.total == 2
        assert summary.passed == 1
        assert summary.pass_rate == 0.5
        assert "f2" in summary.failure_cases

    def test_per_field_accuracy(self):
        scores = [
            EvalScore("f1", True, {"event_type": True, "trial_phase": True}),
            EvalScore("f2", True, {"event_type": True, "trial_phase": False}),
        ]
        summary = EvalSummary(scores)
        assert summary.per_field_accuracy["event_type"] == 1.0
        assert summary.per_field_accuracy["trial_phase"] == 0.5

    def test_empty_scores(self):
        summary = EvalSummary([])
        assert summary.total == 0
        assert summary.pass_rate == 0.0


# ---------------------------------------------------------------------------
# End-to-end: fixtures → FakeLLMClient → extraction → scoring
# ---------------------------------------------------------------------------

class TestEndToEndWithFixtures:
    @pytest.mark.parametrize("fixture_path", sorted(SYNTHETIC_DIR.glob("*.json")))
    def test_synthetic_fixture_extracts_correctly(self, fixture_path: Path):
        """
        For each synthetic fixture, build a FakeLLMClient that returns the
        expected event_type and key fields, then run extraction and score.
        """
        data     = json.loads(fixture_path.read_text(encoding="utf-8"))
        expected = data["expected"]
        tolerance = data.get("tolerance", {})
        doc      = _make_doc_from_fixture(data)

        # Build a canned LLM response that matches expected fields
        canned_response = _make_success_response(expected)
        llm    = FakeLLMClient(default_response=canned_response)
        ext    = SignalExtractor(llm_client=llm)
        result = ext.extract(doc)

        score = score_result(
            fixture_id=data["fixture_id"],
            result=result,
            expected=expected,
            tolerance=tolerance,
        )

        assert score.status_match, (
            f"Fixture {data['fixture_id']!r}: extraction status was "
            f"{result.status} instead of SUCCESS. Errors: {result.validation_errors}"
        )

        failing_fields = [f for f, ok in score.field_scores.items() if not ok]
        assert not failing_fields, (
            f"Fixture {data['fixture_id']!r}: field(s) {failing_fields} did not match. "
            f"Expected: {expected}. "
            f"Got signal: {result.signal.model_dump() if result.signal else None}"
        )

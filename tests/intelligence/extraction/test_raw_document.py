"""
Tests for RawDocument and EntityHints.

Validates:
  1. Valid construction, field defaults, word_count auto-computation.
  2. Field validators: empty title, empty text, invalid source type.
  3. EntityHints optional fields and frozen immutability.
  4. from_text() classmethod convenience constructor.
  5. Round-trip JSON serialization is lossless.
  6. source_url is optional (None for local-file documents).
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

_HINTS = EntityHints(
    asset_id="asset-test-001",
    company_id="company-test-001",
    drug_name="AXD-101",
    indication="Psoriasis",
    ticker="ACME",
)


# ---------------------------------------------------------------------------
# EntityHints
# ---------------------------------------------------------------------------

class TestEntityHints:
    def test_required_fields(self):
        h = EntityHints(asset_id="a", company_id="c")
        assert h.asset_id == "a"
        assert h.company_id == "c"

    def test_optional_defaults_are_none(self):
        h = EntityHints(asset_id="a", company_id="c")
        assert h.drug_name is None
        assert h.indication is None
        assert h.ticker is None
        assert h.nct_id is None

    def test_frozen(self):
        h = EntityHints(asset_id="a", company_id="c")
        with pytest.raises(Exception):
            h.asset_id = "new"  # type: ignore[misc]

    def test_round_trip(self):
        h = EntityHints(
            asset_id="a", company_id="c",
            drug_name="Drug", ticker="TICK", nct_id="NCT12345678",
        )
        h2 = EntityHints.model_validate(h.model_dump())
        assert h2 == h

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            EntityHints(asset_id="a")  # missing company_id


# ---------------------------------------------------------------------------
# RawDocument — construction
# ---------------------------------------------------------------------------

class TestRawDocumentConstruction:
    def test_from_text_basic(self):
        doc = RawDocument.from_text(
            id="doc-001",
            source="press_release",
            title="FDA Approves Drug X",
            raw_text="This is a press release about Drug X approval.",
            entity_hints=_HINTS,
            retrieved_at=_NOW,
        )
        assert doc.id == "doc-001"
        assert doc.source == "press_release"
        assert doc.title == "FDA Approves Drug X"
        assert doc.word_count == 9
        assert doc.source_url is None
        assert doc.published_at is None
        assert doc.retrieved_at == _NOW

    def test_word_count_computed(self):
        doc = RawDocument.from_text(
            id="d", source="manual",
            title="Test",
            raw_text="one two three four five",
            entity_hints=_HINTS,
        )
        assert doc.word_count == 5

    def test_source_url_optional(self):
        doc = RawDocument.from_text(
            id="d", source="manual", title="T", raw_text="text here",
            entity_hints=_HINTS, source_url=None,
        )
        assert doc.source_url is None

    def test_source_url_stored(self):
        doc = RawDocument.from_text(
            id="d", source="press_release", title="T", raw_text="text here",
            entity_hints=_HINTS,
            source_url="https://example.com/pr",
        )
        assert doc.source_url == "https://example.com/pr"

    def test_all_source_types_valid(self):
        valid_types = [
            "press_release", "sec_filing", "clinicaltrials_gov",
            "conference_abstract", "publication", "fda_website",
            "news_aggregator", "manual",
        ]
        for st in valid_types:
            doc = RawDocument.from_text(
                id="d", source=st, title="T", raw_text="text",
                entity_hints=_HINTS,
            )
            assert doc.source == st

    def test_entity_hints_preserved(self):
        doc = RawDocument.from_text(
            id="d", source="manual", title="T", raw_text="text",
            entity_hints=_HINTS,
        )
        assert doc.entity_hints.drug_name == "AXD-101"
        assert doc.entity_hints.ticker == "ACME"

    def test_retrieved_at_defaults_to_now(self):
        before = datetime.now(timezone.utc)
        doc = RawDocument.from_text(
            id="d", source="manual", title="T", raw_text="text",
            entity_hints=_HINTS,
        )
        after = datetime.now(timezone.utc)
        assert before <= doc.retrieved_at <= after

    def test_title_truncated_to_500_chars(self):
        long_title = "A" * 600
        doc = RawDocument.from_text(
            id="d", source="manual", title=long_title, raw_text="text",
            entity_hints=_HINTS,
        )
        assert len(doc.title) == 500

    def test_frozen(self):
        doc = RawDocument.from_text(
            id="d", source="manual", title="T", raw_text="text",
            entity_hints=_HINTS,
        )
        with pytest.raises(Exception):
            doc.title = "new title"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Field validators — rejection cases
# ---------------------------------------------------------------------------

class TestRawDocumentValidation:
    def test_invalid_source_type_raises(self):
        with pytest.raises(ValidationError):
            RawDocument.from_text(
                id="d", source="blog_post",  # not a valid SourceType
                title="T", raw_text="text", entity_hints=_HINTS,
            )

    def test_empty_title_raises(self):
        with pytest.raises(ValidationError):
            RawDocument.from_text(
                id="d", source="manual", title="   ",  # whitespace only
                raw_text="text", entity_hints=_HINTS,
            )

    def test_empty_raw_text_raises(self):
        with pytest.raises(ValidationError):
            RawDocument.from_text(
                id="d", source="manual", title="T",
                raw_text="   ",  # whitespace only
                entity_hints=_HINTS,
            )

    def test_missing_entity_hints_raises(self):
        with pytest.raises((ValidationError, TypeError)):
            RawDocument(
                id="d",
                source="manual",
                title="T",
                raw_text="text",
                retrieved_at=_NOW,
                # entity_hints not provided — required field
            )

    def test_negative_word_count_raises(self):
        with pytest.raises(ValidationError):
            RawDocument(
                id="d",
                source="manual",
                title="T",
                raw_text="text",
                retrieved_at=_NOW,
                entity_hints=_HINTS,
                word_count=-1,
            )


# ---------------------------------------------------------------------------
# Round-trip serialization
# ---------------------------------------------------------------------------

class TestRawDocumentSerialization:
    def test_round_trip_model_dump(self):
        doc = RawDocument.from_text(
            id="doc-rt-001",
            source="fda_website",
            title="FDA Approval Notice",
            raw_text="FDA has approved Drug Y for indication Z.",
            entity_hints=_HINTS,
            retrieved_at=_NOW,
            source_url="https://fda.gov/news/2024",
            published_at=_NOW,
        )
        d = doc.model_dump()
        doc2 = RawDocument.model_validate(d)
        assert doc2.id == doc.id
        assert doc2.source == doc.source
        assert doc2.title == doc.title
        assert doc2.raw_text == doc.raw_text
        assert doc2.word_count == doc.word_count
        assert doc2.entity_hints.asset_id == doc.entity_hints.asset_id

    def test_round_trip_json(self):
        doc = RawDocument.from_text(
            id="doc-json-001",
            source="sec_filing",
            title="10-Q Filing",
            raw_text="Quarterly report content here.",
            entity_hints=EntityHints(
                asset_id="a", company_id="c", ticker="XYZ"
            ),
        )
        json_str = doc.model_dump_json()
        doc2 = RawDocument.model_validate_json(json_str)
        assert doc2 == doc

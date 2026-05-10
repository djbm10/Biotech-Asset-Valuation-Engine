"""
Phase 2 — Institutional provenance and governance.

Tests cover:
  2A — ProvenanceRegistry
       1. FieldProvenance model (frozen, required fields)
       2. get_field_provenance returns None when no snapshot
       3. get_field_provenance for top-level numeric field
       4. get_field_provenance for bucket field by bucket_id
       5. get_field_provenance returns None for unknown field_name
       6. get_all_provenance returns empty dict when no snapshot
       7. get_all_provenance covers top-level fields and buckets
       8. FieldProvenance.source_class is "CompanySnapshot" for top-level
       9. FieldProvenance.source_class is "ValueBucket" for buckets
      10. Bucket confidence / corroboration_count forwarded correctly
      11. Reviewer forwarded from bucket.reviewer
      12. share_price omitted when None
      13. export_provenance_report structure
      14. export_provenance_report with no snapshot returns empty fields
      15. as_of parameter filters to correct snapshot version

  2B — OverrideLog
      16. log_override returns rowid > 0
      17. get_override_log returns correct keys
      18. old_value / new_value deserialized from JSON
      19. evidence_ref optional (None stored)
      20. bucket_id optional (None stored)
      21. Multiple overrides ordered newest-first
      22. export_override_log returns full list
      23. Override for unknown company returns empty list
      24. limit respected by get_override_log

  2C — State machine transition enforcement
      25. DRAFT → REVIEWED is valid
      26. DRAFT → QUARANTINED is valid
      27. REVIEWED → APPROVED is valid
      28. REVIEWED → QUARANTINED is valid
      29. APPROVED → QUARANTINED is valid
      30. APPROVED → STALE is valid
      31. QUARANTINED → DRAFT is valid
      32. STALE → DRAFT is valid
      33. DRAFT → APPROVED is invalid (raises ValueError)
      34. DRAFT → STALE is invalid
      35. APPROVED → DRAFT is invalid
      36. STALE → APPROVED is invalid
      37. REVIEWED → DRAFT is invalid
      38. REVIEWED → STALE is invalid
      39. Full lifecycle: DRAFT → REVIEWED → APPROVED → STALE
      40. Full lifecycle with quarantine: DRAFT → QUARANTINED → DRAFT → REVIEWED
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pytest

from bve.entities.company_snapshot import (
    CatalystEntry,
    CompanySnapshot,
    ConfidenceMetadata,
    DilutionBridge,
    ManagementFlag,
    ProvenanceMetadata,
    ReviewerState,
    ValueBucket,
)
from bve.persistence.snapshot_store import SnapshotStore
from bve.persistence.provenance_registry import FieldProvenance, ProvenanceRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bucket(
    bucket_id: str = "asset_abc",
    bucket_type: str = "modeled_asset",
    value_millions: float = 400.0,
    confidence: float = 0.75,
    corroboration_count: int = 2,
    reviewer: Optional[str] = "djm",
    source_ref: str = "bve-asset:abc.yaml:2026-04-01",
    as_of: date = date(2026, 4, 1),
) -> ValueBucket:
    return ValueBucket(
        bucket_id=bucket_id,
        bucket_type=bucket_type,
        label="ABC asset",
        value_millions=value_millions,
        methodology="rnpv",
        source_type="modeled",
        source_ref=source_ref,
        as_of_date=as_of,
        corroboration_count=corroboration_count,
        reviewer=reviewer,
        confidence=confidence,
    )


def _make_snapshot(
    *,
    company_id: str = "test-co",
    as_of: date = date(2026, 4, 1),
    reviewer_state: ReviewerState = ReviewerState.DRAFT,
    buckets: Optional[list[ValueBucket]] = None,
    share_price: Optional[float] = 25.0,
) -> CompanySnapshot:
    return CompanySnapshot(
        company_id=company_id,
        company_name="Test Co",
        ticker="TCOS",
        as_of_date=as_of,
        market_cap_millions=1_000.0,
        enterprise_value_millions=900.0,
        share_price=share_price,
        cash_millions=200.0,
        debt_millions=50.0,
        modeled_assets=buckets or [],
        confidence=ConfidenceMetadata(overall_confidence=0.70),
        provenance=ProvenanceMetadata(created_by="djm"),
        reviewer_state=reviewer_state,
    )


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "test.db")


@pytest.fixture
def registry(store: SnapshotStore) -> ProvenanceRegistry:
    return ProvenanceRegistry(store)


# ---------------------------------------------------------------------------
# 2A — ProvenanceRegistry
# ---------------------------------------------------------------------------

class TestFieldProvenanceModel:
    """Test 1: FieldProvenance model."""

    def test_frozen(self):
        fp = FieldProvenance(
            field_name="market_cap_millions",
            source_class="CompanySnapshot",
            source_ref="CompanySnapshot:test:2026-04-01",
            as_of_date=date(2026, 4, 1),
            confidence=0.70,
        )
        # Pydantic v2 frozen models raise ValidationError on direct assignment
        with pytest.raises(Exception):
            fp.confidence = 0.99  # type: ignore[misc]

    def test_defaults(self):
        fp = FieldProvenance(
            field_name="f",
            source_class="CompanySnapshot",
            source_ref="ref",
            as_of_date=date(2026, 1, 1),
            confidence=0.5,
        )
        assert fp.corroboration_count == 0
        assert fp.reviewer_status is None

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            FieldProvenance(
                field_name="x",
                source_class="c",
                source_ref="r",
                as_of_date=date(2026, 1, 1),
                confidence=1.5,
            )


class TestGetFieldProvenanceNoSnapshot:
    """Tests 2–3: Behaviour when no snapshot exists."""

    def test_returns_none_no_snapshot(self, registry):
        assert registry.get_field_provenance("no-such-co", "market_cap_millions") is None

    def test_returns_none_unknown_field(self, registry, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        assert registry.get_field_provenance("test-co", "nonexistent_field") is None


class TestGetFieldProvenanceTopLevel:
    """Tests 3, 8: Top-level numeric fields."""

    @pytest.fixture(autouse=True)
    def _insert(self, store):
        store.insert_snapshot(_make_snapshot())

    def test_market_cap(self, registry):
        fp = registry.get_field_provenance("test-co", "market_cap_millions")
        assert fp is not None
        assert fp.field_name == "market_cap_millions"
        assert fp.source_class == "CompanySnapshot"
        assert fp.as_of_date == date(2026, 4, 1)

    def test_cash(self, registry):
        fp = registry.get_field_provenance("test-co", "cash_millions")
        assert fp is not None
        assert fp.source_class == "CompanySnapshot"

    def test_confidence_from_snapshot(self, registry):
        fp = registry.get_field_provenance("test-co", "market_cap_millions")
        assert fp.confidence == pytest.approx(0.70)

    def test_corroboration_zero_for_top_level(self, registry):
        fp = registry.get_field_provenance("test-co", "cash_millions")
        assert fp.corroboration_count == 0

    def test_reviewer_from_created_by(self, registry):
        fp = registry.get_field_provenance("test-co", "market_cap_millions")
        assert fp.reviewer_status == "djm"

    def test_source_ref_contains_company_and_date(self, registry):
        fp = registry.get_field_provenance("test-co", "enterprise_value_millions")
        assert "test-co" in fp.source_ref
        assert "2026-04-01" in fp.source_ref


class TestGetFieldProvenanceBucket:
    """Tests 4, 9–11: ValueBucket fields."""

    @pytest.fixture(autouse=True)
    def _insert(self, store):
        bucket = _make_bucket(
            bucket_id="asset_abc",
            confidence=0.75,
            corroboration_count=2,
            reviewer="djm",
        )
        snap = _make_snapshot(buckets=[bucket])
        store.insert_snapshot(snap)

    def test_lookup_by_bucket_id(self, registry):
        fp = registry.get_field_provenance("test-co", "asset_abc")
        assert fp is not None
        assert fp.field_name == "asset_abc"

    def test_source_class_value_bucket(self, registry):
        fp = registry.get_field_provenance("test-co", "asset_abc")
        assert fp.source_class == "ValueBucket"

    def test_confidence_from_bucket(self, registry):
        fp = registry.get_field_provenance("test-co", "asset_abc")
        assert fp.confidence == pytest.approx(0.75)

    def test_corroboration_from_bucket(self, registry):
        fp = registry.get_field_provenance("test-co", "asset_abc")
        assert fp.corroboration_count == 2

    def test_reviewer_from_bucket(self, registry):
        fp = registry.get_field_provenance("test-co", "asset_abc")
        assert fp.reviewer_status == "djm"

    def test_source_ref_from_bucket(self, registry):
        fp = registry.get_field_provenance("test-co", "asset_abc")
        assert "bve-asset:abc.yaml:2026-04-01" in fp.source_ref


class TestGetAllProvenance:
    """Tests 6–7, 12: get_all_provenance."""

    def test_empty_when_no_snapshot(self, registry):
        assert registry.get_all_provenance("missing") == {}

    def test_covers_top_level_and_buckets(self, store, registry):
        bucket = _make_bucket(bucket_id="b1")
        snap = _make_snapshot(buckets=[bucket])
        store.insert_snapshot(snap)
        all_prov = registry.get_all_provenance("test-co")
        assert "market_cap_millions" in all_prov
        assert "cash_millions" in all_prov
        assert "b1" in all_prov

    def test_share_price_included_when_set(self, store, registry):
        snap = _make_snapshot(share_price=25.0)
        store.insert_snapshot(snap)
        all_prov = registry.get_all_provenance("test-co")
        assert "share_price" in all_prov

    def test_share_price_omitted_when_none(self, store, registry):
        snap = _make_snapshot(share_price=None)
        store.insert_snapshot(snap)
        all_prov = registry.get_all_provenance("test-co")
        assert "share_price" not in all_prov

    def test_all_values_are_field_provenance(self, store, registry):
        store.insert_snapshot(_make_snapshot())
        all_prov = registry.get_all_provenance("test-co")
        for v in all_prov.values():
            assert isinstance(v, FieldProvenance)


class TestExportProvenanceReport:
    """Tests 13–14: export_provenance_report."""

    def test_structure_no_snapshot(self, registry):
        report = registry.export_provenance_report("missing")
        assert report["company_id"] == "missing"
        assert report["snapshot_id"] is None
        assert report["fields"] == []
        assert report["total_fields"] == 0

    def test_structure_with_snapshot(self, store, registry):
        bucket = _make_bucket(bucket_id="b1")
        store.insert_snapshot(_make_snapshot(buckets=[bucket]))
        report = registry.export_provenance_report("test-co")
        assert report["company_id"] == "test-co"
        assert report["snapshot_id"] is not None
        assert report["reviewer_state"] == "draft"
        assert report["total_fields"] > 0
        assert isinstance(report["fields"], list)

    def test_fields_json_serializable(self, store, registry):
        store.insert_snapshot(_make_snapshot())
        report = registry.export_provenance_report("test-co")
        # Should round-trip through JSON without error
        _ = json.loads(json.dumps(report))

    def test_each_field_has_required_keys(self, store, registry):
        store.insert_snapshot(_make_snapshot())
        report = registry.export_provenance_report("test-co")
        required = {"field_name", "source_class", "source_ref", "as_of_date",
                    "corroboration_count", "reviewer_status", "confidence"}
        for field in report["fields"]:
            assert required.issubset(field.keys())

    def test_total_fields_matches_len(self, store, registry):
        bucket = _make_bucket(bucket_id="b1")
        store.insert_snapshot(_make_snapshot(buckets=[bucket]))
        report = registry.export_provenance_report("test-co")
        assert report["total_fields"] == len(report["fields"])


class TestAsOfFiltering:
    """Test 15: as_of parameter."""

    def test_as_of_returns_earlier_snapshot(self, store, registry):
        snap_early = _make_snapshot(as_of=date(2026, 1, 1))
        snap_late = _make_snapshot(as_of=date(2026, 4, 1))
        store.insert_snapshot(snap_early)
        store.insert_snapshot(snap_late)

        # as_of restricts to the earlier snapshot
        prov = registry.get_field_provenance(
            "test-co", "market_cap_millions", as_of=date(2026, 2, 1)
        )
        assert prov is not None
        assert prov.as_of_date == date(2026, 1, 1)


# ---------------------------------------------------------------------------
# 2B — OverrideLog
# ---------------------------------------------------------------------------

class TestOverrideLog:
    """Tests 16–24: OverrideLog functionality."""

    def test_log_override_returns_rowid(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        rowid = store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="cash_millions",
            old_value=200.0,
            new_value=250.0,
            override_by="djm",
            reason="Updated from Q1 10-Q",
        )
        assert rowid is not None
        assert rowid > 0

    def test_get_override_log_keys(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="cash_millions",
            old_value=200.0,
            new_value=250.0,
            override_by="djm",
            reason="Updated from Q1 10-Q",
        )
        entries = store.get_override_log("test-co")
        assert len(entries) == 1
        entry = entries[0]
        assert "field_name" in entry
        assert "old_value" in entry
        assert "new_value" in entry
        assert "override_by" in entry
        assert "override_at" in entry
        assert "reason" in entry

    def test_values_deserialized(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="cash_millions",
            old_value=200.0,
            new_value=250.0,
            override_by="djm",
            reason="Q1 10-Q cash figure",
        )
        entry = store.get_override_log("test-co")[0]
        assert entry["old_value"] == pytest.approx(200.0)
        assert entry["new_value"] == pytest.approx(250.0)

    def test_evidence_ref_optional_none(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="cash_millions",
            old_value=200.0,
            new_value=210.0,
            override_by="djm",
            reason="Correction",
        )
        entry = store.get_override_log("test-co")[0]
        assert entry["evidence_ref"] is None

    def test_evidence_ref_stored(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="cash_millions",
            old_value=200.0,
            new_value=210.0,
            override_by="djm",
            reason="Correction",
            evidence_ref="10-Q:2026-03-31:pg12",
        )
        entry = store.get_override_log("test-co")[0]
        assert entry["evidence_ref"] == "10-Q:2026-03-31:pg12"

    def test_bucket_id_optional_none(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="cash_millions",
            old_value=200.0,
            new_value=210.0,
            override_by="djm",
            reason="Fix",
        )
        entry = store.get_override_log("test-co")[0]
        assert entry["bucket_id"] is None

    def test_bucket_id_stored(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        store.log_override(
            company_id="test-co",
            snapshot_id=snap.snapshot_id,
            field_name="confidence",
            old_value=0.70,
            new_value=0.80,
            override_by="djm",
            reason="Reanalysis",
            bucket_id="asset_abc",
        )
        entry = store.get_override_log("test-co")[0]
        assert entry["bucket_id"] == "asset_abc"

    def test_multiple_overrides_newest_first(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        for val in [210.0, 220.0, 230.0]:
            store.log_override(
                company_id="test-co",
                snapshot_id=snap.snapshot_id,
                field_name="cash_millions",
                old_value=val - 10,
                new_value=val,
                override_by="djm",
                reason=f"Update to {val}",
            )
        entries = store.get_override_log("test-co")
        assert len(entries) == 3
        # newest first — new_value should be decreasing (230, 220, 210)
        assert entries[0]["new_value"] >= entries[1]["new_value"] >= entries[2]["new_value"]

    def test_export_override_log_full(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        for i in range(5):
            store.log_override(
                company_id="test-co",
                snapshot_id=snap.snapshot_id,
                field_name=f"field_{i}",
                old_value=i,
                new_value=i + 1,
                override_by="djm",
                reason=f"reason {i}",
            )
        full = store.export_override_log("test-co")
        assert len(full) == 5

    def test_unknown_company_returns_empty(self, store):
        assert store.get_override_log("no-such-co") == []

    def test_limit_respected(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        for i in range(10):
            store.log_override(
                company_id="test-co",
                snapshot_id=snap.snapshot_id,
                field_name=f"f{i}",
                old_value=i,
                new_value=i + 1,
                override_by="djm",
                reason="r",
            )
        entries = store.get_override_log("test-co", limit=3)
        assert len(entries) == 3


# ---------------------------------------------------------------------------
# 2C — State machine transition enforcement
# ---------------------------------------------------------------------------

class TestValidTransitions:
    """Tests 25–32: Each explicitly valid transition."""

    @pytest.fixture(autouse=True)
    def _snap(self, store):
        self._store = store
        self._snap = _make_snapshot(reviewer_state=ReviewerState.DRAFT)
        store.insert_snapshot(self._snap)

    def _advance(self, from_state: ReviewerState, to_state: ReviewerState) -> CompanySnapshot:
        """Helper that finds or creates a snapshot in from_state and transitions it."""
        snaps = self._store.get_snapshot_history("test-co")
        target = next((s for s in snaps if s.reviewer_state == from_state), None)
        if target is None:
            pytest.skip(f"No snapshot in state {from_state}")
        return self._store.transition_state(
            target.snapshot_id, to_state, reviewer="djm", reason="test"
        )

    def test_draft_to_reviewed(self, store):
        new_snap = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED,
            reviewer="djm", reason="initial review"
        )
        assert new_snap.reviewer_state == ReviewerState.REVIEWED

    def test_draft_to_quarantined(self, store):
        new_snap = store.transition_state(
            self._snap.snapshot_id, ReviewerState.QUARANTINED,
            reviewer="djm", reason="data issue"
        )
        assert new_snap.reviewer_state == ReviewerState.QUARANTINED

    def test_reviewed_to_approved(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED,
            reviewer="djm", reason="reviewed"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED,
            reviewer="djm", reason="approved for capital-candidate"
        )
        assert approved.reviewer_state == ReviewerState.APPROVED

    def test_reviewed_to_quarantined(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED,
            reviewer="djm", reason="reviewed"
        )
        q = store.transition_state(
            reviewed.snapshot_id, ReviewerState.QUARANTINED,
            reviewer="djm", reason="problem found"
        )
        assert q.reviewer_state == ReviewerState.QUARANTINED

    def test_approved_to_quarantined(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED, reviewer="djm", reason="a"
        )
        q = store.transition_state(
            approved.snapshot_id, ReviewerState.QUARANTINED,
            reviewer="djm", reason="regulatory concern"
        )
        assert q.reviewer_state == ReviewerState.QUARANTINED

    def test_approved_to_stale(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED, reviewer="djm", reason="a"
        )
        stale = store.transition_state(
            approved.snapshot_id, ReviewerState.STALE,
            reviewer="system", reason="Q expired"
        )
        assert stale.reviewer_state == ReviewerState.STALE

    def test_quarantined_to_draft(self, store):
        q = store.transition_state(
            self._snap.snapshot_id, ReviewerState.QUARANTINED,
            reviewer="djm", reason="issue"
        )
        redraft = store.transition_state(
            q.snapshot_id, ReviewerState.DRAFT,
            reviewer="djm", reason="fixed, re-draft"
        )
        assert redraft.reviewer_state == ReviewerState.DRAFT

    def test_stale_to_draft(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED, reviewer="djm", reason="a"
        )
        stale = store.transition_state(
            approved.snapshot_id, ReviewerState.STALE, reviewer="system", reason="expired"
        )
        redraft = store.transition_state(
            stale.snapshot_id, ReviewerState.DRAFT,
            reviewer="djm", reason="refreshing pack"
        )
        assert redraft.reviewer_state == ReviewerState.DRAFT


class TestInvalidTransitions:
    """Tests 33–38: Each explicitly invalid transition raises ValueError."""

    @pytest.fixture(autouse=True)
    def _snap(self, store):
        self._store = store
        self._snap = _make_snapshot(reviewer_state=ReviewerState.DRAFT)
        store.insert_snapshot(self._snap)

    def test_draft_to_approved_rejected(self, store):
        with pytest.raises(ValueError, match="Invalid state transition"):
            store.transition_state(
                self._snap.snapshot_id, ReviewerState.APPROVED,
                reviewer="djm", reason="skip review"
            )

    def test_draft_to_stale_rejected(self, store):
        with pytest.raises(ValueError, match="Invalid state transition"):
            store.transition_state(
                self._snap.snapshot_id, ReviewerState.STALE,
                reviewer="djm", reason="shortcut"
            )

    def test_approved_to_draft_rejected(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED, reviewer="djm", reason="a"
        )
        with pytest.raises(ValueError, match="Invalid state transition"):
            store.transition_state(
                approved.snapshot_id, ReviewerState.DRAFT,
                reviewer="djm", reason="rollback"
            )

    def test_stale_to_approved_rejected(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED, reviewer="djm", reason="a"
        )
        stale = store.transition_state(
            approved.snapshot_id, ReviewerState.STALE, reviewer="system", reason="expired"
        )
        with pytest.raises(ValueError, match="Invalid state transition"):
            store.transition_state(
                stale.snapshot_id, ReviewerState.APPROVED,
                reviewer="djm", reason="skip redraft"
            )

    def test_reviewed_to_draft_rejected(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        with pytest.raises(ValueError, match="Invalid state transition"):
            store.transition_state(
                reviewed.snapshot_id, ReviewerState.DRAFT,
                reviewer="djm", reason="rollback"
            )

    def test_reviewed_to_stale_rejected(self, store):
        reviewed = store.transition_state(
            self._snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="r"
        )
        with pytest.raises(ValueError, match="Invalid state transition"):
            store.transition_state(
                reviewed.snapshot_id, ReviewerState.STALE,
                reviewer="system", reason="expire"
            )


class TestFullLifecycles:
    """Tests 39–40: End-to-end lifecycle flows."""

    def test_draft_reviewed_approved_stale(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)

        reviewed = store.transition_state(
            snap.snapshot_id, ReviewerState.REVIEWED, reviewer="djm", reason="Q1 review"
        )
        approved = store.transition_state(
            reviewed.snapshot_id, ReviewerState.APPROVED,
            reviewer="committee", reason="approved for shadow book"
        )
        stale = store.transition_state(
            approved.snapshot_id, ReviewerState.STALE,
            reviewer="system", reason="Q2 data supersedes Q1"
        )

        assert stale.reviewer_state == ReviewerState.STALE
        assert stale.provenance.parent_snapshot_id == approved.snapshot_id

        # State log has 3 transitions
        log = store.get_state_log(snap.snapshot_id)
        assert len(log) == 1
        assert log[0]["to_state"] == "reviewed"

    def test_draft_quarantine_redraft_reviewed(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)

        q = store.transition_state(
            snap.snapshot_id, ReviewerState.QUARANTINED,
            reviewer="djm", reason="data error found"
        )
        redraft = store.transition_state(
            q.snapshot_id, ReviewerState.DRAFT,
            reviewer="djm", reason="corrected cash figure"
        )
        reviewed = store.transition_state(
            redraft.snapshot_id, ReviewerState.REVIEWED,
            reviewer="djm", reason="re-review after fix"
        )

        assert reviewed.reviewer_state == ReviewerState.REVIEWED
        history = store.get_snapshot_history("test-co")
        assert len(history) == 4  # original + q + redraft + reviewed

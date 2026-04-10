"""
Tests for Phase 1 CompanySnapshot layer.

Covers:
- ReviewerState enum
- ValueBucket model
- DilutionBridge model and computed properties
- CatalystEntry / ManagementFlag models
- ConfidenceMetadata / ProvenanceMetadata models
- CompanySnapshot model, validators, and computed properties
- SnapshotStore: insert, retrieve, history, state transitions, staleness
- snapshot_bridge: load_underwriting_pack
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_bucket(
    bucket_id: str = "b1",
    bucket_type: str = "modeled_asset",
    value_millions: float = 500.0,
    confidence: float = 0.80,
    source_type: str = "modeled",
    methodology: str = "rnpv",
) -> "ValueBucket":
    from bve.entities.company_snapshot import ValueBucket
    return ValueBucket(
        bucket_id=bucket_id,
        bucket_type=bucket_type,
        label="Test asset",
        value_millions=value_millions,
        methodology=methodology,
        source_type=source_type,
        source_ref="test:ref",
        as_of_date=date(2026, 4, 1),
        confidence=confidence,
    )


def _make_confidence(overall: float = 0.80) -> "ConfidenceMetadata":
    from bve.entities.company_snapshot import ConfidenceMetadata
    return ConfidenceMetadata(overall_confidence=overall)


def _make_provenance(pack_version: int = 0) -> "ProvenanceMetadata":
    from bve.entities.company_snapshot import ProvenanceMetadata
    return ProvenanceMetadata(pack_version=pack_version, created_by="test")


def _make_snapshot(
    company_id: str = "test-co",
    ticker: str = "TEST",
    market_cap: float = 1000.0,
    cash: float = 200.0,
    debt: float = 0.0,
    reviewer_state: str = "draft",
    pack_version: int = 0,
    modeled_assets: list | None = None,
    dilution_bridge=None,
    stale_since=None,
    stale_reason=None,
) -> "CompanySnapshot":
    from bve.entities.company_snapshot import CompanySnapshot, ReviewerState
    return CompanySnapshot(
        company_id=company_id,
        company_name="Test Company Inc.",
        ticker=ticker,
        as_of_date=date(2026, 4, 1),
        market_cap_millions=market_cap,
        enterprise_value_millions=market_cap - cash + debt,
        cash_millions=cash,
        debt_millions=debt,
        modeled_assets=modeled_assets or [],
        confidence=_make_confidence(),
        provenance=_make_provenance(pack_version),
        reviewer_state=ReviewerState(reviewer_state),
        dilution_bridge=dilution_bridge,
        stale_since=stale_since,
        stale_reason=stale_reason,
    )


# ---------------------------------------------------------------------------
# ReviewerState
# ---------------------------------------------------------------------------

class TestReviewerState:
    def test_all_states_exist(self):
        from bve.entities.company_snapshot import ReviewerState
        assert ReviewerState.DRAFT.value == "draft"
        assert ReviewerState.REVIEWED.value == "reviewed"
        assert ReviewerState.APPROVED.value == "approved"
        assert ReviewerState.QUARANTINED.value == "quarantined"
        assert ReviewerState.STALE.value == "stale"

    def test_string_enum(self):
        from bve.entities.company_snapshot import ReviewerState
        assert ReviewerState("draft") is ReviewerState.DRAFT
        assert ReviewerState("approved") is ReviewerState.APPROVED

    def test_five_states(self):
        from bve.entities.company_snapshot import ReviewerState
        assert len(ReviewerState) == 5


# ---------------------------------------------------------------------------
# ValueBucket
# ---------------------------------------------------------------------------

class TestValueBucket:
    def test_minimal_construction(self):
        b = _make_bucket()
        assert b.bucket_id == "b1"
        assert b.value_millions == 500.0
        assert b.confidence == 0.80

    def test_frozen(self):
        b = _make_bucket()
        with pytest.raises(Exception):
            b.value_millions = 999.0

    def test_confidence_lower_bound(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _make_bucket(confidence=-0.01)

    def test_confidence_upper_bound(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            _make_bucket(confidence=1.01)

    def test_corroboration_defaults(self):
        b = _make_bucket()
        assert b.corroboration_count == 0
        assert b.corroboration_refs == []

    def test_corroboration_with_refs(self):
        from bve.entities.company_snapshot import ValueBucket
        b = ValueBucket(
            bucket_id="b2",
            bucket_type="platform",
            label="Platform",
            value_millions=100.0,
            methodology="analyst_estimate",
            source_type="analyst_bridge",
            source_ref="pack:test",
            as_of_date=date(2026, 4, 1),
            confidence=0.65,
            corroboration_count=2,
            corroboration_refs=["ref1", "ref2"],
        )
        assert b.corroboration_count == 2
        assert len(b.corroboration_refs) == 2

    def test_all_methodology_literals(self):
        for m in ["rnpv", "dcf", "market_comp", "precedent_transaction",
                  "rule_of_thumb", "analyst_estimate", "balance_sheet"]:
            b = _make_bucket(methodology=m)
            assert b.methodology == m

    def test_all_source_types(self):
        for s in ["modeled", "sec_filing", "contractual", "company_disclosure",
                  "investor_day", "analyst_bridge", "inferred"]:
            b = _make_bucket(source_type=s)
            assert b.source_type == s

    def test_all_bucket_types(self):
        for bt in ["modeled_asset", "net_cash", "platform", "unmodeled_pipeline",
                   "royalty", "dilution_reserve"]:
            b = _make_bucket(bucket_type=bt)
            assert b.bucket_type == bt


# ---------------------------------------------------------------------------
# DilutionBridge
# ---------------------------------------------------------------------------

class TestDilutionBridge:
    def test_fully_diluted_no_extras(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=100.0)
        assert bridge.fully_diluted_shares_millions == 100.0

    def test_expected_dilution(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=100.0, expected_dilution_pct=0.10)
        assert bridge.fully_diluted_shares_millions == pytest.approx(110.0)

    def test_warrants_add(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=100.0, warrant_shares_millions=5.0)
        assert bridge.fully_diluted_shares_millions == pytest.approx(105.0)

    def test_convertibles_add(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=100.0, convertible_shares_millions=3.0)
        assert bridge.fully_diluted_shares_millions == pytest.approx(103.0)

    def test_all_together(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(
            current_shares_millions=100.0,
            expected_dilution_pct=0.10,
            warrant_shares_millions=5.0,
            convertible_shares_millions=3.0,
        )
        # 100 + 10 (dilution) + 5 (warrants) + 3 (convertibles) = 118
        assert bridge.fully_diluted_shares_millions == pytest.approx(118.0)

    def test_dilution_multiple(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=100.0, expected_dilution_pct=0.20)
        assert bridge.dilution_multiple == pytest.approx(1.20)

    def test_no_dilution_multiple_is_one(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=50.0)
        assert bridge.dilution_multiple == pytest.approx(1.0)

    def test_validation_rejects_zero_shares(self):
        from bve.entities.company_snapshot import DilutionBridge
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DilutionBridge(current_shares_millions=0.0)

    def test_frozen(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(current_shares_millions=50.0)
        with pytest.raises(Exception):
            bridge.current_shares_millions = 99.0


# ---------------------------------------------------------------------------
# CatalystEntry
# ---------------------------------------------------------------------------

class TestCatalystEntry:
    def test_minimal(self):
        from bve.entities.company_snapshot import CatalystEntry
        c = CatalystEntry(description="Ph3 readout")
        assert c.description == "Ph3 readout"
        assert c.catalyst_type == "readout"

    def test_all_types(self):
        from bve.entities.company_snapshot import CatalystEntry
        for ct in ["readout", "fda_action", "partnership", "milestone", "financing", "conference", "other"]:
            c = CatalystEntry(description="x", catalyst_type=ct)
            assert c.catalyst_type == ct

    def test_probability_bounds(self):
        from bve.entities.company_snapshot import CatalystEntry
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            CatalystEntry(description="x", probability_positive=1.5)
        with pytest.raises(ValidationError):
            CatalystEntry(description="x", probability_positive=-0.1)


# ---------------------------------------------------------------------------
# ManagementFlag
# ---------------------------------------------------------------------------

class TestManagementFlag:
    def test_construction(self):
        from bve.entities.company_snapshot import ManagementFlag
        f = ManagementFlag(
            flag_type="ceo_change",
            flagged_date=date(2026, 1, 15),
            severity="watch",
            description="CEO transition",
        )
        assert f.flag_type == "ceo_change"
        assert not f.resolved

    def test_all_severities(self):
        from bve.entities.company_snapshot import ManagementFlag
        for sev in ["info", "watch", "warning", "critical"]:
            f = ManagementFlag(
                flag_type="restatement",
                flagged_date=date(2026, 1, 1),
                severity=sev,
                description="test",
            )
            assert f.severity == sev


# ---------------------------------------------------------------------------
# ConfidenceMetadata
# ---------------------------------------------------------------------------

class TestConfidenceMetadata:
    def test_bounds(self):
        from bve.entities.company_snapshot import ConfidenceMetadata
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ConfidenceMetadata(overall_confidence=1.1)
        with pytest.raises(ValidationError):
            ConfidenceMetadata(overall_confidence=-0.1)

    def test_defaults(self):
        from bve.entities.company_snapshot import ConfidenceMetadata
        c = ConfidenceMetadata(overall_confidence=0.70)
        assert c.modeled_asset_coverage_pct == 0.0
        assert c.corroboration_score == 0.0
        assert c.bucket_confidence_min is None


# ---------------------------------------------------------------------------
# ProvenanceMetadata
# ---------------------------------------------------------------------------

class TestProvenanceMetadata:
    def test_defaults(self):
        from bve.entities.company_snapshot import ProvenanceMetadata
        p = ProvenanceMetadata()
        assert p.pack_version == 0
        assert p.created_by == "system"

    def test_pack_version_non_negative(self):
        from bve.entities.company_snapshot import ProvenanceMetadata
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ProvenanceMetadata(pack_version=-1)

    def test_parent_snapshot_id(self):
        from bve.entities.company_snapshot import ProvenanceMetadata
        p = ProvenanceMetadata(parent_snapshot_id="abc-123")
        assert p.parent_snapshot_id == "abc-123"


# ---------------------------------------------------------------------------
# CompanySnapshot
# ---------------------------------------------------------------------------

class TestCompanySnapshot:
    def test_minimal_construction(self):
        s = _make_snapshot()
        assert s.company_id == "test-co"
        assert s.ticker == "TEST"

    def test_snapshot_id_is_uuid(self):
        import uuid
        s = _make_snapshot()
        uuid.UUID(s.snapshot_id)  # should not raise

    def test_unique_ids_per_instance(self):
        s1 = _make_snapshot()
        s2 = _make_snapshot()
        assert s1.snapshot_id != s2.snapshot_id

    def test_frozen(self):
        s = _make_snapshot()
        with pytest.raises(Exception):
            s.market_cap_millions = 9999.0

    def test_net_cash(self):
        s = _make_snapshot(cash=300.0, debt=50.0)
        assert s.net_cash_millions == pytest.approx(250.0)

    def test_modeled_asset_value_sums(self):
        b1 = _make_bucket("b1", value_millions=400.0)
        b2 = _make_bucket("b2", value_millions=200.0)
        s = _make_snapshot(modeled_assets=[b1, b2])
        assert s.modeled_asset_value_millions == pytest.approx(600.0)

    def test_platform_value_none_returns_zero(self):
        s = _make_snapshot()
        assert s.platform_value_millions == 0.0

    def test_unmodeled_pipeline_none_returns_zero(self):
        s = _make_snapshot()
        assert s.unmodeled_pipeline_value_millions == 0.0

    def test_sotp_equity_value_decomposition(self):
        b = _make_bucket("b1", value_millions=800.0)
        s = _make_snapshot(cash=200.0, debt=0.0, modeled_assets=[b])
        # net_cash=200 + modeled=800 + platform=0 + unmodeled=0 + royalty=0 - dilution=0 = 1000
        assert s.sotp_equity_value_millions == pytest.approx(1000.0)

    def test_sotp_discount_positive_undervalued(self):
        b = _make_bucket("b1", value_millions=1200.0)
        s = _make_snapshot(market_cap=1000.0, cash=200.0, modeled_assets=[b])
        # sotp = 200 + 1200 = 1400; market = 1000; discount = 0.40
        assert s.sotp_discount == pytest.approx(0.40)

    def test_sotp_discount_negative_overvalued(self):
        b = _make_bucket("b1", value_millions=400.0)
        s = _make_snapshot(market_cap=1000.0, cash=200.0, modeled_assets=[b])
        # sotp = 200 + 400 = 600; market = 1000; discount = -0.40
        assert s.sotp_discount == pytest.approx(-0.40)

    def test_sotp_discount_zero_market_cap(self):
        s = _make_snapshot(market_cap=0.0)
        assert s.sotp_discount == 0.0

    def test_all_buckets_aggregation(self):
        from bve.entities.company_snapshot import CompanySnapshot, ConfidenceMetadata, ProvenanceMetadata, ReviewerState, ValueBucket
        ma = _make_bucket("ma1", "modeled_asset")
        ro = _make_bucket("ro1", "royalty")
        pl = _make_bucket("pl1", "platform")
        un = _make_bucket("un1", "unmodeled_pipeline")
        s = CompanySnapshot(
            company_id="test",
            company_name="Test",
            ticker="TST",
            as_of_date=date(2026, 4, 1),
            market_cap_millions=1000.0,
            enterprise_value_millions=800.0,
            cash_millions=200.0,
            modeled_assets=[ma],
            royalty_streams=[ro],
            platform_value=pl,
            unmodeled_pipeline=un,
            confidence=_make_confidence(),
            provenance=_make_provenance(),
            reviewer_state=ReviewerState.DRAFT,
        )
        assert len(s.all_buckets) == 4

    def test_is_capital_candidate_approved_with_pack(self):
        from bve.entities.company_snapshot import CompanySnapshot, ConfidenceMetadata, ProvenanceMetadata, ReviewerState
        s = CompanySnapshot(
            company_id="test",
            company_name="Test",
            ticker="TST",
            as_of_date=date(2026, 4, 1),
            market_cap_millions=1000.0,
            enterprise_value_millions=800.0,
            cash_millions=200.0,
            confidence=_make_confidence(),
            provenance=_make_provenance(pack_version=1),
            reviewer_state=ReviewerState.APPROVED,
        )
        assert s.is_capital_candidate_eligible

    def test_is_capital_candidate_draft_returns_false(self):
        s = _make_snapshot(reviewer_state="draft", pack_version=0)
        assert not s.is_capital_candidate_eligible

    def test_is_capital_candidate_stale_returns_false(self):
        from bve.entities.company_snapshot import CompanySnapshot, ConfidenceMetadata, ProvenanceMetadata, ReviewerState
        s = CompanySnapshot(
            company_id="test",
            company_name="Test",
            ticker="TST",
            as_of_date=date(2026, 4, 1),
            market_cap_millions=1000.0,
            enterprise_value_millions=800.0,
            cash_millions=200.0,
            confidence=_make_confidence(),
            provenance=_make_provenance(pack_version=1),
            reviewer_state=ReviewerState.APPROVED,
            stale_since=date(2026, 3, 1),
            stale_reason="missed event",
        )
        assert not s.is_capital_candidate_eligible

    def test_validator_approved_requires_pack_version_1(self):
        from bve.entities.company_snapshot import ReviewerState
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="pack_version"):
            _make_snapshot(reviewer_state="approved", pack_version=0)

    def test_validator_stale_requires_reason(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError, match="stale_reason"):
            _make_snapshot(stale_since=date(2026, 3, 1), stale_reason=None)

    def test_dilution_reserve_from_bridge(self):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(
            current_shares_millions=100.0,
            expected_dilution_pct=0.10,  # 10 new shares
        )
        # market_cap=1000, price=10/share; 10 new shares * 10 = 100 reserve
        s = _make_snapshot(market_cap=1000.0, dilution_bridge=bridge)
        assert s.dilution_reserve_millions == pytest.approx(100.0)

    def test_dilution_reserve_zero_no_bridge(self):
        s = _make_snapshot()
        assert s.dilution_reserve_millions == 0.0

    def test_critical_management_flags(self):
        from bve.entities.company_snapshot import CompanySnapshot, ManagementFlag, ConfidenceMetadata, ProvenanceMetadata, ReviewerState
        f_critical = ManagementFlag(
            flag_type="going_concern",
            flagged_date=date(2026, 1, 1),
            severity="critical",
            description="Going concern warning",
        )
        f_info = ManagementFlag(
            flag_type="ceo_change",
            flagged_date=date(2026, 1, 1),
            severity="info",
            description="CEO change",
        )
        s = CompanySnapshot(
            company_id="test",
            company_name="Test",
            ticker="TST",
            as_of_date=date(2026, 4, 1),
            market_cap_millions=100.0,
            enterprise_value_millions=80.0,
            cash_millions=20.0,
            management_flags=[f_critical, f_info],
            confidence=_make_confidence(),
            provenance=_make_provenance(),
            reviewer_state=ReviewerState.DRAFT,
        )
        assert len(s.critical_management_flags) == 1
        assert s.critical_management_flags[0].flag_type == "going_concern"


# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------

class TestSnapshotStore:

    @pytest.fixture
    def store(self, tmp_path):
        from bve.persistence.snapshot_store import SnapshotStore
        db = tmp_path / "test_snapshots.db"
        s = SnapshotStore(db)
        yield s
        s.close()

    def test_init_creates_db_file(self, tmp_path):
        from bve.persistence.snapshot_store import SnapshotStore
        db = tmp_path / "snapshots.db"
        store = SnapshotStore(db)
        store.close()
        assert db.exists()

    def test_insert_and_retrieve(self, store):
        snap = _make_snapshot()
        sid = store.insert_snapshot(snap)
        retrieved = store.get_snapshot(sid)
        assert retrieved is not None
        assert retrieved.company_id == snap.company_id
        assert retrieved.ticker == snap.ticker
        assert retrieved.snapshot_id == sid

    def test_insert_preserves_market_cap(self, store):
        snap = _make_snapshot(market_cap=2500.0)
        sid = store.insert_snapshot(snap)
        retrieved = store.get_snapshot(sid)
        assert retrieved.market_cap_millions == pytest.approx(2500.0)

    def test_get_nonexistent_returns_none(self, store):
        assert store.get_snapshot("does-not-exist") is None

    def test_get_latest_snapshot(self, store):
        s1 = _make_snapshot()
        import uuid
        from bve.entities.company_snapshot import CompanySnapshot
        s2 = CompanySnapshot(**{**s1.model_dump(), "snapshot_id": str(uuid.uuid4()),
                                 "as_of_date": date(2026, 5, 1), "market_cap_millions": 1200.0})
        store.insert_snapshot(s1)
        store.insert_snapshot(s2)
        latest = store.get_latest_snapshot("test-co")
        assert latest is not None
        assert latest.market_cap_millions == pytest.approx(1200.0)

    def test_get_latest_snapshot_as_of_filter(self, store):
        import uuid
        s1 = _make_snapshot()  # as_of_date = 2026-04-01
        s2 = CompanySnapshot(
            **{**s1.model_dump(), "snapshot_id": str(uuid.uuid4()),
               "as_of_date": date(2026, 5, 1), "market_cap_millions": 1200.0}
        ) if False else None  # build properly below

        from bve.entities.company_snapshot import CompanySnapshot
        s2 = CompanySnapshot(**{
            **s1.model_dump(),
            "snapshot_id": str(uuid.uuid4()),
            "as_of_date": date(2026, 5, 1),
            "market_cap_millions": 1200.0,
        })
        store.insert_snapshot(s1)
        store.insert_snapshot(s2)
        # As of April 15 should return April 1 snapshot
        at_april = store.get_latest_snapshot("test-co", as_of=date(2026, 4, 15))
        assert at_april is not None
        assert at_april.market_cap_millions == pytest.approx(1000.0)

    def test_get_snapshot_history_ordered(self, store):
        import uuid
        from bve.entities.company_snapshot import CompanySnapshot
        s1 = _make_snapshot()
        s2 = CompanySnapshot(**{**s1.model_dump(), "snapshot_id": str(uuid.uuid4()),
                                 "as_of_date": date(2026, 5, 1)})
        s3 = CompanySnapshot(**{**s1.model_dump(), "snapshot_id": str(uuid.uuid4()),
                                 "as_of_date": date(2026, 3, 1)})
        store.insert_snapshot(s1)
        store.insert_snapshot(s2)
        store.insert_snapshot(s3)
        history = store.get_snapshot_history("test-co")
        assert history[0].as_of_date > history[1].as_of_date

    def test_list_snapshots_by_reviewer_state(self, store):
        from bve.entities.company_snapshot import ReviewerState
        draft = _make_snapshot()
        store.insert_snapshot(draft)
        results = store.list_snapshots(reviewer_state=ReviewerState.DRAFT)
        assert len(results) >= 1
        assert all(r.reviewer_state == ReviewerState.DRAFT for r in results)

    def test_get_capital_candidates_only_approved(self, store):
        from bve.entities.company_snapshot import CompanySnapshot, ReviewerState
        draft = _make_snapshot()
        approved = CompanySnapshot(
            company_id="approved-co",
            company_name="Approved Co",
            ticker="APC",
            as_of_date=date(2026, 4, 1),
            market_cap_millions=500.0,
            enterprise_value_millions=300.0,
            cash_millions=200.0,
            confidence=_make_confidence(),
            provenance=_make_provenance(pack_version=1),
            reviewer_state=ReviewerState.APPROVED,
        )
        store.insert_snapshot(draft)
        store.insert_snapshot(approved)
        candidates = store.get_capital_candidates()
        tickers = [c.ticker for c in candidates]
        assert "APC" in tickers
        assert "TEST" not in tickers

    def test_transition_state_creates_new_version(self, store):
        from bve.entities.company_snapshot import ReviewerState
        snap = _make_snapshot()
        old_id = store.insert_snapshot(snap)
        new_snap = store.transition_state(old_id, ReviewerState.REVIEWED,
                                          reviewer="djm", reason="First review")
        assert new_snap.reviewer_state == ReviewerState.REVIEWED
        assert new_snap.snapshot_id != old_id
        assert new_snap.provenance.parent_snapshot_id == old_id
        # old snapshot should still exist and be unchanged
        old = store.get_snapshot(old_id)
        assert old.reviewer_state == ReviewerState.DRAFT

    def test_transition_state_logs_audit_trail(self, store):
        from bve.entities.company_snapshot import ReviewerState
        snap = _make_snapshot()
        old_id = store.insert_snapshot(snap)
        store.transition_state(old_id, ReviewerState.REVIEWED,
                               reviewer="djm", reason="Test review")
        log = store.get_state_log(old_id)
        assert len(log) == 1
        assert log[0]["from_state"] == "draft"
        assert log[0]["to_state"] == "reviewed"
        assert log[0]["transitioned_by"] == "djm"

    def test_transition_nonexistent_raises(self, store):
        from bve.entities.company_snapshot import ReviewerState
        with pytest.raises(ValueError, match="not found"):
            store.transition_state("does-not-exist", ReviewerState.REVIEWED,
                                   reviewer="djm", reason="test")

    def test_mark_stale(self, store):
        from bve.entities.company_snapshot import ReviewerState
        snap = _make_snapshot()
        old_id = store.insert_snapshot(snap)
        stale = store.mark_stale(old_id, "Catalyst passed without pack update")
        assert stale.reviewer_state == ReviewerState.STALE
        assert stale.stale_since is not None
        assert "Catalyst passed" in stale.stale_reason

    def test_insert_only_no_duplicate_id(self, store):
        snap = _make_snapshot()
        store.insert_snapshot(snap)
        with pytest.raises(Exception):  # IntegrityError
            store.insert_snapshot(snap)

    def test_buckets_round_trip(self, store):
        b1 = _make_bucket("b1", "modeled_asset", 400.0)
        b2 = _make_bucket("b2", "platform", 100.0, methodology="analyst_estimate",
                          source_type="analyst_bridge")
        snap = _make_snapshot(modeled_assets=[b1])
        from bve.entities.company_snapshot import CompanySnapshot
        snap = CompanySnapshot(**{
            **snap.model_dump(),
            "platform_value": b2,
        })
        sid = store.insert_snapshot(snap)
        retrieved = store.get_snapshot(sid)
        assert len(retrieved.modeled_assets) == 1
        assert retrieved.modeled_assets[0].value_millions == pytest.approx(400.0)
        assert retrieved.platform_value is not None
        assert retrieved.platform_value.value_millions == pytest.approx(100.0)

    def test_dilution_bridge_round_trip(self, store):
        from bve.entities.company_snapshot import DilutionBridge
        bridge = DilutionBridge(
            current_shares_millions=141.5,
            expected_dilution_pct=0.08,
            warrant_shares_millions=3.2,
        )
        snap = _make_snapshot(dilution_bridge=bridge)
        sid = store.insert_snapshot(snap)
        retrieved = store.get_snapshot(sid)
        assert retrieved.dilution_bridge is not None
        assert retrieved.dilution_bridge.current_shares_millions == pytest.approx(141.5)
        assert retrieved.dilution_bridge.expected_dilution_pct == pytest.approx(0.08)

    def test_catalysts_round_trip(self, store):
        from bve.entities.company_snapshot import CatalystEntry, CompanySnapshot
        c = CatalystEntry(
            description="Ph3 readout",
            expected_date="2026-Q3",
            probability_positive=0.65,
        )
        snap = CompanySnapshot(**{
            **_make_snapshot().model_dump(),
            "catalysts": [c],
        })
        sid = store.insert_snapshot(snap)
        retrieved = store.get_snapshot(sid)
        assert len(retrieved.catalysts) == 1
        assert retrieved.catalysts[0].description == "Ph3 readout"

    def test_management_flags_round_trip(self, store):
        from bve.entities.company_snapshot import CompanySnapshot, ManagementFlag
        f = ManagementFlag(
            flag_type="going_concern",
            flagged_date=date(2026, 1, 1),
            severity="critical",
            description="Going concern warning",
        )
        snap = CompanySnapshot(**{
            **_make_snapshot().model_dump(),
            "management_flags": [f],
        })
        sid = store.insert_snapshot(snap)
        retrieved = store.get_snapshot(sid)
        assert len(retrieved.management_flags) == 1
        assert retrieved.management_flags[0].severity == "critical"


# ---------------------------------------------------------------------------
# snapshot_bridge — load_underwriting_pack
# ---------------------------------------------------------------------------

class TestLoadUnderwritingPack:

    def _write_pack(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / "pack.yaml"
        p.write_text(yaml.dump(data))
        return p

    def _minimal_pack_data(self) -> dict:
        return {
            "company_id": "test",
            "company_name": "Test Co",
            "ticker": "TEST",
            "as_of_date": "2026-04-01",
            "market": {
                "market_cap_millions": 1000.0,
                "enterprise_value_millions": 800.0,
                "share_price": 10.0,
                "source_ref": "yfinance:2026-04-01",
            },
            "balance_sheet": {
                "cash_millions": 200.0,
                "debt_millions": 0.0,
                "source_ref": "10-Q:2025-12-31",
            },
            "confidence": {"overall_confidence": 0.70},
            "provenance": {"pack_version": 1, "created_by": "test"},
            "reviewer_state": "draft",
        }

    def test_load_minimal_pack(self, tmp_path):
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        p = self._write_pack(tmp_path, self._minimal_pack_data())
        snap = load_underwriting_pack(p)
        assert snap.ticker == "TEST"
        assert snap.market_cap_millions == pytest.approx(1000.0)
        assert snap.cash_millions == pytest.approx(200.0)

    def test_load_with_modeled_assets(self, tmp_path):
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        data = self._minimal_pack_data()
        data["modeled_assets"] = [{
            "bucket_id": "test_asset1",
            "label": "Drug A",
            "value_millions": 500.0,
            "methodology": "rnpv",
            "source_type": "modeled",
            "source_ref": "bve-asset:configs/test.yaml",
            "as_of_date": "2026-04-01",
            "confidence": 0.80,
        }]
        p = self._write_pack(tmp_path, data)
        snap = load_underwriting_pack(p)
        assert len(snap.modeled_assets) == 1
        assert snap.modeled_assets[0].value_millions == pytest.approx(500.0)

    def test_load_with_dilution_bridge(self, tmp_path):
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        data = self._minimal_pack_data()
        data["dilution"] = {
            "current_shares_millions": 100.0,
            "expected_dilution_pct": 0.10,
            "financing_runway_quarters": 8.0,
            "atm_active": False,
            "warrant_shares_millions": 2.0,
            "convertible_shares_millions": 0.0,
            "source_ref": "10-Q:2025-12-31",
            "as_of_date": "2025-12-31",
        }
        p = self._write_pack(tmp_path, data)
        snap = load_underwriting_pack(p)
        assert snap.dilution_bridge is not None
        assert snap.dilution_bridge.current_shares_millions == pytest.approx(100.0)
        assert snap.dilution_bridge.fully_diluted_shares_millions == pytest.approx(112.0)

    def test_load_with_catalysts(self, tmp_path):
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        data = self._minimal_pack_data()
        data["catalysts"] = [{"description": "Ph3 readout", "expected_date": "2026-Q3",
                              "catalyst_type": "readout", "probability_positive": 0.65}]
        p = self._write_pack(tmp_path, data)
        snap = load_underwriting_pack(p)
        assert len(snap.catalysts) == 1
        assert snap.catalysts[0].probability_positive == pytest.approx(0.65)

    def test_load_reviewer_state_preserved(self, tmp_path):
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        from bve.entities.company_snapshot import ReviewerState
        data = self._minimal_pack_data()
        data["reviewer_state"] = "reviewed"
        p = self._write_pack(tmp_path, data)
        snap = load_underwriting_pack(p)
        assert snap.reviewer_state == ReviewerState.REVIEWED

    def test_load_missing_file_raises(self):
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        with pytest.raises(FileNotFoundError):
            load_underwriting_pack("/nonexistent/path/pack.yaml")

    def test_load_vktx_pack(self):
        """Load the actual VKTX pack and verify it parses correctly."""
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        pack_path = Path(__file__).parents[1] / "examples/packs/vktx.yaml"
        if not pack_path.exists():
            pytest.skip("VKTX pack not found")
        snap = load_underwriting_pack(pack_path)
        assert snap.ticker == "VKTX"
        assert snap.company_id == "vktx"
        assert len(snap.modeled_assets) == 2
        assert len(snap.catalysts) == 3
        assert snap.dilution_bridge is not None
        assert snap.dilution_bridge.current_shares_millions == pytest.approx(141.5)
        assert snap.sotp_equity_value_millions > 0

    def test_template_pack_loads(self):
        """Verify the template YAML loads without error."""
        from bve.analysis.snapshot_bridge import load_underwriting_pack
        pack_path = Path(__file__).parents[1] / "examples/packs/underwriting_pack_template.yaml"
        if not pack_path.exists():
            pytest.skip("Template pack not found")
        snap = load_underwriting_pack(pack_path)
        assert snap.ticker == "TICKER"

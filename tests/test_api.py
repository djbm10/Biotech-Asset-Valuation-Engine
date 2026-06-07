"""Tests for FastAPI endpoints (Step 13).

Uses in-memory SQLite + TestClient — no server required.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import sqlalchemy as sa  # noqa: E402

from tests.asgi_client import SyncASGIClient  # noqa: E402
from bve.persistence.db import Base  # noqa: E402
from bve.persistence.models import (  # noqa: E402
    Asset,
    Catalyst,
    Company,
    DecisionRecord,
    EvidenceItem,
    AcquisitionScore,
    ParameterVersion,
    VariantThesis,
)


# ---------------------------------------------------------------------------
# App fixture — fresh DB per test module
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """Create test client with a StaticPool in-memory SQLite DB (single shared connection)."""
    from sqlalchemy.pool import StaticPool

    test_engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable FK pragma on the shared connection
    @sa.event.listens_for(test_engine, "connect")
    def set_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=test_engine)
    TestSession = sa.orm.sessionmaker(bind=test_engine, autocommit=False, autoflush=False)

    from apps.api.main import app
    from apps.api.deps import get_db

    def override_get_db():
        db = TestSession()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed before starting client
    db = TestSession()
    _seed_test_data(db)
    db.commit()
    db.close()

    yield SyncASGIClient(app)

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def _seed_test_data(db):
    """Insert minimal test fixtures."""
    # Company + asset
    company = Company(
        id="co-mrna",
        ticker="MRNA",
        name="Moderna",
        company_type="public_biotech",
        market_cap=20_000.0,
        cash=5_000.0,
    )
    db.add(company)

    asset = Asset(
        id="asset-mrna-covid",
        company_id="co-mrna",
        name="mRNA-1273",
        modality="mRNA",
        therapeutic_area="infectious_disease",
        indication="COVID-19",
        current_phase="Approved",
        partnered=False,
    )
    db.add(asset)

    # Catalyst
    catalyst = Catalyst(
        asset_id="asset-mrna-covid",
        catalyst_type="label_expansion",
        expected_date="2026-06-01",
        status="pending",
        confidence=0.7,
    )
    db.add(catalyst)

    # Variant thesis
    thesis = VariantThesis(
        asset_id="asset-mrna-covid",
        market_view={"implied_pos": 0.50},
        model_view={"model_pos": 0.70},
        delta_view={"gap": 0.20},
        kill_criteria=["trial fails primary endpoint"],
        confidence=0.65,
        documented=True,
        status="active",
    )
    db.add(thesis)

    # Evidence item
    evidence = EvidenceItem(
        source_type="press_release",
        title="Moderna announces Phase 3 results",
        raw_text="Moderna reports positive Phase 3 data.",
        checksum="abc123test",
        materiality_score=0.85,
    )
    db.add(evidence)

    # Acquirer + target for deals
    acquirer_co = Company(
        id="co-pfizer",
        ticker="PFE",
        name="Pfizer",
        company_type="big_pharma",
        cash=15_000.0,
    )
    db.add(acquirer_co)

    acq_score = AcquisitionScore(
        target_company_id="co-mrna",
        acquirer_company_id="co-pfizer",
        fit_score=0.72,
        timing_bucket="6-12m",
        affordability_score=0.80,
        strategic_fit_score=0.75,
        confidence=0.65,
    )
    db.add(acq_score)

    # Decision + parameter version
    pv = ParameterVersion(
        id="pv-base",
        name="base",
        version="1.0",
        weights={"strategic": 0.25},
        promoted=True,
    )
    db.add(pv)

    decision = DecisionRecord(
        id="dec-001",
        asset_id="asset-mrna-covid",
        decision_type="trade",
        recommendation={"action": "add", "size_pct": 2.5},
        parameter_version_id="pv-base",
    )
    db.add(decision)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

class TestHealth:
    def test_liveness(self, client):
        r = client.get("/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_readiness(self, client):
        r = client.get("/health/ready")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# /api/assets
# ---------------------------------------------------------------------------

class TestAssetsEndpoints:
    def test_list_assets_returns_200(self, client):
        r = client.get("/api/assets/")
        assert r.status_code == 200

    def test_list_assets_returns_list(self, client):
        r = client.get("/api/assets/")
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_assets_filter_ta(self, client):
        r = client.get("/api/assets/?ta=infectious_disease")
        data = r.json()
        assert all(
            "infectious" in (d.get("therapeutic_area") or "").lower()
            for d in data
        )

    def test_list_assets_filter_phase(self, client):
        r = client.get("/api/assets/?phase=Approved")
        data = r.json()
        assert all(d.get("current_phase") == "Approved" for d in data)

    def test_list_assets_filter_ticker(self, client):
        r = client.get("/api/assets/?ticker=MRNA")
        data = r.json()
        assert len(data) >= 1

    def test_list_assets_unknown_ticker_empty(self, client):
        r = client.get("/api/assets/?ticker=ZZZNOTEXIST")
        assert r.status_code == 200
        assert r.json() == []

    def test_get_asset_page_found(self, client):
        r = client.get("/api/assets/MRNA")
        assert r.status_code == 200
        data = r.json()
        assert "asset" in data
        assert "trials" in data
        assert "catalysts" in data

    def test_get_asset_page_has_catalyst(self, client):
        r = client.get("/api/assets/MRNA")
        data = r.json()
        catalysts = data["catalysts"]
        assert any(c["catalyst_type"] == "label_expansion" for c in catalysts)

    def test_get_asset_page_has_variant_thesis(self, client):
        r = client.get("/api/assets/MRNA")
        data = r.json()
        assert data["variant_thesis"] is not None
        assert data["variant_thesis"]["confidence"] == 0.65

    def test_get_asset_page_404(self, client):
        r = client.get("/api/assets/ZZZNONE")
        assert r.status_code == 404

    def test_asset_card_fields(self, client):
        r = client.get("/api/assets/")
        cards = r.json()
        if cards:
            card = cards[0]
            assert "id" in card
            assert "name" in card
            assert "current_phase" in card
            assert "partnered" in card


# ---------------------------------------------------------------------------
# /api/acquirers
# ---------------------------------------------------------------------------

class TestAcquirersEndpoints:
    def test_list_acquirers_returns_200(self, client):
        r = client.get("/api/acquirers/")
        assert r.status_code == 200

    def test_list_acquirers_contains_pfizer(self, client):
        r = client.get("/api/acquirers/")
        data = r.json()
        names = [d["company_name"] for d in data]
        assert "Pfizer" in names

    def test_acquirer_card_fields(self, client):
        r = client.get("/api/acquirers/")
        data = r.json()
        assert len(data) > 0
        card = data[0]
        assert "company_id" in card
        assert "cash_firepower_millions" in card
        assert "strategic_areas" in card
        assert "loe_urgency" in card

    def test_get_acquirer_page_pfizer(self, client):
        r = client.get("/api/acquirers/pfizer")
        assert r.status_code == 200
        data = r.json()
        assert "profile" in data
        assert data["profile"]["name"] == "Pfizer"

    def test_get_acquirer_page_loe_cliffs(self, client):
        r = client.get("/api/acquirers/pfizer")
        data = r.json()
        assert isinstance(data["profile"]["loe_cliffs"], list)

    def test_get_acquirer_page_not_found(self, client):
        r = client.get("/api/acquirers/zzz_nonexistent")
        assert r.status_code == 404

    def test_get_acquirer_top_targets_list(self, client):
        r = client.get("/api/acquirers/pfizer")
        data = r.json()
        assert isinstance(data["top_targets"], list)


# ---------------------------------------------------------------------------
# /api/deals
# ---------------------------------------------------------------------------

class TestDealsEndpoints:
    def test_list_deals_returns_200(self, client):
        r = client.get("/api/deals/")
        assert r.status_code == 200

    def test_list_deals_contains_seeded_pair(self, client):
        r = client.get("/api/deals/")
        data = r.json()
        assert len(data) >= 1
        assert any(
            d["target_name"] == "Moderna" and d["acquirer_name"] == "Pfizer"
            for d in data
        )

    def test_deals_min_fit_score_filter(self, client):
        r = client.get("/api/deals/?min_fit_score=0.90")
        data = r.json()
        assert all(d["fit_score"] >= 0.90 for d in data)

    def test_deals_timing_bucket_filter(self, client):
        r = client.get("/api/deals/?timing_bucket=6-12m")
        data = r.json()
        assert all(d["timing_bucket"] == "6-12m" for d in data)

    def test_deals_acquirer_filter(self, client):
        r = client.get("/api/deals/?acquirer=PFE")
        data = r.json()
        assert all(d["acquirer_name"] == "Pfizer" for d in data)

    def test_deals_unknown_acquirer_empty(self, client):
        r = client.get("/api/deals/?acquirer=ZZZNOTEXIST")
        assert r.status_code == 200
        assert r.json() == []

    def test_deal_card_fields(self, client):
        r = client.get("/api/deals/")
        data = r.json()
        if data:
            card = data[0]
            assert "fit_score" in card
            assert "timing_bucket" in card
            assert "target_name" in card
            assert "acquirer_name" in card


# ---------------------------------------------------------------------------
# /api/alerts
# ---------------------------------------------------------------------------

class TestAlertsEndpoints:
    def test_list_alerts_returns_200(self, client):
        r = client.get("/api/alerts/")
        assert r.status_code == 200

    def test_list_alerts_contains_seeded_item(self, client):
        r = client.get("/api/alerts/?min_materiality=0.5")
        data = r.json()
        titles = [d["title"] for d in data]
        assert any("Phase 3" in (t or "") for t in titles)

    def test_alert_card_fields(self, client):
        r = client.get("/api/alerts/")
        data = r.json()
        if data:
            card = data[0]
            assert "id" in card
            assert "materiality_score" in card

    def test_alerts_min_materiality_filter(self, client):
        r = client.get("/api/alerts/?min_materiality=0.99")
        data = r.json()
        assert all((d["materiality_score"] or 0) >= 0.99 for d in data)


# ---------------------------------------------------------------------------
# /api/calibration
# ---------------------------------------------------------------------------

class TestCalibrationEndpoints:
    def test_calibration_returns_200(self, client):
        r = client.get("/api/calibration/")
        assert r.status_code == 200

    def test_calibration_has_counts(self, client):
        r = client.get("/api/calibration/")
        data = r.json()
        assert "total_decisions" in data
        assert "total_outcomes" in data
        assert "pending_parameter_versions" in data
        assert data["total_decisions"] >= 1

    def test_calibration_promoted_versions(self, client):
        r = client.get("/api/calibration/")
        data = r.json()
        assert isinstance(data["promoted_versions"], list)
        assert any(pv["version"] == "1.0" for pv in data["promoted_versions"])


# ---------------------------------------------------------------------------
# /api/theses + /api/postmortems
# ---------------------------------------------------------------------------

class TestThesesEndpoints:
    def test_create_thesis_returns_201(self, client):
        # First we need an asset — use seeded one
        r = client.post(
            "/api/theses/asset-mrna-covid",
            json={
                "market_view": {"implied_pos": 0.40},
                "model_view": {"model_pos": 0.65},
                "delta_view": {"gap": 0.25},
                "kill_criteria": ["Phase 3 failure"],
                "confidence": 0.70,
                "documented": True,
            },
        )
        assert r.status_code == 201
        assert "id" in r.json()

    def test_create_thesis_undocumented_rejected(self, client):
        r = client.post(
            "/api/theses/asset-mrna-covid",
            json={
                "market_view": {},
                "model_view": {},
                "delta_view": {},
                "kill_criteria": [],
                "confidence": 0.5,
                "documented": False,
            },
        )
        assert r.status_code == 422

    def test_create_thesis_unknown_asset_404(self, client):
        r = client.post(
            "/api/theses/nonexistent-asset-id",
            json={
                "market_view": {}, "model_view": {}, "delta_view": {},
                "kill_criteria": [], "confidence": 0.5, "documented": True,
            },
        )
        assert r.status_code == 404

    def test_create_postmortem_returns_201(self, client):
        r = client.post(
            "/api/postmortems/dec-001",
            json={
                "realized_outcome": {"return_pct": 15.2, "attribution": "confirmed_thesis"},
            },
        )
        assert r.status_code == 201

    def test_create_postmortem_duplicate_409(self, client):
        # Already created above — second attempt should fail
        r = client.post(
            "/api/postmortems/dec-001",
            json={"realized_outcome": {"return_pct": 5.0}},
        )
        assert r.status_code == 409

    def test_create_postmortem_unknown_decision_404(self, client):
        r = client.post(
            "/api/postmortems/nonexistent-dec",
            json={"realized_outcome": {"return_pct": 0.0}},
        )
        assert r.status_code == 404

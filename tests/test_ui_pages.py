"""Tests for Step 13 UI pages."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("BVE_SKIP_STARTUP_TABLES", "1")

import sqlalchemy as sa  # noqa: E402

from tests.asgi_client import SyncASGIClient  # noqa: E402
from bve.persistence.db import Base  # noqa: E402
from bve.persistence.models import (  # noqa: E402
    AcquisitionScore,
    Asset,
    Catalyst,
    Company,
    DecisionRecord,
    EvidenceItem,
    ParameterVersion,
    VariantThesis,
)


@pytest.fixture(scope="module")
def client():
    from sqlalchemy.pool import StaticPool

    test_engine = sa.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

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

    db = TestSession()
    company = Company(
        id="co-mrna",
        ticker="MRNA",
        name="Moderna",
        company_type="public_biotech",
        market_cap=20_000.0,
        cash=5_000.0,
    )
    db.add(company)
    db.add(
        Asset(
            id="asset-mrna-covid",
            company_id="co-mrna",
            name="mRNA-1273",
            modality="mRNA",
            therapeutic_area="infectious_disease",
            indication="COVID-19",
            current_phase="Approved",
            partnered=False,
        )
    )
    db.add(
        Catalyst(
            asset_id="asset-mrna-covid",
            catalyst_type="label_expansion",
            expected_date="2026-06-01",
            status="pending",
            confidence=0.7,
        )
    )
    db.add(
        VariantThesis(
            asset_id="asset-mrna-covid",
            market_view={"implied_pos": 0.50},
            model_view={"model_pos": 0.70},
            delta_view={"gap": 0.20},
            kill_criteria=["trial fails primary endpoint"],
            confidence=0.65,
            documented=True,
            status="active",
        )
    )
    db.add(
        EvidenceItem(
            source_type="press_release",
            title="Moderna announces Phase 3 results",
            raw_text="Moderna reports positive Phase 3 data.",
            checksum="abc123test-ui",
            materiality_score=0.85,
        )
    )
    db.add(
        Company(
            id="co-pfizer",
            ticker="PFE",
            name="Pfizer",
            company_type="big_pharma",
            cash=15_000.0,
        )
    )
    db.add(
        AcquisitionScore(
            target_company_id="co-mrna",
            acquirer_company_id="co-pfizer",
            fit_score=0.72,
            timing_bucket="6-12m",
            affordability_score=0.80,
            strategic_fit_score=0.75,
            confidence=0.65,
        )
    )
    db.add(
        ParameterVersion(
            id="pv-base",
            name="base",
            version="1.0",
            weights={"strategic": 0.25},
            promoted=True,
        )
    )
    db.add(
        DecisionRecord(
            id="dec-001",
            asset_id="asset-mrna-covid",
            decision_type="trade",
            recommendation={"action": "add", "size_pct": 2.5},
            parameter_version_id="pv-base",
        )
    )
    db.commit()
    db.close()

    yield SyncASGIClient(app)

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_dashboard_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Daily biotech decision surface" in response.text
    assert "Tracked Assets" in response.text
    assert "Operator Paths" in response.text
    assert 'href="/assets/MRNA"' in response.text


def test_asset_page_renders(client):
    response = client.get("/assets/MRNA")
    assert response.status_code == 200
    assert "mRNA-1273" in response.text
    assert "Variant Thesis" in response.text
    assert "Deal Readthrough" in response.text


def test_acquirer_page_renders(client):
    response = client.get("/acquirers/pfizer")
    assert response.status_code == 200
    assert "Pfizer" in response.text
    assert "Top Targets" in response.text
    assert 'href="/assets/MRNA"' in response.text


def test_acquirer_index_page_renders(client):
    response = client.get("/acquirers")
    assert response.status_code == 200
    assert "Tracked large-cap buyers" in response.text
    assert 'href="/acquirers/pfizer"' in response.text


def test_deals_page_renders(client):
    response = client.get("/deals")
    assert response.status_code == 200
    assert "Ranked target-acquirer pairs" in response.text
    assert "Moderna" in response.text
    assert "Apply Filters" in response.text
    assert 'href="/acquirers/pfizer"' in response.text


def test_deals_page_filters_round_trip(client):
    response = client.get("/deals?acquirer=PFE&timing_bucket=6-12m&min_fit_score=0.70")
    assert response.status_code == 200
    assert "PFE" in response.text
    assert "6-12m" in response.text
    assert "0.70" in response.text


def test_alerts_page_renders(client):
    response = client.get("/alerts")
    assert response.status_code == 200
    assert "Material evidence feed" in response.text
    assert "Phase 3 results" in response.text
    assert "Apply Filters" in response.text


def test_calibration_page_renders(client):
    response = client.get("/calibration")
    assert response.status_code == 200
    assert "Calibration" in response.text
    assert "Promoted Versions" in response.text
    assert "Promoted" in response.text
